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
  5. web/civic/build3d/data/astana-existing.json — реальные объекты OSM всей Астаны из
     data/civic/astana/osm-objects/ (LOCAL-1): остановки, площадки, спортплощадки, парки/скверы,
     фонари — для подсказки «рядом уже есть …»; жилые кварталы (landuse=residential) — для привязки
     предложения к двору yard-<id> (CONTRACT §4).
  4. web/civic/build3d/data/proposals.fixture.json — два ПРИМЕРА предложений (demo: true) для
     заглушки R06 по CONTRACT §7: освещение по настоящим рёбрам ул. Сыганак и остановка у её края.
     Голоса — синтетические числа для показа карточки (помечены demo).

Данные © OpenStreetMap contributors, ODbL 1.0 (производные).
"""

import collections
import gzip
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
    names_kk = street_names_kk(edges, names)
    streets = {
        "schema": "birge-build3d-streets-v1",
        "purpose": "Улицы для освещения вдоль участка, подписи «рядом» и разворота остановки. "
                   "Заглушка до R12 /targets; форма улиц — настоящая OSM.",
        "bbox": list(FOCUS_BBOX),
        "source": source,
        "fields": ["id", "name_index", "from_node_index", "to_node_index", "length_m", "geometry"],
        "names": names,
        # Казахское название — только если оно есть в OSM (name:kk тех же путей, снимок osm-walking); иначе null и
        # интерфейс показывает русское с lang="ru" (так же делает R12 label_kk). Машинного перевода нет.
        "names_kk": names_kk,
        "names_kk_source": {"path": "data/civic/astana/osm-walking/overpass.json.gz", "tag": "name:kk",
                            "evidence_type": "real (OSM)", "found": sum(1 for x in names_kk if x), "of": len(names)},
        "nodes": nodes,
        "edges": edges,
    }
    print(dump("nura-streets.json", streets, out_dir), len(edges), "edges", len(names), "names",
          sum(1 for x in names_kk if x), "kk")

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
    # Здания для офлайн-демо — только если LOCAL их скачал (INTEGRATION.txt, LOCAL-R05-3). Нет файла — подложка без домов.
    buildings_raw = os.path.join(OSM_OBJECTS, "raw", "buildings_nura.json.gz")
    buildings_file = None
    if os.path.exists(buildings_raw):
        buildings_file = "demo-buildings.json"
        write_buildings(buildings_raw, os.path.join(out_dir, buildings_file))
    basemap = {
        "schema": "birge-build3d-demo-basemap-v1",
        "purpose": "Только для web/civic/build3d/demo.html без интернета. В сборке — подложка R01.",
        "bbox": list(FOCUS_BBOX),
        "source": source,
        "named": named,
        "other": other,
        "nura": nura[0]["rings"] if nura else [],
    }
    if buildings_file:
        basemap["buildings"] = buildings_file
    print(dump("demo-basemap.json", basemap, out_dir), len(named), "named", len(other), "other")
    print(write_demo_proposals(graph, out_dir))
    existing = build_existing()
    print(dump("astana-existing.json", existing, out_dir), {k: len(v) for k, v in existing["points"].items()}, len(existing["yards"]), "yards")


def write_buildings(raw_path, out_path):
    """Контуры зданий OSM фокус-области → GeoJSON для fill-extrusion в demo.html (высота из height / этажей)."""
    with gzip.open(raw_path, "rt", encoding="utf-8") as fh:
        elements = json.load(fh)["elements"]
    feats = []
    for el in elements:
        ring = [[r(g["lon"]), r(g["lat"])] for g in el.get("geometry", []) if g]
        if el.get("type") != "way" or len(ring) < 4 or ring[0] != ring[-1]:
            continue
        tags = el.get("tags", {})
        height = None
        try:
            height = float(str(tags.get("height", "")).replace("m", "").strip())
        except ValueError:
            pass
        if not height and str(tags.get("building:levels", "")).isdigit():
            height = int(tags["building:levels"]) * 3.2
        feats.append({"type": "Feature", "properties": {"id": "osm-way-%d" % el["id"], "height": round(height or 9.0, 1)},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    feats.sort(key=lambda f: f["properties"]["id"])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "license": "ODbL-1.0", "attribution": ATTRIBUTION, "features": feats},
                  fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")


# ── Реальные объекты OSM (LOCAL-1) ──
OSM_OBJECTS = os.path.join(REPO, "data", "civic", "astana", "osm-objects")
USED_SETS = ("bus_stops", "platforms", "playgrounds", "pitches", "parks", "gardens", "street_lamps", "residential")
YARD_SIMPLIFY_M = 2.0


def osm_elements(name):
    with gzip.open(os.path.join(OSM_OBJECTS, "raw", name + ".json.gz"), "rt", encoding="utf-8") as fh:
        return json.load(fh)["elements"]


def element_points(el):
    """Все точки геометрии элемента Overpass (out geom): узел, путь или внешние члены отношения."""
    if el["type"] == "node":
        return [(el["lon"], el["lat"])]
    if el.get("geometry"):
        return [(g["lon"], g["lat"]) for g in el["geometry"] if g]
    pts = []
    for m in el.get("members", []):
        if m.get("role", "outer") in ("outer", "") and m.get("geometry"):
            pts.extend((g["lon"], g["lat"]) for g in m["geometry"] if g)
    return pts


def center(el):
    pts = element_points(el)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def osm_id(el):
    return "osm-%s-%d" % (el["type"], el["id"])  # как у R12: osm-node-<id> / osm-way-<id>


def names(el):
    t = el.get("tags", {})
    ru = t.get("name:ru") or t.get("name") or None
    kk = t.get("name:kk") or t.get("name") or None
    return ru, kk


def outer_rings(el):
    """Кольца жилого квартала: путь — одно кольцо; отношение — склеиваем внешние члены, если получится."""
    if el["type"] == "way":
        ring = [(g["lon"], g["lat"]) for g in el.get("geometry", []) if g]
        return [ring] if len(ring) >= 4 and ring[0] == ring[-1] else []
    rings = []
    for m in el.get("members", []):
        if m.get("role") == "outer" and m.get("geometry"):
            ring = [(g["lon"], g["lat"]) for g in m["geometry"] if g]
            if len(ring) >= 4 and ring[0] == ring[-1]:
                rings.append(ring)
    return rings


OSM_WALKING = os.path.join(REPO, "data", "civic", "astana", "osm-walking", "overpass.json.gz")


def street_names_kk(edges, names):
    """name:kk из снимка OSM для каждого русского названия: самое частое среди путей (way) его рёбер, иначе None."""
    with gzip.open(OSM_WALKING, "rt", encoding="utf-8") as fh:
        way_kk = {el["id"]: (el.get("tags") or {}).get("name:kk") for el in json.load(fh).get("elements", [])
                  if el.get("type") == "way"}
    votes = [collections.Counter() for _ in names]
    for row in edges:
        way = int(row[0].split("-")[1][1:])  # osm-w<way>-<n>
        kk = (way_kk.get(way) or "").strip()
        if kk:
            votes[row[1]][kk] += 1
    return [v.most_common(1)[0][0] if v else None for v in votes]


def is_rail(el):
    """Ж/д и трамвайные платформы — не автобусные остановки (R10 BUGS B-007; то же правило в R10 accuracy.py)."""
    t = el.get("tags") or {}
    return bool(t.get("railway")) or t.get("train") == "yes" or t.get("tram") == "yes"


def point_in_rings(p, rings):
    """Чётно-нечётное правило по всем кольцам полигона (внешние и дыры) — как в R10 accuracy.py."""
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


def city_polygons():
    with open(GEOFENCE, encoding="utf-8") as fh:
        return [poly["rings"] for poly in json.load(fh)["polygons"]]


def in_city(p, city):
    """Внутри Астаны = в одном из полигонов районов OSM (data/civic/astana/geofence.json), CONTRACT §8.3."""
    return any(point_in_rings(p, rings) for rings in city)


def build_existing():
    # Выгрузка LOCAL-1 взята с запасом 0,05° вокруг города: объекты вне районов Астаны не берём (R10 B-008),
    # как и R12 (build_geo_data.py). Проверяются уже округлённые координаты — те, что попадут в файл.
    city = city_polygons()
    seen = set()
    stops = []
    for name in ("bus_stops", "platforms"):  # одна остановка бывает в обоих наборах — убираем повтор по (type, id)
        for el in osm_elements(name):
            key = (el["type"], el["id"])
            if key in seen:
                continue
            seen.add(key)
            if is_rail(el):
                continue
            x, y = center(el)
            if not in_city((r(x), r(y)), city):
                continue
            stops.append([r(x), r(y), osm_id(el)] + list(names(el)))
    points = {"stop": sorted(stops, key=lambda row: row[2])}
    for kind, sets in (("playground", ("playgrounds",)), ("sports", ("pitches",)), ("square", ("parks", "gardens")), ("lamp", ("street_lamps",))):
        rows, ids = [], set()
        for name in sets:
            for el in osm_elements(name):
                if (el["type"], el["id"]) in ids:
                    continue
                ids.add((el["type"], el["id"]))
                x, y = center(el)
                if not in_city((r(x), r(y)), city):
                    continue
                pts = element_points(el)
                # Радиус пятна (м) — для парков и площадок: «рядом» считаем от края, а не от центра.
                rad = max(mf_dist((x, y), p) for p in pts) if len(pts) > 1 else 0.0
                rows.append([r(x), r(y), osm_id(el)] + list(names(el)) + [round(rad, 1)])
        points[kind] = sorted(rows, key=lambda row: row[2])
    yards = []
    for el in osm_elements("residential"):
        for ring in outer_rings(el):
            simple = simplify([list(p) for p in ring], YARD_SIMPLIFY_M)
            # Двор берём, только если ВСЕ вершины внутри города (двор на границе — не наш объект для привязки).
            if not all(in_city(p, city) for p in simple):
                continue
            yards.append(["yard-%d" % el["id"], el["type"]] + list(names(el)) + [simple])
    yards.sort(key=lambda row: (row[0], len(row[-1])))
    with open(os.path.join(OSM_OBJECTS, "SOURCE.json"), encoding="utf-8") as fh:
        src = json.load(fh)
    return {
        "schema": "birge-build3d-existing-v1",
        "purpose": "Настоящие объекты OSM для подсказки «рядом уже есть …» при размещении проекта и привязки к двору "
                   "(yard-<id>, CONTRACT §4). Это существующие объекты, не предложения.",
        "evidence_type": "real (OSM)",
        "source": {"path": "data/civic/astana/osm-objects/", "source_json_sha256": sha256_file(os.path.join(OSM_OBJECTS, "SOURCE.json")),
                   "sets": {x["name"]: {"file": x.get("file"), "osm_base": x.get("osm_base"), "sha256_gzip": x.get("sha256_gzip")}
                            for x in src.get("sets", []) if x["name"] in USED_SETS},
                   "license": "ODbL-1.0", "attribution": ATTRIBUTION},
        "point_fields": ["lon", "lat", "id", "name_ru", "name_kk", "radius_m"],
        "yard_fields": ["id", "osm_type", "name_ru", "name_kk", "ring"],
        "points": points,
        "yards": yards,
    }


def mf_dist(a, b):
    x, y = to_local(a, b)
    return math.hypot(x, y)


def sha256_file(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


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


# Сквер и детская площадка — примеры ВНУТРИ настоящих дворов OSM (landuse=residential) у ул. Сыганак,
# чтобы стартовый вид демо показывал модели, а не одни подписи (UX_REVIEW R11, день 3 #20).
# Пятно (с запасом 3 м) целиком внутри полигона двора; поворот — вдоль самой длинной стороны двора.
YARD_EXAMPLE_CENTER = (71.4009, 51.1276)
YARD_EXAMPLE_KINDS = (("square", 40, 30), ("playground", 24, 18))
YARD_MARGIN_M = 3.0


def point_in_ring_xy(x, y, ring):
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def fit_in_yard(ring_ll, w, d):
    """Место и поворот (азимут, по часовой) для прямоугольника w×d внутри кольца двора или None."""
    c0 = (sum(p[0] for p in ring_ll) / len(ring_ll), sum(p[1] for p in ring_ll) / len(ring_ll))
    ring = [to_local(c0, p) for p in ring_ll]
    best_len, angle = 0, 0.0
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        L = math.hypot(bx - ax, by - ay)
        if L > best_len:
            best_len, angle = L, math.atan2(by - ay, bx - ax)
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    hw, hd = w / 2 + YARD_MARGIN_M, d / 2 + YARD_MARGIN_M
    # Перебор центров по сетке 2 м от центра двора наружу — первый, где все 4 угла и середины сторон внутри.
    cands = []
    for gx in range(int(min(xs)), int(max(xs)) + 1, 2):
        for gy in range(int(min(ys)), int(max(ys)) + 1, 2):
            cands.append((math.hypot(gx, gy), gx, gy))
    cands.sort()
    ca, sa = math.cos(angle), math.sin(angle)
    for _, cx, cy in cands:
        pts = [(sx * hw, sy * hd) for sx in (-1, 0, 1) for sy in (-1, 0, 1) if sx or sy]
        if all(point_in_ring_xy(cx + px * ca - py * sa, cy + px * sa + py * ca, ring) for px, py in pts):
            lon, lat = from_local(c0, (cx, cy))
            # Ось x модели (ширина) — вдоль стороны angle; азимут оси x = 90 + rotation_deg.
            bearing_x = (90 - math.degrees(angle)) % 360
            return (lon, lat), round((bearing_x - 90) % 360)
    return None


def yard_examples(existing):
    out = []
    used = set()
    yards = sorted(existing["yards"], key=lambda y: mf_dist(YARD_EXAMPLE_CENTER, (
        sum(p[0] for p in y[4]) / len(y[4]), sum(p[1] for p in y[4]) / len(y[4]))))
    for kind, w, d in YARD_EXAMPLE_KINDS:
        for y in yards[:40]:
            if y[0] in used:
                continue
            fit = fit_in_yard(y[4], w, d)
            if not fit:
                continue
            (lon, lat), rot = fit
            used.add(y[0])
            out.append({"id": "p-demo-%s-%s" % (kind, y[0]), "kind": kind,
                        "geometry": {"type": "Point", "coordinates": [r(lon), r(lat)]}, "rotation_deg": rot,
                        "status": "proposal", "year": 2027, "district": "nura", "demo": True,
                        "created_at": "2026-10-10T12:00:00+05:00", "votes_up": 41 if kind == "square" else 87,
                        "votes_down": 3 if kind == "square" else 6, "near_street": None,
                        "target": {"kind": "area", "id": y[0], "label_ru": y[2], "label_kk": y[3]}})
            break
    return out


def write_demo_proposals(graph, out_dir=None):
    data = {
        "schema": "birge-proposals-fixture-v1",
        "purpose": "Заглушка GET /api/civic/v2/proposals (CONTRACT §7) до подключения R06. Только примеры (demo: true).",
        "source": {"streets": "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json",
                   "edges": LIGHT_EDGES + [STOP_EDGE], "license": "ODbL-1.0", "attribution": ATTRIBUTION},
        "proposals": demo_proposals(graph) + yard_examples(build_existing()),
    }
    path = os.path.join(out_dir or OUT, "proposals.fixture.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return path


if __name__ == "__main__":
    main()
