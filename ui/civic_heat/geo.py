"""Простая геометрия для тепловой карты (только стандартная библиотека).

Координаты везде [lon, lat] (как в GeoJSON). Расстояния — в метрах по сфере.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

from .config import GEOFENCE_PATH

EARTH_R = 6371008.8

# Сетка ячеек ~150 м для мест, где нет двора (CONTRACT §4: area → cell-<id>).
# Ячейка задаётся номером столбца и строки от фиксированного угла; размер в градусах
# считается на широте Астаны, поэтому ячейка почти квадратная (≈150×150 м).
CELL_M = 150.0
CELL_ORIGIN = (71.0, 50.8)
CELL_LAT0 = 51.15
CELL_DLON = CELL_M / (111320.0 * math.cos(math.radians(CELL_LAT0)))
CELL_DLAT = CELL_M / 110574.0
_CELL_RE = re.compile(r"^cell-(-?\d+)-(-?\d+)$")


def haversine_m(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def line_length_m(coords) -> float:
    return sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def line_midpoint(coords) -> list[float]:
    """Точка посередине линии ПО ДЛИНЕ (а не средняя вершина) — туда ставится значок участка."""
    if len(coords) == 1:
        return list(coords[0])
    total = line_length_m(coords)
    if total <= 0:
        return list(coords[0])
    half = total / 2
    walked = 0.0
    for i in range(len(coords) - 1):
        seg = haversine_m(coords[i], coords[i + 1])
        if walked + seg >= half and seg > 0:
            t = (half - walked) / seg
            return [coords[i][0] + (coords[i + 1][0] - coords[i][0]) * t, coords[i][1] + (coords[i + 1][1] - coords[i][1]) * t]
        walked += seg
    return list(coords[-1])


def ring_centroid(ring) -> list[float]:
    """Центр тяжести кольца; для вырожденного кольца — среднее вершин."""
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-15:
        pts = ring[:-1] or ring
        return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]
    a *= 0.5
    return [cx / (6 * a), cy / (6 * a)]


def point_in_ring(pt, ring) -> bool:
    x, y = pt
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_polygon(pt, rings) -> bool:
    return bool(rings) and point_in_ring(pt, rings[0]) and not any(point_in_ring(pt, h) for h in rings[1:])


def anchor_of(geometry: dict) -> list[float] | None:
    """Где ставить значок с числом: точка — сама точка, линия — середина, область — центр."""
    if not geometry:
        return None
    t, c = geometry.get("type"), geometry.get("coordinates")
    if t == "Point":
        return list(c)
    if t == "LineString":
        return line_midpoint(c)
    if t == "MultiLineString":
        longest = max(c, key=line_length_m)
        return line_midpoint(longest)
    if t == "Polygon":
        return ring_centroid(c[0])
    if t == "MultiPolygon":
        biggest = max(c, key=lambda poly: abs(_ring_area(poly[0])))
        return ring_centroid(biggest[0])
    return None


def _ring_area(ring) -> float:
    return 0.5 * sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))


def bbox_of(geometry: dict) -> tuple[float, float, float, float] | None:
    pts: list = []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                walk(x)

    if not geometry or "coordinates" not in geometry:
        return None
    walk(geometry["coordinates"])
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_intersects(a, b) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def circle_polygon(center, radius_m: float, steps: int = 24) -> dict:
    """Многоугольник-круг: «примерное место», когда точной цели нет (CONTRACT §8.4)."""
    lon, lat = center
    dlat = radius_m / 110574.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    ring = [[round(lon + dlon * math.cos(2 * math.pi * i / steps), 6), round(lat + dlat * math.sin(2 * math.pi * i / steps), 6)] for i in range(steps)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


# ---------- Ячейки ~150 м ----------

def cell_id_for(point) -> str:
    ix = math.floor((point[0] - CELL_ORIGIN[0]) / CELL_DLON)
    iy = math.floor((point[1] - CELL_ORIGIN[1]) / CELL_DLAT)
    return f"cell-{ix}-{iy}"


def cell_polygon(cell_id: str) -> dict | None:
    m = _CELL_RE.match(cell_id or "")
    if not m:
        return None
    ix, iy = int(m.group(1)), int(m.group(2))
    x0 = CELL_ORIGIN[0] + ix * CELL_DLON
    y0 = CELL_ORIGIN[1] + iy * CELL_DLAT
    x1, y1 = x0 + CELL_DLON, y0 + CELL_DLAT
    ring = [[round(x0, 6), round(y0, 6)], [round(x1, 6), round(y0, 6)], [round(x1, 6), round(y1, 6)], [round(x0, 6), round(y1, 6)], [round(x0, 6), round(y0, 6)]]
    return {"type": "Polygon", "coordinates": [ring]}


# ---------- Районы (реальные полигоны OSM из geofence.json) ----------

DISTRICT_NAMES_KK = {
    # В geofence.json только русские названия; казахские — официальные названия районов Астаны.
    "almaty": "Алматы", "baikonur": "Байқоңыр", "esil": "Есіл",
    "nura": "Нұра", "saraishyk": "Сарайшық", "saryarka": "Сарыарқа",
}


@lru_cache(maxsize=1)
def districts(path: str | None = None) -> dict:
    """district_id → {name_ru, name_kk, geometry(MultiPolygon), bbox}."""
    raw = json.loads(Path(path or GEOFENCE_PATH).read_text("utf-8"))
    out: dict = {}
    for p in raw.get("polygons", []):
        d = out.setdefault(p["district_id"], {"id": p["district_id"], "name_ru": p.get("name", p["district_id"]),
                                               "name_kk": DISTRICT_NAMES_KK.get(p["district_id"], p.get("name", "")),
                                               "polys": []})
        d["polys"].append(p["rings"])
    for d in out.values():
        d["geometry"] = {"type": "MultiPolygon", "coordinates": d["polys"]}
        d["bbox"] = bbox_of(d["geometry"])
    return out


def district_of(point) -> str | None:
    for d in districts().values():
        bb = d["bbox"]
        if not (bb[0] <= point[0] <= bb[2] and bb[1] <= point[1] <= bb[3]):
            continue
        if any(point_in_polygon(point, rings) for rings in d["polys"]):
            return d["id"]
    return None
