"""Этап 3: прогон предрегистрированной сетки и агрегирование.

Дизайны:
- v1 (config/experiment_config.json): seed-строка включает все факторы → межэкземплярные сравнения факторов;
  бюджет = доля суммы стоимостей ВСЕХ кандидатов.
- v2 (config/experiment_config_v2.json, после обзора v1): парная вложенная геометрия (suite.make_scenario_v2),
  бюджет = доля суммы max_selected самых дорогих кандидатов, дополнительный вариант G2id, парные контрасты.
Детерминированные выходы (runs, scenarios, summary) отделены от замеров времени (timing).
Вторичный анализ парный: экземпляр основной сетки (n_cand=16, n_pts=25, ratio=0.5, random_1_100, max_selected=3,
радиус 300), меняется только max_selected или радиус (в v2 бюджет считается по базовому max_selected=3).
"""
import math, statistics, time
from functools import partial
from .metric import Problem
from .exact import optimize, problem_digest, budget_sensitivity
from .greedy import greedy_key, greedy_ratio
from .gap import gap
from . import suite

OBJS = ("mean", "minimax", "coverage")
ALG_FUNCS = {"G1": greedy_key, "G2": greedy_ratio, "G2id": partial(greedy_ratio, unknown_tie="id")}
ALG_ORDER = ("G1", "G2", "G2id")
FACTORS = ("slice", "n_candidates", "n_points", "budget_ratio", "weights")


def design(cfg):
    return cfg.get("design", "v1")


def algorithms(cfg):
    return list(cfg.get("algorithms_run", ["G1", "G2"]))


def scenario_plan(cfg):
    """Список (analysis, slice_id, параметры генерации, переопределения) в фиксированном порядке."""
    f, sec = cfg["factors"], cfg["secondary"]
    out = []
    for sl in cfg["baselines"]["slices"]:
        for nc in f["n_candidates"]:
            for npnt in f["n_points"]:
                for br in f["budget_ratio"]:
                    for w in f["weights"]:
                        for seed in cfg["seeds"]:
                            out.append(("main", sl["id"], (nc, npnt, br, w, f["max_selected"], f["coverage_radius_m"], seed), {}))
    base = (16, 25, 0.5, "random_1_100", f["max_selected"], f["coverage_radius_m"])
    for sl in cfg["baselines"]["slices"]:
        for seed in cfg["seeds"]:
            for ms in sec["max_selected"]:
                out.append(("sec_max_selected", sl["id"], base + (seed,), {"max_selected": ms}))
            for rad in sec["coverage_radius_m"]:
                out.append(("sec_radius", sl["id"], base + (seed,), {"coverage_radius_m": rad}))
    return out


def _timed(fn, repeats):
    best, res = None, None
    for _ in range(repeats):
        t = time.perf_counter()
        res = fn()
        dt = time.perf_counter() - t
        best = dt if best is None or dt < best else best
    return res, best


def make(ctx, cfg, params):
    nc, npnt, br, w, ms, rad, seed = params
    if design(cfg) == "v2":
        return suite.make_scenario_v2(ctx, nc, npnt, br, w, ms, rad, seed, cfg["config_version"])
    return suite.make_scenario(ctx, nc, npnt, br, w, ms, rad, seed, cfg["config_version"])


def run_one(ctx, cfg, analysis, slice_id, params, override, repeats):
    nc, npnt, br, w, ms, rad, seed = params
    sc = make(ctx, cfg, params)
    sc.update(override)
    ms, rad = sc["max_selected"], sc["coverage_radius_m"]
    key = f"{analysis}|{slice_id}|nc{nc}|np{npnt}|br{br}|{w}|ms{ms}|r{rad}|s{seed}"
    pr, t_pre = _timed(lambda: Problem(sc["control_points"], ctx["sources"], sc["candidates"], rad), repeats)
    ex, t_ex = _timed(lambda: optimize(pr, sc["budget"], ms, with_pareto=False), repeats)
    assert ex["status"] == "optimal", key
    full, t_full = _timed(lambda: (optimize(pr, sc["budget"], ms, with_pareto=True), budget_sensitivity(pr, sc["budget"], ms)), repeats)
    par = full[0]["pareto"]
    unconstrained = sum(math.comb(nc, k) for k in range(min(ms, nc) + 1))
    row_s = {"scenario_key": key, "analysis": analysis, "slice": slice_id, "n_candidates": nc, "n_points": npnt,
             "budget_ratio": br, "weights": w, "max_selected": ms, "radius_m": rad, "seed": seed, "budget": sc["budget"],
             "problem_digest": problem_digest(ctx, sc), "feasible_count": ex["feasible_count"], "subsets_total": ex["subsets_total"],
             "budget_binding": int(ex["feasible_count"] < unconstrained),
             "baseline_unknown_points": sum(1 for b in pr.base if b is None), "pareto_size": len(par),
             "distinct_exact_plans": len({tuple(ex["objectives"][o]["selected_ids"]) for o in OBJS})}
    for o in OBJS:
        row_s[f"exact_{o}_ids"] = " ".join(ex["objectives"][o]["selected_ids"])
    timing = {"scenario_key": key, "t_precompute_s": t_pre, "t_exact_all3_s": t_ex, "t_exact_full_output_s": t_full}
    runs = []
    for o in OBJS:
        e = ex["objectives"][o]
        for name in algorithms(cfg):
            fn = ALG_FUNCS[name]
            r, t = _timed(lambda: fn(pr, o, sc["budget"], ms), repeats)
            g = r["plan"]
            x = gap(o, g, e)
            if x["greedy_better_than_exact"]:
                raise AssertionError(f"greedy better than exact: {key} {o} {name}")
            timing[f"t_{name}_{o}_s"] = t
            runs.append({"scenario_key": key, "analysis": analysis, "slice": slice_id, "n_candidates": nc, "n_points": npnt,
                         "budget_ratio": br, "weights": w, "max_selected": ms, "radius_m": rad, "seed": seed,
                         "objective": o, "algorithm": name, "hit": int(x["hit"]),
                         "primary_equal": "" if x["abs"] is None else int(x["abs"] == 0),
                         "unknown_worse": int(x["unknown_worse"]), "abs_gap": "" if x["abs"] is None else x["abs"],
                         "rel_gap": "" if x["rel"] is None else f"{x['rel']:.9f}",
                         "greedy_ids": " ".join(g["selected_ids"]), "exact_ids": " ".join(e["selected_ids"]),
                         "greedy_cost": g["cost"], "exact_cost": e["cost"], "steps": len(r["steps"]),
                         "replaced_by_best_single": "" if name == "G1" else int(r["replaced_by_best_single"])})
    return row_s, runs, timing


