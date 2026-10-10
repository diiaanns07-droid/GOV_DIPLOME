"""R12 · точность карты: привязка к улицам и объектам OSM (только стандартная библиотека).

Главное для соседей:
    targets(lon, lat, category)        -> {"candidates": [...]}  кандидаты привязки жалобы (CONTRACT §4, §7)
    target_geometry({"kind", "id"})    -> {"geometry", "label_ru", "label_kk", "approximate"} | None  (R07, R08)
    street_segment(graph, a, b)        -> участок улицы по рёбрам графа
    api.handle(path, query)            -> (код, тело) для маршрутов /api/civic/v2/... (подключает R01)
Подробности — engine/civic_geo/README.md.
"""
from __future__ import annotations

from .api import geo_status, objects_near, segment_between, street_snap, yard_at  # noqa: F401
from .targets import targets  # noqa: F401  (шлюз R01: targets(lon, lat, category=None))


def target_geometry(target: dict) -> dict | None:
    """Форма и подпись цели по её id: объект OSM, ребро графа, двор или ячейка. None — цель неизвестна."""
    from . import geo
    from .graph import get_graph
    from .objects import get_layers
    from .targets import _street_near, cell_target, object_target, segment_street, segment_target, yard_target

    kind, tid = (target or {}).get("kind"), str((target or {}).get("id") or "")
    if not tid:
        return None
    objects, yards, cells = get_layers()
    if kind == "object" or tid.startswith("osm-node-") or tid.startswith("osm-way-") or tid.startswith("osm-relation-"):
        f = objects.by_id.get(tid)
        if f is None:
            return None
        t = object_target(f)
        g = {"type": "Polygon", "coordinates": f.polygon} if f.polygon else {"type": "Point", "coordinates": geo.round_coord(f.point)}
        return {"geometry": g, "point": geo.round_coord(f.point), "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": False}
    if tid.startswith("yard-"):
        f = yards.by_id.get(tid)
        if f is None:
            return None
        t = yard_target(f, _street_near(get_graph(), f.point))
        return {"geometry": {"type": "Polygon", "coordinates": f.polygon}, "point": f.point,
                "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": False}
    if tid.startswith("cell-"):
        try:
            poly = cells.polygon(tid)
        except ValueError:
            return None
        center = cells.center(tid)
        t = cell_target(tid, _street_near(get_graph(), center))
        return {"geometry": {"type": "Polygon", "coordinates": poly}, "point": center,
                "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": True}
    if kind == "segment" or tid.startswith("osm-w"):
        e = get_graph().by_id.get(tid)
        if e is None:
            return None
        t = segment_target(e, segment_street(get_graph(), e))
        coords = [geo.round_coord(c) for c in e.geometry]
        return {"geometry": {"type": "LineString", "coordinates": coords}, "point": coords[len(coords) // 2],
                "label_ru": t["label_ru"], "label_kk": t["label_kk"], "approximate": False}
    return None
