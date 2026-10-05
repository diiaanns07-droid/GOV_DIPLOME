"""K01 round-7: independent strict validator / recomputation for city-whatif-v1 (FEATURE_SPEC round-7). Stdlib only.

  python3 whatif_v1.py --app-root PATH/city-evidence validate FILE.json   # exit 0 valid, 1 rejected
  python3 whatif_v1.py --app-root PATH snapshot CITY CATEGORY             # print source_snapshot
  python3 whatif_v1.py --app-root PATH export FILE.json                   # re-export canonical scenario + recomputed values

Inputs are read only from <app-root>/web/data.js (the slice the page itself uses); nothing is written there.
source_snapshot (proposal, the spec fixes WHAT it covers, not the encoding):
  "cw1-" + sha256(canonical JSON of {schema, city_id, release, bbox, places_social sha256 from the build manifest,
  sorted [id, group, lon, lat] of all places in the slice, distance params})[:32]
It changes when any place record, the manifest hash, the bbox or the formula parameters change; a file name is never trusted.
"""
import hashlib
import json
import math
import re
import sys
from pathlib import Path

SCHEMA = "city-whatif-v1"
CITIES = ("shymkent", "astana")
CATEGORIES = ("school", "outpatient_clinic")
MAX_BYTES = 256 * 1024
MAX_POINTS = 10
R_EARTH_M = 6371008.8
DIST_PARAMS = {"formula": "haversine", "radius_m": R_EARTH_M, "input": "[lon,lat]", "clamp": [0, 1]}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")   # ≤64 chars, no '/', ':' → no URL, path or markup
TOP_KEYS = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object"}
OPTIONAL_TOP = {"computed"}   # accepted only to be discarded: imported results are never trusted
POINT_KEYS = {"id", "lon", "lat"}
PROJECT_KEYS = {"id", "lon", "lat", "category", "kind"}


class ScenarioError(ValueError):
    def __init__(self, code, msg):
        super().__init__(f"{code}: {msg}")
        self.code = code


