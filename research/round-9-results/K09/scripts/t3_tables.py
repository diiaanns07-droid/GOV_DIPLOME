#!/usr/bin/env python3
"""Таблицы T3 из results/stage3/t3_summary.json, t3_timing.json и build_compare (только чтение результатов).

  python3 scripts/t3_tables.py   -> results/stage3/t3_tables.md
"""
import json
from pathlib import Path

K = Path(__file__).resolve().parents[1]
R = K / "results/stage3"


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}"


def m(x, f=".1f"):
    return "—" if x is None else format(x, f)


def row(name, c):
    lo, hi = c["same_plan_wilson95"]
    W = c["W_improvement"]
    name = str(name).replace("|", " · ")
    return (f"| {name} | {c['optimal']} | {pct(c['same_plan_rate'])} ({pct(lo)}–{pct(hi)}) | {c['price_zero']}/{c['price_defined']} | "
            f"{m(c['price_p90_m'])} | {m(c['price_max_m'])} | {m(c['price_positive_p50_m'])} | {W['none']}/{W['unknown']}/{W['wsum']}/{W['max']} | "
            f"{m(c['worst_mean_gain_p50_m_positive'])} | {c['nominal_W_unknown_tasks']}/{c['robust_W_unknown_tasks']} | {c['base_in_worst_nominal']} | "
            f"{c.get('all_cases_noop_tasks', '—')} | {pct(c.get('nontrivial_same_rate'))} | {c.get('worst_ties_nominal', '—')} |")


