# -*- coding: utf-8 -*-
"""
AST-A04 — проверка на РЕАЛЬНОМ образце (kind=observed/derived).
Вход: сохранённый ответ Overpass из репозитория STUPITS
  data/geo_sources/astana_districts_overpass.json
  (osm_base 2026-09-22T08:45:51Z, загружен 2026-09-23T11:28:06Z, © OpenStreetMap contributors, ODbL).
Это общественная карта, НЕ юридические границы.
Проверяет:
  1) состав и площади районов Астаны по OSM (геодезически, WGS84);
  2) целостность объединения (дыры, перекрытия);
  3) какие единицы Акмолинской области примыкают к городу и сколько их площади
     попадает в буфер 2/5/10 км — краевой эффект для расчёта доступности.
Запуск: python3 AST_A04_osm_boundary_check.py <путь к astana_districts_overpass.json>
"""
import json, sys
from shapely.geometry import LineString, Polygon, MultiPolygon, mapping
from shapely.ops import polygonize, unary_union, transform
from pyproj import Geod, Transformer
import shapely, pyproj

SRC = sys.argv[1]
ASTANA_IDS = {3479876: "esil", 3482819: "almaty", 3486954: "saryarka",
              8593081: "baikonur", 20593940: "nura", 19733918: "saraishyk"}
geod = Geod(ellps="WGS84")
# UTM 42N подходит для Астаны (~71.4E) для буферов в метрах
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32642", always_xy=True).transform
to_wgs = Transformer.from_crs("EPSG:32642", "EPSG:4326", always_xy=True).transform

def rel_polygon(el):
    outer, inner = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or "geometry" not in m:
            continue
        line = LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
        (inner if m.get("role") == "inner" else outer).append(line)
    po = unary_union(list(polygonize(unary_union(outer)))) if outer else Polygon()
    pi = unary_union(list(polygonize(unary_union(inner)))) if inner else Polygon()
    return po.difference(pi) if not pi.is_empty else po

def geo_area_km2(g):
    return abs(geod.geometry_area_perimeter(g)[0]) / 1e6

def main():
    d = json.load(open(SRC, encoding="utf-8"))
    out = {"input": SRC, "osm_base": d["osm3s"]["timestamp_osm_base"],
           "retrieved_at": d.get("_provenance", {}).get("retrieved_at"),
           "versions": {"shapely": shapely.__version__, "pyproj": pyproj.__version__},
           "units": []}
    polys = {}
    for el in d["elements"]:
        t = el.get("tags", {})
        g = rel_polygon(el)
        polys[el["id"]] = g
        out["units"].append({
            "osm_relation": el["id"], "name_ru": t.get("name:ru"), "name_kk": t.get("name:kk") or t.get("name"),
            "admin_level": t.get("admin_level"), "addr_region": t.get("addr:region"),
            "kato_tag": t.get("kato"), "wikidata": t.get("wikidata"),
            "is_astana_district": el["id"] in ASTANA_IDS,
            "geom_valid": bool(g.is_valid), "geom_type": g.geom_type,
            "area_km2_geodesic": round(geo_area_km2(g), 1) if not g.is_empty else None})
    ast = [polys[i] for i in ASTANA_IDS]
    union = unary_union(ast)
    # перекрытия между районами Астаны
    ids = list(ASTANA_IDS)
    overl = []
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            inter = polys[ids[a]].intersection(polys[ids[b]])
            ar = geo_area_km2(inter) if inter.area > 0 else 0.0
            if ar > 0.01:
                overl.append({"pair": [ASTANA_IDS[ids[a]], ASTANA_IDS[ids[b]]], "km2": round(ar, 3)})
    parts = list(union.geoms) if isinstance(union, MultiPolygon) else [union]
    holes = [Polygon(r) for p in parts for r in p.interiors]
    out["astana_union"] = {
        "area_km2_geodesic": round(geo_area_km2(union), 1),
        "sum_of_districts_km2": round(sum(geo_area_km2(p) for p in ast), 1),
        "parts": len(parts), "interior_holes": len(holes),
        "holes_area_km2": [round(geo_area_km2(h), 3) for h in sorted(holes, key=lambda h: -h.area)[:10]],
        "district_overlaps_gt_0_01km2": overl}
    # соседи: общая граница и площадь в буферах
    u_utm = transform(to_utm, union)
    neigh = []
    for el in d["elements"]:
        if el["id"] in ASTANA_IDS:
            continue
        g = polys[el["id"]]
        g_utm = transform(to_utm, g)
        shared = u_utm.boundary.intersection(g_utm.boundary).length / 1000
        ov = geo_area_km2(union.intersection(g)) if union.intersection(g).area > 0 else 0.0
        row = {"osm_relation": el["id"], "name_ru": el["tags"].get("name:ru"),
               "shared_boundary_km": round(shared, 1), "overlap_with_astana_km2": round(ov, 3),
               "min_distance_km": round(u_utm.distance(g_utm) / 1000, 2)}
        for km in (2, 5, 10):
            ring = u_utm.buffer(km * 1000).difference(u_utm)
            row[f"area_in_{km}km_buffer_km2"] = round(ring.intersection(g_utm).area / 1e6, 1)
        neigh.append(row)
    out["neighbours_outside_astana"] = sorted(neigh, key=lambda r: -r["shared_boundary_km"])
    ring_total = {km: round(u_utm.buffer(km * 1000).difference(u_utm).area / 1e6, 1) for km in (2, 5, 10)}
    out["buffer_ring_area_km2"] = ring_total
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
