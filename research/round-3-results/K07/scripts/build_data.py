#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K07 round 3: build prototype/data.js from the stored K10 inputs and results/graph_check.json.

Nothing is downloaded. Every value keeps its kind:
  observed_secondary  — Overture record as stored by K10 (not an official registry);
  derived_k07         — computed here (district of a point, segment length class, clip of the K10 request);
  unknown             — not present in the inputs (capacity, pedestrian permission, ...).

Usage (repo root): python3 research/round-3-results/K07/scripts/build_data.py
Requires: Python 3.12, shapely 2.1.2, pyproj 3.8.0
"""
import json
from pathlib import Path

from pyproj import Geod
from shapely.geometry import Point, shape

K07 = Path(__file__).resolve().parents[1]
INP = K07 / "inputs/k10"
GEOD = Geod(ellps="WGS84")
MANIFEST = json.loads((K07 / "inputs/MANIFEST.json").read_text(encoding="utf-8"))

CITY = {"shymkent": {"label": "Шымкент", "iso": "KZ-79"}, "astana": {"label": "Астана", "iso": "KZ-71"}}
GROUPS = {  # K10 group -> (sector, label). Sector = colour, group = marker shape (secondary encoding)
    "school": ("education", "Школа"), "preschool": ("education", "Детский сад"),
    "college_university": ("education", "Колледж / вуз"),
    "hospital": ("health", "Больница"), "outpatient_clinic": ("health", "Поликлиника"), "pharmacy": ("health", "Аптека"),
    "government_office": ("government", "Госучреждение"),
}
PED_CLASSES = {"footway", "path", "pedestrian", "steps", "living_street", "cycleway", "bridleway"}
REASONS_RU = {
    "connector": "Соединители записаны только числом, без connector_id и позиции: топологию можно было бы восстановить только соединением пересекающихся линий, а это запрещено (ложно соединились бы эстакады и тоннели).",
    "access_restrictions": "Нет access_restrictions: право прохода пешком и направление неизвестны.",
    "road_flags": "Нет road_flags / level_rules: мост или тоннель не отличить от перекрёстка.",
    "sample": "Это выборка K10 «первые 8 сегментов каждого класса», а не все сегменты рамки: любой путь оборвался бы на краю выборки.",
}
# deterministic clips of K10_REQUEST.md (centre = sample point with most sample objects within 2 km)
EXPECTED_CLIPS = {
    "shymkent": {"core": [69.57896, 42.29927, 69.62748, 42.33528], "export": [69.56683, 42.29027, 69.63961, 42.34428]},
    "astana": {"core": [71.38389, 51.12029, 71.44104, 51.15624], "export": [71.3696, 51.1113, 71.45533, 51.16523]},
}


def load_jsonl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def clip_for(places):
    best = None
    for p in places:
        n = sum(1 for q in places if GEOD.inv(p["lon"], p["lat"], q["lon"], q["lat"])[2] <= 2000)
        if best is None or n > best[0] or (n == best[0] and p["overture_id"] < best[1]["overture_id"]):
            best = (n, p)
    n, p = best

    def off(dx, dy):
        lon2, lat2, _ = GEOD.fwd(p["lon"], p["lat"], 90, dx)
        lon3, lat3, _ = GEOD.fwd(lon2, lat2, 0, dy)
        return lon3, lat3
    w, s = off(-2000, -2000); e, nn = off(2000, 2000)
    W, S = off(-3000, -3000); E, N = off(3000, 3000)
    r = lambda v: [round(x, 5) for x in v]
    return {"centre": [p["lon"], p["lat"]], "objects_within_2km": n, "core": r([w, s, e, nn]), "export": r([W, S, E, N])}


def reasons_ru(reasons):
    out = []
    for r in reasons:
        key = next((k for k in REASONS_RU if k in r), None)
        out.append(REASONS_RU[key] if key else r)
    return out


def city_block(city, gc, datasets, e02, e03):
    dfc = json.loads((INP / f"samples/{city}_districts_overture.geojson").read_text(encoding="utf-8"))
    city_f = [f for f in dfc["features"] if f["properties"]["unit_kind"] == "city"]
    dist_f = [f for f in dfc["features"] if f["properties"]["unit_kind"] == "district"]
    dshapes = [(f["properties"]["name_primary"], shape(f["geometry"])) for f in dist_f]
    places = load_jsonl(INP / f"samples/{city}_places_social_sample.jsonl")
    seg = json.loads((INP / f"samples/{city}_road_segments_sample.geojson").read_text(encoding="utf-8"))
    prov = {t: json.loads((INP / f"provenance/{city}_{t}.provenance.json").read_text(encoding="utf-8"))
            for t in ("places", "segment", "division_area")}

    pl = []
    for p in places:
        pt = Point(p["lon"], p["lat"])
        d = [n for n, g in dshapes if g.covers(pt)]
        sector, label = GROUPS.get(p["k10_group"], ("other", p["k10_group"]))
        pl.append({"id": p["overture_id"], "name": p.get("name_primary"), "group": p["k10_group"], "group_label": label,
                   "sector": sector, "category": p.get("basic_category"), "taxonomy": p.get("taxonomy_hierarchy"),
                   "confidence": p.get("confidence"), "lon": p["lon"], "lat": p["lat"],
                   "address": (p.get("address_freeform") or [None])[0], "sources": p.get("sources") or [],
                   "overture_version": p.get("overture_version"), "kind": p.get("kind", "observed_secondary"),
                   "district_k07": d[0] if len(d) == 1 else (None if not d else "; ".join(d)),
                   "district_kind": "derived_k07 (точка в полигоне Overture)"})
    segs = []
    for f in seg["features"]:
        pr = f["properties"]
        src = (pr.get("sources") or [{}])[0]
        segs.append({"id": pr["overture_id"], "class": pr["class"], "pedestrian_class": pr["class"] in PED_CLASSES,
                     "name": pr.get("name_primary"), "length_m": pr.get("length_m_geodesic"),
                     "connectors_count": pr.get("connectors"), "record_id": src.get("record_id"),
                     "update_time": src.get("update_time"), "license": src.get("license"),
                     "coords": f["geometry"]["coordinates"]})

    ext = next(r for r in e02["results"] if r["city"] == city)
    by_group_extract = {}
    for dname, cnt in ext["counts_by_threshold"]["confidence>=0.0"].items():
        for g, n in cnt.items():
            by_group_extract[g] = by_group_extract.get(g, 0) + n
    by_group_sample = {}
    for p in pl:
        by_group_sample[p["group"]] = by_group_sample.get(p["group"], 0) + 1
    net = next(r for r in e03["results"] if r["city"] == city)

    clip = clip_for(places)
    assert {"core": clip["core"], "export": clip["export"]} == EXPECTED_CLIPS[city], (city, clip)
    ds = {x["id"]: x for x in datasets["datasets"]}
    g = gc["cities"][city]
    return {
        "key": city, "label": CITY[city]["label"], "iso": CITY[city]["iso"],
        "city_polygons": [f["geometry"] for f in city_f],
        "city_area_km2": city_f[0]["properties"]["area_km2_geodesic_wgs84"],
        "districts": [{"name": f["properties"]["name_primary"], "area_km2": f["properties"]["area_km2_geodesic_wgs84"],
                       "osm_relation": f["properties"].get("osm_relation"), "overture_subtype": f["properties"]["overture_subtype"],
                       "geometry": f["geometry"]} for f in dist_f],
        "places": pl, "segments": segs,
        "counts": {"sample_by_group": by_group_sample, "extract_in_districts_by_group": by_group_extract,
                   "extract_places_in_city": ext["places_inside_city_polygon"],
                   "extract_road_km_in_city": net["road_km_inside_city"],
                   "extract_road_segments_in_city": net["road_segments_intersecting_city"],
                   "sample_segments": len(segs), "sample_road_km": round(sum(s["length_m"] for s in segs) / 1000, 1)},
        "provenance": {
            "release": prov["places"]["release"], "bucket": prov["places"]["bucket"],
            "retrieved_utc": {t: prov[t].get("started_utc") for t in prov},
            "query_bbox": prov["places"].get("query_bbox"),
            "sampling": {"places": "до 15 объектов на группу K10, по убыванию confidence, только внутри полигона города",
                         "segments": "первые 8 сегментов каждого класса в порядке файла, только целиком внутри полигона города"},
            "licenses": {"places": ds["K10-D02"]["license_observed"][city], "segments": ds["K10-D04"]["license_observed"],
                         "divisions": ds["K10-D01"]["license_observed"]},
            "attribution": ds["K10-D04"].get("attribution_required"),
            "limitations": {"places": ds["K10-D02"]["limitations"], "segments": ds["K10-D04"]["limitations"],
                            "divisions": ds["K10-D01"]["limitations"]},
        },
        "graph": {"verdict": g["verdict"], "reasons_ru": reasons_ru(g["reasons"]),
                  "diagnostics": g["diagnostics_not_used_for_graph"], "segments": g["segments"], "km": g["length_km_geodesic"]},
        "k10_request_clip": clip,
    }


def main():
    gc = json.loads((K07 / "results/graph_check.json").read_text(encoding="utf-8"))
    datasets = json.loads((INP / "datasets.json").read_text(encoding="utf-8"))
    e02 = json.loads((INP / "results/E02_social_poi_by_district.json").read_text(encoding="utf-8"))
    e03 = json.loads((INP / "results/E03_road_network_by_district.json").read_text(encoding="utf-8"))
    data = {
        "generated_by": "research/round-3-results/K07/scripts/build_data.py",
        "inputs": {"k10_branch": MANIFEST["source_branch"], "k10_sha": MANIFEST["source_sha"],
                   "manifest": "inputs/MANIFEST.json", "graph_check": "results/graph_check.json"},
        "groups": {k: {"sector": v[0], "label": v[1]} for k, v in GROUPS.items()},
        "cities": {c: city_block(c, gc, datasets, e02, e03) for c in ("shymkent", "astana")},
    }
    js = ("// GENERATED by scripts/build_data.py from stored K10 inputs — do not edit by hand.\n"
          "window.K07_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    out = K07 / "prototype/data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text(js, encoding="utf-8")
    for c, b in data["cities"].items():
        nd = sum(1 for p in b["places"] if p["district_k07"] is None)
        print(c, "places", len(b["places"]), "segments", len(b["segments"]), "districts", len(b["districts"]),
              "places without district", nd, "verdict", b["graph"]["verdict"])
    print("data.js bytes", out.stat().st_size)


if __name__ == "__main__":
    main()
