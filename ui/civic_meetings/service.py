"""«Встречи с акимом» для шлюза R01 (kind="service"): make_service(db_path).handle(...) -> {"status", "headers", "body"}.

Маршруты (префикс /api/civic/v2, CONTRACT §7):
  GET  /meetings?when=upcoming|past|all&district=&device_id=    все: список встреч (ближайшая — next_id)
  GET  /meetings/{id}?device_id=                                все: карточка — вопросы с голосами, поручения, итог
  GET  /meetings/updates?since=&device_id=                      житель: события для ленты R06 (CONTRACT §5.8)
  POST /meetings {district, title_ru, title_kk?, at, duration_min?, place:{kind?, id?, label_ru, label_kk?}, point?}
                                                                сотрудник: новая встреча (с "id" — правка/отмена)
  POST /meetings/{id}/order {text_ru, text_kk?, service, due, link?}           сотрудник: новое поручение
  POST /meetings/{id}/order {order_id, status? | due? | link? | text_ru? ...}  сотрудник: статус, срок, связь
  POST /meetings/{id}/result {result_ru?, result_kk?}           сотрудник: итог встречи (хотя бы на одном языке)
  POST /meetings/{id}/register {going?: true|false}             житель: «Приду» / «Не смогу» (одно устройство — раз)
  POST /meetings/{id}/question {text, lang?, request_id?}       житель: вопрос к встрече (на проверку, как «Вопрос акиму»)

Голос за вопрос встречи — общий маршрут «Вопроса акиму» POST /questions/{id}/vote; проверка вопросов — общая очередь
сотрудника GET /questions/staff?tab=queue (ui/civic_qa). Голосование закрывается к началу встречи.

Сотрудник — сессия R02 (principal от шлюза) + для записи X-CSRF-Token и свой Origin (как у R09 и «Вопроса акиму»).
Ответ ошибки — {"error": код, "message": текст по-русски, "field"?: поле} — так же, как v2_error шлюза.
Публично не отдаём: хэши устройств, кто именно нажал «Приду», логины сотрудников, непроверенные вопросы.
Ведущий встречи — «аким района» без имени (имени нет ни в базе, ни в ответах).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
import re
from urllib.parse import parse_qs

from .store import ORDER_STATUSES, Conflict, MeetingStore, iso, parse_iso

PREFIX = "/api/civic/v2"
DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
# Один справочник служб (CONTRACT §3): новых id не придумываем.
SERVICES = ("road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
            "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
            "parking", "akimat")
LINK_KINDS = ("complaint", "work", "project")
PLACE_KINDS = ("object", "segment", "area")
LANGS = ("ru", "kk")
ASTANA = timezone(timedelta(hours=5))
ASTANA_BOUNDS = (70.9, 50.9, 71.9, 51.4)  # как у шлюза R01: точка вне — ошибка ввода
TITLE_MIN, TITLE_MAX = 5, 120
LABEL_MAX = 120
ORDER_MIN, ORDER_MAX = 5, 300
RESULT_MIN, RESULT_MAX = 10, 1500
QUESTION_MIN, QUESTION_MAX = 10, 300
TOP_QUESTIONS = 10       # сколько вопросов показать в карточке встречи (по голосам)
LIST_LIMIT = 30
DEVICE_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
REQUEST_RE = re.compile(r"[A-Za-z0-9._:-]{8,64}\Z")
MEETING_ID_RE = re.compile(r"m-[A-Za-z0-9-]{1,40}\Z")
ORDER_ID_RE = re.compile(r"o-[A-Za-z0-9-]{1,40}\Z")
LINK_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")  # правило CIVIC_ID шлюза
TARGET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
HOST = {"ru": "Аким района", "kk": "Аудан әкімі"}  # ведущий — должность, без имени (IDEA §2A, CONTRACT §5.7)


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


def _clean(value, *, field: str, low: int, high: int, required: bool = True) -> str | None:
    """Текст без управляющих символов и лишних пробелов. Пусто и не обязательно — None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ApiError(422, "invalid", "Заполните поле.", field)
        return None
    if not isinstance(value, str):
        raise ApiError(422, "invalid", "Нужен текст.", field)
    text = re.sub(r"[ \t ]+", " ", value.replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable())
    if len(text) < low:
        raise ApiError(422, "too_short", f"Слишком коротко: нужно хотя бы {low} символов.", field)
    if len(text) > high:
        raise ApiError(422, "too_long", f"Слишком длинно: не больше {high} символов.", field)
    return text


