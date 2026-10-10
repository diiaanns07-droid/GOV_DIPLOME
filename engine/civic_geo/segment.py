"""Участок улицы между двумя точками — только по рёбрам графа OSM (CONTRACT §8.1: никаких линий «от руки»).

Алгоритм:
1. Каждая точка «прилипает» к ближайшему ребру (не дальше snap_radius_m) — проекция на ось улицы.
2. Если обе точки на одном ребре — берём кусок этого ребра между проекциями.
3. Иначе — кратчайший путь (Дейкстра) между проекциями. Чтобы участок шёл по одной улице,
   рёбра с другим названием стоят дороже (NAME_PENALTY), а путь ограничен по длине.
4. Геометрия = части крайних рёбер + целые рёбра между ними, вершины берутся из OSM без изменений.
"""
from __future__ import annotations

import heapq
from typing import Callable, Sequence

from . import geo
from .graph import Edge, StreetGraph

NAME_PENALTY = 3.0      # во сколько раз дороже ребро с другим названием, если участок «по одной улице»
GROUP_PENALTY = 1.6     # во сколько раз дороже тротуар для участка дороги и наоборот
MAX_SEGMENT_M = 6000.0  # участок длиннее 6 км — скорее ошибка выбора концов
DEFAULT_SNAP_M = 60.0   # дальше 60 м от улицы точку не «прилепляем»


class GeoError(ValueError):
    """Ошибка с кодом для API и понятным текстом для человека."""
    status = 400  # шлюз R01 отвечает этим кодом

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _group_filter(groups: Sequence[str] | None) -> Callable[[Edge], bool] | None:
    if not groups:
        return None
    allowed = set(groups) | {"unknown"}
    return lambda e: e.group in allowed


def snap(graph: StreetGraph, p, radius_m: float = DEFAULT_SNAP_M, groups: Sequence[str] | None = None,
         limit: int = 8):
    """Кандидаты привязки точки к улице. Сначала — рёбра нужных групп; если их нет рядом — любые."""
    found = graph.nearest(p, radius_m, accept=_group_filter(groups))
    if not found and groups:
        found = graph.nearest(p, radius_m)
    # Щелчок «по улице» чаще значит главную улицу, а не безымянный проезд рядом: небольшой штраф в метрах.
    found.sort(key=lambda r: (r[0] + _snap_penalty(r[1], groups), r[1].id))
    return found[:limit]


def _snap_penalty(e: Edge, groups) -> float:
    if not groups:
        return 0.0
    pen = groups.index(e.group) * 8.0 if e.group in groups else 0.0
    return pen + (0.0 if e.name else 4.0)


def _choose_pair(cands_a, cands_b):
    """Пара рёбер для концов: ближе к щелчкам и, если можно, с одним названием улицы."""
    best = None
    for da, ea, pa in cands_a[:6]:
        for db, eb, pb in cands_b[:6]:
            same = bool(ea.name) and ea.name == eb.name
            score = da + db + (0.0 if same or ea is eb else 15.0)
            if best is None or score < best[0]:
                best = (score, (da, ea, pa), (db, eb, pb))
    return best[1], best[2]


def _weight(edge: Edge, street: str | None, group: str | None) -> float:
    w = edge.length_m
    if street is not None and edge.name != street:
        w *= NAME_PENALTY
    if group in ("road", "foot") and edge.group not in (group, "unknown"):
        w *= GROUP_PENALTY
    return w


def street_segment(graph: StreetGraph, a, b, snap_radius_m: float = DEFAULT_SNAP_M,
                   groups: Sequence[str] | None = None) -> dict:
    """Участок улицы от точки a до точки b ([lon, lat]) по форме OSM."""
    cands_a = snap(graph, a, snap_radius_m, groups)
    cands_b = snap(graph, b, snap_radius_m, groups)
    if not cands_a or not cands_b:
        raise GeoError("not_on_street", f"Точка дальше {int(snap_radius_m)} м от улицы. Нажмите ближе к улице.")
    (da, ea, pa), (db, eb, pb) = _choose_pair(cands_a, cands_b)
    if geo.haversine_m(pa.point, pb.point) < 3.0:
        raise GeoError("too_short", "Начало и конец участка совпадают. Нажмите на другой конец участка.")

    if ea is eb:
        # Обе точки на одном ребре — кусок ребра между проекциями.
        coords = geo.cut_polyline(ea.geometry, pa.along_m, pb.along_m)
        pieces = [(ea, pa.along_m, pb.along_m)]
    else:
        street = ea.name if ea.name and ea.name == eb.name else None
        group = ea.group if ea.group == eb.group else None
        straight = geo.haversine_m(pa.point, pb.point)
        limit = min(MAX_SEGMENT_M, 3.0 * straight + 400.0)
        path = _dijkstra(graph, ea, pa, eb, pb, street, group, limit)
        if path is None:
            raise GeoError("no_path", "Между этими точками нет связанного участка улицы. Выберите точки на одной улице.")
        exit_node, middle, entry_node = path
        pieces = [(ea, pa.along_m, 0.0 if exit_node == ea.a else ea.length_m)]
        coords = geo.cut_polyline(ea.geometry, pa.along_m, pieces[0][2])
        node = exit_node
        for e in middle:
            pieces.append((e, 0.0, e.length_m) if node == e.a else (e, e.length_m, 0.0))
            coords.extend([list(c) for c in graph.oriented(e, node)])
            node = graph.other_end(e, node)
        start_last = 0.0 if entry_node == eb.a else eb.length_m
        pieces.append((eb, start_last, pb.along_m))
        coords.extend(geo.cut_polyline(eb.geometry, start_last, pb.along_m))
        coords = geo.dedupe(coords)

    length = geo.polyline_length_m(coords)
    if length > MAX_SEGMENT_M:
        raise GeoError("too_long", "Участок длиннее 6 км. Выберите концы ближе друг к другу.")
    names = []
    for e, _, _ in pieces:
        if e.name and e.name not in names:
            names.append(e.name)
    first_named = next((e for e, _, _ in pieces if e.name), None)
    return {
        "geometry": {"type": "LineString", "coordinates": [geo.round_coord(c) for c in coords]},
        "edge_ids": [e.id for e, _, _ in pieces],
        "pieces": [{"edge_id": e.id, "from_m": round(s, 2), "to_m": round(t, 2)} for e, s, t in pieces],
        "length_m": round(length, 1),
        "names": names,
        "street_ru": names[0] if len(names) == 1 else (first_named.name if first_named else None),
        "street_kk": first_named.label_kk() if first_named else None,
        "same_street": len(names) == 1 and all(e.name == names[0] for e, _, _ in pieces),
        "from": {"edge_id": ea.id, "snap_m": round(da, 1), "point": geo.round_coord(pa.point)},
        "to": {"edge_id": eb.id, "snap_m": round(db, 1), "point": geo.round_coord(pb.point)},
    }


