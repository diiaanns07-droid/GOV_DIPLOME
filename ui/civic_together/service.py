"""«Мой двор» и «Сделаем вместе» для шлюза R01 (kind="service"):
make_service(db_path).handle(method, path, query, body, principal, context) -> {"status", "headers", "body"}.

Маршруты (префикс /api/civic/v2, CONTRACT §7; [доп.] — сверх таблицы §7, их R01 добавляет по INTEGRATION.txt):
  GET  together/initiatives?bbox&status&kind&yard&district&view   все: опубликованные и «сделано»; view=mine — свои
                                                                   (и на проверке); view=staff&tab=… — сотрудник
  GET  together/initiatives?similar=1&lon&lat&kind&title          все: похожие рядом («Присоединиться к существующей»)
  POST together/initiatives                                        житель (X-Birge-Device): на проверку -> 201
  GET  together/initiatives/{id}                                   все (на проверке — только автору и сотруднику)
  POST together/initiatives/{id}/join · /leave                     житель: «Я приду» — одно устройство, один раз
  POST together/initiatives/{id}/support                           сотрудник: «Поддержать» (инвентарь, вывоз waste)
  POST together/initiatives/{id}/moderate                          сотрудник: publish | hide | cancel | publish_report |
                                                                   hide_report
  POST together/initiatives/{id}/report                            автор (на проверку) или сотрудник (сразу «сделано»)
  GET  together/yards [доп.]                                       все: дворы, где уже есть соседи или инициативы
  GET  together/yards/{id}                                         все: страница двора; блоки соседей — «пока нет данных»
  POST together/yards/{id}/join · /leave                           житель: «Я живу здесь» / «Больше не живу»
  POST together/yards/{id}/captain [доп.]                          житель-сосед: «старший по двору» (имя на проверку)
  POST together/yards/{id}/moderate [доп.]                         сотрудник: имя старшего — publish | hide
  GET  together/updates?since                                      житель: события для ленты R06 (CONTRACT §5.8)

Сотрудник — сессия R02 (principal шлюза) + для записи X-CSRF-Token и свой Origin (как R09, R13; R15 S05/S17).
Ошибка — {"error": код, "message": текст по-русски, "field"?} — как v2_error шлюза.
Наружу не отдаём (CONTRACT §10): хэши и id устройств, время вступления и «Я приду», кто именно живёт во дворе,
логин сотрудника, исходный текст до модерации (только сотруднику), причину снятия (только автору — кодом).
"""

from __future__ import annotations

from collections import deque
from datetime import timedelta
import logging
import math
import os
import re
import threading
import time
from urllib.parse import parse_qs

from . import moderation, neighbors
from .photos import PhotoError, clean_photo, data_url
from .store import Conflict, TogetherStore, TooMany, iso, parse_iso

LOGGER = logging.getLogger("civic_together")

PREFIX = "/api/civic/v2"
KINDS = ("cleanup", "greening", "snow", "repair", "help", "other")
LANGS = ("ru", "kk", "mixed")
DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
# Справочник служб — CONTRACT §3 (те же id, что у R09 lifecycle.SERVICES и таблицы R08). Новых не придумываем.
SERVICES = ("road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
            "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
            "parking", "akimat")
HIDE_REASONS = ("personal_data", "rude", "spam", "duplicate", "not_initiative", "other")
TITLE_MIN, TITLE_MAX = 5, 80
TEXT_MAX = 600
BRING_ITEMS, BRING_LEN = 8, 40
NOTE_MAX = 200
REPORT_MIN, REPORT_MAX = 10, 600
CAPTAIN_MIN, CAPTAIN_MAX = 2, 40
LIST_LIMIT = 60
MAX_AHEAD_DAYS = 180         # инициатива — не дальше полугода вперёд
MAX_HOURS = 14               # одно дело — в пределах одного дня
SIMILAR_RADIUS_M = 600       # «похожая рядом»: тот же вид, ближе 600 м, ещё не прошла
DEVICE_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
REQUEST_RE = re.compile(r"[A-Za-z0-9._:-]{8,64}\Z")
INITIATIVE_ID = re.compile(r"i-[a-z0-9-]{4,40}\Z")
YARD_ID = re.compile(r"(?:yard|cell)-[A-Za-z0-9_-]{1,60}\Z")
ASTANA_BOUNDS = (70.9, 50.9, 71.9, 51.4)
KK_LETTERS = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]")
PUBLIC_STATUSES = ("published", "done")
# Лимиты частоты в модуле (на устройство; лимиты по адресу клиента — у шлюза R01, INTEGRATION.txt):
# (окно, сек; сколько действий). Создание инициатив ограничено ещё и в базе: 3 на проверке, 5 в сутки.
LIMITS = {
    "join": ((60, 30), (86400, 200)),
    "yard": ((60, 10), (86400, 30)),
    "report": ((3600, 20),),
    "captain": ((3600, 5),),
}