# ---------- статистика ----------
def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return None, None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(max(0.0, c - h), 6), round(min(1.0, c + h), 6)


def mcnemar_exact(b, c):
    """Двусторонний точный биномиальный тест для несогласных пар (b, c): p = min(1, 2·P(X ≤ min(b,c))), X ~ Bin(b+c, 1/2).
    Без округления; ниже наименьшего float даёт 0.0 — тогда смотреть mcnemar_log10."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def mcnemar_log10(b, c):
    """log10 того же p точно на целых (p может быть меньше наименьшего float)."""
    n = b + c
    if n == 0:
        return 0.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return round(min(0.0, math.log10(2 * tail) - n * math.log10(2)), 3)


def _q(xs, q):
    """Квантиль методом nearest-rank (детерминирован, без интерполяции)."""
    if not xs:
        return None
    xs = sorted(xs)
    return xs[max(0, math.ceil(q * len(xs)) - 1)]


def _cell(rows):
    n = len(rows)
    hits = sum(r["hit"] for r in rows)
    lo, hi = wilson(hits, n)
    rel = [float(r["rel_gap"]) for r in rows if r["rel_gap"] != ""]
    rel_miss = [v for v in rel if v > 0]
    pe = [r["primary_equal"] for r in rows if r["primary_equal"] != ""]
    return {"n": n, "hits": hits, "hit_rate": round(hits / n, 6) if n else None, "wilson95": [lo, hi],
            "primary_equal": sum(pe), "primary_defined": len(pe), "unknown_worse": sum(r["unknown_worse"] for r in rows),
            "rel_defined": len(rel), "rel_undefined": n - len(rel),
            "rel_mean": round(statistics.fmean(rel), 6) if rel else None, "rel_p50": _q(rel, 0.5), "rel_p90": _q(rel, 0.9),
            "rel_max": max(rel) if rel else None, "rel_positive_n": len(rel_miss),
            "rel_positive_p50": _q(rel_miss, 0.5), "rel_positive_p90": _q(rel_miss, 0.9)}


def _mcn(xa, xb):
    """xa, xb: {pair_key: 0/1}; общие ключи."""
    ks = sorted(set(xa) & set(xb))
    b = sum(1 for k in ks if xa[k] and not xb[k])
    c = sum(1 for k in ks if xb[k] and not xa[k])
    return {"pairs": len(ks), "a_only": b, "b_only": c, "both": sum(1 for k in ks if xa[k] and xb[k]),
            "neither": sum(1 for k in ks if not xa[k] and not xb[k]),
            "a_rate": round(sum(xa[k] for k in ks) / len(ks), 6) if ks else None,
            "b_rate": round(sum(xb[k] for k in ks) / len(ks), 6) if ks else None,
            "p_exact_two_sided": mcnemar_exact(b, c), "log10_p": mcnemar_log10(b, c)}


def _pe(r):
    return 1 if r["primary_equal"] == 1 else 0


def summarize(runs, scen, cfg=None):
    algs = [a for a in ALG_ORDER if any(r["algorithm"] == a for r in runs)]
    out = {"algorithms": algs, "overall": {}, "by_factor": {}, "by_budget_binding": {}, "secondary": {},
           "g1_vs_g2_mcnemar": {}, "g1_vs_g2_mcnemar_primary": {}, "exact_plans": {}}
    binding = {s["scenario_key"]: s["budget_binding"] for s in scen}
    main = [r for r in runs if r["analysis"] == "main"]
    for o in OBJS:
        for a in algs:
            sel = [r for r in main if r["objective"] == o and r["algorithm"] == a]
            out["overall"][f"{a}/{o}"] = _cell(sel)
            for fac in FACTORS:
                levels = sorted({r[fac] for r in sel}, key=lambda v: (str(type(v)), v))
                out["by_factor"].setdefault(fac, {})[f"{a}/{o}"] = {str(v): _cell([r for r in sel if r[fac] == v]) for v in levels}
            out["by_budget_binding"][f"{a}/{o}"] = {str(b): _cell([r for r in sel if binding[r["scenario_key"]] == b])
                                                    for b in (0, 1) if any(binding[r["scenario_key"]] == b for r in sel)}
            for an, fac in (("sec_max_selected", "max_selected"), ("sec_radius", "radius_m")):
                s2 = [r for r in runs if r["analysis"] == an and r["objective"] == o and r["algorithm"] == a]
                levels = sorted({r[fac] for r in s2})
                out["secondary"].setdefault(an, {})[f"{a}/{o}"] = {str(v): _cell([r for r in s2 if r[fac] == v]) for v in levels}
        hit = {a: {r["scenario_key"]: r["hit"] for r in main if r["objective"] == o and r["algorithm"] == a} for a in algs}
        pe = {a: {r["scenario_key"]: _pe(r) for r in main if r["objective"] == o and r["algorithm"] == a} for a in algs}
        m = _mcn(hit["G1"], hit["G2"])
        out["g1_vs_g2_mcnemar"][o] = {"G1_only_hit": m["a_only"], "G2_only_hit": m["b_only"], "both_hit": m["both"],
                                      "both_miss": m["neither"], "p_exact_two_sided": m["p_exact_two_sided"], "log10_p": m["log10_p"]}
        out["g1_vs_g2_mcnemar_primary"][o] = _mcn(pe["G1"], pe["G2"])
        if "G2id" in algs:
            out.setdefault("g2_vs_g2id_mcnemar", {})[o] = _mcn(hit["G2"], hit["G2id"])
    ms = [s for s in scen if s["analysis"] == "main"]
    out["exact_plans"] = {"scenarios": len(ms),
                          "distinct_plans_across_objectives": {str(k): sum(1 for s in ms if s["distinct_exact_plans"] == k) for k in (1, 2, 3)},
                          "baseline_unknown_scenarios": sum(1 for s in ms if s["baseline_unknown_points"] > 0),
                          "budget_binding_scenarios": sum(s["budget_binding"] for s in ms),
                          "feasible_count_max": max(s["feasible_count"] for s in ms),
                          "pareto_size_p50": _q([s["pareto_size"] for s in ms], 0.5)}
    out["budget_binding_by_cell"] = {}
    for nc in sorted({s["n_candidates"] for s in ms}):
        for br in sorted({s["budget_ratio"] for s in ms}):
            cell = [s for s in ms if s["n_candidates"] == nc and s["budget_ratio"] == br]
            out["budget_binding_by_cell"][f"nc{nc}|br{br}"] = {"n": len(cell), "binding": sum(s["budget_binding"] for s in cell)}
    if cfg and cfg.get("paired_contrasts"):
        out["paired_contrasts"] = paired_contrasts(main, algs, cfg["paired_contrasts"])
    return out


def paired_contrasts(main, algs, specs):
    """Для дизайна v2: пары сценариев с одинаковыми прочими факторами и seed, различающиеся одним фактором."""
    fields = ("slice", "n_candidates", "n_points", "budget_ratio", "weights", "max_selected", "radius_m", "seed")
    out = {}
    for sp in specs:
        fac, a, b = sp["factor"], sp["a"], sp["b"]
        name = f"{fac}:{a}_vs_{b}"
        out[name] = {}
        for o in OBJS:
            for alg in algs:
                rows = [r for r in main if r["objective"] == o and r["algorithm"] == alg]
                key = lambda r: tuple(r[f] for f in fields if f != fac)
                xa = {key(r): r["hit"] for r in rows if str(r[fac]) == str(a)}
                xb = {key(r): r["hit"] for r in rows if str(r[fac]) == str(b)}
                out[name][f"{alg}/{o}"] = _mcn(xa, xb)
    return out


def timing_summary(timing, scen):
    by = {s["scenario_key"]: s for s in scen}
    cols = [c for c in timing[0] if c.startswith("t_")]
    out = {}
    for an in sorted({s["analysis"] for s in scen}):
        rows = [t for t in timing if by[t["scenario_key"]]["analysis"] == an]
        groups = {}
        for t in rows:
            s = by[t["scenario_key"]]
            groups.setdefault(f"nc{s['n_candidates']}|ms{s['max_selected']}", []).append(t)
        out[an] = {g: {"n": len(v), **{c: {"p50": _q([t[c] for t in v], 0.5), "p90": _q([t[c] for t in v], 0.9),
                                            "max": max(t[c] for t in v)} for c in cols}} for g, v in sorted(groups.items())}
    return out
