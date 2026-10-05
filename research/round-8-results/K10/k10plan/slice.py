"""K10 round 8: read-only loader of the real K10 slices from a BUILD app root (stdlib only).

    ctx = load_context(app_root, "shymkent")      # oracle context: city_id, bbox, source_snapshot, records, versions
    man = input_manifest(app_root)                # sha256 of every input file the packs depend on (immutability check)

source_snapshot formats (both reproduce the BUILD's JavaScript byte for byte; checked with node):
    "plan-v2"   web/plan.js sourceSnapshot() of BUILD 60f44d9 (default; what a city-plan-v2 import compares with)
                "sha256:" + sha256hex(JSON.stringify(["city-plan-v2", city, release, places_sha256, placesDigest, "haversine-mm-v1"]))
    "whatif-v1" web/whatif.js sourceSnapshot() of BUILD a5b5e2d
                "sha256:" + sha256hex(JSON.stringify(["city-whatif-v1", city, release, places_sha256, placesDigest, "haversine:R=6371008.8"]))
    placesDigest = sha256hex(JSON.stringify(rows sorted by id of [id, Math.round(lon*1e7)/1e7, Math.round(lat*1e7)/1e7]))
A different snapshot format changes only the snapshot string, never the distances.
Nothing here writes to the app root; files are opened for reading only.
"""
import hashlib
import json
import math
from pathlib import Path

SNAPSHOT_FORMATS = {"plan-v2": ("city-plan-v2", "haversine-mm-v1"), "whatif-v1": ("city-whatif-v1", "haversine:R=6371008.8")}
DEFAULT_SNAPSHOT = "plan-v2"
DATA_FILES = ("web/data.js", "web/evidence.js", "inputs/k10/data/shymkent/places_social.geojson",
              "inputs/k10/data/astana/places_social.geojson", "inputs/k10/package_manifest.json")
CODE_FILES = ("web/whatif.js", "web/facts.js", "web/plan.js")  # informational: code may change between builds
INPUT_FILES = DATA_FILES + CODE_FILES


def parse_js(raw):
    t = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def js_number(x):
    """Number formatted as JavaScript JSON.stringify would (repr is the shortest round trip in both languages)."""
    if isinstance(x, bool):
        raise TypeError("bool")
    if isinstance(x, int):
        return str(x)
    if not math.isfinite(x):
        return "null"
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    r = repr(x)
    if "e" in r:  # Python 1e-07 / 1.5e+22 -> JS 1e-7 / 1.5e+22
        mant, exp = r.split("e")
        sign = "-" if exp.startswith("-") else "+"
        r = f"{mant}e{sign}{int(exp.lstrip('+-'))}"
    return r


def js_stringify(v):
    """JSON.stringify for the plain values used in the snapshot (lists, ASCII/Unicode strings, numbers, null)."""
    if v is None:
        return "null"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return js_number(v)
    if isinstance(v, list):
        return "[" + ",".join(js_stringify(x) for x in v) + "]"
    raise TypeError(type(v).__name__)


def r7(x):
    return math.floor(x * 1e7 + 0.5) / 1e7  # Math.round(x*1e7)/1e7 (half up), not Python's banker's round


def places_digest(city_data):
    rows = sorted(([p["id"], r7(p["lon"]), r7(p["lat"])] for p in city_data["places"]), key=lambda r: r[0])
    return hashlib.sha256(js_stringify(rows).encode("utf-8")).hexdigest()


def snapshot_components(city, city_data, fmt=DEFAULT_SNAPSHOT):
    schema, metric = SNAPSHOT_FORMATS[fmt]
    fsha = ((city_data.get("files") or {}).get("places_social") or {}).get("sha256")
    return [schema, city, city_data["release"], fsha, places_digest(city_data), metric]


def source_snapshot(city, city_data, fmt=DEFAULT_SNAPSHOT):
    return "sha256:" + hashlib.sha256(js_stringify(snapshot_components(city, city_data, fmt)).encode("utf-8")).hexdigest()


def qa_codes(ev_city):
    out = {}
    for g in ev_city["qa"]["colocated"]:
        for i in g["ids"]:
            out.setdefault(i, set()).add("COLOCATED")
    for d in ev_city["qa"]["possible_duplicates"]:
        for i in (d["a"], d["b"]):
            out.setdefault(i, set()).add("POSSIBLE_DUPLICATE")
    for i in ev_city["qa"]["category_doubt"]:
        out.setdefault(i, set()).add("CATEGORY_DOUBT")
    return {k: sorted(v) for k, v in out.items()}


def load_app(app_root):
    app = Path(app_root)
    return parse_js((app / "web/data.js").read_bytes()), parse_js((app / "web/evidence.js").read_bytes())


def load_context(app_root, city, _cache=None):
    data, ev = _cache or load_app(app_root)
    c = data["cities"][city]
    qa = qa_codes(ev["cities"][city])
    records = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"], "name": p.get("name"),
                "qa_flags": qa.get(p["id"], [])} for p in c["places"]]
    return {"city_id": city, "bbox": list(c["bbox"]), "source_snapshot": source_snapshot(city, c),
            "snapshot_components": snapshot_components(city, c), "release": c["release"],
            "whatif_v1_snapshot": source_snapshot(city, c, "whatif-v1"),
            "places_file": c["files"]["places_social"]["path"], "places_file_sha256": c["files"]["places_social"]["sha256"],
            "records": records, "qa_colocated": ev["cities"][city]["qa"]["colocated"],
            "versions": {"snapshot_format": "plan-v2: web/plan.js sourceSnapshot (BUILD 60f44d9)"}}


def input_manifest(app_root):
    app = Path(app_root)
    return {rel: (sha256_file(app / rel) if (app / rel).exists() else None) for rel in INPUT_FILES}
