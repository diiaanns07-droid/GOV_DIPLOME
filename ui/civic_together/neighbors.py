"""Что «Мой двор» читает у соседей — только их функциями и только на чтение (CONTRACT §7, prompts/R16 «НЕ ДЕЛАЙ»).

  R12 engine.civic_geo  — двор по id (подпись, точка, форма OSM) и двор по точке;
  R07 ui.civic_heat     — проблемы двора: цели тепловой карты в форме двора и рядом (те же числа, что на карте;
                           источник — жалобы R09, которые шлюз R01 подключает к карте в wire());
  R06 ui.civic_store.v2 — идеи жителей рядом и работы рядом (функции list_ideas, nearby_items);
  R06 / R07             — район по точке (геозона OSM).

Каждая функция возвращает блок {"status": "ok", ...} или {"status": "no_data", "reason": ...}: нет модуля, модуль не
связан с хранилищем, сбой — экран показывает «пока нет данных», а не ошибку. Подмена для тестов и для R01 —
configure(problems=..., ideas=..., works=..., yard_geo=..., district_of=...).
"""

from __future__ import annotations

import logging
import math
import threading
import time

LOGGER = logging.getLogger("civic_together")

PROBLEM_RADIUS_M = 60      # цель тепловой карты относится к двору: внутри формы двора или не дальше 60 м от края
IDEA_RADIUS_M = 600        # идеи жителей рядом с двором
WORK_RADIUS_M = 800        # работы и отключения рядом
_GEO_TTL_S = 3600          # подпись и форма двора OSM меняются только с новой выгрузкой — кэш на час
_GEO_CACHE_MAX = 4096      # R15 S51: id двора приходит из адреса — кэш не растёт без предела

_overrides: dict = {}
_geo_cache: dict = {}
_lock = threading.Lock()


def configure(**sources) -> None:
    """Подменить источник: problems(geo) | ideas(geo, district) | works(geo, district) | yard_geo(id) |
    yard_at(lon, lat) | district_of(point). None — вернуть стандартный источник."""
    for name, fn in sources.items():
        if fn is None:
            _overrides.pop(name, None)
        else:
            _overrides[name] = fn
    with _lock:
        _geo_cache.clear()


def no_data(reason: str) -> dict:
    return {"status": "no_data", "reason": reason, "items": []}


# --------------------------------------------------------------------------- геометрия (метры, локально)
_M_LAT = 110_574.0


def _xy(point, lat0: float) -> tuple[float, float]:
    return point[0] * 111_320.0 * math.cos(math.radians(lat0)), point[1] * _M_LAT


def distance_m(a, b) -> float:
    lat0 = (a[1] + b[1]) / 2
    (ax, ay), (bx, by) = _xy(a, lat0), _xy(b, lat0)
    return math.hypot(ax - bx, ay - by)


def _seg_distance(p, a, b, lat0) -> float:
    (px, py), (ax, ay), (bx, by) = _xy(p, lat0), _xy(a, lat0), _xy(b, lat0)
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _inside(point, ring) -> bool:
    x, y, inside = point[0], point[1], False
    for i in range(len(ring)):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i - 1][0], ring[i - 1][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def _rings(geometry) -> list:
    if not isinstance(geometry, dict):
        return []
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Polygon":
        return [coords[0]] if coords else []
    if kind == "MultiPolygon":
        return [poly[0] for poly in coords or [] if poly]
    return []


def point_to_area_m(point, geometry) -> float:
    """0 — точка внутри формы двора; иначе расстояние до края в метрах."""
    rings = _rings(geometry)
    if not rings:
        return math.inf
    best = math.inf
    for ring in rings:
        if _inside(point, ring):
            return 0.0
        lat0 = point[1]
        for i in range(1, len(ring)):
            best = min(best, _seg_distance(point, ring[i - 1], ring[i], lat0))
    return best


def _points(geometry) -> list:
    if not isinstance(geometry, dict):
        return []
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        return [coords]
    if kind in ("LineString", "MultiPoint"):
        return list(coords or [])
    if kind in ("Polygon", "MultiLineString"):
        return [p for line in coords or [] for p in line]
    if kind == "MultiPolygon":
        return [p for poly in coords or [] for line in poly for p in line]
    return []


def geometry_to_area_m(geometry, area) -> float:
    """Ближайшая точка геометрии (вершины линии, точка) до формы двора — для «рядом с двором»."""
    pts = _points(geometry)
    if not pts:
        return math.inf
    # Длинный участок улицы: середины рёбер тоже, чтобы короткий двор у середины участка не «потерялся».
    extra = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(pts, pts[1:])]
    return min(point_to_area_m(p, area) for p in pts + extra)


