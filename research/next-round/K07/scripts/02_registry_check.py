#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K07 stage 3: registry check for school / social-object accessibility. No network access.

Parts:
  1. Product layer (real files of this repository): data/real_context.json, data/real_context_meta.json,
     data/astana_districts.geojson, fetch_real_context.py. Checks claims made by A04/A05/AST-A12.
  2. Registry candidates per city (Astana and Shymkent kept apart) from the stored AST-A12 sample of a
     third-party crawl of the data.egov.kz catalogue (secondary source; the portal itself is blocked here).
  3. Field contract that separates inputs of GEOGRAPHIC ACCESS from inputs of PROVISION BY SEATS,
     and what is computable per city today.
  4. Row validator for a future registry (null vs 0, provenance of numbers, coordinates inside the city,
     duplicate IDs, one city per file). Self-test on clearly synthetic fixture rows + Astana OSM polygons.

Usage: python3 02_registry_check.py [--repo-root PATH] [--out PATH]
Requires: Python 3.12, shapely 2.1.2.
"""
import argparse, json, re
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve()
DEFAULT_ROOT = HERE.parents[4]
AST_A12 = "research/astana-results/12_data_gis/extracted_files__33_"

# ---------------------------------------------------------------- 3. contract
CONTRACT = {
    "registry_row": {
        "object_id": "stable id from the source (BIN / portal id); required",
        "city": "astana | shymkent; one city per file, never mixed",
        "kind": "school | kindergarten | other",
        "operating_status": "operating | closed | planned | unknown; only operating objects count",
        "lon": "WGS84, null if unknown (never 0)", "lat": "WGS84, null if unknown (never 0)",
        "coord_source": "registry | osm | manual | null",
        "design_capacity": {"value": "int or null", "source_id": "required if value", "period": "required if value"},
        "enrolled": {"value": "int or null", "source_id": "required if value", "period": "required if value"},
        "shifts": {"value": "int or null", "source_id": "required if value"},
        "source_id": "provenance of the row", "retrieved_at": "ISO date", "license": "string or null",
    },
    "demand_area_row": {
        "area_id": "district / block / grid cell id with boundary version",
        "children_by_age": {"value": "int or null", "age_band": "e.g. 6-17", "source_id": "required if value", "period": "required if value"},
    },
}
ANALYSES = {
    # analysis -> inputs it needs
    "geographic_access_radius_baseline": ["object coordinates", "residential locations"],
    "geographic_access_network": ["object coordinates", "residential locations", "pedestrian network"],
    "provision_arithmetic_by_area": ["design capacity", "children by area", "area of each object"],
    "provision_within_reach_2sfca": ["object coordinates", "design capacity", "children by area", "pedestrian network"],
    "utilization": ["design capacity", "enrolled", "shifts"],
}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def check_product_layer(root):
    rc, meta = load(root / "data/real_context.json"), load(root / "data/real_context_meta.json")
    gj = load(root / "data/astana_districts.geojson")
    code = (root / "fetch_real_context.py").read_text(encoding="utf-8")
    values = [v for d in rc.values() for v in d.values()]
    ids_code = re.search(r"DISTRICT_IDS\s*=\s*\(([^)]*)\)", code).group(1)
    district_ids_code = [s.strip().strip('"\'') for s in ids_code.split(",") if s.strip()]
    gj_ids = [f["properties"]["id"] for f in gj["features"]]
    line346 = code.splitlines()[345]
    consumers = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".js", ".html", ".ts", ".jsx", ".tsx"} \
                and "research" not in p.parts and ".git" not in p.parts and p.name != "fetch_real_context.py":
            if "real_context" in p.read_text(encoding="utf-8", errors="ignore"):
                consumers.append(str(p.relative_to(root)))
    findings = [
        {"id": "K07-R01", "kind": "observed",
         "statement": "real_context.json holds 0 for every district and category while meta.status is 'unavailable'",
         "evidence": {"meta_status": meta["status"], "n_values": len(values), "n_zero": values.count(0),
                      "meta_generated_at": meta["generated_at"]},
         "confirms": ["A05 §2 (A05-F005)", "A04 §2 item 2"],
         "consequence": "a future layer must write null + status, otherwise 0 reads as 'no schools'"},
        {"id": "K07-R02", "kind": "observed",
         "statement": "line 346 of fetch_real_context.py documents that zeros mean 'no data' when status is unavailable",
         "evidence": {"line_346": line346.strip()}, "confirms": ["A05 §2"]},
        {"id": "K07-R03", "kind": "observed",
         "statement": "no code outside the collector reads real_context (zeros do not reach the UI today)",
         "evidence": {"consumers_in_code": consumers}, "confirms": ["A04 §2 item 2"]},
        {"id": "K07-R04", "kind": "observed",
         "statement": "the stored stub was generated with schematic districts before the OSM polygons were saved",
         "evidence": {"meta_districts_source": meta.get("districts_source"), "meta_generated_at": meta["generated_at"],
                      "geojson_metadata_source": gj["metadata"]["source"], "geojson_generated_at": gj["metadata"]["generated_at"]},
         "consequence": "meta.warning about schematic districts is stale; rerun the collector before any use"},
        {"id": "K07-R05", "kind": "derived_from_code",
         "statement": "the collector loads 5 district ids; the GeoJSON has 6 features. Objects in Sarayshyk would be counted as 'outside districts' together with objects outside the city",
         "evidence": {"DISTRICT_IDS": district_ids_code, "geojson_ids": gj_ids,
                      "saraishyk_scoring_enabled": next(f["properties"]["scoring_enabled"] for f in gj["features"] if f["properties"]["id"] == "saraishyk"),
                      "code": "aggregate(): find_district() is None -> outside[category] += 1; meta.outside_districts"},
         "consequence": "for real accessibility the 6th district needs its own bucket; 'outside' must mean outside the city"},
        {"id": "K07-R06", "kind": "derived_from_code",
         "statement": "duplicates are removed only for named objects (same category + normalized name within 150 m schools / 100 m kindergartens); unnamed objects are never de-duplicated",
         "evidence": {"dedup_radius_m": meta.get("dedup_radius_m"),
                      "code": "key = (cat, normalize_name(name)) if name else None"},
         "confirms": ["A05 §2 (dedup by normalized name)"],
         "consequence": "an unnamed school mapped as node + building would be counted twice; two buildings of one named school within 150 m are merged"},
    ]
    return findings


def registry_candidates(root):
    samples = load(root / AST_A12 / "AST_A12_samples_real.json")["samples"]
    ev = load(root / AST_A12 / "AST_A12_evidence.json")
    rows = [r for s in samples for r in s.get("rows", []) if "api_uri" in r]
    by_uri = {r["api_uri"]: r for r in rows}
    src = {s["source_id"]: s for s in ev["sources"]}
    f024 = next(f for f in ev["facts"] if f["fact_id"] == "AST-A12-F024")

    def card(uri, city, scope):
        r = by_uri.get(uri)
        return {"city": city, "api_uri": uri, "present_in_stored_sample": r is not None,
                "title": r and r["title"], "publisher": r and r["passport_gov_agency"],
                "renewal_date": r and r["passport_renewal_date"], "crawled_at": r and r["crawled_at"],
                "geographic_scope": scope,
                "source": {"source_id": "AST-A12-S016", "url": src["AST-A12-S016"]["url"], "type": src["AST-A12-S016"]["source_type"]},
                "known_fields": ["nate1 (region filter, from third-party code AST-A12-S018)"] if uri.endswith("boi4") else [],
                "unknown": ["rows", "coordinates", "addresses", "design capacity", "enrolment", "shifts", "license"],
                "portal_check": "not done: data.egov.kz returns 403 on CONNECT in this environment (access_check.json)"}

    cands = {
        "astana": [card("onirler_oblystar_kalalar_boi4", "astana",
                        "national registry (all regions); Astana rows must be filtered by region field, not by name")],
        "shymkent": [card("opendata-api-uri981", "shymkent", "akimat of Shymkent dataset; city scope by publisher")],
    }
    notes = [
        {"id": "K07-R07", "kind": "observed",
         "statement": "AST-A12-F024 also names a kindergarten registry 'boi6', but the stored sample has no row with that api_uri",
         "evidence": {"api_uris_in_sample": sorted(by_uri)}, "status": "not verifiable from the repository; needs the original crawl CSV or the portal"},
        {"id": "K07-R08", "kind": "observed",
         "statement": "in the stored crawl sample api_uri and title disagree for at least one row (api_uri about cattle, title about heat supply)",
         "evidence": {"api_uri": "435_the_number_of_cattle_by_r", "title": by_uri["435_the_number_of_cattle_by_r"]["title"]},
         "status": "secondary catalogue metadata can be inconsistent; registry cards must be confirmed on the portal"},
    ]
    return cands, notes, f024["statement"]


# ---------------------------------------------------------------- 4. validator
NUMERIC = ("design_capacity", "enrolled", "shifts")


def validate_registry(rows, city, city_polygon=None):
    issues, seen = [], set()
    for r in rows:
        rid = r.get("object_id")
        def add(code, msg):
            issues.append({"object_id": rid, "code": code, "message": msg})
        if not rid:
            add("V1_missing_id", "object_id is required")
        elif rid in seen:
            add("V4_duplicate_id", "object_id repeats")
        seen.add(rid)
        if r.get("city") != city:
            add("V6_city_mix", f"row city {r.get('city')!r} in a {city!r} file")
        lon, lat = r.get("lon"), r.get("lat")
        if lon == 0 or lat == 0:
            add("V2_zero_coordinate", "0 used instead of null for a coordinate")
        elif lon is not None and lat is not None:
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                add("V3_bad_coordinate", "coordinate out of range")
            elif city_polygon is not None and not city_polygon.covers(Point(lon, lat)):
                add("V3_outside_city", "point outside the city polygon (check region filter / geocoding)")
        for k in NUMERIC:
            f = r.get(k) or {}
            v = f.get("value")
            if v == 0 and f.get("status") != "observed":
                add("V2_zero_as_unknown", f"{k}=0 without observed status; unknown must be null")
            if v not in (None, 0) and not (f.get("source_id") and (k == "shifts" or f.get("period"))):
                add("V5_number_without_provenance", f"{k} has a value but no source_id/period")
    computable = {
        "geographic_access_network": "needs pedestrian network (blocked) and residential locations",
        "provision": "computable only for rows with design_capacity provenance AND an area demand table",
    }
    rows_with_cap = sum(1 for r in rows if (r.get("design_capacity") or {}).get("value") not in (None, 0)
                        and (r.get("design_capacity") or {}).get("source_id"))
    return {"n_rows": len(rows), "n_issues": len(issues), "issues": issues,
            "rows_with_sourced_capacity": rows_with_cap, "computability_note": computable}


def aggregated_layer_check(rc, meta):
    """Aggregated count layers (like real_context.json): if status != ok every value must be null."""
    bad = [(d, k) for d, cats in rc.items() for k, v in cats.items() if meta.get("status") != "ok" and v is not None]
    return {"status": meta.get("status"), "values_that_should_be_null": len(bad), "ok": not bad}


SYNTHETIC_FIXTURE = [  # SYNTHETIC test rows for the validator; not real schools, names are placeholders
    {"object_id": "TEST-1", "city": "astana", "kind": "school", "lon": 71.43, "lat": 51.13,
     "design_capacity": {"value": None, "status": "unknown"}},
    {"object_id": "TEST-2", "city": "astana", "kind": "school", "lon": 0, "lat": 0,
     "design_capacity": {"value": 0, "status": "unknown"}},
    {"object_id": "TEST-3", "city": "astana", "kind": "school", "lon": 71.20, "lat": 51.45,
     "design_capacity": {"value": 999, "source_id": None, "period": None}},
    {"object_id": "TEST-3", "city": "shymkent", "kind": "school", "lon": None, "lat": None},
]
EXPECTED_CODES = {("TEST-2", "V2_zero_coordinate"), ("TEST-2", "V2_zero_as_unknown"),
                  ("TEST-3", "V3_outside_city"), ("TEST-3", "V5_number_without_provenance"),
                  ("TEST-3", "V4_duplicate_id"), ("TEST-3", "V6_city_mix")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(DEFAULT_ROOT))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    root = Path(a.repo_root).resolve()
    out = Path(a.out) if a.out else root / "research/next-round/K07/results/registry_check_results.json"

    product = check_product_layer(root)
    cands, notes, f024 = registry_candidates(root)
    gj = load(root / "data/astana_districts.geojson")
    astana_union = unary_union([shape(f["geometry"]) for f in gj["features"]])
    v = validate_registry(SYNTHETIC_FIXTURE, "astana", astana_union)
    got = {(i["object_id"], i["code"]) for i in v["issues"]}
    selftest = {"expected_codes": sorted(map(list, EXPECTED_CODES)), "got_codes": sorted(map(list, got)),
                "passed": got == EXPECTED_CODES}
    assert selftest["passed"], selftest
    agg = aggregated_layer_check(load(root / "data/real_context.json"), load(root / "data/real_context_meta.json"))

    status_today = {
        city: {
            "object_registry_rows": "not obtained (data.egov.kz blocked; only a catalogue card from a secondary crawl)",
            "object_coordinates": "not obtained (Overpass blocked; OSM points of schools absent from the repo)",
            "pedestrian_network": "not obtained (Overpass blocked; data/geo_sources/sara_osm.json has only 66 boundary roads, not a walk network)" if city == "astana" else "not obtained (no OSM data for Shymkent in the repo)",
            "district_polygons": "available: 6 OSM community boundaries, snapshot 2026-09-22 (not legal boundaries)" if city == "astana" else "not available in the repo",
            "design_capacity": "unknown, no source", "children_by_area": "unknown, no source",
            "computable_now": [],
            "computable_after_osm_access": ["geographic_access_radius_baseline", "geographic_access_network"],
            "needs_capacity_and_demand_sources": ["provision_arithmetic_by_area", "provision_within_reach_2sfca", "utilization"],
        } for city in ("astana", "shymkent")}

    res = {"kind": "registry check; real repository files + secondary catalogue sample; validator self-test on synthetic rows",
           "product_layer_findings": product,
           "aggregated_layer_check_real_context": agg,
           "registry_candidates": cands, "registry_notes": notes,
           "AST_A12_F024_as_stated": f024,
           "contract": CONTRACT, "analyses_and_inputs": ANALYSES,
           "status_today_by_city": status_today,
           "validator_selftest_synthetic": selftest,
           "validator_result_on_synthetic_fixture": v}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"product_findings": [f["id"] for f in product], "aggregated_layer_ok": agg["ok"],
                      "registry_candidates": {c: [x["api_uri"] for x in v_] for c, v_ in cands.items()},
                      "notes": [n["id"] for n in notes], "validator_selftest_passed": selftest["passed"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
