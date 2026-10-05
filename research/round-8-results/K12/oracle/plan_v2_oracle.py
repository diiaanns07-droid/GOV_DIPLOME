"""K12 round 8: INDEPENDENT Python oracle for city-plan-v2 computation (CORE_SPEC.txt @ c3f6c00).

Not a translation of the JS reference: different enumeration (itertools.combinations by subset size),
different Pareto (pairwise dominance), Python tuple ordering for the lexicographic keys. Computation
only — input scenarios are assumed already validated (validation is covered by the fixtures).

    python plan_v2_oracle.py --app-root <prototypes/city-evidence copy> --problems problems.json [--out out.json]

problems.json: {"problems": [{"name": ..., "scenario": {...clean city-plan-v2...}, "budgets": [optional list]}]}
"""
import argparse
import itertools
import json
import math
import sys
from pathlib import Path

R_EARTH = 6371008.8
METRIC_VERSION = "haversine-mm-v1"
INF = float("inf")


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def to_mm(d_m):
    return math.floor(d_m * 1000 + 0.5)   # spec: floor(x+0.5); all values are non-negative


def load_sources(app_root):
    text = (Path(app_root) / "web" / "data.js").read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"):text.rstrip().rindex(";")])
    return {city: c["places"] for city, c in data["cities"].items()}


def solve(scenario, places):
    pts = scenario["control_points"]
    cands = {c["id"]: c for c in scenario["candidates"]}
    src = [p for p in places if p["group"] == scenario["category"]]
    radius_mm = scenario["coverage_radius_m"] * 1000
    total_w = sum(p["weight"] for p in pts)

    base = {}
    cand_d = {}
    for p in pts:
        ds = [(to_mm(haversine_m(p["lon"], p["lat"], s["lon"], s["lat"])), str(s["id"])) for s in src]
        base[p["id"]] = min(ds) if ds else None
        for cid, c in cands.items():
            cand_d[(p["id"], cid)] = to_mm(haversine_m(p["lon"], p["lat"], c["lon"], c["lat"]))

    def metrics(ids):
        unknown = wsum = covered = 0
        mx = None
        for p in pts:
            options = [base[p["id"]][0]] if base[p["id"]] else []
            options += [cand_d[(p["id"], cid)] for cid in ids]
            if not options:
                unknown += 1
                continue
            a = min(options)
            wsum += p["weight"] * a
            mx = a if mx is None else max(mx, a)
            if a <= radius_mm:
                covered += p["weight"]
        cost = sum(cands[cid]["cost"] for cid in ids)
        return {"unknown_count": unknown, "weighted_sum_mm": wsum, "max_mm": mx if unknown == 0 else None,
                "covered_weight": covered, "total_weight": total_w, "cost": cost}

    def run(budget):
        req = sorted(scenario["required_ids"])
        free = sorted(set(cands) - set(req) - set(scenario["excluded_ids"]))
        plans = []
        room = scenario["max_selected"] - len(req)
        for k in range(0, max(room, -1) + 1):
            for combo in itertools.combinations(free, k):
                ids = tuple(sorted(req + list(combo)))
                m = metrics(ids)
                if m["cost"] <= budget:
                    plans.append((ids, m))
        mx = lambda m: INF if m["max_mm"] is None else m["max_mm"]
        keys = {
            "mean": lambda t: (t[1]["unknown_count"], t[1]["weighted_sum_mm"], mx(t[1]), t[1]["cost"], t[0]),
            "minimax": lambda t: (t[1]["unknown_count"], mx(t[1]), t[1]["weighted_sum_mm"], t[1]["cost"], t[0]),
            "coverage": lambda t: (-t[1]["covered_weight"], t[1]["unknown_count"], t[1]["weighted_sum_mm"], mx(t[1]), t[1]["cost"], t[0]),
        }
        objectives = {name: ({"selected_ids": list(min(plans, key=key)[0]), "metrics": min(plans, key=key)[1]} if plans else None)
                      for name, key in keys.items()}
        full = [(m["cost"], m["weighted_sum_mm"], ids) for ids, m in plans if m["unknown_count"] == 0]
        front = {}
        for c, w, ids in full:
            dominated = any((c2 <= c and w2 <= w) and (c2 < c or w2 < w) for c2, w2, _ in full)
            if not dominated:
                key = (c, w)
                if key not in front or ids < front[key]:
                    front[key] = ids
        pareto = [{"cost": c, "weighted_sum_mm": w, "selected_ids": list(front[(c, w)])} for c, w in sorted(front)]
        return {"status": "optimal" if plans else "infeasible", "objectives": objectives, "pareto": pareto,
                "feasible_count": len(plans), "evaluated": 2 ** len(free), "budget": budget}

    out = run(scenario["budget"])
    out["metric_version"] = METRIC_VERSION
    out["selected_evaluation"] = metrics(tuple(sorted(scenario["selected_ids"])))
    out["selected_after_mm"] = {}
    for p in pts:
        options = ([base[p["id"]][0]] if base[p["id"]] else []) + [cand_d[(p["id"], cid)] for cid in scenario["selected_ids"]]
        out["selected_after_mm"][p["id"]] = min(options) if options else None
    out["sensitivity"] = [{"budget": b, **{k: v for k, v in run(b).items() if k in ("status", "feasible_count")},
                           "mean_ids": (run(b)["objectives"]["mean"] or {}).get("selected_ids")}
                          for b in sorted({0, scenario["budget"] // 2, scenario["budget"]})]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--problems", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    sources = load_sources(a.app_root)
    probs = json.loads(Path(a.problems).read_text(encoding="utf-8"))["problems"]
    import hashlib
    data_sha = hashlib.sha256((Path(a.app_root) / "web" / "data.js").read_bytes()).hexdigest()
    res = {"oracle": "k12r8-python-oracle", "metric_version": METRIC_VERSION, "data_js_sha256": data_sha,
           "results": [{"name": p["name"], **solve(p["scenario"], sources[p["scenario"]["city_id"]])} for p in probs]}
    text = json.dumps(res, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
