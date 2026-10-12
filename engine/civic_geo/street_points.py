"""Светофоры, пешеходные переходы и перекрёстки как цели жалобы (POLISH_WAVE п. 1).

- Светофор (highway=traffic_signals) и переход (highway=crossing) — настоящие узлы OSM. Их координаты не меняем;
  к ним добавляем улицы, на которых они стоят (из рёбер графа в этом узле), — для подписи.
- Перекрёсток — узел графа улиц, где сходятся ≥ 3 рёбра проезжей части (тип дороги из way_tags) с ≥ 2 разными
  названиями. «≥ 3 разных улицы» в задании понимаем так: ≥ 3 ветки дорог в узле (обычный крест двух улиц — 4 ветки
  и 2 названия). У проспекта с разделительной полосой одна развязка — это 2–4 узла графа; узлы с той же парой улиц
  ближе CLUSTER_M склеиваем в один перекрёсток. Его точка — настоящий узел OSM, ближайший к центру группы,
  id — osm-node-<id> (формат, который принимают R09 и R07).
"""
from __future__ import annotations

import math
from collections import Counter

from . import geo, names
from .graph import StreetGraph

CLUSTER_M = 60.0           # узлы одной развязки (двойные проспекты, съезды)
SIGNAL_TO_JUNCTION_M = 60.0  # светофор «на подходе» относится к перекрёстку не дальше 60 м
ON_STREET_M = 15.0           # светофор/переход дальше 15 м от улиц графа — не на открытой улице
NEAR_STREET_M = 150.0        # без своей улицы — подпись по ближайшей улице с названием (как у безымянного участка)
NODE_PREFIX = "osm-n"


def osm_node_id(graph_node_id: str) -> str:
    """'osm-n12345' -> 'osm-node-12345'."""
    return "osm-node-" + graph_node_id[len(NODE_PREFIX):]


def graph_node_id(osm_id: str) -> str | None:
    return NODE_PREFIX + osm_id[len("osm-node-"):] if osm_id.startswith("osm-node-") else None


def node_streets(graph: StreetGraph, node: str, groups=("road",)) -> tuple[list[str], list[str | None], int]:
    """Названия улиц в узле (сначала самая частая), их kk-имена и число рёбер нужных групп."""
    counts: Counter = Counter()
    kk: dict = {}
    degree = 0
    for idx in graph.adj.get(node, ()):
        e = graph.edges[idx]
        if groups and e.group not in groups:
            continue
        degree += 1
        if e.name:
            counts[e.name] += 1
            kk.setdefault(e.name, e.name_kk)
    ordered = sorted(counts, key=lambda n: (-counts[n], n))
    return ordered, [kk.get(n) for n in ordered], degree


def find_intersections(graph: StreetGraph, inside=None) -> list[dict]:
    """Перекрёстки города: [{id, kind, node, point, streets_ru, streets_kk, nodes}] (inside(point) — фильтр границы)."""
    cands = []
    for node, (lon, lat) in graph.nodes.items():
        streets, streets_kk, degree = node_streets(graph, node)
        if degree >= 3 and len(streets) >= 2:
            cands.append({"node": node, "point": (lon, lat), "pair": tuple(sorted(streets[:2])),
                          "streets": streets[:2],
                          "streets_kk": [names.kk_street(n, k) for n, k in zip(streets[:2], streets_kk[:2])]})
    # Склейка: узлы с той же парой улиц ближе CLUSTER_M — одна развязка (жадно, в порядке id: результат стабилен).
    by_pair: dict = {}
    for c in sorted(cands, key=lambda c: c["node"]):
        by_pair.setdefault(c["pair"], []).append(c)
    out = []
    for pair, group in by_pair.items():
        clusters: list[list[dict]] = []
        for c in group:
            for cl in clusters:
                if any(geo.haversine_m(c["point"], o["point"]) <= CLUSTER_M for o in cl):
                    cl.append(c)
                    break
            else:
                clusters.append([c])
        for cl in clusters:
            cx = sum(c["point"][0] for c in cl) / len(cl)
            cy = sum(c["point"][1] for c in cl) / len(cl)
            rep = min(cl, key=lambda c: (geo.haversine_m(c["point"], (cx, cy)), c["node"]))
            if inside is not None and not inside(rep["point"]):
                continue
            out.append({"node": rep["node"], "point": rep["point"], "streets": rep["streets"],
                        "streets_kk": rep["streets_kk"], "nodes": sorted(c["node"] for c in cl)})
    out.sort(key=lambda x: x["node"])
    return out


class _PointIndex:
    """Сетка 100 м для поиска ближайшего перекрёстка у светофора."""

    def __init__(self, items: list[dict]):
        self.items = items
        self.k = 100.0 / geo.M_PER_DEG
        self.cells: dict = {}
        for i, it in enumerate(items):
            self.cells.setdefault(self._key(it["point"]), []).append(i)

    def _key(self, p):
        return (math.floor(p[0] / (self.k * 1.6)), math.floor(p[1] / self.k))

    def nearest(self, p, radius_m: float):
        kx, ky = self._key(p)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in self.cells.get((kx + dx, ky + dy), ()):
                    d = geo.haversine_m(p, self.items[i]["point"])
                    if d <= radius_m and (best is None or d < best[0]):
                        best = (d, self.items[i])
        return best


