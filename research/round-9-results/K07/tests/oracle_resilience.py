#!/usr/bin/env python3
"""K07 round 9: independent Python oracle for city-resilience-v1 (research/round-9/CORE_SPEC.txt).

Written from CORE_SPEC only (not translated from web/resilience_k07.js nor from BUILD plan.js): source records come
straight from the viewer's data.js, every case filters them itself, subsets come from itertools.combinations,
objectives are Python tuples with math.inf for an unknown max. Standard library only.
    python3 oracle_resilience.py --data <web/data.js> --cases cases.json --out oracle.json
cases.json: [{"name": ..., "envelope": {"schema_version": "city-resilience-v1", "plan": {...}, "cases": [...]}}]
Validation is not repeated here (the envelopes in the file are valid by construction).
"""
import argparse, itertools, json, math

R = 6371008.8
INF = math.inf


def load(path):
    t = open(path, encoding="utf-8").read()
    return json.loads(t[t.index("{"):t.rstrip().rstrip(";").rindex("}") + 1])


def mm(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return math.floor(2 * R * math.asin(math.sqrt(min(1.0, max(0.0, h)))) * 1000 + 0.5)


def metrics(after, weights, radius_mm):
    unknown = sum(1 for a in after if a is None)
    known = [(a, w) for a, w in zip(after, weights) if a is not None]
    wsum = sum(a * w for a, w in known)
    total = sum(weights)
    return {"unknown_count": unknown, "weighted_sum_mm": wsum,
            "weighted_mean_mm": wsum / total if unknown == 0 and total else None,
            "max_mm": max(a for a, _ in known) if unknown == 0 and known else None,
            "covered_weight": sum(w for a, w in known if a <= radius_mm)}


def loss(m):
    return (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"])


def solve(item, data):
    env = item["envelope"]
    plan = env["plan"]
    places = [p for p in data["cities"][plan["city_id"]]["places"] if p["group"] == plan["category"]]
    cases = [{"id": "base", "off": set()}] + [{"id": c["id"], "off": set(c["disabled_source_ids"])} for c in env["cases"]]
    pts, weights = plan["control_points"], [p["weight"] for p in plan["control_points"]]
    cands = {c["id"]: c for c in plan["candidates"]}
    radius_mm = plan["coverage_radius_m"] * 1000
    baseline = []
    for case in cases:
        src = [s for s in places if s["id"] not in case["off"]]
        baseline.append([min([mm(p["lon"], p["lat"], s["lon"], s["lat"]) for s in src], default=None) for p in pts])
    cdist = {cid: [mm(p["lon"], p["lat"], c["lon"], c["lat"]) for p in pts] for cid, c in cands.items()}

    def per_case(chosen):
        out = []
        for case, base in zip(cases, baseline):
            after = []
            for j, b in enumerate(base):
                opts = ([b] if b is not None else []) + [cdist[c][j] for c in chosen]
                after.append(min(opts) if opts else None)
            m = metrics(after, weights, radius_mm)
            out.append({"case_id": case["id"], "metrics": m, "loss": loss(m)})
        W = max(x["loss"] for x in out)
        return out, W, sorted(x["case_id"] for x in out if x["loss"] == W)

    req, exc = set(plan["required_ids"]), set(plan["excluded_ids"])
    free = sorted(set(cands) - req - exc)
    plans = []
    for k in range(0, plan["max_selected"] - len(req) + 1):
        for extra in itertools.combinations(free, k):
            chosen = sorted(req | set(extra))
            cost = sum(cands[c]["cost"] for c in chosen)
            if cost > plan["budget"]:
                continue
            pcs, W, worst = per_case(chosen)
            plans.append({"ids": chosen, "cost": cost, "per": pcs, "W": W, "worst": worst, "Lb": pcs[0]["loss"]})

    def show(x):
        return None if x is None else {"selected_ids": x["ids"], "cost": x["cost"], "worst_case_ids": x["worst"],
                                       "worst_vector": [None if v == INF else v for v in x["W"]],
                                       "per_case": [{"case_id": c["case_id"], **{k: c["metrics"][k] for k in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight")}} for c in x["per"]]}

    if not plans:
        return {"name": item["name"], "status": "infeasible", "feasible_count": 0, "nominal": None, "robust": None, "price_of_robustness_m": None}
    nominal = min(plans, key=lambda x: (x["Lb"], x["cost"], x["ids"]))
    robust = min(plans, key=lambda x: (x["W"], x["Lb"], x["cost"], x["ids"]))
    mn, mr = nominal["per"][0]["metrics"]["weighted_mean_mm"], robust["per"][0]["metrics"]["weighted_mean_mm"]
    manual = sorted(plan["selected_ids"])
    mp, mW, mworst = per_case(manual)
    return {"name": item["name"], "status": "optimal", "feasible_count": len(plans), "nominal": show(nominal), "robust": show(robust),
            "price_of_robustness_m": (mr - mn) / 1000 if mn is not None and mr is not None else None,
            "manual": show({"ids": manual, "cost": sum(cands[c]["cost"] for c in manual), "per": mp, "W": mW, "worst": mworst})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = load(a.data)
    out = [solve(c, data) for c in json.load(open(a.cases, encoding="utf-8"))]
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"oracle: {len(out)} envelopes")


if __name__ == "__main__":
    main()
