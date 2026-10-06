"""K06 round 8: independent Python oracle for city-plan-v2 (CORE_SPEC.txt, round 8).

Written from the specification, not translated from any JS implementation. Standard library only.

Metric "haversine-mm-v1": haversine, R = 6371008.8 m, input [lon, lat], intermediate clamped to [0, 1];
every distance rounded ONCE to integer millimetres with floor(d_m * 1000 + 0.5) (all values >= 0).
Distances are straight-line inside the slice: no walking time, population, capacity or traffic.

API (JSON-compatible dicts):
  parse_strict(text)                          -> object; rejects >256 KiB, duplicate keys, NaN/Infinity/1e999
  validate(scenario, context)                 -> normalised scenario, or raises PlanError(code, detail)
  evaluate(context, scenario, selected_ids)   -> {"rows", "metrics", "feasible", "reasons", "selected_ids"}
  optimize(context, scenario)                 -> {"status", "objectives": {mean, minimax, coverage}, "pareto",
                                                  "evaluated", "feasible_count", "problem_digest", "metric_version"}
  sensitivity(context, scenario)              -> [{"budget", "status", "objectives"}] for budgets [0, B//2, B]
  problem_digest(context, scenario)           -> order-independent sha256 of the optimisation problem
context = {"city_id", "bbox": [W, S, E, N], "source_snapshot", "records": [{"id", "lon", "lat", "group"}]}

Conventions where the spec leaves a choice (documented, checked by tests):
  * tie between equal millimetre distances: key (mm, namespace, id), namespace "source" < "hypothetical";
  * "evaluated" = subsets enumerated after fixing required and removing excluded (2 ** n_free, or 0 when the
    required set alone is infeasible); "feasible_count" = those within budget and max_selected;
  * a Pareto point is (cost, weighted_sum_mm) of a feasible plan with unknown_count == 0; equal pairs collapse
    to the plan with the lexicographically smallest sorted IDs; sorted by (cost, weighted_sum_mm).
"""
import hashlib
import json
import math
from itertools import combinations

METRIC_VERSION = "haversine-mm-v1"
SCHEMA = "city-plan-v2"
R_EARTH_M = 6371008.8
CATEGORIES = ("school", "outpatient_clinic")
MAX_JSON_BYTES = 256 * 1024
MAX_ID = 64
LIMITS = {"points": (1, 25), "candidates": (0, 16), "max_selected": (0, 5), "weight": (1, 100),
          "cost": (1, 1_000_000), "budget": (0, 1_000_000), "radius": (100, 5000)}
FIELDS = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
          "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"}
OPTIONAL_FIELDS = {"derived_results"}           # allowed but never trusted
INF = float("inf")
NS_RANK = {"source": 0, "hypothetical": 1}      # tie order: source before hypothetical (NOT alphabetical)


class PlanError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# ---------------------------------------------------------------------------------------------- distance
def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R_EARTH_M * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def to_mm(d_m):
    return math.floor(d_m * 1000 + 0.5)


def dist_mm(a, b):
    return to_mm(haversine_m(a["lon"], a["lat"], b["lon"], b["lat"]))


