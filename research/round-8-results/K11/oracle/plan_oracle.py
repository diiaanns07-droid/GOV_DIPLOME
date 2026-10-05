"""K11 round 8: independent Python oracle for city-plan-v2 optimisation (CORE_SPEC), stdlib only.

Written from the spec, not translated from src/plan_core.js: subsets come from itertools.combinations,
Pareto dominance is checked pairwise, ties use Python's native str/list ordering.

    python plan_oracle.py <fixture.json> [...]          -> prints JSON results
    python plan_oracle.py --write-expected <dir>        -> fixtures/<dir>/*.json -> expected_oracle.json
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

R = 6371008.8


def haversine(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R * math.asin(math.sqrt(a))


def mm(d):
    return math.floor(d * 1000 + 0.5)  # CORE_SPEC: Python floor(x+0.5), values are non-negative


def solve(context, sc, budget=None):
    budget = sc["budget"] if budget is None else budget
    sources = [r for r in context["records"] if r["group"] == sc["category"]]
    points = sc["control_points"]
    cands = {c["id"]: c for c in sc["candidates"]}
    total_w = sum(p["weight"] for p in points)
    radius = sc["coverage_radius_m"] * 1000
    base = {}
    for p in points:
        opts = [(mm(haversine(p["lon"], p["lat"], s["lon"], s["lat"])), s["id"]) for s in sources]
        base[p["id"]] = min(opts)[0] if opts else None
    cdist = {(cid, p["id"]): mm(haversine(p["lon"], p["lat"], c["lon"], c["lat"]))
             for cid, c in cands.items() for p in points}

    def metrics(ids):
        unknown, ws, mx, cov = 0, 0, -1, 0
        for p in points:
            vals = [v for v in [base[p["id"]]] + [cdist[(c, p["id"])] for c in ids] if v is not None]
            if not vals:
                unknown += 1
                continue
            a = min(vals)
            ws += p["weight"] * a
            mx = max(mx, a)
            if a <= radius:
                cov += p["weight"]
        return {"unknown": unknown, "ws": ws, "max": math.inf if unknown else mx, "covered": cov,
                "cost": sum(cands[c]["cost"] for c in ids)}

    req, exc = set(sc["required_ids"]), set(sc["excluded_ids"])
    feasible = []
    for k in range(0, sc["max_selected"] + 1):
        for combo in itertools.combinations(sorted(cands), k):
            s = set(combo)
            if not req <= s or s & exc:
                continue
            x = metrics(combo)
            if x["cost"] > budget:
                continue
            feasible.append((sorted(combo), x))
    if not feasible:
        reasons = []
        if len(req) > sc["max_selected"]:
            reasons.append("required_exceeds_max_selected")
        if sum(cands[c]["cost"] for c in req) > budget:
            reasons.append("required_exceeds_budget")
        return {"status": "infeasible", "reasons": reasons or ["no_feasible_set"], "feasible_count": 0, "budget": budget}

    keys = {
        "mean": lambda ids, x: (x["unknown"], x["ws"], x["max"], x["cost"], ids),
        "minimax": lambda ids, x: (x["unknown"], x["max"], x["ws"], x["cost"], ids),
        "coverage": lambda ids, x: (-x["covered"], x["unknown"], x["ws"], x["max"], x["cost"], ids),
    }

    def public(ids, x):
        known = x["unknown"] == 0
        return {"selected_ids": ids, "cost": x["cost"], "unknown_count": x["unknown"], "weighted_sum_mm": x["ws"],
                "max_mm": x["max"] if known else None, "covered_weight": x["covered"],
                "weighted_mean_mm": x["ws"] / total_w if known else None}

    objectives = {k: public(*min(feasible, key=lambda t, f=f: f(t[0], t[1]))) for k, f in keys.items()}

    full = [(ids, x["cost"], x["ws"]) for ids, x in feasible if x["unknown"] == 0]
    rep = {}
    for ids, c, w in full:
        if (c, w) not in rep or ids < rep[(c, w)]:
            rep[(c, w)] = ids
    pts = [(c, w, ids) for (c, w), ids in rep.items()]
    pareto = [p for p in pts if not any(q[0] <= p[0] and q[1] <= p[1] and (q[0] < p[0] or q[1] < p[1]) for q in pts)]
    pareto.sort(key=lambda p: (p[0], p[1]))
    return {"status": "optimal", "feasible_count": len(feasible), "budget": budget, "objectives": objectives,
            "pareto": [{"selected_ids": ids, "cost": c, "weighted_sum_mm": w} for c, w, ids in pareto]}


def main(argv):
    if argv[:1] == ["--write-expected"]:
        d = Path(argv[1])
        out = {}
        for f in sorted(d.glob("*.json")):
            if f.name == "expected_oracle.json" or f.name == "MANIFEST.json":
                continue
            fx = json.loads(f.read_bytes().decode("utf-8"))
            sc = fx["scenario"]
            budgets = sorted({0, sc["budget"] // 2, sc["budget"]})
            out[f.name] = {"main": solve(fx["context"], sc),
                           "sensitivity": {str(b): solve(fx["context"], sc, b) for b in budgets}}
        (d / "expected_oracle.json").write_bytes(
            (json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False, default=str) + "\n").encode("utf-8"))
        print(f"expected results for {len(out)} fixtures -> {d / 'expected_oracle.json'}")
        return 0
    for p in argv:
        fx = json.loads(Path(p).read_bytes().decode("utf-8"))
        print(json.dumps(solve(fx["context"], fx["scenario"]), ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
