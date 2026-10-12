"""«Вопрос акиму» для шлюза R01 (kind="service"): make_service(db_path).handle(...) -> {"status", "headers", "body"}.

Маршруты (префикс /api/civic/v2; схема экрана — R11 IA_WAVE2 §7):
  GET  /questions?tab=top|new|answered&district=&device_id=   житель: опубликованные вопросы, «Вы поддержали»
  POST /questions {text, district, lang?, device_id, request_id?} житель: вопрос на проверку -> 201 {question}
  POST /questions/{id}/vote {device_id}                         житель: «Поддержать» (одно устройство — один голос)
  GET  /questions/staff?tab=queue|top|answered&district=        сотрудник: проверка, топ-5 недели, отвечено
  POST /questions/{id}/publish                                  сотрудник: опубликовать
  POST /questions/{id}/reject {reason, note?}                   сотрудник: отклонить с причиной (или снять с публикации)
  POST /questions/{id}/answer {answer_ru?, answer_kk?}          сотрудник: ответ акима (хотя бы на одном языке)

Сотрудник — сессия R02 (principal от шлюза) + для записи X-CSRF-Token и свой Origin (как у R09, R15 S05/S17).
Ответ ошибки — {"error": код, "message": текст по-русски, "field"?: поле} — так же, как v2_error шлюза.
Публично не отдаём: хэш устройства, логин сотрудника, отклонённые и непроверенные вопросы, причину отказа.
Грубые слова в публичных ответах звёздочками закрывает шлюз (public_text, R04); сотруднику — пометка rude.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import re
from urllib.parse import parse_qs

from .store import Conflict, QuestionStore, iso

PREFIX = "/api/civic/v2"
DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
LANGS = ("ru", "kk")
TEXT_MIN, TEXT_MAX = 10, 300
ANSWER_MAX = 1500
NOTE_MAX = 200
WEEKLY_TOP = 5  # «Раз в неделю аким отвечает на 5 вопросов с наибольшим числом голосов» (ask.rule)
LIST_LIMIT = 30
REJECT_REASONS = ("personal_data", "rude", "not_question", "duplicate", "other")
DEVICE_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
REQUEST_RE = re.compile(r"[A-Za-z0-9._:-]{8,64}\Z")
ID_RE = re.compile(r"q-[a-z0-9-]{4,40}\Z")
ASTANA = timezone(timedelta(hours=5))

# Подсказка модератору «похоже на личные данные» (сам вопрос не меняем: решает человек, причина — personal_data).
PII_PATTERNS = (
    ("phone", re.compile(r"(?<![\d+])(?:(?:\+\s*)?[78][\s(-]*)?7(?:[\s().-]{0,2}\d){9}(?!\d)")),
    ("iin", re.compile(r"(?<!\d)(?:\d[\s-]?){11}\d(?!\d)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field


def _reply(status: int, body: dict) -> dict:
    return {"status": status, "headers": {}, "body": body}


def _header(context, name: str):
    headers = (context or {}).get("headers") or {}
    return headers.get(name.lower()) or headers.get(name)


def _is_staff(principal) -> bool:
    if principal is None:
        return False
    flag = getattr(principal, "is_staff", None)
    if isinstance(flag, bool):
        return flag
    role = getattr(principal, "role", None) or (principal.get("role") if isinstance(principal, dict) else None)
    return role in ("editor", "admin", "staff")


def _actor(principal) -> str:
    name = getattr(principal, "username", None) or (principal.get("username") if isinstance(principal, dict) else None)
    return str(name or "staff")[:64]


def pii_kinds(text: str) -> list[str]:
    return [kind for kind, rx in PII_PATTERNS if rx.search(text or "")]


def _rude(text: str):
    """Пометка для сотрудника (фильтр R04). Нет модуля — None: экран просто не показывает пометку."""
    try:
        from ui.civic_ml_api import profanity
    except Exception:
        return None
    try:
        return bool(profanity.is_rude(text))
    except Exception:
        return None


def clean_text(value, *, field: str, low: int, high: int) -> str:
    if not isinstance(value, str):
        raise ApiError(422, "invalid", "Напишите текст.", field)
    text = re.sub(r"[ \t ]+", " ", value.replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable())
    if len(text) < low:
        raise ApiError(422, "too_short", f"Слишком коротко: нужно хотя бы {low} символов.", field)
    if len(text) > high:
        raise ApiError(422, "too_long", f"Слишком длинно: не больше {high} символов.", field)
    return text


def week_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Неделя по времени Астаны: понедельник 00:00 — следующий понедельник 00:00 (в UTC)."""
    local = now.astimezone(ASTANA)
    start = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc), (start + timedelta(days=7)).astimezone(timezone.utc)


