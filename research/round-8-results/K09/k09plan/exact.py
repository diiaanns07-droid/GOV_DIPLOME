"""Точный поиск по CORE_SPEC: полный перебор допустимых подмножеств (≤16 свободных кандидатов).

Расстояния предвычислены в Problem (мм); внутри перебора гаверсинус не считается. Вектор after для маски
получается из родителя (маска без младшего бита) поэлементным минимумом с одним кандидатом.
Подмножество допустимого плана тоже допустимо (стоимости > 0), поэтому достаточно обходить допустимые маски.
"""
import hashlib, json
from . import METRIC_VERSION
from .metric import OBJECTIVES

MAX_FREE = 16


def constraint_indices(pr, required_ids, excluded_ids):
    req = sorted(pr.cand_index[c] for c in required_ids)
    exc = set(pr.cand_index[c] for c in excluded_ids)
    free = [i for i in range(len(pr.cand_ids)) if i not in exc and i not in req]
    return req, exc, free


def infeasibility(pr, req, budget, max_selected):
    if len(req) > max_selected:
        return "required_count_exceeds_max_selected"
    if sum(pr.cost[i] for i in req) > budget:
        return "required_cost_exceeds_budget"
    return None


def problem_digest(context, scenario):
    """Не зависит от порядка массивов и записи чисел (70 и 70.0 — один digest); selected_ids не входит."""
    payload = {
        "metric_version": METRIC_VERSION, "source_snapshot": context["source_snapshot"], "city_id": scenario["city_id"],
        "category": scenario["category"],
        "points": sorted([p["id"], float(p["lon"]), float(p["lat"]), int(p["weight"])] for p in scenario["control_points"]),
        "candidates": sorted([c["id"], float(c["lon"]), float(c["lat"]), int(c["cost"]), c["category"], c["kind"]] for c in scenario["candidates"]),
        "budget": int(scenario["budget"]), "max_selected": int(scenario["max_selected"]), "radius_m": int(scenario["coverage_radius_m"]),
        "required": sorted(scenario["required_ids"]), "excluded": sorted(scenario["excluded_ids"]),
        "sources": sorted([s["id"], float(s["lon"]), float(s["lat"])] for s in context["sources"]),
    }
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def pareto_front(entries):
    """entries: [(cost, wsum, ids)] только для планов без unknown. Минимизация (cost, wsum); равные пары -> один (меньшие ids)."""
    out, best_w = [], None
    for cost, wsum, ids in sorted(entries):
        if best_w is None or wsum < best_w:      # строго лучше по wsum при не меньшем cost; равные пары остаются первыми (меньшие ids)
            out.append((cost, wsum, ids))
            best_w = wsum
    return [{"cost": c, "weighted_sum_mm": w, "selected_ids": ids} for c, w, ids in out]


def optimize(pr, budget, max_selected, required_ids=(), excluded_ids=(), with_pareto=True):
    """Возвращает {status, reason?, objectives{mean,minimax,coverage}, pareto, evaluated, feasible_count, free_n}."""
    req, exc, free = constraint_indices(pr, required_ids, excluded_ids)
    why = infeasibility(pr, req, budget, max_selected)
    if why:
        return {"status": "infeasible", "reason": why, "objectives": {k: None for k in OBJECTIVES}, "pareto": [],
                "evaluated": 0, "feasible_count": 0, "free_n": len(free)}
    if len(free) > MAX_FREE:
        return {"status": "too_large", "reason": f"free candidates {len(free)} > {MAX_FREE}", "objectives": {k: None for k in OBJECTIVES},
                "pareto": [], "evaluated": 0, "feasible_count": 0, "free_n": len(free)}
    nf = len(free)
    base_after = pr.after_vector(req)
    base_cost = sum(pr.cost[i] for i in req)
    room = max_selected - len(req)
    after = {0: base_after}
    cost_of = {0: base_cost}
    cnt_of = {0: 0}
    best = {k: None for k in OBJECTIVES}
    best_key = {k: None for k in OBJECTIVES}
    pareto_entries = []
    weights, rad = pr.weights, pr.radius_mm
    evaluated = 0
    for mask in range(1 << nf):
        if mask:
            low = mask & -mask
            parent = mask ^ low
            if parent not in after:
                continue
            bit = low.bit_length() - 1
            c = free[bit]
            cnt = cnt_of[parent] + 1
            cost = cost_of[parent] + pr.cost[c]
            if cnt > room or cost > budget:
                continue
            row = pr.cand_mm[c]
            after[mask] = [d if (v is None or d < v) else v for v, d in zip(after[parent], row)]
            cost_of[mask] = cost
            cnt_of[mask] = cnt
        av = after[mask]
        evaluated += 1
        unknown = 0; wsum = 0; mx = -1; covered = 0
        for w, v in zip(weights, av):
            if v is None:
                unknown += 1
            else:
                wsum += w * v
                if v > mx: mx = v
                if v <= rad: covered += w
        sel = req + [free[b] for b in range(nf) if mask >> b & 1]
        m = {"unknown_count": unknown, "weighted_sum_mm": wsum, "max_mm": mx if unknown == 0 and av else None,
             "covered_weight": covered, "cost": cost_of[mask], "selected_ids": sorted(pr.cand_ids[i] for i in sel)}
        for k, keyf in OBJECTIVES.items():
            kk = keyf(m)
            if best_key[k] is None or kk < best_key[k]:
                best_key[k], best[k] = kk, m
        if with_pareto and unknown == 0:
            pareto_entries.append((m["cost"], wsum, m["selected_ids"]))
    objectives = {}
    for k, m in best.items():
        full = dict(m)
        full["weighted_mean_mm"] = (m["weighted_sum_mm"] / pr.total_weight) if m["unknown_count"] == 0 else None
        full["coverage_fraction"] = m["covered_weight"] / pr.total_weight
        objectives[k] = full
    return {"status": "optimal", "objectives": objectives, "pareto": pareto_front(pareto_entries) if with_pareto else None,
            "evaluated": evaluated, "feasible_count": evaluated, "free_n": nf, "subsets_total": 1 << nf}


def budget_sensitivity(pr, budget, max_selected, required_ids=(), excluded_ids=()):
    out = []
    for b in sorted({0, budget // 2, budget}):
        r = optimize(pr, b, max_selected, required_ids, excluded_ids, with_pareto=False)
        out.append({"budget": b, "status": r["status"], "reason": r.get("reason"),
                    "objectives": {k: (None if v is None else {"selected_ids": v["selected_ids"], "cost": v["cost"],
                                                               "weighted_sum_mm": v["weighted_sum_mm"], "max_mm": v["max_mm"],
                                                               "covered_weight": v["covered_weight"], "unknown_count": v["unknown_count"]})
                                   for k, v in r["objectives"].items()}})
    return out