def bbox_around(geometry, point, pad_m: float) -> tuple[float, float, float, float]:
    pts = _points(geometry) or [point]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    lat0 = sum(lats) / len(lats)
    dlat = pad_m / _M_LAT
    dlon = pad_m / (111_320.0 * math.cos(math.radians(lat0)))
    return (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)


# --------------------------------------------------------------------------- R12: двор
def yard_geo(yard_id: str) -> dict | None:
    """{"label_ru", "label_kk", "point", "geometry", "street", "approximate"} по id двора или None (нет R12/двора)."""
    if "yard_geo" in _overrides:
        return _overrides["yard_geo"](yard_id)
    with _lock:
        hit = _geo_cache.get(yard_id)
        if hit and time.monotonic() - hit[0] < _GEO_TTL_S:
            return hit[1]
    value = None
    try:
        from engine.civic_geo import target_info
        info = target_info(yard_id)
        target = info.get("target") or {}
        value = {"label_ru": target.get("label_ru"), "label_kk": target.get("label_kk"), "point": info.get("point"),
                 "geometry": info.get("geometry"), "street": info.get("street"),
                 "approximate": bool(info.get("approximate"))}
    except Exception as exc:  # TargetError — нет такого двора; ImportError — нет модуля
        LOGGER.info("R12: двор %s не найден (%s)", yard_id, type(exc).__name__)
        value = None
    with _lock:
        if len(_geo_cache) >= _GEO_CACHE_MAX:
            _geo_cache.clear()
        _geo_cache[yard_id] = (time.monotonic(), value)
    return value


def yard_at(lon: float, lat: float) -> dict | None:
    """Двор OSM, в котором точка ({"id", "label_ru", "label_kk", "geometry"}), или None."""
    if "yard_at" in _overrides:
        return _overrides["yard_at"](lon, lat)
    try:
        from engine.civic_geo.api import yard_at as r12_yard_at
        return (r12_yard_at(lon, lat) or {}).get("yard")
    except Exception:
        return None


def district_of(point) -> str | None:
    if "district_of" in _overrides:
        return _overrides["district_of"](point)
    if not point:
        return None
    try:
        from ui.civic_store.districts import district_of as r06_district_of
        return r06_district_of({"type": "Point", "coordinates": [float(point[0]), float(point[1])]})
    except Exception:
        pass
    try:
        from ui.civic_heat.geo import district_of as r07_district_of
        return r07_district_of(point)
    except Exception:
        return None


# --------------------------------------------------------------------------- R07: проблемы двора
def _problem_view(item: dict) -> dict:
    by_category = item.get("by_category") or {}
    category = max(by_category, key=by_category.get) if by_category else None
    sub = item.get("top_subtopic") or {}
    target = item.get("target") or {}
    return {
        "target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk")},
        "level": item.get("level"), "color": item.get("color"), "count": int(item.get("count") or 0),
        "state": item.get("state"), "status": item.get("status"), "category": category,
        "subtopic": {"id": sub.get("id"), "ru": sub.get("ru"), "kk": sub.get("kk")} if sub else None,
        "anchor": item.get("anchor"), "last_at": item.get("last_at"), "fixed_at": item.get("fixed_at"),
        "demo": bool(item.get("demo")),
    }


