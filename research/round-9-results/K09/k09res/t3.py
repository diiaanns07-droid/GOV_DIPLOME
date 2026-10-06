"""Протокол T3: генерация задач, прогон nominal/robust оракулом, агрегирование (config/t3_config.json)."""
import math, random, statistics, time
from . import resilience as RS
from k09plan.metric import dist_mm
from k09plan import suite

FAMILIES_RANDOM = ("single", "pair", "cluster")


def geometry(ctx, cfg, seed):
    """25 точек, 12 кандидатов со стоимостями, 25 весов — один раз на (город, категория, seed)."""
    base = f"{cfg['config_version']}|{ctx['city_id']}|{ctx['category']}"
    g = random.Random(f"{base}|geom|{seed}")
    w, s, e, n = ctx["bbox"]
    pt = lambda: (round(g.uniform(w, e), 6), round(g.uniform(s, n), 6))
    pts = [pt() for _ in range(25)]
    cands = []
    for _ in range(12):
        lon, lat = pt()
        cands.append((lon, lat, g.randint(100, 1000)))
    wr = random.Random(f"{base}|w|random_1_100|{seed}")
    wts = [wr.randint(1, 100) for _ in range(25)]
    return pts, cands, wts


def exclusion_cases(ctx, cfg, family, k, seed, attribute_sets):
    src = sorted(ctx["sources"], key=lambda s: s["id"])
    ids = [s["id"] for s in src]
    if family == "attribute":
        return [dict(c) for c in attribute_sets]
    if family == "all_disabled":
        return [{"id": "all", "label": "все записи категории условно исключены", "disabled_source_ids": list(ids)}]
    r = random.Random(f"{cfg['config_version']}|{ctx['city_id']}|{ctx['category']}|excl|{family}|{k}|{seed}")
    out = []
    if family == "single":
        pick = r.sample(ids, k)
        for i, s in enumerate(pick):
            out.append({"id": f"single{i}", "label": f"без одной записи ({i + 1})", "disabled_source_ids": [s]})
    elif family == "pair":
        for i in range(k):
            out.append({"id": f"pair{i}", "label": f"без двух записей ({i + 1})", "disabled_source_ids": sorted(r.sample(ids, 2))})
    elif family == "cluster":
        w, s_, e, n = ctx["bbox"]
        for i in range(k):
            alon, alat = round(r.uniform(w, e), 6), round(r.uniform(s_, n), 6)
            near = sorted(src, key=lambda x: (dist_mm(alon, alat, x["lon"], x["lat"]), x["id"]))[:3]
            out.append({"id": f"cluster{i}", "label": f"без трёх записей у точки {i + 1}", "disabled_source_ids": sorted(x["id"] for x in near)})
    else:
        raise ValueError(family)
    return out


def make_env(ctx, cfg, size, budget_ratio, max_selected, seed, cases):
    sz = cfg["sizes"][size]
    pts, cands, wts = geometry(ctx, cfg, seed)
    P = [{"id": f"p{i:02d}", "lon": pts[i][0], "lat": pts[i][1], "weight": wts[i]} for i in range(sz["n_points"])]
    C = [{"id": f"c{i:02d}", "lon": cands[i][0], "lat": cands[i][1], "category": ctx["category"], "kind": "hypothetical", "cost": cands[i][2]}
         for i in range(sz["n_candidates"])]
    top = sorted((c["cost"] for c in C), reverse=True)[:max_selected]
    plan = {"schema_version": "city-plan-v2", "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"], "category": ctx["category"],
            "control_points": P, "candidates": C, "budget": int(budget_ratio * sum(top)), "max_selected": max_selected,
            "coverage_radius_m": cfg["coverage_radius_m"], "required_ids": [], "excluded_ids": [], "selected_ids": []}
    return {"schema_version": RS.SCHEMA, "plan": plan, "cases": cases}


def task_plan(cfg, attr):
    """[(analysis, slice_id, size, family, k, budget_ratio, max_selected, seed)] в фиксированном порядке."""
    out = []
    for sl in cfg["slices"]:
        for size in cfg["sizes"]:
            for br in cfg["budget_ratio"]:
                for seed in cfg["seeds"]:
                    for fam in FAMILIES_RANDOM:
                        for k in cfg["families"][fam]["k_cases"]:
                            out.append(("main", sl["id"], size, fam, k, br, cfg["max_selected"], seed))
                    out.append(("main", sl["id"], size, "attribute", len(attr[sl["id"]]["cases"]), br, cfg["max_selected"], seed))
                    out.append(("main", sl["id"], size, "all_disabled", 1, br, cfg["max_selected"], seed))
    st = cfg["stress"]
    for sl in cfg["slices"]:
        for seed in cfg["seeds"]:
            out.append(("stress", sl["id"], st["size"], st["family"], st["k_cases"], st["budget_ratio"], st["max_selected"], seed))
    return out