def _dijkstra(graph: StreetGraph, ea: Edge, pa, eb: Edge, pb, street, group, limit_m):
    """Путь от проекции на ea до проекции на eb: (узел выхода с ea, рёбра между, узел входа на eb)."""
    # Стартовые узлы: концы первого ребра, стоимость — остаток ребра от проекции.
    dist: dict[str, float] = {}
    real: dict[str, float] = {}   # настоящая длина в метрах (для ограничения длины)
    prev: dict[str, tuple[str | None, int | None]] = {}
    heap: list[tuple[float, str]] = []
    w_ea = _weight(ea, street, group) / max(ea.length_m, 1e-9)
    for node, part in ((ea.a, pa.along_m), (ea.b, ea.length_m - pa.along_m)):
        c = part * w_ea
        if c < dist.get(node, float("inf")):
            dist[node] = c
            real[node] = part
            prev[node] = (None, None)
            heapq.heappush(heap, (c, node))
    w_eb = _weight(eb, street, group) / max(eb.length_m, 1e-9)
    targets = {eb.a: pb.along_m * w_eb, eb.b: (eb.length_m - pb.along_m) * w_eb}
    best_total, best_node = float("inf"), None
    while heap:
        c, node = heapq.heappop(heap)
        if c > dist.get(node, float("inf")) or c >= best_total:
            continue
        if node in targets and c + targets[node] < best_total:
            best_total, best_node = c + targets[node], node
        for idx in graph.adj.get(node, ()):
            e = graph.edges[idx]
            if e is ea or e is eb:
                continue
            nxt = graph.other_end(e, node)
            r = real[node] + e.length_m
            if r > limit_m:
                continue
            nc = c + _weight(e, street, group)
            if nc < dist.get(nxt, float("inf")):
                dist[nxt] = nc
                real[nxt] = r
                prev[nxt] = (node, idx)
                heapq.heappush(heap, (nc, nxt))
    if best_node is None:
        return None
    middle: list[Edge] = []
    node = best_node
    while prev[node][0] is not None:
        p_node, idx = prev[node]
        middle.append(graph.edges[idx])
        node = p_node
    middle.reverse()
    return node, middle, best_node


def snap_polyline(graph: StreetGraph, coords, snap_radius_m: float = DEFAULT_SNAP_M,
                  groups: Sequence[str] | None = None) -> dict:
    """Привязка нарисованной от руки линии: участок по улице через все её вершины по порядку."""
    if len(coords) < 2:
        raise GeoError("too_short", "У линии меньше двух точек.")
    parts = [street_segment(graph, coords[i], coords[i + 1], snap_radius_m, groups) for i in range(len(coords) - 1)]
    out_coords: list = []
    edge_ids: list[str] = []
    pieces: list[dict] = []
    names: list[str] = []
    for part in parts:
        out_coords.extend(part["geometry"]["coordinates"])
        for eid in part["edge_ids"]:
            if not edge_ids or edge_ids[-1] != eid:
                edge_ids.append(eid)
        pieces.extend(part["pieces"])
        for n in part["names"]:
            if n not in names:
                names.append(n)
    out_coords = [geo.round_coord(c) for c in geo.dedupe(out_coords)]
    return {
        "geometry": {"type": "LineString", "coordinates": out_coords},
        "edge_ids": edge_ids,
        "pieces": pieces,
        "length_m": round(geo.polyline_length_m(out_coords), 1),
        "names": names,
        "street_ru": parts[0]["street_ru"],
        "street_kk": parts[0]["street_kk"],
        "same_street": len(names) == 1 and all(p["same_street"] for p in parts),
        "max_snap_m": max(max(p["from"]["snap_m"], p["to"]["snap_m"]) for p in parts),
    }
