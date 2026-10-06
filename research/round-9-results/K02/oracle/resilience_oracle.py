"""K02 r9: независимый Python-оракул city-resilience-v1 (CORE_SPEC r9) — не трансляция resilience_ref.js/plan.js.

Исходные записи берутся из r8-фикстуры (inputs/r8/fixtures/*.json, context.sources; совпадение с data.js сборки
подтверждено тестом B0), envelope — из fixtures/res_*.json. Гаверсинус и мм-округление написаны заново.
Выход: expected/res_<name>.json. Запуск: python3 oracle/resilience_oracle.py
"""
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
R = 6371008.8
INF = float("inf")


def mm(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return math.floor(2 * R * math.asin(math.sqrt(min(1.0, max(0.0, a)))) * 1000 + 0.5)


def metrics(sc, sources, chosen):
    cand = {c["id"]: c for c in sc["candidates"]}
    objs = [(s["lon"], s["lat"]) for s in sources] + [(cand[i]["lon"], cand[i]["lat"]) for i in chosen]
    unknown, wsum, mx, cov, tot = 0, 0, -1, 0, 0
    for p in sc["control_points"]:
        tot += p["weight"]
        ds = [mm(p["lon"], p["lat"], lo, la) for lo, la in objs]
        if not ds:
            unknown += 1
            continue
        d = min(ds)
        wsum += p["weight"] * d
        mx = max(mx, d)
        if d <= sc["coverage_radius_m"] * 1000:
            cov += p["weight"]
    return {"unknown_count": unknown, "weighted_sum_mm": wsum, "weighted_mean_mm": wsum / tot if unknown == 0 else None,
            "max_mm": mx if unknown == 0 else None, "covered_weight": cov, "cost": sum(cand[i]["cost"] for i in chosen)}


def Lvec(m):
    return (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"])


def feasible(sc, chosen):
    cost = sum(c["cost"] for c in sc["candidates"] if c["id"] in chosen)
    return cost <= sc["budget"] and len(chosen) <= sc["max_selected"] and set(sc["required_ids"]) <= set(chosen) and not set(sc["excluded_ids"]) & set(chosen)


def per_cases(sc, sources, cases, chosen):
    out = []
    for c in cases:
        src = [s for s in sources if s["id"] not in set(c["disabled_source_ids"])]
        out.append((c["id"], metrics(sc, src, chosen)))
    worst = max(Lvec(m) for _, m in out)
    return out, worst, sorted(cid for cid, m in out if Lvec(m) == worst)


def main():
    out = HERE / "expected"
    out.mkdir(exist_ok=True)
    for f in sorted((HERE / "fixtures").glob("res_*.json")):
        fx = json.loads(f.read_text(encoding="utf-8"))
        r8 = json.loads((HERE / "inputs/r8/fixtures" / (fx["provenance"]["from_r8_fixture"] + ".json")).read_text(encoding="utf-8"))
        sources, env = r8["context"]["sources"], fx["envelope"]
        sc = env["plan"]
        cases = [{"id": "base", "disabled_source_ids": []}] + env["cases"]
        ids = sorted(c["id"] for c in sc["candidates"])
        plans = [comb for k in range(len(ids) + 1) for comb in itertools.combinations(ids, k) if feasible(sc, comb)]
        res = {"fixture": fx["name"], "feasible_count": len(plans)}
        if not plans:
            res.update(status="infeasible", nominal=None, robust=None, price_m=None)
        else:
            def base_m(comb):
                return metrics(sc, sources, comb)
            nominal = min(plans, key=lambda c: ((lambda m: (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"], m["cost"]))(base_m(c)), c))
            scored = []
            for comb in plans:
                pcs, worst, wids = per_cases(sc, sources, cases, comb)
                scored.append(((worst, Lvec(pcs[0][1]), pcs[0][1]["cost"], comb), comb))
            robust = min(scored)[1]

            def summary(comb):
                pcs, worst, wids = per_cases(sc, sources, cases, comb)
                return {"selected_ids": list(comb), "worst_vector": [worst[0], worst[1], None if worst[2] == INF else worst[2]], "worst_case_ids": wids,
                        "per_case": {cid: m for cid, m in pcs}}
            n, r = summary(nominal), summary(robust)
            nm, rm = n["per_case"]["base"]["weighted_mean_mm"], r["per_case"]["base"]["weighted_mean_mm"]
            res.update(status="optimal", nominal=n, robust=r, price_m=None if nm is None or rm is None else (rm - nm) / 1000)
        man = sorted(sc["selected_ids"])
        pcs, worst, wids = per_cases(sc, sources, cases, man)
        res["manual"] = {"selected_ids": man, "worst_vector": [worst[0], worst[1], None if worst[2] == INF else worst[2]], "worst_case_ids": wids,
                         "per_case": {cid: m for cid, m in pcs}, "feasible": feasible(sc, man)}
        (out / f"{fx['name']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(fx["name"], res["status"], res["nominal"] and res["nominal"]["selected_ids"], res["robust"] and res["robust"]["selected_ids"], res["price_m"])


if __name__ == "__main__":
    main()