HEAD = ("| Группа | задач | same_plan, % (Wilson 95%, задачи как независимые) | цена = 0 / определена | цена p90, м | цена max, м | цена p50 среди >0, м | W: нет/unknown/wsum/max | выигрыш W p50 среди >0, м | W.unknown>0: nominal/robust | есть случай без влияния (base среди худших, nominal) | все случаи без влияния | same_plan на нетривиальных, % | ничьи W (nominal) |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def main():
    S = json.loads((R / "t3_summary.json").read_text(encoding="utf-8"))
    T = json.loads((R / "t3_timing.json").read_text(encoding="utf-8"))["by_group"]
    B = json.loads((R / "build_compare_33cc635.json").read_text(encoding="utf-8"))
    B2 = json.loads((R / "build_compare_d18847f.json").read_text(encoding="utf-8")) if (R / "build_compare_d18847f.json").exists() else None
    L = ["# Таблицы T3 (сгенерировано scripts/t3_tables.py из results/stage3)\n",
         f"config_version={S['config_version']}; задач {S['tasks']} (основная сетка {S['main']['n']}, stress {S['stress']['n']}).",
         "Цена — (mean_base(robust) − mean_base(nominal))/1000 м. Выигрыш W — (W_nominal.wsum − W_robust.wsum)/сумма весов/1000 м, только при unknown = 0 у обоих.",
         "Квантили — nearest-rank. Все точки, кандидаты, стоимости и исключения synthetic/hypothetical, исходные записи — observed_secondary.\n",
         "## 1. Основная сетка\n", HEAD, row("все (main)", S["main"])]
    for fac, title in (("family_group", "Группа семейств"), ("family", "Семейство"), ("family_x_k", "Семейство × k"),
                       ("k_cases_random_families", "Число случаев k — только случайные семейства (single, pair, cluster)"),
                       ("k_cases", "Число случаев k — СМЕШАННО (k=1 включает all_disabled и attribute astana; не для выводов о k)"), ("size", "Размер"),
                       ("budget_ratio", "Бюджет"), ("slice", "Срез"), ("family_x_slice", "Семейство × срез")):
        L += [f"\n## {title}\n", HEAD] + [row(k, c) for k, c in S["by"][fac].items()]
    L += ["\n## Парные контрасты same_plan (одинаковая геометрия)\n",
          "McNemar (предрегистрирован) считает пары независимыми и поэтому завышает значимость. Sign-flip — точный тест по 20 независимым геометриям (срез × seed), добавлен после обзора.\n",
          "| Контраст | пар | same a, % | same b, % | только a / только b | McNemar log10 p | sign-flip p (20 геометрий) |", "|---|---|---|---|---|---|---|"]
    for k, v in S["paired"].items():
        sf = v.get("sign_flip_over_geometries")
        L.append(f"| {k} | {v['pairs']} | {pct(v['a_same_rate'])} | {pct(v['b_same_rate'])} | {v['a_only']} / {v['b_only']} | {v['log10_p']} | "
                 + ("—" if not sf else f"{sf['p_exact_two_sided']:.4g}") + " |")
    CI = S.get("cluster_inference")
    if CI:
        L += ["\n## Доля same_plan с учётом зависимости задач (после обзора)\n", CI["note"] + ".\n",
              "| Группа | доля | 95% кластерный бутстрэп (10000, по геометриям) | доли по геометриям min–max |", "|---|---|---|---|"]
        for k, v in CI.items():
            if isinstance(v, dict):
                L.append(f"| {k.replace('same_plan_', '')} | {pct(v['rate'])} | {pct(v['ci95'][0])}–{pct(v['ci95'][1])} | {pct(v['cluster_rates_min_max'][0])}–{pct(v['cluster_rates_min_max'][1])} |")
    L += ["\n## Stress (12 кандидатов × 25 точек × 8 случаев, max_selected = 5)\n", HEAD, row("stress", S["stress"])]
    # дополнительно (НЕ предрегистрировано, описательно): стоимость устойчивости в условных единицах, когда планы различаются
    import csv
    rows = [r for r in csv.DictReader(open(R / "t3_runs.csv", encoding="utf-8")) if r["analysis"] == "main" and r["status"] == "optimal"]
    diff = [r for r in rows if r["same_plan"] == "0"]
    zero_price = [r for r in diff if float(r["price_m"]) == 0.0]
    dc = sorted(int(r["robust_cost"]) - int(r["nominal_cost"]) for r in diff)
    import math
    qq = lambda v, p: v[max(0, math.ceil(p * len(v)) - 1)] if v else None   # nearest-rank
    L += ["\n## Дополнительно (не предрегистрировано): различающиеся планы\n",
          f"Планы различаются в {len(diff)} из {len(rows)} задач основной сетки; из них цена в расстоянии на base = 0 в {len(zero_price)} "
          f"(при той же взвешенной сумме расстояний на base устойчивый план отличается составом и стоимостью).",
          f"Разница стоимости robust − nominal (усл. ед.) среди различающихся: min {dc[0]}, p50 {qq(dc, 0.5)}, p90 {qq(dc, 0.9)}, max {dc[-1]}; "
          f"robust дороже в {sum(1 for x in dc if x > 0)}, дешевле в {sum(1 for x in dc if x < 0)}, равная в {sum(1 for x in dc if x == 0)}."]
    L += ["\n## Время, мс (медиана / p90 / max)\n", "| Группа | n | оракул K09 (Python, минимум из 3) | BUILD 33cc635 (Node, минимум из 3) | BUILD d18847f (Node, минимум из 3) |", "|---|---|---|---|---|"]
    bt = B["build_optimize_ms"]
    for g, v in T.items():
        an, size, k, ms = g.split("|")
        cases = int(k[1:]) + 1
        b = bt.get(f"{an}|{size}|cases{cases}")
        b2 = B2["build_optimize_ms"].get(f"{an}|{size}|cases{cases}") if B2 else None
        L.append(f"| {an} {size} k={k[1:]} (случаев: {cases}) {ms} | {v['n']} | {v['p50_ms']} / {v['p90_ms']} / {v['max_ms']} | "
                 + ("—" if not b else f"{b['p50']} / {b['p90']} / {b['max']}") + " | " + ("—" if not b2 else f"{b2['p50']} / {b2['p90']} / {b2['max']}") + " |")
    L += ["\nВремя оракула и BUILD измерено на одной машине (Linux x64, 4 CPU) и машинно-зависимо. Браузер и Web Worker не измерялись.",
          "\nN.B. для k: в группу k=1 входят и all_disabled (1 случай), и attribute для astana (1 случай); чистые сравнения по k — в таблице «Семейство × k» и в парных контрастах."]
    (R / "t3_tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    main()
