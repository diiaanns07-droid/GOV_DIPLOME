#!/usr/bin/env python3
"""Таблицы для RESULTS.md из <results>/*.csv|json (только чтение результатов, без пересчёта задач).

  python3 scripts/make_tables.py               # v1: results/tables.md, results/posthoc.json
  python3 scripts/make_tables.py results_v2    # v2: results_v2/tables.md, results_v2/posthoc.json

Разделы: предрегистрированные (из summary.json) и post-hoc (стратификация по размеру точного плана,
структура промахов, время). Обоснование post-hoc §4: G1 и G2 гарантированно совпадают с exact при |exact| ≤ 1
(required пуст): G1 первым шагом берёт лучший одиночный план по ключу; G2 в конце сравнивает с ним.
"""
import csv, json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan.experiment import wilson, OBJS  # noqa: E402


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}"


def ci(c):
    lo, hi = c["wilson95"]
    return "—" if lo is None else f"{100 * lo:.1f}–{100 * hi:.1f}"


def num(x, f=".3f"):
    return "—" if x is None else format(x, f)


def main():
    R = K / (sys.argv[1] if len(sys.argv) > 1 else "results")
    S = json.loads((R / "summary.json").read_text(encoding="utf-8"))
    T = json.loads((R / "timing_summary.json").read_text(encoding="utf-8"))
    runs = list(csv.DictReader(open(R / "runs.csv", encoding="utf-8")))
    main_runs = [r for r in runs if r["analysis"] == "main"]
    algs = S["algorithms"]
    KEYS = [f"{a}/{o}" for o in OBJS for a in algs]
    v2 = S.get("design") == "v2"
    L = []
    A = L.append
    A(f"# Таблицы K09 round-8, дизайн {S.get('design', 'v1')} (сгенерировано scripts/make_tables.py)\n")
    A(f"config_version={S['config_version']}, metric_version={S['metric_version']}, base_sha={S['base_sha']}, data.js sha256={S['data_sha256']}.")
    A(f"Сценариев: {S['scenarios']} (основная сетка {S['exact_plans']['scenarios']}); строк runs: {S['runs']}.")
    A(f"Бюджет ограничивает (feasible_count меньше, чем без бюджета) в {S['exact_plans']['budget_binding_scenarios']} из {S['exact_plans']['scenarios']} задач основной сетки.")
    A("Все точки, кандидаты и стоимости synthetic. Исходные записи — реальный срез Overture или пустое synthetic-условие.\n")
    n_main = S["exact_plans"]["scenarios"]
    A(f"## 1. Основная сетка (max_selected=3, радиус 300 м), n={n_main} на ячейку\n")
    A("| Алгоритм/цель | hit, % | Wilson 95% | первичная метрика равна, % | rel>0, n | rel p90 (все) | rel p90 (rel>0) | rel max | rel не определён |")
    A("|---|---|---|---|---|---|---|---|---|")
    for k in KEYS:
        c = S["overall"][k]
        A(f"| {k} | {pct(c['hit_rate'])} | {ci(c)} | {pct(c['primary_equal'] / c['primary_defined'])} | {c['rel_positive_n']} | "
          f"{num(c['rel_p90'])} | {num(c.get('rel_positive_p90'))} | {num(c['rel_max'])} | {c['rel_undefined']} |")
    A("\nrel — относительный разрыв:")
    A("- (greedy − exact) / exact для mean и minimax;")
    A("- (exact − greedy) / exact для covered_weight;")
    A("- null, если знаменатель равен 0.")
    A("\n«rel p90 (все)» считается по всем задачам, включая совпадения (rel = 0); «rel p90 (rel>0)» — только по промахам с разрывом. Квантили — nearest-rank.")
    A("unknown_worse = 0 во всех строках. В этом дизайне это гарантировано: любой кандидат делает все точки известными, а оба жадных алгоритма добавляют объект, пока есть unknown и доступный кандидат.\n")
    A("### McNemar G1 против G2 (парно по сценарию, точный биномиальный, двусторонний)\n")
    A("| Цель | hit: только G1 / только G2 | log10 p | первичная метрика: только G1 / только G2 | log10 p |")
    A("|---|---|---|---|---|")
    for o in OBJS:
        m, q = S["g1_vs_g2_mcnemar"][o], S["g1_vs_g2_mcnemar_primary"][o]
        A(f"| {o} | {m['G1_only_hit']} / {m['G2_only_hit']} | {m['log10_p']} | {q['a_only']} / {q['b_only']} | {q['log10_p']} |")
    if "g2_vs_g2id_mcnemar" in S:
        A("\n### G2 (ничья по снижению unknown: стоимость, затем id) против G2id (только id)\n")
        A("| Цель | hit G2, % | hit G2id, % | только G2 / только G2id | log10 p |")
        A("|---|---|---|---|---|")
        for o in OBJS:
            m = S["g2_vs_g2id_mcnemar"][o]
            A(f"| {o} | {pct(m['a_rate'])} | {pct(m['b_rate'])} | {m['a_only']} / {m['b_only']} | {m['log10_p']} |")
    A("\n## 2. hit, % по уровням факторов (Wilson 95%)\n")
    if not v2:
        A("В v1 геометрия различается между уровнями (seed-строка включает все факторы), поэтому сравнения уровней непарные.\n")
    for fac in ("slice", "n_candidates", "n_points", "budget_ratio", "weights"):
        bf = S["by_factor"][fac]
        levels = list(bf[KEYS[0]])
        if fac in ("n_candidates", "n_points", "budget_ratio"):
            levels.sort(key=float)
        A(f"### {fac}\n")
        A("| Алгоритм/цель | " + " | ".join(levels) + " |")
        A("|---|" + "---|" * len(levels))
        for k in KEYS:
            A(f"| {k} | " + " | ".join(f"{pct(bf[k][l]['hit_rate'])} ({ci(bf[k][l])})" for l in levels) + " |")
        A("")
    A("### Ограничивает ли бюджет (доля задач по ячейкам n_candidates × budget_ratio)\n")
    A("| Ячейка | ограничивает / всего |")
    A("|---|---|")
    for cell, v in S["budget_binding_by_cell"].items():
        A(f"| {cell.replace('|', ', ')} | {v['binding']} / {v['n']} |")
    A("\n### hit, % по признаку «бюджет ограничивает» (0 — нет, 1 — да)\n")
    A("| Алгоритм/цель | не ограничивает | ограничивает |")
    A("|---|---|---|")
    for k in KEYS:
        d = S["by_budget_binding"][k]
        A(f"| {k} | " + " | ".join(f"{pct(d[b]['hit_rate'])} (n={d[b]['n']})" if b in d else "—" for b in ("0", "1")) + " |")
    if "paired_contrasts" in S:
        A("\n### Парные контрасты v2 (одинаковые геометрия, веса и seed; различается один фактор)\n")
        A("| Контраст | Алгоритм/цель | пар | hit a, % | hit b, % | только a / только b | log10 p |")
        A("|---|---|---|---|---|---|---|")
        for cn, d in S["paired_contrasts"].items():
            for k in KEYS:
                m = d[k]
                A(f"| {cn} | {k} | {m['pairs']} | {pct(m['a_rate'])} | {pct(m['b_rate'])} | {m['a_only']} / {m['b_only']} | {m['log10_p']} |")
    A("\n## 3. Вторичный анализ: парный, n=30 на уровень (3 среза × 10 seeds)\n")
    A("Подвыборка: n_cand=16, n_pts=25, ratio 0.5, random_1_100." + (" Бюджет считается по max_selected=3 и при изменении max_selected не меняется." if v2 else "") + "\n")
    for an, fac in (("sec_max_selected", "max_selected"), ("sec_radius", "радиус, м")):
        sec = S["secondary"][an]
        levels = sorted(sec[KEYS[0]], key=float)
        A(f"### {fac}\n")
        A("| Алгоритм/цель | " + " | ".join(levels) + " |")
        A("|---|" + "---|" * len(levels))
        for k in KEYS:
            A(f"| {k} | " + " | ".join(f"{pct(sec[k][l]['hit_rate'])} (rel max {num(sec[k][l]['rel_max'])})" for l in levels) + " |")
        A("")
    # ---------- post-hoc ----------
    post = {"size_distribution": {}, "nontrivial": {}, "nontrivial_by_slice": {}}
    for o in OBJS:
        g1 = [r for r in main_runs if r["objective"] == o and r["algorithm"] == "G1"]
        dist = {}
        for r in g1:
            n = len(r["exact_ids"].split())
            dist[n] = dist.get(n, 0) + 1
        post["size_distribution"][o] = {str(k): dist[k] for k in sorted(dist)}
        for a in algs:
            rows = [r for r in main_runs if r["objective"] == o and r["algorithm"] == a]
            small = [r for r in rows if len(r["exact_ids"].split()) <= 1]
            assert all(r["hit"] == "1" for r in small), (o, a)   # теоретическая гарантия, проверяется на данных
            nt = [r for r in rows if len(r["exact_ids"].split()) >= 2]
            h = sum(r["hit"] == "1" for r in nt)
            pe = [r for r in nt if r["primary_equal"] != ""]
            post["nontrivial"][f"{a}/{o}"] = {"n": len(nt), "hits": h, "hit_rate": round(h / len(nt), 6) if nt else None,
                                              "wilson95": list(wilson(h, len(nt))),
                                              "primary_equal_rate": round(sum(r["primary_equal"] == "1" for r in pe) / len(pe), 6) if pe else None,
                                              "small_exact_all_hit": len(small)}
            for sl in sorted({r["slice"] for r in nt}):
                ns = [r for r in nt if r["slice"] == sl]
                hs = sum(r["hit"] == "1" for r in ns)
                post["nontrivial_by_slice"].setdefault(f"{a}/{o}", {})[sl] = {"n": len(ns), "hit_rate": round(hs / len(ns), 6),
                                                                             "wilson95": list(wilson(hs, len(ns)))}
    A("## 4. POST-HOC (не предрегистрировано): размер точного плана и нетривиальные задачи\n")
    A("Распределение размера точного плана (число выбранных кандидатов), основная сетка:\n")
    A("| Цель | " + " | ".join(f"размер {k}" for k in range(4)) + " |")
    A("|---|---|---|---|---|")
    for o in OBJS:
        d = post["size_distribution"][o]
        A(f"| {o} | " + " | ".join(str(d.get(str(k), 0)) for k in range(4)) + " |")
    A("\nПри размере точного плана ≤ 1 все жадные варианты совпадают с exact (гарантия; на данных проверено assert). Ниже — только задачи с размером ≥ 2:\n")
    A("| Алгоритм/цель | n | hit, % | Wilson 95% | первичная метрика равна, % |")
    A("|---|---|---|---|---|")
    for k in KEYS:
        c = post["nontrivial"][k]
        A(f"| {k} | {c['n']} | {pct(c['hit_rate'])} | {ci(c)} | {pct(c['primary_equal_rate'])} |")
    A("\nНетривиальные задачи по срезам, hit, %:\n")
    sls = sorted(post["nontrivial_by_slice"][KEYS[0]])
    A("| Алгоритм/цель | " + " | ".join(sls) + " |")
    A("|---|" + "---|" * len(sls))
    for k in KEYS:
        d = post["nontrivial_by_slice"][k]
        A(f"| {k} | " + " | ".join(f"{pct(d[s]['hit_rate'])} (n={d[s]['n']})" if s in d else "—" for s in sls) + " |")
    A("\n## 4б. POST-HOC: структура промахов (hit=0), основная сетка\n")
    A("Сравнение промахнувшегося жадного плана с exact-планом той же цели: дешевле, меньше объектов, тот же размер, больше объектов.\n")
    A("| Алгоритм/цель | budget_ratio | промахов | дешевле exact | меньше объектов | тот же размер | больше объектов |")
    A("|---|---|---|---|---|---|---|")
    post["miss_structure"] = {}
    for k in KEYS:
        a, o = k.split("/")
        for br in sorted({r["budget_ratio"] for r in main_runs}, key=float):
            ms_ = [r for r in main_runs if r["algorithm"] == a and r["objective"] == o and r["budget_ratio"] == br and r["hit"] == "0"]
            sz = lambda r: (len(r["greedy_ids"].split()), len(r["exact_ids"].split()))
            c = {"miss": len(ms_), "cheaper": sum(int(r["greedy_cost"]) < int(r["exact_cost"]) for r in ms_),
                 "fewer": sum(sz(r)[0] < sz(r)[1] for r in ms_), "same_size": sum(sz(r)[0] == sz(r)[1] for r in ms_),
                 "more": sum(sz(r)[0] > sz(r)[1] for r in ms_)}
            post["miss_structure"].setdefault(k, {})[br] = c
            A(f"| {k} | {br} | {c['miss']} | {c['cheaper']} | {c['fewer']} | {c['same_size']} | {c['more']} |")
    post["replaced_by_best_single"] = {}
    for a in algs:
        if a == "G1":
            continue
        g = [r for r in main_runs if r["algorithm"] == a]
        post["replaced_by_best_single"][a] = {o: sum(r["replaced_by_best_single"] == "1" for r in g if r["objective"] == o) for o in OBJS}
        A(f"\n{a} заменён лучшим одиночным кандидатом (из {n_main}): " + ", ".join(f"{o} {post['replaced_by_best_single'][a][o]}" for o in OBJS) + ".")
    A("\n## 5. Время, мс (time.perf_counter, минимум из 3 повторов, медиана / p90 по сценариям)\n")
    A("Exact считает три цели за один проход, без Парето. «Полный выход» — exact с Парето плюс чувствительность к бюджету (три дополнительных перебора), то есть то, что требует CORE_SPEC optimizePlans. G1/G2 — одна цель за запуск.")
    A("Абсолютные значения зависят от машины (run_meta.json).\n")
    hdr = "| Группа | n | предвычисление | exact (3 цели) | полный выход | " + " | ".join(f"{a} mean" for a in algs) + " | " + " | ".join(f"{a} minimax" for a in algs) + " |"
    A(hdr)
    A("|---|" + "---|" * (hdr.count("|") - 2))
    order = [("main", "nc6|ms3"), ("main", "nc10|ms3"), ("main", "nc16|ms3"), ("sec_max_selected", "nc16|ms1"),
             ("sec_max_selected", "nc16|ms2"), ("sec_max_selected", "nc16|ms5")]
    for an, g in order:
        v = T[an][g]
        f = lambda c: f"{v[c]['p50'] * 1e3:.2f} / {v[c]['p90'] * 1e3:.2f}" if c in v else "—"
        A(f"| {an} {g.replace('|', ', ')} | {v['n']} | {f('t_precompute_s')} | {f('t_exact_all3_s')} | {f('t_exact_full_output_s')} | "
          + " | ".join(f(f"t_{a}_mean_s") for a in algs) + " | " + " | ".join(f(f"t_{a}_minimax_s") for a in algs) + " |")
    (R / "tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (R / "posthoc.json").write_text(json.dumps(post, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
