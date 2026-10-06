"""K10 round 10: raw pinned Overture extracts -> small committed inputs of the Astana school package.

Usage (repo root, Python with shapely + pyproj):
  python research/round-10-results/K10/scripts/make_inputs.py <raw_dir> [--code-sha d2ff344c…]
<raw_dir> holds the outputs of overture_bbox.py for the query box [71.3754, 51.1360, 71.4900, 51.2080]
(slice bbox + ~3 km): astana_places_q3km.jsonl, astana_land_use_q3km.jsonl, astana_buildings_q3km.jsonl and their
.provenance.json. Raw files are not committed (6–22 MB); their sha256 is kept in inputs/provenance/.
Writes research/round-10-results/K10/inputs/:
  app_slice_astana.json             school/preschool records of the app slice (web/govtech/core/data.js @ code sha)
  overture_places_education.jsonl   education places (no phones/e-mails/socials; websites kept as organisation leads)
  osm_landuse_education.jsonl       OSM education land use via Overture base/land_use (contact tags dropped)
  osm_buildings_education.jsonl     OSM/ML buildings with an education class/subtype
  buildings_bbox_residential.jsonl  residential building footprints whose centroid lies in the slice bbox (origin pool)
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import shapely
import shapely.ops
import shapely.wkt
from pyproj import Transformer

K = Path(__file__).resolve().parents[1]
ROOT = K.parents[2]
CODE_SHA = "d2ff344c5ec9b9a729ea59df50ec81f981e619de"
BBOX = (71.418372, 51.163033, 71.447, 51.181)
UTM = Transformer.from_crs(4326, 32642, always_xy=True)  # WGS 84 / UTM 42N (Astana ≈ 71.4°E)
RES = {"apartments", "residential", "house", "detached", "semidetached_house", "terrace", "dormitory", "bungalow"}
EDU_B = {"school", "kindergarten", "college", "university"}
CONTACT = re.compile(r"(^|:)(phone|email|fax|mobile|contact:phone|contact:email)$|^contact:(phone|email|fax|mobile)")


def r7(v):
    return round(float(v), 7)


def rows(p):
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


def src(sources):
    return [{k: s.get(k) for k in ("dataset", "license", "record_id", "update_time", "property", "version")} for s in sources or []]


def wkt7(g):
    return shapely.wkt.dumps(g, rounding_precision=7, trim=True)


def write_jsonl(path, items):
    items = sorted(items, key=lambda x: x["id"])
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for it in items:
            fh.write(json.dumps(it, ensure_ascii=False, sort_keys=True) + "\n")
    return len(items)


def app_slice(code_sha):
    blob = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{code_sha}:web/govtech/core/data.js"])
    js = blob.decode("utf-8")
    node = "const vm=require('vm'),b={};vm.createContext(b);b.window=b;vm.runInContext(require('fs').readFileSync(0,'utf8'),b);process.stdout.write(JSON.stringify(b.CITY_EVIDENCE.cities.astana))"
    c = json.loads(subprocess.run(["node", "-e", node], input=blob, capture_output=True, check=True).stdout)
    keep = [p for p in c["places"] if p["group"] in ("school", "preschool")]
    return {"source_file": "web/govtech/core/data.js", "code_sha": code_sha, "data_js_sha256": hashlib.sha256(blob).hexdigest(),
            "city": "astana", "bbox": c["bbox"], "release": c["release"], "retrieved_utc": c["retrieved_utc"], "kind": c["kind"],
            "counts_places_by_group": c["counts"]["places_by_group"], "places_school_and_preschool": sorted(keep, key=lambda p: p["id"]),
            "note": "Copied from the pinned app slice (observed_secondary Overture/OSM), not an official registry. Contact fields are absent in the slice."}


def main(a):
    raw = Path(a[0])
    code_sha = a[a.index("--code-sha") + 1] if "--code-sha" in a else CODE_SHA
    out = K / "inputs"
    (out / "provenance").mkdir(parents=True, exist_ok=True)
    box = shapely.box(*BBOX)
    res = {}
    sl = app_slice(code_sha)
    (out / "app_slice_astana.json").write_text(json.dumps(sl, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    res["app_slice_astana.json"] = len(sl["places_school_and_preschool"])

    places = []
    for r in rows(raw / "astana_places_q3km.jsonl"):
        h = (r.get("taxonomy") or {}).get("hierarchy") or []
        if not h or h[0] != "education":
            continue
        g = shapely.from_wkt(r["geometry"])
        places.append({"id": r["id"], "version": r.get("version"), "lon": r7(g.x), "lat": r7(g.y), "confidence": r.get("confidence"),
                       "names": {"primary": (r.get("names") or {}).get("primary"), "common": (r.get("names") or {}).get("common")},
                       "addresses": [{k: x.get(k) for k in ("freeform", "locality", "postcode", "country")} for x in r.get("addresses") or []],
                       "taxonomy": r.get("taxonomy"), "basic_category": r.get("basic_category"), "operating_status": r.get("operating_status"),
                       "websites": r.get("websites"), "sources": src(r.get("sources"))})
    res["overture_places_education.jsonl"] = write_jsonl(out / "overture_places_education.jsonl", places)

    lu = []
    for r in rows(raw / "astana_land_use_q3km.jsonl"):
        if r.get("subtype") != "education":
            continue
        tags = [[k, v] for k, v in (r.get("source_tags") or []) if not CONTACT.search(k)]
        lu.append({"id": r["id"], "version": r.get("version"), "class": r.get("class"), "subtype": r.get("subtype"),
                   "names": {"primary": (r.get("names") or {}).get("primary"), "common": (r.get("names") or {}).get("common")},
                   "source_tags": sorted(tags), "sources": src(r.get("sources")), "geometry_wkt": wkt7(shapely.from_wkt(r["geometry"]))})
    res["osm_landuse_education.jsonl"] = write_jsonl(out / "osm_landuse_education.jsonl", lu)

    be, br = [], []
    counts = {}
    for r in rows(raw / "astana_buildings_q3km.jsonl"):
        g = shapely.from_wkt(r["geometry"])
        cls, sub = r.get("class"), r.get("subtype")
        if cls in EDU_B or sub == "education":
            be.append({"id": r["id"], "version": r.get("version"), "class": cls, "subtype": sub, "num_floors": r.get("num_floors"),
                       "height": r.get("height"), "names": {"primary": (r.get("names") or {}).get("primary"), "common": (r.get("names") or {}).get("common")},
                       "sources": src(r.get("sources")), "geometry_wkt": wkt7(g)})
        c = g.centroid if g.centroid.within(g) else g.representative_point()
        if c.within(box):
            counts[cls or "null"] = counts.get(cls or "null", 0) + 1
            if cls in RES:
                gm = shapely.ops.transform(lambda x, y, z=None: UTM.transform(x, y), g)
                br.append({"id": r["id"], "version": r.get("version"), "class": cls, "subtype": sub, "num_floors": r.get("num_floors"),
                           "height": r.get("height"), "lon": r7(c.x), "lat": r7(c.y), "point_method": "centroid" if g.centroid.within(g) else "representative_point",
                           "footprint_area_m2": round(gm.area, 1), "sources": src(r.get("sources"))})
    res["osm_buildings_education.jsonl"] = write_jsonl(out / "osm_buildings_education.jsonl", be)
    res["buildings_bbox_residential.jsonl"] = write_jsonl(out / "buildings_bbox_residential.jsonl", br)

    prov = {"raw_dir_files": {}, "bbox_building_counts_by_class": dict(sorted(counts.items())), "outputs": {}}
    for f in ("astana_places_q3km.jsonl", "astana_land_use_q3km.jsonl", "astana_buildings_q3km.jsonl"):
        p = json.loads((raw / (f + ".provenance.json")).read_text(encoding="utf-8"))
        assert p["output_sha256"] == hashlib.sha256((raw / f).read_bytes()).hexdigest(), f
        (out / "provenance" / (f + ".provenance.json")).write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        prov["raw_dir_files"][f] = {"sha256": p["output_sha256"], "rows": p["rows_out"], "release": p["release"], "query_bbox": p["query_bbox"]}
    for f in res:
        prov["outputs"][f] = {"rows": res[f], "sha256": hashlib.sha256((out / f).read_bytes()).hexdigest()}
    (out / "provenance" / "inputs_manifest.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(res))


if __name__ == "__main__":
    main(sys.argv[1:])