def astana_date(moment: datetime) -> date:
    return moment.astimezone(ASTANA).date()


def service_names() -> dict:
    """Названия служб ru/kk — из таблицы R08 (CONTRACT §3: названия живут там); нет R08 — из справочника R09."""
    try:
        from ui.civic_akim import routing  # noqa: WPS433 — модуль соседа, только чтение
        names = routing.table().get("services") or {}
        if names:
            return {k: {"ru": v.get("ru"), "kk": v.get("kk")} for k, v in names.items() if k in SERVICES}
    except Exception:
        pass
    try:
        from ui.civic_feedback.v2.lifecycle import SERVICES as R09_SERVICES  # noqa: WPS433
        return {k: dict(v) for k, v in R09_SERVICES.items() if k in SERVICES}
    except Exception:
        return {}


class MeetingService:
    """Сервис встреч. qa — сервис «Вопроса акиму» (та же база): вопросы к встрече живут там."""

    def __init__(self, store: MeetingStore, qa=None):
        self.store = store
        self.qa = qa  # ui.civic_qa.QuestionService | None

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
            return _reply(404, {"error": "not_found", "message": "Встреча не найдена."})

    def _route(self, method, path, query, body, principal, context):
        rel = path[len(PREFIX):] if path.startswith(PREFIX) else path
        rel = rel.split("?", 1)[0]
        parts = [p for p in rel.strip("/").split("/") if p]
        q = self._query(query)
        body = body if isinstance(body, dict) else {}
        if not parts or parts[0] != "meetings":
            return None
        if len(parts) == 1:
            if method == "GET":
                return self.list_meetings(q, principal, context)
            if method == "POST":
                self._require_staff(principal, context, unsafe=True)
                return self.save_meeting(body, principal)
            raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
        if parts == ["meetings", "updates"]:
            if method != "GET":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            return self.updates_route(q, context)
        mid = parts[1]
        if not MEETING_ID_RE.match(mid):
            raise LookupError(mid)
        if len(parts) == 2:
            if method != "GET":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            return self.card(mid, q, principal, context)
        if len(parts) == 3:
            if method != "POST":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            action = parts[2]
            if action == "register":
                return self.register(mid, body, context)
            if action == "question":
                return self.ask(mid, body, context)
            if action in ("order", "result"):
                self._require_staff(principal, context, unsafe=True)
                return self.order(mid, body, principal) if action == "order" else self.result(mid, body, principal)
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
    def _resident_write(context):
        """Житель пишет только со своей страницы (как «Вопрос акиму»: R15 S05/S17)."""
        if context.get("host_allowed") is False or context.get("is_same_origin") is False:
            raise ApiError(403, "forbidden", "Запрос с чужого сайта отклонён.")

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
    def _phase(self, row: dict, now: datetime) -> str:
        """upcoming — ещё не началась; live — идёт; held — прошла; cancelled — отменена."""
        if row.get("status") == "cancelled":
            return "cancelled"
        start = parse_iso(row["at"])
        end = start + timedelta(minutes=int(row.get("duration_min") or 90))
        if now < start:
            return "upcoming"
        if now < end:
            return "live"
        return "held"

    @staticmethod
    def _order_view(row: dict, today: date, names: dict) -> dict:
        overdue = row["status"] != "done" and row["due"] < today.isoformat()
        link = {"kind": row["link_kind"], "id": row["link_id"]} if row.get("link_kind") and row.get("link_id") else None
        return {
            "id": row["id"], "text_ru": row["text_ru"], "text_kk": row.get("text_kk"), "service": row["service"],
            "service_name": names.get(row["service"]), "due": row["due"], "status": row["status"],
            "overdue": overdue, "link": link, "updated_at": row["updated_at"], "done_at": row.get("done_at"),
            "demo": bool(row.get("demo")),
        }

    @staticmethod
    def _order_counts(orders: list[dict]) -> dict:
        counts = {"total": len(orders), "todo": 0, "in_progress": 0, "done": 0, "overdue": 0}
        for o in orders:
            counts[o["status"]] += 1
            if o["overdue"]:
                counts["overdue"] += 1
        return counts

    def _summary(self, row: dict, now: datetime, orders: list[dict], qcounts: dict, mine: bool) -> dict:
        start = parse_iso(row["at"])
        place = None
        if row.get("place_label_ru") or row.get("place_id"):
            place = {"kind": row.get("place_kind"), "id": row.get("place_id"), "label_ru": row.get("place_label_ru"),
                     "label_kk": row.get("place_label_kk")}
        point = [row["lon"], row["lat"]] if row.get("lon") is not None and row.get("lat") is not None else None
        return {
            "id": row["id"], "district": row["district"], "title_ru": row["title_ru"], "title_kk": row.get("title_kk"),
            "at": row["at"], "ends_at": iso(start + timedelta(minutes=int(row.get("duration_min") or 90))),
            "duration_min": int(row.get("duration_min") or 90), "place": place, "point": point,
            "phase": self._phase(row, now), "registered": int(row.get("registered") or 0), "my_registration": mine,
            "questions_count": {"published": qcounts.get("published", 0), "answered": qcounts.get("answered", 0)},
            "orders_count": self._order_counts(orders), "has_result": bool(row.get("result_at")),
            "host": HOST, "demo": bool(row.get("demo")),
        }

    def _views(self, rows: list[dict], device: str | None) -> list[dict]:
        now = self.store.now()
        today = astana_date(now)
        names = service_names()
        ids = [r["id"] for r in rows]
        orders = self.store.orders(ids)
        qcounts = self.qa.store.meeting_counts(ids) if self.qa is not None else {}
        mine = self.store.registered_by(ids, device)
        out = []
        for row in rows:
            order_views = [self._order_view(o, today, names) for o in orders.get(row["id"], [])]
            out.append((row, order_views, self._summary(row, now, order_views, qcounts.get(row["id"], {}),
                                                        row["id"] in mine)))
        return out

    # ------------------------------------------------------------------ чтение (все)
    def list_meetings(self, q: dict, principal, context) -> dict:
        when = q.get("when") or "all"
        if when not in ("upcoming", "past", "all"):
            raise ApiError(400, "bad_request", "when: upcoming, past или all.", "when")
        district = self._district(q.get("district"), required=False)
        device = self._device({}, context, q, required=False)
        upcoming = self.store.list_meetings(district=district, when="upcoming", limit=LIST_LIMIT)
        past = self.store.list_meetings(district=district, when="past", limit=LIST_LIMIT)
        rows = {"upcoming": upcoming, "past": past, "all": upcoming + past}[when]
        items = [summary for _row, _orders, summary in self._views(rows, device)]
        next_id = upcoming[0]["id"] if upcoming else None
        return _reply(200, {"when": when, "district": district, "items": items, "next_id": next_id,
                            "counts": {"upcoming": len(upcoming), "past": len(past)}, "host": HOST,
                            "staff": _is_staff(principal), "services": service_names(),
                            "limits": {"question_min": QUESTION_MIN, "question_max": QUESTION_MAX}})

    def card(self, mid: str, q: dict, principal, context) -> dict:
        device = self._device({}, context, q, required=False)
        row = self.store.get_meeting(mid)
        (row, orders, summary), = self._views([row], device)
        meeting = dict(summary)
        meeting["orders"] = orders
        meeting["result"] = ({"ru": row.get("result_ru"), "kk": row.get("result_kk"), "at": row["result_at"]}
                             if row.get("result_at") else None)
        meeting["questions"] = []
        staff = _is_staff(principal)
        if self.qa is not None:
            qs = self.qa.store
            rows = qs.list(status="published", meeting=mid, order="votes", limit=TOP_QUESTIONS)
            mine = qs.voted([r["id"] for r in rows], device)
            meeting["questions"] = [self.qa._public_view(r, r["id"] in mine) for r in rows]
            if staff:
                pending = qs.list(status="pending", meeting=mid, order="queue", limit=50)
                meeting["pending_questions"] = [self.qa._staff_view(r) for r in pending]
        meeting["voting_open"] = summary["phase"] == "upcoming"
        return _reply(200, {"meeting": meeting, "staff": staff, "services": service_names()})

    # ------------------------------------------------------------------ житель
    def register(self, mid: str, body: dict, context) -> dict:
        self._resident_write(context)
        device = self._device(body, context)
        going = body.get("going", True)
        if not isinstance(going, bool):
            raise ApiError(400, "bad_request", "going: true или false.", "going")
        return _reply(200, self.store.register(mid, device, going))

    def ask(self, mid: str, body: dict, context) -> dict:
        self._resident_write(context)
        if self.qa is None:
            raise ApiError(503, "module_not_ready", "Вопросы к встрече пока не подключены.")
        device = self._device(body, context)
        row = self.store.get_meeting(mid)
        now = self.store.now()
        if self._phase(row, now) != "upcoming":
            raise Conflict("closed", "Встреча уже началась — вопросы к ней больше не принимаются.")
        from ui.civic_qa.service import moderate_text  # noqa: WPS433 — тот же фильтр R04, что у «Вопроса акиму»
        text = _clean(body.get("text"), field="text", low=QUESTION_MIN, high=QUESTION_MAX)
        lang = body.get("lang") if body.get("lang") in LANGS else "ru"
        request_id = body.get("request_id")
        if request_id is not None and (not isinstance(request_id, str) or not REQUEST_RE.match(request_id)):
            raise ApiError(400, "bad_request", "request_id: строка 8–64 символа.", "request_id")
        public, flags = moderate_text(text, lang)
        try:
            question, created = self.qa.store.create(
                text=text, lang=lang, district=row["district"], device_id=device, request_id=request_id,
                meeting_id=mid, votes_close_at=row["at"], text_public=public, flags=flags)
        except Exception as exc:  # Conflict «Вопроса акиму» (лимиты устройства) -> 409 с тем же кодом
            code = getattr(exc, "code", None)
            if code:
                raise Conflict(code, getattr(exc, "message", str(exc))) from None
            raise
        # Житель видит только номер и «на проверке»: вопрос появится в карточке встречи после проверки.
        return _reply(201 if created else 200, {"question": {"id": question["id"], "status": question["status"],
                                                             "meeting_id": mid}, "created": created})

    # ------------------------------------------------------------------ сотрудник
    def _meeting_fields(self, body: dict, *, partial: bool) -> dict:
        fields: dict = {}
        if not partial or "district" in body:
            fields["district"] = self._district(body.get("district"), required=True)
        if not partial or "title_ru" in body:
            fields["title_ru"] = _clean(body.get("title_ru"), field="title_ru", low=TITLE_MIN, high=TITLE_MAX)
        if "title_kk" in body:
            fields["title_kk"] = _clean(body.get("title_kk"), field="title_kk", low=TITLE_MIN, high=TITLE_MAX,
                                        required=False)
        if not partial or "at" in body:
            start = parse_iso(body.get("at")) if isinstance(body.get("at"), str) else None
            if start is None:
                raise ApiError(422, "invalid", "Укажите дату и время встречи.", "at")
            now = self.store.now()
            if not now - timedelta(days=366) <= start <= now + timedelta(days=366):
                raise ApiError(422, "invalid", "Дата встречи — в пределах года от сегодня.", "at")
            fields["at"] = iso(start)
        if "duration_min" in body:
            value = body.get("duration_min")
            if isinstance(value, bool) or not isinstance(value, int) or not 30 <= value <= 480:
                raise ApiError(422, "invalid", "Длительность — от 30 до 480 минут.", "duration_min")
            fields["duration_min"] = value
        if not partial or "place" in body:
            fields["place"] = self._place(body.get("place"))
        if "point" in body:
            fields["point"] = self._point(body.get("point"))
        if partial and "status" in body:
            if body["status"] not in ("scheduled", "cancelled"):
                raise ApiError(422, "invalid", "status: scheduled или cancelled.", "status")
            fields["status"] = body["status"]
        return fields

    @staticmethod
    def _place(raw) -> dict:
        if not isinstance(raw, dict):
            raise ApiError(422, "invalid", "Укажите место встречи.", "place")
        label_ru = _clean(raw.get("label_ru"), field="place", low=2, high=LABEL_MAX)
        label_kk = _clean(raw.get("label_kk"), field="place", low=2, high=LABEL_MAX, required=False)
        kind, target_id = raw.get("kind"), raw.get("id")
        if kind in (None, "") and target_id in (None, ""):
            return {"kind": None, "id": None, "label_ru": label_ru, "label_kk": label_kk}
        if kind not in PLACE_KINDS or not isinstance(target_id, str) or not TARGET_ID_RE.match(target_id):
            raise ApiError(422, "invalid", "Место на карте: цель {kind, id} (объект, участок улицы или двор).", "place")
        return {"kind": kind, "id": target_id, "label_ru": label_ru, "label_kk": label_kk}

    @staticmethod
    def _point(raw):
        if raw is None:
            return None
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise ApiError(422, "invalid", "point: пара [долгота, широта].", "point")
        try:
            lon, lat = float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            raise ApiError(422, "invalid", "point: пара чисел.", "point") from None
        w, s, e, n = ASTANA_BOUNDS
        if not (w <= lon <= e and s <= lat <= n):
            raise ApiError(422, "invalid", "point: точка вне Астаны.", "point")
        return [round(lon, 7), round(lat, 7)]

    def save_meeting(self, body: dict, principal) -> dict:
        mid = body.get("id")
        if mid not in (None, ""):
            if not isinstance(mid, str) or not MEETING_ID_RE.match(mid):
                raise LookupError(mid)
            fields = self._meeting_fields(body, partial=True)
            row = self.store.update_meeting(mid, fields)
            if "at" in fields and self.qa is not None:
                self.qa.store.set_votes_close(mid, fields["at"])  # голосование закрывается к новому началу
            return self.card(row["id"], {}, principal, {})
        fields = self._meeting_fields(body, partial=False)
        row = self.store.create_meeting(fields, _actor(principal))
        reply = self.card(row["id"], {}, principal, {})
        reply["status"] = 201
        return reply

    def _order_fields(self, body: dict, *, partial: bool, meeting_at: str) -> dict:
        fields: dict = {}
        if not partial or "text_ru" in body:
            fields["text_ru"] = _clean(body.get("text_ru"), field="text_ru", low=ORDER_MIN, high=ORDER_MAX)
        if "text_kk" in body:
            fields["text_kk"] = _clean(body.get("text_kk"), field="text_kk", low=ORDER_MIN, high=ORDER_MAX,
                                       required=False)
        if not partial or "service" in body:
            if body.get("service") not in SERVICES:
                raise ApiError(422, "invalid", "Выберите службу из справочника.", "service")
            fields["service"] = body["service"]
        if not partial or "due" in body:
            due = body.get("due")
            if not isinstance(due, str) or not DATE_RE.match(due):
                raise ApiError(422, "invalid", "Срок — дата ГГГГ-ММ-ДД.", "due")
            try:
                due_date = date.fromisoformat(due)
            except ValueError:
                raise ApiError(422, "invalid", "Срок — существующая дата.", "due") from None
            meeting_day = astana_date(parse_iso(meeting_at))
            if not meeting_day - timedelta(days=1) <= due_date <= meeting_day + timedelta(days=731):
                raise ApiError(422, "invalid", "Срок — не раньше встречи и не позже двух лет.", "due")
            fields["due"] = due
        if "status" in body:
            if body["status"] not in ORDER_STATUSES:
                raise ApiError(422, "invalid", "Статус: todo, in_progress или done.", "status")
            fields["status"] = body["status"]
        if "link" in body:
            fields["link"] = self._link(body.get("link"))
        return fields

    @staticmethod
    def _link(raw):
        if raw in (None, "", {}):
            return None
        if not isinstance(raw, dict) or raw.get("kind") not in LINK_KINDS:
            raise ApiError(422, "invalid", "Связь: обращение, работа или проект.", "link")
        target_id = raw.get("id")
        if not isinstance(target_id, str) or not LINK_ID_RE.match(target_id):
            raise ApiError(422, "invalid", "Связь: номер записи.", "link")
        return {"kind": raw["kind"], "id": target_id}

    def order(self, mid: str, body: dict, principal) -> dict:
        meeting = self.store.get_meeting(mid)
        oid = body.get("order_id")
        names = service_names()
        today = astana_date(self.store.now())
        if oid in (None, ""):
            fields = self._order_fields(body, partial=False, meeting_at=meeting["at"])
            status = fields.pop("status", "todo")
            row = self.store.add_order(mid, fields, _actor(principal))
            if status != "todo":
                row = self.store.update_order(mid, row["id"], {"status": status}, _actor(principal))
            return _reply(201, {"order": self._order_view(row, today, names)})
        if not isinstance(oid, str) or not ORDER_ID_RE.match(oid):
            raise LookupError(oid)
        fields = self._order_fields(body, partial=True, meeting_at=meeting["at"])
        if not fields:
            raise ApiError(422, "invalid", "Нечего менять: передайте статус, срок, связь или текст.", "order_id")
        row = self.store.update_order(mid, oid, fields, _actor(principal))
        return _reply(200, {"order": self._order_view(row, today, names)})

    def result(self, mid: str, body: dict, principal) -> dict:
        texts = {lang: _clean(body.get("result_" + lang), field="result_" + lang, low=RESULT_MIN, high=RESULT_MAX,
                              required=False) for lang in LANGS}
        if not texts["ru"] and not texts["kk"]:
            raise ApiError(422, "invalid", "Напишите итог хотя бы на одном языке.", "result_ru")
        self.store.set_result(mid, texts["ru"], texts["kk"])
        return self.card(mid, {}, principal, {})

    # ------------------------------------------------------------------ лента уведомлений (R06)
    def updates_route(self, q: dict, context) -> dict:
        device = self._device({}, context, q)
        since = q.get("since") or None
        if since is not None and parse_iso(since) is None:
            raise ApiError(400, "bad_request", "since: время ISO 8601.", "since")
        items = self.updates(device, since)
        return _reply(200, {"items": items, "since": since, "now": iso(self.store.now())})

    def updates(self, device: str, since: str | None = None, *, limit: int = 50) -> list[dict]:
        """События для ленты «Что нового для меня» (CONTRACT §5.8) — только по встречам, где устройство нажало
        «Приду» или задало вопрос: итог встречи, смена статуса поручения, вопрос опубликован / на него ответили,
        напоминание за сутки до начала. Чужие устройства, логины и непроверенные тексты не попадают."""
        if not device or not DEVICE_RE.match(str(device)):
            return []
        since_dt = parse_iso(since) if since else None
        since_iso = iso(since_dt) if since_dt else None
        now = self.store.now()
        questions = self.qa.store.device_meeting_questions(device) if self.qa is not None else []
        ids = sorted(set(self.store.meetings_of_device(device)) | {q["meeting_id"] for q in questions})
        if not ids:
            return []
        meetings = {}
        for mid in ids:
            try:
                meetings[mid] = self.store.get_meeting(mid)
            except LookupError:
                continue
        events: list[dict] = []

        def add(event_id, at, kind, meeting, title_ru, title_kk, anchor=None, sub=None):
            if since_iso and at <= since_iso:
                return
            if at > iso(now):
                return
            target = {"kind": meeting.get("place_kind"), "id": meeting.get("place_id")} if meeting.get("place_id") \
                else {"kind": "meeting", "id": meeting["id"]}
            events.append({"id": event_id, "at": at, "module": "R13", "kind": kind, "sub": sub,
                           "target": dict(target, meeting_id=meeting["id"]), "title_ru": title_ru, "title_kk": title_kk,
                           "link": f"#meetings/{meeting['id']}" + (f"/{anchor}" if anchor else ""),
                           "demo": bool(meeting.get("demo"))})

        registered = set(self.store.meetings_of_device(device))
        for mid, m in meetings.items():
            if m.get("status") == "cancelled":
                continue
            if m.get("result_at"):
                add(f"mt-{mid}-result", m["result_at"], "meeting.result", m,
                    "Итоги встречи с акимом района опубликованы", "Аудан әкімімен кездесудің қорытындысы жарияланды",
                    sub="result")
            start = parse_iso(m["at"])
            if mid in registered and start is not None:
                remind = iso(start - timedelta(days=1))
                if remind <= iso(now) < m["at"]:
                    local = start.astimezone(ASTANA).strftime("%H:%M")
                    add(f"mt-{mid}-remind", remind, "meeting.result", m, f"Завтра в {local} — встреча с акимом района",
                        f"Ертең {local}-да — аудан әкімімен кездесу", sub="reminder")
        for row in self.store.order_log(list(meetings), since_iso):
            m = meetings.get(row["meeting_id"])
            if m is None or row["to_status"] not in ("in_progress", "done"):
                continue
            done = row["to_status"] == "done"
            short_ru = _short(row["text_ru"])
            short_kk = _short(row.get("text_kk") or row["text_ru"])
            add(f"mt-log-{row['id']}", row["at"], "meeting.result", m,
                (f"Поручение выполнено: {short_ru}" if done else f"Поручение в работе: {short_ru}"),
                (f"Тапсырма орындалды: {short_kk}" if done else f"Тапсырма орындалуда: {short_kk}"),
                anchor=row["order_id"], sub="order")
        for q in questions:
            m = meetings.get(q["meeting_id"])
            if m is None or q["status"] != "published":
                continue
            if q.get("published_at"):
                add(f"mt-{q['id']}-published", q["published_at"], "meeting.result", m,
                    "Ваш вопрос к встрече опубликован", "Кездесуге қойған сұрағыңыз жарияланды", anchor=q["id"],
                    sub="question")
            if q.get("answered_at"):
                add(f"mt-{q['id']}-answered", q["answered_at"], "meeting.result", m,
                    "На ваш вопрос ответили на встрече", "Сұрағыңызға кездесуде жауап берілді", anchor=q["id"],
                    sub="answer")
        events.sort(key=lambda e: (e["at"], e["id"]), reverse=True)
        return events[:limit]

    # ------------------------------------------------------------------ «Картина дня» R08, аналитик R03
    def board_block(self, *, district: str | None = None, limit: int = 5) -> dict:
        """Блок «Встречи» для «Картины дня» и Ситуационного центра R08: ближайшая встреча и поручения со сроком.

        orders — открытые поручения: сначала просроченные, затем по сроку; закрытые — только в числах.
        """
        now = self.store.now()
        today = astana_date(now)
        names = service_names()
        upcoming = self.store.list_meetings(district=district, when="upcoming", limit=1)
        nxt = None
        if upcoming:
            (_row, _orders, nxt), = self._views(upcoming, None)
        orders = self.store.all_orders(district=district)
        views = []
        for o in orders:
            view = self._order_view(o, today, names)
            view.update({"meeting_id": o["meeting_id"], "district": o["district"],
                         "meeting_title_ru": o["meeting_title_ru"], "meeting_title_kk": o["meeting_title_kk"],
                         "meeting_at": o["meeting_at"]})
            views.append(view)
        counts = self._order_counts(views)
        open_orders = [v for v in views if v["status"] != "done"]
        open_orders.sort(key=lambda v: (not v["overdue"], v["due"], v["id"]))
        demo = any(v["demo"] for v in views) or bool(nxt and nxt["demo"])
        return {"next": nxt, "orders": open_orders[:limit], "counts": counts, "district": district,
                "card": _board_card(nxt, counts), "link": "#meetings", "demo": demo, "module": "R13", "as_of": iso(now)}


