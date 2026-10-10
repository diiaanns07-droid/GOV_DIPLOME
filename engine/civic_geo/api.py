"""HTTP-функции R12 для оболочки R01 (маршруты подключает R01 в ui/web_server.py).

    GET /api/civic/v2/targets?lon=..&lat=..&category=..      -> targets_response(query)
    GET /api/civic/v2/street-segment?from=lon,lat&to=lon,lat[&kind=road|foot]  -> segment_response(query)
    GET /api/civic/v2/geo/status                            -> status_response()

Каждая функция получает разобранный query (как parse_qs: {"lon": ["71.4"]} или просто {"lon": "71.4"})
и возвращает (код, словарь для JSON). Исключений наружу не бросает: ошибки — 400/503 с понятным текстом.
Первый вызов загружает граф (~2 с); R01 может вызвать warm_up() при старте сервера.
"""
from __future__ import annotations

import logging
import math

from .graph import get_graph
from .objects import get_layers
from .segment import GeoError, street_segment
from .targets import TargetError, load_categories, targets

LOGGER = logging.getLogger(__name__)
# Граница запросов — bbox графа OSM (Астана и окрестности); точная граница города проверяется отчётом точности.
QUERY_BBOX = (71.2079, 50.9206, 71.7953, 51.3612)


def _one(query: dict, key: str):
    v = query.get(key)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return v.strip() if isinstance(v, str) else v


def _coord(text, name: str) -> tuple[float, float]:
    try:
        lon, lat = (float(x) for x in str(text).split(","))
    except (TypeError, ValueError):
        raise TargetError("bad_point", f"Параметр {name}: нужны два числа «долгота,широта».")
    return _check_point(lon, lat)


def _check_point(lon: float, lat: float) -> tuple[float, float]:
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise TargetError("bad_point", "Координаты должны быть числами.")
    if not (QUERY_BBOX[0] <= lon <= QUERY_BBOX[2] and QUERY_BBOX[1] <= lat <= QUERY_BBOX[3]):
        raise TargetError("outside_city", "Точка вне карты Астаны. Выберите место в городе.")
    return lon, lat


def _error(status: int, code: str, message: str):
    return status, {"error": {"code": code, "message": message}}


def targets_response(query: dict):
    try:
        try:
            lon, lat = float(_one(query, "lon")), float(_one(query, "lat"))
        except (TypeError, ValueError):
            raise TargetError("bad_point", "Нужны параметры lon и lat — числа.")
        lon, lat = _check_point(lon, lat)
        category = _one(query, "category") or "other"
        limit = _one(query, "limit")
        limit = max(1, min(3, int(limit))) if limit and str(limit).isdigit() else 3
        return 200, targets(lon, lat, category, limit=limit)
    except TargetError as exc:
        return _error(400, exc.code, exc.message)
    except Exception:  # граф не загрузился, файл испорчен и т. п.
        LOGGER.exception("civic_geo targets failed")
        return _error(503, "geo_unavailable", "Привязка к карте сейчас недоступна. Повторите позже.")


def segment_response(query: dict):
    try:
        a = _coord(_one(query, "from"), "from")
        b = _coord(_one(query, "to"), "to")
        kind = _one(query, "kind")
        groups = {"road": ("road", "service"), "foot": ("foot",)}.get(kind) if kind else None
        return 200, street_segment(get_graph(), a, b, groups=groups)
    except (TargetError, GeoError) as exc:
        return _error(400, exc.code, exc.message)
    except Exception:
        LOGGER.exception("civic_geo street-segment failed")
        return _error(503, "geo_unavailable", "Построить участок улицы сейчас нельзя. Повторите позже.")


def status_response():
    try:
        g = get_graph()
        objects, yards, cells = get_layers()
        return 200, {"graph_id": g.id, "graph_digest": g.digest, "snapshot_at": g.snapshot_at, "edges": len(g.edges),
                     "way_tags": g.has_tags, "objects": len(objects.items), "yards": len(yards.items),
                     "cell_m": cells.params["cell_m"], "categories": len(load_categories()),
                     "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors"}
    except Exception:
        LOGGER.exception("civic_geo status failed")
        return _error(503, "geo_unavailable", "Данные карты не загрузились.")


def warm_up():
    """Загрузить граф, слои и категории заранее (чтобы первый житель не ждал 2 с)."""
    get_graph()
    get_layers()
    load_categories()
