"""Реальные объекты OSM для стенда R09 (data/civic/astana/osm-objects, LOCAL-1, ODbL, только чтение).

Это НЕ модуль R12: стенд использует их, пока R12 /targets не готов, чтобы путь жителя проверялся на
настоящих остановках, площадках и дворах, а не на выдуманных точках. Формат цели — CONTRACT §4:
  object -> osm-node-<id> / osm-way-<id> / osm-relation-<id>;  area (жилой квартал) -> yard-<id> / yard-r<id>.
Геометрия: узел -> Point; замкнутый путь -> Polygon; отношение -> MultiPolygon из сшитых outer-путей
(если внешние пути не сшиваются в кольца — объект пропускается, а не рисуется «как получится»).
"""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RAW = ROOT / "data" / "civic" / "astana" / "osm-objects" / "raw"

# набор -> (вид, подпись ru, подпись kk, «маленький» ли объект-площадь, kind цели)
KINDS = {
    "bus_stops": ("stop", "Остановка", "Аялдама", True, "object"),
    "playgrounds": ("playground", "Детская площадка", "Балалар алаңы", True, "object"),
    "pitches": ("pitch", "Спортплощадка", "Спорт алаңы", True, "object"),
    "gardens": ("garden", "Сквер", "Гүлбақ", True, "object"),
    "parks": ("park", "Парк", "Саябақ", False, "object"),
    "schools": ("school", "Школа", "Мектеп", False, "object"),
    "kindergartens": ("kindergarten", "Детский сад", "Балабақша", False, "object"),
    "waste_disposal": ("waste", "Контейнерная площадка", "Қоқыс алаңы", True, "object"),
    "residential": ("yard", "Двор", "Аула", False, "area"),
}
POINT_RADIUS_M = 60      # точечный объект дальше 60 м от нажатия не предлагаем
EDGE_RADIUS_M = 30       # площадь: нажатие внутри или не дальше 30 м от контура
BIG_AREA_SCORE_M = 40    # нажатие внутри двора/парка уступает остановке в 15 м и улице в 5 м


def _meters(lon1, lat1, lon2, lat2):
    kx = 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 111_320)


def _seg_m(p, a, b):
    kx = 111_320 * math.cos(math.radians(p[1]))
    ax, ay = (a[0] - p[0]) * kx, (a[1] - p[1]) * 111_320
    bx, by = (b[0] - p[0]) * kx, (b[1] - p[1]) * 111_320
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / l2))
    return math.hypot(ax + t * dx, ay + t * dy)


def _inside(p, ring):
    x, y, inside = p[0], p[1], False
    for i in range(len(ring) - 1):
        (x1, y1), (x2, y2) = ring[i], ring[i + 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _stitch(parts):
    """Сшить незамкнутые outer-пути отношения в кольца по совпадающим концам."""
    parts = [list(p) for p in parts if len(p) >= 2]
    rings = []
    while parts:
        ring = parts.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, part in enumerate(parts):
                if part[0] == ring[-1]:
                    ring += part[1:]
                elif part[-1] == ring[-1]:
                    ring += part[::-1][1:]
                elif part[-1] == ring[0]:
                    ring = part[:-1] + ring
                elif part[0] == ring[0]:
                    ring = part[::-1][:-1] + ring
                else:
                    continue
                parts.pop(i)
                changed = True
                break
        if ring[0] != ring[-1] or len(ring) < 4:
            return None
        rings.append(ring)
    return rings


def _geometry(element):
    if element["type"] == "node":
        return {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
    if element["type"] == "way":
        coords = [[g["lon"], g["lat"]] for g in element.get("geometry", []) if g]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return {"type": "Polygon", "coordinates": [coords]}
        return None
    outer = [[[g["lon"], g["lat"]] for g in m.get("geometry", []) if g]
             for m in element.get("members", []) if m.get("type") == "way" and m.get("role") == "outer"]
    rings = _stitch(outer)
    if not rings:
        return None
    return {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}


def _rings(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry["type"] == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    return []


# Казахский порядок: «Нұра» аялдамасы — имя, затем вид в притяжательной форме (-сы/-ы).
KK_NAMED = {"Остановка": "аялдамасы", "Детская площадка": "балалар алаңы", "Спортплощадка": "спорт алаңы",
            "Сквер": "гүлбағы", "Парк": "саябағы", "Контейнерная площадка": "қоқыс алаңы"}


def _labels(kind_ru, kind_kk, tags):
    name = tags.get("name")
    name_kk = tags.get("name:kk") or name
    if not name:
        return kind_ru, kind_kk
    if kind_ru == "Двор":
        return f"Двор: {name}", f"Аула: {name_kk}"
    if kind_ru in ("Школа", "Детский сад"):   # имя уже содержит вид («Школа-лицей №…»)
        return name, name_kk
    return f"{kind_ru} «{name}»", f"«{name_kk}» {KK_NAMED[kind_ru]}"


class OsmObjects:
    def __init__(self, bbox=None):
        self.items = []
        seen = set()
        for dataset, (kind, ru, kk, small, target_kind) in KINDS.items():
            path = RAW / f"{dataset}.json.gz"
            if not path.exists():
                continue
            for element in json.loads(gzip.open(path).read())["elements"]:
                key = (element["type"], element["id"])
                if key in seen:          # один объект может быть в нескольких наборах
                    continue
                geometry = _geometry(element)
                if geometry is None:
                    continue
                if bbox and not self._touches(geometry, bbox):
                    continue
                seen.add(key)
                if target_kind == "area":
                    target_id = f"yard-{element['id']}" if element["type"] == "way" else f"yard-r{element['id']}"
                    if element["type"] == "node":
                        continue      # двор-точка без контура — не область, пропускаем
                else:
                    target_id = f"osm-{element['type']}-{element['id']}"
                label_ru, label_kk = _labels(ru, kk, element.get("tags", {}))
                self.items.append({"kind": kind, "small": small, "geometry": geometry,
                                   "target": {"kind": target_kind, "id": target_id,
                                              "label_ru": label_ru, "label_kk": label_kk}})

    @staticmethod
    def _touches(geometry, bbox):
        lon0, lat0, lon1, lat1 = bbox
        coords = [geometry["coordinates"]] if geometry["type"] == "Point" else \
            [pt for ring in _rings(geometry) for pt in ring]
        return any(lon0 <= x <= lon1 and lat0 <= y <= lat1 for x, y in coords)

    def nearby(self, lon, lat):
        """-> [(score_m, distance_m, item)] — объекты рядом с нажатием."""
        p = (lon, lat)
        found = []
        for item in self.items:
            g = item["geometry"]
            if g["type"] == "Point":
                d = _meters(lon, lat, *g["coordinates"])
                if d <= POINT_RADIUS_M:
                    found.append((d, d, item))
                continue
            rings = _rings(g)
            if any(_inside(p, ring) for ring in rings):
                found.append((0.0 if item["small"] else BIG_AREA_SCORE_M, 0.0, item))
                continue
            d = min(_seg_m(p, r[i], r[i + 1]) for r in rings for i in range(len(r) - 1))
            if d <= EDGE_RADIUS_M:
                found.append((d + (0 if item["small"] else BIG_AREA_SCORE_M), d, item))
        found.sort(key=lambda f: f[0])
        return found

    def geojson(self, kinds=("stop", "playground", "pitch", "yard", "park", "garden")):
        """Слой для подложки стенда (остановки точками, площадки и дворы бледной заливкой)."""
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": i["geometry"], "properties": {"kind": i["kind"]}}
            for i in self.items if i["kind"] in kinds]}
