"""Рёбра пешеходного графа OSM с настоящей формой улиц и сеточный пространственный индекс.

Граф только читается: engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json
(94 089 рёбер, у каждого — геометрия OSM). Файл сверяется с file_sha256 из MANIFEST.json рядом с ним.

Тип дороги (highway) и казахское название в граф не входят; их даёт небольшая таблица
data/civic/astana/geo/way_tags.json, собранная из того же снимка OSM (build_way_tags.py).
Без неё всё работает, только без предпочтения «проезжая часть / тротуар».
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from pathlib import Path
from typing import Callable, Iterable

from . import geo
from .paths import GRAPH_ID, GRAPHS_DIR, GEO_DIR

# Группы типов дорог OSM (ключ highway), чтобы предлагать «улицу» для жалобы на дорогу
# и «тротуар» для жалобы на тротуар.
ROAD_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
    "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street",
    "road", "busway",
}
SERVICE_CLASSES = {"service", "services", "rest_area", "track"}
FOOT_CLASSES = {"footway", "path", "pedestrian", "steps", "cycleway", "corridor", "elevator", "bridleway"}

KAZAKH_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")


def street_group(highway: str | None) -> str:
    """road — проезжая часть, service — проезды во дворах, foot — тротуары и дорожки, other/unknown."""
    if highway is None:
        return "unknown"
    if highway in ROAD_CLASSES:
        return "road"
    if highway in SERVICE_CLASSES:
        return "service"
    if highway in FOOT_CLASSES:
        return "foot"
    return "other"


class Edge:
    __slots__ = ("idx", "id", "a", "b", "name", "name_kk", "geometry", "length_m", "way_id", "access",
                 "highway", "sidewalk", "group", "bbox")

    def __init__(self, idx: int, raw: dict, tags: list | None):
        self.idx = idx
        self.id = raw["id"]
        self.a = raw["from"]
        self.b = raw["to"]
        self.name = raw.get("name") or None
        self.geometry = [(float(p[0]), float(p[1])) for p in raw["geometry"]]
        self.length_m = float(raw.get("length_m") or geo.polyline_length_m(self.geometry))
        self.way_id = raw.get("osm_way_id")
        self.access = raw.get("access")
        self.highway = tags[0] if tags else None
        self.name_kk = tags[1] if tags and len(tags) > 1 else None
        self.sidewalk = bool(tags[2]) if tags and len(tags) > 2 else False
        self.group = street_group(self.highway)
        self.bbox = geo.bbox_of(self.geometry)

    def label_ru(self) -> str | None:
        return self.name

    def label_kk(self) -> str | None:
        """Казахское название, если оно есть в OSM; иначе — то же, что по-русски."""
        return self.name_kk or self.name


class GridIndex:
    """Сетка ~cell_m метров: в ячейке — номера рёбер, чей охватывающий прямоугольник её задевает.

    Поиск ближайшего: берём ячейки в радиусе и считаем точное расстояние до ломаной
    только для рёбер из этих ячеек (обычно десятки рёбер вместо 94 тысяч).
    """

    def __init__(self, items: Iterable[tuple[int, list[float]]], center_lat: float, cell_m: float = 100.0):
        self.cell_m = cell_m
        self.dlat = cell_m / geo.M_PER_DEG
        self.dlon = cell_m / (geo.M_PER_DEG * math.cos(math.radians(center_lat)))
        self.cells: dict[tuple[int, int], list[int]] = {}
        for idx, bb in items:
            x0, y0 = self.key(bb[0], bb[1])
            x1, y1 = self.key(bb[2], bb[3])
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    self.cells.setdefault((x, y), []).append(idx)

    def key(self, lon: float, lat: float) -> tuple[int, int]:
        return (math.floor(lon / self.dlon), math.floor(lat / self.dlat))

    def around(self, lon: float, lat: float, radius_m: float) -> set[int]:
        """Номера объектов из ячеек, покрывающих круг radius_m вокруг точки (с запасом)."""
        r = int(math.ceil(radius_m / self.cell_m))
        cx, cy = self.key(lon, lat)
        found: set[int] = set()
        for x in range(cx - r, cx + r + 1):
            for y in range(cy - r, cy + r + 1):
                bucket = self.cells.get((x, y))
                if bucket:
                    found.update(bucket)
        return found


class StreetGraph:
    def __init__(self, raw: dict, way_tags: dict | None = None):
        self.id = raw.get("id")
        self.digest = raw.get("digest")
        self.bbox = raw.get("bbox")
        self.license = raw.get("license")
        self.snapshot_at = (raw.get("source") or {}).get("snapshot_at")
        tags = (way_tags or {}).get("ways") or {}
        classes = (way_tags or {}).get("classes") or []
        self.edges: list[Edge] = []
        self.by_id: dict[str, Edge] = {}
        for i, e in enumerate(raw["edges"]):
            t = tags.get(str(e.get("osm_way_id")))
            if t is not None:
                t = [classes[t[0]] if isinstance(t[0], int) and t[0] < len(classes) else None] + list(t[1:])
            edge = Edge(i, e, t)
            self.edges.append(edge)
            self.by_id[edge.id] = edge
        self.nodes: dict[str, tuple[float, float]] = {n["id"]: (float(n["lon"]), float(n["lat"])) for n in raw["nodes"]}
        self.adj: dict[str, list[int]] = {}
        for edge in self.edges:
            self.adj.setdefault(edge.a, []).append(edge.idx)
            self.adj.setdefault(edge.b, []).append(edge.idx)
        center_lat = (self.bbox[1] + self.bbox[3]) / 2 if self.bbox else 51.15
        self.index = GridIndex(((e.idx, e.bbox) for e in self.edges), center_lat)
        self.has_tags = bool(tags)

    def nearest(self, p, radius_m: float = 60.0, limit: int | None = None,
                accept: Callable[[Edge], bool] | None = None) -> list[tuple[float, Edge, geo.Projection]]:
        """Рёбра не дальше radius_m от точки p, по возрастанию расстояния: [(метры, ребро, проекция)]."""
        out = []
        for idx in self.index.around(p[0], p[1], radius_m):
            e = self.edges[idx]
            if accept is not None and not accept(e):
                continue
            pr = geo.project_on_polyline(p, e.geometry)
            if pr.distance_m <= radius_m:
                out.append((pr.distance_m, e, pr))
        out.sort(key=lambda r: (r[0], r[1].id))
        return out[:limit] if limit else out

    def other_end(self, edge: Edge, node: str) -> str:
        return edge.b if node == edge.a else edge.a

    def oriented(self, edge: Edge, from_node: str) -> list[tuple[float, float]]:
        """Геометрия ребра в направлении от узла from_node."""
        return edge.geometry if from_node == edge.a else list(reversed(edge.geometry))


_lock = threading.Lock()
_cache: dict[str, StreetGraph] = {}


def _manifest_entry(graph_id: str) -> dict:
    manifest = json.loads((GRAPHS_DIR / "MANIFEST.json").read_text("utf-8"))
    for g in manifest["graphs"]:
        if g["id"] == graph_id:
            return g
    raise KeyError(f"граф {graph_id} не найден в MANIFEST.json")


def load_raw_graph(graph_id: str = GRAPH_ID, path: Path | None = None) -> dict:
    """Читает граф; файл из MANIFEST.json сверяется по sha256 (испорченный файл — ошибка, а не «пустая карта»)."""
    if path is not None:
        return json.loads(Path(path).read_text("utf-8"))
    entry = _manifest_entry(graph_id)
    data = (GRAPHS_DIR / entry["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["file_sha256"]:
        raise ValueError("файл графа изменён относительно MANIFEST.json")
    raw = json.loads(data.decode("utf-8"))
    if raw.get("digest") != entry.get("digest"):
        raise ValueError("digest графа не совпадает с MANIFEST.json")
    return raw


def load_way_tags(path: Path | None = None) -> dict | None:
    p = Path(path) if path else GEO_DIR / "way_tags.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text("utf-8"))


def get_graph(graph_id: str = GRAPH_ID, path: Path | None = None, way_tags_path: Path | None = None) -> StreetGraph:
    """Граф из кэша процесса (первая загрузка Астаны ~2–4 с, дальше — мгновенно)."""
    key = f"{graph_id}|{path}|{way_tags_path}"
    with _lock:
        g = _cache.get(key)
        if g is None:
            g = StreetGraph(load_raw_graph(graph_id, path), load_way_tags(way_tags_path))
            _cache[key] = g
        return g


def has_kazakh_letters(text: str | None) -> bool:
    return bool(text) and any(ch in KAZAKH_LETTERS for ch in text)
