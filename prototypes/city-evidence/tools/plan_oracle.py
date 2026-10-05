"""Independent Python oracle for city-plan-v2 (research/round-8/CORE_SPEC.txt), stdlib only.

Written from the spec, not translated from web/plan.js: subsets are enumerated with itertools.combinations,
objective keys are Python tuples, the Pareto front is a brute-force O(n^2) dominance check.

  distance  : haversine, R = 6371008.8 m, input [lon, lat], intermediate clamped to [0, 1]
  metric    : haversine-mm-v1 = floor(d_m * 1000 + 0.5), rounded once
  nearest   : by (mm, kind: source before hypothetical, id)
  objectives: mean     (unknown, wsum, max, cost, ids)
              minimax  (unknown, max, wsum, cost, ids)
              coverage (-covered_weight, unknown, wsum, max, cost, ids)   max = inf when unknown > 0
  pareto    : complete plans only (unknown == 0), minimise (cost, wsum); equal pairs -> smallest ids

Usage:
  python3 tools/plan_oracle.py           -> tests/expected_plans.json (synthetic hand fixtures + both city slices)
  python3 tools/plan_oracle.py --check   -> exit 1 if the file differs from a fresh run
Fixtures are SYNTHETIC: candidate sites, costs and weights are invented test inputs, not city data or prices.
"""
import itertools
import json
import math
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / "tests" / "expected_plans.json"
R = 6371008.8
INF = float("inf")


def hav_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    h = max(0.0, min(1.0, h))
    return 2 * R * math.asin(math.sqrt(h))


def mm(a, b):
    return math.floor(hav_m(a, b) * 1000 + 0.5)


