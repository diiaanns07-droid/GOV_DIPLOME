"""HTTP API v2 модуля R06 (раунд 14): объекты с этапами, предложения и голоса. CONTRACT §7.

    v2 = CivicV2(service)              # service — тот же CivicService (одна база, сессии, CSRF)
    v2.handle(method, path, query, body, context) -> None | {status, headers, body}
      None — путь не /api/civic/v2/{objects,proposals,...}: решает диспетчер R01.

Маршруты (все ответы — конверт {ok, data} / {ok:false, error}, как в v1):
  GET  /objects?bbox&district            объекты + stage, planned_end, forecast_end, delay_days, stale
  GET  /objects/lagging?district         для «Картины дня» R08: отстающие и устаревшие
  GET  /objects/{id}                     объект + публичная история этапов
  PUT  /objects/{id}/stage               сотрудник: {stage, planned_end, forecast_end, reason, expected_revision}
  POST /objects/{id}/stage               то же (шлюз R01 сейчас не принимает PUT)
  GET  /staff/objects/{id}/stage         сотрудник: этап черновика, stage_revision, служебная история
  GET  /proposals?status&bbox&district&device_id
  POST /proposals                        сотрудник: {kind, geometry, title_ru?, title_kk?, rotation_deg?, planned_year?, demo?}
  GET  /proposals/summary?since          для R08
  GET  /proposals/{id}?device_id
  POST /proposals/{id}/vote              житель: {value: 1|-1, device_id}
  POST /proposals/{id}/approve|reject|withdraw   сотрудник: {reason?}
  GET  /meta                             перечисления (этапы, виды, районы, порог устаревания)

Права: чтение и голос — публичные (только адрес этого сервера; голос — без чужого Origin);
запись этапа и решения по предложениям — сессия редактора + X-CSRF-Token (require_staff R02).
"""

from __future__ import annotations

import logging
import sqlite3
from urllib.parse import unquote

from .db import StorageError
from .districts import DISTRICT_NAMES
from .objects import BadRequest, Conflict, NotFound
from .proposals import DECISIONS, KINDS, ProposalRepository, VISIBLE_STATUSES, _VoteRateLimited
from .service import MAX_BODY, _TooLarge, error, ok, parse_body, parse_query
from .stages import STAGES, STALE_DAYS, StageRepository, parse_district, _single
from .validate import ValidationError, is_valid_id


LOGGER = logging.getLogger("ui.civic_store.v2")
PREFIX_V2 = "/api/civic/v2"
OWN_ROOTS = ("objects", "proposals", "staff", "meta")


def meta_v2() -> dict:
    return {
        "stages": list(STAGES), "proposal_kinds": list(KINDS), "proposal_statuses": list(VISIBLE_STATUSES),
        "proposal_actions": list(DECISIONS), "stale_after_days": STALE_DAYS,
        "districts": [{"id": key, **names} for key, names in DISTRICT_NAMES.items()],
        "vote": {"values": [1, -1], "device_id": "16–128 символов [A-Za-z0-9_-], случайный, хранится в браузере",
                 "rule": "один голос с устройства; повтор того же значения ничего не меняет, другое — меняет голос"},
        "errors": {"bad_request": 400, "unauthenticated": 401, "cross_origin": 403, "csrf_failed": 403,
                   "forbidden_host": 403, "not_found": 404, "method_not_allowed": 405, "stale_revision": 409,
                   "voting_closed": 409, "already_decided": 409, "payload_too_large": 413,
                   "validation_failed": 422, "rate_limited": 429, "internal_error": 500, "busy": 503},
    }


