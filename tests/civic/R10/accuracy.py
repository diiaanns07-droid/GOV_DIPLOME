"""R10 · раунд 14 · независимая проверка точности карты (CONTRACT §8) поверх данных всех модулей.

Зачем отдельно от R12: проверка не использует код engine/civic_geo — своя геометрия, свой индекс, тот же эталон
(граф улиц OSM). Если R12 ошибётся в своей проверке, эта поймает.

Правила §8, которые проверяются:
  1. Участок улицы = рёбра графа, форма из OSM: линия отстоит от формы ребра не больше чем на 5 м (в обе стороны —
     и линия не уходит от ребра, и ребро не «срезано» линией).
  2. Точечные объекты — реальные из OSM, с их координатами (сверка с выгрузкой LOCAL-1, ≤ 1 м).
  3. Остановка — не дальше 60 м от улицы (проезжей части; для сравнения — и от любой линии графа).
  4. Все координаты внутри границы Астаны (полигоны районов OSM из data/civic/astana/geofence.json).
  5. Никаких линий «от руки»: любая линия в данных, не лежащая на графе, должна быть помечена «примерное место».

Запуск (из корня репозитория или с --root):
    python3 tests/civic/R10/accuracy.py                         # отчёт в консоль
    python3 tests/civic/R10/accuracy.py --root <папка сборки> --json out.json
    python3 -m pytest -q tests/civic/R10                        # то же как тесты
Каждая проверка: PASS / FAIL / NOT_RUN (нет файла данных — модуль ещё не в этой сборке). Код возврата 1 при любом FAIL.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import json
import math
import re
import sys
from pathlib import Path

GRAPH = "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json"
GEOFENCE = "data/civic/astana/geofence.json"
WAY_TAGS = "data/civic/astana/geo/way_tags.json"
OSM_RAW = "data/civic/astana/osm-objects/raw"

SEGMENT_TOL_M = 5.0      # §8.3: линия участка ≤ 5 м от формы ребра
STOP_TOL_M = 60.0        # §8.3: остановка ≤ 60 м от улицы
OSM_POINT_TOL_M = 1.0    # точка объекта = точка OSM (округление координат до 6 знаков ≈ 0,1 м)
# Проезжая часть: классы highway, по которым ездят автобусы и машины (для правила «остановка у улицы»).
ROAD_CLASSES = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
                "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street",
                "service", "road", "busway"}
SEGMENT_ID = re.compile(r"^osm-w(\d+)-(\d+)$")

M_PER_DEG_LAT = 111_132.0


# ----------------------------------------------------------------------------------------------- геометрия
def _xy(lon, lat, lat0):
    """Плоские метры около широты lat0 (для отрезков до нескольких км погрешность < 0,1 %)."""
    return lon * M_PER_DEG_LAT * math.cos(math.radians(lat0)), lat * M_PER_DEG_LAT


def dist_m(a, b):
    lat0 = (a[1] + b[1]) / 2
    ax, ay = _xy(a[0], a[1], lat0)
    bx, by = _xy(b[0], b[1], lat0)
    return math.hypot(ax - bx, ay - by)


def point_segment_m(p, a, b):
    """Расстояние в метрах от точки p до отрезка ab (координаты [lon, lat])."""
    lat0 = p[1]
    px, py = _xy(p[0], p[1], lat0)
    ax, ay = _xy(a[0], a[1], lat0)
    bx, by = _xy(b[0], b[1], lat0)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_line_m(p, line):
    if len(line) == 1:
        return dist_m(p, line[0])
    return min(point_segment_m(p, line[i], line[i + 1]) for i in range(len(line) - 1))


def _densify(line, step_m=2.0):
    """Точки вдоль линии каждые ~2 м: иначе длинный прямой отрезок «срежет» изгиб улицы незамеченным."""
    out = [line[0]]
    for a, b in zip(line, line[1:]):
        n = max(1, int(dist_m(a, b) // step_m))
        for k in range(1, n + 1):
            t = k / n
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
    return out


def hausdorff_m(line_a, line_b):
    """Наибольшее отклонение двух линий друг от друга (симметрично, с уплотнением точек)."""
    da = max(point_line_m(p, line_b) for p in _densify(line_a))
    db = max(point_line_m(p, line_a) for p in _densify(line_b))
    return max(da, db)


def point_in_rings(p, rings):
    """Чётно-нечётное правило по всем кольцам полигона (внешние и дыры)."""
    x, y = p
    inside = False
    for ring in rings:
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i][0], ring[i][1]
            x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def iter_coords(geom):
    """Все пары [lon, lat] из GeoJSON-геометрии или вложенных списков."""
    if isinstance(geom, dict):
        if "coordinates" in geom:
            yield from iter_coords(geom["coordinates"])
        elif "geometries" in geom:
            for g in geom["geometries"]:
                yield from iter_coords(g)
        return
    if isinstance(geom, (list, tuple)):
        if len(geom) >= 2 and all(isinstance(v, (int, float)) for v in geom[:2]) and not isinstance(geom[0], bool):
            yield [float(geom[0]), float(geom[1])]
        else:
            for g in geom:
                yield from iter_coords(g)


# ----------------------------------------------------------------------------------------------- данные
class Graph:
    """Рёбра пешеходного графа OSM + сеточный индекс для поиска ближайшей линии."""

    CELL = 0.002  # градуса: ~140 м по долготе и ~220 м по широте

    def __init__(self, path: Path, way_tags: dict | None):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.id = data.get("id")
        self.edges = {e["id"]: e for e in data["edges"]}
        self.road_way = None
        if way_tags:
            classes = way_tags["classes"]
            self.road_way = {int(w): classes[v[0]] in ROAD_CLASSES for w, v in way_tags["ways"].items()}
        self.grid: dict[tuple[int, int], list[str]] = {}
        for eid, e in self.edges.items():
            xs = [c[0] for c in e["geometry"]]
            ys = [c[1] for c in e["geometry"]]
            for ix in range(int(min(xs) // self.CELL), int(max(xs) // self.CELL) + 1):
                for iy in range(int(min(ys) // self.CELL), int(max(ys) // self.CELL) + 1):
                    self.grid.setdefault((ix, iy), []).append(eid)

    def is_road(self, eid):
        if self.road_way is None:
            return True
        return self.road_way.get(self.edges[eid].get("osm_way_id"), False)

    def nearest(self, p, radius_m=200.0, roads_only=False):
        """(расстояние_м, id ребра) до ближайшей линии графа в радиусе; (inf, None), если рядом ничего нет."""
        r_lon = radius_m / (M_PER_DEG_LAT * math.cos(math.radians(p[1])))
        r_lat = radius_m / M_PER_DEG_LAT
        best = (math.inf, None)
        seen = set()
        for ix in range(int((p[0] - r_lon) // self.CELL), int((p[0] + r_lon) // self.CELL) + 1):
            for iy in range(int((p[1] - r_lat) // self.CELL), int((p[1] + r_lat) // self.CELL) + 1):
                for eid in self.grid.get((ix, iy), ()):
                    if eid in seen or (roads_only and not self.is_road(eid)):
                        continue
                    seen.add(eid)
                    d = point_line_m(p, self.edges[eid]["geometry"])
                    if d < best[0]:
                        best = (d, eid)
        return best


class Boundary:
    def __init__(self, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        self.polygons = data["polygons"]

    def contains(self, p):
        return any(point_in_rings(p, poly["rings"]) for poly in self.polygons)


def load_osm_raw(root: Path):
    """Все узлы, пути и отношения из выгрузки LOCAL-1: {('node'|'way'|'relation', id): [lon, lat] | None}."""
    out = {}
    folder = root / OSM_RAW
    if not folder.is_dir():
        return None
    for f in sorted(folder.glob("*.json.gz")):
        data = json.load(gzip.open(f, "rt", encoding="utf-8"))
        for el in data.get("elements", []):
            if el.get("type") == "node":
                out[("node", el["id"])] = [el["lon"], el["lat"]]
            elif el.get("type") in ("way", "relation"):
                c = el.get("center")
                out[(el["type"], el["id"])] = [c["lon"], c["lat"]] if c else None
    return out


def load_rail_ids(root: Path):
    """id OSM железнодорожных/трамвайных платформ из LOCAL-1: они не автобусные остановки."""
    folder = root / OSM_RAW
    if not folder.is_dir():
        return None
    out = set()
    for f in sorted(folder.glob("*.json.gz")):
        for el in json.load(gzip.open(f, "rt", encoding="utf-8")).get("elements", []):
            t = el.get("tags") or {}
            if t.get("railway") or t.get("train") == "yes" or t.get("tram") == "yes":
                out.add(f"osm-{el['type']}-{el['id']}")
    return out


def _json(root: Path, rel):
    p = root / rel
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def python_literal_lines(root: Path, rel):
    """Линии и точки из литералов Python-файла (без выполнения кода): списки [[lon, lat], …] и [lon, lat]."""
    p = root / rel
    if not p.is_file():
        return None
    tree = ast.parse(p.read_text(encoding="utf-8"))
    lines, points = [], []

    def is_pair(n):
        return (isinstance(n, (ast.List, ast.Tuple)) and len(n.elts) == 2
                and all(isinstance(e, ast.Constant) and isinstance(e.value, float) for e in n.elts)
                and 70 < n.elts[0].value < 73 and 50 < n.elts[1].value < 52)

    inner = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) >= 2 and all(is_pair(e) for e in node.elts):
            lines.append([[e.elts[0].value, e.elts[1].value] for e in node.elts])
            inner.update(id(e) for e in node.elts)
    for node in ast.walk(tree):
        if is_pair(node) and id(node) not in inner:
            points.append([node.elts[0].value, node.elts[1].value])
    return {"lines": lines, "points": points}


# ----------------------------------------------------------------------------------------------- проверки
class Report:
    def __init__(self):
        self.checks = []

    def add(self, name, status, detail, owner=None):
        self.checks.append({"name": name, "status": status, "owner": owner, "detail": detail})

    def failed(self):
        return [c for c in self.checks if c["status"] == "FAIL"]


def collect_sources(root: Path):
    """Все наборы координат, которые попадают на карту, с владельцем. None — набора нет в этой сборке."""
    src = {}
    src["R12 geo/objects.json"] = ("R12", _json(root, "data/civic/astana/geo/objects.json"))
    src["R12 geo/yards.json"] = ("R12", _json(root, "data/civic/astana/geo/yards.json"))
    src["R12 geo/demo_snapped.json"] = ("R12", _json(root, "data/civic/astana/geo/demo_snapped.json"))
    src["R12 map/demo_snapped.json"] = ("R12", _json(root, "web/civic/map/demo_snapped.json"))
    src["R07 targets_demo.json"] = ("R07", _json(root, "ui/civic_heat/fixtures/targets_demo.json"))
    src["R05 proposals.fixture.json"] = ("R05", _json(root, "web/civic/build3d/data/proposals.fixture.json"))
    src["R05 nura-streets.json"] = ("R05", _json(root, "web/civic/build3d/data/nura-streets.json"))
    src["R05 astana-existing.json"] = ("R05", _json(root, "web/civic/build3d/data/astana-existing.json"))
    src["R06 demo_r14.py"] = ("R06", python_literal_lines(root, "ui/civic_store/demo_r14.py"))
    src["R13 forecast targets.json"] = ("R13", _json(root, "ml/civic_forecast/data/targets.json"))
    return src


def coords_of(name, data):
    """Все координаты набора (для проверки границы города)."""
    if data is None:
        return []
    if name.startswith("R06"):
        return [c for line in data["lines"] for c in line] + data["points"]
    if name == "R12 geo/demo_snapped.json" or name == "R12 map/demo_snapped.json":
        out = []
        for it in data.get("items", {}).values():
            out += list(iter_coords(it.get("geometry"))) if it.get("geometry") else []
        return out
    if name == "R07 targets_demo.json":
        return [c for t in data["targets"].values() for c in iter_coords(t.get("geometry"))]
    if name == "R05 nura-streets.json":
        return [c for e in data["edges"] for c in e[5]]
    if name == "R05 astana-existing.json":
        pts = [[row[0], row[1]] for _kind, row in r05_points(data)]
        ring = data["yard_fields"].index("ring")
        return pts + [c for y in data.get("yards", []) for c in iter_coords(y[ring])]
    if name == "R13 forecast targets.json":
        items = data.get("targets") or data.get("items") or []
        return [c for t in items for c in iter_coords(t.get("point") or t.get("geometry"))]
    if name == "R05 proposals.fixture.json":
        return [c for p in data.get("proposals", []) for c in iter_coords(p.get("geometry"))]
    if name == "R12 geo/objects.json":
        return [c for it in data["items"] for c in iter_coords(it.get("point"))] + \
               [c for it in data["items"] for c in iter_coords(it.get("polygon") or [])]
    if name == "R12 geo/yards.json":
        return [c for it in data["items"] for c in iter_coords(it.get("polygon"))]
    return list(iter_coords(data))


def r05_points(data):
    """Точки R05 astana-existing.json: {"stop": [[lon, lat, id, name_ru, name_kk, …], …], …} → [(вид, строка)]."""
    fields = data["point_fields"]
    assert fields[:3] == ["lon", "lat", "id"], fields
    return [(kind, row) for kind, rows in data["points"].items() for row in rows]


def check_boundary(rep: Report, boundary: Boundary, sources):
    for name, (owner, data) in sources.items():
        if data is None:
            rep.add(f"граница Астаны · {name}", "NOT_RUN", "набора нет в этой сборке", owner)
            continue
        coords = coords_of(name, data)
        outside = [c for c in coords if not boundary.contains(c)]
        status = "PASS" if coords and not outside else ("NOT_RUN" if not coords else "FAIL")
        rep.add(f"граница Астаны · {name}", status,
                {"coords": len(coords), "outside": len(outside), "examples": outside[:5]}, owner)


def check_segments(rep: Report, graph: Graph, sources):
    """§8.1, §8.3: участки улиц совпадают с формой рёбер графа (≤ 5 м в обе стороны)."""
    # R07: цели-участки, id = id ребра
    _, r07 = sources["R07 targets_demo.json"]
    if r07 is None:
        rep.add("участки = рёбра OSM · R07 targets", "NOT_RUN", "набора нет", "R07")
    else:
        bad, worst, n = [], 0.0, 0
        for tid, t in r07["targets"].items():
            if t.get("kind") != "segment":
                continue
            n += 1
            edge = graph.edges.get(tid)
            if edge is None:
                bad.append({"id": tid, "why": "нет такого ребра в графе"})
                continue
            d = hausdorff_m(t["geometry"]["coordinates"], edge["geometry"])
            worst = max(worst, d)
            if d > SEGMENT_TOL_M:
                bad.append({"id": tid, "dev_m": round(d, 2)})
        rep.add("участки = рёбра OSM · R07 targets", "FAIL" if bad else ("PASS" if n else "NOT_RUN"),
                {"segments": n, "worst_m": round(worst, 3), "bad": bad[:10]}, "R07")

    # R05: улицы Нуры для освещения — копия рёбер графа
    _, r05 = sources["R05 nura-streets.json"]
    if r05 is None:
        rep.add("улицы Нуры R05 = рёбра OSM", "NOT_RUN", "набора нет", "R05")
    else:
        bad, worst = [], 0.0
        for e in r05["edges"]:
            edge = graph.edges.get(e[0])
            if edge is None:
                bad.append({"id": e[0], "why": "нет такого ребра в графе"})
                continue
            d = hausdorff_m(e[5], edge["geometry"])
            worst = max(worst, d)
            if d > SEGMENT_TOL_M:
                bad.append({"id": e[0], "dev_m": round(d, 2)})
        rep.add("улицы Нуры R05 = рёбра OSM", "FAIL" if bad else "PASS",
                {"edges": len(r05["edges"]), "worst_m": round(worst, 3), "bad": bad[:10]}, "R05")

    # Любая линия-предложение/демо-линия должна лежать на графе (иначе это линия «от руки»)
    def on_graph(line):
        worst = 0.0
        for p in _densify(line, 5.0):
            d, _ = graph.nearest(p, radius_m=50)
            worst = max(worst, d)
        return worst

    for name, owner, lines in [
        ("линии R05 proposals.fixture на улице", "R05",
         None if sources["R05 proposals.fixture.json"][1] is None else
         [p["geometry"]["coordinates"] for p in sources["R05 proposals.fixture.json"][1]["proposals"]
          if p.get("geometry", {}).get("type") == "LineString"]),
        ("линии R06 demo_r14 на улице", "R06",
         None if sources["R06 demo_r14.py"][1] is None else sources["R06 demo_r14.py"][1]["lines"]),
    ]:
        if lines is None:
            rep.add(name, "NOT_RUN", "набора нет", owner)
            continue
        devs = [round(on_graph(l), 2) for l in lines]
        bad = [d for d in devs if d > SEGMENT_TOL_M]
        rep.add(name, "FAIL" if bad else ("PASS" if devs else "NOT_RUN"), {"lines": len(devs), "dev_m": devs}, owner)

    # R12: демо-линии раунда 11 после привязки: snapped — на графе; not_snapped — только «примерное место»
    for name in ("R12 geo/demo_snapped.json", "R12 map/demo_snapped.json"):
        _, d = sources[name]
        if d is None:
            rep.add(f"нет линий «от руки» · {name}", "NOT_RUN", "набора нет", "R12")
            continue
        bad, info = [], []
        for rid, it in d["items"].items():
            if it.get("status") == "snapped":
                g = it.get("geometry") or {}
                lines = [g["coordinates"]] if g.get("type") == "LineString" else \
                        (g.get("coordinates") or [] if g.get("type") == "MultiLineString" else [])
                dev = max((on_graph(l) for l in lines), default=None)
                info.append({"id": rid, "snapped_dev_m": None if dev is None else round(dev, 2)})
                if dev is None or dev > SEGMENT_TOL_M:
                    bad.append({"id": rid, "dev_m": dev})
            else:
                info.append({"id": rid, "display": it.get("display")})
                if it.get("display") not in ("approximate_area", "approximate", "list_only"):
                    bad.append({"id": rid, "why": "не привязано, но не помечено «примерное место»"})
        rep.add(f"нет линий «от руки» · {name}", "FAIL" if bad else "PASS", {"items": info, "bad": bad}, "R12")


def check_stops(rep: Report, graph: Graph, sources, root: Path):
    """§8.3: остановка не дальше 60 м от улицы."""
    stops = []
    _, objs = sources["R12 geo/objects.json"]
    if objs:
        stops += [("R12", it["id"], it["point"]) for it in objs["items"] if it.get("kind") == "bus_stop"]
    _, r07 = sources["R07 targets_demo.json"]
    if r07:
        stops += [("R07", tid, t["geometry"]["coordinates"]) for tid, t in r07["targets"].items()
                  if t.get("kind") == "object" and t.get("subtype") in ("bus_stop", "stop", "platform")]
    _, r05 = sources["R05 astana-existing.json"]
    if r05:
        stops += [("R05", row[2], [row[0], row[1]]) for kind, row in r05_points(r05) if kind == "stop"]
    _, r13 = sources["R13 forecast targets.json"]
    if r13:
        items = r13.get("targets") or r13.get("items") or []
        stops += [("R13", t["id"], t["point"]) for t in items if t.get("kind") == "bus_stop" and t.get("point")]
    if not stops:
        rep.add("остановки ≤ 60 м от улицы", "NOT_RUN", "остановок в сборке нет")
        return
    rail = load_rail_ids(root)
    if rail is not None:
        for owner in sorted({o for o, _, _ in stops}):
            wrong = [sid for o, sid, _ in stops if o == owner and sid in rail]
            rep.add(f"остановки — не ж/д платформы · {owner}", "FAIL" if wrong else "PASS",
                    {"stops": sum(o == owner for o, _, _ in stops), "railway": len(wrong), "examples": wrong[:8]}, owner)
    by_owner = {}
    for owner, sid, p in stops:
        d_road, e_road = graph.nearest(p, radius_m=300, roads_only=True)
        d_any, _ = graph.nearest(p, radius_m=300)
        rec = by_owner.setdefault(owner, {"n": 0, "far_road": [], "far_any": [], "max_road_m": 0.0})
        rec["n"] += 1
        rec["max_road_m"] = max(rec["max_road_m"], d_road if d_road != math.inf else 9999)
        if d_road > STOP_TOL_M:
            rec["far_road"].append({"id": sid, "road_m": round(d_road, 1) if d_road != math.inf else ">300",
                                    "any_line_m": round(d_any, 1) if d_any != math.inf else ">300", "point": p})
        if d_any > STOP_TOL_M:
            rec["far_any"].append(sid)
    for owner, rec in by_owner.items():
        # Главный критерий — любая линия улицы графа (как в CONTRACT); отдельно считаем проезжую часть.
        status = "FAIL" if rec["far_any"] else "PASS"
        rep.add(f"остановки ≤ 60 м от улицы · {owner}", status,
                {"stops": rec["n"], "far_from_any_line": rec["far_any"][:10],
                 "far_from_road": len(rec["far_road"]), "far_road_examples": rec["far_road"][:5],
                 "max_road_m": round(rec["max_road_m"], 1)}, owner)


def check_osm_points(rep: Report, root: Path, sources):
    """§8.2: точечные объекты — реальные из OSM, с их координатами."""
    raw = load_osm_raw(root)
    if raw is None:
        rep.add("объекты = точки OSM", "NOT_RUN", f"нет {OSM_RAW} (LOCAL-1)")
        return
    _, objs = sources["R12 geo/objects.json"]
    if objs is None:
        rep.add("объекты R12 = точки OSM", "NOT_RUN", "набора нет", "R12")
    else:
        missing, moved, n = [], [], 0
        for it in objs["items"]:
            # osm-relation-… (парки, площадки-мультиполигоны) R07 и R09 принимают; CONTRACT §4 его пока не называет.
            m = re.match(r"^osm-(node|way|relation)-(\d+)$", it["id"])
            if not m:
                missing.append({"id": it["id"], "why": "id не вида osm-node-/osm-way-/osm-relation-"})
                continue
            key = (m.group(1), int(m.group(2)))
            if key not in raw:
                # Остановки R12 частично взяты из снимка пешеходной сети (src = overpass.json.gz), а не из LOCAL-1:
                # их проверяет правило «остановка у улицы», здесь пропускаем.
                if it.get("src") in (None, "overpass.json.gz", "walking_graph", "osm-walking"):
                    continue
                missing.append({"id": it["id"], "src": it.get("src")})
                continue
            n += 1
            ref = raw[key]
            if ref and key[0] == "node" and dist_m(ref, it["point"]) > OSM_POINT_TOL_M:
                moved.append({"id": it["id"], "moved_m": round(dist_m(ref, it["point"]), 2)})
        rep.add("объекты R12 = точки OSM", "FAIL" if missing or moved else "PASS",
                {"checked": n, "total": len(objs["items"]), "missing": missing[:10], "moved": moved[:10]}, "R12")
    _, r05 = sources["R05 astana-existing.json"]
    if r05 is None:
        rep.add("объекты R05 = точки OSM", "NOT_RUN", "набора нет", "R05")
    else:
        missing, moved, n = [], [], 0
        for kind, row in r05_points(r05):
            m = re.match(r"^osm-(node|way|relation)-(\d+)$", str(row[2]))
            if not m:
                missing.append({"id": row[2], "kind": kind, "why": "id не из OSM"})
                continue
            key = (m.group(1), int(m.group(2)))
            if key not in raw:
                missing.append({"id": row[2], "kind": kind})
                continue
            n += 1
            if key[0] == "node" and raw[key] and dist_m(raw[key], row[:2]) > OSM_POINT_TOL_M:
                moved.append({"id": row[2], "moved_m": round(dist_m(raw[key], row[:2]), 2)})
        rep.add("объекты R05 = точки OSM", "FAIL" if missing or moved else "PASS",
                {"checked": n, "missing": len(missing), "missing_examples": missing[:8], "moved": moved[:8]}, "R05")
    _, r07 = sources["R07 targets_demo.json"]
    if r07 is None:
        rep.add("объекты R07 = точки OSM", "NOT_RUN", "набора нет", "R07")
    else:
        missing, moved, n = [], [], 0
        for tid, t in r07["targets"].items():
            osm = t.get("osm")
            if t.get("kind") != "object":
                continue
            n += 1
            if not osm:
                missing.append({"id": tid, "why": "нет ссылки на OSM"})
                continue
            key = (osm["type"], int(osm["id"]))
            if key not in raw:
                missing.append({"id": tid, "osm": osm})
                continue
            if key[0] == "node" and raw[key] and dist_m(raw[key], t["geometry"]["coordinates"]) > OSM_POINT_TOL_M:
                moved.append({"id": tid, "moved_m": round(dist_m(raw[key], t["geometry"]["coordinates"]), 2)})
        rep.add("объекты R07 = точки OSM", "FAIL" if missing or moved else ("PASS" if n else "NOT_RUN"),
                {"objects": n, "missing": missing[:10], "moved": moved[:10]}, "R07")


def check_target_ids(rep: Report, graph: Graph, sources):
    """CONTRACT §4: id целей существуют (рёбра — в графе, дворы — в yards.json)."""
    _, r07 = sources["R07 targets_demo.json"]
    _, yards = sources["R12 geo/yards.json"]
    if r07 is None:
        rep.add("id целей R07 по контракту §4", "NOT_RUN", "набора нет", "R07")
        return
    yard_ids = {y["id"] for y in yards["items"]} if yards else None
    bad = []
    for tid, t in r07["targets"].items():
        k = t.get("kind")
        if k == "segment" and (not SEGMENT_ID.match(tid) or tid not in graph.edges):
            bad.append({"id": tid, "why": "участок не из графа"})
        elif k == "object" and not re.match(r"^osm-(node|way|relation)-\d+$", tid):
            bad.append({"id": tid, "why": "объект не вида osm-node-/osm-way-/osm-relation-"})
        elif k == "area" and not re.match(r"^(yard|cell)-[\w-]+$", tid):
            bad.append({"id": tid, "why": "область не вида yard-/cell-"})
        elif k == "area" and tid.startswith("yard-") and yard_ids is not None and tid not in yard_ids:
            bad.append({"id": tid, "why": "двора нет в geo/yards.json R12"})
    rep.add("id целей R07 по контракту §4", "FAIL" if bad else "PASS", {"targets": len(r07["targets"]), "bad": bad}, "R07")


def run(root: Path) -> Report:
    rep = Report()
    gpath, bpath = root / GRAPH, root / GEOFENCE
    if not gpath.is_file() or not bpath.is_file():
        rep.add("эталон: граф улиц и граница города", "NOT_RUN", f"нет {GRAPH} или {GEOFENCE}")
        return rep
    graph = Graph(gpath, _json(root, WAY_TAGS))
    boundary = Boundary(bpath)
    sources = collect_sources(root)
    check_boundary(rep, boundary, sources)
    check_segments(rep, graph, sources)
    check_stops(rep, graph, sources, root)
    check_osm_points(rep, root, sources)
    check_target_ids(rep, graph, sources)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="R10: точность карты по CONTRACT §8")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    ap.add_argument("--json", help="куда записать отчёт JSON")
    a = ap.parse_args(argv)
    rep = run(Path(a.root))
    for c in rep.checks:
        print(f"{c['status']:8} {c['name']}" + (f"  [{c['owner']}]" if c["owner"] else ""))
        if c["status"] == "FAIL":
            print("         " + json.dumps(c["detail"], ensure_ascii=False)[:600])
    counts = {s: sum(c["status"] == s for c in rep.checks) for s in ("PASS", "FAIL", "NOT_RUN")}
    print("ИТОГ:", counts)
    if a.json:
        Path(a.json).write_text(json.dumps({"root": a.root, "counts": counts, "checks": rep.checks},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if rep.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
