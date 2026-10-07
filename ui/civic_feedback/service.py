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
SCHEMA_VERSION = "civic-feedback-v2"
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
# Статус ОБРАБОТКИ на платформе (round 12) — отдельная ось от публикации (moderation).
# Описывает работу сотрудников этого сервиса, не статус eOtinish/iKOMEK и не работы города.
HANDLING = ("new", "in_review", "answered", "duplicate", "closed")
HANDLING_LABELS = {
    "new": "Новое — ещё не рассмотрено на платформе",
    "in_review": "На рассмотрении у сотрудника платформы",
    "answered": "Дан ответ платформы",
    "duplicate": "Объединено с похожим сообщением",
    "closed": "Рассмотрено на платформе, закрыто",
}
# Допустимые переходы; повторное открытие всегда через in_review.
HANDLING_TRANSITIONS = {
    "new": frozenset({"in_review", "answered", "duplicate", "closed"}),
    "in_review": frozenset({"answered", "duplicate", "closed"}),
    "answered": frozenset({"in_review", "closed"}),
    "duplicate": frozenset({"in_review"}),
    "closed": frozenset({"in_review"}),
}
MODERATE_ACTIONS = ("approve", "reject", "status", "note", "recategorize")
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
    "note_max": 1000,
    "search_max": 100,
    "text_min_letters": 5,
    "text_max_links": 3,
    "page_size": 20,
    "page_max": 50,
}

SUBMIT_FIELDS = frozenset({"object_id", "geometry", "category", "text", "consent_public",
                           "kind", "client_request_id", "confirm_duplicate"})
MODERATE_FIELDS = frozenset({"expected_revision", "action", "reason", "public_reply", "public_text",
                             "status", "duplicate_of", "internal_note", "category"})
# Какие поля допустимы для каждого действия (кроме action/expected_revision).
ACTION_FIELDS = {
    "approve": frozenset({"reason", "public_reply", "public_text", "status", "duplicate_of"}),
    "reject": frozenset({"reason", "public_reply", "status", "duplicate_of"}),
    "status": frozenset({"reason", "public_reply", "status", "duplicate_of"}),
    "note": frozenset({"internal_note"}),
    "recategorize": frozenset({"reason", "category"}),
}
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
  classifier_json TEXT,
  handling_status TEXT NOT NULL DEFAULT 'new',
  duplicate_of INTEGER,
  staff_category TEXT,
  handled_by TEXT,
  handled_at TEXT
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