def _vec(v):
    return (v["unknown_count"], v["weighted_sum_mm"], math.inf if v["max_mm"] is None else v["max_mm"])


def _timed(fn, repeats):
    best, res = None, None
    for _ in range(repeats):
        t = time.perf_counter(); res = fn(); dt = time.perf_counter() - t
        best = dt if best is None or dt < best else best
    return res, best


def run_one(ctx, cfg, attr, spec, repeats=1):
    an, sid, size, fam, k, br, ms, seed = spec
    cases = exclusion_cases(ctx, cfg, fam, k, seed, attr[sid]["cases"])
    env = RS.validate_resilience(make_env(ctx, cfg, size, br, ms, seed, cases), ctx)
    r, t = _timed(lambda: RS.optimize_resilience(ctx, env, validated=True), repeats)
    key = f"{an}|{sid}|{size}|{fam}|k{k}|br{br}|ms{ms}|s{seed}"
    tw = sum(p["weight"] for p in env["plan"]["control_points"])
    row = {"task_key": key, "analysis": an, "slice": sid, "size": size, "n_candidates": len(env["plan"]["candidates"]),
           "n_points": len(env["plan"]["control_points"]), "family": fam, "k_cases": len(cases), "budget_ratio": br, "max_selected": ms,
           "seed": seed, "budget": env["plan"]["budget"], "n_sources": len(ctx["sources"]),
           "distinct_exclusion_sets": len({tuple(c["disabled_source_ids"]) for c in cases}),
           "excluded_records_max": max(len(c["disabled_source_ids"]) for c in cases),
           "status": r["status"], "resilience_problem_digest": r["resilience_problem_digest"]}
    if r["status"] != "optimal":
        row.update({"same_plan": "", "price_m": "", "price_null_reason": r["price_null_reason"]})
        return row, t
    N, Rb = r["nominal"], r["robust"]
    Wn, Wr = _vec(N["worst_vector"]), _vec(Rb["worst_vector"])
    assert Wr <= Wn and _vec(N["base_vector"]) <= _vec(Rb["base_vector"]), key       # инварианты определения
    if Wr == Wn:
        cls = "none"
    elif Wr[0] < Wn[0]:
        cls = "unknown"
    elif Wr[1] < Wn[1]:
        cls = "wsum"
    else:
        cls = "max"
    both_known = Wn[0] == 0 and Wr[0] == 0
    row.update({
        "nominal_ids": " ".join(N["selected_ids"]), "robust_ids": " ".join(Rb["selected_ids"]), "same_plan": int(r["same_plan"]),
        "nominal_cost": N["cost"], "robust_cost": Rb["cost"],
        "nominal_W_unknown": Wn[0], "nominal_W_wsum": Wn[1], "nominal_W_max": "" if Wn[2] == math.inf else Wn[2],
        "robust_W_unknown": Wr[0], "robust_W_wsum": Wr[1], "robust_W_max": "" if Wr[2] == math.inf else Wr[2],
        "nominal_base_unknown": N["base_vector"]["unknown_count"], "nominal_base_wsum": N["base_vector"]["weighted_sum_mm"],
        "robust_base_unknown": Rb["base_vector"]["unknown_count"], "robust_base_wsum": Rb["base_vector"]["weighted_sum_mm"],
        "nominal_worst_case_ids": " ".join(N["worst_case_ids"]), "robust_worst_case_ids": " ".join(Rb["worst_case_ids"]),
        "base_in_worst_nominal": int("base" in N["worst_case_ids"]), "base_in_worst_robust": int("base" in Rb["worst_case_ids"]),
        "W_improvement": cls,
        "worst_mean_gain_m": f"{(Wn[1] - Wr[1]) / tw / 1000:.6f}" if both_known else "",
        "worst_max_gain_m": f"{(Wn[2] - Wr[2]) / 1000:.6f}" if both_known else "",
        "price_m": "" if r["price_of_robustness_m"] is None else f"{r['price_of_robustness_m']:.6f}",
        "price_null_reason": r["price_null_reason"] or "",
        "evaluated": r["evaluated"], "feasible_count": r["feasible_count"], "subsets_total": r["subsets_total"]})
    return row, t


# ---------------------------------------------------------------- статистика
def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n; den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h), 6), round(min(1.0, c + h), 6)]


