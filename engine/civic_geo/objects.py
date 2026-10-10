"""Объекты OSM (остановки, площадки, парки, места для мусора), дворы и ячейки ~150 м.

Файлы (собирает build_geo_data.py):
    data/civic/astana/geo/objects.json — точечные/площадные объекты OSM: id, kind, имя ru/kk, point, [polygon]
    data/civic/astana/geo/yards.json   — дворы: полигоны landuse=residential (упрощённые)
    data/civic/astana/geo/cells.json   — параметры сетки ячеек (для мест, где двора нет)
Нет файла — пустой набор (честно: «объектов рядом нет»), а не выдуманные объекты.
"""
from __future__ import annotations

import json
import math
import re
import threading
from pathlib import Path

from . import geo
from .graph import GridIndex
from .paths import GEO_DIR

# Сетка ячеек ~150 м — ОДНА на весь раунд: те же константы, что в ui/civic_heat/geo.py у R07
# (CELL_ORIGIN, CELL_LAT0, CELL_DLON = 150 / (111320·cos 51.15°), CELL_DLAT = 150 / 110574), чтобы id cell-<ix>-<iy>
# из /targets и с тепловой карты означали один и тот же квадрат. Меняется только вместе с R07.
DEFAULT_CELLS = {
    "schema": "r12-cells-v2",
    "origin": [71.0, 50.8],
    "cell_m": 150,
    "ref_lat": 51.15,
    "m_per_deg_lat": 110574.0,
    "m_per_deg_lon_equator": 111320.0,
}


class Feature:
    __slots__ = ("id", "kind", "name_ru", "name_kk", "point", "polygon", "bbox", "raw")

    def __init__(self, raw: dict):
        self.raw = raw
        self.id = raw["id"]
        self.kind = raw.get("kind")
        self.name_ru = raw.get("name_ru")
        self.name_kk = raw.get("name_kk")
        poly = raw.get("polygon")
        self.polygon = poly if poly else None
        self.point = raw.get("point") or (geo.bbox_center(poly[0]) if poly else None)
        coords = poly[0] if poly else [self.point]
        self.bbox = geo.bbox_of(coords)

    def distance_m(self, p) -> float:
        if self.polygon:
            return geo.distance_to_polygon_m(p, self.polygon)
        return geo.haversine_m(p, self.point)

    def contains(self, p) -> bool:
        return bool(self.polygon) and geo.point_in_polygon(p, self.polygon)


class FeatureSet:
    def __init__(self, items: list[dict], meta: dict | None = None):
        self.meta = meta or {}
        self.items = [Feature(r) for r in items]
        self.by_id = {f.id: f for f in self.items}
        self.index = GridIndex(((i, f.bbox) for i, f in enumerate(self.items)), 51.14, cell_m=150.0)

    def near(self, p, radius_m: float, kinds=None) -> list[tuple[float, Feature]]:
        out = []
        for i in self.index.around(p[0], p[1], radius_m):
            f = self.items[i]
            if kinds and f.kind not in kinds:
                continue
            d = f.distance_m(p)
            if d <= radius_m:
                out.append((d, f))
        out.sort(key=lambda r: (r[0], r[1].id))
        return out

    def containing(self, p) -> list[Feature]:
        """Полигоны, внутри которых точка (самый маленький — первым: это и есть «двор»)."""
        hits = [self.items[i] for i in self.index.around(p[0], p[1], 0.0) if self.items[i].contains(p)]
        hits.sort(key=lambda f: ((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), f.id))
        return hits


class Cells:
    """Квадратная сетка ~150 м: id ячейки cell-<ix>-<iy>, считается одинаково в Python и JS."""

    def __init__(self, params: dict | None = None):
        p = dict(DEFAULT_CELLS)
        p.update(params or {})
        self.params = p
        self.lon0, self.lat0 = p["origin"]
        self.dlat = p["cell_m"] / p["m_per_deg_lat"]
        self.dlon = p["cell_m"] / (p["m_per_deg_lon_equator"] * math.cos(math.radians(p["ref_lat"])))

    def cell_id(self, p) -> str:
        ix = math.floor((p[0] - self.lon0) / self.dlon)
        iy = math.floor((p[1] - self.lat0) / self.dlat)
        return f"cell-{ix}-{iy}"

    def polygon(self, cell_id: str) -> list[list[list[float]]]:
        m = re.match(r"^cell-(-?\d+)-(-?\d+)$", cell_id or "")
        if not m:
            raise ValueError("неверный id ячейки")
        ix, iy = int(m.group(1)), int(m.group(2))
        w, s = self.lon0 + ix * self.dlon, self.lat0 + iy * self.dlat
        e, n = w + self.dlon, s + self.dlat
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        return [[geo.round_coord(c, 6) for c in ring]]  # 6 знаков — как у R07

    def center(self, cell_id: str) -> list[float]:
        ring = self.polygon(cell_id)[0]
        return geo.round_coord([(ring[0][0] + ring[2][0]) / 2, (ring[0][1] + ring[2][1]) / 2])


def _read(path: Path) -> dict | None:
    return json.loads(path.read_text("utf-8")) if path.is_file() else None


_lock = threading.Lock()
_cache: dict[str, tuple] = {}


def get_layers(geo_dir: Path | None = None) -> tuple[FeatureSet, FeatureSet, Cells]:
    """(объекты, дворы, ячейки) из data/civic/astana/geo/ — с кэшем процесса."""
    d = Path(geo_dir) if geo_dir else GEO_DIR
    key = str(d.resolve())
    with _lock:
        if key not in _cache:
            objects = _read(d / "objects.json") or {"items": []}
            yards = _read(d / "yards.json") or {"items": []}
            cells = _read(d / "cells.json")
            _cache[key] = (FeatureSet(objects["items"], objects), FeatureSet(yards["items"], yards), Cells(cells))
        return _cache[key]


def clear_cache():
    with _lock:
        _cache.clear()
