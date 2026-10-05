"""K02 r8: независимый Python-оракул city-plan-v2 (CORE_SPEC), не трансляция plan_engine.js.

Отличия реализации от JS: перебор itertools.combinations по ВСЕМ кандидатам с фильтром required/excluded,
ключи — кортежи Python, ничьи — сравнение кортежей (id-кортеж в конце), гаверсинус написан заново по формуле.
Вход: fixtures/<name>.json (context + scenario) и variants.json. Выход: expected/<name>__<variant>.json — ожидаемые факты.
Запуск: python3 oracle/plan_oracle.py   (stdlib, без сети)
"""
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
R = 6371008.8


def hav_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    a = min(1.0, max(0.0, a))
    return 2 * R * math.asin(math.sqrt(a))


def to_mm(d):
    return math.floor(d * 1000 + 0.5)  # все расстояния неотрицательны


def nearest(point, objects):
    """objects: [(key, lon, lat)] → (mm, key) | None; ничья — меньший key."""
    best = None
    for key, lon, lat in objects:
        cand = (to_mm(hav_m(point["lon"], point["lat"], lon, lat)), key)
        if best is None or cand < best:
            best = cand
    return best


def metrics(sc, sources, chosen):
    cands = {c["id"]: c for c in sc["candidates"]}
    objs = [("source:" + s["id"], s["lon"], s["lat"]) for s in sources]
    objs += [("hypothetical:" + i, cands[i]["lon"], cands[i]["lat"]) for i in chosen]
    radius = sc["coverage_radius_m"] * 1000
    known, unknown, covered, total = [], 0, 0, 0
    for p in sc["control_points"]:
        total += p["weight"]
        n = nearest(p, objs)
        if n is None:
            unknown += 1
        else:
            known.append((p["weight"], n[0]))
            if n[0] <= radius:
                covered += p["weight"]
    wsum = sum(w * d for w, d in known)
    return {
        "unknown_count": unknown, "weighted_sum_mm": wsum,
        "weighted_mean_mm": wsum / total if unknown == 0 else None,
        "max_mm": max(d for _, d in known) if unknown == 0 else None,
        "covered_weight": covered, "coverage_fraction": covered / total,
        "cost": sum(cands[i]["cost"] for i in chosen), "count": len(chosen),
    }


def feasible(sc, chosen, budget):
    m_cost = sum(c["cost"] for c in sc["candidates"] if c["id"] in chosen)
    return (m_cost <= budget and len(chosen) <= sc["max_selected"]
            and set(sc["required_ids"]) <= set(chosen) and not set(sc["excluded_ids"]) & set(chosen))


def solve(sc, sources, budget):
    ids = sorted(c["id"] for c in sc["candidates"])
    plans = []
    for k in range(0, len(ids) + 1):
        for comb in itertools.combinations(ids, k):
            if feasible(sc, comb, budget):
                plans.append((comb, metrics(sc, sources, comb)))
    inf = float("inf")
    keyf = {
        "mean": lambda m: (m["unknown_count"], m["weighted_sum_mm"], inf if m["max_mm"] is None else m["max_mm"], m["cost"]),
        "minimax": lambda m: (m["unknown_count"], inf if m["max_mm"] is None else m["max_mm"], m["weighted_sum_mm"], m["cost"]),
        "coverage": lambda m: (-m["covered_weight"], m["unknown_count"], m["weighted_sum_mm"], inf if m["max_mm"] is None else m["max_mm"], m["cost"]),
    }
    winners = {}
    for name, f in keyf.items():
        best = min(plans, key=lambda pm: (f(pm[1]), pm[0]), default=None)
        winners[name] = None if best is None else {"selected_ids": list(best[0]), "metrics": best[1]}
    full = {}
    for comb, m in plans:
        if m["unknown_count"] == 0:
            k = (m["cost"], m["weighted_sum_mm"])
            if k not in full or comb < full[k]:
                full[k] = comb
    pts = list(full.items())
    front = sorted([(k, comb) for k, comb in pts
                    if not any(o[0] <= k[0] and o[1] <= k[1] and o != k for o, _ in pts)])
    return {"status": "optimal" if plans else "infeasible", "feasible_count": len(plans), "objectives": winners,
            "pareto": [{"cost": k[0], "weighted_sum_mm": k[1], "selected_ids": list(c)} for k, c in front]}


def expected(fx, patch):
    sc = dict(fx["scenario"], **patch)
    sources = fx["context"]["sources"]
    main = solve(sc, sources, sc["budget"])
    tw = sum(p["weight"] for p in sc["control_points"])
    roles = {"baseline": {"selected_ids": [], "metrics": metrics(sc, sources, ())},
             "manual": {"selected_ids": sorted(sc["selected_ids"]), "metrics": metrics(sc, sources, tuple(sorted(sc["selected_ids"])))}}
    roles.update({k: v for k, v in main["objectives"].items() if v is not None})
    facts = {}
    for role, p in roles.items():
        m = p["metrics"]
        for key, mk in [("weighted_mean", "weighted_mean_mm"), ("max", "max_mm"), ("covered_weight", "covered_weight"), ("cost", "cost"),
                        ("count", "count"), ("unknown_count", "unknown_count"), ("coverage_fraction", "coverage_fraction")]:
            facts[f"plan.{role}.{key}"] = m[mk]
        facts[f"plan.{role}.selection"] = ", ".join(p["selected_ids"])
    facts["plan.manual.feasible"] = 1 if feasible(sc, sc["selected_ids"], sc["budget"]) else 0
    facts["constraint.feasible_count"] = main["feasible_count"]
    facts["constraint.sources"] = len(sources)
    budgets = sorted(set([0, sc["budget"] // 2, sc["budget"]]))
    for i, b in enumerate(budgets):
        r = solve(sc, sources, b)
        facts[f"sensitivity.s{i + 1}.budget"] = b
        facts[f"sensitivity.s{i + 1}.status"] = r["status"]
        mean = r["objectives"]["mean"]
        facts[f"sensitivity.s{i + 1}.mean_cost"] = mean["metrics"]["cost"] if mean else None
        facts[f"sensitivity.s{i + 1}.mean_weighted_mean"] = mean["metrics"]["weighted_mean_mm"] if mean else None
    for i, q in enumerate(main["pareto"]):
        facts[f"pareto.p{i + 1}.cost"] = q["cost"]
        facts[f"pareto.p{i + 1}.weighted_mean"] = q["weighted_sum_mm"] / tw
        facts[f"pareto.p{i + 1}.selection"] = ", ".join(q["selected_ids"])
    return {"status": main["status"], "facts": facts}


def main():
    variants = json.loads((HERE / "variants.json").read_text(encoding="utf-8"))
    out = HERE / "expected"
    out.mkdir(exist_ok=True)
    for v in variants["variants"]:
        fx = json.loads((HERE / "fixtures" / (v["fixture"] + ".json")).read_text(encoding="utf-8"))
        res = expected(fx, v.get("patch", {}))
        res.update({"fixture": v["fixture"], "variant": v["name"], "patch": v.get("patch", {}), "oracle": "plan_oracle.py (Python, независимая реализация)"})
        (out / f"{v['fixture']}__{v['name']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(v["fixture"], v["name"], res["status"], res["facts"].get("plan.mean.selection"), res["facts"].get("plan.minimax.selection"),
              res["facts"].get("plan.coverage.selection"))


if __name__ == "__main__":
    main()