def solve(places, sc, budgets=None):
    pts = {p["id"]: p for p in sc["control_points"]}
    cands = {c["id"]: c for c in sc["candidates"]}
    src = [p for p in places if p["group"] == sc["category"]]
    base = {}
    for pid, p in pts.items():
        opts = [(mm((p["lon"], p["lat"]), (s["lon"], s["lat"])), 0, s["id"]) for s in src]
        base[pid] = min(opts) if opts else None
    hyp = {(cid, pid): mm((pts[pid]["lon"], pts[pid]["lat"]), (c["lon"], c["lat"])) for cid, c in cands.items() for pid in pts}
    radius = sc["coverage_radius_m"] * 1000
    total_w = sum(p["weight"] for p in pts.values())

    def evaluate(ids):
        rows, unknown, wsum, mx, cov = {}, 0, 0, 0, 0
        for pid, p in pts.items():
            opts = ([base[pid]] if base[pid] else []) + [(hyp[(cid, pid)], 1, cid) for cid in ids]
            best = min(opts) if opts else None
            b = base[pid]
            rows[pid] = {"before_mm": b[0] if b else None, "nearest_before": {"kind": "source", "id": b[2]} if b else None,
                         "after_mm": best[0] if best else None,
                         "nearest_after": {"kind": "source" if best[1] == 0 else "hypothetical", "id": best[2]} if best else None,
                         "delta_mm": b[0] - best[0] if b and best else None}
            if best is None:
                unknown += 1
            else:
                wsum += p["weight"] * best[0]
                mx = max(mx, best[0])
                if best[0] <= radius:
                    cov += p["weight"]
        cost = sum(cands[c]["cost"] for c in ids)
        return {"ids": sorted(ids), "rows": rows, "unknown_count": unknown, "weighted_sum_mm": wsum,
                "max_mm": mx if unknown == 0 else None, "covered_weight": cov, "total_weight": total_w, "cost": cost}

    def optimize(budget):
        req = sorted(sc["required_ids"])
        free = sorted(set(cands) - set(req) - set(sc["excluded_ids"]))
        out = {"budget": budget, "evaluated": 2 ** len(free)}
        req_cost = sum(cands[c]["cost"] for c in req)
        reasons = []
        if len(req) > sc["max_selected"]:
            reasons.append("required_exceeds_max_selected")
        if req_cost > budget:
            reasons.append("required_cost_exceeds_budget")
        if reasons:
            return {**out, "status": "infeasible", "reasons": reasons, "feasible_count": 0, "evaluated": 0,
                    "objectives": None, "pareto": []}
        plans = []
        for k in range(0, sc["max_selected"] - len(req) + 1):
            for combo in itertools.combinations(free, k):
                ids = req + list(combo)
                if sum(cands[c]["cost"] for c in ids) <= budget:
                    plans.append(evaluate(ids))
        keyed = lambda e: (e["max_mm"] if e["max_mm"] is not None else INF)  # noqa: E731
        keys = {
            "mean": lambda e: (e["unknown_count"], e["weighted_sum_mm"], keyed(e), e["cost"], e["ids"]),
            "minimax": lambda e: (e["unknown_count"], keyed(e), e["weighted_sum_mm"], e["cost"], e["ids"]),
            "coverage": lambda e: (-e["covered_weight"], e["unknown_count"], e["weighted_sum_mm"], keyed(e), e["cost"], e["ids"]),
        }
        objectives = {}
        for name, key in keys.items():
            w = min(plans, key=key)
            objectives[name] = {k: w[k] for k in ("ids", "cost", "unknown_count", "weighted_sum_mm", "max_mm", "covered_weight")}
        complete = [e for e in plans if e["unknown_count"] == 0]
        front = []
        for e in complete:
            dominated = any(o["cost"] <= e["cost"] and o["weighted_sum_mm"] <= e["weighted_sum_mm"]
                            and (o["cost"] < e["cost"] or o["weighted_sum_mm"] < e["weighted_sum_mm"]) for o in complete)
            if not dominated:
                front.append(e)
        reps = {}
        for e in front:
            k = (e["cost"], e["weighted_sum_mm"])
            if k not in reps or e["ids"] < reps[k]["ids"]:
                reps[k] = e
        pareto = [{"ids": e["ids"], "cost": e["cost"], "weighted_sum_mm": e["weighted_sum_mm"]} for e in sorted(reps.values(), key=lambda e: (e["cost"], e["weighted_sum_mm"]))]
        return {**out, "status": "optimal", "reasons": [], "feasible_count": len(plans), "objectives": objectives, "pareto": pareto,
                "pareto_excluded_unknown": len(plans) - len(complete)}

    manual = evaluate(sorted(sc["selected_ids"]))
    b = sc["budget"]
    sens = sorted(set([0, b // 2, b]))
    return {"manual": manual, "optimize": optimize(b),
            "sensitivity": [{"budget": x, **{k: v for k, v in optimize(x).items() if k in ("status", "objectives", "feasible_count", "reasons")}} for x in sens]}


# ---------------- fixtures (synthetic) ----------------
def P(i, lon, lat, w=1):
    return {"id": f"P{i:02d}", "lon": lon, "lat": lat, "weight": w}


def C(cid, lon, lat, cost, cat="school"):
    return {"id": cid, "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical", "cost": cost}


def sc_(points, cands, budget, max_sel, radius=500, req=(), exc=(), sel=(), cat="school"):
    return {"category": cat, "control_points": points, "candidates": cands, "budget": budget, "max_selected": max_sel,
            "coverage_radius_m": radius, "required_ids": list(req), "excluded_ids": list(exc), "selected_ids": list(sel)}


EQ_BBOX = [-0.1, -0.1, 0.1, 0.1]
EQ_SRC = [{"id": "src-a", "group": "school", "lon": 0.01, "lat": 0.0}, {"id": "src-b", "group": "school", "lon": -0.01, "lat": 0.0},
          {"id": "clinic-1", "group": "outpatient_clinic", "lon": 0.0, "lat": 0.05}]


def hand_fixtures():
    pts3 = [P(1, 0, 0, 1), P(2, 0.02, 0.02, 2), P(3, -0.03, 0.0, 3)]
    f = []
    f.append(("ties_equal_costs", EQ_SRC, sc_([P(1, 0, 0)], [C("C2", 0, -0.005, 10), C("C1", 0, 0.005, 10)], 10, 1, sel=["C2"])))
    f.append(("source_hyp_tie", EQ_SRC, sc_([P(1, 0, 0)], [C("C1", 0, 0.01, 5)], 10, 1, sel=["C1"])))
    f.append(("required_cost_over_budget", EQ_SRC, sc_(pts3, [C("C1", 0.02, 0.02, 10), C("C2", -0.03, 0, 4)], 5, 2, req=["C1"], sel=["C1"])))
    f.append(("required_over_max_selected", EQ_SRC, sc_(pts3, [C("C1", 0.02, 0.02, 1), C("C2", -0.03, 0, 1)], 10, 1, req=["C1", "C2"])))
    f.append(("zero_budget", EQ_SRC, sc_(pts3, [C("C1", 0.02, 0.02, 1), C("C2", -0.03, 0, 1)], 0, 2)))
    f.append(("no_candidates", EQ_SRC, sc_(pts3, [], 100, 3)))
    oc = "outpatient_clinic"  # EQ_SRC has one clinic far away -> baseline known; use a category with no records below
    f.append(("no_baseline", [p for p in EQ_SRC if p["group"] != oc],
              sc_(pts3, [C("C1", 0.02, 0.02, 3, oc), C("C2", -0.03, 0, 3, oc), C("C3", 0, 0, 2, oc)], 6, 2, cat=oc, sel=["C3"])))
    f.append(("no_baseline_no_source_at_all", [], sc_(pts3, [C("C1", 0.02, 0.02, 3), C("C2", -0.03, 0, 3)], 3, 2, sel=[])))
    f.append(("dominated_plans", EQ_SRC, sc_(pts3, [C("Cheap", 0.02, 0.019, 2), C("Dear", 0.02, 0.015, 9), C("Mid", -0.03, 0.001, 5)], 20, 3, sel=["Dear"])))
    f.append(("excluded_and_required", EQ_SRC, sc_(pts3, [C("A", 0.02, 0.02, 3), C("B", -0.03, 0, 3), C("D", 0, 0.001, 3)], 6, 2, req=["D"], exc=["A"], sel=["A", "B"])))
    f.append(("coverage_vs_mean", EQ_SRC, sc_([P(1, 0.05, 0.05, 1), P(2, 0.051, 0.05, 1), P(3, -0.06, -0.06, 5)],
                                          [C("Near12", 0.0505, 0.05, 5), C("Far3", -0.058, -0.058, 5)], 5, 1, radius=300)))
    return f


def slice_fixture(data, city, cat, n_c, n_p, budget, max_sel, radius):
    """Deterministic SYNTHETIC candidates / points on a grid inside the real bbox (records of the slice untouched)."""
    w, s, e, n = data["cities"][city]["bbox"]
    g = lambda fx, fy: (round(w + (e - w) * fx, 6), round(s + (n - s) * fy, 6))  # noqa: E731
    pts = []
    for k in range(n_p):
        lon, lat = g(0.1 + 0.8 * ((k % 5) / 4), 0.1 + 0.8 * ((k // 5) / 4 if n_p > 5 else 0.5))
        pts.append(P(k + 1, lon, lat, 1 + (k * 7) % 10))
    cands = []
    for k in range(n_c):
        lon, lat = g(0.15 + 0.7 * ((k % 4) / 3), 0.15 + 0.7 * ((k // 4) / 3))
        cands.append(C(f"K{k + 1:02d}", lon, lat, 100 + (k * 37) % 400, cat))
    return sc_(pts, cands, budget, max_sel, radius, sel=[cands[0]["id"]] if cands else [], cat=cat)


def load_data():
    text = (APP / "web" / "data.js").read_text(encoding="utf-8")
    body = text[text.index("window.CITY_EVIDENCE =") + len("window.CITY_EVIDENCE ="):].strip()
    return json.loads(body[:-1] if body.endswith(";") else body)


def build():
    data = load_data()
    cases = []
    for name, places, sc in hand_fixtures():
        cases.append({"name": name, "kind": "synthetic_hand", "bbox": EQ_BBOX, "places": places, "scenario": sc, "expected": solve(places, sc)})
    for city in sorted(data["cities"]):
        places = [{"id": p["id"], "group": p["group"], "lon": p["lon"], "lat": p["lat"]} for p in data["cities"][city]["places"]]
        for cat, args in (("school", (16, 25, 900, 5, 400)), ("outpatient_clinic", (8, 10, 500, 3, 300))):
            sc = slice_fixture(data, city, cat, *args)
            cases.append({"name": f"{city}_{cat}_{args[0]}x{args[1]}", "kind": "synthetic_on_real_slice", "city": city, "scenario": sc,
                          "expected": solve(places, sc)})
    return {"generator": "tools/plan_oracle.py", "metric_version": "haversine-mm-v1",
            "note": "SYNTHETIC fixtures: candidate sites, costs (conditional units) and weights are invented; source records are the real slices unchanged",
            "cases": cases}


def main():
    text = json.dumps(build(), ensure_ascii=False, indent=1) + "\n"
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(("OK " if ok else "STALE ") + str(OUT.relative_to(APP)))
        return 0 if ok else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {OUT.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
