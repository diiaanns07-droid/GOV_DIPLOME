"""Independent Python oracle for city-resilience-v1 (research/round-9/CORE_SPEC.txt), stdlib only.

Written from the spec; shares no code with web/plan.js, web/resilience.js or tools/plan_oracle.py:
  - distance  : haversine R = 6371008.8 m, [lon, lat], clamp to [0, 1]; metric haversine-mm-v1 = floor(d*1000 + 0.5)
  - nearest   : min over (mm, kind 0=source / 1=hypothetical, id)
  - case loss : L = (unknown_count, weighted_sum_mm, max_mm or +inf when unknown)
  - worst     : W = max(L over base + user cases); worst ids = every case with L == W, sorted
  - nominal   : min (L_base, cost, sorted ids)        (= v2 "mean" objective on the base case)
  - robust    : min (W, L_base, cost, sorted ids)
  - price     : (robust base weighted mean - nominal base weighted mean) / 1000 m, None if a mean is unknown
Plans are enumerated with itertools.combinations over free candidates (required always in, excluded never).

Usage:
  python3 tools/resilience_oracle.py           -> tests/expected_resilience.json
  python3 tools/resilience_oracle.py --check   -> exit 1 if the file differs from a fresh run
Fixtures are SYNTHETIC inputs (points, weights, candidate sites, costs, case choices); on real slices the source
records are the saved Overture records, unchanged.
"""
import itertools
import json
import math
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
OUT = APP / "tests" / "expected_resilience.json"
R = 6371008.8
INF = float("inf")


