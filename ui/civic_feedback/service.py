"""R06 civic-v1: сообщения жителей о городских объектах и очередь модерации.

FeedbackService(db_path, object_lookup, clock=None).handle(method, path, query,
body, principal, context) -> None | {status, headers, body}.

* Сообщение — запись на платформе, а не официальное обращение iKOMEK/eOtinish.
  Статусы описывают только модерацию на сайте и не обещают работ городских служб.
* Публично видно лишь approved + consent_public=true + согласие не отозвано.
* Права берутся только из principal (его даёт серверный resolve_principal R02/R01).
  Поля role/actor/revision из JSON не принимаются.
* Хранилище — собственные таблицы feedback_* в SQLite. Чужие таблицы не меняются.
* Классификатор R08 необязателен: его отсутствие, ошибка или зависание не теряют
  сообщение, а машинная категория остаётся подсказкой модератору.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import math
from pathlib import Path
import re
import secrets
import sqlite3
import threading
from urllib.parse import parse_qs, unquote, urlsplit

from . import text as textutil

LOGGER = logging.getLogger(__name__)

API_PREFIX = "/api/civic/v1"
SCHEMA_VERSION = "civic-feedback-v1"
CITY = "astana"
CATEGORIES = ("roads", "sidewalks", "transport_stops", "lighting", "landscaping", "other")
CATEGORY_LABELS = {
    "roads": "Дороги",
    "sidewalks": "Тротуары и пешеходные пути",
    "transport_stops": "Остановки транспорта",
    "lighting": "Освещение",
    "landscaping": "Благоустройство и озеленение",
    "other": "Другое",
}
KINDS = ("problem", "suggestion")
KIND_LABELS = {"problem": "Проблема", "suggestion": "Предложение"}
MODERATION = ("pending", "approved", "rejected")
# Формулировки сознательно не обещают исполнения городскими службами.
MODERATION_LABELS = {
    "pending": "Ожидает проверки модератором платформы",
    "approved": "Проверено модератором платформы",
    "rejected": "Отклонено модератором платформы",
}
PUBLIC_NOTICE = ("Сообщения жителей на платформе. Это не официальные обращения: "
                 "регистрация в iKOMEK/eOtinish не выполняется, публикация не означает, "
                 "что работы начаты или запланированы.")
RECEIPT_NOTICE = ("Сообщение сохранено на платформе и ожидает проверки модератором. "
                  "Официальная регистрация обращения не выполняется; городские службы "
                  "автоматически не уведомляются.")
PUBLIC_ACTOR_LABEL = "Модератор платформы"
DEFAULT_STAFF_ROLES = frozenset({"editor", "moderator", "admin"})
# Широкая рамка вокруг Астаны (lon_min, lat_min, lon_max, lat_max), WGS84.
ASTANA_BBOX = (70.9, 50.8, 72.0, 51.5)
OBJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")
STAFF_ID = re.compile(r"^[0-9]{1,12}$")
RECEIPT_ID = re.compile(r"^fbr_[A-Za-z0-9_-]{16,64}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")

DEFAULT_LIMITS = {
    "max_body_bytes": 16 * 1024,
    "text_min": 10,
    "text_max": 2000,
    "reason_min": 3,
    "reason_max": 500,
    "reply_max": 2000,
    "per_sender_window_s": 600,
    "per_sender_max": 5,
    "per_sender_day_max": 30,
    "global_window_s": 60,
    "global_max": 60,
    "duplicate_window_s": 24 * 3600,
    "location_conflict_m": 1500.0,
    "similar_radius_m": 300.0,
    "similar_window_days": 180,
    "similar_threshold": 0.35,
    "classifier_timeout_s": 2.0,
    "page_size": 20,
    "page_max": 50,
}

SUBMIT_FIELDS = frozenset({"object_id", "geometry", "category", "text", "consent_public",
                           "kind", "client_request_id", "confirm_duplicate"})
MODERATE_FIELDS = frozenset({"expected_revision", "action", "reason", "public_reply", "public_text"})
RECEIPT_FIELDS = frozenset({"receipt_id"})

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS feedback_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_id TEXT NOT NULL UNIQUE,
  receipt_id TEXT NOT NULL UNIQUE,
  city TEXT NOT NULL,
  object_id TEXT,
  lon REAL,
  lat REAL,
  kind TEXT NOT NULL,
  category TEXT NOT NULL,
  text TEXT NOT NULL,
  text_fingerprint TEXT NOT NULL,
  language TEXT NOT NULL,
  consent_public INTEGER NOT NULL CHECK (consent_public IN (0, 1)),
  consent_withdrawn_at TEXT,
  moderation TEXT NOT NULL CHECK (moderation IN ('pending', 'approved', 'rejected')),
  public_text TEXT,
  public_reply TEXT,
  moderation_reason TEXT,
  moderated_by TEXT,
  moderated_at TEXT,
  published_at TEXT,
  revision INTEGER NOT NULL CHECK (revision >= 1),
  created_at TEXT NOT NULL,
  created_ts REAL NOT NULL,
  updated_at TEXT NOT NULL,
  client_hash TEXT NOT NULL,
  client_request_id TEXT,
  duplicate_confirmed INTEGER NOT NULL DEFAULT 0,
  classifier_status TEXT NOT NULL DEFAULT 'not_run',
  classifier_json TEXT
);
CREATE INDEX IF NOT EXISTS feedback_messages_object
  ON feedback_messages (object_id, moderation, consent_public);
CREATE INDEX IF NOT EXISTS feedback_messages_sender
  ON feedback_messages (client_hash, created_ts);
CREATE INDEX IF NOT EXISTS feedback_messages_queue
  ON feedback_messages (moderation, id);
CREATE TABLE IF NOT EXISTS feedback_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL REFERENCES feedback_messages (id),
  revision INTEGER NOT NULL,
  at TEXT NOT NULL,
  action TEXT NOT NULL,
  actor_kind TEXT NOT NULL,
  actor TEXT,
  reason TEXT,
  changed_fields TEXT NOT NULL,
  is_public INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS feedback_events_message ON feedback_events (feedback_id, id);
"""

