"""K10 round 8: independent Python oracle for CORE_SPEC city-plan-v2 (stdlib only).

Written from research/round-8/CORE_SPEC.txt, not translated from any JS implementation.
Distances: haversine R=6371008.8 m, input [lon, lat], intermediate clamped to [0, 1]; every distance is rounded
once to integer millimetres with floor(d_m*1000 + 0.5) (metric_version "haversine-mm-v1").
Ties between equally distant facilities: key (kind_rank, id) with source=0 < hypothetical=1.

Public functions (JSON-compatible dicts in / out):
  parse_strict(text)                       -> object or raises PlanError("bad_json"/"too_large"/...)
  validate_plan_scenario(obj, context)     -> normalised scenario or raises PlanError(code, detail)
  evaluate_plan(context, scenario, ids)    -> {"rows", "metrics", "feasibility"}
  optimize_plans(context, scenario, opts)  -> {"status", "objectives", "pareto", "evaluated", "feasible_count",
                                               "problem_digest", "metric_version", "sensitivity"}
context = {"city_id", "bbox", "source_snapshot", "records": [{"id","lon","lat","group"}], "versions": {...}}
          a context with "synthetic": True may use a city_id outside CITIES (synthetic test geometry only).
"""
import hashlib
import itertools
import json
import math

SCHEMA = "city-plan-v2"
METRIC_VERSION = "haversine-mm-v1"
R_EARTH_M = 6371008.8
CITIES = ("shymkent", "astana")
CATEGORIES = ("school", "outpatient_clinic")
MAX_BYTES = 256 * 1024
TOP_KEYS = {"schema_version", "city_id", "source_snapshot", "category", "control_points", "candidates", "budget",
            "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"}
OPTIONAL_TOP = {"derived_results"}
CP_KEYS = {"id", "lon", "lat", "weight"}
CAND_KEYS = {"id", "lon", "lat", "category", "kind", "cost"}
INF = float("inf")


class PlanError(ValueError):
    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# ---------------------------------------------------------------- geometry
def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH_M * math.asin(math.sqrt(a))


def to_mm(d_m):
    return int(math.floor(d_m * 1000 + 0.5))


# ---------------------------------------------------------------- strict JSON
def parse_strict(text):
    if isinstance(text, bytes):
        if len(text) > MAX_BYTES:
            raise PlanError("too_large", f"{len(text)} bytes > {MAX_BYTES}")
        text = text.decode("utf-8")
    elif len(text.encode("utf-8")) > MAX_BYTES:
        raise PlanError("too_large", "> 256 KiB")

    def pairs(kv):
        d = {}
        for k, v in kv:
            if k in d:
                raise PlanError("duplicate_key", k)
            d[k] = v
        return d

    def bad_const(c):
        raise PlanError("non_finite", c)

    def flt(s):
        v = float(s)
        if not math.isfinite(v):
            raise PlanError("non_finite", s)
        return v

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_const, parse_float=flt)
    except PlanError:
        raise
    except ValueError as e:
        raise PlanError("bad_json", str(e)) from None


# ---------------------------------------------------------------- validation
def _int(v, lo, hi, what):
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise PlanError("bad_value", f"{what}: integer {lo}..{hi} expected")
    return v


def _id(v, what):
    if not isinstance(v, str) or not 1 <= len(v) <= 64:
        raise PlanError("bad_id", f"{what}: string of 1..64 chars expected")
    return v


def _coord(p, bbox, what):
    lon, lat = p.get("lon"), p.get("lat")
    for v in (lon, lat):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise PlanError("bad_coordinate", what)
    if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
        raise PlanError("out_of_bbox", what)
    return float(lon), float(lat)


def _id_list(v, what, known):
    if not isinstance(v, list):
        raise PlanError("bad_shape", f"{what}: array expected")
    out = [_id(x, f"{what}[{i}]") for i, x in enumerate(v)]
    if len(set(out)) != len(out):
        raise PlanError("duplicate_id", what)
    unknown = [x for x in out if x not in known]
    if unknown:
        raise PlanError("unknown_candidate", f"{what}: {unknown[0]}")
    return sorted(out)


