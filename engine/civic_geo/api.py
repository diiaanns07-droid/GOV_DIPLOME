"""HTTP-функции R12 для оболочки R01 (маршруты подключает R01 в ui/web_server.py).

    GET /api/civic/v2/targets?lon=..&lat=..&category=..      -> targets_response(query)
    GET /api/civic/v2/street-segment?from=lon,lat&to=lon,lat[&kind=road|foot]  -> segment_response(query)
    GET /api/civic/v2/street-snap?lon=..&lat=..[&kind=road|foot]   -> snap_response(query)   (редактор: клик прилипает к оси)
    GET /api/civic/v2/objects-near?lon=..&lat=..            -> near_response(query)   (редактор: точка -> объект OSM)
    GET /api/civic/v2/yard?lon=..&lat=..                    -> yard_response(query)   (редактор: двор выбором полигона)
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
from . import geo
from .segment import DEFAULT_SNAP_M, GeoError, snap, street_segment
from .targets import OBJECT_RADIUS_M, TargetError, load_categories, object_target, segment_target, targets, yard_target, _street_near

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
        category = _one(query, "category") or None
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
        groups = KIND_GROUPS.get(kind) if kind else None
        return 200, street_segment(get_graph(), a, b, groups=groups)
    except (TargetError, GeoError) as exc:
        return _error(400, exc.code, exc.message)
    except Exception:
        LOGGER.exception("civic_geo street-segment failed")
        return _error(503, "geo_unavailable", "Построить участок улицы сейчас нельзя. Повторите позже.")


KIND_GROUPS = {"road": ("road", "service"), "foot": ("foot",)}


def _point(query: dict) -> tuple[float, float]:
    try:
        lon, lat = float(_one(query, "lon")), float(_one(query, "lat"))
    except (TypeError, ValueError):
        raise TargetError("bad_point", "Нужны параметры lon и lat — числа.")
    return _check_point(lon, lat)


def snap_response(query: dict):
    """Точка на оси ближайшей улицы (не дальше 60 м) — первый щелчок инструмента «Участок улицы»."""
    try:
        p = _point(query)
        found = snap(get_graph(), p, DEFAULT_SNAP_M, KIND_GROUPS.get(_one(query, "kind")), limit=1)
        if not found:
            raise GeoError("not_on_street", f"Рядом нет улицы (дальше {int(DEFAULT_SNAP_M)} м). Нажмите на саму улицу.")
        d, e, pr = found[0]
        t = segment_target(e)
        return 200, {"point": geo.round_coord(pr.point), "edge_id": e.id, "distance_m": round(d, 1),
                     "street_ru": e.name, "street_kk": e.label_kk() if e.name else None,
                     "label_ru": t["label_ru"], "label_kk": t["label_kk"]}
    except (TargetError, GeoError) as exc:
        return _error(400, exc.code, exc.message)
    except Exception:
        LOGGER.exception("civic_geo street-snap failed")
        return _error(503, "geo_unavailable", "Привязка к улице сейчас недоступна. Повторите позже.")


def near_response(query: dict):
    """До трёх реальных объектов OSM рядом с точкой (остановки, площадки, парки, места для мусора)."""
    try:
        p = _point(query)
        objects, _, _ = get_layers()
        out = []
        for d, f in objects.near(p, OBJECT_RADIUS_M)[:3]:
            t = object_target(f)
            out.append({"id": f.id, "kind": f.kind, "label_ru": t["label_ru"], "label_kk": t["label_kk"],
                        "point": geo.round_coord(f.point), "distance_m": round(d, 1)})
        return 200, {"objects": out, "count_total": len(objects.items)}
    except TargetError as exc:
        return _error(400, exc.code, exc.message)
    except Exception:
        LOGGER.exception("civic_geo objects-near failed")
        return _error(503, "geo_unavailable", "Объекты рядом сейчас недоступны. Повторите позже.")


def yard_response(query: dict):
    """Двор OSM (landuse=residential), внутри которого точка; yard=null, если двора нет или данных ещё нет."""
    try:
        p = _point(query)
        _, yards, _ = get_layers()
        inside = yards.containing(p)
        if not inside:
            reason = "no_yards_data" if not yards.items else "not_in_yard"
            return 200, {"yard": None, "reason": reason}
        f = inside[0]
        t = yard_target(f, _street_near(get_graph(), p))
        return 200, {"yard": {"id": f.id, "label_ru": t["label_ru"], "label_kk": t["label_kk"],
                              "geometry": {"type": "Polygon", "coordinates": f.polygon}}, "reason": None}
    except TargetError as exc:
        return _error(400, exc.code, exc.message)
    except Exception:
        LOGGER.exception("civic_geo yard failed")
        return _error(503, "geo_unavailable", "Дворы сейчас недоступны. Повторите позже.")


ROUTES = {
    "/targets": targets_response,
    "/street-segment": segment_response,
    "/street-snap": snap_response,
    "/objects-near": near_response,
    "/yard": yard_response,
}


def handle(path: str, query: dict):
    """Один вход для R01: path без префикса /api/civic/v2 ("/targets", ...). (код, тело) или None — не наш путь."""
    if path == "/geo/status":
        return status_response()
    fn = ROUTES.get(path)
    return fn(query) if fn else None


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


# ---------- функции в стиле шлюза R01 (research/round-14-results/R01/INTEGRATION.txt §1) ----------
# Возвращают словарь (-> 200) или бросают исключение с status/code/message (-> этот код).
class GeoUnavailable(RuntimeError):
    status = 503
    code = "geo_unavailable"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _unwrap(result):
    status, body = result
    if status == 200:
        return body
    err = body.get("error") or {}
    exc = (TargetError if status == 400 else GeoUnavailable)(*((err.get("code"), err.get("message")) if status == 400 else (err.get("message"),)))
    raise exc


def street_snap(lon, lat, kind=None) -> dict:
    return _unwrap(snap_response({"lon": str(lon), "lat": str(lat), "kind": kind}))


def segment_between(from_point, to_point, kind=None) -> dict:
    """from_point/to_point — [lon, lat] или строка «lon,lat»."""
    as_text = lambda p: p if isinstance(p, str) else ",".join(str(x) for x in p)  # noqa: E731
    return _unwrap(segment_response({"from": as_text(from_point), "to": as_text(to_point), "kind": kind}))


def objects_near(lon, lat) -> dict:
    return _unwrap(near_response({"lon": str(lon), "lat": str(lat)}))


def yard_at(lon, lat) -> dict:
    return _unwrap(yard_response({"lon": str(lon), "lat": str(lat)}))


def geo_status() -> dict:
    return _unwrap(status_response())