# Видимость в публичной проекции — единственное место, где она определяется.
PUBLIC_WHERE = ("moderation = 'approved' AND consent_public = 1 "
                "AND consent_withdrawn_at IS NULL AND public_text IS NOT NULL")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | None = None,
                 extra: dict | None = None, headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.fields, self.extra, self.headers = fields, extra, headers


def _ok(status: int, data, *, private: bool = True) -> dict:
    headers = {"Cache-Control": "no-store" if private else "no-cache"}
    return {"status": status, "headers": headers, "body": {"ok": True, "data": data}}


def _error(exc: ApiError) -> dict:
    error = {"code": exc.code, "message": exc.message}
    if exc.fields:
        error["fields"] = exc.fields
    if exc.extra:
        error.update(exc.extra)
    headers = {"Cache-Control": "no-store"}
    headers.update(exc.headers or {})
    return {"status": exc.status, "headers": headers, "body": {"ok": False, "error": error}}


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _geometry_points(geometry) -> list[tuple[float, float]]:
    """Вершины civic-v1 геометрии объекта; некорректная геометрия даёт пустой список."""
    if not isinstance(geometry, Mapping):
        return []
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        coords = [coords]
    elif kind == "Polygon" and isinstance(coords, list):
        coords = [point for ring in coords if isinstance(ring, list) for point in ring]
    elif kind != "LineString":
        return []
    points = []
    for point in coords if isinstance(coords, list) else []:
        if (isinstance(point, list) and len(point) >= 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in point[:2])):
            points.append((float(point[0]), float(point[1])))
    return points


def _distance_to_object_m(lon: float, lat: float, geometry) -> float | None:
    points = _geometry_points(geometry)
    if not points:
        return None
    if geometry.get("type") == "Polygon":
        lons, lats = [p[0] for p in points], [p[1] for p in points]
        if min(lons) <= lon <= max(lons) and min(lats) <= lat <= max(lats):
            return 0.0
    # Расстояние до ближайшей вершины: грубо, но достаточно для поиска противоречия.
    return min(_haversine_m(lon, lat, p[0], p[1]) for p in points)


def _header(context: Mapping, name: str) -> str | None:
    headers = context.get("headers") or {}
    if hasattr(headers, "get") and headers.get(name) is not None:
        return headers.get(name)
    lowered = name.lower()
    try:
        for key, value in headers.items():
            if str(key).lower() == lowered:
                return value
    except AttributeError:
        return None
    return None


