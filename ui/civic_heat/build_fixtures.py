"""Собирает фикстуры R07 из НАСТОЯЩИХ данных OSM (запускать вручную; результат лежит в Git).

    python -m ui.civic_heat.build_fixtures

Что строится:
  ui/civic_heat/fixtures/targets_demo.json — цели для демо-жалоб: участки улиц (форма ребра пешеходного
      графа OSM, без правок), реальные остановки, дворы (landuse=residential), детские и контейнерные площадки
      из data/civic/astana/osm-objects/ (LOCAL-1) и ячейки ~150 м только для «запахов»;
  ui/civic_heat/fixtures/osm_street_labels.json — подписи безымянных объектов OSM по ближайшей улице;
  web/civic/heat/fixtures/basemap-nura.geojson — улицы крупного плана Нуры для офлайн-подложки демо;
  web/civic/heat/fixtures/basemap-city.geojson — магистрали города и границы районов (мелкий масштаб).

Отбор детерминированный: одинаковые данные → одинаковые файлы. Объекты не выдумываются.
Место промзоны в OSM-наборе нет (landuse=industrial не выгружали) — «запахи» пока на ячейках у Коргалжинского шоссе.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from . import geo, osm_objects
from .config import GRAPH_PATH, ROOT
from .targets import kk_street_from_ru, near_street_labels, segment_labels, short_street_ru

SNAPSHOT = ROOT / "data" / "civic" / "astana" / "osm-walking" / "overpass.json.gz"
OUT_TARGETS = Path(__file__).resolve().parent / "fixtures" / "targets_demo.json"
OUT_STREET_LABELS = Path(__file__).resolve().parent / "fixtures" / "osm_street_labels.json"
OUT_BASEMAP_NURA = ROOT / "web" / "civic" / "heat" / "fixtures" / "basemap-nura.geojson"
OUT_BASEMAP_CITY = ROOT / "web" / "civic" / "heat" / "fixtures" / "basemap-city.geojson"

# Крупный план Нуры: самая плотная по улицам часть района (подсчёт рёбер по сетке 1 км).
FOCUS = (71.405, 51.128)
FOCUS_RADIUS_M = 2600.0
BASEMAP_HALF_M = 2600.0
KK_LETTERS = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]")
MAJOR = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}
STREET_CLASSES = MAJOR | {"tertiary", "tertiary_link", "residential", "living_street", "unclassified", "service", "pedestrian", "footway", "path", "cycleway"}


def _way_id(edge_id: str) -> int | None:
    m = re.match(r"^osm-w(\d+)-\d+$", edge_id)
    return int(m.group(1)) if m else None


def load_inputs():
    graph = json.loads(Path(GRAPH_PATH).read_text("utf-8"))
    snap = json.loads(gzip.open(SNAPSHOT).read().decode("utf-8"))
    ways = {e["id"]: e for e in snap["elements"] if e["type"] == "way"}
    nodes = {e["id"]: e for e in snap["elements"] if e["type"] == "node"}
    return graph, ways, nodes


def kk_name(way: dict | None) -> str | None:
    """Казахское название улицы из OSM: name:kk, а если его нет — name, если он по-казахски."""
    if not way:
        return None
    tags = way.get("tags", {})
    if tags.get("name:kk"):
        return tags["name:kk"]
    if tags.get("name") and KK_LETTERS.search(tags["name"]):
        return tags["name"]
    return None


def build():
    graph, ways, nodes = load_inputs()
    edges = graph["edges"]
    by_node = defaultdict(list)
    for e in edges:
        by_node[e["from"]].append(e)
        by_node[e["to"]].append(e)

    def kk_of_edge(e):
        return kk_name(ways.get(_way_id(e["id"])))

    def cross_street(node_id, own_name):
        """Название пересекающей улицы в конце ребра (для подписи «от … до …»)."""
        for other in sorted(by_node.get(node_id, []), key=lambda x: x["id"]):
            if other.get("name") and other["name"] != own_name:
                return other["name"], kk_of_edge(other)
        return None, None

    def nearest_street(pt, max_m=250.0):
        best = None
        for e in near_edges:
            if not e.get("name"):
                continue
            d = geo.haversine_m(pt, e["_mid"])
            if d <= max_m and (best is None or d < best[0]):
                best = (d, e)
        return best[1] if best else None

    # Рёбра около фокуса Нуры (с серединой и районом)
    near_edges = []
    for e in edges:
        mid = geo.line_midpoint(e["geometry"])
        if geo.haversine_m(mid, FOCUS) > FOCUS_RADIUS_M + 1500:
            continue
        e = dict(e)
        e["_mid"] = mid
        e["_district"] = geo.district_of(mid)
        near_edges.append(e)

    targets = {}

    def add_segment(e, role):
        name = e.get("name")
        fr, fr_kk = cross_street(e["from"], name)
        to, to_kk = cross_street(e["to"], name)
        ru, kk = segment_labels(name, kk_of_edge(e), fr, to, fr_kk, to_kk)
        targets[e["id"]] = {
            "kind": "segment", "role": role, "geometry": {"type": "LineString", "coordinates": e["geometry"]},
            "label_ru": ru, "label_kk": kk, "district": e.get("_district") or geo.district_of(geo.line_midpoint(e["geometry"])),
            "street_ru": name, "length_m": round(e.get("length_m") or geo.line_length_m(e["geometry"]), 1),
            "source": "osm-walking-graph", "osm_way_id": _way_id(e["id"]),
        }

    # --- Участки улиц Нуры: по одному лучшему ребру на улицу (длина 120–450 м, ближе к фокусу) ---
    best_by_street = {}
    for e in near_edges:
        name = e.get("name")
        L = e.get("length_m") or 0
        if not name or e["_district"] != "nura" or not 120 <= L <= 450:
            continue
        way = ways.get(_way_id(e["id"]))
        hw = (way or {}).get("tags", {}).get("highway")
        if hw not in STREET_CLASSES or hw in ("footway", "path", "cycleway", "service"):
            continue
        d = geo.haversine_m(e["_mid"], FOCUS)
        if d > FOCUS_RADIUS_M:
            continue
        if name not in best_by_street or d < best_by_street[name][0]:
            best_by_street[name] = (d, e)
    streets = sorted(best_by_street.items(), key=lambda kv: (kv[1][0], kv[0]))
    roles = ["snow"] * 7 + ["roads"] * 3 + ["sidewalks"] * 2 + ["lighting"] * 2 + ["parking"] * 2
    for (name, (_, e)), role in zip(streets, roles):
        add_segment(e, role)

    # --- Реальные объекты OSM (LOCAL-1): дворы жилых комплексов, площадки, контейнерные площадки ---
    objs = osm_objects.load()

    def real_near(subtype, n, roles, min_gap_m=250.0, need_name=False, max_area_m2=None):
        """n реальных объектов подтипа у фокуса Нуры: ближе к центру, не слипаются, подписи не повторяются."""
        cands = []
        for tid, it in objs.items():
            if it["subtype"] != subtype or it["district"] != "nura":
                continue
            if need_name and it.get("needs_street_label"):
                continue
            anchor = geo.anchor_of(it["geometry"])
            d = geo.haversine_m(anchor, FOCUS)
            if d > FOCUS_RADIUS_M:
                continue
            if max_area_m2 and it["geometry"]["type"] != "Point" and polygon_area_m2(it["geometry"]) > max_area_m2:
                continue
            cands.append((d, tid, it, anchor))
        cands.sort(key=lambda x: (x[0], x[1]))
        picked = []
        for d, tid, it, anchor in cands:
            if any(geo.haversine_m(anchor, q) < min_gap_m for q in picked_points):
                continue
            label_ru, label_kk = real_labels(tid, it)
            if any(v.get("label_ru") == label_ru for v in targets.values()):
                continue  # одинаковые подписи в списке «Горячие места» сбивают с толку
            role = roles[len(picked)]
            targets[tid] = {"kind": it["kind"], "subtype": subtype, "role": role, "geometry": it["geometry"],
                            "label_ru": label_ru, "label_kk": label_kk, "district": it["district"],
                            "source": it["source"], "osm": it["osm"]}
            picked.append(tid)
            picked_points.append(anchor)
            if len(picked) == n:
                break
        return picked

    def real_labels(tid, it):
        if not it.get("needs_street_label"):
            return it["label_ru"], it["label_kk"]
        lab = street_labels.get(tid)
        return tuple(lab) if lab else (it["label_ru"], it["label_kk"])

    street_labels = write_street_labels(objs, edges, kk_of_edge)
    picked_points: list = []
    # Двор = landuse=residential (жилой комплекс). Огромные массивы (> 0.12 км²) не берём — это уже не двор.
    real_near("yard", 7, ["yards", "yards", "waste", "lighting", "yards", "parking", "utilities"], max_area_m2=120000)
    real_near("playground", 2, ["playground", "playground"])
    real_near("waste_disposal", 2, ["waste_site", "waste_site"], min_gap_m=150.0)

    # --- Запахи: кварталы на окраине Нуры у Коргалжинского шоссе (место промзоны не проверено) ---
    korg = [e for e in edges if e.get("name") == "Коргалжинское шоссе"]
    korg_nura = []
    for e in korg:
        mid = geo.line_midpoint(e["geometry"])
        if geo.district_of(mid) == "nura":
            korg_nura.append((mid, e))
    korg_nura.sort(key=lambda x: (round(x[0][0], 4), x[1]["id"]))
    if korg_nura:
        base = korg_nura[len(korg_nura) // 3][0]
        bx = geo.cell_id_for(base)
        ix, iy = map(int, bx.split("-")[1:])
        kk_korg = kk_of_edge(korg_nura[0][1]) or "Қорғалжын тас жолы"
        for dx, dy in ((0, 1), (1, 1), (0, 2)):
            cid = f"cell-{ix + dx}-{iy + dy}"
            poly = geo.cell_polygon(cid)
            targets[cid] = {"kind": "area", "role": "smell_air", "geometry": poly,
                            "label_ru": "Квартал у Коргалжинского шоссе", "label_kk": f"{kk_korg} маңындағы орам",
                            "district": geo.district_of(geo.anchor_of(poly)), "source": "cell-grid-150m"}

    # --- Остановки Нуры: реальные узлы OSM highway=bus_stop (LOCAL-1), только с названием ---
    real_near("bus_stop", 5, ["transport"] * 5, min_gap_m=200.0, need_name=True)

    # --- Другие районы: по 2 настоящих участка у центра района (для вида «весь город») ---
    dist = geo.districts()
    for d_id in sorted(dist):
        if d_id == "nura":
            continue
        center = geo.anchor_of(dist[d_id]["geometry"])
        cands = []
        for e in edges:
            L = e.get("length_m") or 0
            if not e.get("name") or not 150 <= L <= 500:
                continue
            mid = geo.line_midpoint(e["geometry"])
            dd = geo.haversine_m(mid, center)
            if dd < 2500 and geo.district_of(mid) == d_id:
                cands.append((dd, e["id"], e))
        cands.sort(key=lambda x: (x[0], x[1]))
        used = set()
        n_added = 0
        for _, _, e in cands:
            if e["name"] in used:
                continue
            used.add(e["name"])
            e = dict(e)
            e["_district"] = d_id
            add_segment(e, "city_snow" if n_added == 0 else "city_roads")
            n_added += 1
            if n_added == 2:
                break

    meta = {
        "built_by": "ui/civic_heat/build_fixtures.py",
        "graph": {"id": graph.get("id"), "digest": graph.get("digest")},
        "osm_snapshot": json.loads((SNAPSHOT.parent / "SOURCE.json").read_text("utf-8")).get("snapshot_at"),
        "license": "ODbL-1.0 © OpenStreetMap contributors",
        "note": "Формы и названия — из OSM без правок. Роли (snow, yards…) — только для демо-жалоб (synthetic).",
        "focus": FOCUS,
    }
    for v in targets.values():
        v["geometry"] = _round_geom(v["geometry"])
    OUT_TARGETS.parent.mkdir(parents=True, exist_ok=True)
    OUT_TARGETS.write_text(json.dumps({"_meta": meta, "targets": dict(sorted(targets.items()))}, ensure_ascii=False, indent=1) + "\n", "utf-8")
    write_basemaps(graph, ways, nodes)
    return targets


def polygon_area_m2(geometry) -> float:
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    total = 0.0
    for poly in polys:
        ring = poly[0]
        kx = 111320 * math.cos(math.radians(ring[0][1]))
        ky = 110574
        total += abs(sum(ring[i][0] * kx * ring[i + 1][1] * ky - ring[i + 1][0] * kx * ring[i][1] * ky for i in range(len(ring) - 1)) / 2)
    return total


def write_street_labels(objs, edges, kk_of_edge) -> dict:
    """Подписи безымянных объектов OSM по ближайшей улице («Остановка у ул. …») — заранее, чтобы
    сервер не грузил граф улиц (2–3 с) на первом запросе. Казахское название улицы — из OSM name:kk."""
    cell = 0.003
    grid: dict = {}
    for e in edges:
        if e.get("name"):
            mid = geo.line_midpoint(e["geometry"])
            grid.setdefault((int(mid[0] // cell), int(mid[1] // cell)), []).append((mid, e))
    out = {}
    for tid, it in sorted(objs.items()):
        if not it.get("needs_street_label"):
            continue
        anchor = geo.anchor_of(it["geometry"])
        if not anchor:
            continue
        cx, cy = int(anchor[0] // cell), int(anchor[1] // cell)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for mid, e in grid.get((cx + dx, cy + dy), ()):
                    d = geo.haversine_m(anchor, mid)
                    if d <= 250 and (best is None or d < best[0] or (d == best[0] and e["id"] < best[1]["id"])):
                        best = (d, e)
        if best:
            lab = near_street_labels(it["subtype"], best[1]["name"], kk_of_edge(best[1]))
            if lab:
                out[tid] = list(lab)
    OUT_STREET_LABELS.write_text(json.dumps({"_meta": {"built_by": "ui/civic_heat/build_fixtures.py",
                                                       "license": "ODbL-1.0 © OpenStreetMap contributors",
                                                       "note": "Подпись безымянного объекта OSM по ближайшей улице (≤ 250 м)."},
                                             "labels": out}, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    return out


def edges_near_point(edges, pt, radius_m=300.0):
    dlat = radius_m / 110574.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(pt[1])))
    for e in edges:
        c = e["geometry"][0]
        if abs(c[0] - pt[0]) <= dlon * 3 and abs(c[1] - pt[1]) <= dlat * 3:
            yield e


def _round_geom(g, digits=6):
    def r(c):
        if c and isinstance(c[0], (int, float)):
            return [round(c[0], digits), round(c[1], digits)]
        return [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def write_basemaps(graph, ways, nodes):
    """Офлайн-подложка демо: настоящие улицы OSM (тайлы в облаке недоступны, на финале может не быть сети)."""
    half_lat = BASEMAP_HALF_M / 110574.0
    half_lon = BASEMAP_HALF_M / (111320.0 * math.cos(math.radians(FOCUS[1])))
    box = (FOCUS[0] - half_lon, FOCUS[1] - half_lat, FOCUS[0] + half_lon, FOCUS[1] + half_lat)
    feats = []
    for e in graph["edges"]:
        coords = e["geometry"]
        if not any(box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3] for c in coords):
            continue
        hw = (ways.get(_way_id(e["id"])) or {}).get("tags", {}).get("highway", "")
        if hw in ("footway", "path", "cycleway", "steps", "track", "corridor", "elevator", ""):
            continue  # тротуары и тропинки на подложке не нужны: улицы и дворовые проезды видны и так
        cls = "major" if hw in MAJOR else ("street" if hw in ("tertiary", "tertiary_link", "residential", "living_street", "unclassified", "pedestrian") else "minor")
        props = {"c": cls}
        if e.get("name") and cls != "minor":
            props["n"] = e["name"]
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": [[round(c[0], 5), round(c[1], 5)] for c in coords]}})
    nura = {"type": "FeatureCollection", "name": "basemap-nura", "attribution": "© OpenStreetMap contributors (ODbL)",
            "bbox": [round(v, 5) for v in box], "features": feats}
    OUT_BASEMAP_NURA.parent.mkdir(parents=True, exist_ok=True)
    OUT_BASEMAP_NURA.write_text(json.dumps(nura, ensure_ascii=False, separators=(",", ":")), "utf-8")

    city = []
    for w in ways.values():
        hw = w.get("tags", {}).get("highway")
        if hw not in ("motorway", "trunk", "primary", "secondary"):
            continue
        coords = [[round(nodes[n]["lon"], 4), round(nodes[n]["lat"], 4)] for n in w.get("nodes", []) if n in nodes]
        if len(coords) >= 2:
            city.append({"type": "Feature", "properties": {"c": "major"}, "geometry": {"type": "LineString", "coordinates": coords}})
    for d in geo.districts().values():
        for rings in d["polys"]:
            city.append({"type": "Feature", "properties": {"c": "district", "id": d["id"]},
                         "geometry": {"type": "LineString", "coordinates": [[round(x, 4), round(y, 4)] for x, y in rings[0]]}})
    OUT_BASEMAP_CITY.write_text(json.dumps({"type": "FeatureCollection", "name": "basemap-city",
                                            "attribution": "© OpenStreetMap contributors (ODbL)", "features": city},
                                           ensure_ascii=False, separators=(",", ":")), "utf-8")


if __name__ == "__main__":
    t = build()
    from collections import Counter

    print("целей:", len(t), dict(Counter(v["role"] for v in t.values())))
    for p in (OUT_TARGETS, OUT_BASEMAP_NURA, OUT_BASEMAP_CITY):
        print(p.relative_to(ROOT), round(p.stat().st_size / 1024), "КБ")
