"""K10 round 8: read-only loader of the real K10 slices from a BUILD app root (stdlib only).

    ctx = load_context(app_root, "shymkent")      # oracle context: city_id, bbox, source_snapshot, records, versions
    man = input_manifest(app_root)                # sha256 of every input file the packs depend on (immutability check)

The source_snapshot reproduces web/whatif.js sourceSnapshot() of BUILD a5b5e2d byte for byte:
    "sha256:" + sha256hex(JSON.stringify([SCHEMA_V1, city, release, places_file_sha256, placesDigest, FORMULA]))
    placesDigest = sha256hex(JSON.stringify(rows sorted by id of [id, Math.round(lon*1e7)/1e7, Math.round(lat*1e7)/1e7]))
If BUILD gives city-plan-v2 its own snapshot format, only the snapshot string changes, not the distances.
Nothing here writes to the app root; files are opened for reading only.
"""
import hashlib
import json
import math
from pathlib import Path

SNAPSHOT_SCHEMA = "city-whatif-v1"
SNAPSHOT_FORMULA = "haversine:R=6371008.8"
INPUT_FILES = ("web/data.js", "web/evidence.js", "web/whatif.js", "web/facts.js",
               "inputs/k10/data/shymkent/places_social.geojson", "inputs/k10/data/astana/places_social.geojson",
               "inputs/k10/package_manifest.json")


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


def snapshot_components(city, city_data):
    fsha = ((city_data.get("files") or {}).get("places_social") or {}).get("sha256")
    return [SNAPSHOT_SCHEMA, city, city_data["release"], fsha, places_digest(city_data), SNAPSHOT_FORMULA]


def source_snapshot(city, city_data):
    return "sha256:" + hashlib.sha256(js_stringify(snapshot_components(city, city_data)).encode("utf-8")).hexdigest()


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
            "places_file": c["files"]["places_social"]["path"], "places_file_sha256": c["files"]["places_social"]["sha256"],
            "records": records, "qa_colocated": ev["cities"][city]["qa"]["colocated"],
            "versions": {"snapshot_format": "web/whatif.js sourceSnapshot (BUILD a5b5e2d)"}}


def input_manifest(app_root):
    app = Path(app_root)
    return {rel: (sha256_file(app / rel) if (app / rel).exists() else None) for rel in INPUT_FILES}