def validate_plan_scenario(obj, context):
    if not isinstance(obj, dict):
        raise PlanError("bad_shape", "object expected")
    keys = set(obj)
    if not TOP_KEYS <= keys:
        raise PlanError("missing_field", ",".join(sorted(TOP_KEYS - keys)))
    extra = keys - TOP_KEYS - OPTIONAL_TOP
    if extra:
        raise PlanError("unexpected_field", ",".join(sorted(extra)))
    if obj["schema_version"] != SCHEMA:
        raise PlanError("bad_schema_version", str(obj["schema_version"]))
    if obj["city_id"] != context["city_id"] or (obj["city_id"] not in CITIES and not context.get("synthetic")):
        raise PlanError("bad_city", str(obj["city_id"]))
    if obj["source_snapshot"] != context["source_snapshot"]:
        raise PlanError("foreign_snapshot", "source_snapshot differs from the current slice")
    if obj["category"] not in CATEGORIES:
        raise PlanError("bad_category", str(obj["category"]))
    bbox = context["bbox"]
    cps = obj["control_points"]
    if not isinstance(cps, list) or not 1 <= len(cps) <= 25:
        raise PlanError("bad_point_count", "control_points: 1..25")
    out_cps, seen = [], set()
    for i, p in enumerate(cps):
        what = f"control_points[{i}]"
        if not isinstance(p, dict) or set(p) != CP_KEYS:
            raise PlanError("bad_shape", f"{what}: fields {sorted(CP_KEYS)}")
        pid = _id(p["id"], what + ".id")
        if pid in seen:
            raise PlanError("duplicate_id", what + ".id")
        seen.add(pid)
        lon, lat = _coord(p, bbox, what)
        out_cps.append({"id": pid, "lon": lon, "lat": lat, "weight": _int(p["weight"], 1, 100, what + ".weight")})
    cands = obj["candidates"]
    if not isinstance(cands, list) or not 0 <= len(cands) <= 16:
        raise PlanError("bad_candidate_count", "candidates: 0..16")
    out_c, seen = [], set()
    for i, c in enumerate(cands):
        what = f"candidates[{i}]"
        if not isinstance(c, dict) or set(c) != CAND_KEYS:
            raise PlanError("bad_shape", f"{what}: fields {sorted(CAND_KEYS)}")
        cid = _id(c["id"], what + ".id")
        if cid in seen:
            raise PlanError("duplicate_id", what + ".id")
        seen.add(cid)
        if c["category"] != obj["category"]:
            raise PlanError("candidate_category_mismatch", what)
        if c["kind"] != "hypothetical":
            raise PlanError("candidate_not_hypothetical", what)
        lon, lat = _coord(c, bbox, what)
        out_c.append({"id": cid, "lon": lon, "lat": lat, "category": c["category"], "kind": "hypothetical",
                      "cost": _int(c["cost"], 1, 1000000, what + ".cost")})
    known = {c["id"] for c in out_c}
    req = _id_list(obj["required_ids"], "required_ids", known)
    exc = _id_list(obj["excluded_ids"], "excluded_ids", known)
    if set(req) & set(exc):
        raise PlanError("required_excluded_overlap", ",".join(sorted(set(req) & set(exc))))
    sel = _id_list(obj["selected_ids"], "selected_ids", known)
    return {"schema_version": SCHEMA, "city_id": obj["city_id"], "source_snapshot": obj["source_snapshot"],
            "category": obj["category"], "control_points": out_cps, "candidates": out_c,
            "budget": _int(obj["budget"], 0, 1000000, "budget"), "max_selected": _int(obj["max_selected"], 0, 5, "max_selected"),
            "coverage_radius_m": _int(obj["coverage_radius_m"], 100, 5000, "coverage_radius_m"),
            "required_ids": req, "excluded_ids": exc, "selected_ids": sel}


# ---------------------------------------------------------------- digests
def _canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def problem_payload(sc):
    return {"schema_version": sc["schema_version"], "metric_version": METRIC_VERSION, "city_id": sc["city_id"],
            "source_snapshot": sc["source_snapshot"], "category": sc["category"],
            "control_points": sorted([p["id"], p["lon"], p["lat"], p["weight"]] for p in sc["control_points"]),
            "candidates": sorted([c["id"], c["lon"], c["lat"], c["cost"]] for c in sc["candidates"]),
            "budget": sc["budget"], "max_selected": sc["max_selected"], "coverage_radius_m": sc["coverage_radius_m"],
            "required_ids": sorted(sc["required_ids"]), "excluded_ids": sorted(sc["excluded_ids"])}


