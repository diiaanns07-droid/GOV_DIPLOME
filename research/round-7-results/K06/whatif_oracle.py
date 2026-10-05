"""K06 round 7: independent oracle for the "Если добавить объект" (city-whatif-v1) distance comparison.

Implements FEATURE_SPEC.txt (round 7) literally, standard library only:
  * haversine in metres, R = 6371008.8 m, input [longitude, latitude], intermediate clamped to [0, 1],
    computed without rounding (rounding only for display);
  * before = min distance to the matching source records of the category in the slice;
    after  = min(before, distance_to_proposed) if before is known;
    no source records: before = null, after = distance_to_proposed (if a project exists), delta = null;
    no project: after = before, delta = 0 if before is known (null otherwise);
    delta = before - after only when both are known; a positive delta is a smaller GEOMETRIC distance only;
  * ties: the nearest record is chosen stably by (distance, id); a tie never changes the length.
Distances are straight-line ("по прямой"). No walking time, flows, population or capacity are computed.

Independent check (not used by the oracle itself): chord_distance_m() computes the same great-circle distance
via 3-D unit vectors and 2*R*asin(chord/2), a different formula with different rounding behaviour.
"""
import math

R_EARTH_M = 6371008.8
CATEGORIES = ("school", "outpatient_clinic")
MAX_POINTS = 10
MAX_ID_LEN = 64


class ScenarioError(ValueError):
    pass


def _finite(*xs):
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in xs)


def haversine_m(lon1, lat1, lon2, lat2):
    """Spec formula. Raises on non-finite input; clamps the intermediate value to [0, 1]."""
    if not _finite(lon1, lat1, lon2, lat2):
        raise ScenarioError("non-finite coordinate")
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH_M * math.asin(math.sqrt(a))


def chord_distance_m(lon1, lat1, lon2, lat2):
    """Independent great-circle distance on the same sphere via the 3-D chord (for cross-checking only)."""
    def v(lon, lat):
        lo, la = math.radians(lon), math.radians(lat)
        return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    a, b = v(lon1, lat1), v(lon2, lat2)
    c = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return 2 * R_EARTH_M * math.asin(min(1.0, c / 2))


def nearest(point, records):
    """(distance_m, record) of the nearest record, ties broken by record id; (None, None) if no records."""
    best = None
    for r in records:
        d = haversine_m(point["lon"], point["lat"], r["lon"], r["lat"])
        key = (d, str(r["id"]))
        if best is None or key < best[0]:
            best = (key, r)
    return (None, None) if best is None else (best[0][0], best[1])


def in_bbox(lon, lat, bbox):
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def validate(scenario, bbox, require_points=True):
    """Structural checks of FEATURE_SPEC needed for the distance computation (not the full import validator)."""
    if scenario.get("category") not in CATEGORIES:
        raise ScenarioError("unknown category")
    pts = scenario.get("control_points") or []
    if require_points and not 1 <= len(pts) <= MAX_POINTS:
        raise ScenarioError("1..10 control points required")
    ids = set()
    proposed = scenario.get("proposed_object")
    for p in pts + ([proposed] if proposed else []):
        pid = p.get("id")
        if not isinstance(pid, str) or not pid or len(pid) > MAX_ID_LEN:
            raise ScenarioError("bad id")
        if pid in ids:
            raise ScenarioError("duplicate id " + pid)
        ids.add(pid)
        if not _finite(p.get("lon"), p.get("lat")):
            raise ScenarioError("non-finite coordinate in " + pid)
        if not (-180 <= p["lon"] <= 180 and -90 <= p["lat"] <= 90):
            raise ScenarioError("coordinate out of range in " + pid)
        if not in_bbox(p["lon"], p["lat"], bbox):
            raise ScenarioError("outside bbox: " + pid)
    if proposed is not None:
        if proposed.get("category") != scenario["category"] or proposed.get("kind") != "hypothetical":
            raise ScenarioError("proposed object must be hypothetical and of the selected category")


def compute(scenario, records, bbox):
    """Rows per control point: before/after/delta (metres, unrounded) and the source of the nearest record."""
    validate(scenario, bbox)
    cat = scenario["category"]
    pool = [r for r in records if r.get("group") == cat]   # same source sample before and after
    prop = scenario.get("proposed_object")
    rows = []
    for p in scenario["control_points"]:
        before, rec = nearest(p, pool)
        d_prop = haversine_m(p["lon"], p["lat"], prop["lon"], prop["lat"]) if prop else None
        if before is None:
            after, delta = d_prop, None
        elif prop is None:
            after, delta = before, 0.0
        else:
            after = min(before, d_prop)
            delta = before - after
        rows.append({"control_point": p["id"], "before_m": before, "after_m": after, "delta_m": delta,
                     "nearest_record_id": rec["id"] if rec else None,
                     "nearest_is_proposed": bool(prop) and after is not None and d_prop is not None and d_prop == after
                                            and (before is None or d_prop < before),
                     "note": "В срезе нет исходных записей; улучшение не вычисляется" if before is None else None})
    return rows
