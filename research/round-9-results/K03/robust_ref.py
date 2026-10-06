"""K03 r9, этап 3: независимый оракул случаев устойчивости — baseline каждого случая с нуля и полный перебор планов.

Используется только для проверки (сборка считает сама в web/resilience.js). Правила — CORE_SPEC r9:
  baseline случая = ближайшая НЕисключённая запись категории (haversine-mm-v1, ничья → меньший ID; записей нет → None);
  after = min(baseline, выбранные кандидаты), ничья: source раньше hypothetical, затем ID;
  L = (unknown_count, weighted_sum_mm, max_mm | +inf при неизвестных); W = lex max L по случаям (включая base);
  обычный план = min (L_base, cost, IDs); устойчивый = min (W, L_base, cost, IDs); цена = (mean_base устойчивого − обычного)/1000 м.
"""
import itertools
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import R, u16  # noqa: E402
from resilience_cases_ref import case_baseline  # noqa: E402

INF = math.inf


def cmp_ids_key(ids):
    """cmpIds сборки: поэлементно по UTF-16, затем более короткий раньше — как кортеж ключей."""
    return tuple(u16(i) for i in ids)


def per_case_rows(data, plan, cases):
    """{case_id: [{'point', 'base': {'id','mm','tied_ids'}|None}]} для base и пользовательских случаев."""
    allc = [{'id': 'base', 'disabled_source_ids': []}] + list(cases)
    return {c['id']: list(zip([p['id'] for p in plan['control_points']],
                              case_baseline(data, plan['city_id'], plan['category'], c['disabled_source_ids'], plan['control_points'])))
            for c in allc}


def after_rows(base_rows, plan, selected):
    cands = {q['id']: q for q in plan['candidates']}
    out = []
    for (pid, b), cp in zip(base_rows, plan['control_points']):
        pool = [(b['mm'], 0, u16(b['id']), 'source', b['id'])] if b else []
        pool += [(R.mm_between(cp, cands[i]), 1, u16(i), 'hypothetical', i) for i in selected]
        best = min(pool) if pool else None
        out.append({'point': pid, 'before_mm': b['mm'] if b else None, 'before_id': b['id'] if b else None,
                    'after_mm': best[0] if best else None, 'after': {'kind': best[3], 'id': best[4]} if best else None,
                    'delta_mm': b['mm'] - best[0] if b and best else None})
    return out


def loss(rows, weights):
    u = s = mx = 0
    for r, w in zip(rows, weights):
        if r['after_mm'] is None:
            u += 1
            continue
        s += w * r['after_mm']
        mx = max(mx, r['after_mm'])
    return (u, s, INF if u else mx)


def brute_force(data, plan, cases):
    """Полный перебор: nominal, robust, цена устойчивости, худшие случаи. Ничего не отбрасывает и не меняет ограничения."""
    rows = per_case_rows(data, plan, cases)
    order = ['base'] + [c['id'] for c in cases]
    weights = [p['weight'] for p in plan['control_points']]
    tw = sum(weights)
    cost_of = {q['id']: q['cost'] for q in plan['candidates']}
    ids_all = sorted(cost_of, key=u16)
    req, exc = set(plan['required_ids']), set(plan['excluded_ids'])
    best_n = best_r = None
    feasible = total = 0
    for k in range(len(ids_all) + 1):
        for sub in itertools.combinations(ids_all, k):
            total += 1
            s = set(sub)
            cost = sum(cost_of[i] for i in sub)
            if cost > plan['budget'] or len(sub) > plan['max_selected'] or not req <= s or s & exc:
                continue
            feasible += 1
            L = {c: loss(after_rows(rows[c], plan, list(sub)), weights) for c in order}
            W = max(L.values())
            kn = (L['base'], cost, cmp_ids_key(sub))
            kr = (W, L['base'], cost, cmp_ids_key(sub))
            if best_n is None or kn < best_n[0]:
                best_n = (kn, list(sub))
            if best_r is None or kr < best_r[0]:
                best_r = (kr, list(sub))

    def describe(sel):
        L = {c: loss(after_rows(rows[c], plan, sel), weights) for c in order}
        W = max(L.values())
        vec = lambda x: {'unknown_count': x[0], 'weighted_sum_mm': x[1], 'max_mm': None if x[2] == INF else x[2]}  # noqa: E731
        base = L['base']
        return {'selected_ids': sel, 'worst_vector': vec(W), 'worst_case_ids': sorted((c for c in order if L[c] == W), key=u16),
                'base_weighted_mean_mm': None if base[0] else base[1] / tw, 'loss': {c: vec(L[c]) for c in order},
                'cost': sum(cost_of[i] for i in sel)}
    if best_n is None:
        return {'status': 'infeasible', 'feasible_count': 0, 'subsets': total}
    n, r = describe(best_n[1]), describe(best_r[1])
    a, b = r['base_weighted_mean_mm'], n['base_weighted_mean_mm']
    return {'status': 'optimal', 'subsets': total, 'feasible_count': feasible, 'nominal': n, 'robust': r,
            'same_plan': n['selected_ids'] == r['selected_ids'], 'price_of_robustness_m': None if a is None or b is None else (a - b) / 1000}