# ---------------- slice ----------------
def load_slice(app_root):
    t = (Path(app_root) / "web" / "data.js").read_text(encoding="utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def snapshot_id(data, city_id):
    c = data["cities"][city_id]
    payload = {"schema": SCHEMA, "city_id": city_id, "release": c["release"], "bbox": c["bbox"],
               "places_social_sha256": c["files"]["places_social"]["sha256"],
               "places": sorted([p["id"], p["group"], p["lon"], p["lat"]] for p in c["places"]),
               "distance": DIST_PARAMS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "cw1-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# ---------------- strict parsing ----------------
def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ScenarioError("duplicate_key", f"ключ {k!r} повторяется")
        d[k] = v
    return d


def _bad_const(name):
    raise ScenarioError("non_finite", f"{name} не допускается")


def _float(s):
    v = float(s)
    if not math.isfinite(v):
        raise ScenarioError("non_finite", f"число {s} вне диапазона")
    return v


def parse_bytes(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise ScenarioError("type", "ожидаются байты JSON")
    if len(raw) > MAX_BYTES:
        raise ScenarioError("too_large", f"{len(raw)} байт > {MAX_BYTES}")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise ScenarioError("encoding", "не UTF-8")
    try:
        return json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_bad_const, parse_float=_float)
    except ScenarioError:
        raise
    except (json.JSONDecodeError, RecursionError) as e:
        raise ScenarioError("json", f"неверный JSON: {e}")


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ScenarioError("coord", f"{what}: ожидается конечное число")
    return float(v)


def _point(o, keys, where, bbox):
    if not isinstance(o, dict):
        raise ScenarioError("shape", f"{where}: ожидается объект")
    if set(o) != keys:
        raise ScenarioError("shape", f"{where}: поля {sorted(o)} != {sorted(keys)}")
    if not isinstance(o["id"], str) or not ID_RE.match(o["id"]):
        raise ScenarioError("id", f"{where}: id должен соответствовать {ID_RE.pattern}")
    lon, lat = _num(o["lon"], f"{where}.lon"), _num(o["lat"], f"{where}.lat")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ScenarioError("coord", f"{where}: координаты вне диапазона")
    if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
        raise ScenarioError("outside_bbox", f"{where} ({lon}, {lat}) вне сохранённого квадрата города {bbox}")
    return lon, lat


def validate(obj, data):
    """Return a normalized scenario dict or raise ScenarioError. Never mutates obj or data."""
    if not isinstance(obj, dict):
        raise ScenarioError("shape", "сценарий должен быть объектом")
    extra = set(obj) - TOP_KEYS - OPTIONAL_TOP
    missing = TOP_KEYS - set(obj)
    if missing:
        raise ScenarioError("shape", f"нет полей {sorted(missing)}")
    if extra:
        raise ScenarioError("shape", f"неизвестные поля {sorted(extra)}")
    if obj["schema_version"] != SCHEMA:
        raise ScenarioError("version", f"неизвестная версия {obj['schema_version']!r}")
    city = obj["city_id"]
    if city not in CITIES or city not in data["cities"]:
        raise ScenarioError("city", f"неизвестный город {city!r}")
    if obj["category"] not in CATEGORIES:
        raise ScenarioError("category", f"категория {obj['category']!r} не входит в MVP {CATEGORIES}")
    expected = snapshot_id(data, city)
    if obj["source_snapshot"] != expected:
        raise ScenarioError("snapshot", "source_snapshot не совпадает с текущим срезом города (чужой или устаревший срез)")
    bbox = data["cities"][city]["bbox"]
    cps = obj["control_points"]
    if not isinstance(cps, list) or not 1 <= len(cps) <= MAX_POINTS:
        raise ScenarioError("points", f"контрольных точек должно быть 1..{MAX_POINTS}")
    pts, ids = [], set()
    for i, p in enumerate(cps):
        lon, lat = _point(p, POINT_KEYS, f"control_points[{i}]", bbox)
        if p["id"] in ids:
            raise ScenarioError("duplicate_id", f"id {p['id']!r} повторяется")
        ids.add(p["id"])
        pts.append({"id": p["id"], "lon": lon, "lat": lat})
    pr = obj["proposed_object"]
    proj = None
    if isinstance(pr, list):
        raise ScenarioError("project", "допускается не более одного проектного объекта")
    if pr is not None:
        lon, lat = _point(pr, PROJECT_KEYS, "proposed_object", bbox)
        if pr["kind"] != "hypothetical":
            raise ScenarioError("project", "proposed_object.kind должен быть 'hypothetical'")
        if pr["category"] != obj["category"]:
            raise ScenarioError("category", "категория проекта не совпадает с category сценария")
        if pr["id"] in ids:
            raise ScenarioError("duplicate_id", f"id {pr['id']!r} повторяется")
        proj = {"id": pr["id"], "lon": lon, "lat": lat, "category": pr["category"], "kind": "hypothetical"}
    return {"schema_version": SCHEMA, "city_id": city, "source_snapshot": expected, "category": obj["category"],
            "control_points": pts, "proposed_object": proj}


def load_scenario(raw, data):
    """bytes -> (normalized scenario, notes). 'computed' from the file is dropped and recomputed."""
    obj = parse_bytes(raw)
    notes = ["imported 'computed' ignored: recomputed from the slice"] if isinstance(obj, dict) and "computed" in obj else []
    return validate(obj, data), notes


# ---------------- computation ----------------
def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH_M * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def compute(sc, data):
    places = [p for p in data["cities"][sc["city_id"]]["places"] if p["group"] == sc["category"]]
    pr = sc["proposed_object"]
    rows = []
    for cp in sc["control_points"]:
        best = None
        for p in sorted(places, key=lambda p: p["id"]):
            d = haversine_m(cp["lon"], cp["lat"], p["lon"], p["lat"])
            if best is None or d < best[0]:
                best = (d, p)
        before = best[0] if best else None
        row = {"control_point_id": cp["id"], "before_m": before,
               "nearest_before": None if not best else {"id": best[1]["id"], "name": best[1].get("name"),
                                                        "sources": [s.get("dataset") for s in best[1].get("sources") or []],
                                                        "confidence": best[1].get("confidence")}}
        if pr is None:
            row.update(after_m=before, delta_m=0.0 if before is not None else None, nearest_after="source")
        else:
            dp = haversine_m(cp["lon"], cp["lat"], pr["lon"], pr["lat"])
            if before is None:
                row.update(after_m=dp, delta_m=None, nearest_after="proposed",
                           note="В срезе нет исходных записей; улучшение не вычисляется")
            else:
                after = min(before, dp)
                row.update(after_m=after, delta_m=before - after, nearest_after="proposed" if dp < before else "source")
        rows.append(row)
    return {"kind": "derived", "distance": DIST_PARAMS, "source_records_considered": len(places), "rows": rows}


def export(sc, data):
    out = dict(sc, computed=compute(sc, data))
    txt = json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False) + "\n"
    assert len(txt.encode("utf-8")) <= MAX_BYTES
    return txt


def explanation_digest(sc, data):
    """Digest over source_snapshot, category, points, project and recomputed values (for the template explanation)."""
    c = compute(sc, data)
    payload = [sc["source_snapshot"], sc["category"], [[p["id"], p["lon"], p["lat"]] for p in sc["control_points"]],
               None if sc["proposed_object"] is None else [sc["proposed_object"][k] for k in ("id", "lon", "lat")],
               [[r["control_point_id"], r["before_m"], r["after_m"], r["delta_m"]] for r in c["rows"]]]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()).hexdigest()[:16]


class ScenarioStore:
    """UI-like holder: a rejected import leaves the active scenario untouched; city/category change resets."""

    def __init__(self, data):
        self.data, self.active, self.message = data, None, None

    def import_bytes(self, raw):
        try:
            sc, notes = load_scenario(raw, self.data)
        except ScenarioError as e:
            self.message = f"Импорт отклонён ({e.code}); текущий сценарий не изменён"
            return False
        self.active, self.message = sc, "; ".join(notes) or None
        return True

    def switch(self, city_id, category):
        if self.active and (self.active["city_id"], self.active["category"]) != (city_id, category):
            self.active, self.message = None, "Город/категория изменены: сценарий и объяснение сброшены"


def main(argv):
    if len(argv) < 4 or argv[0] != "--app-root":
        print(__doc__); return 2
    data = load_slice(argv[1])
    cmd = argv[2]
    if cmd == "snapshot":
        print(snapshot_id(data, argv[3])); return 0
    raw = Path(argv[3]).read_bytes()
    try:
        sc, notes = load_scenario(raw, data)
    except ScenarioError as e:
        print(json.dumps({"valid": False, "code": e.code, "error": str(e)}, ensure_ascii=False)); return 1
    if cmd == "export":
        sys.stdout.write(export(sc, data)); return 0
    print(json.dumps({"valid": True, "notes": notes, "digest": explanation_digest(sc, data), "computed": compute(sc, data)},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
