#!/usr/bin/env python3
"""Таблицы для RESULTS.md из results/*.csv|json (только чтение результатов, без пересчёта задач).

Разделы:
- предрегистрированные (из summary.json);
- post-hoc (не были в config): стратификация по размеру точного плана |exact| и замеры времени.
Обоснование post-hoc: G1 и G2 гарантированно совпадают с exact при |exact| ≤ 1
(G1 первым шагом берёт лучший одиночный план по ключу; G2 в конце сравнивает с ним).
Поэтому информативны задачи с |exact| ≥ 2.
  python3 scripts/make_tables.py   -> results/tables.md, results/posthoc.json
"""
import csv, json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan.experiment import wilson, _q, OBJS  # noqa: E402

R = K / "results"


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}"


def ci(c):
    lo, hi = c["wilson95"]
    return "—" if lo is None else f"{100 * lo:.1f}–{100 * hi:.1f}"


def main():
    S = json.loads((R / "summary.json").read_text(encoding="utf-8"))
    T = json.loads((R / "timing_summary.json").read_text(encoding="utf-8"))
    runs = list(csv.DictReader(open(R / "runs.csv", encoding="utf-8")))
    main_runs = [r for r in runs if r["analysis"] == "main"]
    L = []
    A = L.append
    A("# Таблицы K09 round-8 (сгенерировано scripts/make_tables.py)\n")
    A(f"config_version={S['config_version']}, metric_version={S['metric_version']}, base_sha={S['base_sha']}, data.js sha256={S['data_sha256']}.")
    A(f"Сценариев: {S['scenarios']} (основная сетка {S['exact_plans']['scenarios']}); строк runs: {S['runs']}.")
    A("Все точки, кандидаты и стоимости synthetic. Исходные записи — реальный срез Overture или пустое synthetic-условие.\n")
    A("## 1. Предрегистрированное: основная сетка (max_selected=3, радиус 300 м), n=2430 на ячейку\n")
    A("| Алгоритм/цель | hit, % | Wilson 95% | первичная метрика равна, % | rel>0, n | rel p90 | rel max | unknown_worse | rel не определён |")
    A("|---|---|---|---|---|---|---|---|---|")
    for k in ("G1/mean", "G2/mean", "G1/minimax", "G2/minimax", "G1/coverage", "G2/coverage"):
        c = S["overall"][k]
        A(f"| {k} | {pct(c['hit_rate'])} | {ci(c)} | {pct(c['primary_equal'] / c['primary_defined'])} | {c['rel_positive_n']} | "
          f"{c['rel_p90']:.3f} | {c['rel_max']:.3f} | {c['unknown_worse']} | {c['rel_undefined']} |")
    A("\nrel — относительный разрыв: (greedy − exact) / exact для mean и minimax; (exact − greedy) / exact для covered_weight.")
    A("Значение null, если знаменатель 0. Квантили — nearest-rank.\n")
    A("### McNemar (парно по сценарию, точный биномиальный, двусторонний), hit G1 против G2\n")
    A("| Цель | только G1 | только G2 | оба | ни один | p (log10 p) |")
    A("|---|---|---|---|---|---|")
    for o in OBJS:
        m = S["g1_vs_g2_mcnemar"][o]
        A(f"| {o} | {m['G1_only_hit']} | {m['G2_only_hit']} | {m['both_hit']} | {m['both_miss']} | {m['p_exact_two_sided']:.3g} ({m['log10_p']}) |")
    A("\n## 2. Предрегистрированное: hit, % по уровням факторов\n")
    for fac in ("slice", "n_candidates", "n_points", "budget_ratio", "weights"):
        bf = S["by_factor"][fac]
        levels = list(bf["G1/mean"])
        if fac in ("n_candidates", "n_points", "budget_ratio"):
            levels.sort(key=float)
        A(f"### {fac}\n")
        A("| Алгоритм/цель | " + " | ".join(levels) + " |")
        A("|---|" + "---|" * len(levels))
        for k in ("G1/mean", "G2/mean", "G1/minimax", "G2/minimax", "G1/coverage", "G2/coverage"):
            A(f"| {k} | " + " | ".join(f"{pct(bf[k][l]['hit_rate'])} ({ci(bf[k][l])})" for l in levels) + " |")
        A("")
    A("## 3. Предрегистрированное, вторичный анализ: парный, n=30 на уровень (3 среза × 10 seeds)\n")
    A("Подвыборка: n_cand=16, n_pts=25, ratio 0.5, random_1_100.\n")
    for an, fac in (("sec_max_selected", "max_selected"), ("sec_radius", "радиус, м")):
        sec = S["secondary"][an]
        levels = sorted(sec["G1/mean"], key=float)
        A(f"### {fac}\n")
        A("| Алгоритм/цель | " + " | ".join(levels) + " |")
        A("|---|" + "---|" * len(levels))
        for k in ("G1/mean", "G2/mean", "G1/minimax", "G2/minimax", "G1/coverage", "G2/coverage"):
            A(f"| {k} | " + " | ".join(f"{pct(sec[k][l]['hit_rate'])} (rel max {sec[k][l]['rel_max']:.3f})" for l in levels) + " |")
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
        for a in ("G1", "G2"):
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
    A("\nПри |exact| ≤ 1 оба жадных алгоритма совпадают с exact (гарантия, на данных проверено assert). Ниже — только |exact| ≥ 2:\n")
    A("| Алгоритм/цель | n | hit, % | Wilson 95% | первичная метрика равна, % |")
    A("|---|---|---|---|---|")
    for k in ("G1/mean", "G2/mean", "G1/minimax", "G2/minimax", "G1/coverage", "G2/coverage"):
        c = post["nontrivial"][k]
        A(f"| {k} | {c['n']} | {pct(c['hit_rate'])} | {ci(c)} | {pct(c['primary_equal_rate'])} |")
    A("\nНетривиальные задачи по срезам, hit, %:\n")
    sls = sorted(post["nontrivial_by_slice"]["G1/mean"])
    A("| Алгоритм/цель | " + " | ".join(sls) + " |")
    A("|---|" + "---|" * len(sls))
    for k in ("G1/mean", "G2/mean", "G1/minimax", "G2/minimax", "G1/coverage", "G2/coverage"):
        d = post["nontrivial_by_slice"][k]
        A(f"| {k} | " + " | ".join(f"{pct(d[s]['hit_rate'])} (n={d[s]['n']})" if s in d else "—" for s in sls) + " |")
    A("\n## 4б. POST-HOC: структура промахов (hit=0), основная сетка\n")
    A("Сравнение промахнувшегося жадного плана с exact-планом той же цели: дешевле, меньше объектов, тот же размер.\n")
    A("| Алгоритм/цель | budget_ratio | промахов | дешевле exact | меньше объектов | тот же размер |")
    A("|---|---|---|---|---|---|")
    post["miss_structure"] = {}
    for k in ("G1/mean", "G2/mean", "G1/minimax", "G2/minimax", "G1/coverage", "G2/coverage"):
        a, o = k.split("/")
        for br in sorted({r["budget_ratio"] for r in main_runs}, key=float):
            ms_ = [r for r in main_runs if r["algorithm"] == a and r["objective"] == o and r["budget_ratio"] == br and r["hit"] == "0"]
            c = {"miss": len(ms_), "cheaper": sum(int(r["greedy_cost"]) < int(r["exact_cost"]) for r in ms_),
                 "fewer": sum(len(r["greedy_ids"].split()) < len(r["exact_ids"].split()) for r in ms_),
                 "same_size": sum(len(r["greedy_ids"].split()) == len(r["exact_ids"].split()) for r in ms_)}
            post["miss_structure"].setdefault(k, {})[br] = c
            A(f"| {k} | {br} | {c['miss']} | {c['cheaper']} | {c['fewer']} | {c['same_size']} |")
    g2 = [r for r in main_runs if r["algorithm"] == "G2"]
    post["g2_replaced_by_best_single"] = {o: sum(r["replaced_by_best_single"] == "1" for r in g2 if r["objective"] == o) for o in OBJS}
    A("\nG2 заменён лучшим одиночным кандидатом (из 2430): " + ", ".join(f"{o} {post['g2_replaced_by_best_single'][o]}" for o in OBJS) + ".")
    A("\n## 5. Время, мс (time.perf_counter, минимум из 3 повторов, медиана / p90 по сценариям)\n")
    A("Exact считает три цели за один проход; G1/G2 — одна цель за запуск. Абсолютные значения зависят от машины (results/run_meta.json).\n")
    A("| Группа | n | предвычисление | exact (3 цели) | G1 mean | G2 mean | G1 minimax | G2 minimax |")
    A("|---|---|---|---|---|---|---|---|")
    order = [("main", "nc6|ms3"), ("main", "nc10|ms3"), ("main", "nc16|ms3"), ("sec_max_selected", "nc16|ms1"),
             ("sec_max_selected", "nc16|ms2"), ("sec_max_selected", "nc16|ms5")]
    for an, g in order:
        v = T[an][g]
        f = lambda c: f"{v[c]['p50'] * 1e3:.2f} / {v[c]['p90'] * 1e3:.2f}"
        A(f"| {an} {g.replace('|', ', ')} | {v['n']} | {f('t_precompute_s')} | {f('t_exact_all3_s')} | {f('t_G1_mean_s')} | {f('t_G2_mean_s')} | "
          f"{f('t_G1_minimax_s')} | {f('t_G2_minimax_s')} |")
    (R / "tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (R / "posthoc.json").write_text(json.dumps(post, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
