"""Район Астаны по геометрии объекта (R06, раунд 14).

Полигоны — data/civic/astana/geofence.json: реальные административные отношения OpenStreetMap
(ODbL, © OpenStreetMap contributors). Это не официальное юридическое описание границ — для
«Картины дня» по районам точности хватает, но в интерфейсе район не выдаётся за юридический факт.

Файл только читается. Если его нет, district_of() возвращает None — модуль продолжает работать.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading

from .db import REPO_ROOT

GEOFENCE_PATH = REPO_ROOT / "data" / "civic" / "astana" / "geofence.json"

# Подписи районов. id совпадают с geofence.json (district_id) и с CONTRACT §5 (district: "nura").
DISTRICT_NAMES = {
    "almaty": {"ru": "Алматы", "kk": "Алматы"},
    "baikonur": {"ru": "Байконур", "kk": "Байқоңыр"},
    "esil": {"ru": "Есиль", "kk": "Есіл"},
    "nura": {"ru": "Нура", "kk": "Нұра"},
    "saraishyk": {"ru": "Сарайшык", "kk": "Сарайшық"},
    "saryarka": {"ru": "Сарыарка", "kk": "Сарыарқа"},
}

_lock = threading.Lock()
_cache: dict[str, object] = {}


def _load(path: Path = GEOFENCE_PATH):
    """[(district_id, ring, bbox)] — у района может быть несколько колец (эксклавы)."""
    key = str(path)
    with _lock:
        if key in _cache:
            return _cache[key]
        polygons = []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data.get("polygons", []):
                district = item.get("district_id")
                if district not in DISTRICT_NAMES:
                    continue
                for ring in item.get("rings", []):
                    if len(ring) < 4:
                        continue
                    lons = [p[0] for p in ring]
                    lats = [p[1] for p in ring]
                    polygons.append((district, ring, (min(lons), min(lats), max(lons), max(lats))))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            polygons = []
        _cache[key] = polygons
        return polygons


def _inside(lon: float, lat: float, ring) -> bool:
    """Точка в кольце: классический луч вправо (чётность пересечений)."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def representative_point(geometry):
    """Точка, по которой определяется район: Point — сама точка; линия — средняя вершина;
    полигон — среднее вершин внешнего кольца (для дворов и скверов этого достаточно)."""
    if not isinstance(geometry, dict):
        return None
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    try:
        if kind == "Point":
            return float(coords[0]), float(coords[1])
        if kind == "LineString" and coords:
            point = coords[len(coords) // 2]
            return float(point[0]), float(point[1])
        if kind == "Polygon" and coords and coords[0]:
            ring = coords[0][:-1] or coords[0]
            return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
    return None


def district_of(geometry, path: Path = GEOFENCE_PATH):
    """id района или None (нет геометрии, точка вне полигонов, нет файла)."""
    point = representative_point(geometry)
    if point is None:
        return None
    lon, lat = point
    for district, ring, (min_lon, min_lat, max_lon, max_lat) in _load(path):
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat and _inside(lon, lat, ring):
            return district
    return None


def geometry_bbox(geometry):
    """(min_lon, min_lat, max_lon, max_lat) геометрии или None."""
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    kind = geometry.get("type")
    points = []
    try:
        if kind == "Point":
            points = [coords]
        elif kind == "LineString":
            points = coords
        elif kind == "Polygon":
            points = [p for ring in coords for p in ring]
        if not points:
            return None
        lons = [float(p[0]) for p in points]
        lats = [float(p[1]) for p in points]
    except (TypeError, ValueError, IndexError):
        return None
    return min(lons), min(lats), max(lons), max(lats)


def bbox_intersects(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
