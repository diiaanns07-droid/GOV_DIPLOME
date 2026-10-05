"""K10 round 7: reference calculation for FEATURE_SPEC «Если добавить объект» (city-whatif-v1). Stdlib only.

Distance: haversine in metres, R = 6371008.8, input [lon, lat], intermediate value clamped to [0, 1],
no rounding inside the calculation (round only for display).
before = min distance to source records of the scenario category (ties: smallest id, string order);
after  = min(before, d_proposed) when before is known; before None -> after = d_proposed (or None), delta None;
delta  = before - after when both known; without a proposed object after = before, delta = 0.
nearest_after: the proposed object only when d_proposed < before (a tie keeps the source record).
These tie/ordering details are K10 readings of the spec and are stated in every fixture.
"""
import hashlib
import json
import math

R_EARTH_M = 6371008.8
SCHEMA = "city-whatif-v1"
SNAPSHOT_SCHEMA = "k10-snapshot-v1"
CATEGORIES = ("school", "outpatient_clinic")
CITIES = ("shymkent", "astana")
FORMULA = {"name": "haversine", "radius_m": R_EARTH_M, "input": "[lon, lat]", "clamp": [0, 1], "rounding": "output only"}
EMPTY_LABEL = "В срезе нет исходных записей; улучшение не вычисляется"


def haversine_m(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    h = min(1.0, max(0.0, h))
    return 2 * R_EARTH_M * math.asin(math.sqrt(h))


def canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def snapshot_id(city, release, bbox, source_file_sha256, places):
    """Fingerprint of the slice used for the calculation (not a file name).

    places: list of {id, lon, lat, group} as delivered to the UI (web/data.js)."""
    comp = {"schema": SNAPSHOT_SCHEMA, "city": city, "release": release, "bbox": bbox,
            "places_social_sha256": source_file_sha256,
            "ui_places_digest": hashlib.sha256(canon(sorted([p["id"], p["lon"], p["lat"], p["group"]] for p in places)).encode()).hexdigest(),
            "formula": FORMULA}
    return "k10s1-" + hashlib.sha256(canon(comp).encode()).hexdigest()[:32], comp


def nearest(point, records):
    best = None
    for r in records:
        d = haversine_m((point["lon"], point["lat"]), (r["lon"], r["lat"]))
        if best is None or d < best[0] or (d == best[0] and r["id"] < best[1]["id"]):
            best = (d, r)
    return best


def compute(scenario, records):
    """records: source records of ALL categories in the slice ({id, lon, lat, group})."""
    cat = scenario["category"]
    pool = [r for r in records if r["group"] == cat]
    prop = scenario.get("proposed_object")
    rows = []
    for cp in scenario["control_points"]:
        nb = nearest(cp, pool)
        before = nb[0] if nb else None
        d_prop = haversine_m((cp["lon"], cp["lat"]), (prop["lon"], prop["lat"])) if prop else None
        if before is None:
            after, delta = d_prop, None
            after_src = prop["id"] if prop else None
        elif d_prop is None:
            after, delta, after_src = before, 0.0, nb[1]["id"]
        else:
            after = min(before, d_prop)
            delta = before - after
            after_src = prop["id"] if d_prop < before else nb[1]["id"]
        rows.append({"control_point_id": cp["id"], "before_m": before, "nearest_before_id": nb[1]["id"] if nb else None,
                     "distance_to_proposed_m": d_prop, "after_m": after, "nearest_after_id": after_src,
                     "delta_m": delta, "label": EMPTY_LABEL if before is None else None})
    return {"category_records_in_slice": len(pool), "rows": rows}


class ScenarioError(ValueError):
    def __init__(self, code, field):
        super().__init__(f"{code}: {field}")
        self.code, self.field = code, field


def validate(s, bbox, snapshot, max_points=10):
    """Minimal contract check used by the fixtures (bbox/category/ids/count/finite). Raises ScenarioError."""
    if s.get("schema_version") != SCHEMA:
        raise ScenarioError("BAD_SCHEMA_VERSION", "schema_version")
    if s.get("city_id") not in CITIES:
        raise ScenarioError("BAD_CITY", "city_id")
    if s.get("source_snapshot") != snapshot:
        raise ScenarioError("FOREIGN_SNAPSHOT", "source_snapshot")
    if s.get("category") not in CATEGORIES:
        raise ScenarioError("BAD_CATEGORY", "category")
    cps = s.get("control_points") or []
    if not 1 <= len(cps) <= max_points:
        raise ScenarioError("BAD_POINT_COUNT", "control_points")
    seen = set()
    pts = [(f"control_points[{i}]", p) for i, p in enumerate(cps)]
    if s.get("proposed_object") is not None:
        pts.append(("proposed_object", s["proposed_object"]))
        if s["proposed_object"].get("category") != s["category"]:
            raise ScenarioError("PROPOSED_CATEGORY_MISMATCH", "proposed_object.category")
        if s["proposed_object"].get("kind") != "hypothetical":
            raise ScenarioError("PROPOSED_NOT_HYPOTHETICAL", "proposed_object.kind")
    for field, p in pts:
        pid = p.get("id")
        if not isinstance(pid, str) or not 1 <= len(pid) <= 64 or pid in seen:
            raise ScenarioError("BAD_OR_DUPLICATE_ID", field + ".id")
        seen.add(pid)
        lon, lat = p.get("lon"), p.get("lat")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (lon, lat)):
            raise ScenarioError("NON_FINITE_COORDINATE", field)
        if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            raise ScenarioError("OUT_OF_BBOX", field)
    return True
