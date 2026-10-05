#!/usr/bin/env python3
"""A02 — изолированный эксперимент. ВСЕ ДАННЫЕ SYNTHETIC.

Проверяемое предположение (методическое, не про Шымкент):
  «Прозрачная оценка LoF x CoF даёт ранжирование, заметно отличающееся от правила
   "сначала самый старый", и это различие зависит от (а) того, что реально вызывает аварии,
   (б) целевой функции (число аварий или последствия), (в) пропусков и смещения данных».

Эксперимент НЕ доказывает пользу в Шымкенте: генеративная модель придумана нами,
поэтому любые цифры ниже описывают только поведение метода в заданных мирах.

Запуск:  python3 A02_priority_experiment.py  [--reps 200] [--out results.json]
Зависимости: только numpy.
"""
import argparse, json, platform, sys
import numpy as np

N = 400                    # сегментов/участков (synthetic)
MAT_NAMES = ["steel_or_cast_iron", "asbestos_cement", "polyethylene"]
MAT_SCORE = np.array([1.0, 0.7, 0.1])          # экспертная шкала риска материала (допущение)
REPORT_BY_DISTRICT = np.array([0.5, 0.8, 1.0, 1.0, 1.2])  # склонность жаловаться (допущение)

DEFAULT_W_LOF = {"age": 0.35, "material": 0.25, "complaints": 0.25, "pressure": 0.15}


def pct(x):
    """Перцентильный ранг 0..1 (устойчив к выбросам, единицы не важны)."""
    order = np.argsort(np.argsort(x, kind="stable"), kind="stable")
    return order / max(len(x) - 1, 1)


def generate(rng, world):
    n = N
    district = rng.integers(0, 5, n)
    material = rng.choice(3, n, p=[0.35, 0.25, 0.40])
    age = np.where(material == 2, rng.uniform(0, 25, n), rng.uniform(5, 60, n))
    high_pressure = rng.random(n) < 0.3
    length = rng.uniform(0.1, 2.0, n)                       # км
    pop = rng.lognormal(np.log(1500), 0.8, n)               # жителей в зоне влияния
    critical = rng.random(n) < 0.12                          # больница/школа/детсад в зоне
    if world == "W1_age_dominated":
        f = np.exp(age / 12.0)
    elif world == "W2_mixed_drivers":
        f = np.exp(age / 40.0) * np.array([3.0, 2.0, 0.5])[material] * np.where(high_pressure, 2.5, 1.0)
    else:
        raise ValueError(world)
    lam = f * (0.08 / f.mean())                             # аварий на км в год, среднее 0.08
    exp_fail = lam * length                                  # ожидаемое число аварий в год
    cons = pop / 1000.0 * (1 + 2 * critical)                 # условная тяжесть последствий
    complaints = rng.poisson(exp_fail * REPORT_BY_DISTRICT[district] * 20 + 0.3)
    return dict(district=district, material=material, age=age, high_pressure=high_pressure,
                length=length, pop=pop, critical=critical, exp_fail=exp_fail,
                true_risk=exp_fail * cons, complaints=complaints.astype(float))


def score(d, w=None, use=("age", "material", "complaints", "pressure"), age_known=None,
          unknown_policy="median"):
    """Прозрачная оценка: LoF (взвешенная сумма 0..1) x CoF (0.2..1). Возвращает score и вклады."""
    w = dict(DEFAULT_W_LOF if w is None else w)
    for k in list(w):
        if k not in use:
            w.pop(k)
    tot = sum(w.values())
    w = {k: v / tot for k, v in w.items()}
    age = d["age"].copy()
    unknown = np.zeros(N, bool) if age_known is None else ~age_known
    if unknown.any():
        age[unknown] = np.median(age[~unknown])
    parts = {
        "age": pct(age),
        "material": MAT_SCORE[d["material"]],
        "complaints": pct(d["complaints"] / d["length"]),
        "pressure": d["high_pressure"].astype(float),
    }
    contrib = {k: w[k] * parts[k] for k in w}
    lof = sum(contrib.values())
    if unknown_policy == "inspect_bonus" and unknown.any():
        lof = lof + 0.15 * unknown          # неизвестный возраст = повод обследовать
    cof = 0.2 + 0.8 * (0.6 * pct(d["pop"]) + 0.4 * d["critical"])
    return lof * cof, contrib, cof


def top(order_key, k):
    return np.argsort(-order_key, kind="stable")[:k]


def evaluate(d, sel, k):
    o_risk = np.sort(d["true_risk"])[::-1][:k].sum()
    o_fail = np.sort(d["exp_fail"])[::-1][:k].sum()
    return d["true_risk"][sel].sum() / o_risk, d["exp_fail"][sel].sum() / o_fail