class FeedbackService:
    """Сервис сообщений жителей. Потокобезопасен: одно соединение под блокировкой."""

    def __init__(self, db_path, object_lookup: Callable[[str], Mapping | None],
                 clock: Callable[[], datetime | float] | None = None, *,
                 classifier: Callable[[str, str], Mapping] | None = None,
                 staff_roles=DEFAULT_STAFF_ROLES, limits: Mapping | None = None):
        if not callable(object_lookup):
            raise TypeError("object_lookup должен быть функцией object_id -> объект|None")
        self.object_lookup = object_lookup
        self.clock = clock
        self.classifier = classifier
        self.staff_roles = frozenset(staff_roles)
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self._lock = threading.RLock()
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False,
                                   isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._db.executescript(SCHEMA_SQL)
            self._db.execute("INSERT OR IGNORE INTO feedback_meta (key, value) VALUES (?, ?)",
                             ("schema_version", SCHEMA_VERSION))
            # Соль для хэша адреса клиента живёт только в runtime-БД, не в Git.
            self._db.execute("INSERT OR IGNORE INTO feedback_meta (key, value) VALUES (?, ?)",
                             ("client_salt", secrets.token_hex(32)))
            self._salt = self._db.execute(
                "SELECT value FROM feedback_meta WHERE key = 'client_salt'").fetchone()[0].encode()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    # ------------------------------------------------------------------ routing
    def handle(self, method, path, query, body, principal, context):
        """Ответ API-конверта для маршрутов R06 либо None, если путь не наш."""
        method = (method or "").upper()
        segments = self._segments(path)
        if segments is None:
            return None
        context = context if isinstance(context, Mapping) else {}
        try:
            route = self._route(method, segments)
            if route is None:
                return None
            handler, args = route
            return handler(*args, query=self._query(query, path), body=body,
                           principal=principal, context=context)
        except ApiError as exc:
            return _error(exc)
        except sqlite3.Error:
            LOGGER.exception("feedback storage error")
            return _error(ApiError(503, "storage_unavailable",
                                   "Хранилище сообщений временно недоступно. Текст не потерян в форме — повторите позже."))

    @staticmethod
    def _segments(path) -> list[str] | None:
        if not isinstance(path, str):
            return None
        raw = urlsplit(path).path
        if raw.startswith(API_PREFIX + "/"):
            raw = raw[len(API_PREFIX):]
        elif raw == API_PREFIX:
            return None
        parts = [unquote(part) for part in raw.split("/") if part != ""]
        if not parts:
            return None
        if parts[0] == "feedback":
            return parts
        if parts[0] == "staff" and len(parts) >= 2 and parts[1] == "feedback":
            return parts
        if parts[0] == "objects" and len(parts) >= 3 and parts[2] == "feedback":
            return parts
        return None

    def _route(self, method, parts):
        def need(allowed, handler, *args):
            if method == "HEAD" and "GET" in allowed:
                return handler, args
            if method not in allowed:
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.",
                               headers={"Allow": ", ".join(allowed)})
            return handler, args

        not_found = ApiError(404, "not_found", "Адрес не найден.")
        if parts[0] == "objects":
            if len(parts) != 3:
                raise not_found
            return need(("GET",), self._public_list, parts[1])
        if parts[0] == "feedback":
            if len(parts) == 1:
                return need(("POST",), self._submit)
            if parts[1:] == ["receipt"]:
                return need(("POST",), self._receipt_status)
            if parts[1:] == ["withdraw-consent"]:
                return need(("POST",), self._withdraw_consent)
            raise not_found
        # staff/feedback...
        if len(parts) == 2:
            return need(("GET",), self._queue)
        if len(parts) == 3:
            return need(("GET",), self._staff_detail, parts[2])
        if len(parts) == 4 and parts[3] == "moderate":
            return need(("POST",), self._moderate, parts[2])
        raise not_found

    @staticmethod
    def _query(query, path) -> dict:
        if query is None:
            query = urlsplit(path).query if isinstance(path, str) else ""
        if isinstance(query, (str, bytes)):
            query = parse_qs(query.decode() if isinstance(query, bytes) else query)
        result = {}
        for key, value in (query.items() if isinstance(query, Mapping) else []):
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            result[str(key)] = "" if value is None else str(value)
        return result

    # ---------------------------------------------------------------- helpers
    def _now(self) -> datetime:
        value = self.clock() if self.clock else datetime.now(timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def _client_hash(self, context: Mapping) -> str:
        client = str(context.get("client_ip") or "unknown")
        return hmac.new(self._salt, client.encode("utf-8"), hashlib.sha256).hexdigest()

    def _json_body(self, body) -> dict:
        limit = self.limits["max_body_bytes"]
        if body is None or body == b"" or body == "":
            raise ApiError(400, "invalid_body", "Ожидается JSON-объект в теле запроса.")
        if isinstance(body, (bytes, bytearray, str)):
            raw = body.encode("utf-8") if isinstance(body, str) else bytes(body)
            if len(raw) > limit:
                raise ApiError(413, "too_large", "Слишком большой запрос.")
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                raise ApiError(400, "invalid_json", "Тело запроса — не корректный JSON.") from None
        elif isinstance(body, Mapping):
            try:
                size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except (TypeError, ValueError):
                raise ApiError(400, "invalid_body", "Тело запроса нельзя представить как JSON.") from None
            if size > limit:
                raise ApiError(413, "too_large", "Слишком большой запрос.")
        if not isinstance(body, Mapping):
            raise ApiError(400, "invalid_body", "Ожидается JSON-объект в теле запроса.")
        return dict(body)

    @staticmethod
    def _reject_unknown(body: dict, allowed: frozenset) -> None:
        unknown = sorted(key for key in body if key not in allowed)
        if unknown:
            raise ApiError(400, "unknown_fields", "Запрос содержит недопустимые поля.",
                           fields={key: "Поле не принимается сервером." for key in unknown})

    @staticmethod
    def _require_same_origin(context: Mapping) -> None:
        if context.get("is_same_origin") is not True:
            raise ApiError(403, "cross_origin", "Запрос с другого сайта отклонён.")

    def _staff(self, principal, context: Mapping, *, write: bool) -> str:
        """Проверка редактора: только серверный principal, роль, срок, Origin и CSRF."""
        if principal is None:
            raise ApiError(401, "unauthenticated", "Войдите как редактор платформы.")
        get = principal.get if isinstance(principal, Mapping) else (lambda key, default=None: getattr(principal, key, default))
        if get("authenticated", True) is not True:
            raise ApiError(401, "unauthenticated", "Сессия закрыта. Войдите снова.")
        expires = get("expires_at")
        if expires is not None:
            try:
                moment = expires if isinstance(expires, datetime) else datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
            except ValueError:
                raise ApiError(401, "unauthenticated", "Сессия недействительна. Войдите снова.") from None
            if moment <= self._now():
                raise ApiError(401, "session_expired", "Сессия истекла. Войдите снова — действие не выполнено.")
        role = get("role")
        name = get("name") or get("username") or get("id")
        if role not in self.staff_roles or not isinstance(name, str) or not name:
            raise ApiError(403, "forbidden", "Недостаточно прав для модерации сообщений.")
        if write:
            self._require_same_origin(context)
            if context.get("csrf_verified") is not True:
                expected = get("csrf_token")
                supplied = _header(context, "X-CSRF-Token")
                if not (isinstance(expected, str) and expected and isinstance(supplied, str)
                        and hmac.compare_digest(expected, supplied)):
                    raise ApiError(403, "csrf_failed", "Проверка CSRF не пройдена. Обновите страницу.")
        return name

    def _lookup(self, object_id: str) -> Mapping | None:
        try:
            item = self.object_lookup(object_id)
        except Exception:  # чужой модуль: сбой не должен становиться traceback-ответом
            LOGGER.exception("object_lookup failed")
            raise ApiError(503, "object_lookup_unavailable",
                           "Справочник объектов временно недоступен. Повторите позже.") from None
        return item if isinstance(item, Mapping) else None

    @staticmethod
    def _is_public_object(item: Mapping | None) -> bool:
        return bool(item) and item.get("city") == CITY and item.get("publication") == "published"

    def _paging(self, query: dict) -> tuple[int, int]:
        try:
            limit = int(query.get("limit") or self.limits["page_size"])
            offset = int(query.get("cursor") or 0)
        except ValueError:
            raise ApiError(400, "invalid_query", "Параметры limit/cursor должны быть числами.") from None
        if not 1 <= limit <= self.limits["page_max"] or offset < 0 or offset > 1_000_000:
            raise ApiError(400, "invalid_query", "Недопустимые limit/cursor.")
        return limit, offset

    # ------------------------------------------------------------ resident API
    def _validate_submission(self, body: dict) -> dict:
        self._reject_unknown(body, SUBMIT_FIELDS)
        fields: dict[str, str] = {}
        limits = self.limits

        kind = body.get("kind", "problem")
        if kind not in KINDS:
            fields["kind"] = "Выберите: проблема или предложение."
        category = body.get("category")
        if category not in CATEGORIES:
            fields["category"] = "Выберите категорию из списка."
        consent = body.get("consent_public")
        if not isinstance(consent, bool):
            fields["consent_public"] = "Укажите явно, можно ли публиковать текст (да или нет)."
        raw_text = body.get("text")
        text = textutil.clean_text(raw_text) if isinstance(raw_text, str) else None
        if text is None:
            fields["text"] = "Напишите текст сообщения."
        elif len(text) < limits["text_min"]:
            fields["text"] = f"Опишите подробнее: не меньше {limits['text_min']} символов."
        elif len(text) > limits["text_max"]:
            fields["text"] = f"Слишком длинный текст: не больше {limits['text_max']} символов."

        object_id = body.get("object_id")
        if object_id is not None and not (isinstance(object_id, str) and OBJECT_ID.match(object_id)):
            fields["object_id"] = "Некорректный идентификатор объекта."
        point = None
        geometry = body.get("geometry")
        if geometry is not None:
            point = self._parse_point(geometry, fields)
        if object_id is None and geometry is None:
            fields["location"] = "Выберите объект на карте или укажите место."
        request_id = body.get("client_request_id")
        if request_id is not None and not (isinstance(request_id, str) and REQUEST_ID.match(request_id)):
            fields["client_request_id"] = "Некорректный идентификатор отправки."
        confirm = body.get("confirm_duplicate", False)
        if not isinstance(confirm, bool):
            fields["confirm_duplicate"] = "Ожидается true или false."
        if fields:
            code = "location_required" if set(fields) == {"location"} else "validation_failed"
            raise ApiError(422, code, "Проверьте поля формы.", fields=fields)
        return {"kind": kind, "category": category, "consent": consent, "text": text,
                "object_id": object_id, "point": point, "request_id": request_id,
                "confirm_duplicate": confirm}

    @staticmethod
    def _parse_point(geometry, fields: dict) -> tuple[float, float] | None:
        if not (isinstance(geometry, Mapping) and geometry.get("type") == "Point"
                and set(geometry) <= {"type", "coordinates"}):
            fields["geometry"] = "Место передаётся как GeoJSON Point [долгота, широта]."
            return None
        coords = geometry.get("coordinates")
        if not (isinstance(coords, list) and len(coords) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                        for v in coords)):
            fields["geometry"] = "Координаты точки: [долгота, широта] конечными числами."
            return None
        lon, lat = float(coords[0]), float(coords[1])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            fields["geometry"] = "Координаты вне диапазона WGS84."
            return None
        lon_min, lat_min, lon_max, lat_max = ASTANA_BBOX
        if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
            fields["geometry"] = "Место находится за пределами Астаны."
            return None
        return lon, lat

    def _submit(self, *, query, body, principal, context):
        self._require_same_origin(context)
        data = self._validate_submission(self._json_body(body))
        object_id, point = data["object_id"], data["point"]
        if object_id is not None:
            item = self._lookup(object_id)
            # Черновик, архив и несуществующий объект неразличимы для жителя.
            if not self._is_public_object(item):
                raise ApiError(422, "object_not_found", "Объект не найден среди опубликованных объектов Астаны.",
                               fields={"object_id": "Объект не найден или не опубликован."})
            if point is not None:
                distance = _distance_to_object_m(point[0], point[1], item.get("geometry"))
                if distance is not None and distance > self.limits["location_conflict_m"]:
                    raise ApiError(422, "location_conflict",
                                   "Указанное место далеко от выбранного объекта. Уточните объект или точку.",
                                   fields={"geometry": f"Около {round(distance / 1000, 1)} км от объекта."})

        now = self._now()
        now_ts = now.timestamp()
        client_hash = self._client_hash(context)
        fingerprint = textutil.text_fingerprint(data["text"])
        limits = self.limits
        with self._transaction() as db:
            if data["request_id"]:
                previous = db.execute(
                    "SELECT * FROM feedback_messages WHERE client_request_id = ? AND client_hash = ? "
                    "AND created_ts >= ?", (data["request_id"], client_hash,
                                            now_ts - limits["duplicate_window_s"])).fetchone()
                if previous is not None:
                    if previous["text_fingerprint"] != fingerprint or previous["object_id"] != object_id:
                        raise ApiError(409, "request_id_conflict",
                                       "Идентификатор отправки уже использован для другого сообщения.")
                    # Повтор той же отправки (например, после обрыва сети) — тот же receipt.
                    return _ok(200, self._receipt(previous, replayed=True))

            recent = db.execute("SELECT COUNT(*) FROM feedback_messages WHERE client_hash = ? AND created_ts >= ?",
                                (client_hash, now_ts - limits["per_sender_window_s"])).fetchone()[0]
            daily = db.execute("SELECT COUNT(*) FROM feedback_messages WHERE client_hash = ? AND created_ts >= ?",
                               (client_hash, now_ts - 86400)).fetchone()[0]
            overall = db.execute("SELECT COUNT(*) FROM feedback_messages WHERE created_ts >= ?",
                                 (now_ts - limits["global_window_s"],)).fetchone()[0]
            if recent >= limits["per_sender_max"] or daily >= limits["per_sender_day_max"]:
                raise ApiError(429, "rate_limited", "Слишком много сообщений подряд. Попробуйте позже.",
                               headers={"Retry-After": str(int(limits["per_sender_window_s"]))})
            if overall >= limits["global_max"]:
                raise ApiError(429, "rate_limited", "Сервис перегружен. Попробуйте через минуту.",
                               headers={"Retry-After": str(int(limits["global_window_s"]))})

            if not data["confirm_duplicate"]:
                same = db.execute(
                    "SELECT id FROM feedback_messages WHERE client_hash = ? AND text_fingerprint = ? "
                    "AND object_id IS ? AND created_ts >= ? LIMIT 1",
                    (client_hash, fingerprint, object_id, now_ts - limits["duplicate_window_s"])).fetchone()
                if same is not None:
                    raise ApiError(409, "duplicate_warning",
                                   "Такое же сообщение уже отправлено с этого устройства. "
                                   "Отправить ещё раз всё равно?",
                                   extra={"can_confirm": True})

            stamp = _iso(now)
            receipt_id = "fbr_" + secrets.token_urlsafe(18)
            cursor = db.execute(
                "INSERT INTO feedback_messages (public_id, receipt_id, city, object_id, lon, lat, kind, "
                "category, text, text_fingerprint, language, consent_public, moderation, revision, "
                "created_at, created_ts, updated_at, client_hash, client_request_id, duplicate_confirmed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1, ?, ?, ?, ?, ?, ?)",
                ("fbp_" + secrets.token_urlsafe(9), receipt_id, CITY, object_id,
                 point[0] if point else None, point[1] if point else None,
                 data["kind"], data["category"], data["text"], fingerprint,
                 textutil.detect_language(data["text"]), int(data["consent"]),
                 stamp, now_ts, stamp, client_hash, data["request_id"], int(data["confirm_duplicate"])))
            message_id = cursor.lastrowid
            self._event(message_id, 1, stamp, "submitted", "resident", None, None,
                        ["text", "category", "kind", "location", "consent_public"], False)

        # Сообщение уже сохранено; классификатор может только добавить подсказку.
        self._classify(message_id, data["text"])
        with self._lock:
            row = self._db.execute("SELECT * FROM feedback_messages WHERE id = ?", (message_id,)).fetchone()
        return _ok(201, self._receipt(row))

    def _receipt(self, row, *, replayed: bool = False) -> dict:
        warnings = []
        if textutil.blocking_hints(row["text"]):
            warnings.append("Похоже, в тексте есть контактные данные или номер документа. "
                            "Они не будут опубликованы: модератор скроет их или не опубликует текст.")
        result = {
            "receipt_id": row["receipt_id"],
            "moderation": row["moderation"],
            "moderation_label": MODERATION_LABELS[row["moderation"]],
            "consent_public": bool(row["consent_public"]) and row["consent_withdrawn_at"] is None,
            "submitted_at": row["created_at"],
            "kind": row["kind"],
            "category": row["category"],
            "official_registration": False,
            "notice": RECEIPT_NOTICE,
            "warnings": warnings,
        }
        if replayed:
            result["replayed"] = True
        return result

    def _receipt_row(self, body) -> sqlite3.Row:
        data = self._json_body(body)
        self._reject_unknown(data, RECEIPT_FIELDS)
        receipt_id = data.get("receipt_id")
        if not (isinstance(receipt_id, str) and RECEIPT_ID.match(receipt_id)):
            raise ApiError(422, "validation_failed", "Некорректный номер квитанции.",
                           fields={"receipt_id": "Некорректный номер квитанции."})
        row = self._db.execute("SELECT * FROM feedback_messages WHERE receipt_id = ?", (receipt_id,)).fetchone()
        if row is None:
            raise ApiError(404, "receipt_not_found", "Квитанция не найдена.")
        return row

    def _receipt_status(self, *, query, body, principal, context):
        self._require_same_origin(context)
        with self._lock:
            row = self._receipt_row(body)
        result = self._receipt(row)
        result["public_reply"] = row["public_reply"]
        result["is_public"] = self._row_is_public(row)
        return _ok(200, result)

    def _withdraw_consent(self, *, query, body, principal, context):
        """Автор по номеру квитанции отзывает согласие; публичная карточка исчезает."""
        self._require_same_origin(context)
        with self._transaction():
            row = self._receipt_row(body)
            if row["consent_public"] and row["consent_withdrawn_at"] is None:
                stamp = _iso(self._now())
                revision = row["revision"] + 1
                self._db.execute(
                    "UPDATE feedback_messages SET consent_public = 0, consent_withdrawn_at = ?, "
                    "public_text = NULL, revision = ?, updated_at = ? WHERE id = ?",
                    (stamp, revision, stamp, row["id"]))
                self._event(row["id"], revision, stamp, "consent_withdrawn", "resident", None, None,
                            ["consent_public", "public_text"], False)
                row = self._db.execute("SELECT * FROM feedback_messages WHERE id = ?", (row["id"],)).fetchone()
        result = self._receipt(row)
        result["is_public"] = False
        return _ok(200, result)

    def _public_list(self, object_id, *, query, body, principal, context):
        if not OBJECT_ID.match(object_id):
            raise ApiError(404, "object_not_found", "Объект не найден.")
        if not self._is_public_object(self._lookup(object_id)):
            raise ApiError(404, "object_not_found", "Объект не найден.")
        limit, offset = self._paging(query)
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM feedback_messages WHERE object_id = ? AND {PUBLIC_WHERE} "
                "ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?",
                (object_id, limit + 1, offset)).fetchall()
            items = [self._public_dto(row) for row in rows[:limit]]
        next_cursor = str(offset + limit) if len(rows) > limit else None
        return _ok(200, {"items": items, "next_cursor": next_cursor, "notice": PUBLIC_NOTICE},
                   private=False)

    # --------------------------------------------------------------- projections
    @staticmethod
    def _row_is_public(row) -> bool:
        return (row["moderation"] == "approved" and bool(row["consent_public"])
                and row["consent_withdrawn_at"] is None and row["public_text"] is not None)

    def _public_dto(self, row) -> dict:
        """Allowlist публичной проекции. Никаких причин модерации, контактов, хэшей."""
        events = self._db.execute(
            "SELECT revision, at, action, changed_fields FROM feedback_events "
            "WHERE feedback_id = ? AND is_public = 1 ORDER BY id", (row["id"],)).fetchall()
        return {
            "id": row["public_id"],
            "object_id": row["object_id"],
            "kind": row["kind"],
            "kind_label": KIND_LABELS[row["kind"]],
            "category": row["category"],
            "category_label": CATEGORY_LABELS[row["category"]],
            "text": row["public_text"],
            "public_reply": row["public_reply"],
            "submitted_on": row["created_at"][:10],
            "published_at": row["published_at"],
            "moderation_label": MODERATION_LABELS["approved"],
            "official_registration": False,
            "history": [{"revision": event["revision"], "at": event["at"], "event": event["action"],
                         "changed_fields": json.loads(event["changed_fields"]),
                         "public_actor_label": PUBLIC_ACTOR_LABEL} for event in events],
        }

    def _staff_dto(self, row, *, full_text: bool = True) -> dict:
        classifier = json.loads(row["classifier_json"]) if row["classifier_json"] else None
        hints = textutil.personal_hints(row["text"])
        same_sender = self._db.execute(
            "SELECT COUNT(*) FROM feedback_messages WHERE client_hash = ? AND created_ts BETWEEN ? AND ? AND id != ?",
            (row["client_hash"], row["created_ts"] - 86400, row["created_ts"] + 86400, row["id"])).fetchone()[0]
        return {
            "id": str(row["id"]),
            "public_id": row["public_id"],
            "object_id": row["object_id"],
            "geometry": ({"type": "Point", "coordinates": [row["lon"], row["lat"]]}
                         if row["lon"] is not None else None),
            "kind": row["kind"],
            "category": row["category"],
            "category_label": CATEGORY_LABELS[row["category"]],
            "text": row["text"] if full_text else row["text"][:280],
            "language": row["language"],
            "consent_public": bool(row["consent_public"]),
            "consent_withdrawn_at": row["consent_withdrawn_at"],
            "moderation": row["moderation"],
            "moderation_label": MODERATION_LABELS[row["moderation"]],
            "moderation_reason": row["moderation_reason"],
            "public_text": row["public_text"],
            "public_reply": row["public_reply"],
            "is_public": self._row_is_public(row),
            "revision": row["revision"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "moderated_at": row["moderated_at"],
            "moderated_by": row["moderated_by"],
            "published_at": row["published_at"],
            "personal_data_hints": hints,
            "classifier": {"status": row["classifier_status"], "suggestion": classifier,
                           "note": "Подсказка модели, не решение. Категорию жителя не меняет."},
            "antispam": {"same_sender_24h": same_sender,
                         "duplicate_confirmed_by_sender": bool(row["duplicate_confirmed"])},
        }

    def _staff_history(self, message_id: int) -> list[dict]:
        rows = self._db.execute("SELECT * FROM feedback_events WHERE feedback_id = ? ORDER BY id",
                                (message_id,)).fetchall()
        return [{"id": str(row["id"]), "revision": row["revision"], "at": row["at"],
                 "action": row["action"], "actor_kind": row["actor_kind"], "actor": row["actor"],
                 "reason": row["reason"], "changed_fields": json.loads(row["changed_fields"]),
                 "is_public": bool(row["is_public"])} for row in rows]

    def _event(self, message_id, revision, at, action, actor_kind, actor, reason, changed, public):
        self._db.execute(
            "INSERT INTO feedback_events (feedback_id, revision, at, action, actor_kind, actor, reason, "
            "changed_fields, is_public) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, revision, at, action, actor_kind, actor, reason,
             json.dumps(sorted(changed)), int(public)))

    # ---------------------------------------------------------------- staff API
    def _queue(self, *, query, body, principal, context):
        self._staff(principal, context, write=False)
        clauses, params = [], []
        moderation = query.get("moderation") or "pending"
        if moderation != "all":
            if moderation not in MODERATION:
                raise ApiError(400, "invalid_query", "moderation: pending|approved|rejected|all.")
            clauses.append("moderation = ?")
            params.append(moderation)
        if query.get("object_id"):
            if not OBJECT_ID.match(query["object_id"]):
                raise ApiError(400, "invalid_query", "Некорректный object_id.")
            clauses.append("object_id = ?")
            params.append(query["object_id"])
        for key, allowed in (("category", CATEGORIES), ("kind", KINDS)):
            if query.get(key):
                if query[key] not in allowed:
                    raise ApiError(400, "invalid_query", f"Недопустимое значение {key}.")
                clauses.append(f"{key} = ?")
                params.append(query[key])
        if query.get("consent"):
            if query["consent"] not in ("true", "false"):
                raise ApiError(400, "invalid_query", "consent: true|false.")
            clauses.append("consent_public = ? AND consent_withdrawn_at IS NULL"
                           if query["consent"] == "true" else "(consent_public = ? OR consent_withdrawn_at IS NOT NULL)")
            params.append(1 if query["consent"] == "true" else 0)
        limit, offset = self._paging(query)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        # Очередь pending — старые первыми, остальные — новые первыми.
        order = "ASC" if moderation == "pending" else "DESC"
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM feedback_messages {where} ORDER BY id {order} LIMIT ? OFFSET ?",
                                    (*params, limit + 1, offset)).fetchall()
            items = []
            for row in rows[:limit]:
                item = self._staff_dto(row, full_text=False)
                item["similar_count"] = len(self._similar(row))
                items.append(item)
            counts = {name: 0 for name in MODERATION}
            for name, count in self._db.execute(
                    "SELECT moderation, COUNT(*) FROM feedback_messages GROUP BY moderation"):
                counts[name] = count
        return _ok(200, {"items": items, "next_cursor": str(offset + limit) if len(rows) > limit else None,
                         "counts": counts})

    def _message_by_staff_id(self, message_id: str):
        if not STAFF_ID.match(message_id):
            raise ApiError(404, "feedback_not_found", "Сообщение не найдено.")
        row = self._db.execute("SELECT * FROM feedback_messages WHERE id = ?", (int(message_id),)).fetchone()
        if row is None:
            raise ApiError(404, "feedback_not_found", "Сообщение не найдено.")
        return row

    def _object_summary(self, object_id):
        if object_id is None:
            return None
        try:
            item = self._lookup(object_id)
        except ApiError:
            return {"id": object_id, "available": False}
        if item is None:
            return {"id": object_id, "available": False}
        summary = {key: item.get(key) for key in ("id", "title", "kind", "status", "publication",
                                                  "geometry", "evidence_type", "revision")}
        summary["available"] = True
        return summary

    def _staff_detail(self, message_id, *, query, body, principal, context):
        self._staff(principal, context, write=False)
        with self._lock:
            row = self._message_by_staff_id(message_id)
            item = self._staff_dto(row)
            history = self._staff_history(row["id"])
            similar = self._similar(row)
        return _ok(200, {"item": item, "history": history, "object": self._object_summary(row["object_id"]),
                         "similar": similar,
                         "similar_note": "Похожие сообщения — подсказка. Система не объединяет и не отклоняет их сама."})

    def _similar(self, row, limit: int = 5) -> list[dict]:
        """Похожие сообщения по объекту/месту и нормализованному тексту (только для редактора)."""
        since = row["created_ts"] - self.limits["similar_window_days"] * 86400
        if row["object_id"] is not None:
            candidates = self._db.execute(
                "SELECT * FROM feedback_messages WHERE object_id = ? AND id != ? AND created_ts >= ?",
                (row["object_id"], row["id"], since)).fetchall()
        elif row["lon"] is not None:
            delta = 0.01  # предварительный отбор ~1 км, точное расстояние ниже
            candidates = [
                other for other in self._db.execute(
                    "SELECT * FROM feedback_messages WHERE object_id IS NULL AND id != ? AND created_ts >= ? "
                    "AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?",
                    (row["id"], since, row["lon"] - delta, row["lon"] + delta,
                     row["lat"] - delta, row["lat"] + delta)).fetchall()
                if _haversine_m(row["lon"], row["lat"], other["lon"], other["lat"]) <= self.limits["similar_radius_m"]]
        else:
            candidates = []
        scored = []
        for other in candidates:
            exact = other["text_fingerprint"] == row["text_fingerprint"]
            score = 1.0 if exact else textutil.similarity(row["text"], other["text"])
            if score >= self.limits["similar_threshold"]:
                scored.append({"id": str(other["id"]), "score": round(score, 2), "exact_text": exact,
                               "moderation": other["moderation"], "created_at": other["created_at"],
                               "category": other["category"], "excerpt": other["text"][:160]})
        scored.sort(key=lambda item: (-item["score"], item["id"]))
        return scored[:limit]

    def _moderate(self, message_id, *, query, body, principal, context):
        actor = self._staff(principal, context, write=True)
        data = self._json_body(body)
        self._reject_unknown(data, MODERATE_FIELDS)
        fields: dict[str, str] = {}
        limits = self.limits
        expected = data.get("expected_revision")
        if not (isinstance(expected, int) and not isinstance(expected, bool) and expected >= 1):
            fields["expected_revision"] = "Нужна текущая ревизия сообщения (целое число ≥ 1)."
        action = data.get("action")
        if action not in ("approve", "reject"):
            fields["action"] = "Действие: approve или reject."
        reason = data.get("reason")
        reason = textutil.clean_text(reason) if isinstance(reason, str) else None
        if not reason or not limits["reason_min"] <= len(reason) <= limits["reason_max"]:
            fields["reason"] = f"Укажите причину решения ({limits['reason_min']}–{limits['reason_max']} символов)."
        # Отсутствующий public_reply сохраняет прежний ответ; null — удаляет его.
        reply_given = "public_reply" in data
        reply = data.get("public_reply")
        if reply is not None:
            reply = textutil.clean_text(reply) if isinstance(reply, str) else False
            if reply is False or len(reply) > limits["reply_max"]:
                fields["public_reply"] = f"Ответ — текст до {limits['reply_max']} символов или null."
            elif reply == "":
                reply = None
        public_text = data.get("public_text")
        if public_text is not None:
            public_text = textutil.clean_text(public_text) if isinstance(public_text, str) else False
            if public_text is False or not limits["text_min"] <= len(public_text) <= limits["text_max"]:
                fields["public_text"] = "Публичный текст — от 10 до 2000 символов или null."
        if fields:
            raise ApiError(422, "validation_failed", "Проверьте поля решения.", fields=fields)

        with self._transaction() as db:
            row = self._message_by_staff_id(message_id)
            if row["revision"] != expected:
                raise ApiError(409, "stale_revision",
                               "Сообщение изменено другим действием. Обновите карточку.",
                               extra={"current_revision": row["revision"]})
            consent = bool(row["consent_public"]) and row["consent_withdrawn_at"] is None
            if not reply_given:
                reply = row["public_reply"]
            if public_text is not None and not consent:
                raise ApiError(422, "no_consent",
                               "Автор не разрешил публиковать текст — публичная версия текста недоступна.",
                               fields={"public_text": "Нет согласия автора на публикацию."})
            if public_text is not None and action != "approve":
                raise ApiError(422, "validation_failed", "Публичную версию текста задают только при approve.",
                               fields={"public_text": "Только вместе с action=approve."})
            # При reject редакторская версия сохраняется, но не видна публично.
            new_public_text = row["public_text"] if action == "reject" else None
            if action == "approve" and consent:
                new_public_text = public_text or row["public_text"] or row["text"]
                leaked = textutil.blocking_hints(new_public_text)
                if leaked:
                    raise ApiError(422, "personal_data_suspected",
                                   "В публичном тексте похоже есть персональные данные. Скройте их перед публикацией.",
                                   fields={"public_text": ", ".join(sorted({h["label"] for h in leaked}))},
                                   extra={"hints": leaked})
            if reply:
                if textutil.blocking_hints(reply):
                    raise ApiError(422, "personal_data_suspected",
                                   "Ответ похоже содержит персональные данные.",
                                   fields={"public_reply": "Уберите контакты/номера из ответа."})
                hidden_source = new_public_text if action == "approve" and new_public_text else ""
                quoted = textutil.mentions_any(reply, textutil.hidden_fragments(row["text"], hidden_source))
                if quoted:
                    raise ApiError(422, "reply_reveals_hidden_text",
                                   "Ответ цитирует фрагменты, которые не публикуются. Перефразируйте ответ.",
                                   fields={"public_reply": "Скрытые фрагменты: " + ", ".join(quoted[:5])})

            now = _iso(self._now())
            revision = row["revision"] + 1
            moderation = "approved" if action == "approve" else "rejected"
            visible = moderation == "approved" and new_public_text is not None
            was_visible = self._row_is_public(row)
            published_at = row["published_at"] or (now if visible else None)
            changed = ["moderation", "moderation_reason"]
            if reply != row["public_reply"]:
                changed.append("public_reply")
            if new_public_text != row["public_text"]:
                changed.append("public_text")
            db.execute(
                "UPDATE feedback_messages SET moderation = ?, moderation_reason = ?, public_reply = ?, "
                "public_text = ?, moderated_by = ?, moderated_at = ?, published_at = ?, revision = ?, "
                "updated_at = ? WHERE id = ? AND revision = ?",
                (moderation, reason, reply, new_public_text, actor, now, published_at, revision, now,
                 row["id"], row["revision"]))
            if visible and not was_visible:
                public_event, public_fields = "published", ["text"] + (["public_reply"] if reply else [])
            elif visible:
                public_event = "updated"
                public_fields = [{"public_text": "text"}.get(f, f) for f in changed
                                 if f in ("public_reply", "public_text")]
            else:
                public_event, public_fields = None, []
            self._event(row["id"], revision, now, moderation, "staff", actor, reason, changed, False)
            if public_event and public_fields:
                self._event(row["id"], revision, now, public_event, "staff", actor, None, public_fields, True)
            row = db.execute("SELECT * FROM feedback_messages WHERE id = ?", (row["id"],)).fetchone()
            return _ok(200, {"item": self._staff_dto(row), "history": self._staff_history(row["id"])})

    # --------------------------------------------------------------- classifier
    def _classify(self, message_id: int, text: str) -> None:
        if self.classifier is None:
            self._store_classifier(message_id, "unavailable", None)
            return
        outcome: dict = {}

        def run():
            try:
                outcome["value"] = self.classifier(text, textutil.detect_language(text))
            except Exception as exc:  # чужая модель: любая ошибка = подсказки нет
                outcome["error"] = type(exc).__name__

        worker = threading.Thread(target=run, name="civic-r06-classifier", daemon=True)
        worker.start()
        worker.join(self.limits["classifier_timeout_s"])
        if worker.is_alive():
            self._store_classifier(message_id, "timeout", None)
        elif "error" in outcome:
            LOGGER.warning("classifier error: %s", outcome["error"])
            self._store_classifier(message_id, "error", None)
        else:
            suggestion = self._clean_suggestion(outcome.get("value"))
            self._store_classifier(message_id, "ok" if suggestion else "invalid", suggestion)

    @staticmethod
    def _clean_suggestion(value) -> dict | None:
        if not isinstance(value, Mapping) or value.get("label") not in CATEGORIES:
            return None
        score = value.get("score")
        if not (isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score)):
            score = None
        def short(key):
            item = value.get(key)
            return item[:80] if isinstance(item, str) else None
        return {"label": value["label"], "label_text": CATEGORY_LABELS[value["label"]], "score": score,
                "score_kind": short("score_kind"), "needs_review": value.get("needs_review") is not False,
                "model_version": short("model_version"),
                "training_data_status": short("training_data_status")}

    def _store_classifier(self, message_id: int, status: str, suggestion: dict | None) -> None:
        try:
            with self._lock:
                self._db.execute("UPDATE feedback_messages SET classifier_status = ?, classifier_json = ? WHERE id = ?",
                                 (status, json.dumps(suggestion, ensure_ascii=False) if suggestion else None,
                                  message_id))
        except sqlite3.Error:
            LOGGER.exception("could not store classifier suggestion")

    # ------------------------------------------------------------ maintenance
    def purge_antispam(self, older_than_days: int = 30) -> int:
        """Обезличить служебные антиспам-поля старых сообщений; текст и решения остаются."""
        cutoff = self._now().timestamp() - older_than_days * 86400
        with self._lock:
            cursor = self._db.execute(
                "UPDATE feedback_messages SET client_hash = 'purged', client_request_id = NULL "
                "WHERE created_ts < ? AND client_hash != 'purged'", (cutoff,))
            return cursor.rowcount