def q(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[max(0, math.ceil(p * len(xs)) - 1)]


def mcnemar_log10(b, c):
    n = b + c
    if n == 0:
        return 0.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return round(min(0.0, math.log10(2 * tail) - n * math.log10(2)), 3)


def cell(rows):
    ok = [r for r in rows if r["status"] == "optimal"]
    n = len(ok)
    same = sum(r["same_plan"] for r in ok)
    price = [float(r["price_m"]) for r in ok if r["price_m"] != ""]
    pos = [p for p in price if p > 0]
    gain = [float(r["worst_mean_gain_m"]) for r in ok if r["worst_mean_gain_m"] != ""]
    gpos = [g for g in gain if g > 0]
    cls = {c: sum(1 for r in ok if r["W_improvement"] == c) for c in ("none", "unknown", "wsum", "max")}
    return {"n": len(rows), "optimal": n, "same_plan": same, "same_plan_rate": round(same / n, 6) if n else None, "same_plan_wilson95": wilson(same, n),
            "price_defined": len(price), "price_null": n - len(price), "price_zero": sum(1 for p in price if p == 0),
            "price_p50_m": q(price, 0.5), "price_p90_m": q(price, 0.9), "price_max_m": max(price) if price else None,
            "price_positive_p50_m": q(pos, 0.5),
            "W_improvement": cls,
            "worst_mean_gain_positive_n": len(gpos), "worst_mean_gain_p50_m_positive": q(gpos, 0.5), "worst_mean_gain_max_m": max(gain) if gain else None,
            "nominal_W_unknown_tasks": sum(1 for r in ok if r["nominal_W_unknown"] > 0), "robust_W_unknown_tasks": sum(1 for r in ok if r["robust_W_unknown"] > 0),
            "base_in_worst_nominal": sum(r["base_in_worst_nominal"] for r in ok), "base_in_worst_robust": sum(r["base_in_worst_robust"] for r in ok)}


def summarize(rows, cfg):
    main = [r for r in rows if r["analysis"] == "main"]
    out = {"config_version": cfg["config_version"], "tasks": len(rows), "main": cell(main), "by": {}, "paired": {}}
    for fac in ("family", "k_cases", "size", "budget_ratio", "slice"):
        levels = sorted({r[fac] for r in main}, key=lambda v: (str(type(v)), v))
        out["by"][fac] = {str(l): cell([r for r in main if r[fac] == l]) for l in levels}
    out["by"]["family_x_k"] = {f"{f}|k{k}": cell([r for r in main if r["family"] == f and r["k_cases"] == k])
                               for f in FAMILIES_RANDOM for k in cfg["families"][f]["k_cases"]}
    out["by"]["family_x_slice"] = {f"{f}|{s}": cell([r for r in main if r["family"] == f and r["slice"] == s])
                                   for f in ("single", "pair", "cluster", "attribute", "all_disabled") for s in sorted({r["slice"] for r in main})}
    # парные контрасты (одинаковая геометрия): k=1 против k=7 (случайные семейства) и бюджет 0.5 против 1.0
    def pair(rows_, fac, a, b, keyf):
        xa = {keyf(r): r["same_plan"] for r in rows_ if r[fac] == a and r["status"] == "optimal"}
        xb = {keyf(r): r["same_plan"] for r in rows_ if r[fac] == b and r["status"] == "optimal"}
        ks = sorted(set(xa) & set(xb))
        bb = sum(1 for k in ks if xa[k] and not xb[k]); cc = sum(1 for k in ks if xb[k] and not xa[k])
        return {"pairs": len(ks), "a_same_rate": round(sum(xa[k] for k in ks) / len(ks), 6) if ks else None,
                "b_same_rate": round(sum(xb[k] for k in ks) / len(ks), 6) if ks else None, "a_only": bb, "b_only": cc, "log10_p": mcnemar_log10(bb, cc)}
    rnd = [r for r in main if r["family"] in FAMILIES_RANDOM]
    for f in FAMILIES_RANDOM:
        rf = [r for r in rnd if r["family"] == f]
        out["paired"][f"{f}:k1_vs_k7"] = pair(rf, "k_cases", 1, 7, lambda r: (r["slice"], r["size"], r["budget_ratio"], r["seed"]))
    out["paired"]["budget:0.5_vs_1.0"] = pair(main, "budget_ratio", 0.5, 1.0, lambda r: (r["slice"], r["size"], r["family"], r["k_cases"], r["seed"]))
    out["stress"] = cell([r for r in rows if r["analysis"] == "stress"])
    return out


def timing_summary(timing, rows):
    by = {r["task_key"]: r for r in rows}
    groups = {}
    for key, t in timing.items():
        r = by[key]
        groups.setdefault(f"{r['analysis']}|{r['size']}|k{r['k_cases']}|ms{r['max_selected']}", []).append(t)
    return {g: {"n": len(v), "p50_ms": round(q(v, 0.5) * 1e3, 3), "p90_ms": round(q(v, 0.9) * 1e3, 3), "max_ms": round(max(v) * 1e3, 3)}
            for g, v in sorted(groups.items())}
