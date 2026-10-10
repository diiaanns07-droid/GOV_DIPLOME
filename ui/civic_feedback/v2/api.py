"""HTTP-слой жалоб v2: /api/civic/v2/... (CONTRACT §7, владелец R09).

Тот же конверт, что у v1 и шлюза R01: {"status", "headers", "body": {"ok", "data"|"error"}}.
handle(...) возвращает None для чужих путей — шлюз может опрашивать сервисы по очереди.

Маршруты (подключает R01 в ui/web_server.py, см. research/round-14-results/R09/INTEGRATION.txt):
  GET  /categories                       категории v2, сроки ответа, уровни тепловой карты
  POST /complaints                       новая жалоба (заголовок X-Birge-Device)
  GET  /complaints?bbox&since&category&status&days   список для карты (без текстов)
  GET  /complaints/mine                  «Мои обращения» этого устройства (свои тексты)
  GET  /complaints/events?after=N        события created/metoo/status/duplicate (для R07)
  GET  /complaints/summary?target_id&category&days   сколько человек сообщили о цели
  GET  /complaints/place?lon&lat         запасное «примерное место» (ячейка ~150 м)
  GET  /complaints/{id}                  одна жалоба (житель — без текста; автор и акимат — с текстом)
  POST /complaints/{id}/metoo            «Я тоже» (одно на устройство)
  POST /complaints/{id}/status           смена статуса (только сотрудник)
  POST /complaints/{id}/duplicate        отметить дублем {of} (только сотрудник)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import timedelta
from urllib.parse import parse_qs, unquote, urlsplit

from . import categories
from . import record as rec
from .record import RecordError
from .store import ComplaintStore, Conflict, LimitError, NotFound

LOGGER = logging.getLogger(__name__)
API_PREFIX = "/api/civic/v2"
DEVICE_HEADER = "X-Birge-Device"
MAX_BODY = 32 * 1024


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields, self.headers = status, code, message, fields, headers


def _ok(status, data):
    return {"status": status, "headers": {"Cache-Control": "no-store"}, "body": {"ok": True, "data": data}}


def _error(exc: ApiError):
    error = {"code": exc.code, "message": exc.message}
    if exc.fields:
        error["fields"] = exc.fields
    headers = {"Cache-Control": "no-store", **(exc.headers or {})}
    return {"status": exc.status, "headers": headers, "body": {"ok": False, "error": error}}


def _header(context, name):
    headers = (context or {}).get("headers") or {}
    lowered = name.lower()
    try:
        for key, value in headers.items():
            if str(key).lower() == lowered:
                return value
    except AttributeError:
        return None
    return None


def _is_staff(principal) -> bool:
    if principal is None:
        return False
    if isinstance(principal, dict):
        return bool(principal.get("is_staff"))
    return bool(getattr(principal, "is_staff", False))


def _actor(principal) -> str | None:
    if isinstance(principal, dict):
        return principal.get("username") or principal.get("name")
    return getattr(principal, "username", None)


class ComplaintsV2Service:
    def __init__(self, store: ComplaintStore):
        self.store = store

    # ------------------------------------------------------------ вход
    def handle(self, method, path, query, body, principal, context):
        method = (method or "").upper()
        if not isinstance(path, str):
            return None
        raw = urlsplit(path).path
        if not raw.startswith(API_PREFIX + "/"):
            return None
        parts = [unquote(p) for p in raw[len(API_PREFIX):].split("/") if p]
        if not parts or parts[0] not in ("categories", "complaints"):
            return None
        context = context if isinstance(context, dict) else {}
        try:
            if context.get("host_allowed") is False:
                raise ApiError(403, "host_not_allowed", "Откройте Birge через адрес этого сервера.")
            if method == "POST" and context.get("is_same_origin") is False:
                raise ApiError(403, "cross_origin", "Запрос с чужого сайта отклонён.")
            params = self._query(query, path)
            handler, args = self._route(method, parts)
            return handler(*args, params=params, body=body, principal=principal, context=context)
        except ApiError as exc:
            return _error(exc)
        except LimitError as exc:
            minutes = max(1, (exc.retry_after_s + 59) // 60)
            return _error(ApiError(429, "too_many", f"Слишком много обращений подряд. Повторите через {minutes} мин.",
                                   headers={"Retry-After": str(exc.retry_after_s)}))
        except NotFound as exc:
            return _error(ApiError(404, "not_found", str(exc)))
        except Conflict as exc:
            return _error(ApiError(409, "conflict", str(exc), exc.fields))
        except RecordError as exc:
            return _error(ApiError(422, "invalid", str(exc), exc.fields))
        except sqlite3.Error:
            LOGGER.exception("complaints v2 storage error")
            return _error(ApiError(503, "storage_unavailable", "Хранилище временно недоступно. Повторите позже."))
        except Exception:  # наружу только конверт, без traceback
            LOGGER.exception("complaints v2 handler failed")
            return _error(ApiError(500, "internal_error", "Не удалось выполнить запрос. Повторите."))

    def _route(self, method, parts):
        def need(allowed, handler, *args):
            if method not in allowed and not (method == "HEAD" and "GET" in allowed):
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается.",
                               headers={"Allow": ", ".join(allowed)})
            return handler, args

        if parts == ["categories"]:
            return need(("GET",), self._categories)
        if parts == ["complaints"]:
            return need(("GET", "POST"), self._list if method in ("GET", "HEAD") else self._create)
        if len(parts) == 2:
            special = {"mine": self._mine, "events": self._events, "summary": self._summary, "place": self._place}
            if parts[1] in special:
                return need(("GET",), special[parts[1]])
            return need(("GET",), self._detail, parts[1])
        if len(parts) == 3:
            action = {"metoo": self._metoo, "status": self._status, "duplicate": self._duplicate}.get(parts[2])
            if action:
                return need(("POST",), action, parts[1])
        raise ApiError(404, "not_found", "Адрес не найден.")

    # ------------------------------------------------------------ разбор
    @staticmethod
    def _query(query, path) -> dict:
        if query is None:
            query = urlsplit(path).query
        if isinstance(query, bytes):
            query = query.decode()
        if isinstance(query, str):
            query = parse_qs(query)
        result = {}
        for key, value in (query or {}).items():
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            result[str(key)] = "" if value is None else str(value)
        return result

    @staticmethod
    def _json(body) -> dict:
        if isinstance(body, dict):
            return body
        if isinstance(body, (bytes, str)) and body:
            if len(body) > MAX_BODY:
                raise ApiError(413, "too_large", "Слишком большой запрос.")
            try:
                data = json.loads(body)
            except ValueError:
                raise ApiError(400, "invalid_body", "Ожидается JSON-объект.") from None
            if isinstance(data, dict):
                return data
        if body in (None, b"", ""):
            return {}
        raise ApiError(400, "invalid_body", "Ожидается JSON-объект.")

    @staticmethod
    def _device(context, body=None):
        return _header(context, DEVICE_HEADER) or (body or {}).get("device_id")

    @staticmethod
    def _require_staff(principal, context):
        if not _is_staff(principal):
            raise ApiError(403, "forbidden", "Действие доступно только сотрудникам акимата.")
        check = getattr(principal, "check_csrf", None)
        if callable(check) and not check(_header(context, "X-CSRF-Token")):
            raise ApiError(403, "csrf_failed", "Сессия устарела. Обновите страницу.")

    @staticmethod
    def _bbox(value):
        if not value:
            return None
        try:
            parts = [float(v) for v in value.split(",")]
        except ValueError:
            raise ApiError(422, "invalid", "Неверная область.", {"bbox": "lon_min,lat_min,lon_max,lat_max"}) from None
        if len(parts) != 4 or parts[0] > parts[2] or parts[1] > parts[3]:
            raise ApiError(422, "invalid", "Неверная область.", {"bbox": "lon_min,lat_min,lon_max,lat_max"})
        return parts

    def _view(self, record, principal, context):
        if _is_staff(principal):
            return rec.staff_view(record)
        device = self._device(context)
        if device and self.store.is_author(record["id"], device):
            return rec.author_view(record)
        return rec.public_view(record)

    # ------------------------------------------------------------ обработчики
    def _categories(self, *, params, body, principal, context):
        return _ok(200, categories.public_payload())

    def _create(self, *, params, body, principal, context):
        data = self._json(body)
        record, created = self.store.create(data, self._device(context, data))
        return _ok(201 if created else 200, {"complaint": rec.author_view(record), "replayed": not created})

    def _list(self, *, params, body, principal, context):
        since = params.get("since") or None
        if params.get("days"):
            try:
                days = max(1, min(int(params["days"]), 365))
            except ValueError:
                raise ApiError(422, "invalid", "Неверный период.", {"days": "число дней"}) from None
            since = self.store._now() - timedelta(days=days)
        category = [c for c in params.get("category", "").split(",") if c] or None
        if category and not all(categories.is_category(c) for c in category):
            raise ApiError(422, "invalid", "Неизвестная категория.", {"category": ",".join(categories.ids())})
        status = [s for s in params.get("status", "").split(",") if s] or None
        if status and not all(s in rec.STATUSES for s in status):
            raise ApiError(422, "invalid", "Неизвестный статус.", {"status": ",".join(rec.STATUSES)})
        items = self.store.list(self._bbox(params.get("bbox")), since, category, status=status,
                                include_duplicates=params.get("duplicates") == "1")
        view = rec.staff_view if _is_staff(principal) else rec.public_view
        return _ok(200, {"items": [view(r) for r in items], "count": len(items),
                         "generated_at": rec.iso(self.store._now())})

    def _mine(self, *, params, body, principal, context):
        items = []
        for record in self.store.mine(self._device(context)):
            relation = record.pop("relation")
            view = rec.author_view(record) if relation == "author" else rec.public_view(record)
            view["relation"] = relation
            if relation == "metoo":
                view["steps"] = rec.resident_steps(record)
                view["metoo_at"] = record.get("metoo_at")
            items.append(view)
        return _ok(200, {"items": items, "count": len(items)})

    def _events(self, *, params, body, principal, context):
        try:
            after = int(params.get("after") or 0)
        except ValueError:
            raise ApiError(422, "invalid", "Неверный номер события.", {"after": "целое число"}) from None
        events = self.store.events_since(after)
        return _ok(200, {"events": events, "last": events[-1]["seq"] if events else after})

    def _summary(self, *, params, body, principal, context):
        target_id = params.get("target_id") or ""
        if not target_id or len(target_id) > 100:
            raise ApiError(422, "invalid", "Не указана цель.", {"target_id": "id объекта, участка или двора"})
        category = params.get("category") or None
        if category and not categories.is_category(category):
            raise ApiError(422, "invalid", "Неизвестная категория.", {"category": ",".join(categories.ids())})
        days = int(params["days"]) if params.get("days", "").isdigit() else 14
        return _ok(200, self.store.target_summary(target_id, days=max(1, min(days, 90)), category=category))

    def _place(self, *, params, body, principal, context):
        try:
            point = rec.parse_point([float(params.get("lon", "")), float(params.get("lat", ""))])
        except ValueError:
            raise ApiError(422, "invalid", "Неверное место.", {"lon": "число", "lat": "число"}) from None
        target = rec.cell_target(*point)
        return _ok(200, {"target": target, "geometry": {"type": "Polygon",
                                                        "coordinates": [rec.cell_polygon(target["id"])]}})

    def _detail(self, complaint_id, *, params, body, principal, context):
        record = self.store.get(complaint_id) or self.store.get_by_code(complaint_id)
        if record is None:
            raise ApiError(404, "not_found", "Обращение не найдено.")
        return _ok(200, {"complaint": self._view(record, principal, context)})

    def _metoo(self, complaint_id, *, params, body, principal, context):
        data = self._json(body)
        record, result = self.store.metoo(complaint_id, self._device(context, data))
        return _ok(200, {"result": result, "complaint": rec.public_view(record)})

    def _status(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        data = self._json(body)
        record = self.store.set_status(complaint_id, data.get("status"), actor=_actor(principal),
                                       note=data.get("note"), expected=data.get("expected"))
        return _ok(200, {"complaint": rec.staff_view(record)})

    def _duplicate(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        data = self._json(body)
        if not isinstance(data.get("of"), str):
            raise ApiError(422, "invalid", "Укажите исходное обращение.", {"of": "id обращения"})
        record = self.store.mark_duplicate(complaint_id, data["of"], actor=_actor(principal))
        return _ok(200, {"complaint": rec.staff_view(record)})
