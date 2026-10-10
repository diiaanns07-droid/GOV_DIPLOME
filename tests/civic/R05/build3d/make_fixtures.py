"""R05 · 3D-превью: сборка фикстур из реальных данных OSM (раунд 14).

Запуск из корня репозитория:
    python tests/civic/R05/build3d/make_fixtures.py

Что делает (детерминированно, без сети):
  1. web/civic/build3d/data/nura-streets.json — именованные улицы фокус-области Нуры
     из пешеходного графа engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json.
     Нужны для освещения «вдоль участка улицы» (пока нет R12 /targets), для подписи
     «рядом: улица …» и для разворота остановки вдоль улицы. Форма — настоящая форма OSM.
  2. web/civic/build3d/data/astana-districts.json — упрощённые границы районов
     (data/civic/astana/geofence.json): проверка «внутри Астаны» и район предложения.
  3. web/civic/build3d/data/demo-basemap.json — ВСЕ рёбра графа в фокус-области: только для
     demo.html (подложка без интернета). В общую сборку не нужен.
  4. web/civic/build3d/data/proposals.fixture.json — два ПРИМЕРА предложений (demo: true) для
     заглушки R06 по CONTRACT §7: освещение по настоящим рёбрам ул. Сыганак и остановка у её края.
     Голоса — синтетические числа для показа карточки (помечены demo).

Данные © OpenStreetMap contributors, ODbL 1.0 (производные).
"""

import json
import math
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
GRAPH = os.path.join(REPO, "engine", "civic_scenarios", "graphs", "osm-astana-walking-20260506.graph.json")
GEOFENCE = os.path.join(REPO, "data", "civic", "astana", "geofence.json")
OUT = os.path.join(REPO, "web", "civic", "build3d", "data")

# Фокус-область демо: жилые кварталы Нуры между пр. Туран, ул. Сыганак и ул. Айтеке Би.
FOCUS_BBOX = (71.375, 51.115, 71.420, 51.140)  # lon_min, lat_min, lon_max, lat_max
DIGITS = 6  # 1e-6 градуса ≈ 0.07–0.11 м — с запасом для допуска 5 м (CONTRACT §8)
SIMPLIFY_M = 15.0  # допуск упрощения границ районов, метры

ATTRIBUTION = "© OpenStreetMap contributors"


def r(v):
    return round(v, DIGITS)


def edge_in_bbox(geom, bbox):
    xs = [p[0] for p in geom]
    ys = [p[1] for p in geom]
    return not (max(xs) < bbox[0] or min(xs) > bbox[2] or max(ys) < bbox[1] or min(ys) > bbox[3])


def to_xy(lon, lat, lat0):
    """Локальная равнопромежуточная проекция в метрах (для упрощения линий)."""
    k = math.pi / 180 * 6371008.8
    return lon * k * math.cos(lat0 * math.pi / 180), lat * k