def mm(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    h = min(1.0, max(0.0, h))
    return math.floor(2 * R * math.asin(math.sqrt(h)) * 1000 + 0.5)


def solve(records, plan, cases):
    cat = plan["category"]
    pts = plan["control_points"]
    cands = {c["id"]: c for c in plan["candidates"]}
    all_cases = [{"id": "base", "disabled_source_ids": []}] + cases
    srcs = {c["id"]: [r for r in records if r["group"] == cat and r["id"] not in set(c["disabled_source_ids"])] for c in all_cases}
    radius = plan["coverage_radius_m"] * 1000
    tw = sum(p["weight"] for p in pts)

    def loss(case_id, ids):
        unknown = wsum = mx = cov = 0
        for p in pts:
            opts = [(mm(p["lon"], p["lat"], s["lon"], s["lat"]), 0, s["id"]) for s in srcs[case_id]]
            opts += [(mm(p["lon"], p["lat"], cands[i]["lon"], cands[i]["lat"]), 1, i) for i in ids]
            if not opts:
                unknown += 1
                continue
            d = min(opts)[0]
            wsum += p["weight"] * d
            mx = max(mx, d)
            cov += p["weight"] if d <= radius else 0
        return (unknown, wsum, mx if unknown == 0 else INF), cov

    def describe(ids):
        per = {}
        for c in all_cases:
            (u, s, m), cov = loss(c["id"], ids)
            per[c["id"]] = {"unknown_count": u, "weighted_sum_mm": s, "max_mm": None if m == INF else m, "covered_weight": cov,
                            "weighted_mean_mm": (s / tw) if u == 0 else None}
        keys = {cid: (v["unknown_count"], v["weighted_sum_mm"], INF if v["max_mm"] is None else v["max_mm"]) for cid, v in per.items()}
        w = max(keys.values())
        return {"ids": sorted(ids), "cost": sum(cands[i]["cost"] for i in ids), "per_case": per,
                "worst": {"unknown_count": w[0], "weighted_sum_mm": w[1], "max_mm": None if w[2] == INF else w[2]},
                "worst_case_ids": sorted(cid for cid, k in keys.items() if k == w)}

    req = sorted(plan["required_ids"])
    free = sorted(set(cands) - set(req) - set(plan["excluded_ids"]))
    out = {"manual": describe(sorted(plan["selected_ids"]))}
    reasons = []
    if len(req) > plan["max_selected"]:
        reasons.append("required_exceeds_max_selected")
    if sum(cands[i]["cost"] for i in req) > plan["budget"]:
        reasons.append("required_cost_exceeds_budget")
    if reasons:
        out["optimize"] = {"status": "infeasible", "reasons": reasons, "feasible_count": 0}
        return out
    best_n = best_r = None
    count = 0
    for k in range(plan["max_selected"] - len(req) + 1):
        for combo in itertools.combinations(free, k):
            ids = req + list(combo)
            cost = sum(cands[i]["cost"] for i in ids)
            if cost > plan["budget"]:
                continue
            count += 1
            ls = {c["id"]: loss(c["id"], ids)[0] for c in all_cases}
            w = max(ls.values())
            kn = (ls["base"], cost, sorted(ids))
            kr = (w, ls["base"], cost, sorted(ids))
            if best_n is None or kn < best_n:
                best_n = kn
            if best_r is None or kr < best_r:
                best_r = kr
    nominal, robust = describe(best_n[2]), describe(best_r[3])
    a, b = robust["per_case"]["base"]["weighted_mean_mm"], nominal["per_case"]["base"]["weighted_mean_mm"]
    out["optimize"] = {"status": "optimal", "reasons": [], "feasible_count": count, "evaluated": 2 ** len(free),
                       "nominal": nominal, "robust": robust, "same_plan": nominal["ids"] == robust["ids"],
                       "price_of_robustness_m": None if a is None or b is None else (a - b) / 1000}
    return out


# ---------------- fixtures ----------------
def P(i, lon, lat, w=1):
    return {"id": f"P{i}", "lon": lon, "lat": lat, "weight": w}


def C(cid, lon, lat, cost, cat="school"):
    return {"id": cid, "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical", "cost": cost}


def plan(points, cands, budget, max_sel, radius=500, req=(), exc=(), sel=(), cat="school"):
    return {"schema_version": "city-plan-v2", "category": cat, "control_points": points, "candidates": cands, "budget": budget,
            "max_selected": max_sel, "coverage_radius_m": radius, "required_ids": list(req), "excluded_ids": list(exc), "selected_ids": list(sel)}


def case(cid, label, ids):
    return {"id": cid, "label": label, "disabled_source_ids": list(ids)}


EQ_BBOX = [-0.1, -0.1, 0.1, 0.1]
EQ = [{"id": "A", "group": "school", "lon": 0.0, "lat": 0.0}, {"id": "B", "group": "school", "lon": 0.02, "lat": 0.0},
      {"id": "K", "group": "outpatient_clinic", "lon": 0.05, "lat": 0.05}]


def hand():
    two = [P(1, 0.0, 0.001, 1), P(2, 0.02, 0.001, 1)]
    differ = [C("C1", 0.0, 0.0009, 5), C("C2", 0.02, 0.0015, 5)]
    return [
        ("robust_differs_from_nominal", EQ, plan(two, differ, 5, 1, sel=["C1"]), [case("noB", "Без записи B", ["B"])]),
        ("identical_plans", EQ, plan(two, differ, 10, 2), [case("noB", "Без B", ["B"])]),
        ("all_sources_off_unknown", EQ, plan(two, [C("C1", 0.0, 0.0009, 5)], 0, 1), [case("none", "Без всех школ", ["A", "B"])]),
        ("unknown_vs_candidate", EQ, plan(two, [C("C1", 0.0, 0.0009, 5), C("C2", 0.02, 0.0015, 5)], 5, 1), [case("none", "Без всех школ", ["A", "B"])]),
        ("duplicate_cases", EQ, plan(two, differ, 5, 1), [case("x1", "Без B", ["B"]), case("x2", "Без B (повтор)", ["B"])]),
        ("required_excluded", EQ, plan(two, differ + [C("C3", 0.01, 0.0, 2)], 10, 2, req=["C3"], exc=["C2"]), [case("noB", "Без B", ["B"]), case("noA", "Без A", ["A"])]),
        ("required_over_budget", EQ, plan(two, differ, 4, 1, req=["C1"]), [case("noB", "Без B", ["B"])]),
        ("zero_budget", EQ, plan(two, differ, 0, 2, sel=["C2"]), [case("noA", "Без A", ["A"])]),
        ("no_candidates", EQ, plan(two, [], 100, 2), [case("noA", "Без A", ["A"])]),
    ]


def load_data():
    text = (APP / "web" / "data.js").read_text(encoding="utf-8")
    body = text[text.index("window.CITY_EVIDENCE =") + len("window.CITY_EVIDENCE ="):].strip()
    return json.loads(body[:-1] if body.endswith(";") else body)


def real(data, city, cat, n_c, n_p, budget, max_sel, radius):
    c = data["cities"][city]
    w, s, e, n = c["bbox"]
    g = lambda fx, fy: (round(w + (e - w) * fx, 6), round(s + (n - s) * fy, 6))  # noqa: E731
    pts = [P(k + 1, *g(0.1 + 0.8 * ((k % 4) / 3), 0.1 + 0.8 * ((k // 4) / 3)), 1 + (k * 7) % 9) for k in range(n_p)]
    cands = [C(f"K{k + 1:02d}", *g(0.15 + 0.7 * ((k % 4) / 3), 0.2 + 0.6 * ((k // 4) / 2)), 100 + (k * 37) % 300, cat) for k in range(n_c)]
    src = sorted(p["id"] for p in c["places"] if p["group"] == cat)
    cases = [case("every2", "Каждая вторая запись", src[::2]), case("first3", "Первые три записи по ID", src[:3]),
             case("all", "Все записи категории", src), case("first3dup", "Повтор первых трёх", src[:3])]
    records = [{"id": p["id"], "group": p["group"], "lon": p["lon"], "lat": p["lat"]} for p in c["places"]]
    return records, plan(pts, cands, budget, max_sel, radius, sel=[cands[0]["id"]], cat=cat), cases


def build():
    data = load_data()
    out = []
    for name, records, pl, cs in hand():
        out.append({"name": name, "kind": "synthetic_hand", "bbox": EQ_BBOX, "records": records, "plan": pl, "cases": cs, "expected": solve(records, pl, cs)})
    for city in sorted(data["cities"]):
        for cat in ("school", "outpatient_clinic"):
            records, pl, cs = real(data, city, cat, 8, 12, 600, 3, 400)
            out.append({"name": f"{city}_{cat}_8x12x5", "kind": "synthetic_inputs_on_real_slice", "city": city, "plan": pl, "cases": cs,
                        "expected": solve(records, pl, cs)})
    return {"generator": "tools/resilience_oracle.py", "metric_version": "haversine-mm-v1", "objective_version": "worst-lex-v1",
            "note": "SYNTHETIC inputs; source records on real slices unchanged", "cases": out}


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
