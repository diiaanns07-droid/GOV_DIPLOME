"""Детерминированные жадные базовые линии (не точный оптимум).

G1 «по ключу цели»: начиная с required, на каждом шаге добавить допустимого кандидата с наименьшим ключом цели
(CORE_SPEC); остановиться, если лучший ключ не меньше текущего. Ничьи: кандидаты перебираются по возрастанию id,
выбор только при строгом улучшении ключа (а ключ сам заканчивается отсортированными ID).
G2 «выгода/стоимость»: приоритет — уменьшение unknown_count (больше уменьшение, затем меньшая стоимость, затем id);
иначе максимум прироста основной метрики на единицу стоимости (только при приросте > 0; ничьи — меньший id).
В конце сравнить с лучшим одиночным допустимым кандидатом (required + 1) по ключу цели.
"""
from fractions import Fraction
from .metric import OBJECTIVES
from .exact import constraint_indices, infeasibility


def _metrics(pr, sel, after):
    return pr.metrics_from_after(after, sel)


def _extend(pr, after, c):
    row = pr.cand_mm[c]
    return [d if (v is None or d < v) else v for v, d in zip(after, row)]


def _primary(objective, m):
    """Основная метрика «чем больше, тем лучше» для приращения G2."""
    if objective == "mean":
        return -m["weighted_sum_mm"]
    if objective == "minimax":
        return None if m["max_mm"] is None else -m["max_mm"]
    return m["covered_weight"]


def greedy_key(pr, objective, budget, max_selected, required_ids=(), excluded_ids=()):
    keyf = OBJECTIVES[objective]
    req, exc, free = constraint_indices(pr, required_ids, excluded_ids)
    why = infeasibility(pr, req, budget, max_selected)
    if why:
        return {"status": "infeasible", "reason": why, "plan": None, "steps": []}
    sel = list(req)
    after = pr.after_vector(sel)
    cost = sum(pr.cost[i] for i in sel)
    cur = _metrics(pr, sel, after)
    steps = []
    while len(sel) < max_selected:
        best = None
        for c in sorted(free, key=lambda i: pr.cand_ids[i]):
            if c in sel or cost + pr.cost[c] > budget:
                continue
            a2 = _extend(pr, after, c)
            m2 = _metrics(pr, sel + [c], a2)
            k2 = keyf(m2)
            if best is None or k2 < best[0]:
                best = (k2, c, a2, m2)
        if best is None or not best[0] < keyf(cur):
            break
        _, c, after, cur = best
        sel.append(c); cost += pr.cost[c]
        steps.append(pr.cand_ids[c])
    return {"status": "heuristic", "plan": cur, "steps": steps}


def greedy_ratio(pr, objective, budget, max_selected, required_ids=(), excluded_ids=()):
    keyf = OBJECTIVES[objective]
    req, exc, free = constraint_indices(pr, required_ids, excluded_ids)
    why = infeasibility(pr, req, budget, max_selected)
    if why:
        return {"status": "infeasible", "reason": why, "plan": None, "steps": []}
    sel = list(req)
    after = pr.after_vector(sel)
    cost = sum(pr.cost[i] for i in sel)
    cur = _metrics(pr, sel, after)
    steps = []
    while len(sel) < max_selected:
        best_unknown, best_ratio = None, None
        for c in sorted(free, key=lambda i: pr.cand_ids[i]):
            if c in sel or cost + pr.cost[c] > budget:
                continue
            a2 = _extend(pr, after, c)
            m2 = _metrics(pr, sel + [c], a2)
            du = cur["unknown_count"] - m2["unknown_count"]
            if du > 0:
                cand = (-du, pr.cost[c], pr.cand_ids[c])
                if best_unknown is None or cand < best_unknown[0]:
                    best_unknown = (cand, c, a2, m2)
                continue
            p0, p1 = _primary(objective, cur), _primary(objective, m2)
            if p0 is None or p1 is None:
                continue
            gain = p1 - p0
            if gain <= 0:
                continue
            ratio = Fraction(gain, pr.cost[c])
            if best_ratio is None or ratio > best_ratio[0]:
                best_ratio = (ratio, c, a2, m2)
        pick = best_unknown or best_ratio
        if pick is None:
            break
        _, c, after, cur = pick
        sel.append(c); cost += pr.cost[c]
        steps.append(pr.cand_ids[c])
    # сравнение с лучшим одиночным допустимым кандидатом (required + 1)
    single = None
    if len(req) < max_selected:
        base_after = pr.after_vector(req)
        base_cost = sum(pr.cost[i] for i in req)
        for c in sorted(free, key=lambda i: pr.cand_ids[i]):
            if base_cost + pr.cost[c] > budget:
                continue
            m = _metrics(pr, req + [c], _extend(pr, base_after, c))
            if single is None or keyf(m) < keyf(single):
                single = m
    if single is not None and keyf(single) < keyf(cur):
        return {"status": "heuristic", "plan": single, "steps": steps, "replaced_by_best_single": True}
    return {"status": "heuristic", "plan": cur, "steps": steps, "replaced_by_best_single": False}