def problem_digest(sc):
    return "sha256:" + hashlib.sha256(_canon(problem_payload(sc)).encode("utf-8")).hexdigest()


def scenario_digest(sc):
    p = problem_payload(sc)
    p["selected_ids"] = sorted(sc["selected_ids"])
    return "sha256:" + hashlib.sha256(_canon(p).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- precomputation
class Matrix:
    """Distances in mm, computed once: base[i] = (mm, id) of nearest source record or None; cand[i][j] = mm."""

    def __init__(self, context, sc):
        pool = sorted((r for r in context["records"] if r["group"] == sc["category"]), key=lambda r: r["id"])
        self.cps = sc["control_points"]
        self.cands = sc["candidates"]
        self.cand_index = {c["id"]: j for j, c in enumerate(self.cands)}
        self.base = []
        for p in self.cps:
            best = None
            for r in pool:
                key = (to_mm(haversine_m(p["lon"], p["lat"], r["lon"], r["lat"])), 0, r["id"])
                if best is None or key < best:
                    best = key
            self.base.append(best)
        self.cand = [[to_mm(haversine_m(p["lon"], p["lat"], c["lon"], c["lat"])) for c in self.cands] for p in self.cps]
        self.weights = [p["weight"] for p in self.cps]
        self.total_weight = sum(self.weights)
        self.pool_size = len(pool)


def _after(m, i, sel_idx):
    best = m.base[i]
    for j in sel_idx:
        key = (m.cand[i][j], 1, m.cands[j]["id"])
        if best is None or key < best:
            best = key
    return best


def _metrics(m, sc, sel_idx):
    unknown = wsum = covered = 0
    mx = None
    afters = []
    rad = sc["coverage_radius_m"] * 1000
    for i, w in enumerate(m.weights):
        a = _after(m, i, sel_idx)
        afters.append(a)
        if a is None:
            unknown += 1
            continue
        wsum += w * a[0]
        mx = a[0] if mx is None else max(mx, a[0])
        if a[0] <= rad:
            covered += w
    cost = sum(m.cands[j]["cost"] for j in sel_idx)
    ids = sorted(m.cands[j]["id"] for j in sel_idx)
    met = {"unknown_count": unknown, "weighted_sum_mm": wsum,
           "weighted_mean_mm": (wsum / m.total_weight) if unknown == 0 else None,
           "max_mm": mx if unknown == 0 else None, "covered_weight": covered,
           "coverage_fraction": covered / m.total_weight, "cost": cost, "selected_ids": ids}
    return met, afters


def _feasible(m, sc, sel_idx):
    ids = {m.cands[j]["id"] for j in sel_idx}
    reasons = []
    if len(sel_idx) > sc["max_selected"]:
        reasons.append("count_exceeds_max_selected")
    if sum(m.cands[j]["cost"] for j in sel_idx) > sc["budget"]:
        reasons.append("cost_exceeds_budget")
    if set(sc["required_ids"]) - ids:
        reasons.append("required_missing")
    if ids & set(sc["excluded_ids"]):
        reasons.append("excluded_selected")
    return not reasons, reasons


def _ref(kind, rid):
    return None if rid is None else {"kind": kind, "id": rid}


def evaluate_plan(context, sc, selected_ids, _m=None):
    m = _m or Matrix(context, sc)
    unknown_ids = [x for x in selected_ids if x not in m.cand_index]
    if unknown_ids:
        raise PlanError("unknown_candidate", unknown_ids[0])
    sel_idx = sorted(m.cand_index[x] for x in set(selected_ids))
    met, afters = _metrics(m, sc, sel_idx)
    rows = []
    for i, p in enumerate(m.cps):
        b, a = m.base[i], afters[i]
        rows.append({"control_point_id": p["id"], "weight": p["weight"],
                     "before_mm": b[0] if b else None, "nearest_before": _ref("source", b[2]) if b else None,
                     "after_mm": a[0] if a else None,
                     "nearest_after": _ref("source" if a[1] == 0 else "hypothetical", a[2]) if a else None,
                     "delta_mm": (b[0] - a[0]) if (b is not None and a is not None) else None})
    ok, reasons = _feasible(m, sc, sel_idx)
    return {"rows": rows, "metrics": met, "feasibility": {"feasible": ok, "reasons": reasons},
            "baseline_records_in_category": m.pool_size}


# ---------------------------------------------------------------- exact search
def _keys(met):
    mx = met["max_mm"] if met["max_mm"] is not None else INF
    ids = met["selected_ids"]
    return {"mean": (met["unknown_count"], met["weighted_sum_mm"], mx, met["cost"], ids),
            "minimax": (met["unknown_count"], mx, met["weighted_sum_mm"], met["cost"], ids),
            "coverage": (-met["covered_weight"], met["unknown_count"], met["weighted_sum_mm"], mx, met["cost"], ids)}


def _infeasible_reasons(sc, m):
    req = [m.cand_index[x] for x in sc["required_ids"]]
    out = []
    if len(req) > sc["max_selected"]:
        out.append("required_count_exceeds_max_selected")
    if sum(m.cands[j]["cost"] for j in req) > sc["budget"]:
        out.append("required_cost_exceeds_budget")
    return out or ["no_subset_satisfies_constraints"]


def _search(m, sc):
    allowed = [j for j, c in enumerate(m.cands) if c["id"] not in set(sc["excluded_ids"])]
    req = sorted(m.cand_index[x] for x in sc["required_ids"])
    free = [j for j in allowed if j not in req]
    evaluated = feasible = 0
    best = {"mean": None, "minimax": None, "coverage": None}
    plans = []
    for k in range(0, max(0, sc["max_selected"] - len(req)) + 1):
        if len(req) + k > sc["max_selected"]:
            break
        for extra in itertools.combinations(free, k):
            sel = sorted(req + list(extra))
            evaluated += 1
            if sum(m.cands[j]["cost"] for j in sel) > sc["budget"]:
                continue
            feasible += 1
            met, _ = _metrics(m, sc, sel)
            plans.append(met)
            ks = _keys(met)
            for name in best:
                if best[name] is None or ks[name] < best[name][0]:
                    best[name] = (ks[name], met)
    return evaluated, feasible, best, plans


def _pareto(plans):
    full = [p for p in plans if p["unknown_count"] == 0]
    rep = {}
    for p in full:  # equal (cost, wsum) pairs collapse to the smallest sorted ids
        k = (p["cost"], p["weighted_sum_mm"])
        if k not in rep or p["selected_ids"] < rep[k]["selected_ids"]:
            rep[k] = p
    pts = sorted(rep.values(), key=lambda p: (p["cost"], p["weighted_sum_mm"], p["selected_ids"]))
    front, best_wsum = [], None
    for p in pts:  # sorted by cost asc: keep a point only if it strictly improves wsum
        if best_wsum is None or p["weighted_sum_mm"] < best_wsum:
            front.append({"cost": p["cost"], "weighted_sum_mm": p["weighted_sum_mm"], "selected_ids": p["selected_ids"]})
            best_wsum = p["weighted_sum_mm"]
    return front, len(full) < len(plans)


def optimize_plans(context, sc, options=None):
    options = options or {}
    m = Matrix(context, sc)
    evaluated, feasible, best, plans = _search(m, sc)
    out = {"status": "optimal" if feasible else "infeasible", "metric_version": METRIC_VERSION,
           "problem_digest": problem_digest(sc), "evaluated": evaluated, "feasible_count": feasible,
           "candidate_count": len(m.cands), "objectives": None, "pareto": [], "pareto_note": None}
    if not feasible:
        out["infeasible_reasons"] = _infeasible_reasons(sc, m)
    else:
        out["objectives"] = {k: v[1] for k, v in best.items()}
        out["pareto"], partial = _pareto(plans)
        if partial:
            out["pareto_note"] = "plans with unknown_count>0 are not placed on the cost/distance front"
    if options.get("sensitivity", True):
        sens = []
        for b in sorted({0, sc["budget"] // 2, sc["budget"]}):
            s2 = dict(sc, budget=b)
            r = optimize_plans(context, s2, {"sensitivity": False})
            sens.append({"budget": b, "status": r["status"],
                         "objectives": {k: {"selected_ids": v["selected_ids"], "cost": v["cost"],
                                            "weighted_sum_mm": v["weighted_sum_mm"], "max_mm": v["max_mm"],
                                            "covered_weight": v["covered_weight"], "unknown_count": v["unknown_count"]}
                                        for k, v in (r["objectives"] or {}).items()},
                         "infeasible_reasons": r.get("infeasible_reasons")})
        out["sensitivity"] = sens
    return out
