"""HTTP-обёртка «Картины дня» для ui/web_server.py (подключает R01, см. research/round-14-results/R08/INTEGRATION.txt).

    from ui.civic_akim.api import handle_get
    status, body = handle_get(path, query)     # query — dict из parse_qs или простой dict

Маршруты (CONTRACT §7):
    GET /api/civic/v2/akim/summary?date=2026-10-12&district=nura
        date — день в календаре Астаны (по умолчанию сегодня), district — id района или all.
    GET /api/civic/v2/akim/routing                 таблица «категория / уточнение → служба» (routing.py)
    GET /api/civic/v2/akim/routing?category=roads&subtopic=marking   → одна служба (для карточки R09)
    PUT /api/civic/v2/akim/routing  {"rules": {...}, "services": {...}}   правка акимата:
        handle_put(path, body, staff=True, actor=…) — только для сотрудника; кто сотрудник и CSRF — решает шлюз R01.
    POST /api/civic/v2/akim/decisions/<id>  {"option": 1|2}   «Выбрать» вариант в «Нужно решение акима»:
        handle_post(path, body, staff=True, actor=…) — тоже только сотрудник.
Раунд 15 — только сотрудник (шлюз R01: V2Handler kind="raw", staff_view=True → сюда приходит staff=True;
без сессии сотрудника — 401 staff_only):
    GET /api/civic/v2/akim/board?district=nura      «Ситуационный центр» (situation.py): KPI, пульс, места, службы R17,
                                                    кризис R17, жители вместе R16, поручения и прогноз R13
    GET /api/civic/v2/akim/week?date=2026-10-15&district=nura   «Картина недели» (weekly.py): 7 дней до date
Раздел жителя «Рядом» (nearby.py, публично, без личных данных):
    GET  /api/civic/v2/nearby?district=nura&tab=now|done|planned|outages
    GET  /api/civic/v2/nearby/subscriptions?device_id=…        мои подписки
    POST /api/civic/v2/nearby/subscriptions {device_id, scope: district|item, id, on: true|false}
    GET  /api/civic/v2/nearby/updates?device_id=…&since=…      для R09 «Мои обращения → Что изменилось»
Ошибка в параметрах → 400 {"error":"bad_request","field":…,"message":…}. Сбой расчёта → 500, сервер не падает.
В ответе нет текстов жалоб и данных жителей — только числа и подписи мест.
"""
from __future__ import annotations

import logging
import traceback

from . import decisions, nearby, routing
from .summary import AkimError, default_service

PREFIX = "/api/civic/v2"
log = logging.getLogger("civic_akim")


def _one(query: dict, name: str):
    v = (query or {}).get(name)
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


# Маршруты только для сотрудника: табло служб и кризисный штаб R17 — внутренние данные акимата (CONTRACT §7).
STAFF_ONLY = (PREFIX + "/akim/board", PREFIX + "/akim/week")


def handle_get(path: str, query: dict | None = None, service=None, staff: bool | None = None) -> tuple[int, dict]:
    """staff — шлюз R01 проверил сессию сотрудника (staff_view): передаёт staff=True только тогда."""
    svc = service or default_service()
    try:
        if path in STAFF_ONLY and staff is not True:
            return 401, {"error": "staff_only",
                         "message": "Ситуационный центр и «Картина недели» открываются после входа сотрудника акимата"}
        if path == PREFIX + "/akim/board":
            return 200, svc.board(district=_one(query, "district"))
        if path == PREFIX + "/akim/week":
            return 200, svc.week(date=_one(query, "date"), district=_one(query, "district"))
        if path == PREFIX + "/akim/summary":
            return 200, svc.summary(date=_one(query, "date"), district=_one(query, "district"))
        if path == PREFIX + "/akim/routing":
            category = _one(query, "category")
            if category:
                return 200, routing.service_for(str(category), _one(query, "subtopic") or None)
            return 200, routing.table()
        if path == PREFIX + "/nearby":
            return 200, nearby.feed(_one(query, "district"), _one(query, "tab") or None)
        if path == PREFIX + "/nearby/subscriptions":
            return 200, {"items": nearby.subscriptions(_one(query, "device_id"))}
        if path == PREFIX + "/nearby/updates":
            return 200, {"items": nearby.updates_for(_one(query, "device_id"), _one(query, "since"))}
        return 404, {"error": "not_found", "message": "нет такого адреса"}
    except nearby.NearbyError as exc:
        return exc.status, {"error": "bad_request", "field": exc.field, "message": str(exc)}
    except (AkimError, routing.RoutingError) as exc:
        return 400, {"error": "bad_request", "field": exc.field, "message": str(exc)}
    except Exception:  # картина дня не должна ронять сервер
        log.error("akim summary failed: %s", traceback.format_exc())
        return 500, {"error": "akim_failed", "message": "картина дня временно не считается"}