# Тексты событий ленты (CONTRACT §5.8) и ленты двора: ru / kk. Числа и названия подставляет код.
EVENT_TEXT = {
    ("published", "yard"): ("Новое дело во дворе: «{title}»", "Аулада жаңа іс: «{title}»"),
    ("published", "author"): ("Ваша инициатива опубликована: «{title}»", "Бастамаңыз жарияланды: «{title}»"),
    ("hidden", "author"): ("Инициатива не опубликована: «{title}»", "Бастама жарияланбады: «{title}»"),
    ("supported", "yard"): ("Акимат поддержал: «{title}»", "Әкімдік қолдады: «{title}»"),
    ("supported", "joined"): ("Акимат поддержал: «{title}»", "Әкімдік қолдады: «{title}»"),
    ("cancelled", "yard"): ("Отменено: «{title}»", "Тоқтатылды: «{title}»"),
    ("cancelled", "joined"): ("Отменено: «{title}»", "Тоқтатылды: «{title}»"),
    ("done", "yard"): ("Сделано вместе: «{title}» — {n} соседей", "Бірге жасалды: «{title}» — {n} көрші"),
    ("done", "joined"): ("Сделано вместе: «{title}» — {n} соседей", "Бірге жасалды: «{title}» — {n} көрші"),
    ("done", "author"): ("Сделано вместе: «{title}» — {n} соседей", "Бірге жасалды: «{title}» — {n} көрші"),
}
EVENT_KIND = {"yard": "yard.news", "joined": "initiative.update", "author": "initiative.update"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.field, self.retry_after = status, code, message, field, retry_after


def _reply(status: int, body: dict, headers: dict | None = None) -> dict:
    return {"status": status, "headers": headers or {}, "body": body}


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
    """Кто решил — хранится для журнала, наружу не отдаётся (только «акимат»)."""
    name = getattr(principal, "username", None) or (principal.get("username") if isinstance(principal, dict) else None)
    return str(name or "staff")[:64]


class _Limiter:
    """Скользящее окно в памяти процесса (как RateLimiter шлюза): allow(ключ, правила) -> 0 или секунды до повтора."""

    def __init__(self, clock=time.monotonic, max_keys: int = 20_000):
        self._hits: dict = {}
        self._lock = threading.Lock()
        self._clock = clock
        self._max_keys = max_keys

    def allow(self, key, rules) -> int:
        now = self._clock()
        with self._lock:
            for window, limit in rules:
                hits = self._hits.setdefault((key, window), deque())
                while hits and now - hits[0] >= window:
                    hits.popleft()
                if len(hits) >= limit:
                    return max(1, int(window - (now - hits[0])) + 1)
            for window, _limit in rules:
                self._hits[(key, window)].append(now)
            if len(self._hits) > self._max_keys:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < 86400}
        return 0


def clean_text(value, *, field: str, low: int, high: int, required: bool = True) -> str:
    if value in (None, "") and not required:
        return ""
    if not isinstance(value, str):
        raise ApiError(422, "invalid", "Напишите текст.", field)
    text = re.sub(r"[ \t ]+", " ", value.replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable())
    if not text and not required:
        return ""
    if len(text) < low:
        raise ApiError(422, "too_short", f"Слишком коротко: нужно хотя бы {low} символов.", field)
    if len(text) > high:
        raise ApiError(422, "too_long", f"Слишком длинно: не больше {high} символов.", field)
    return text


def text_lang(text: str, fallback: str = "ru") -> str:
    return "kk" if KK_LETTERS.search(text or "") else (fallback if fallback in LANGS else "ru")


