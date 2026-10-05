#!/usr/bin/env python3
"""K07 round 8: independent Python oracle for city-plan-v2 (research/round-8/CORE_SPEC.txt).

Written from CORE_SPEC, not translated from web/plan_calc.js: subsets come from itertools.combinations (the JS walks
bitmasks), objectives are Python tuples, Pareto is a brute-force O(n^2) dominance check. Reads the records from the
viewer's data.js and a cases file written by tests/plan_calc.test.cjs; writes the oracle answers as JSON.
    python3 oracle_plan.py --data <web/data.js> --cases cases.json --out oracle.json
Only the standard library is used. Snapshot/field validation is not re-done here (that is the validator's job).
"""
import argparse, itertools, json, math

R = 6371008.8


def load_data(path):
    text = open(path, encoding="utf-8").read()
    start, end = text.index("{"), text.rstrip().rstrip(";").rindex("}") + 1
    return json.loads(text[start:end])


def dist_mm(lon1, lat1, lon2, lat2):
    f1, f2 = math.radians(lat1), math.radians(lat2)
    h = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    h = min(1.0, max(0.0, h))
    d = 2 * R * math.asin(math.sqrt(h))
    return math.floor(d * 1000 + 0.5)


def plan_metrics(points, base, cand_d, chosen, radius_mm):
    unknown = wsum = covered = 0
    worst = 0
    total_w = sum(p["weight"] for p in points)
    for i, p in enumerate(points):
        options = ([base[i]] if base[i] is not None else []) + [cand_d[c][i] for c in chosen]
        if not options:
            unknown += 1
            continue
        a = min(options)
        wsum += p["weight"] * a
        worst = max(worst, a)
        if a <= radius_mm:
            covered += p["weight"]
    return {"unknown_count": unknown, "weighted_sum_mm": wsum, "max_mm": None if unknown else worst,
            "covered_weight": covered, "total_weight": total_w}


def solve(case, data):
    sc = case["scenario"]
    places = [p for p in data["cities"][sc["city_id"]]["places"] if p["group"] == sc["category"]]
    pts, cands = sc["control_points"], {c["id"]: c for c in sc["candidates"]}
    base = []
    for p in pts:
        ds = [dist_mm(p["lon"], p["lat"], s["lon"], s["lat"]) for s in places]
        base.append(min(ds) if ds else None)
    cand_d = {cid: [dist_mm(p["lon"], p["lat"], c["lon"], c["lat"]) for p in pts] for cid, c in cands.items()}
    radius_mm = sc["coverage_radius_m"] * 1000
    req, exc = set(sc["required_ids"]), set(sc["excluded_ids"])
    free = sorted(set(cands) - req - exc)
    B = sc["budget"]
    budgets = sorted({0, B // 2, B})
    plans = []
    for k in range(0, sc["max_selected"] - len(req) + 1):
        for extra in itertools.combinations(free, k):
            chosen = sorted(req | set(extra))
            cost = sum(cands[c]["cost"] for c in chosen)
            if cost > B or len(chosen) > sc["max_selected"]:
                continue
            m = plan_metrics(pts, base, cand_d, chosen, radius_mm)
            m["cost"] = cost
            plans.append((chosen, m))
    inf = float("inf")
    mx = lambda m: inf if m["max_mm"] is None else m["max_mm"]
    keys = {
        "mean": lambda ids, m: (m["unknown_count"], m["weighted_sum_mm"], mx(m), m["cost"], ids),
        "minimax": lambda ids, m: (m["unknown_count"], mx(m), m["weighted_sum_mm"], m["cost"], ids),
        "coverage": lambda ids, m: (-m["covered_weight"], m["unknown_count"], m["weighted_sum_mm"], mx(m), m["cost"], ids),
    }

    def winners(pl):
        return {k: (None if not pl else min(pl, key=lambda x: f(x[0], x[1]))) for k, f in keys.items()}

    def show(w):
        return None if w is None else {"selected_ids": w[0], **{k: w[1][k] for k in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost")}}

    known = [(ids, m) for ids, m in plans if m["unknown_count"] == 0]
    front = []
    for ids, m in known:
        dominated = any(o["cost"] <= m["cost"] and o["weighted_sum_mm"] <= m["weighted_sum_mm"]
                        and (o["cost"] < m["cost"] or o["weighted_sum_mm"] < m["weighted_sum_mm"]) for _, o in known)
        if not dominated:
            front.append((ids, m))
    collapsed = {}
    for ids, m in front:
        key = (m["cost"], m["weighted_sum_mm"])
        if key not in collapsed or ids < collapsed[key]:
            collapsed[key] = ids
    pareto = [{"selected_ids": collapsed[k], "cost": k[0], "weighted_sum_mm": k[1]} for k in sorted(collapsed)]
    sens = []
    for b in budgets:
        pb = [x for x in plans if x[1]["cost"] <= b]
        sens.append({"budget": b, "feasible_count": len(pb), "objectives": {k: show(v) for k, v in winners(pb).items()}})
    manual = sorted(sc["selected_ids"])
    mm = plan_metrics(pts, base, cand_d, manual, radius_mm)
    mm["cost"] = sum(cands[c]["cost"] for c in manual)
    return {"name": case["name"], "status": "optimal" if plans else "infeasible", "feasible_count": len(plans),
            "objectives": {k: show(v) for k, v in winners(plans).items()}, "pareto": pareto,
            "pareto_excluded_unknown": len(plans) - len(known), "sensitivity": sens,
            "manual": {"selected_ids": manual, **mm, "before_mm": base}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = load_data(a.data)
    cases = json.load(open(a.cases, encoding="utf-8"))
    out = [solve(c, data) for c in cases]
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"oracle: {len(out)} cases")


if __name__ == "__main__":
    main()