class CivicV2:
    def __init__(self, service):
        self.service = service
        self.stages = StageRepository(service.db, service.clock)
        self.proposals = ProposalRepository(service.db, service.clock)

    # --- функции для соседей без HTTP (R08 «Картина дня», R05, R01) ---------------------

    def lagging_objects(self, district=None) -> dict:
        return self.stages.lagging(district)

    def proposals_summary(self, since=None) -> dict:
        return self.proposals.summary(since)

    def list_objects(self, query=None) -> dict:
        return self.stages.list_public(parse_query(query))

    def list_proposals(self, query=None, device_id=None) -> dict:
        return self.proposals.list(parse_query(query), device_id)

    # --- HTTP ------------------------------------------------------------------------------

    def handle(self, method, path, query, body, context):
        if not isinstance(path, str) or not path.startswith(PREFIX_V2 + "/"):
            return None
        segments = [unquote(part) for part in path[len(PREFIX_V2):].split("/")[1:]]
        if not segments or segments[0] not in OWN_ROOTS:
            return None  # /classify, /heat, /complaints... — модули других ролей
        route = self._route(segments)
        if route is None:
            return None
        method = (method or "").upper()
        effective = "GET" if method == "HEAD" else method
        if effective not in route:
            allowed = set(route) | ({"HEAD"} if "GET" in route else set())
            return error(405, "method_not_allowed", "Метод не поддерживается.",
                         headers={"Allow": ", ".join(sorted(allowed))})
        handler, args = route[effective]
        context = context or {}
        try:
            params = parse_query(query)
            payload = parse_body(body) if effective in ("POST", "PUT") else {}
            return handler(context, params, payload, *args)
        except _TooLarge:
            return error(413, "payload_too_large", f"Запрос больше {MAX_BODY // 1024} КиБ.")
        except ValidationError as exc:
            return error(422, "validation_failed", exc.message, exc.fields)
        except BadRequest as exc:
            return error(400, "bad_request", str(exc), exc.fields or None)
        except NotFound:
            return error(404, "not_found", "Не найдено.")
        except Conflict as exc:
            extra = {"current_revision": exc.current_revision} if exc.current_revision is not None else {}
            return error(409, exc.code, str(exc), **extra)
        except _VoteRateLimited as exc:
            return error(429, "rate_limited", "Слишком много голосов подряд. Повторите через минуту.",
                         headers={"Retry-After": str(exc.retry_after)}, retry_after=exc.retry_after)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) or "busy" in str(exc):
                return error(503, "busy", "База занята, повторите запрос.", headers={"Retry-After": "1"})
            LOGGER.exception("civic v2 db error on %s %s", effective, segments[:2])
            return error(500, "internal_error", "Внутренняя ошибка сервера.")
        except StorageError:
            LOGGER.exception("civic v2 storage error")
            return error(500, "internal_error", "Хранилище недоступно.")
        except Exception:  # noqa: BLE001 — клиенту только конверт без traceback
            LOGGER.exception("civic v2 handler failed on %s %s", effective, segments[:2])
            return error(500, "internal_error", "Внутренняя ошибка сервера.")

    def _route(self, s):
        n = len(s)
        if s == ["meta"]:
            return {"GET": (self._meta, ())}
        if s == ["objects"]:
            return {"GET": (self._objects, ())}
        if s == ["objects", "lagging"]:
            return {"GET": (self._lagging, ())}
        if n == 2 and s[0] == "objects":
            return {"GET": (self._object, (s[1],))}
        if n == 3 and s[0] == "objects" and s[2] == "stage":
            return {"PUT": (self._set_stage, (s[1],)), "POST": (self._set_stage, (s[1],))}
        if n == 4 and s[:2] == ["staff", "objects"] and s[3] == "stage":
            return {"GET": (self._staff_stage, (s[2],))}
        if s == ["proposals"]:
            return {"GET": (self._proposals, ()), "POST": (self._create_proposal, ())}
        if s == ["proposals", "summary"]:
            return {"GET": (self._proposals_summary, ())}
        if n == 2 and s[0] == "proposals":
            return {"GET": (self._proposal, (s[1],))}
        if n == 3 and s[0] == "proposals" and s[2] == "vote":
            return {"POST": (self._vote, (s[1],))}
        if n == 3 and s[0] == "proposals" and s[2] in DECISIONS:
            return {"POST": (self._decide, (s[1], s[2]))}
        return None

    # --- обработчики -----------------------------------------------------------------------

    @staticmethod
    def _public_ok(context):
        if context.get("host_allowed") is not True:
            return error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        return None

    def _meta(self, context, params, payload):
        return self._public_ok(context) or ok(meta_v2())

    def _objects(self, context, params, payload):
        return self._public_ok(context) or ok(self.stages.list_public(params))

    def _lagging(self, context, params, payload):
        return self._public_ok(context) or ok(self.stages.lagging(parse_district(params)))

    def _object(self, context, params, payload, object_id):
        return self._public_ok(context) or ok(self.stages.get_public(object_id))

    def _set_stage(self, context, params, payload, object_id):
        principal, denied = self.service.require_staff(context, unsafe=True)
        if denied:
            return denied
        return ok(self.stages.set_stage(principal.actor(), object_id, payload))

    def _staff_stage(self, context, params, payload, object_id):
        principal, denied = self.service.require_staff(context, unsafe=False)
        if denied:
            return denied
        return ok(self.stages.get_staff(object_id))

    def _proposals(self, context, params, payload):
        denied = self._public_ok(context)
        if denied:
            return denied
        return ok(self.proposals.list(params, _single(params, "device_id")))

    def _proposals_summary(self, context, params, payload):
        denied = self._public_ok(context)
        if denied:
            return denied
        since = _single(params, "since")
        if since is not None and (len(since) > 40 or not since[:4].isdigit()):
            raise BadRequest("Недопустимый since.", {"since": "ISO 8601, например 2026-10-11"})
        return ok(self.proposals.summary(since))

    def _proposal(self, context, params, payload, proposal_id):
        denied = self._public_ok(context)
        if denied:
            return denied
        return ok(self.proposals.get(proposal_id, _single(params, "device_id")))

    def _create_proposal(self, context, params, payload):
        principal, denied = self.service.require_staff(context, unsafe=True)
        if denied:
            return denied
        return ok(self.proposals.create(principal.actor(), payload), status=201)

    def _vote(self, context, params, payload, proposal_id):
        denied = self._public_ok(context)
        if denied:
            return denied
        if context.get("is_same_origin") is False:
            return error(403, "cross_origin", "Голос с чужого сайта отклонён.")
        if not is_valid_id(proposal_id):
            raise BadRequest("Недопустимый ID предложения.", {"id": "Пустой или недопустимый ID."})
        client = str(context.get("client_ip") or "unknown")
        return ok(self.proposals.vote(proposal_id, payload, client_key=client))

    def _decide(self, context, params, payload, proposal_id, action):
        principal, denied = self.service.require_staff(context, unsafe=True)
        if denied:
            return denied
        return ok(self.proposals.decide(principal.actor(), proposal_id, action, payload))