class TogetherService:
    def __init__(self, store: TogetherStore, *, autopublish: bool | None = None):
        self.store = store
        self.limiter = _Limiter()
        # Автопубликация чистых текстов — только если модерация R04 есть в сборке и флаг включён явно.
        self.autopublish = (os.environ.get("CIVIC_TOGETHER_AUTOPUBLISH") == "1") if autopublish is None else autopublish

    # ------------------------------------------------------------------ вход
    def handle(self, method, path, query=None, body=None, principal=None, context=None):
        try:
            return self._route(str(method).upper(), path, query, body, principal, context or {})
        except ApiError as exc:
            out = {"error": exc.code, "message": exc.message}
            if exc.field:
                out["field"] = exc.field
            headers = {}
            if exc.retry_after:
                out["retry_after"] = exc.retry_after
                headers["Retry-After"] = str(exc.retry_after)
            return _reply(exc.status, out, headers)
        except TooMany as exc:
            return _reply(429, {"error": exc.code, "message": exc.message, "retry_after": exc.retry_after},
                          {"Retry-After": str(exc.retry_after)})
        except Conflict as exc:
            return _reply(409, {"error": exc.code, "message": exc.message})
        except LookupError:
            return _reply(404, {"error": "not_found", "message": "Не найдено: запись удалена или ещё на проверке."})

    def _route(self, method, path, query, body, principal, context):
        rel = path[len(PREFIX):] if str(path).startswith(PREFIX) else str(path)
        rel = rel.split("?", 1)[0]
        parts = [p for p in rel.strip("/").split("/") if p]
        q = self._query(query)
        body = body if isinstance(body, dict) else {}
        if len(parts) < 2 or parts[0] != "together":
            raise ApiError(404, "not_found", "Адрес API не найден.")
        section, rest = parts[1], parts[2:]
        if section == "initiatives":
            if not rest:
                if method == "GET":
                    return self.list_initiatives(q, principal, context)
                if method == "POST":
                    return self.create(body, context)
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            iid = rest[0]
            if not INITIATIVE_ID.match(iid):
                raise LookupError(iid)
            if len(rest) == 1 and method == "GET":
                return self.get_initiative(iid, q, principal, context)
            if len(rest) == 2 and method == "POST":
                action = rest[1]
                if action == "join":
                    return self.join(iid, body, context)
                if action == "leave":
                    return self.leave(iid, body, context)
                if action == "support":
                    self._require_staff(principal, context, unsafe=True)
                    return self.support(iid, body, principal)
                if action == "moderate":
                    self._require_staff(principal, context, unsafe=True)
                    return self.moderate(iid, body, principal)
                if action == "report":
                    return self.report(iid, body, principal, context)
        elif section == "yards":
            if not rest:
                if method == "GET":
                    return self.list_yards(q)
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            yid = rest[0]
            if not YARD_ID.match(yid):
                raise LookupError(yid)
            if len(rest) == 1 and method == "GET":
                return self.yard_page(yid, q, context)
            if len(rest) == 2 and method == "POST":
                if rest[1] in ("join", "leave"):
                    return self.yard_membership(yid, rest[1] == "join", body, context)
                if rest[1] == "captain":
                    return self.captain(yid, body, context)
                if rest[1] == "moderate":
                    self._require_staff(principal, context, unsafe=True)
                    return self.moderate_captain(yid, body)
        elif section == "updates" and not rest and method == "GET":
            return self.updates_route(q, context)
        raise ApiError(404, "not_found", "Адрес API не найден.")

    # ------------------------------------------------------------------ разбор запроса
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
        if context.get("host_allowed") is False or context.get("is_same_origin") is False:
            raise ApiError(403, "forbidden", "Запрос с чужого сайта отклонён.")

    @staticmethod
    def _device(body, context, q=None, required=True):
        device = _header(context, "X-Birge-Device") or (body or {}).get("device_id") or (q or {}).get("device_id")
        if device in (None, "") and not required:
            return None
        if not isinstance(device, str) or not DEVICE_RE.match(device):
            raise ApiError(400, "bad_request", "Не удалось определить устройство. Обновите страницу.", "device_id")
        return device

    def _limit(self, action: str, device: str):
        retry = self.limiter.allow((action, self.store.device_hash(device)), LIMITS[action])
        if retry:
            raise ApiError(429, "too_many_requests", "Слишком часто. Повторите чуть позже.", retry_after=retry)

    @staticmethod
    def _number(raw, field, low, high) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ApiError(400, "bad_request", f"{field}: нужно число.", field) from None
        if not (low <= value <= high):
            raise ApiError(400, "bad_request", f"{field}: вне Астаны.", field)
        return value

    def _point(self, raw, field="point") -> list[float]:
        if not isinstance(raw, (list, tuple)) or len(raw) != 2 or any(isinstance(v, bool) for v in raw):
            raise ApiError(422, "invalid", "Отметьте место на карте.", field)
        return [round(self._number(raw[0], field, ASTANA_BOUNDS[0], ASTANA_BOUNDS[2]), 6),
                round(self._number(raw[1], field, ASTANA_BOUNDS[1], ASTANA_BOUNDS[3]), 6)]

    def _bbox(self, raw):
        parts = str(raw).split(",")
        if len(parts) != 4:
            raise ApiError(400, "bad_request", "bbox: четыре числа через запятую.", "bbox")
        lon1, lat1, lon2, lat2 = (self._number(p, "bbox", -180, 180) for p in parts)
        if lon1 >= lon2 or lat1 >= lat2:
            raise ApiError(400, "bad_request", "bbox: сначала меньшие координаты.", "bbox")
        return (lon1, lat1, lon2, lat2)

    @staticmethod
    def _district(value, required=False):
        if value in (None, ""):
            if required:
                raise ApiError(422, "invalid", "Выберите район.", "district")
            return None
        if value not in DISTRICTS:
            raise ApiError(400, "bad_request", "Неизвестный район.", "district")
        return value

    # ------------------------------------------------------------------ виды записи
    def _photos_view(self, item: dict, *, full: bool) -> list[dict]:
        """Фото «после» — data URL загруженного фото (миниатюра в списке, само фото в карточке дела)."""
        if not item.get("photos"):
            return []
        out = []
        blobs = {p["id"]: p for p in self.store.photo_data(item["id"], thumbs=not full)}
        for photo in item["photos"]:
            # Поправка П1: фото «после» — только настоящие (загруженные). Статические картинки демо (src) из прежних
            # баз не показываем — нарисованное «фото» выдавало бы себя за настоящее.
            if photo.get("src"):
                continue
            blob = blobs.get(photo["id"]) or {}
            url = data_url(blob.get("mime"), blob.get("data")) if full else \
                data_url(blob.get("thumb_mime"), blob.get("thumb"))
            if url:
                out.append({"id": photo["id"], "width": photo.get("width"), "height": photo.get("height"),
                            "data_url": url, "demo": bool(photo.get("demo"))})
        return out

    def _public(self, item: dict, *, my_join=False, mine=False, full=False) -> dict:
        report = item.get("report")
        public_report = None
        if report and report.get("status") == "published":
            public_report = {"text": report.get("text_public") or report.get("text"), "joined": report.get("joined_final"),
                             "at": report.get("published_at"), "photos": self._photos_view(item, full=full),
                             "demo": bool(report.get("demo"))}
        support = item.get("support") or None
        if support:
            support = {k: support.get(k) for k in ("by_akimat", "inventory", "pickup_service", "note", "at")}
        target = None
        if item.get("target_id"):
            target = {"kind": item.get("target_kind") or "area", "id": item["target_id"],
                      "label_ru": item.get("label_ru"), "label_kk": item.get("label_kk")}
        view = {
            "id": item["id"], "kind": item["kind"], "title": item.get("title_public") or item["title"],
            "text": item.get("text_public") or item.get("text") or "", "lang": item.get("lang") or "ru",
            "target": target, "point": [item["lon"], item["lat"]], "district": item.get("district"),
            "starts_at": item["starts_at"], "ends_at": item.get("ends_at"), "bring": item.get("bring") or [],
            "status": item["status"], "joined": int(item.get("joined") or 0), "my_join": bool(my_join),
            "mine": bool(mine), "support": support, "report": public_report, "from_idea": item.get("from_idea"),
            "published_at": item.get("published_at"), "done_at": item.get("done_at"), "demo": bool(item.get("demo")),
        }
        if mine:
            # Автор видит, что с его записью: «на проверке», причину снятия (кодом), отчёт на проверке.
            view["hide_reason"] = item.get("hide_reason") if item["status"] == "hidden" else None
            view["report_status"] = report.get("status") if report else None
        return view

    def _staff_view(self, item: dict, *, full=False) -> dict:
        view = self._public(item, full=full)
        report = item.get("report")
        mod = item.get("moderation") or {}
        flags = mod.get("flags") or []
        if not mod.get("source"):
            # Запись без проверки при создании (демо-набор, демо-мир, старая база) — пометки считаем при чтении.
            flags = moderation.local_check(item["title"] + "\n" + (item.get("text") or ""))["flags"]
        view.update({
            "original": {"title": item["title"], "text": item.get("text") or ""},
            "flags": flags, "moderation_source": mod.get("source"),
            "hide_reason": item.get("hide_reason"), "created_at": item.get("created_at"),
            "report_status": report.get("status") if report else None,
            "report_draft": ({"text": report.get("text"), "flags": (moderation.local_check(report.get("text") or "")
                                                                   ["flags"]), "photos": self._photos_view(item, full=full)}
                             if report and report.get("status") == "on_review" else None),
        })
        return view

    # ------------------------------------------------------------------ инициативы: чтение
    def list_initiatives(self, q: dict, principal, context) -> dict:
        view = q.get("view") or "public"
        if q.get("similar") == "1":
            return self.similar(q)
        if view == "staff":
            self._require_staff(principal, context, unsafe=False)
            return self.list_staff(q)
        bbox = self._bbox(q["bbox"]) if q.get("bbox") else None
        kind = q.get("kind") or None
        if kind and kind not in KINDS:
            raise ApiError(400, "bad_request", "kind: " + ", ".join(KINDS) + ".", "kind")
        yard = q.get("yard") or None
        if yard and not YARD_ID.match(yard):
            raise ApiError(400, "bad_request", "yard: id двора yard-….", "yard")
        district = self._district(q.get("district"))
        limit = LIST_LIMIT
        if q.get("limit"):
            try:
                limit = max(1, min(LIST_LIMIT, int(q["limit"])))
            except ValueError:
                raise ApiError(400, "bad_request", "limit: целое число.", "limit") from None
        device = self._device({}, context, q, required=view == "mine")
        if view == "mine":
            rows = self.store.list(statuses=("on_review", "published", "done", "cancelled", "hidden"),
                                   author_device=device, limit=limit, order="recent")
            joined = self.store.joined_by([r["id"] for r in rows], device)
            return _reply(200, {"view": "mine", "items": [self._public(r, my_join=r["id"] in joined, mine=True)
                                                          for r in rows]})
        status = q.get("status") or ""
        statuses = {"": PUBLIC_STATUSES, "published": ("published",), "done": ("done",),
                    "active": ("published",)}.get(status)
        if statuses is None:
            raise ApiError(400, "bad_request", "status: published, done или active.", "status")
        rows = self.store.list(statuses=statuses, bbox=bbox, kind=kind, yard=yard, district=district,
                               upcoming_only=status == "active", limit=limit)
        joined = self.store.joined_by([r["id"] for r in rows], device)
        mine = {r["id"] for r in rows if device and r.get("author_hash") == self.store.device_hash(device)}
        counts = {"published": self.store.count(statuses=("published",), yard=yard, district=district),
                  "done": self.store.count(statuses=("done",), yard=yard, district=district)}
        return _reply(200, {"view": "public", "items": [self._public(r, my_join=r["id"] in joined, mine=r["id"] in mine)
                                                         for r in rows],
                            "counts": counts, "kinds": list(KINDS),
                            "demo": bool(rows) and all(r.get("demo") for r in rows),
                            "limits": {"title_min": TITLE_MIN, "title_max": TITLE_MAX, "text_max": TEXT_MAX,
                                       "bring_items": BRING_ITEMS}})

    def list_staff(self, q: dict) -> dict:
        tab = q.get("tab") or "queue"
        if tab not in ("queue", "published", "done", "hidden"):
            raise ApiError(400, "bad_request", "tab: queue, published, done или hidden.", "tab")
        district = self._district(q.get("district"))
        reports = self.store.reports_on_review()
        captains = self.store.captains_on_review()
        if tab == "queue":
            rows = self.store.list(statuses=("on_review",), district=district, order="queue", limit=50)
        else:
            status = {"published": ("published",), "done": ("done",), "hidden": ("hidden", "cancelled")}[tab]
            rows = self.store.list(statuses=status, district=district, limit=LIST_LIMIT,
                                   order="soon" if tab != "hidden" else "recent")
        queue_size = self.store.count(statuses=("on_review",), district=district) + len(reports) + len(captains)
        if tab != "queue":
            reports, captains = [], []
        counts = {"queue": queue_size,
            "published": self.store.count(statuses=("published",), district=district),
            "done": self.store.count(statuses=("done",), district=district),
            "hidden": self.store.count(statuses=("hidden", "cancelled"), district=district)}
        return _reply(200, {
            "view": "staff", "tab": tab, "items": [self._staff_view(r) for r in rows],
            "reports": [self._staff_view(r, full=True) for r in reports],
            "captains": [{"yard_id": c["id"], "label_ru": c["label_ru"], "label_kk": c["label_kk"],
                          "district": c["district"], "display_name": c["captain_name"],
                          "flags": moderation.local_check(c["captain_name"] or "")["flags"]} for c in captains],
            "counts": counts, "reasons": list(HIDE_REASONS), "services": ["waste"],
            "moderation": {"r04": moderation.available()}})

    def get_initiative(self, iid: str, q: dict, principal, context) -> dict:
        item = self.store.get(iid)
        device = self._device({}, context, q, required=False)
        mine = bool(device) and item.get("author_hash") == self.store.device_hash(device)
        staff = _is_staff(principal)
        if item["status"] in ("on_review", "hidden") and not (mine or staff):
            raise LookupError(iid)
        my_join = bool(self.store.joined_by([iid], device)) if device else False
        if staff and q.get("view") == "staff":
            return _reply(200, {"initiative": self._staff_view(item, full=True)})
        return _reply(200, {"initiative": self._public(item, my_join=my_join, mine=mine, full=True)})

    def similar(self, q: dict) -> dict:
        """Похожие рядом: тот же вид, ещё не прошли, ближе 600 м (+ R04 similar_initiatives, если есть в сборке)."""
        lon = self._number(q.get("lon"), "lon", ASTANA_BOUNDS[0], ASTANA_BOUNDS[2])
        lat = self._number(q.get("lat"), "lat", ASTANA_BOUNDS[1], ASTANA_BOUNDS[3])
        kind = q.get("kind") or None
        if kind and kind not in KINDS:
            raise ApiError(400, "bad_request", "kind: " + ", ".join(KINDS) + ".", "kind")
        dlat = SIMILAR_RADIUS_M / 110_574.0
        dlon = SIMILAR_RADIUS_M / (111_320.0 * math.cos(math.radians(lat)))
        rows = self.store.list(statuses=("published",), bbox=(lon - dlon, lat - dlat, lon + dlon, lat + dlat),
                               kind=kind, upcoming_only=True, limit=20)
        found = {}
        for row in rows:
            d = neighbors.distance_m((lon, lat), (row["lon"], row["lat"]))
            if d <= SIMILAR_RADIUS_M:
                found[row["id"]] = (d, row)
        title = (q.get("title") or "")[:TITLE_MAX]
        for iid in self._r04_similar(title, [lon, lat]):
            if iid in found:
                continue
            try:
                row = self.store.get(iid)
            except LookupError:
                continue
            if row["status"] == "published":
                found[iid] = (neighbors.distance_m((lon, lat), (row["lon"], row["lat"])), row)
        ordered = sorted(found.values(), key=lambda pair: pair[0])[:3]
        return _reply(200, {"items": [dict(self._public(row), distance_m=round(d)) for d, row in ordered],
                            "radius_m": SIMILAR_RADIUS_M})

    @staticmethod
    def _r04_similar(title: str, point) -> list[str]:
        if len(title) < TITLE_MIN:
            return []
        try:
            from ui.civic_ml_api import similar_initiatives  # R04, раунд 15
        except Exception:
            return []
        try:
            result = similar_initiatives(title, point, 30)
        except Exception:
            LOGGER.exception("R04 similar_initiatives не сработал")
            return []
        items = result.get("items") if isinstance(result, dict) else result
        out = []
        for item in items or []:
            iid = item if isinstance(item, str) else (item.get("id") if isinstance(item, dict) else None)
            if isinstance(iid, str) and INITIATIVE_ID.match(iid):
                out.append(iid)
        return out[:5]

    # ------------------------------------------------------------------ инициативы: запись
    def _clean_fields(self, body: dict) -> dict:
        kind = body.get("kind")
        if kind not in KINDS:
            raise ApiError(422, "invalid", "Выберите, что будем делать.", "kind")
        title = clean_text(body.get("title"), field="title", low=TITLE_MIN, high=TITLE_MAX)
        text = clean_text(body.get("text"), field="text", low=0, high=TEXT_MAX, required=False)
        point = self._point(body.get("point"))
        now = self.store.now()
        starts = parse_iso(body.get("starts_at"))
        if starts is None:
            raise ApiError(422, "invalid", "Выберите дату и время.", "starts_at")
        if starts < now - timedelta(minutes=30):
            raise ApiError(422, "in_past", "Это время уже прошло. Выберите другое.", "starts_at")
        if starts > now + timedelta(days=MAX_AHEAD_DAYS):
            raise ApiError(422, "too_far", "Не дальше чем на полгода вперёд.", "starts_at")
        ends = parse_iso(body.get("ends_at")) if body.get("ends_at") else starts + timedelta(hours=3)
        if ends is None or ends <= starts or ends > starts + timedelta(hours=MAX_HOURS):
            raise ApiError(422, "invalid", "Окончание — в тот же день, позже начала.", "ends_at")
        bring = []
        raw_bring = body.get("bring") or []
        if not isinstance(raw_bring, list) or len(raw_bring) > BRING_ITEMS:
            raise ApiError(422, "invalid", f"Что взять — не больше {BRING_ITEMS} пунктов.", "bring")
        for value in raw_bring:
            item = clean_text(value, field="bring", low=1, high=BRING_LEN)
            if item.lower() not in (b.lower() for b in bring):
                bring.append(item)
        lang = body.get("lang") if body.get("lang") in LANGS else text_lang(title + " " + text)
        target, district = self._target(body.get("target"), point)
        district = district or self._district(body.get("district"))
        return {"kind": kind, "title": title, "text": text, "point": point, "starts_at": iso(starts),
                "ends_at": iso(ends), "bring": bring, "lang": lang, "target": target, "district": district}

    def _target(self, raw, point):
        """Цель — двор R12 (подписи только с карты R12, не из запроса: R15 S04/S12). Нет — двор по точке; нет и его —
        без двора (инициатива на карте и в списке, но не на странице двора)."""
        district = neighbors.district_of(point)
        yard_id = None
        if raw not in (None, ""):
            if not isinstance(raw, dict) or raw.get("kind") != "area" or not YARD_ID.match(str(raw.get("id") or "")):
                raise ApiError(422, "invalid", "Место — двор с карты.", "target")
            yard_id = raw["id"]
        if yard_id is None:
            found = neighbors.yard_at(point[0], point[1])
            if found and YARD_ID.match(str(found.get("id") or "")):
                yard_id = found["id"]
        if yard_id is None:
            return None, district
        geo = neighbors.yard_geo(yard_id)
        known = self.store.yard(yard_id)
        if geo is None and known is None:
            raise ApiError(422, "unknown_yard", "Двор не найден на карте. Выберите место ещё раз.", "target")
        label_ru = (geo or {}).get("label_ru") or (known or {}).get("label_ru")
        label_kk = (geo or {}).get("label_kk") or (known or {}).get("label_kk")
        if geo and geo.get("geometry") and neighbors.point_to_area_m(point, geo["geometry"]) > 300:
            raise ApiError(422, "far_from_yard", "Точка далеко от выбранного двора. Отметьте место во дворе.", "point")
        return {"kind": "area", "id": yard_id, "label_ru": label_ru, "label_kk": label_kk}, \
            district or (known or {}).get("district")

    def create(self, body: dict, context) -> dict:
        self._resident_write(context)
        device = self._device(body, context)
        fields = self._clean_fields(body)
        request_id = body.get("request_id")
        if request_id is not None and (not isinstance(request_id, str) or not REQUEST_RE.match(request_id)):
            raise ApiError(400, "bad_request", "request_id: строка 8–64 символа.", "request_id")
        checked = moderation.check(fields["title"] + "\n" + fields["text"], fields["lang"])
        title_mod = moderation.check(fields["title"], fields["lang"])
        text_mod = moderation.check(fields["text"], fields["lang"]) if fields["text"] else {"text_public": ""}
        fields["moderation"] = {"flags": checked["flags"], "source": checked["source"]}
        fields["title_public"] = title_mod["text_public"] if title_mod["text_public"] != fields["title"] else None
        fields["text_public"] = text_mod["text_public"] if text_mod["text_public"] != fields["text"] else None
        status = "published" if (self.autopublish and checked["source"] == "r04" and not checked["flags"]) \
            else "on_review"
        item, created = self.store.create(fields, device_id=device, request_id=request_id, status=status)
        # Житель видит номер и «на проверке» (или «опубликовано» при автопубликации) — и подсказку о личных данных.
        return _reply(201 if created else 200, {
            "initiative": self._public(item, mine=True, full=True), "created": created,
            "hints": moderation.hints(fields["title"] + "\n" + fields["text"])})

    def join(self, iid: str, body: dict, context) -> dict:
        self._resident_write(context)
        device = self._device(body, context)
        self._limit("join", device)
        result, created = self.store.join(iid, device)
        return _reply(200, dict(result, created=created))

    def leave(self, iid: str, body: dict, context) -> dict:
        self._resident_write(context)
        device = self._device(body, context)
        self._limit("join", device)
        result, changed = self.store.leave(iid, device)
        return _reply(200, dict(result, changed=changed))

    def support(self, iid: str, body: dict, principal) -> dict:
        inventory = body.get("inventory", True)
        if not isinstance(inventory, bool):
            raise ApiError(422, "invalid", "inventory: да или нет.", "inventory")
        pickup = body.get("pickup_service", "waste" if body.get("pickup", True) else None)
        if pickup not in (None, *SERVICES):
            raise ApiError(422, "invalid", "Служба вывоза — из справочника служб.", "pickup_service")
        if not inventory and pickup is None:
            raise ApiError(422, "invalid", "Выберите, чем поддержать: инвентарь или вывоз.", "inventory")
        note = clean_text(body.get("note"), field="note", low=0, high=NOTE_MAX, required=False) or None
        item = self.store.support(iid, {"inventory": inventory, "pickup_service": pickup, "note": note},
                                  actor=_actor(principal))
        return _reply(200, {"initiative": self._staff_view(item)})

    def moderate(self, iid: str, body: dict, principal) -> dict:
        action = body.get("action")
        if action in ("publish_report", "hide_report"):
            item = self.store.moderate_report(iid, action == "publish_report")
            return _reply(200, {"initiative": self._staff_view(item)})
        if action not in ("publish", "hide", "cancel"):
            raise ApiError(422, "invalid", "action: publish, hide, cancel, publish_report или hide_report.", "action")
        reason = body.get("reason")
        if action == "hide" and reason not in HIDE_REASONS:
            raise ApiError(422, "invalid", "Выберите причину.", "reason")
        item = self.store.moderate(iid, action, actor=_actor(principal), reason=reason)
        return _reply(200, {"initiative": self._staff_view(item)})

    def report(self, iid: str, body: dict, principal, context) -> dict:
        staff = _is_staff(principal)
        if staff:
            self._require_staff(principal, context, unsafe=True)
        else:
            self._resident_write(context)
            device = self._device(body, context)
            if not self.store.is_author(iid, device):
                # Чужая инициатива: жителю — как будто записи нет (не раскрываем, кто автор).
                raise ApiError(403, "forbidden", "Отчёт добавляет автор инициативы или акимат.")
            self._limit("report", device)
            item = self.store.get(iid)
            if parse_iso(item["starts_at"]) > self.store.now() + timedelta(hours=1):
                raise ApiError(409, "not_started", "Отчёт — после того, как дело состоится.")
        text = clean_text(body.get("text"), field="text", low=REPORT_MIN, high=REPORT_MAX, required=False) or None
        photos = []
        if body.get("photo") not in (None, ""):
            try:
                photos.append(clean_photo(body["photo"]))
            except PhotoError as exc:
                raise ApiError(422, "bad_photo", str(exc), "photo") from None
        if text is None and not photos:
            raise ApiError(422, "invalid", "Напишите, что сделали, или добавьте фото.", "text")
        checked = moderation.check(text, None) if text else None
        try:
            item = self.store.report(iid, text=text, text_public=(checked["text_public"] if checked and
                                                                   checked["text_public"] != text else None),
                                     moderation={"flags": checked["flags"], "source": checked["source"]} if checked else None,
                                     by_role="staff" if staff else "author", publish=staff, photos=photos)
        except ValueError:
            raise ApiError(422, "invalid", "Напишите, что сделали.", "text") from None
        view = self._staff_view(item, full=True) if staff else self._public(item, mine=True, full=True)
        return _reply(200, {"initiative": view})

    # ------------------------------------------------------------------ дворы
    def list_yards(self, q: dict) -> dict:
        district = self._district(q.get("district"))
        rows = self.store.yards(district=district)
        return _reply(200, {"items": [{"id": r["id"], "label_ru": r["label_ru"], "label_kk": r["label_kk"],
                                       "district": r["district"], "point": [r["lon"], r["lat"]] if r["lon"] else None,
                                       "members": int(r["members"] or 0), "initiatives": int(r["initiatives"] or 0),
                                       "demo": bool(r["demo"])} for r in rows]})

    def _yard_info(self, yard_id: str) -> tuple[dict | None, dict | None]:
        return neighbors.yard_geo(yard_id), self.store.yard(yard_id)

    def yard_page(self, yard_id: str, q: dict, context) -> dict:
        geo, known = self._yard_info(yard_id)
        if geo is None and known is None:
            raise LookupError(yard_id)
        device = self._device({}, context, q, required=False)
        point = (geo or {}).get("point") or ([known["lon"], known["lat"]] if known and known.get("lon") else None)
        district = (known or {}).get("district") or neighbors.district_of(point)
        if known is None or not known.get("label_ru"):
            known = self.store.remember_yard(yard_id, label_ru=(geo or {}).get("label_ru"),
                                             label_kk=(geo or {}).get("label_kk"), district=district, point=point)
        area = {"id": yard_id, "point": point, "geometry": (geo or {}).get("geometry")}
        problems = neighbors.problems(area)
        ideas = neighbors.ideas(area, district)
        works = neighbors.works(area, district)
        upcoming = self.store.list(statuses=("published",), yard=yard_id, limit=20)
        done = self.store.list(statuses=("done",), yard=yard_id, limit=10)
        joined = self.store.joined_by([r["id"] for r in upcoming], device)
        dev_hash = self.store.device_hash(device) if device else None
        initiatives = {"status": "ok", "items": [self._public(r, my_join=r["id"] in joined,
                                                              mine=bool(dev_hash) and r.get("author_hash") == dev_hash)
                                                 for r in upcoming],
                       "done": [self._public(r) for r in done]}
        captain = None
        if known.get("captain_status") == "published" and known.get("captain_name"):
            captain = {"display_name": known["captain_name"], "since": known.get("captain_since")}
        me = {"member": self.store.is_member(yard_id, device), "captain": bool(dev_hash) and
              known.get("captain_hash") == dev_hash, "captain_status": (known.get("captain_status") if dev_hash and
                                                                       known.get("captain_hash") == dev_hash else None)}
        members = int(known.get("members") or 0)
        yard = {"id": yard_id, "label_ru": (geo or {}).get("label_ru") or known.get("label_ru"),
                "label_kk": (geo or {}).get("label_kk") or known.get("label_kk"), "district": district,
                "point": point, "geometry": (geo or {}).get("geometry"), "street": (geo or {}).get("street"),
                "approximate": yard_id.startswith("cell-") or bool((geo or {}).get("approximate")),
                "members": members, "captain": captain, "demo": bool(known.get("demo")),
                "map": "real" if geo else "unknown"}
        counts = {"members": members, "problems": problems.get("count") if problems["status"] == "ok" else None,
                  "initiatives": len(upcoming) + self.store.count(statuses=("done",), yard=yard_id)}
        return _reply(200, {"yard": yard, "me": me, "counts": counts, "problems": problems, "ideas": ideas,
                            "initiatives": initiatives, "works": works,
                            "feed": self._yard_feed(yard_id, problems)})

    def _yard_feed(self, yard_id: str, problems: dict) -> list[dict]:
        """Лента двора: дела соседей (события модуля) и проблемы двора с карты (новое сообщение, исправлено)."""
        feed = []
        titles = {}
        for event in self.store.yard_events(yard_id, limit=20):
            text = self._event_text(event, titles)
            if text:
                feed.append(dict(text, at=event["at"], kind="initiative." + event["code"], demo=bool(event["demo"])))
        for item in (problems.get("items") or []) + (problems.get("fixed") or []):
            target = item["target"]
            label_ru, label_kk = target.get("label_ru") or "", target.get("label_kk") or ""
            if item.get("state") == "fixed" and item.get("fixed_at"):
                feed.append({"at": item["fixed_at"], "kind": "problem.fixed", "title_ru": f"Исправлено: {label_ru}",
                             "title_kk": f"Түзетілді: {label_kk}", "target": target, "demo": item.get("demo", False)})
            elif item.get("last_at"):
                sub = item.get("subtopic") or {}
                feed.append({"at": item["last_at"], "kind": "problem.new",
                             "title_ru": f"Жители сообщили: {sub.get('ru') or 'проблема'} — {label_ru}",
                             "title_kk": f"Тұрғындар хабарлады: {sub.get('kk') or 'мәселе'} — {label_kk}",
                             "target": target, "demo": item.get("demo", False)})
        feed.sort(key=lambda e: e["at"] or "", reverse=True)
        return feed[:12]

    def _event_text(self, event: dict, cache: dict, audience: str | None = None) -> dict | None:
        iid = event.get("initiative_id")
        if not iid:
            return None
        if iid not in cache:
            try:
                cache[iid] = self.store.get(iid)
            except LookupError:
                cache[iid] = None
        item = cache[iid]
        # Запись на проверке или снятая видна в ленте только автору (событие «не опубликовано»).
        if item is None or (item["status"] in ("on_review", "hidden") and (audience or event.get("audience")) != "author"):
            return None
        pattern = EVENT_TEXT.get((event["code"], audience or event.get("audience") or "yard"))
        if pattern is None:
            return None
        n = (item.get("report") or {}).get("joined_final") or item.get("joined") or 0
        title = item.get("title_public") or item["title"]
        return {"title_ru": pattern[0].format(title=title, n=n), "title_kk": pattern[1].format(title=title, n=n),
                "link": "#together/" + iid, "initiative_id": iid}

    def yard_membership(self, yard_id: str, join: bool, body: dict, context) -> dict:
        self._resident_write(context)
        device = self._device(body, context)
        self._limit("yard", device)
        geo, known = self._yard_info(yard_id)
        if geo is None and known is None:
            raise LookupError(yard_id)
        if join:
            point = (geo or {}).get("point")
            members, changed = self.store.join_yard(
                yard_id, device, label_ru=(geo or {}).get("label_ru"), label_kk=(geo or {}).get("label_kk"),
                district=neighbors.district_of(point) if point else None, point=point)
        else:
            members, changed = self.store.leave_yard(yard_id, device)
        return _reply(200, {"yard_id": yard_id, "members": members, "member": join, "changed": changed})

    def captain(self, yard_id: str, body: dict, context) -> dict:
        self._resident_write(context)
        device = self._device(body, context)
        self._limit("captain", device)
        if body.get("remove") is True:
            yard = self.store.set_captain(yard_id, device, None)
        else:
            name = clean_text(body.get("display_name"), field="display_name", low=CAPTAIN_MIN, high=CAPTAIN_MAX)
            if moderation.hints(name):
                raise ApiError(422, "personal_data", "Только имя — без телефона и других данных.", "display_name")
            yard = self.store.set_captain(yard_id, device, name)
        return _reply(200, {"yard_id": yard_id, "captain_status": yard.get("captain_status")
                            if yard.get("captain_hash") == self.store.device_hash(device) else None})

    def moderate_captain(self, yard_id: str, body: dict) -> dict:
        action = body.get("action")
        if action not in ("publish", "hide"):
            raise ApiError(422, "invalid", "action: publish или hide.", "action")
        yard = self.store.moderate_captain(yard_id, action == "publish")
        return _reply(200, {"yard_id": yard_id, "captain_status": yard.get("captain_status")})

    # ------------------------------------------------------------------ лента уведомлений (R06)
    def updates(self, device_id: str, since: str | None = None, limit: int = 50) -> list[dict]:
        """События для ленты «Что нового для меня» (CONTRACT §5.8) — функция для сборщика R06 и маршрута updates."""
        if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
            return []
        since_iso = None
        if since:
            moment = parse_iso(since)
            since_iso = iso(moment) if moment else None
        out, cache = [], {}
        for event in self.store.events_for_device(device_id, since_iso, limit=limit):
            text = self._event_text(event, cache, audience=event["audience"])
            if not text:
                continue
            item = cache.get(event["initiative_id"]) or {}
            if event["audience"] == "yard":
                target = {"kind": "area", "id": event["yard_id"]}
            else:
                target = {"kind": item.get("target_kind") or "area", "id": item.get("target_id")} \
                    if item.get("target_id") else None
            out.append({"id": f"tg-{event['seq']}", "at": event["at"], "module": "R16",
                        "kind": EVENT_KIND[event["audience"]], "target": target, "title_ru": text["title_ru"],
                        "title_kk": text["title_kk"], "link": text["link"], "demo": bool(event["demo"])})
        return out

    def updates_route(self, q: dict, context) -> dict:
        device = self._device({}, context, q)
        # «+05:00» в адресе без кодирования приходит пробелом (parse_qs) — возвращаем плюс.
        since = (q.get("since") or "").strip().replace(" ", "+") or None
        if since and parse_iso(since) is None:
            raise ApiError(400, "bad_request", "since: время ISO 8601.", "since")
        return _reply(200, {"items": self.updates(device, since), "now": iso(self.store.now()),
                            "yards": self.store.my_yards(device)})

    # ------------------------------------------------------------------ идея -> инициатива (R06)
    def create_from_idea(self, idea: dict, *, starts_at: str | None = None, actor: str = "staff",
                         kind: str | None = None) -> dict:
        """Идея жителя (R06 DTO) -> опубликованная инициатива «Сделайте вместе — поддержим инвентарём».

        Вызывает R06 (POST ideas/{id}/to-initiative, сотрудник). Повтор для той же идеи — та же инициатива."""
        if not isinstance(idea, dict) or not idea.get("id"):
            raise ValueError("idea: нужна запись идеи R06 с id")
        existing = [r for r in self.store.list(statuses=("on_review", "published", "done", "cancelled", "hidden"),
                                               limit=LIST_LIMIT, order="recent") if r.get("from_idea") == idea["id"]]
        if existing:
            return self._public(existing[0])
        points = neighbors._points(idea.get("geometry"))
        if not points:
            raise ValueError("idea: у идеи нет места на карте")
        lang = idea.get("lang") if idea.get("lang") in ("ru", "kk") else "ru"
        title = (idea.get("title_" + lang) or idea.get("title") or idea.get("title_ru") or "")[:TITLE_MAX]
        text = (idea.get("description_" + lang) or idea.get("description") or "")[:TEXT_MAX]
        object_kind = ((idea.get("object") or {}).get("kind") or "")
        kind = kind or {"greening": "greening", "square": "greening", "playground": "repair", "benches": "repair",
                        "lighting": "repair", "sports": "repair"}.get(object_kind, "other")
        starts = parse_iso(starts_at) if starts_at else None
        if starts is None:
            from .demo import next_weekday
            starts = next_weekday(self.store.now(), 5, 10)
        body = {"kind": kind, "title": title if len(title) >= TITLE_MIN else "Сделаем вместе", "text": text,
                "point": [points[0][0], points[0][1]], "starts_at": iso(starts), "lang": lang}
        fields = self._clean_fields(body)
        fields["from_idea"] = idea["id"]
        fields["moderation"] = {"flags": [], "source": "idea"}  # текст идеи уже прошёл проверку R06
        item, _created = self.store.create(fields, device_id=None, status="published", actor=actor)
        self.store.support(item["id"], {"inventory": True, "pickup_service": "waste",
                                        "note": "Сделайте вместе — поддержим инвентарём"}, actor=actor)
        return self._public(self.store.get(item["id"]))