def problems(geo: dict) -> dict:
    """Цели тепловой карты в форме двора и до 60 м от края: те же цвет и число людей, что на карте (R07)."""
    if "problems" in _overrides:
        return _overrides["problems"](geo)
    if not geo or not geo.get("point"):
        return no_data("no_yard_geometry")
    try:
        from ui.civic_heat import default_service
        svc = default_service()
        box = bbox_around(geo.get("geometry"), geo["point"], PROBLEM_RADIUS_M + 40)
        heat = svc.heat(bbox=",".join(f"{v:.6f}" for v in box), zoom="16")
    except Exception:
        LOGGER.exception("R07: проблемы двора не прочитаны")
        return no_data("heat_unavailable")
    area = geo.get("geometry")
    items = []
    for item in heat.get("items") or []:
        target = item.get("target") or {}
        # Соседний двор — не проблема этого двора (у него своя страница); улицы и объекты рядом — да.
        if target.get("kind") == "area" and geo.get("id") and target.get("id") != geo["id"]:
            continue
        geometry = item.get("geometry")
        near = geometry_to_area_m(geometry, area) if area else (
            min((distance_m(p, geo["point"]) for p in _points(geometry)), default=math.inf))
        if near <= (PROBLEM_RADIUS_M if area else PROBLEM_RADIUS_M * 3):
            items.append(_problem_view(item))
    active = [i for i in items if i["state"] != "fixed"]
    fixed = [i for i in items if i["state"] == "fixed"]
    active.sort(key=lambda i: (-(i["level"] or 0), -i["count"]))
    fixed.sort(key=lambda i: i.get("fixed_at") or "", reverse=True)
    return {"status": "ok", "items": active[:12], "fixed": fixed[:6], "count": len(active),
            "people": sum(i["count"] for i in active), "demo": bool(heat.get("demo")),
            "legend": (heat.get("legend") or {}).get("levels")}


# --------------------------------------------------------------------------- R06: идеи и работы рядом
def ideas(geo: dict, district: str | None) -> dict:
    if "ideas" in _overrides:
        return _overrides["ideas"](geo, district)
    if not geo or not geo.get("point"):
        return no_data("no_yard_geometry")
    try:
        from ui.civic_store import v2 as r06
        data = r06.list_ideas(district=district)
    except Exception as exc:
        LOGGER.info("R06: идеи не прочитаны (%s)", type(exc).__name__)
        return no_data("ideas_unavailable")
    out = []
    for item in (data or {}).get("items") or []:
        pts = _points(item.get("geometry"))
        if not pts:
            continue
        near = point_to_area_m(pts[0], geo.get("geometry")) if geo.get("geometry") else distance_m(pts[0], geo["point"])
        if near > IDEA_RADIUS_M or item.get("status") not in ("voting", "checking", "project"):
            continue
        out.append({"id": item.get("id"), "status": item.get("status"), "title_ru": item.get("title_ru"),
                    "title_kk": item.get("title_kk"), "votes": item.get("votes"), "point": pts[0],
                    "distance_m": round(near), "demo": bool(item.get("demo"))})
    out.sort(key=lambda i: (i["distance_m"], -(i["votes"] or 0)))
    return {"status": "ok", "items": out[:6], "count": len(out)}


def works(geo: dict, district: str | None) -> dict:
    if "works" in _overrides:
        return _overrides["works"](geo, district)
    if not geo or not geo.get("point"):
        return no_data("no_yard_geometry")
    try:
        from ui.civic_store import v2 as r06
        rows = r06.nearby_items(district)
    except Exception as exc:
        LOGGER.info("R06: работы рядом не прочитаны (%s)", type(exc).__name__)
        return no_data("works_unavailable")
    rows = rows.get("items") if isinstance(rows, dict) else rows
    out = []
    for item in rows or []:
        pts = _points(item.get("geometry"))
        if not pts:
            continue
        near = min(point_to_area_m(p, geo.get("geometry")) if geo.get("geometry") else distance_m(p, geo["point"])
                   for p in pts)
        if near > WORK_RADIUS_M or item.get("status") in ("done", "cancelled"):
            continue
        out.append({"id": item.get("id"), "type": item.get("type"), "status": item.get("status"),
                    "title_ru": item.get("title_ru"), "title_kk": item.get("title_kk"),
                    "start": item.get("start"), "end": item.get("end") or item.get("planned_end"),
                    "utility": item.get("utility"), "work_kind": item.get("work_kind"),
                    "distance_m": round(near), "demo": bool(item.get("demo"))})
    out.sort(key=lambda i: i["distance_m"])
    return {"status": "ok", "items": out[:6], "count": len(out)}