RU_MONTHS = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
KK_MONTHS = ("қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел")


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _board_card(nxt: dict | None, counts: dict) -> dict:
    """Карточка «Встречи» для ряда «Ведомства · Жители вместе · Встречи» «Картины дня» (IA_ROUND15 §5.10):
    заголовок, одно крупное число (поручения в работе), две строки, «Открыть» → #meetings. Числа — из базы, тексты — код."""
    open_n = counts["todo"] + counts["in_progress"]
    lines = [{"ru": f"Выполнено {counts['done']} из {counts['total']}"
                    + (f" · просрочено {counts['overdue']}" if counts["overdue"] else ""),
              "kk": f"{counts['total']} тапсырманың {counts['done']} орындалды"
                    + (f" · мерзімі өткені — {counts['overdue']}" if counts["overdue"] else "")}]
    if nxt:
        start = parse_iso(nxt["at"]).astimezone(ASTANA)
        when = f"{start.day} {{m}}, {start:%H:%M}"
        lines.append({"ru": "Ближайшая встреча: " + when.format(m=RU_MONTHS[start.month - 1]) + f" · «Приду» {nxt['registered']}",
                      "kk": "Жақын кездесу: " + when.format(m=KK_MONTHS[start.month - 1]) + f" · «Барамын» {nxt['registered']}"})
    else:
        lines.append({"ru": "Ближайших встреч пока нет", "kk": "Жақын арада кездесу жоқ"})
    return {"title_ru": "Встречи с жителями", "title_kk": "Тұрғындармен кездесулер", "value": open_n,
            "value_ru": _plural_ru(open_n, "поручение в работе", "поручения в работе", "поручений в работе"),
            "value_kk": "тапсырма орындалуда", "lines": lines, "link": "#meetings",
            "action_ru": "Открыть", "action_kk": "Ашу"}


def _short(text: str, limit: int = 70) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def make_service(db_path, *, clock=None, demo: bool | None = None, qa=None) -> MeetingService:
    """Сервис на базе шлюза. demo=None — по CIVIC_DEMO=1 (run-city.bat) и без CIVIC_DEMO_WORLD=1: свой демо-набор
    (3 встречи «Пример»). В демо-мире (CIVIC_DEMO_WORLD=1) встречи приходят из world_v1.json через seed_world."""
    from ui.civic_qa import make_service as make_qa  # noqa: WPS433 — вопросы встреч живут в «Вопросе акиму»
    from . import demo as demo_data
    store = MeetingStore(db_path, clock=clock) if clock else MeetingStore(db_path)
    if qa is None:
        try:
            qa = make_qa(db_path, clock=clock, demo=False) if clock else make_qa(db_path, demo=False)
        except Exception:
            qa = None
    if demo is None:
        demo = os.environ.get("CIVIC_DEMO") == "1" and os.environ.get("CIVIC_DEMO_WORLD") != "1"
    service = MeetingService(store, qa)
    if demo:
        demo_data.seed(service)
    return service
