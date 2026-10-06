"""K06 round 9 stage 2: independent brute-force gold for city-resilience-v1 small problems.
No code shared with resilience_oracle.py / plan_oracle.py: per-plan metrics come from r8/gold_bruteforce._plan_metrics
(itself independent of the oracle); worst vector, keys, nominal and robust are recomputed here with bitmasks over ALL
candidates and a full sort. Input assumed valid. Suitable for <= 8 candidates."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "r8"))
import gold_bruteforce as G


def solve(records, env):
    sc = env["plan"]
    cases = [{"id": "base", "disabled_source_ids": []}] + env["cases"]
    srcs = [r for r in records if r["group"] == sc["category"]]
    cands, n = sc["candidates"], len(sc["candidates"])
    req, exc = set(sc["required_ids"]), set(sc["excluded_ids"])
    rc = sum(c["cost"] for c in cands if c["id"] in req)
    if len(req) > sc["max_selected"] or rc > sc["budget"]:
        return {"status": "infeasible"}
    big = float("inf")
    plans = []
    for mask in range(1 << n):
        ch = [cands[i] for i in range(n) if mask >> i & 1]
        ids = sorted(c["id"] for c in ch)
        if not req <= set(ids) or exc & set(ids) or len(ch) > sc["max_selected"] or sum(c["cost"] for c in ch) > sc["budget"]:
            continue
        Ls = {}
        for cs in cases:
            off = set(cs["disabled_source_ids"])
            m = G._plan_metrics([s for s in srcs if s["id"] not in off], sc["control_points"], ch, sc["coverage_radius_m"])
            Ls[cs["id"]] = (m["unknown_count"], m["weighted_sum_mm"], big if m["max_mm"] is None else m["max_mm"])
        W = max(Ls.values())
        plans.append({"ids": ids, "cost": sum(c["cost"] for c in ch), "L": Ls, "W": W,
                      "worst": sorted(k for k, v in Ls.items() if v == W)})
    nominal = sorted(plans, key=lambda p: (p["L"]["base"][0], p["L"]["base"][1], p["L"]["base"][2], p["cost"], p["ids"]))[0]
    robust = sorted(plans, key=lambda p: (p["W"], p["L"]["base"], p["cost"], p["ids"]))[0]
    ext = lambda v: [v[0], v[1], None if v[2] == big else v[2]]
    tw = sum(p["weight"] for p in sc["control_points"])
    meanb = lambda p: None if p["L"]["base"][0] else p["L"]["base"][1] / tw
    price = None if meanb(nominal) is None or meanb(robust) is None else (meanb(robust) - meanb(nominal)) / 1000
    view = lambda p: {"selected_ids": p["ids"], "worst_vector": ext(p["W"]), "worst_case_ids": p["worst"],
                      "loss_by_case": {k: ext(v) for k, v in p["L"].items()}}
    return {"status": "optimal", "feasible_count": len(plans), "nominal": view(nominal), "robust": view(robust),
            "price_of_robustness_m": price}
