#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AST-A05 — изолированный эксперимент для Астаны.
Часть A (REAL, derived): реальные OSM-полигоны районов Астаны из кэша репозитория STUPITS
  (data/astana_districts.geojson, data/geo_sources/astana_districts_overpass.json;
   © OpenStreetMap contributors, ODbL; снимок базы Overpass 2026-09-22T08:45:51Z).
  Проверяет: (1) наличие ключа КАТО для стыковки со статистикой; (2) площади;
  (3) пустоты внутри объединения районов; (4) долю территории у внутренних границ
  (зона риска ошибочной привязки объекта к району); (5) смежность с единицами
  Акмолинской области (агломерация).
Часть B (SYNTHETIC): ловушки сопоставления названий, специфичные для Астаны
  (переименование Нур-Султан/Астана, казахские падежные формы, разные владельцы).
Запуск: python3 AST_A05_experiment.py <путь к корню репозитория STUPITS>
"""
import json, math, re, sys, platform
from pathlib import Path
import numpy as np
import shapely, pyproj
from shapely.geometry import shape, LineString, mapping
from shapely.ops import transform, unary_union, polygonize, linemerge

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
GJ = json.load(open(ROOT / "data/astana_districts.geojson", encoding="utf-8"))
OV = json.load(open(ROOT / "data/geo_sources/astana_districts_overpass.json", encoding="utf-8"))
to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32642", always_xy=True).transform  # UTM 42N
geod = pyproj.Geod(ellps="WGS84")

out = {"meta": {"python": sys.version.split()[0], "numpy": np.__version__, "shapely": shapely.__version__,
                "pyproj": pyproj.__version__, "platform": platform.platform(),
                "input_geojson_generated_at": GJ["metadata"]["generated_at"],
                "input_osm_base_timestamp": GJ["metadata"]["osm_base_timestamp"],
                "crs_metric": "EPSG:32642 (UTM 42N)", "license": "ODbL, © OpenStreetMap contributors"}}

# ---------- A1: районы, КАТО, площади ----------
tags_by_rel = {e["id"]: e.get("tags", {}) for e in OV["elements"] if e["type"] == "relation"}
dist = {}
rows = []
for f in GJ["features"]:
    p = f["properties"]; g = shape(f["geometry"]); gu = transform(to_utm, g)
    ga = abs(geod.geometry_area_perimeter(g)[0]) / 1e6
    t = tags_by_rel.get(p["osm_id"], {})
    dist[p["id"]] = {"geom": g, "utm": gu, "name": p["name"]}
    rows.append({"id": p["id"], "name": p["name"], "osm_id": p["osm_id"], "osm_admin_level": t.get("admin_level"),
                 "kato": t.get("kato"), "wikidata": t.get("wikidata"), "valid": g.is_valid,
                 "area_km2_utm": round(gu.area / 1e6, 2), "area_km2_geodesic": round(ga, 2),
                 "area_km2_repo": p.get("area_km2"), "scoring_enabled_in_stupits": p.get("scoring_enabled")})
out["A1_districts"] = rows
out["A1_kato_present"] = sum(1 for r in rows if r["kato"])

# ---------- A2: объединение и пустоты ----------
U = unary_union([d["utm"] for d in dist.values()])
holes = []
for poly in (U.geoms if U.geom_type == "MultiPolygon" else [U]):
    for ring in poly.interiors:
        from shapely.geometry import Polygon
        h = Polygon(ring)
        holes.append(round(h.area / 1e6, 4))
pair_overlap = 0.0
ids = list(dist)
for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
        pair_overlap += dist[ids[i]]["utm"].intersection(dist[ids[j]]["utm"]).area
inv = pyproj.Transformer.from_crs("EPSG:32642", "EPSG:4326", always_xy=True).transform
parts = []
for p in sorted(U.geoms if hasattr(U, "geoms") else [U], key=lambda p: -p.area):
    c = transform(inv, p.centroid)
    parts.append({"area_km2": round(p.area / 1e6, 3), "centroid_lon": round(c.x, 4), "centroid_lat": round(c.y, 4),
                  "districts": [k for k, d in dist.items() if d["utm"].intersection(p).area > 1e4]})
out["A2_union_parts"] = parts
out["A2_union"] = {"geom_type": U.geom_type, "n_parts": len(U.geoms) if hasattr(U, "geoms") else 1,
                   "area_km2": round(U.area / 1e6, 2), "sum_district_area_km2": round(sum(d["utm"].area for d in dist.values()) / 1e6, 2),
                   "pairwise_overlap_km2": round(pair_overlap / 1e6, 6),
                   "interior_holes_count": len(holes), "interior_holes_km2": sorted(holes, reverse=True)[:10],
                   "interior_holes_total_km2": round(sum(holes), 3)}

# ---------- A3: доля территории у внутренних границ ----------
ext = U.boundary.buffer(5)
internal = unary_union([d["utm"].boundary for d in dist.values()]).difference(ext)
out["A3_internal_boundary_km"] = round(internal.length / 1000 / 2, 1)  # каждая общая граница учтена дважды
a3 = {}
for k, d in dist.items():
    a3[k] = {}
    for m in (100, 250, 500):
        a3[k][str(m)] = round(d["utm"].intersection(internal.buffer(m)).area / d["utm"].area, 4)
tot = {}
for m in (100, 250, 500):
    tot[str(m)] = round(U.intersection(internal.buffer(m)).area / U.area, 4)
out["A3_share_of_area_near_internal_boundary"] = {"by_district": a3, "city_union": tot,
    "interpretation": "доля площади в пределах m метров от границы между районами; не доля населения или школ"}

# ---------- A4: смежность с единицами Акмолинской области ----------
def relation_polygon(el):
    lines = [LineString([(pt["lon"], pt["lat"]) for pt in m["geometry"]])
             for m in el.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry")]
    polys = list(polygonize(linemerge(unary_union(lines))))
    return unary_union(polys) if polys else None
neighbors = []
astana_ids = {f["properties"]["osm_id"] for f in GJ["features"]}
for el in OV["elements"]:
    if el["type"] != "relation" or el["id"] in astana_ids: continue
    g = relation_polygon(el)
    t = el.get("tags", {})
    if g is None or g.is_empty:
        neighbors.append({"osm_id": el["id"], "name_ru": t.get("name:ru"), "assembled": False}); continue
    gu = transform(to_utm, g)
    shared = U.boundary.intersection(gu.buffer(50)).length / 1000
    neighbors.append({"osm_id": el["id"], "name_ru": t.get("name:ru"), "admin_level": t.get("admin_level"),
                      "assembled": True, "area_km2_in_bbox_assembly": round(gu.area / 1e6, 1),
                      "shared_border_with_astana_union_km": round(shared, 1),
                      "overlap_with_astana_union_km2": round(gu.intersection(U).area / 1e6, 3),
                      "overlap_by_district_km2": {k: round(gu.intersection(d["utm"]).area / 1e6, 3) for k, d in dist.items() if gu.intersection(d["utm"]).area > 1e4},
                      "member_roles": {r: sum(1 for m in el.get("members", []) if m.get("role") == r) for r in {m.get("role") for m in el.get("members", [])}},
                      "assembly_note": "контур собран polygonize из outer-путей; inner-члены не вычитались"})
out["A4_neighbors"] = neighbors
out["A4_union_perimeter_km"] = round(U.exterior.length / 1000 if U.geom_type == "Polygon" else sum(p.exterior.length for p in U.geoms) / 1000, 1)

# ---------- B: ловушки названий (SYNTHETIC) ----------
NUM_RE = re.compile(r"(?:№|N°|No\.?|#)\s*(\d{1,3})|\b(\d{1,3})\s*(?:мектеп|школ|бала|ясли|сад)", re.I)
NUM_RE2 = re.compile(r"(?:школ\w*|лице\w*|гимнази\w*|мектеп\w*|сад\w*|балабақша\w*)\s+(\d{1,3})\b", re.I)
def norm(s): return " ".join(s.lower().replace("ё", "е").replace("«", " ").replace("»", " ").replace('"', " ").split())
def kind(s):
    s = norm(s)
    if re.search(r"сад|балабақша|бөбекжай|ясли", s): return "kg"
    if re.search(r"школ|мектеп|гимназ|лице|nis|ниш|зияткерлік", s): return "school"
    return "unknown"
def number(s):
    m = NUM_RE.search(norm(s))
    if m: return int(m.group(1) or m.group(2))
    m = NUM_RE2.search(norm(s)); return int(m.group(1)) if m else None
BASE_STOP = {"гу", "кгу", "гккп", "на", "пхв", "коммунальное", "государственное", "учреждение", "управления",
             "образования", "города", "имени", "атындағы", "акимата", "әкімдігінің"}
CITY_STOP = {"астаны", "астана", "нур", "султан", "нұр", "сұлтан", "қаласы", "қаласының", "nur", "sultan", "astana"}
def toks(s, stop): return {t for t in re.findall(r"[a-zа-яәіңғүұқөһ]+", norm(s)) if t not in stop and len(t) > 2}
def match(reg, osm, stop):
    res = []
    for r in reg:
        auto, review = [], []
        kr, nr = kind(r["name"]), number(r["name"])
        for o in osm:
            ko, no = kind(o["name"]), number(o["name"])
            if "unknown" not in (kr, ko) and kr != ko: continue
            d = math.hypot(r["x"] - o["x"], r["y"] - o["y"])
            a, b = toks(r["name"], stop), toks(o["name"], stop)
            jac = len(a & b) / len(a | b) if a and b else 0.0
            if nr is not None and nr == no:
                if d <= 300 and kr == ko: auto.append((o["id"], d))
                elif d <= 1000: review.append((o["id"], d))
            elif nr is not None and no is not None: continue
            elif nr is None and no is None and jac >= 0.5 and d <= 150:
                (auto if kr == ko else review).append((o["id"], d))
            elif d <= 100: review.append((o["id"], d))
        if len(auto) == 1 and not review: res.append((r["id"], auto[0][0], "auto"))
        elif auto or review: res.append((r["id"], "REVIEW", ";".join(f"{i}@{d:.0f}м" for i, d in auto + review)))
        else: res.append((r["id"], None, "нет кандидата"))
    return res
REG = [
 {"id": "R1", "name": "ГУ «Школа-лицей № 59» акимата города Нур-Султан", "x": 0, "y": 0},
 {"id": "R2", "name": "№ 90 мектеп-гимназиясы", "x": 1500, "y": 200},
 {"id": "R3", "name": "Назарбаев Зияткерлік мектебі (тестовая)", "x": 3000, "y": 3000},
 {"id": "R4", "name": "Ясли-сад № 59 «Тестовый»", "x": 60, "y": 40},
 {"id": "R5", "name": "Частная школа «Бета» города Астаны", "x": 2000, "y": 2500},
 {"id": "R6", "name": "Школа-гимназия № 7", "x": 800, "y": 2600}]
OSM = [
 {"id": "O1", "name": "Мектеп-лицей №59", "x": 40, "y": -30},
 {"id": "O2", "name": "Школа-гимназия 90", "x": 1480, "y": 260},
 {"id": "O3", "name": "Назарбаев Зияткерлік мектебі", "x": 3050, "y": 2980},
 {"id": "O4", "name": "Балабақша №59", "x": 70, "y": 50},
 {"id": "O5", "name": "Бета Астана", "x": 2010, "y": 2490},
 {"id": "O6", "name": "Школа-гимназия № 7", "x": 820, "y": 2610},
 {"id": "O6b", "name": "Школа-гимназия № 7 (новое здание)", "x": 1300, "y": 2900}]
TRUTH = {"R1": "O1", "R2": "O2", "R3": "O3", "R4": "O4", "R5": "O5", "R6": "O6"}
def score(res):
    auto = [(r, o) for r, o, _ in res if o not in (None, "REVIEW")]
    return {"auto": len(auto), "auto_correct": sum(1 for r, o in auto if TRUTH[r] == o),
            "false_auto": sum(1 for r, o in auto if TRUTH[r] != o),
            "review": sum(1 for _, o, _ in res if o == "REVIEW"),
            "none": sum(1 for _, o, _ in res if o is None),
            "results": [{"reg": r, "osm": o, "rule": w, "truth": TRUTH[r]} for r, o, w in res]}
out["B_name_matching_synthetic"] = {"kind": "synthetic",
    "without_city_stopwords": score(match(REG, OSM, BASE_STOP)),
    "with_city_stopwords": score(match(REG, OSM, BASE_STOP | CITY_STOP)),
    "note": "6 синтетических записей; проверяет поведение правил на ловушках Астаны, не точность на реальных данных."}

def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.integer,)): return int(o)
    return o
json.dump(clean(out), open("AST_A05_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(clean(out), ensure_ascii=False, indent=1))
