#!/usr/bin/env python3
"""Независимый Python-оракул city-plan-v2 (K05 r8). Не трансляция plan.js:
перебор itertools.combinations по размеру плана, расстояния по формуле CORE_SPEC с floor(x+0.5),
ключи целей кортежами Python, Парето через явное O(N²) доминирование.

  python oracle/oracle.py --cases runs/cases_dump.json [--json OUT]
cases_dump.json пишет tests/dump_cases.cjs: [{name, context, scenario, result}] — result это ответ plan.js,
оракул пересчитывает задачу сам и сравнивает.
"""
import argparse
import itertools
import json
import math
import sys

R = 6371008.8


def mm(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    a = min(1.0, max(0.0, a))
    return math.floor(2 * R * math.asin(math.sqrt(a)) * 1000 + 0.5)


def solve(ctx, s, budget=None):
    budget = s["budget"] if budget is None else budget
    src = [r for r in ctx["records"] if r["group"] == s["category"]]
    pts = s["control_points"]
    cands = {c["id"]: c for c in s["candidates"]}
    base = []
    for p in pts:
        ds = [mm(p["lon"], p["lat"], r["lon"], r["lat"]) for r in src]
        base.append(min(ds) if ds else None)
    cd = {cid: [mm(p["lon"], p["lat"], c["lon"], c["lat"]) for p in pts] for cid, c in cands.items()}
    total_w = sum(p["weight"] for p in pts)
    req, exc = set(s["required_ids"]), set(s["excluded_ids"])
    plans = []
    ids_all = sorted(cands)
    for k in range(0, len(ids_all) + 1):
        for combo in itertools.combinations(ids_all, k):
            sel = set(combo)
            cost = sum(cands[c]["cost"] for c in combo)
            if not req <= sel or sel & exc or k > s["max_selected"] or cost > budget:
                continue
            after = []
            for i in range(len(pts)):
                vals = ([base[i]] if base[i] is not None else []) + [cd[c][i] for c in combo]
                after.append(min(vals) if vals else None)
            unknown = sum(1 for a in after if a is None)
            wsum = sum(p["weight"] * a for p, a in zip(pts, after) if a is not None)
            mx = max(after) if unknown == 0 else None
            covered = sum(p["weight"] for p, a in zip(pts, after) if a is not None and a <= s["coverage_radius_m"] * 1000)
            plans.append({"ids": list(combo), "cost": cost, "unknown_count": unknown, "weighted_sum_mm": wsum,
                          "max_mm": mx, "covered_weight": covered,
                          "weighted_mean_mm": wsum / total_w if unknown == 0 else None})
    inf = float("inf")
    keys = {
        "mean": lambda q: (q["unknown_count"], q["weighted_sum_mm"], inf if q["max_mm"] is None else q["max_mm"], q["cost"], q["ids"]),
        "minimax": lambda q: (q["unknown_count"], inf if q["max_mm"] is None else q["max_mm"], q["weighted_sum_mm"], q["cost"], q["ids"]),
        "coverage": lambda q: (-q["covered_weight"], q["unknown_count"], q["weighted_sum_mm"], inf if q["max_mm"] is None else q["max_mm"], q["cost"], q["ids"]),
    }
    best = {o: (min(plans, key=f) if plans else None) for o, f in keys.items()}
    known = [q for q in plans if q["unknown_count"] == 0]
    nd = [b for b in known if not any(a["cost"] <= b["cost"] and a["weighted_sum_mm"] <= b["weighted_sum_mm"]
                                      and (a["cost"] < b["cost"] or a["weighted_sum_mm"] < b["weighted_sum_mm"]) for a in known)]
    rep = {}
    for q in nd:
        k = (q["cost"], q["weighted_sum_mm"])
        if k not in rep or q["ids"] < rep[k]["ids"]:
            rep[k] = q
    pareto = [rep[k] for k in sorted(rep)]
    return {"feasible_count": len(plans), "best": best, "pareto": pareto, "excluded_partial": len(plans) - len(known)}


def compare(case):
    ctx, s, res = case["context"], case["scenario"], case["result"]
    o = solve(ctx, s)
    problems = []
    if res["status"] == "infeasible":
        if o["feasible_count"]:
            problems.append(f"JS infeasible, оракул нашёл {o['feasible_count']} планов")
        return problems
    if res["feasible_count"] != o["feasible_count"]:
        problems.append(f"feasible_count {res['feasible_count']} != {o['feasible_count']}")
    for obj in ("mean", "minimax", "coverage"):
        j, p = res["objectives"][obj], o["best"][obj]
        if j["ids"] != p["ids"]:
            problems.append(f"{obj}: ids {j['ids']} != {p['ids']}")
        for k in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"):
            if j["metrics"][k] != p[k]:
                problems.append(f"{obj}.{k}: {j['metrics'][k]} != {p[k]}")
    jp = [(q["cost"], q["weighted_sum_mm"], q["ids"]) for q in res["pareto"]]
    op = [(q["cost"], q["weighted_sum_mm"], q["ids"]) for q in o["pareto"]]
    if jp != op:
        problems.append(f"pareto JS {jp[:4]}… != oracle {op[:4]}…")
    if res["pareto_excluded_partial"] != o["excluded_partial"]:
        problems.append("pareto_excluded_partial")
    for row in res.get("sensitivity") or []:
        so = solve(ctx, s, row["budget"])
        if row["status"] == "infeasible":
            if so["feasible_count"]:
                problems.append(f"sensitivity {row['budget']}: JS infeasible")
            continue
        for obj in ("mean", "minimax", "coverage"):
            if row["objectives"][obj]["ids"] != so["best"][obj]["ids"]:
                problems.append(f"sensitivity {row['budget']} {obj}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    cases = json.load(open(a.cases, encoding="utf-8"))
    out = []
    for c in cases:
        pr = compare(c)
        out.append({"name": c["name"], "ok": not pr, "problems": pr})
        print(("PASS " if not pr else "FAIL ") + c["name"] + ("" if not pr else " — " + "; ".join(pr[:3])))
    n_ok = sum(x["ok"] for x in out)
    print(f"\n{n_ok}/{len(out)} совпали с оракулом")
    if a.json:
        json.dump({"cases": len(out), "ok": n_ok, "results": out}, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if n_ok == len(out) else 1


if __name__ == "__main__":
    sys.exit(main())