def handle_put(path: str, body, *, staff: bool = False, actor: str | None = None) -> tuple[int, dict]:
    """PUT /api/civic/v2/akim/routing — правка таблицы служб. staff=False → 403 (житель не меняет маршруты)."""
    if path != PREFIX + "/akim/routing":
        return 404, {"error": "not_found", "message": "нет такого адреса"}
    if not staff:
        return 403, {"error": "forbidden", "message": "менять таблицу служб может только сотрудник акимата"}
    try:
        return 200, routing.update(body, actor=actor)
    except routing.RoutingError as exc:
        return 400, {"error": "bad_request", "field": exc.field, "message": str(exc)}
    except Exception:
        log.error("akim routing update failed: %s", traceback.format_exc())
        return 500, {"error": "akim_failed", "message": "таблица служб не сохранилась"}


def handle_post(path: str, body, *, staff: bool = False, actor: str | None = None, service=None) -> tuple[int, dict]:
    """POST /api/civic/v2/akim/decisions/<id> {"option": 1|2} (staff=False → 403);
    POST /api/civic/v2/nearby/subscriptions {device_id, scope, id, on} — житель, без входа."""
    if path == PREFIX + "/nearby/subscriptions":
        b = body if isinstance(body, dict) else {}
        try:
            items = nearby.subscribe(b.get("device_id"), b.get("scope"), b.get("id"), on=b.get("on", True) is not False)
            return 200, {"items": items}
        except nearby.NearbyError as exc:
            return exc.status, {"error": "bad_request", "field": exc.field, "message": str(exc)}
        except Exception:
            log.error("nearby subscribe failed: %s", traceback.format_exc())
            return 500, {"error": "nearby_failed", "message": "подписка не сохранилась"}
    prefix = PREFIX + "/akim/decisions/"
    if not path.startswith(prefix):
        return 404, {"error": "not_found", "message": "нет такого адреса"}
    if not staff:
        return 403, {"error": "forbidden", "message": "выбрать вариант может только сотрудник акимата"}
    svc = service or default_service()
    try:
        option = (body or {}).get("option") if isinstance(body, dict) else None
        return 200, svc.choose_decision(path[len(prefix):], option, actor=actor)
    except decisions.DecisionError as exc:
        return exc.status, {"error": "bad_request" if exc.status == 400 else "not_found", "field": exc.field,
                            "message": str(exc)}
    except AkimError as exc:
        return 400, {"error": "bad_request", "field": exc.field, "message": str(exc)}
    except Exception:
        log.error("akim decision choice failed: %s", traceback.format_exc())
        return 500, {"error": "akim_failed", "message": "выбор не сохранился"}


# ---------------------------------------------------------------- для шлюза R01 (V2Handler kind="function")
# Чтение — raw: handle_get (akim/summary, akim/routing, nearby, nearby/subscriptions, nearby/updates);
# akim/board и akim/week — raw со staff_view=True (только сотрудник, см. STAFF_ONLY).
# Запись — функции ниже: шлюз R01 сам проверяет сотрудника и CSRF (staff=True в V2Handler) и передаёт principal;
# ошибки ввода — ValueError с полями status/code/field (шлюз отвечает 400/404/429), см. INTEGRATION.txt §8.

def _require_staff(principal):
    """R15-S29: защита в глубину — запись только с сотрудником от шлюза (principal есть лишь у staff=True в
    V2_HANDLERS R01). Забытая пометка в таблице маршрутов даст 403, а не правку от анонима."""
    if not principal:
        raise PermissionError("только сотрудник акимата")


def routing_update(body, principal=None):
    """PUT /akim/routing — staff. body: {"rules": {...}, "services": {...}}."""
    _require_staff(principal)
    actor = (principal or {}).get("username") if isinstance(principal, dict) else None
    try:
        return routing.update(body if isinstance(body, dict) else {}, actor=actor)
    except routing.RoutingError as exc:
        exc.status, exc.code = 400, "bad_request"
        raise


def decision_choose(decision_id, body, principal=None):
    """POST /akim/decisions/{id} — staff. body: {"option": 1|2}."""
    _require_staff(principal)
    actor = (principal or {}).get("username") if isinstance(principal, dict) else None
    option = body.get("option") if isinstance(body, dict) else None
    try:
        return default_service().choose_decision(str(decision_id), option, actor=actor)
    except decisions.DecisionError as exc:
        exc.code = "bad_request" if exc.status == 400 else "not_found"
        raise


def nearby_subscribe(body):
    """POST /nearby/subscriptions — житель, без входа (лимит запросов — у шлюза). body: {device_id, scope, id, on}."""
    b = body if isinstance(body, dict) else {}
    try:
        return {"items": nearby.subscribe(b.get("device_id"), b.get("scope"), b.get("id"), on=b.get("on", True) is not False)}
    except nearby.NearbyError as exc:
        exc.code = "too_many_requests" if exc.status == 429 else "bad_request"
        raise
