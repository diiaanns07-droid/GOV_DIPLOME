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
Ошибка в параметрах → 400 {"error":"bad_request","field":…,"message":…}. Сбой расчёта → 500, сервер не падает.
В ответе нет текстов жалоб и данных жителей — только числа и подписи мест.
"""
from __future__ import annotations

import logging
import traceback

from . import routing
from .summary import AkimError, default_service

PREFIX = "/api/civic/v2"
log = logging.getLogger("civic_akim")


def _one(query: dict, name: str):
    v = (query or {}).get(name)
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def handle_get(path: str, query: dict | None = None, service=None) -> tuple[int, dict]:
    svc = service or default_service()
    try:
        if path == PREFIX + "/akim/summary":
            return 200, svc.summary(date=_one(query, "date"), district=_one(query, "district"))
        if path == PREFIX + "/akim/routing":
            category = _one(query, "category")
            if category:
                return 200, routing.service_for(str(category), _one(query, "subtopic") or None)
            return 200, routing.table()
        return 404, {"error": "not_found", "message": "нет такого адреса"}
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
