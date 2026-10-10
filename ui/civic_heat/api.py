"""HTTP-обёртка тепловой карты для ui/web_server.py (подключает R01, см. INTEGRATION.txt).

    from ui.civic_heat.api import handle_get
    status, body = handle_get(path, query)      # query — dict из urllib.parse.parse_qs или простой dict

Маршруты (CONTRACT §7, всё под /api/civic/v2/):
    GET /heat?bbox&days&category&district&zoom  → {generated_at, items:[{target, geometry, weight, level, count, fixed_until, …}]}
    GET /heat/meta                              → категории, легенда, районы, периоды (интерфейс ничего не копирует)
    GET /heat/target?kind&id&days               → одна цель для карточки + «Что пишут жители» (texts.groups)
Тексты настоящих жалоб — только сотруднику: шлюз R01 передаёт staff=True после проверки входа (principal R02).
Без этого в texts только примеры (demo: true), а люди настоящих жалоб — числом hidden_people.
Ошибка в параметрах → 400 {"error":"bad_request","field":…,"message":…}. Сбой расчёта → 500 без падения сервера.
"""
from __future__ import annotations

import logging
import traceback

from .service import HeatError, default_service

PREFIX = "/api/civic/v2"
log = logging.getLogger("civic_heat")


def _one(query: dict, name: str):
    v = (query or {}).get(name)
    if isinstance(v, (list, tuple)):
        return v[0] if v else None
    return v


def handle_get(path: str, query: dict | None = None, service=None, staff: bool = False) -> tuple[int, dict]:
    svc = service or default_service()
    q = query or {}
    try:
        if path == PREFIX + "/heat":
            return 200, svc.heat(bbox=_one(q, "bbox"), days=_one(q, "days"), category=_one(q, "category"),
                                 district=_one(q, "district"), zoom=_one(q, "zoom"))
        if path == PREFIX + "/heat/meta":
            return 200, svc.meta()
        if path == PREFIX + "/heat/target":
            kind, tid = _one(q, "kind"), _one(q, "id")
            if not kind or not tid:
                return 400, {"error": "bad_request", "field": "id", "message": "нужны kind и id цели"}
            item = svc.target(kind, tid, days=_one(q, "days"), include_real_texts=bool(staff))
            if item is None:
                return 404, {"error": "not_found", "message": "по этой цели жалоб за период нет"}
            return 200, {"item": item, "legend": svc.config.legend(), "demo": svc.is_demo}
        return 404, {"error": "not_found", "message": "нет такого адреса"}
    except HeatError as exc:
        return 400, {"error": "bad_request", "field": exc.field, "message": str(exc)}
    except Exception:  # сервер не должен падать из-за карты
        log.error("heat failed: %s", traceback.format_exc())
        return 500, {"error": "heat_failed", "message": "тепловая карта временно не считается"}