# ---------------------------------------------------------------------------------------------- strict JSON
def parse_strict(text):
    if isinstance(text, bytes):
        if len(text) > MAX_JSON_BYTES:
            raise PlanError("too_large", f"{len(text)} bytes")
        text = text.decode("utf-8")
    elif len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise PlanError("too_large", "> 256 KiB")

    def no_dupes(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise PlanError("duplicate_key", k)
            obj[k] = v
        return obj

    def bad_const(name):
        raise PlanError("non_finite", name)

    def num(s):
        v = float(s)
        if not math.isfinite(v):
            raise PlanError("non_finite", s)
        return v

    try:
        return json.loads(text, object_pairs_hook=no_dupes, parse_constant=bad_const, parse_float=num)
    except json.JSONDecodeError as e:
        raise PlanError("bad_json", str(e))


# ---------------------------------------------------------------------------------------------- validation
def _int_in(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, int) and not (isinstance(v, float) and v.is_integer()):
        raise PlanError("bad_integer", what)
    v = int(v)
    if not lo <= v <= hi:
        raise PlanError("out_of_range", f"{what}={v}")
    return v


def _id(v, what):
    if not isinstance(v, str) or not v or len(v) > MAX_ID:
        raise PlanError("bad_id", what)
    return v


def _coord(o, bbox, what):
    lon, lat = o.get("lon"), o.get("lat")
    for v in (lon, lat):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise PlanError("bad_coordinate", what)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise PlanError("bad_coordinate", what)
    if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
        raise PlanError("outside_bbox", what)
    return float(lon), float(lat)


def _unique_ids(lst, what):
    ids = [_id(x, what) for x in lst]
    if len(set(ids)) != len(ids):
        raise PlanError("duplicate_id", what)
    return ids


def validate(sc, ctx):
    if not isinstance(sc, dict):
        raise PlanError("bad_shape", "scenario must be an object")
    extra = set(sc) - FIELDS - OPTIONAL_FIELDS
    if extra:
        raise PlanError("unexpected_field", ",".join(sorted(extra)))
    missing = FIELDS - set(sc)
    if missing:
        raise PlanError("missing_field", ",".join(sorted(missing)))
    if sc["schema_version"] != SCHEMA:
        raise PlanError("bad_version", str(sc["schema_version"]))
    if sc["city_id"] != ctx["city_id"]:
        raise PlanError("foreign_city", str(sc["city_id"]))
    if sc["source_snapshot"] != ctx["source_snapshot"]:
        raise PlanError("foreign_snapshot", str(sc["source_snapshot"]))
    if sc["category"] not in CATEGORIES:
        raise PlanError("bad_category", str(sc["category"]))
    bbox = ctx["bbox"]
    pts = sc["control_points"]
    if not isinstance(pts, list) or not LIMITS["points"][0] <= len(pts) <= LIMITS["points"][1]:
        raise PlanError("bad_points", "1..25 control points")
    _unique_ids([p.get("id") if isinstance(p, dict) else None for p in pts], "control_points")
    npts = []
    for p in pts:
        if set(p) - {"id", "lon", "lat", "weight"}:
            raise PlanError("unexpected_field", "control_point")
        lon, lat = _coord(p, bbox, p["id"])
        npts.append({"id": p["id"], "lon": lon, "lat": lat,
                     "weight": _int_in(p.get("weight", 1), *LIMITS["weight"], "weight")})
    cands = sc["candidates"]
    if not isinstance(cands, list) or len(cands) > LIMITS["candidates"][1]:
        raise PlanError("bad_candidates", "0..16 candidates")
    cids = _unique_ids([c.get("id") if isinstance(c, dict) else None for c in cands], "candidates")
    ncands = []
    for c in cands:
        if set(c) - {"id", "lon", "lat", "category", "kind", "cost"}:
            raise PlanError("unexpected_field", "candidate")
        if c.get("kind") != "hypothetical" or c.get("category") != sc["category"]:
            raise PlanError("bad_candidate", c["id"])
        lon, lat = _coord(c, bbox, c["id"])
        ncands.append({"id": c["id"], "lon": lon, "lat": lat, "category": c["category"], "kind": "hypothetical",
                       "cost": _int_in(c.get("cost"), *LIMITS["cost"], "cost")})
    budget = _int_in(sc["budget"], *LIMITS["budget"], "budget")
    max_sel = _int_in(sc["max_selected"], *LIMITS["max_selected"], "max_selected")
    radius = _int_in(sc["coverage_radius_m"], *LIMITS["radius"], "coverage_radius_m")
    lists = {}
    for k in ("required_ids", "excluded_ids", "selected_ids"):
        if not isinstance(sc[k], list):
            raise PlanError("bad_shape", k)
        lists[k] = _unique_ids(sc[k], k)
        unknown = set(lists[k]) - set(cids)
        if unknown:
            raise PlanError("unknown_candidate", f"{k}: {sorted(unknown)}")
    if set(lists["required_ids"]) & set(lists["excluded_ids"]):
        raise PlanError("required_excluded_overlap", "")
    return {"schema_version": SCHEMA, "city_id": sc["city_id"], "source_snapshot": sc["source_snapshot"],
            "category": sc["category"], "control_points": npts, "candidates": ncands, "budget": budget,
            "max_selected": max_sel, "coverage_radius_m": radius, **lists}


# ---------------------------------------------------------------------------------------------- evaluation
class Problem:
    """Precomputed millimetre distances; the search never calls haversine."""

    def __init__(self, ctx, sc):
        self.sc = sc
        self.points = sc["control_points"]
        self.cands = {c["id"]: c for c in sc["candidates"]}
        srcs = sorted((r for r in ctx["records"] if r.get("group") == sc["category"]), key=lambda r: str(r["id"]))
        self.base = []                       # per point: (mm, "source", id) or None
        for p in self.points:
            best = min(((dist_mm(p, r), NS_RANK["source"], str(r["id"])) for r in srcs), default=None)
            self.base.append(best)
        self.cmm = {cid: [dist_mm(p, c) for p in self.points] for cid, c in self.cands.items()}
        self.total_w = sum(p["weight"] for p in self.points)
        self.radius_mm = sc["coverage_radius_m"] * 1000

    def rows_metrics(self, ids):
        ids = sorted(ids)
        rows, unknown, wsum, mx, covered = [], 0, 0, 0, 0
        for i, p in enumerate(self.points):
            best = self.base[i]
            for cid in ids:
                k = (self.cmm[cid][i], NS_RANK["hypothetical"], cid)
                if best is None or k < best:
                    best = k
            before = self.base[i][0] if self.base[i] else None
            after = best[0] if best else None
            rows.append({"control_point": p["id"], "weight": p["weight"], "before_mm": before, "after_mm": after,
                         "delta_mm": None if before is None or after is None else before - after,
                         "nearest": None if best is None else {"kind": ("source", "hypothetical")[best[1]], "id": best[2]}})
            if after is None:
                unknown += 1
                continue
            wsum += p["weight"] * after
            mx = max(mx, after)
            if after <= self.radius_mm:
                covered += p["weight"]
        cost = sum(self.cands[c]["cost"] for c in ids)
        m = {"unknown_count": unknown, "weighted_sum_mm": wsum,
             "weighted_mean_mm": wsum / self.total_w if unknown == 0 else None,
             "max_mm": mx if unknown == 0 else None, "covered_weight": covered,
             "coverage_fraction": covered / self.total_w, "cost": cost, "count": len(ids)}
        return rows, m

    def feasibility(self, ids):
        s, reasons = set(ids), []
        if len(ids) > self.sc["max_selected"]:
            reasons.append("count_exceeds_max_selected")
        if sum(self.cands[c]["cost"] for c in ids) > self.sc["budget"]:
            reasons.append("cost_exceeds_budget")
        if not set(self.sc["required_ids"]) <= s:
            reasons.append("required_missing")
        if s & set(self.sc["excluded_ids"]):
            reasons.append("excluded_selected")
        return reasons


def evaluate(ctx, sc, selected_ids):
    sc = validate(sc, ctx)
    pr = Problem(ctx, sc)
    unknown = set(selected_ids) - set(pr.cands)
    if unknown or len(set(selected_ids)) != len(selected_ids):
        raise PlanError("bad_selection", str(sorted(unknown)))
    rows, m = pr.rows_metrics(selected_ids)
    reasons = pr.feasibility(selected_ids)
    return {"selected_ids": sorted(selected_ids), "rows": rows, "metrics": m, "feasible": not reasons, "reasons": reasons}


def objective_keys(m, ids):
    mx = INF if m["max_mm"] is None else m["max_mm"]
    sid = sorted(ids)
    return {"mean": (m["unknown_count"], m["weighted_sum_mm"], mx, m["cost"], sid),
            "minimax": (m["unknown_count"], mx, m["weighted_sum_mm"], m["cost"], sid),
            "coverage": (-m["covered_weight"], m["unknown_count"], m["weighted_sum_mm"], mx, m["cost"], sid)}


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def problem_digest(ctx, sc, include_selected=False):
    sc = validate(sc, ctx)
    body = {"schema": SCHEMA, "metric_version": METRIC_VERSION, "city_id": sc["city_id"],
            "source_snapshot": sc["source_snapshot"], "category": sc["category"],
            "control_points": sorted(([p["id"], p["lon"], p["lat"], p["weight"]] for p in sc["control_points"])),
            "candidates": sorted(([c["id"], c["lon"], c["lat"], c["cost"]] for c in sc["candidates"])),
            "budget": sc["budget"], "max_selected": sc["max_selected"], "coverage_radius_m": sc["coverage_radius_m"],
            "required_ids": sorted(sc["required_ids"]), "excluded_ids": sorted(sc["excluded_ids"])}
    if include_selected:
        body["selected_ids"] = sorted(sc["selected_ids"])
    return "sha256:" + hashlib.sha256(_canon(body).encode()).hexdigest()


def optimize(ctx, sc):
    sc = validate(sc, ctx)
    pr = Problem(ctx, sc)
    req = sorted(sc["required_ids"])
    free = sorted(set(pr.cands) - set(req) - set(sc["excluded_ids"]))
    out = {"metric_version": METRIC_VERSION, "problem_digest": problem_digest(ctx, sc), "objectives": None,
           "pareto": [], "evaluated": 0, "feasible_count": 0}
    req_cost = sum(pr.cands[c]["cost"] for c in req)
    reasons = []
    if len(req) > sc["max_selected"]:
        reasons.append("required_count_exceeds_max_selected")
    if req_cost > sc["budget"]:
        reasons.append("required_cost_exceeds_budget")
    if reasons:
        return dict(out, status="infeasible", reasons=reasons)
    best = {}
    front = {}                                             # (cost, wsum) -> sorted ids
    for k in range(0, len(free) + 1):
        for extra in combinations(free, k):
            out["evaluated"] += 1
            ids = req + list(extra)
            if len(ids) > sc["max_selected"]:
                continue
            cost = req_cost + sum(pr.cands[c]["cost"] for c in extra)
            if cost > sc["budget"]:
                continue
            out["feasible_count"] += 1
            _, m = pr.rows_metrics(ids)
            for name, key in objective_keys(m, ids).items():
                if name not in best or key < best[name][0]:
                    best[name] = (key, sorted(ids), m)
            if m["unknown_count"] == 0:
                pt = (m["cost"], m["weighted_sum_mm"])
                if pt not in front or sorted(ids) < front[pt]:
                    front[pt] = sorted(ids)
    pareto = []
    for (c, w), ids in sorted(front.items()):
        if not any(c2 <= c and w2 <= w and (c2, w2) != (c, w) for (c2, w2) in front):
            pareto.append({"selected_ids": ids, "cost": c, "weighted_sum_mm": w})
    out["objectives"] = {n: {"selected_ids": v[1], "metrics": v[2]} for n, v in best.items()}
    out["pareto"] = pareto
    out["status"] = "optimal"
    return out


def sensitivity(ctx, sc):
    sc = validate(sc, ctx)
    res = []
    for b in sorted({0, sc["budget"] // 2, sc["budget"]}):
        r = optimize(ctx, dict(sc, budget=b))
        res.append({"budget": b, "status": r["status"], "reasons": r.get("reasons", []),
                    "objectives": {n: v["selected_ids"] for n, v in (r["objectives"] or {}).items()}})
    return res