def annotate(obj: dict, graph: StreetGraph, junctions: _PointIndex | None = None) -> dict:
    """Добавляет светофору/переходу streets_ru/streets_kk: улицы в его узле (или ближайшая улица) и перекрёсток рядом."""
    node = graph_node_id(obj["id"])
    streets, streets_kk = [], []
    if node and node in graph.adj:
        streets, streets_kk, _ = node_streets(graph, node)
        if not streets:  # узел только на дорожках/проездах — берём любые названия
            streets, streets_kk, _ = node_streets(graph, node, groups=None)
    if not streets:
        near = graph.nearest(obj["point"], 40.0, limit=1, accept=lambda e: bool(e.name) and e.group == "road")
        if near:
            e = near[0][1]
            streets, streets_kk = [e.name], [e.name_kk]
    if obj["kind"] == "traffic_signal" and len(streets) < 2 and junctions is not None:
        j = junctions.nearest(obj["point"], SIGNAL_TO_JUNCTION_M)
        if j:  # светофор на подходе к перекрёстку — подписываем перекрёстком
            streets, streets_kk = list(j[1]["streets"]), list(j[1]["streets_kk"])
            obj["junction"] = osm_node_id(j[1]["node"])
    obj["streets_ru"] = streets[:2]
    obj["streets_kk"] = [names.kk_street(n, k) for n, k in zip(streets[:2], streets_kk[:2])]
    obj.pop("near_ru", None)
    obj.pop("near_kk", None)
    if not streets:  # переход на дворовом проезде: «… у улицы X» по ближайшей улице с названием (как безымянный участок)
        near = graph.nearest(obj["point"], NEAR_STREET_M, limit=1, accept=lambda e: bool(e.name))
        if near:
            e = near[0][1]
            obj["near_ru"], obj["near_kk"] = e.name, names.kk_street(e.name, e.name_kk)
    return obj


def labels(obj: dict) -> tuple[str, str]:
    s_ru, s_kk = obj.get("streets_ru") or [], obj.get("streets_kk") or []
    if obj["kind"] == "intersection":
        ru, kk = names.intersection_labels(s_ru, s_kk)
    elif obj["kind"] == "traffic_signal":
        ru, kk = names.signal_labels(s_ru, s_kk)
    else:
        ru, kk = names.crossing_labels(s_ru, s_kk, signals=obj.get("subkind") == "signals")
    if not s_ru:  # голое «Пешеходный переход» в списке «Это здесь?» ничего не говорит
        ru, kk = names.near_labels(ru, kk, obj.get("near_ru"), obj.get("near_kk"))
    return ru, kk


def build_street_points(objects: dict, graph: StreetGraph, inside) -> dict:
    """Дополняет objects (id -> запись) перекрёстками и подписывает светофоры/переходы. Возвращает счётчики."""
    junctions = find_intersections(graph, inside)
    index = _PointIndex(junctions)
    # Светофор/переход не на улице графа (например, на дороге в статусе «строится», highway=construction) —
    # не цель для жалобы: убираем (тот же допуск 15 м, что в отчёте точности).
    off_street = [oid for oid, o in objects.items() if o["kind"] in ("traffic_signal", "crossing")
                  and not graph.nearest(o["point"], ON_STREET_M, limit=1)]
    for oid in off_street:
        del objects[oid]
    for obj in objects.values():
        if obj["kind"] in ("traffic_signal", "crossing"):
            annotate(obj, graph, index)
            # у светофора/перехода имени в OSM почти никогда нет — пустые поля не храним (файл меньше)
            for k in ("name_ru", "name_kk"):
                if obj.get(k) is None:
                    obj.pop(k, None)
    added = merged = 0
    for j in junctions:
        oid = osm_node_id(j["node"])
        if oid in objects:
            # В узле развязки уже стоит светофор OSM: один объект — светофор с подписью перекрёстка.
            objects[oid]["streets_ru"], objects[oid]["streets_kk"] = list(j["streets"]), \
                [names.kk_street(n, k) for n, k in zip(j["streets"], j["streets_kk"])]
            objects[oid]["junction"] = oid
            merged += 1
            continue
        objects[oid] = {"id": oid, "kind": "intersection", "point": geo.round_coord(j["point"]),
                        "streets_ru": list(j["streets"]),
                        "streets_kk": [names.kk_street(n, k) for n, k in zip(j["streets"], j["streets_kk"])],
                        "graph_nodes": len(j["nodes"]), "src": "graph"}
        added += 1
    return {"intersections": added, "intersections_on_signal_nodes": merged, "off_street_dropped": len(off_street)}
