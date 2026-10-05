"""K10-E01: district coverage/overlap check on Overture division_area extracts.

Inputs: <raw_dir>/<city>_division_area.jsonl from overture_extract.py.
Optional: repo data/astana_districts.geojson for comparison with the product layer.
Output: JSON with geodesic areas (km2), coverage of city polygon by its districts,
pairwise overlaps, and per-district area comparison with the product layer.
"""
import json
import sys
from itertools import combinations

import shapely
from pyproj import Geod

GEOD = Geod(ellps="WGS84")
CITY_REGION = {"shymkent": "KZ-79", "astana": "KZ-71"}


def km2(g):
    return abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6


def osm_ref(row):
    for s in row.get("sources") or []:
        if s.get("dataset") == "OpenStreetMap" and s.get("property") in ("", None):
            return s.get("record_id")
    for s in row.get("sources") or []:
        if s.get("dataset") == "OpenStreetMap":
            return s.get("record_id")
    return None


def load(raw_dir, city):
    rows = [json.loads(l) for l in open(f"{raw_dir}/{city}_division_area.jsonl", encoding="utf-8")]
    reg = CITY_REGION[city]
    region = [r for r in rows if r["subtype"] == "region" and r.get("region") == reg]
    districts = [r for r in rows if r.get("region") == reg and r["subtype"] == "county"]
    # Astana's Saraishyk is tagged admin_level=8 in OSM and lands in Overture as "locality"
    extra = [r for r in rows if r.get("region") == reg and r["subtype"] == "locality"
             and "ауданы" in (r["names"]["primary"] or "")]
    return region, districts, extra


def analyse(raw_dir, city, product_geojson=None):
    region, districts, extra = load(raw_dir, city)
    assert len(region) == 1, (city, len(region))
    city_g = shapely.from_wkt(region[0]["geometry"])
    units = []
    for r in districts + extra:
        g = shapely.from_wkt(r["geometry"])
        units.append({"name": r["names"]["primary"], "subtype": r["subtype"], "admin_level": r.get("admin_level"),
                      "overture_division_id": r["division_id"], "overture_area_id": r["id"],
                      "osm": osm_ref(r), "overture_version": r.get("version"),
                      "area_km2": round(km2(g), 3), "is_valid": bool(g.is_valid),
                      "share_inside_city": round(km2(g.intersection(city_g)) / km2(g), 4), "_g": g})
    union = shapely.union_all([u["_g"] for u in units])
    overlaps = []
    for a, b in combinations(units, 2):
        inter = a["_g"].intersection(b["_g"])
        if not inter.is_empty and inter.area > 0:
            overlaps.append({"a": a["name"], "b": b["name"], "area_km2": round(km2(inter), 3)})
    out = {
        "city": city,
        "region_code": CITY_REGION[city],
        "city_polygon": {"name": region[0]["names"]["primary"], "osm": osm_ref(region[0]),
                         "overture_division_id": region[0]["division_id"],
                         "area_km2": round(km2(city_g), 3)},
        "districts": [{k: v for k, v in u.items() if k != "_g"} for u in units],
        "districts_union_km2": round(km2(union), 3),
        "city_area_covered_by_districts_share": round(km2(union.intersection(city_g)) / km2(city_g), 4),
        "city_area_not_covered_km2": round(km2(city_g.difference(union)), 3),
        "pairwise_overlaps": overlaps,
    }
    if product_geojson:
        prod = json.load(open(product_geojson, encoding="utf-8"))
        cmp = []
        for f in prod["features"]:
            pg = shapely.geometry.shape(f["geometry"])
            best = max(units, key=lambda u: u["_g"].intersection(pg).area)
            inter = km2(best["_g"].intersection(pg))
            uni = km2(best["_g"].union(pg))
            props = f.get("properties", {})
            cmp.append({"product_props": {k: props.get(k) for k in list(props)[:6]},
                        "matched_overture": best["name"], "osm": best["osm"],
                        "product_area_km2": round(km2(pg), 3), "overture_area_km2": best["area_km2"],
                        "iou": round(inter / uni, 4)})
        out["product_layer_comparison"] = {"file": product_geojson, "features": cmp}
    return out


if __name__ == "__main__":
    raw_dir = sys.argv[1]
    product = sys.argv[2] if len(sys.argv) > 2 else None
    res = {"experiment_id": "K10-E01",
           "shymkent": analyse(raw_dir, "shymkent"),
           "astana": analyse(raw_dir, "astana", product)}
    print(json.dumps(res, ensure_ascii=False, indent=1))
