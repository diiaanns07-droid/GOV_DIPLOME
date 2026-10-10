"""Привязка точки пользователя к пешеходной сети графа (round 13).

Человек указывает место на карте, а расчёт идёт между узлами графа. Правила:
  * кандидаты — только узлы, инцидентные ребру с access=allowed (unknown не считается доступным);
  * берётся ближайший по гаверсинусу узел; ничья — по ID узла;
  * дальше порога (по умолчанию 150 м) — отказ too_far, без «переноса» на далёкую улицу;
  * точка вне bbox выгрузки — отказ outside_graph (фон карты вне графа расчёта не означает);
  * сообщаются: расстояние до найденного узла, ближе ли линия с неизвестным/запрещённым доступом,
    размер компоненты связности (по allowed-рёбрам без учёта направления) и главная ли она;
  если узел во фрагменте, а узел основной сети есть в пределах порога, он даётся как альтернатива
  (main_alternative) — выбрать её может только пользователь.
Отрезок от точки до узла — подход, он НЕ входит в длину маршрута и не проверен как путь (может
пересекать реку или ограду). Та же логика повторена в web/civic/scenarios/scenarios.js (snapPoint).
"""
import math

from .errors import ScenarioError

SNAP_MAX_M = 150.0
SEARCH_MAX_M = 1000.0
CELL_DEG_LAT = 0.002          # ~222 м по широте
R_EARTH = 6371008.8


def haversine_m(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * R_EARTH * math.asin(min(1.0, math.sqrt(h)))


class SnapIndex:
    """Сетка узлов (allowed и прочих) + компоненты связности allowed-рёбер. Строится один раз на граф."""

    def __init__(self, pg):
        lats = [c[1] for c in pg.coords.values()] or [0.0]
        mid = sum(lats) / len(lats)
        self.cell_lat = CELL_DEG_LAT
        self.cell_lon = CELL_DEG_LAT / max(0.2, math.cos(math.radians(mid)))
        allowed_nodes, other_nodes = set(), set()
        parent = {}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for frm, to, _mm, access, _oneway in pg.edges.values():
            if access == "allowed":
                allowed_nodes.update((frm, to))
                parent.setdefault(frm, frm)
                parent.setdefault(to, to)
                a, b = find(frm), find(to)
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                other_nodes.update((frm, to))
        size = {}
        for frm, to, _mm, access, _oneway in pg.edges.values():
            if access == "allowed":
                r = find(frm)
                size[r] = size.get(r, 0) + 1
        self.component = {n: find(n) for n in allowed_nodes}
        self.component_edges = size
        self.main_component = max(size, key=lambda r: (size[r], r)) if size else None
        self.allowed = self._grid(pg, allowed_nodes)
        self.main = self._grid(pg, {n for n, r in self.component.items() if r == self.main_component})
        self.other = self._grid(pg, other_nodes - allowed_nodes)
        self.coords = pg.coords

    def _key(self, lon, lat):
        return (math.floor(lon / self.cell_lon), math.floor(lat / self.cell_lat))

    def _grid(self, pg, nodes):
        grid = {}
        for n in sorted(nodes):
            lon, lat = pg.coords[n]
            grid.setdefault(self._key(lon, lat), []).append(n)
        return grid

    def nearest(self, grid, lon, lat, limit_m):
        cx, cy = self._key(lon, lat)
        rings = int(math.ceil(limit_m / (self.cell_lat * 111_000))) + 1
        best = None
        for dx in range(-rings, rings + 1):
            for dy in range(-rings, rings + 1):
                for n in grid.get((cx + dx, cy + dy), ()):
                    d = haversine_m((lon, lat), self.coords[n])
                    if d <= limit_m and (best is None or (d, n) < best):
                        best = (d, n)
        return best


def snap_index(pg):
    if pg._snap_cache is None:
        pg._snap_cache = SnapIndex(pg)
    return pg._snap_cache


def snap_point(pg, lon, lat, *, max_m=SNAP_MAX_M):
    """Результат привязки одной точки [lon, lat] (WGS84). Не бросает исключений для «плохого места»."""
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lon, lat, max_m)):
        raise ScenarioError("invalid_payload", "lon/lat/max_m — конечные числа")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90) or not 1 <= max_m <= SEARCH_MAX_M:
        raise ScenarioError("invalid_payload", "координаты WGS84 и порог 1–1000 м")
    out = {"input": [lon, lat], "max_m": max_m, "status": None, "node_id": None, "node": None, "distance_m": None,
           "nearest_allowed_m": None, "nearer_unverified_m": None, "component_edges": None, "main_component": None,
           "main_alternative": None}
    if pg.bbox and not (pg.bbox[0] <= lon <= pg.bbox[2] and pg.bbox[1] <= lat <= pg.bbox[3]):
        out["status"] = "outside_graph"
        return out
    idx = snap_index(pg)
    best = idx.nearest(idx.allowed, lon, lat, SEARCH_MAX_M)
    other = idx.nearest(idx.other, lon, lat, best[0] if best else SEARCH_MAX_M)
    if other is not None and (best is None or other[0] < best[0]):
        out["nearer_unverified_m"] = round(other[0], 1)
    if best is None:
        out["status"] = "too_far"
        return out
    out["nearest_allowed_m"] = round(best[0], 1)
    if best[0] > max_m:
        out["status"] = "too_far"
        return out
    node = best[1]
    comp = idx.component[node]
    out.update(status="ok", node_id=node, node=list(pg.coords[node]), distance_m=round(best[0], 1),
               component_edges=idx.component_edges[comp], main_component=comp == idx.main_component)
    if not out["main_component"]:
        # Ближайший узел — во фрагменте, не связанном с основной сетью модели. Узел основной сети
        # в пределах порога предлагается как ЯВНЫЙ выбор пользователя, а не подставляется молча.
        alt = idx.nearest(idx.main, lon, lat, max_m)
        if alt is not None:
            out["main_alternative"] = {"node_id": alt[1], "node": list(pg.coords[alt[1]]), "distance_m": round(alt[0], 1)}
    return out