def run(reps, seed=20261004):
    rng = np.random.default_rng(seed)
    results = {}
    for world in ("W1_age_dominated", "W2_mixed_drivers"):
        acc = {}
        def add(name, val):
            acc.setdefault(name, []).append(val)
        stab = []
        for _ in range(reps):
            d = generate(rng, world)
            k = N // 10
            age_ord = d["age"]
            pols = {
                "random": rng.permutation(N)[:k],
                "oldest_first": top(age_ord, k),
                "score_operator_data": top(score(d)[0], k),
                "score_open_proxies_only": top(score(d, use=("complaints",))[0], k),
            }
            for p, sel in pols.items():
                r, f = evaluate(d, sel, k)
                add(f"base|{p}|risk", r); add(f"base|{p}|failures", f)
            # R2: ресурс обследований урезан вдвое
            k2 = k // 2
            for p, key in {"oldest_first": age_ord, "score_operator_data": score(d)[0]}.items():
                r, f = evaluate(d, top(key, k2), k2)
                add(f"R2_capacity_half|{p}|risk", r); add(f"R2_capacity_half|{p}|failures", f)
            # R1: ложный всплеск жалоб в районе 4 (кампания/соцсети), риск не изменился
            d1 = dict(d); d1["complaints"] = np.where(d["district"] == 4, d["complaints"] * 3, d["complaints"])
            s0, s1 = score(d)[0], score(d1)[0]
            r, f = evaluate(d, top(s1, k), k)
            add("R1_false_complaint_surge|score_operator_data|risk", r)
            add("R1_false_complaint_surge|score_operator_data|failures", f)
            add("R1_false_complaint_surge|top_overlap_with_base", len(set(top(s0, k)) & set(top(s1, k))) / k)
            add("R1_false_complaint_surge|share_top_from_district4",
                float(np.mean(d["district"][top(s1, k)] == 4)))
            # R3: 40% возраста неизвестно
            known = rng.random(N) > 0.4
            age_imp = d["age"].copy(); age_imp[~known] = np.median(d["age"][known])
            for p, key in {
                "oldest_first_median_imputed": age_imp,
                "score_median_imputed": score(d, age_known=known)[0],
                "score_inspect_bonus": score(d, age_known=known, unknown_policy="inspect_bonus")[0],
            }.items():
                r, f = evaluate(d, top(key, k), k)
                add(f"R3_age_40pct_unknown|{p}|risk", r); add(f"R3_age_40pct_unknown|{p}|failures", f)
            # устойчивость к весам: Дирихле вокруг весов по умолчанию
            base_top = set(top(score(d)[0], k))
            alpha = np.array(list(DEFAULT_W_LOF.values())) * 20
            ov = []
            for _ in range(20):
                ww = dict(zip(DEFAULT_W_LOF, rng.dirichlet(alpha)))
                ov.append(len(base_top & set(top(score(d, w=ww)[0], k))) / k)
            stab.append(np.mean(ov))
        res = {key: {"mean": round(float(np.mean(v)), 3), "sd": round(float(np.std(v)), 3)} for key, v in acc.items()}
        res["weight_perturbation|mean_top10pct_overlap"] = {"mean": round(float(np.mean(stab)), 3),
                                                             "sd": round(float(np.std(stab)), 3)}
        results[world] = res
    # пример объяснения для 5 верхних позиций (один прогон, W2)
    d = generate(np.random.default_rng(seed + 1), "W2_mixed_drivers")
    s, contrib, cof = score(d)
    expl = []
    for i in top(s, 5):
        c = {k: round(float(v[i]), 3) for k, v in contrib.items()}
        expl.append({"segment": f"SYN-{i:04d}", "score": round(float(s[i]), 3), "lof_contrib": c,
                     "cof": round(float(cof[i]), 3), "age_years": round(float(d["age"][i]), 1),
                     "material": MAT_NAMES[d["material"][i]], "critical_in_zone": bool(d["critical"][i]),
                     "main_driver": max(c, key=c.get)})
    return results, expl, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--out", default="A02_experiment_results.json")
    ap.add_argument("--sample-csv", default="A02_synthetic_segments_sample.csv")
    a = ap.parse_args()
    results, expl, d = run(a.reps)
    meta = {"kind": "synthetic", "python": sys.version.split()[0], "numpy": np.__version__,
            "platform": platform.platform(), "N_segments": N, "reps": a.reps, "seed": 20261004,
            "k": "top 10% (40 of 400); R2 uses 20",
            "metrics": {"risk": "доля ожидаемого риска (аварии x последствия) в выбранных, нормированная на оракула",
                        "failures": "доля ожидаемого числа аварий в выбранных, нормированная на оракула"},
            "warning": "Генеративная модель выдумана. Цифры не являются оценкой эффекта в Шымкенте."}
    json.dump({"meta": meta, "results": results, "explanation_example": expl},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(a.sample_csv, "w", encoding="utf-8") as f:
        f.write("segment_id,kind,district_idx,material,age_years,high_pressure,length_km,pop_in_zone,critical_in_zone,complaints_12m\n")
        for i in range(20):
            f.write(f"SYN-{i:04d},synthetic,{d['district'][i]},{MAT_NAMES[d['material'][i]]},{d['age'][i]:.1f},"
                    f"{int(d['high_pressure'][i])},{d['length'][i]:.2f},{d['pop'][i]:.0f},{int(d['critical'][i])},"
                    f"{int(d['complaints'][i])}\n")
    for w, r in results.items():
        print(f"\n== {w}")
        for key in sorted(r):
            print(f"  {key:70s} {r[key]['mean']:.3f} ± {r[key]['sd']:.3f}")
    print("\nTop-5 explanation (W2, synthetic):")
    for e in expl:
        print(" ", e)


if __name__ == "__main__":
    main()