def make_service(db_path, *, clock=None, demo: bool | None = None, autopublish: bool | None = None) -> TogetherService:
    """Сервис на базе шлюза. demo=None — по переменной CIVIC_DEMO=1 (run-city.bat): тогда засевается демо-набор
    (без демо-мира R02; с CIVIC_DEMO_WORLD=1 R01 вызывает seed_world, и своя фикстура не нужна)."""
    store = TogetherStore(db_path, clock=clock) if clock else TogetherStore(db_path)
    want_demo = (os.environ.get("CIVIC_DEMO") == "1") if demo is None else demo
    if want_demo and not (demo is None and os.environ.get("CIVIC_DEMO_WORLD") == "1"):
        from . import demo as demo_data
        yards, items = demo_data.rows(store.now())
        store.seed(yards, items)
    service = TogetherService(store, autopublish=autopublish)
    _register(service)
    return service


# Последний сервис процесса: функции модуля updates() и create_from_idea() для R06 работают без db_path.
_services: dict = {}


def _register(service: TogetherService) -> None:
    _services[service.store.db_path] = service
    _services[None] = service


def default_service(db_path=None) -> TogetherService | None:
    if db_path is not None:
        key = str(db_path)
        return _services.get(key) or make_service(key, demo=False)
    if None in _services:
        return _services[None]
    env = os.environ.get("CIVIC_DB_PATH")
    return make_service(env, demo=False) if env else None


__all__ = ["ApiError", "TogetherService", "default_service", "make_service"]
