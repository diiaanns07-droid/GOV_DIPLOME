"""HTTP-обёртка «Картины дня» для ui/web_server.py (подключает R01, см. research/round-14-results/R08/INTEGRATION.txt).

    from ui.civic_akim.api import handle_get
    status, body = handle_get(path, query)     # query — dict из parse_qs или простой dict

Маршрут (CONTRACT §7):
    GET /api/civic/v2/akim/summary?date=2026-10-12&district=nura
        date — день в календаре Астаны (по умолчанию сегодня), district — id района или all.
Ошибка в параметрах → 400 {"error":"bad_request","field":…,"message":…}. Сбой расчёта → 500, сервер не падает.
В ответе нет текстов жалоб и данных жителей — только числа и подписи мест.
"""
from __future__ import annotations

import logging
import traceback

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
        return 404, {"error": "not_found", "message": "нет такого адреса"}
    except AkimError as exc:
        return 400, {"error": "bad_request", "field": exc.field, "message": str(exc)}
    except Exception:  # картина дня не должна ронять сервер
        log.error("akim summary failed: %s", traceback.format_exc())
        return 500, {"error": "akim_failed", "message": "картина дня временно не считается"}
