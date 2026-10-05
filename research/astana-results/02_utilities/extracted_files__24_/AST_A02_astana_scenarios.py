#!/usr/bin/env python3
"""AST-A02 — изолированный эксперимент для Астаны. ВСЕ ДАННЫЕ SYNTHETIC.

Общий код: функции pct/score/top/evaluate импортируются без изменений из
A02_priority_experiment.py (первый проход, Шымкент). Отдельно для города задаются
только генератор синтетического мира и параметры сценариев.

Три сценария, привязанные к вопросам прохода по Астане (не к найденным фактам о проблемах):
  RA1 «Новые территории»: жалобы в молодых зонах вызваны хроническим дефицитом
      (давление/подключение), а не износом. Что будет, если не разделять классы событий?
  RA2 «Отопительный сезон»: последствия отказа теплосети зимой в k раз тяжелее.
      k неизвестен. Сколько теряет совместный план вода+тепло при неверном k?
  RA3 «Смена границ (новый район без истории)»: у одного из 6 районов нет истории
      сигналов. Что даёт «пропуск = 0» по сравнению с явной обработкой пропуска?

Запуск: python3 AST_A02_astana_scenarios.py [--reps 200]
Зависимости: numpy; файл A02_priority_experiment.py в той же папке.
"""
import argparse, json, platform, sys
import numpy as np
from A02_priority_experiment import pct, score, top, evaluate, N  # общий код, без изменений

NEW_DISTRICT = 5  # индекс синтетического «нового района» (аналог ситуации с Сарайшыком)


def gen_astana(rng, new_frac=0.15, heat_frac=0.5):
    n = N
    district = rng.integers(0, 6, n)
    heat = rng.random(n) < heat_frac
    new = rng.random(n) < new_frac
    material = rng.choice(3, n, p=[0.35, 0.25, 0.40])
    material[new] = 2
    age = np.where(material == 2, rng.uniform(0, 25, n), rng.uniform(5, 60, n))
    age[new] = rng.uniform(0, 8, new.sum())
    high_pressure = rng.random(n) < 0.3
    length = rng.uniform(0.1, 2.0, n)
    pop = rng.lognormal(np.log(1500), 0.8, n)
    critical = rng.random(n) < 0.12
    f = np.exp(age / 40.0) * np.array([3.0, 2.0, 0.5])[material] * np.where(high_pressure, 2.5, 1.0)
    lam = f * (0.08 / f.mean())
    exp_fail = lam * length
    failure_signals = rng.poisson(exp_fail * 20 + 0.3).astype(float)
    deficit_signals = np.where(new, rng.poisson(8, n), 0).astype(float)
    cons = pop / 1000.0 * (1 + 2 * critical)
    return dict(district=district, heat=heat, new=new, material=material, age=age,
                high_pressure=high_pressure, length=length, pop=pop, critical=critical,
                exp_fail=exp_fail, cons=cons, failure_signals=failure_signals,
                deficit_signals=deficit_signals, true_risk=exp_fail * cons,
                complaints=failure_signals + deficit_signals)


def ra1(rng, acc, k):
    d = gen_astana(rng)
    variants = {
        "mixed_signals": d["failure_signals"] + d["deficit_signals"],
        "separated_perfect": d["failure_signals"],
        # классификатор ошибается: 30% «дефицитных» сигналов попадают в очередь износа
        "separated_70pct": d["failure_signals"] + rng.binomial(d["deficit_signals"].astype(int), 0.3),
    }
    for name, sig in variants.items():
        dd = dict(d); dd["complaints"] = sig
        # operator_data: возраст, материал, давление, сигналы; open_only: только сигналы (уровень A)
        for mode, use in {"operator_data": ("age", "material", "complaints", "pressure"),
                          "open_only": ("complaints",)}.items():
            sel = top(score(dd, use=use)[0], k)
            r, f = evaluate(d, sel, k)
            acc.setdefault(f"RA1|{mode}|{name}|risk", []).append(r)
            acc.setdefault(f"RA1|{mode}|{name}|share_top_new_territory", []).append(float(d["new"][sel].mean()))
    sel = top(d["age"], k)
    acc.setdefault("RA1|oldest_first|risk", []).append(evaluate(d, sel, k)[0])
    acc.setdefault("RA1|oldest_first|share_top_new_territory", []).append(float(d["new"][sel].mean()))
    acc.setdefault("RA1|share_of_segments_new_territory", []).append(float(d["new"].mean()))


def ra2(rng, acc, k, ks=(1.0, 3.0, 6.0)):
    d = gen_astana(rng, new_frac=0.0)
    base, _, _ = score(d)
    for k_true in ks:
        dt = dict(d); dt["true_risk"] = d["exp_fail"] * d["cons"] * np.where(d["heat"], k_true, 1.0)
        o = np.sort(dt["true_risk"])[::-1][:k].sum()
        for k_ass in ks:
            sel = top(base * np.where(d["heat"], k_ass, 1.0), k)
            acc.setdefault(f"RA2|true_k={k_true:g}|assumed_k={k_ass:g}|risk", []).append(dt["true_risk"][sel].sum() / o)
            acc.setdefault(f"RA2|true_k={k_true:g}|assumed_k={k_ass:g}|share_heat_in_top", []).append(float(d["heat"][sel].mean()))


def ra3(rng, acc, k):
    d = gen_astana(rng, new_frac=0.0)
    miss = d["district"] == NEW_DISTRICT
    oracle_top = top(d["true_risk"], k)
    acc.setdefault("RA3|oracle|share_top_new_district", []).append(float(miss[oracle_top].mean()))
    # a) пропуск = 0
    da = dict(d); da["complaints"] = np.where(miss, 0.0, d["complaints"])
    # b) медианная импутация плотности сигналов
    dens = d["complaints"] / d["length"]
    med = np.median(dens[~miss])
    db = dict(d); db["complaints"] = np.where(miss, med * d["length"], d["complaints"])
    # c) критерий сигналов исключён для строк без истории, веса перенормированы
    s_full = score(da)[0]
    s_wo = score(d, use=("age", "material", "pressure"))[0]
    s_c = np.where(miss, s_wo, s_full)
    for name, s in {"missing_as_zero": score(da)[0], "median_imputed": score(db)[0],
                    "criterion_dropped_renormalized": s_c, "true_history_available": score(d)[0]}.items():
        sel = top(s, k)
        acc.setdefault(f"RA3|{name}|risk", []).append(evaluate(d, sel, k)[0])
        acc.setdefault(f"RA3|{name}|share_top_new_district", []).append(float(miss[sel].mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--out", default="AST_A02_experiment_results.json")
    a = ap.parse_args()
    rng = np.random.default_rng(20261005)
    k = N // 10
    acc = {}
    for _ in range(a.reps):
        ra1(rng, acc, k); ra2(rng, acc, k); ra3(rng, acc, k)
    res = {key: {"mean": round(float(np.mean(v)), 3), "sd": round(float(np.std(v)), 3)} for key, v in acc.items()}
    meta = {"kind": "synthetic", "python": sys.version.split()[0], "numpy": np.__version__,
            "platform": platform.platform(), "N_segments": N, "k": k, "reps": a.reps, "seed": 20261005,
            "shared_code": "A02_priority_experiment.py: pct, score, top, evaluate (без изменений)",
            "warning": "Синтетический мир. Параметры (доля новых территорий 15%, k зимы, 6 районов) — допущения, не факты об Астане."}
    json.dump({"meta": meta, "results": res}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for key in sorted(res):
        print(f"{key:62s} {res[key]['mean']:.3f} ± {res[key]['sd']:.3f}")


if __name__ == "__main__":
    main()