def simplify(ring, tol_m):
    """Дуглас–Пекер в метрах. Замкнутое кольцо: первая точка = последняя."""
    if len(ring) < 5:
        return ring
    lat0 = sum(p[1] for p in ring) / len(ring)
    pts = [to_xy(p[0], p[1], lat0) for p in ring]
    keep = [False] * len(ring)
    keep[0] = keep[-1] = True
    # Кольцо делим на две половины, чтобы у отрезка были разные концы.
    mid = len(ring) // 2
    keep[mid] = True
    stack = [(0, mid), (mid, len(ring) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if L2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > best:
                best, idx = d, i
        if best > tol_m and idx > 0:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [[r(ring[i][0]), r(ring[i][1])] for i in range(len(ring)) if keep[i]]


def dump(name, data, out_dir=None):
    path = os.path.join(out_dir or OUT, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    return path, os.path.getsize(path)


def main(out_dir=None):
    """out_dir — куда писать (по умолчанию web/civic/build3d/data; тест пишет во временную папку)."""
    out_dir = out_dir or OUT
    os.makedirs(out_dir, exist_ok=True)
    with open(GRAPH, encoding="utf-8") as fh:
        graph = json.load(fh)
    with open(GEOFENCE, encoding="utf-8") as fh:
        geofence = json.load(fh)
    source = {
        "graph_id": graph["id"],
        "graph_digest": graph["digest"],
        "graph_path": "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json",
        "osm_snapshot": graph["limitations"][0] if graph.get("limitations") else None,
        "license": "ODbL-1.0",
        "attribution": ATTRIBUTION,
        "evidence_type": "real (OSM), derived",
    }

    # 1. Именованные улицы фокус-области. Узлы и рёбра сохраняются с id графа — это
    #    те же id, что у R12 /targets (osm-w<way>-<n>), поэтому цель «участок улицы» совместима.
    names, name_idx, nodes, node_idx, edges = [], {}, [], {}, []
    for e in graph["edges"]:
        name = (e.get("name") or "").strip()
        if not name or not edge_in_bbox(e["geometry"], FOCUS_BBOX):
            continue
        if name not in name_idx:
            name_idx[name] = len(names)
            names.append(name)
        for nid in (e["from"], e["to"]):
            if nid not in node_idx:
                node_idx[nid] = len(nodes)
                nodes.append(nid)
        edges.append([
            e["id"], name_idx[name], node_idx[e["from"]], node_idx[e["to"]],
            round(e["length_m"], 2), [[r(x), r(y)] for x, y in e["geometry"]],
        ])
    edges.sort(key=lambda row: row[0])
    streets = {
        "schema": "birge-build3d-streets-v1",
        "purpose": "Улицы для освещения вдоль участка, подписи «рядом» и разворота остановки. "
                   "Заглушка до R12 /targets; форма улиц — настоящая OSM.",
        "bbox": list(FOCUS_BBOX),
        "source": source,
        "fields": ["id", "name_index", "from_node_index", "to_node_index", "length_m", "geometry"],
        "names": names,
        "nodes": nodes,
        "edges": edges,
    }
    print(dump("nura-streets.json", streets, out_dir), len(edges), "edges", len(names), "names")

    # 2. Районы: упрощённые кольца + bbox города.
    districts = []
    for poly in geofence["polygons"]:
        rings = [simplify(ring, SIMPLIFY_M) for ring in poly["rings"]]
        districts.append({"id": poly["district_id"], "name_ru": poly["name"], "osm_relation": poly.get("osm_relation"),
                          "rings": rings})
    dump_d = {
        "schema": "birge-build3d-districts-v1",
        "purpose": "Проверка «внутри Астаны» и район предложения. Не официальная граница.",
        "simplify_m": SIMPLIFY_M,
        "city_bbox": geofence["city_bbox"],
        "source": {"path": "data/civic/astana/geofence.json", "license": "ODbL-1.0", "attribution": ATTRIBUTION},
        "districts": districts,
    }
    print(dump("astana-districts.json", dump_d, out_dir), sum(len(rg) for d in districts for rg in d["rings"]), "points")

    # 3. Подложка demo.html: все рёбра фокус-области (без имён) + именованные отдельно.
    named, other = [], []
    for e in graph["edges"]:
        if not edge_in_bbox(e["geometry"], FOCUS_BBOX):
            continue
        line = [[r(x), r(y)] for x, y in e["geometry"]]
        (named if (e.get("name") or "").strip() else other).append(line)
    nura = [d for d in districts if d["id"] == "nura"]
    basemap = {
        "schema": "birge-build3d-demo-basemap-v1",
        "purpose": "Только для web/civic/build3d/demo.html без интернета. В сборке — подложка R01.",
        "bbox": list(FOCUS_BBOX),
        "source": source,
        "named": named,
        "other": other,
        "nura": nura[0]["rings"] if nura else [],
    }
    print(dump("demo-basemap.json", basemap, out_dir), len(named), "named", len(other), "other")
    print(write_demo_proposals(graph, out_dir))


# ── Примеры предложений ──
LIGHT_EDGES = ["osm-w1328815797-6", "osm-w1328815797-7", "osm-w1328815797-8"]  # ул. Сыганак, ~208 м
STOP_EDGE = "osm-w1189551423-0"  # ул. Сыганак, другая проезжая часть, 182 м
STOP_OFFSET_M = 8.0  # центр остановки от оси проезжей части (пятно 4.5 м + тротуар)
EARTH_R = 6371008.8  # как в MapLibre и build3d-core.js


def merc(lon, lat):
    return (180 + lon) / 360, (180 - 180 / math.pi * math.log(math.tan(math.pi / 4 + lat * math.pi / 360))) / 360


def to_local(origin, p):
    s = 1 / (2 * math.pi * EARTH_R) / math.cos(origin[1] * math.pi / 180)
    ox, oy = merc(*origin)
    x, y = merc(*p)
    return (x - ox) / s, -(y - oy) / s


def from_local(origin, xy):
    s = 1 / (2 * math.pi * EARTH_R) / math.cos(origin[1] * math.pi / 180)
    ox, oy = merc(*origin)
    x, y = ox + xy[0] * s, oy - xy[1] * s
    lon = x * 360 - 180
    lat = 360 / math.pi * math.atan(math.exp((180 - y * 360) * math.pi / 180)) - 90
    return lon, lat


def bearing(dx, dy):
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360


def demo_proposals(graph):
    by_id = {e["id"]: e for e in graph["edges"]}
    # Освещение: цепочка рёбер одной улицы, проверяем, что они соединены.
    chain = [by_id[i] for i in LIGHT_EDGES]
    coords = [list(p) for p in chain[0]["geometry"]]
    for prev, e in zip(chain, chain[1:]):
        assert prev["to"] == e["from"], (prev["id"], e["id"])
        coords.extend(list(p) for p in e["geometry"][1:])
    light = [[r(x), r(y)] for x, y in coords]
    name = chain[0]["name"]
    # Остановка: середина ребра, сдвиг от оси на внешнюю сторону (дальше от второй проезжей части).
    e = by_id[STOP_EDGE]
    a, b = e["geometry"][0], e["geometry"][-1]
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    ax, ay = to_local(mid, a)
    bx, by = to_local(mid, b)
    L = math.hypot(bx - ax, by - ay)
    dx, dy = (bx - ax) / L, (by - ay) / L
    nx, ny = dy, -dx  # правая нормаль
    other = to_local(mid, light[len(light) // 2])
    side = -1 if other[0] * nx + other[1] * ny > 0 else 1  # от второй проезжей части
    center = from_local(mid, (nx * STOP_OFFSET_M * side, ny * STOP_OFFSET_M * side))
    to_street = bearing(-nx * side, -ny * side)
    rot = round((to_street - 180) % 360)  # «открытая» сторона павильона (−y модели) — к дороге
    common = {"status": "proposal", "year": 2027, "district": "nura", "demo": True, "created_at": "2026-10-10T12:00:00+05:00"}
    return [
        dict(common, id="p-demo-light-syganak", kind="lighting",
             geometry={"type": "LineString", "coordinates": light}, rotation_deg=0,
             votes_up=128, votes_down=12, near_street=name,
             target={"kind": "segment", "id": LIGHT_EDGES[0], "ids": LIGHT_EDGES, "label_ru": name, "label_kk": name}),
        dict(common, id="p-demo-stop-syganak", kind="stop",
             geometry={"type": "Point", "coordinates": [r(center[0]), r(center[1])]}, rotation_deg=rot,
             votes_up=64, votes_down=5, near_street=e["name"]),
    ]


def write_demo_proposals(graph, out_dir=None):
    data = {
        "schema": "birge-proposals-fixture-v1",
        "purpose": "Заглушка GET /api/civic/v2/proposals (CONTRACT §7) до подключения R06. Только примеры (demo: true).",
        "source": {"streets": "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json",
                   "edges": LIGHT_EDGES + [STOP_EDGE], "license": "ODbL-1.0", "attribution": ATTRIBUTION},
        "proposals": demo_proposals(graph),
    }
    path = os.path.join(out_dir or OUT, "proposals.fixture.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return path


if __name__ == "__main__":
    main()