# Колонки round 12: старая runtime-БД (civic-feedback-v1) дополняется ALTER TABLE без потери строк.
MIGRATION_COLUMNS = (
    ("handling_status", "TEXT NOT NULL DEFAULT 'new'"),
    ("duplicate_of", "INTEGER"),
    ("staff_category", "TEXT"),
    ("handled_by", "TEXT"),
    ("handled_at", "TEXT"),
)
EFFECTIVE_CATEGORY = "COALESCE(staff_category, category)"

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
            self._migrate()
            self._db.execute("INSERT OR REPLACE INTO feedback_meta (key, value) VALUES (?, ?)",
                             ("schema_version", SCHEMA_VERSION))
            # Соль для хэша адреса клиента живёт только в runtime-БД, не в Git.
            self._db.execute("INSERT OR IGNORE INTO feedback_meta (key, value) VALUES (?, ?)",
                             ("client_salt", secrets.token_hex(32)))
            self._salt = self._db.execute(
                "SELECT value FROM feedback_meta WHERE key = 'client_salt'").fetchone()[0].encode()

    def _migrate(self) -> None:
        """civic-feedback-v1 -> v2: добавить колонки обработки, не трогая существующие данные.

        Старым строкам статус обработки выводится из решения модерации: pending -> new;
        решение с ответом -> answered; решение без ответа -> closed. Это консервативно:
        сотрудник может снова открыть сообщение (in_review).
        """
        db = self._db
        db.create_function("r06_norm", 1, lambda value: textutil.normalize_for_match(value or ""),
                           deterministic=True)
        have = {row[1] for row in db.execute("PRAGMA table_info(feedback_messages)")}
        added = [name for name, _ in MIGRATION_COLUMNS if name not in have]
        if added:
            db.execute("BEGIN IMMEDIATE")
            try:
                for name, ddl in MIGRATION_COLUMNS:
                    if name in added:
                        db.execute(f"ALTER TABLE feedback_messages ADD COLUMN {name} {ddl}")
                if "handling_status" in added:
                    db.execute("UPDATE feedback_messages SET handling_status = CASE "
                               "WHEN moderation = 'pending' THEN 'new' "
                               "WHEN public_reply IS NOT NULL THEN 'answered' ELSE 'closed' END")
                db.execute("INSERT OR REPLACE INTO feedback_meta (key, value) VALUES (?, ?)",
                           ("migrated_v2_columns", ",".join(added)))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        db.execute("CREATE INDEX IF NOT EXISTS feedback_messages_handling "
                   "ON feedback_messages (handling_status, id)")

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
            if context.get("host_allowed") is False:
                raise ApiError(403, "host_not_allowed", "Недопустимый адрес сервера.")
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
        except Exception:  # страховка: наружу только конверт, без traceback и путей
            LOGGER.exception("feedback handler failed")
            return _error(ApiError(500, "internal_error", "Не удалось выполнить запрос. Попробуйте ещё раз."))

    @staticmethod
    def _segments(path) -> list[str] | None:
        if not isinstance(path, str):
            return None
        raw = urlsplit(path).path
        # Как CivicService R02: только полный путь /api/civic/v1/...; чужие пути (в т.ч.
        # возможная статическая страница /feedback) не перехватываются.
        if not raw.startswith(API_PREFIX + "/"):
            return None
        raw = raw[len(API_PREFIX):]
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
            self._reject_unencodable(body)
            try:
                size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except (TypeError, ValueError):
                raise ApiError(400, "invalid_body", "Тело запроса нельзя представить как JSON.") from None
            if size > limit:
                raise ApiError(413, "too_large", "Слишком большой запрос.")
        if not isinstance(body, Mapping):
            raise ApiError(400, "invalid_body", "Ожидается JSON-объект в теле запроса.")
        self._reject_unencodable(body)
        return dict(body)

    @classmethod
    def _reject_unencodable(cls, value, depth: int = 0) -> None:
        """JSON допускает одиночные суррогаты (\\ud800), UTF-8 и SQLite — нет: 400, а не исключение."""
        if depth > 20:
            raise ApiError(400, "invalid_body", "Слишком глубокая вложенность JSON.")
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ApiError(400, "invalid_text", "Текст содержит недопустимые символы.") from None
        elif isinstance(value, Mapping):
            for key, item in value.items():
                cls._reject_unencodable(key, depth + 1)
                cls._reject_unencodable(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            for item in value:
                cls._reject_unencodable(item, depth + 1)

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
            # R02 Principal.expires_at — epoch-секунды; допускаются также datetime и ISO8601.
            try:
                if isinstance(expires, bool):
                    raise ValueError(expires)
                if isinstance(expires, (int, float)):
                    moment = datetime.fromtimestamp(float(expires), timezone.utc)
                elif isinstance(expires, datetime):
                    moment = expires
                else:
                    moment = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
            except (ValueError, OverflowError, OSError):
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
        else:
            # Простая защита от мусора: не CAPTCHA и не аккаунт, а проверка, что это текст.
            letters = [ch for ch in text if ch.isalpha()]
            if len(letters) < limits["text_min_letters"] or len(set(ch.casefold() for ch in letters)) < 3:
                fields["text"] = "Опишите ситуацию словами — сообщение должно содержать текст, а не только символы."
            elif len(textutil.links(text)) > limits["text_max_links"]:
                fields["text"] = f"Слишком много ссылок: не больше {limits['text_max_links']}. Опишите ситуацию текстом."

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
                        # Тот же client_request_id и то же устройство: прежняя версия уже сохранена
                        # (ответ мог потеряться в сети). Возвращаем её квитанцию, чтобы автор её не потерял.
                        raise ApiError(409, "request_id_conflict",
                                       "Предыдущая версия этого сообщения уже сохранена. Изменённый текст "
                                       "можно отправить отдельным сообщением.",
                                       extra={"previous_receipt": self._receipt(previous)})
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
            # Статус обработки на платформе (round 12); номер исходного сообщения автору не раскрывается.
            "handling_status": row["handling_status"],
            "handling_label": HANDLING_LABELS[row["handling_status"]],
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
            "handling_status": row["handling_status"],
            "handling_label": HANDLING_LABELS[row["handling_status"]],
            "official_registration": False,
            "history": [{"revision": event["revision"], "at": event["at"], "event": event["action"],
                         "changed_fields": json.loads(event["changed_fields"]),
                         "public_actor_label": PUBLIC_ACTOR_LABEL} for event in events],
        }

    def _staff_dto(self, row) -> dict:
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
            # Категория жителя не перезаписывается; сотрудник может указать свою (staff_category).
            "staff_category": row["staff_category"],
            "effective_category": row["staff_category"] or row["category"],
            "effective_category_label": CATEGORY_LABELS[row["staff_category"] or row["category"]],
            "handling_status": row["handling_status"],
            "handling_label": HANDLING_LABELS[row["handling_status"]],
            "handling_next": sorted(HANDLING_TRANSITIONS[row["handling_status"]]),
            "duplicate_of": str(row["duplicate_of"]) if row["duplicate_of"] is not None else None,
            "handled_by": row["handled_by"],
            "handled_at": row["handled_at"],
            "text": row["text"],
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
        """Очередь сотрудника. Фильтры: moderation, status (обработка), category (с учётом
        исправления сотрудником), kind, consent, object_id, q (поиск по тексту/номеру), order.

        Обратная совместимость: без moderation и status показывается moderation=pending, как в
        civic-v1; если задан только status — moderation по умолчанию all.
        """
        self._staff(principal, context, write=False)
        clauses, params = [], []
        moderation = query.get("moderation") or ("all" if query.get("status") else "pending")
        if moderation != "all":
            if moderation not in MODERATION:
                raise ApiError(400, "invalid_query", "moderation: pending|approved|rejected|all.")
            clauses.append("moderation = ?")
            params.append(moderation)
        status = query.get("status") or ""
        if status and status != "all":
            wanted = status.split(",")
            if not all(item in HANDLING for item in wanted) or len(wanted) > len(HANDLING):
                raise ApiError(400, "invalid_query", "status: " + "|".join(HANDLING) + " (через запятую) или all.")
            clauses.append("handling_status IN (" + ",".join("?" * len(wanted)) + ")")
            params.extend(wanted)
        if query.get("object_id"):
            if not OBJECT_ID.match(query["object_id"]):
                raise ApiError(400, "invalid_query", "Некорректный object_id.")
            clauses.append("object_id = ?")
            params.append(query["object_id"])
        if query.get("category"):
            if query["category"] not in CATEGORIES:
                raise ApiError(400, "invalid_query", "Недопустимое значение category.")
            clauses.append(f"{EFFECTIVE_CATEGORY} = ?")
            params.append(query["category"])
        if query.get("kind"):
            if query["kind"] not in KINDS:
                raise ApiError(400, "invalid_query", "Недопустимое значение kind.")
            clauses.append("kind = ?")
            params.append(query["kind"])
        if query.get("consent"):
            if query["consent"] not in ("true", "false"):
                raise ApiError(400, "invalid_query", "consent: true|false.")
            clauses.append("consent_public = ? AND consent_withdrawn_at IS NULL"
                           if query["consent"] == "true" else "(consent_public = ? OR consent_withdrawn_at IS NOT NULL)")
            params.append(1 if query["consent"] == "true" else 0)
        search = (query.get("q") or "").strip()
        if search:
            if len(search) > self.limits["search_max"]:
                raise ApiError(400, "invalid_query", f"Поиск — не длиннее {self.limits['search_max']} символов.")
            number = search.lstrip("#")
            needle = textutil.normalize_for_match(search)
            if number.isdigit() and len(number) <= 12:
                clauses.append("(id = ? OR instr(r06_norm(text), ?) > 0)")
                params.extend([int(number), needle])
            elif needle:
                clauses.append("instr(r06_norm(text), ?) > 0")
                params.append(needle)
        limit, offset = self._paging(query)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        order = query.get("order") or ""
        if order not in ("", "oldest", "newest"):
            raise ApiError(400, "invalid_query", "order: oldest|newest.")
        # По умолчанию необработанное (pending/new) — старые первыми, остальное — новые первыми.
        if not order:
            order = "oldest" if moderation == "pending" or status in ("new", "in_review", "new,in_review") else "newest"
        direction = "ASC" if order == "oldest" else "DESC"
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM feedback_messages {where} ORDER BY id {direction} LIMIT ? OFFSET ?",
                                    (*params, limit + 1, offset)).fetchall()
            items = []
            for row in rows[:limit]:
                # Полный текст: модератор может решить даже без маршрута GET /staff/feedback/{id}.
                item = self._staff_dto(row)
                item["similar_count"] = len(self._similar(row))
                items.append(item)
            counts = {name: 0 for name in MODERATION}
            for name, count in self._db.execute(
                    "SELECT moderation, COUNT(*) FROM feedback_messages GROUP BY moderation"):
                counts[name] = count
            handling_counts = {name: 0 for name in HANDLING}
            for name, count in self._db.execute(
                    "SELECT handling_status, COUNT(*) FROM feedback_messages GROUP BY handling_status"):
                handling_counts[name] = count
        return _ok(200, {"items": items, "next_cursor": str(offset + limit) if len(rows) > limit else None,
                         "counts": counts, "handling_counts": handling_counts,
                         "filters": {"moderation": moderation, "status": status or "all", "order": order}})

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
            duplicates = [self._brief(other) for other in self._db.execute(
                "SELECT * FROM feedback_messages WHERE duplicate_of = ? AND handling_status = 'duplicate' ORDER BY id",
                (row["id"],)).fetchall()]
            original = None
            if row["duplicate_of"] is not None:
                target = self._db.execute("SELECT * FROM feedback_messages WHERE id = ?", (row["duplicate_of"],)).fetchone()
                original = self._brief(target) if target is not None else None
        return _ok(200, {"item": item, "history": history, "object": self._object_summary(row["object_id"]),
                         "similar": similar, "duplicate_of": original, "duplicates": duplicates,
                         "similar_note": "Похожие сообщения — подсказка. Система не объединяет и не отклоняет их сама."})

    @staticmethod
    def _brief(row) -> dict:
        return {"id": str(row["id"]), "moderation": row["moderation"], "handling_status": row["handling_status"],
                "handling_label": HANDLING_LABELS[row["handling_status"]], "created_at": row["created_at"],
                "category": row["staff_category"] or row["category"], "excerpt": row["text"][:160]}

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
                               "score_kind": "word_overlap",
                               "moderation": other["moderation"], "handling_status": other["handling_status"],
                               "created_at": other["created_at"],
                               "category": other["category"], "excerpt": other["text"][:160]})
        scored.sort(key=lambda item: (-item["score"], item["id"]))
        return scored[:limit]

    def _moderate(self, message_id, *, query, body, principal, context):
        """Действия сотрудника над сообщением (один маршрут, обратно совместимое тело).

        approve/reject — решение о публикации (как в civic-v1) и, при необходимости, статус обработки;
        status — только статус обработки (+ ответ платформы); note — служебная заметка (не публична,
        ревизию не меняет); recategorize — категория сотрудника (категория жителя сохраняется).
        """
        actor = self._staff(principal, context, write=True)
        data = self._json_body(body)
        self._reject_unknown(data, MODERATE_FIELDS)
        limits = self.limits
        fields: dict[str, str] = {}
        action = data.get("action")
        if action not in MODERATE_ACTIONS:
            fields["action"] = "Действие: approve, reject, status, note или recategorize."
        else:
            for key in sorted(data):
                if key not in ("action", "expected_revision") and key not in ACTION_FIELDS[action]:
                    fields[key] = f"Поле не используется с action={action}."
        expected = data.get("expected_revision")
        if action != "note" and not (isinstance(expected, int) and not isinstance(expected, bool) and expected >= 1):
            fields["expected_revision"] = "Нужна текущая ревизия сообщения (целое число ≥ 1)."
        reason = None
        if action != "note":
            reason = data.get("reason")
            reason = textutil.clean_text(reason) if isinstance(reason, str) else None
            if not reason or not limits["reason_min"] <= len(reason) <= limits["reason_max"]:
                fields["reason"] = f"Укажите обоснование ({limits['reason_min']}–{limits['reason_max']} символов)."
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
        status = data.get("status")
        if "status" in data and status not in HANDLING:
            fields["status"] = "Статус: " + ", ".join(HANDLING) + "."
        if action == "status" and status is None and "status" not in fields:
            fields["status"] = "Выберите статус обработки."
        duplicate_of = data.get("duplicate_of")
        if duplicate_of is not None:
            if isinstance(duplicate_of, int) and not isinstance(duplicate_of, bool) and duplicate_of >= 1:
                duplicate_of = str(duplicate_of)
            if not (isinstance(duplicate_of, str) and STAFF_ID.match(duplicate_of)):
                fields["duplicate_of"] = "Номер исходного сообщения — целое число."
        note = None
        if action == "note":
            note = data.get("internal_note")
            note = textutil.clean_text(note) if isinstance(note, str) else None
            if not note or len(note) > limits["note_max"]:
                fields["internal_note"] = f"Заметка — текст от 1 до {limits['note_max']} символов."
        category = data.get("category")
        if action == "recategorize" and category not in CATEGORIES:
            fields["category"] = "Выберите категорию из списка."
        if fields:
            raise ApiError(422, "validation_failed", "Проверьте поля решения.", fields=fields)

        with self._transaction() as db:
            row = self._message_by_staff_id(message_id)
            now = _iso(self._now())
            if action == "note":
                # Служебная заметка: только для сотрудников, не меняет сообщение и его ревизию.
                self._event(row["id"], row["revision"], now, "note", "staff", actor, note, [], False)
                return _ok(200, {"item": self._staff_dto(row), "history": self._staff_history(row["id"])})
            if row["revision"] != expected:
                raise ApiError(409, "stale_revision",
                               "Сообщение изменено другим действием. Обновите карточку.",
                               extra={"current_revision": row["revision"]})
            revision = row["revision"] + 1
            if action == "recategorize":
                effective = row["staff_category"] or row["category"]
                if category == effective:
                    raise ApiError(422, "no_change", "Категория уже такая.", fields={"category": "Без изменений."})
                staff_category = None if category == row["category"] else category
                db.execute("UPDATE feedback_messages SET staff_category = ?, revision = ?, updated_at = ? "
                           "WHERE id = ? AND revision = ?", (staff_category, revision, now, row["id"], row["revision"]))
                self._event(row["id"], revision, now, "recategorized", "staff", actor,
                            f"{effective} -> {category}: {reason}", ["staff_category"], False)
                row = db.execute("SELECT * FROM feedback_messages WHERE id = ?", (row["id"],)).fetchone()
                return _ok(200, {"item": self._staff_dto(row), "history": self._staff_history(row["id"])})

            consent = bool(row["consent_public"]) and row["consent_withdrawn_at"] is None
            if not reply_given:
                reply = row["public_reply"]
            if action == "status":
                moderation, new_public_text = row["moderation"], row["public_text"]
            else:
                if public_text is not None and not consent:
                    raise ApiError(422, "no_consent",
                                   "Автор не разрешил публиковать текст — публичная версия текста недоступна.",
                                   fields={"public_text": "Нет согласия автора на публикацию."})
                moderation = "approved" if action == "approve" else "rejected"
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
            visible = moderation == "approved" and consent and new_public_text is not None
            if reply:
                if textutil.blocking_hints(reply):
                    raise ApiError(422, "personal_data_suspected",
                                   "Ответ похоже содержит персональные данные.",
                                   fields={"public_reply": "Уберите контакты/номера из ответа."})
                hidden_source = new_public_text if visible else ""
                quoted = textutil.mentions_any(reply, textutil.hidden_fragments(row["text"], hidden_source))
                if quoted:
                    raise ApiError(422, "reply_reveals_hidden_text",
                                   "Ответ цитирует фрагменты, которые не публикуются. Перефразируйте ответ.",
                                   fields={"public_reply": "Скрытые фрагменты: " + ", ".join(quoted[:5])})
            handling, dup = self._resolve_handling(db, row, action, status, duplicate_of, reply)

            was_visible = self._row_is_public(row)
            published_at = row["published_at"] or (now if visible else None)
            changed = ["moderation", "moderation_reason"] if action != "status" else []
            if reply != row["public_reply"]:
                changed.append("public_reply")
            if new_public_text != row["public_text"]:
                changed.append("public_text")
            if handling != row["handling_status"]:
                changed.append("handling_status")
            if dup != row["duplicate_of"]:
                changed.append("duplicate_of")
            if action == "status" and not changed:
                raise ApiError(422, "no_change", "Статус и ответ не изменились.",
                               fields={"status": "Без изменений."})
            handled = handling != row["handling_status"] or dup != row["duplicate_of"]
            db.execute(
                "UPDATE feedback_messages SET moderation = ?, moderation_reason = ?, public_reply = ?, "
                "public_text = ?, moderated_by = ?, moderated_at = ?, published_at = ?, revision = ?, "
                "updated_at = ?, handling_status = ?, duplicate_of = ?, handled_by = ?, handled_at = ? "
                "WHERE id = ? AND revision = ?",
                (moderation, reason if action != "status" else row["moderation_reason"], reply, new_public_text,
                 actor if action != "status" else row["moderated_by"],
                 now if action != "status" else row["moderated_at"], published_at, revision, now,
                 handling, dup, actor if handled else row["handled_by"], now if handled else row["handled_at"],
                 row["id"], row["revision"]))
            if visible and not was_visible:
                public_event, public_fields = "published", ["text"] + (["public_reply"] if reply else [])
            elif visible:
                public_event = "updated"
                public_fields = [{"public_text": "text"}.get(f, f) for f in changed
                                 if f in ("public_reply", "public_text")]
            else:
                public_event, public_fields = None, []
            event_action = moderation if action != "status" else "status_changed"
            self._event(row["id"], revision, now, event_action, "staff", actor, reason, changed, False)
            if public_event and public_fields:
                self._event(row["id"], revision, now, public_event, "staff", actor, None, public_fields, True)
            row = db.execute("SELECT * FROM feedback_messages WHERE id = ?", (row["id"],)).fetchone()
            return _ok(200, {"item": self._staff_dto(row), "history": self._staff_history(row["id"])})

    def _resolve_handling(self, db, row, action, requested, duplicate_of, reply):
        """Следующий статус обработки и ссылка на исходное сообщение для дубля.

        Без явного status действие approve/reject над новым сообщением переводит его в
        in_review (или answered, если дан ответ); иначе статус обработки не меняется.
        """
        current = row["handling_status"]
        if requested is None:
            if duplicate_of is not None:
                raise ApiError(422, "validation_failed", "duplicate_of задаётся вместе со status=duplicate.",
                               fields={"duplicate_of": "Только со статусом duplicate."})
            if current != "new":
                if current == "answered" and not reply:
                    raise ApiError(422, "reply_required",
                                   "У сообщения статус «Дан ответ платформы»: ответ нельзя удалить без смены статуса.",
                                   fields={"public_reply": "Сначала смените статус обработки."})
                return current, row["duplicate_of"]
            requested = "answered" if reply else "in_review"
        if requested != current and requested not in HANDLING_TRANSITIONS[current]:
            allowed = sorted(HANDLING_TRANSITIONS[current])
            raise ApiError(422, "invalid_transition",
                           f"Из статуса «{HANDLING_LABELS[current]}» нельзя перейти в «{HANDLING_LABELS[requested]}».",
                           fields={"status": "Допустимо: " + ", ".join(allowed) + "."}, extra={"allowed": allowed})
        if requested == "answered" and not reply:
            raise ApiError(422, "reply_required", "Для статуса «Дан ответ платформы» нужен текст ответа.",
                           fields={"public_reply": "Напишите ответ платформы."})
        if requested != "duplicate":
            if duplicate_of is not None:
                raise ApiError(422, "validation_failed", "duplicate_of задаётся вместе со status=duplicate.",
                               fields={"duplicate_of": "Только со статусом duplicate."})
            return requested, None
        if duplicate_of is None:
            if current == "duplicate" and row["duplicate_of"] is not None:
                return requested, row["duplicate_of"]
            raise ApiError(422, "validation_failed", "Укажите номер исходного сообщения.",
                           fields={"duplicate_of": "Номер исходного сообщения обязателен."})
        target = db.execute("SELECT id, handling_status, duplicate_of FROM feedback_messages WHERE id = ?",
                            (int(duplicate_of),)).fetchone()
        if target is None or target["id"] == row["id"]:
            raise ApiError(422, "validation_failed", "Исходное сообщение не найдено.",
                           fields={"duplicate_of": "Нет такого другого сообщения."})
        if target["handling_status"] == "duplicate":
            raise ApiError(422, "duplicate_chain",
                           f"Сообщение #{target['id']} само отмечено как дубль #{target['duplicate_of']}. Укажите исходное.",
                           fields={"duplicate_of": f"Укажите #{target['duplicate_of']}."})
        children = db.execute("SELECT COUNT(*) FROM feedback_messages WHERE duplicate_of = ? AND handling_status = 'duplicate'",
                              (row["id"],)).fetchone()[0]
        if children:
            raise ApiError(422, "has_duplicates",
                           "На это сообщение уже ссылаются дубли. Оставьте его исходным или сначала откройте дубли.",
                           fields={"duplicate_of": f"Связанных дублей: {children}."})
        return requested, target["id"]

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
    def stats(self) -> dict:
        """Только агрегаты: по статусам, с согласием/без, отозванные согласия, подсказки модели."""
        with self._lock:
            db = self._db
            by_status = {name: 0 for name in MODERATION}
            for name, count in db.execute("SELECT moderation, COUNT(*) FROM feedback_messages GROUP BY moderation"):
                by_status[name] = count
            public = db.execute(f"SELECT COUNT(*) FROM feedback_messages WHERE {PUBLIC_WHERE}").fetchone()[0]
            withdrawn = db.execute(
                "SELECT COUNT(*) FROM feedback_messages WHERE consent_withdrawn_at IS NOT NULL").fetchone()[0]
            classifier = dict(db.execute(
                "SELECT classifier_status, COUNT(*) FROM feedback_messages GROUP BY classifier_status").fetchall())
            handling = {name: 0 for name in HANDLING}
            for name, count in db.execute("SELECT handling_status, COUNT(*) FROM feedback_messages GROUP BY handling_status"):
                handling[name] = count
        return {"schema_version": SCHEMA_VERSION, "moderation": by_status, "handling": handling, "public": public,
                "consent_withdrawn": withdrawn, "classifier_status": classifier}

    def purge_antispam(self, older_than_days: int = 30) -> int:
        """Обезличить служебные антиспам-поля старых сообщений; текст и решения остаются."""
        cutoff = self._now().timestamp() - older_than_days * 86400
        with self._lock:
            cursor = self._db.execute(
                "UPDATE feedback_messages SET client_hash = 'purged', client_request_id = NULL "
                "WHERE created_ts < ? AND client_hash != 'purged'", (cutoff,))
            return cursor.rowcount