# ===========================================================================================
# Функции уровня модуля для шлюза R01 (ui/web_server.py, CivicV2Gateway, ветка claude/sharp-dijkstra-0t87gl).
# Шлюз ищет их по именам из V2_HANDLERS и отдаёт результат как есть (без обёртки ok/data);
# ошибка — исключение с атрибутами status и code (V2Error). Перед первым вызовом R01 один раз
# вызывает bind(store_service) — тот же CivicService, что обслуживает v1 (одна база, одни сессии).
# ===========================================================================================

class V2Error(Exception):
    """Ошибка для шлюза R01: status (HTTP), code (строка), message (по-русски), fields (по полям)."""

    def __init__(self, status: int, code: str, message: str, fields=None, current_revision=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.fields = fields or {}
        self.current_revision = current_revision


_BOUND: CivicV2 | None = None


def bind(service) -> CivicV2:
    """Связать модуль с CivicService шлюза. Повторный вызов с тем же сервисом ничего не меняет."""
    global _BOUND
    if _BOUND is None or _BOUND.service is not service:
        _BOUND = CivicV2(service)
    return _BOUND


def _v2() -> CivicV2:
    if _BOUND is None:
        raise V2Error(503, "module_not_ready", "R06 не связан с хранилищем: шлюз должен вызвать bind(service).")
    return _BOUND


def _run(fn, *args, **kwargs):
    """Перевод исключений хранилища в V2Error (те же коды, что у CivicV2.handle)."""
    try:
        return fn(*args, **kwargs)
    except ValidationError as exc:
        raise V2Error(422, "validation_failed", exc.message, exc.fields)
    except BadRequest as exc:
        raise V2Error(400, "bad_request", str(exc), exc.fields)
    except NotFound:
        raise V2Error(404, "not_found", "Не найдено.")
    except Conflict as exc:
        raise V2Error(409, exc.code, str(exc), current_revision=exc.current_revision)
    except _VoteRateLimited:
        raise V2Error(429, "rate_limited", "Слишком много голосов подряд. Повторите через минуту.")


def _query(bbox=None, district=None, status=None):
    query = {}
    if bbox is not None:
        query["bbox"] = [",".join(str(float(v)) for v in bbox)]
    if district:
        query["district"] = [district]
    if status:
        query["status"] = [status]
    return query


def _actor(context):
    """Сотрудник из серверной сессии (cookie). principal-словарь шлюза не содержит user_id для истории."""
    principal = _v2().service.resolve_principal(context or {})
    if principal is None or not principal.is_staff:
        raise V2Error(401, "unauthenticated", "Войдите как сотрудник акимата.")
    return principal.actor()


def list_proposals(bbox=None, district=None, status=None, device_id=None, context=None):
    return _run(_v2().proposals.list, _query(bbox, district, status), device_id)


def get_proposal(proposal_id, device_id=None, context=None):
    return _run(_v2().proposals.get, proposal_id, device_id)


def create_proposal(body, context=None, principal=None):
    return 201, _run(_v2().proposals.create, _actor(context), body or {})


def vote_proposal(proposal_id, value, device_id, context=None):
    client = str((context or {}).get("client_ip") or "unknown")
    return _run(_v2().proposals.vote, proposal_id, {"value": value, "device_id": device_id}, client_key=client)


def decide_proposal(proposal_id, action, body=None, context=None, principal=None):
    return _run(_v2().proposals.decide, _actor(context), proposal_id, action, body or {})


def proposals_summary(since=None):
    return _run(_v2().proposals.summary, since)


def list_objects(bbox=None, district=None, context=None):
    return _run(_v2().stages.list_public, _query(bbox, district))


def get_object(object_id, context=None):
    return _run(_v2().stages.get_public, object_id)


def set_object_stage(object_id, body, context=None, principal=None):
    return _run(_v2().stages.set_stage, _actor(context), object_id, body or {})


def get_object_stage(object_id, context=None, principal=None):
    _actor(context)
    return _run(_v2().stages.get_staff, object_id)


def lagging_objects(district=None):
    """Для R08 «Картина дня»: {today, late:[…], stale:[…], counts, by_district}."""
    return _run(_v2().stages.lagging, district)
