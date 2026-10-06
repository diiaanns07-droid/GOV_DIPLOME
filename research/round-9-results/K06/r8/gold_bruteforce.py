"""K06 round 8 stage 2: deliberately different brute-force "gold" solver for small city-plan-v2 problems.

Independent of plan_oracle.py on purpose (no shared code):
  * enumerates ALL 2**n bitmasks over every candidate and filters constraints afterwards (oracle: combinations of
    free candidates only);
  * recomputes every distance inside every subset from coordinates (oracle: precomputed matrix);
  * builds the full list of plans and picks winners with sorted() on explicit key tuples (oracle: running minimum);
  * Pareto by O(n^2) pairwise dominance over all complete plans, then collapses equal (cost, sum) pairs
    (oracle: dictionary of points).
Only the spec formula itself (haversine + clamp + floor(x*1000+0.5)) is necessarily the same.
Input is assumed already valid (validation is tested separately). Suitable for n <= 10 candidates.
"""
import math

R = 6371008.8


def _mm(lon1, lat1, lon2, lat2):
    f1, f2 = lat1 * math.pi / 180, lat2 * math.pi / 180
    h = math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin((lon2 - lon1) * math.pi / 360) ** 2
    if h > 1:
        h = 1.0
    if h < 0:
        h = 0.0
    return math.floor(2 * R * math.asin(h ** 0.5) * 1000 + 0.5)


def _plan_metrics(sources, points, chosen, radius_m):
    wsum, unknown, worst, cov, wall = 0, 0, None, 0, 0
    for p in points:
        wall += p["weight"]
        ds = [_mm(p["lon"], p["lat"], s["lon"], s["lat"]) for s in sources] + \
             [_mm(p["lon"], p["lat"], c["lon"], c["lat"]) for c in chosen]
        if not ds:
            unknown += 1
            continue
        d = min(ds)
        wsum += p["weight"] * d
        worst = d if worst is None or d > worst else worst
        if d <= radius_m * 1000:
            cov += p["weight"]
    return {"unknown_count": unknown, "weighted_sum_mm": wsum, "max_mm": worst if unknown == 0 else None,
            "covered_weight": cov, "cost": sum(c["cost"] for c in chosen)}


def solve(records, sc):
    sources = [r for r in records if r["group"] == sc["category"]]
    cands = sc["candidates"]
    n = len(cands)
    req, exc = set(sc["required_ids"]), set(sc["excluded_ids"])
    if len(req) > sc["max_selected"] or sum(c["cost"] for c in cands if c["id"] in req) > sc["budget"]:
        why = []
        if len(req) > sc["max_selected"]:
            why.append("required_count_exceeds_max_selected")
        if sum(c["cost"] for c in cands if c["id"] in req) > sc["budget"]:
            why.append("required_cost_exceeds_budget")
        return {"status": "infeasible", "reasons": why, "feasible_count": 0, "objectives": None, "pareto": []}
    plans = []
    for mask in range(1 << n):
        chosen = [cands[i] for i in range(n) if mask >> i & 1]
        ids = sorted(c["id"] for c in chosen)
        if not req.issubset(ids) or exc.intersection(ids):
            continue
        if len(chosen) > sc["max_selected"] or sum(c["cost"] for c in chosen) > sc["budget"]:
            continue
        m = _plan_metrics(sources, sc["control_points"], chosen, sc["coverage_radius_m"])
        plans.append((ids, m))
    big = float("inf")
    mx = lambda m: big if m["max_mm"] is None else m["max_mm"]
    keyf = {"mean": lambda t: (t[1]["unknown_count"], t[1]["weighted_sum_mm"], mx(t[1]), t[1]["cost"], t[0]),
            "minimax": lambda t: (t[1]["unknown_count"], mx(t[1]), t[1]["weighted_sum_mm"], t[1]["cost"], t[0]),
            "coverage": lambda t: (-t[1]["covered_weight"], t[1]["unknown_count"], t[1]["weighted_sum_mm"], mx(t[1]),
                                   t[1]["cost"], t[0])}
    obj = {k: sorted(plans, key=f)[0] for k, f in keyf.items()}
    complete = [(ids, m["cost"], m["weighted_sum_mm"]) for ids, m in plans if m["unknown_count"] == 0]
    nd = [x for x in complete if not any(y[1] <= x[1] and y[2] <= x[2] and (y[1] < x[1] or y[2] < x[2]) for y in complete)]
    rep = {}
    for ids, c, w in nd:
        if (c, w) not in rep or ids < rep[(c, w)]:
            rep[(c, w)] = ids
    pareto = [{"selected_ids": rep[k], "cost": k[0], "weighted_sum_mm": k[1]} for k in sorted(rep)]
    return {"status": "optimal", "reasons": [], "feasible_count": len(plans),
            "objectives": {k: {"selected_ids": v[0], "metrics": v[1]} for k, v in obj.items()}, "pareto": pareto}