class QuestionService:
    def __init__(self, store: QuestionStore):
        self.store = store

    # ------------------------------------------------------------------ вход
    def handle(self, method, path, query=None, body=None, principal=None, context=None):
        try:
            return self._route(method.upper(), path, query, body, principal, context or {})
        except ApiError as exc:
            out = {"error": exc.code, "message": exc.message}
            if exc.field:
                out["field"] = exc.field
            return _reply(exc.status, out)
        except Conflict as exc:
            return _reply(409, {"error": exc.code, "message": exc.message})
        except LookupError:
            return _reply(404, {"error": "not_found", "message": "Вопрос не найден."})

    def _route(self, method, path, query, body, principal, context):
        rel = path[len(PREFIX):] if path.startswith(PREFIX) else path
        rel = rel.split("?", 1)[0]
        parts = [p for p in rel.strip("/").split("/") if p]
        q = self._query(query)
        body = body if isinstance(body, dict) else {}
        if not parts or parts[0] != "questions":
            return None
        if len(parts) == 1:
            if method == "GET":
                return self.list_public(q, context)
            if method == "POST":
                return self.create(body, context)
            raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
        if parts == ["questions", "staff"]:
            if method != "GET":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            self._require_staff(principal, context, unsafe=False)
            return self.list_staff(q)
        if len(parts) == 3 and method == "POST":
            qid, action = parts[1], parts[2]
            if not ID_RE.match(qid):
                raise LookupError(qid)
            if action == "vote":
                return self.vote(qid, body, context)
            if action in ("publish", "reject", "answer"):
                self._require_staff(principal, context, unsafe=True)
                if action == "publish":
                    return _reply(200, {"question": self._staff_view(self.store.publish(qid, _actor(principal)))})
                if action == "reject":
                    return self.reject(qid, body, principal)
                return self.answer(qid, body, principal)
        raise ApiError(404, "not_found", "Адрес API не найден.")

    @staticmethod
    def _query(query) -> dict:
        if isinstance(query, bytes):
            query = query.decode("utf-8", "replace")
        if isinstance(query, str):
            query = parse_qs(query.lstrip("?"), keep_blank_values=True)
        out = {}
        for key, value in (query or {}).items():
            if isinstance(value, (list, tuple)):
                value = value[-1] if value else ""
            out[str(key)] = "" if value is None else str(value)
        return out

    @staticmethod
    def _require_staff(principal, context, *, unsafe: bool):
        if context.get("host_allowed") is False:
            raise ApiError(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        if principal is None:
            raise ApiError(401, "unauthenticated", "Войдите как сотрудник акимата.")
        if not _is_staff(principal):
            raise ApiError(403, "forbidden", "Действие доступно только сотрудникам акимата.")
        if unsafe:
            if context.get("is_same_origin") is False:
                raise ApiError(403, "cross_origin", "Запрос с чужого сайта отклонён.")
            check = getattr(principal, "check_csrf", None)
            # Нет проверки CSRF у principal (другой формат сессии) — отказ, а не пропуск (R15 S05).
            if not callable(check) or not check(_header(context, "X-CSRF-Token")):
                raise ApiError(403, "csrf_failed", "Сессия устарела. Обновите страницу.")

    @staticmethod
    def _device(body, context, q=None, required=True):
        device = _header(context, "X-Birge-Device") or (body or {}).get("device_id") or (q or {}).get("device_id")
        if device in (None, "") and not required:
            return None
        if not isinstance(device, str) or not DEVICE_RE.match(device):
            raise ApiError(400, "bad_request", "device_id: строка 8–128 символов.", "device_id")
        return device

    @staticmethod
    def _district(value, required: bool):
        if value in (None, ""):
            if required:
                raise ApiError(422, "invalid", "Выберите район.", "district")
            return None
        if value not in DISTRICTS:
            raise ApiError(422 if required else 400, "invalid", "Неизвестный район.", "district")
        return value

    # ------------------------------------------------------------------ виды записи
    @staticmethod
    def _public_view(row: dict, mine: bool = False) -> dict:
        answered = bool(row.get("answered_at"))
        return {
            "id": row["id"], "text": row["text"], "lang": row["lang"], "district": row["district"],
            "votes": int(row.get("votes") or 0), "published_at": row.get("published_at"),
            "answer": ({"ru": row.get("answer_ru"), "kk": row.get("answer_kk"), "answered_at": row["answered_at"],
                        "edited_at": row.get("answer_edited_at")} if answered else None),
            "demo": bool(row.get("demo")), "my_vote": bool(mine),
        }

    @staticmethod
    def _staff_view(row: dict) -> dict:
        view = QuestionService._public_view(row)
        view.update({"status": row["status"], "created_at": row["created_at"], "pii": pii_kinds(row["text"]),
                     "rude": _rude(row["text"]), "reject_reason": row.get("reject_reason")})
        view.pop("my_vote", None)
        return view

    # ------------------------------------------------------------------ житель
    def list_public(self, q: dict, context) -> dict:
        tab = q.get("tab") or "top"
        if tab not in ("top", "new", "answered"):
            raise ApiError(400, "bad_request", "tab: top, new или answered.", "tab")
        district = self._district(q.get("district"), required=False)
        device = self._device({}, context, q, required=False)
        # «Популярные» — без ответа (ответ — во вкладке «С ответом»); «Новые» — все опубликованные по дате.
        rows = {
            "top": lambda: self.store.list(status="published", answered=False, district=district, order="votes",
                                           limit=LIST_LIMIT),
            "new": lambda: self.store.list(status="published", district=district, order="new", limit=LIST_LIMIT),
            "answered": lambda: self.store.list(status="published", answered=True, district=district,
                                                order="answered", limit=LIST_LIMIT),
        }[tab]()
        mine = self.store.voted([r["id"] for r in rows], device)
        counts = {"top": self.store.count(status="published", answered=False, district=district),
                  "new": self.store.count(status="published", district=district),
                  "answered": self.store.count(status="published", answered=True, district=district)}
        return _reply(200, {"tab": tab, "district": district, "items": [self._public_view(r, r["id"] in mine)
                                                                         for r in rows],
                            "counts": counts, "weekly_top": WEEKLY_TOP, "limits": {"text_min": TEXT_MIN,
                                                                                    "text_max": TEXT_MAX}})

    def create(self, body: dict, context) -> dict:
        if context.get("host_allowed") is False or context.get("is_same_origin") is False:
            raise ApiError(403, "forbidden", "Запрос с чужого сайта отклонён.")
        device = self._device(body, context)
        text = clean_text(body.get("text"), field="text", low=TEXT_MIN, high=TEXT_MAX)
        district = self._district(body.get("district"), required=True)
        lang = body.get("lang") if body.get("lang") in LANGS else "ru"
        request_id = body.get("request_id")
        if request_id is not None and (not isinstance(request_id, str) or not REQUEST_RE.match(request_id)):
            raise ApiError(400, "bad_request", "request_id: строка 8–64 символа.", "request_id")
        row, created = self.store.create(text=text, lang=lang, district=district, device_id=device,
                                         request_id=request_id)
        # Житель видит только номер и «на проверке» — ни текста в чужих списках, ни голосов до публикации.
        return _reply(201 if created else 200, {"question": {"id": row["id"], "status": row["status"]},
                                                "created": created})

    def vote(self, qid: str, body: dict, context) -> dict:
        if context.get("host_allowed") is False or context.get("is_same_origin") is False:
            raise ApiError(403, "forbidden", "Запрос с чужого сайта отклонён.")
        device = self._device(body, context)
        result, created = self.store.vote(qid, device)
        return _reply(200, dict(result, created=created))

    # ------------------------------------------------------------------ сотрудник
    def list_staff(self, q: dict) -> dict:
        tab = q.get("tab") or "queue"
        if tab not in ("queue", "top", "answered"):
            raise ApiError(400, "bad_request", "tab: queue, top или answered.", "tab")
        district = self._district(q.get("district"), required=False)
        now = self.store.now()
        start, end = week_bounds(now)
        if tab == "queue":
            rows = self.store.list(status="pending", district=district, order="queue", limit=50)
        elif tab == "top":
            rows = self.store.list(status="published", answered=False, district=district, order="votes",
                                   limit=WEEKLY_TOP)
        else:
            rows = self.store.list(status="published", answered=True, district=district, order="answered", limit=50)
        counts = {"queue": self.store.count(status="pending", district=district),
                  "top": min(WEEKLY_TOP, self.store.count(status="published", answered=False, district=district)),
                  "answered": self.store.count(status="published", answered=True, district=district)}
        week = {"start": iso(start), "end": iso(end), "limit": WEEKLY_TOP,
                "answered": self.store.count(status="published", answered=True, district=district,
                                             answered_since=iso(start))}
        return _reply(200, {"tab": tab, "district": district, "items": [self._staff_view(r) for r in rows],
                            "counts": counts, "week": week, "reasons": list(REJECT_REASONS)})

    def reject(self, qid: str, body: dict, principal) -> dict:
        reason = body.get("reason")
        if reason not in REJECT_REASONS:
            raise ApiError(422, "invalid", "Выберите причину отказа.", "reason")
        note = body.get("note")
        if note in (None, ""):
            note = None
        else:
            note = clean_text(note, field="note", low=1, high=NOTE_MAX)
        return _reply(200, {"question": self._staff_view(self.store.reject(qid, reason, note, _actor(principal)))})

    def answer(self, qid: str, body: dict, principal) -> dict:
        texts = {}
        for lang in LANGS:
            value = body.get("answer_" + lang)
            if value in (None, "") or (isinstance(value, str) and not value.strip()):
                texts[lang] = None
            else:
                texts[lang] = clean_text(value, field="answer_" + lang, low=10, high=ANSWER_MAX)
        if not texts["ru"] and not texts["kk"]:
            raise ApiError(422, "invalid", "Напишите ответ хотя бы на одном языке.", "answer_ru")
        row = self.store.answer(qid, texts["ru"], texts["kk"], _actor(principal))
        return _reply(200, {"question": self._staff_view(row)})


def make_service(db_path, *, clock=None, demo: bool | None = None) -> QuestionService:
    """Сервис на базе шлюза. demo=None — по переменной CIVIC_DEMO=1 (run-city.bat): тогда добавляются демо-вопросы."""
    from . import demo as demo_data  # локально: демо-тексты нужны только при засеве
    store = QuestionStore(db_path, clock=clock) if clock else QuestionStore(db_path)
    if (os.environ.get("CIVIC_DEMO") == "1") if demo is None else demo:
        store.seed(demo_data.rows(store.now()))
    return QuestionService(store)
