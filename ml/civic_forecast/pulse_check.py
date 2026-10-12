"""R13 · проверка метода «Пульса района» R08 (волна 2 п. 8) на потоках с ЗАРАНЕЕ ИЗВЕСТНЫМИ всплесками. SYNTHETIC.

Зачем. «Пульс» показывает акиму 1–5 тревог («Снег в Нуре: ×3 к обычному»). Метод — R08 (ui/civic_akim/pulse.py):
всплеск = за 7 дней сообщений ≥ 5 и ≥ 2 × среднее за 4 прошлые недели. Реальной истории нет, поэтому проверяем так:
  1. Обычный уровень жалоб «район × категория» за неделю берём из синтетической истории R13 (history.py: сезон,
     погода LOCAL-9, горячие места) — месяц M, жалоб в неделю = жалобы месяца / 4,35.
  2. Строим 5 недель жалоб ~ Пуассон(обычный уровень) — 4 недели «как обычно» и текущую.
  3. В текущую неделю у 3 случайных пар «район × категория» вставляем всплеск ×f (f = 2, 3, 5) — это «правда».
  4. Зовём pulse.alarms R08 как есть и считаем: сколько вставленных всплесков попало в тревоги (найдено) и сколько
     тревог не про вставленные всплески (ложные — шум обычной недели). Отдельно — недели без всплесков вовсе.
  5. То же с предложенной проверкой «не случайно ли» (POISSON_GUARD): тревога остаётся, только если при обычном
     уровне такое число сообщений бывает реже, чем раз в 100 недель (P(X ≥ сейчас | Пуассон(обычный)) ≤ 1 %).
     Объяснение для акима не меняется («×3 к обычному»), меняется только то, какие строки попадают в пульс.

Масштаб: «город» — уровень истории R13 (все 2 334 территории, пилот); «демо» — ×0,25 (меньше жителей на платформе).
Запуск (нужен модуль R08 — сборка R01 или ветка R08):
    PYTHONPATH=<сборка R01> python3 -m ml.civic_forecast.pulse_check [--trials 200] [--out results_pulse.json]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import importlib
import json
import math
from pathlib import Path
import random

from .history import generate
from .targets import DISTRICT_NAMES

HERE = Path(__file__).resolve().parent
WEEKS_PER_MONTH = 4.35
GUARD_P = 0.01
MONTHS = ("2026-01", "2026-04", "2026-07", "2026-10")  # зима, весна, лето, начало отопительного сезона
FACTORS = (2.0, 3.0, 5.0)
N_SPIKES = 3
SCALES = {"city": 1.0, "demo": 0.25}
AS_OF = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
VARIANTS = ("r08", "poisson", "binomial")


def poisson_tail(k: int, lam: float) -> float:
    """P(X ≥ k) для X ~ Пуассон(lam). Считаем через сумму P(X < k) — k здесь небольшие (десятки)."""
    if k <= 0:
        return 1.0
    lam = max(lam, 1e-9)
    term, cdf = math.exp(-lam), 0.0
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


def binom_tail(k: int, n: int, q: float) -> float:
    """P(X ≥ k) для X ~ Биномиальное(n, q)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(k, n + 1))


def surprise(value: int, base: float | None, weeks: int, test: str) -> float:
    """Насколько неожиданна неделя: вероятность увидеть столько же или больше «просто так».

    poisson  — обычный уровень = среднее прошлых недель, как будто известен точно: P(X ≥ value | Пуассон(base)).
    binomial — обычный уровень сам посчитан по weeks неделям и шумит. Если всё как обычно, каждое из n = value + сумма
               прошлых недель сообщений с равной вероятностью попадает в любую из weeks + 1 недель; P(в текущую ≥ value).
               Тот же смысл для акима: «из всех сообщений за 5 недель на последнюю пришлось слишком много».
    """
    base = float(base or 0.0)
    if test == "poisson":
        return poisson_tail(int(value), max(base, 0.5))
    past = int(round(base * weeks))
    return binom_tail(int(value), int(value) + past, 1.0 / (weeks + 1))


def guard(alarm: dict, p: float = GUARD_P, test: str = "binomial") -> bool:
    """Оставить ли тревогу-всплеск R08: да, если неделя неожиданна (surprise ≤ p) хотя бы в одном её районе."""
    kind = alarm.get("kind")
    if kind not in ("spike", "spike_new", "spike_city"):
        return True
    weeks = int(alarm.get("weeks") or 4)
    if kind == "spike_city":
        rows = alarm.get("districts") or []
        return any(surprise(r["value"], r["value"] / r["ratio"] if r.get("ratio") else 0.0, weeks, test) <= p
                   for r in rows)
    return surprise(alarm["value"], alarm.get("base"), weeks, test) <= p


def weekly_levels(history, month: str, scale: float) -> dict:
    """Обычный уровень жалоб в неделю по паре (район, категория) в месяце month."""
    mi = history.month_index(month)
    acc: dict = {}
    for t in history.targets:
        d = t.get("district")
        if not d:
            continue
        for ci, n in enumerate(history.counts[t["id"]][mi]):
            if n:
                key = (d, history.categories[ci])
                acc[key] = acc.get(key, 0.0) + n
    return {k: v / WEEKS_PER_MONTH * scale for k, v in acc.items()}


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 60:  # нормальное приближение: быстро и достаточно точно для больших уровней
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def simulate_week(levels: dict, rng: random.Random, spikes: dict) -> list[dict]:
    """Записи жалоб за 5 недель до AS_OF; spikes — {(район, категория): множитель} для текущей недели."""
    out = []
    for (d, cat), lam in levels.items():
        for week in range(5):  # 0 — текущая неделя, 1..4 — обычные
            n = _poisson(rng, lam * (spikes.get((d, cat), 1.0) if week == 0 else 1.0))
            for _ in range(n):
                t = AS_OF - timedelta(days=7 * week) - timedelta(seconds=rng.uniform(60, 7 * 86400 - 60))
                out.append({"created_at": t.isoformat(), "category": cat, "district": d, "metoo": 0})
    return out


def covered(alarm: dict) -> set:
    if alarm["kind"] == "spike_city":
        return {(r["district"], alarm["category"]) for r in alarm.get("districts") or []}
    return {(alarm.get("district"), alarm.get("category"))}


def run(trials: int = 200, seed: int = 2026, pulse_module: str = "ui.civic_akim.pulse", p: float = GUARD_P) -> dict:
    pulse = importlib.import_module(pulse_module)
    history = generate()
    cats = [{"id": c, "ru": c, "kk": c} for c in history.categories]
    names = {d: {"ru": ru, "kk": kk} for d, (ru, kk) in DISTRICT_NAMES.items()}
    parse = lambda v: datetime.fromisoformat(v) if v else None  # noqa: E731
    max_alarms = pulse.MAX_ALARMS
    results = {}
    for scale_name, scale in SCALES.items():
        for month in MONTHS:
            levels = weekly_levels(history, month, scale)
            for factor in (1.0,) + FACTORS:
                rng = random.Random(f"{seed}:{scale_name}:{month}:{factor}")
                stats = {name: {"found": 0, "false": 0, "shown": 0, "quiet_weeks": 0} for name in VARIANTS}
                stats["injected"] = 0
                eligible = sorted(k for k, lam in levels.items() if lam >= 0.5)  # всплеск там, где жалобы вообще бывают
                for _ in range(trials):
                    picked = rng.sample(eligible, k=min(N_SPIKES, len(eligible))) if factor > 1 else []
                    spikes = {k: factor for k in picked}
                    records = simulate_week(levels, rng, spikes)
                    pulse.MAX_ALARMS = 1000  # все тревоги до обрезки; обрезаем ниже сами, как экран
                    try:
                        raw = pulse.alarms(records, AS_OF, parse_time=parse, district_of=lambda r: r["district"],
                                           categories=cats, district_names=names, items_now=[], items_prev=[])["items"]
                    finally:
                        pulse.MAX_ALARMS = max_alarms
                    variants = {"r08": raw[:max_alarms],
                                "poisson": [a for a in raw if guard(a, p, test="poisson")][:max_alarms],
                                "binomial": [a for a in raw if guard(a, p, test="binomial")][:max_alarms]}
                    stats["injected"] += len(picked)
                    for name, shown in variants.items():
                        s = stats[name]
                        cover = set().union(*(covered(a) for a in shown)) if shown else set()
                        s["found"] += sum(1 for k in picked if k in cover)
                        s["false"] += sum(1 for a in shown if not (covered(a) & set(picked)))
                        s["shown"] += len(shown)
                        s["quiet_weeks"] += 1 if not shown else 0
                results[f"{scale_name}:{month}:x{factor:g}"] = {
                    "scale": scale_name, "month": month, "factor": factor, "trials": trials,
                    "pairs": len(levels), "median_level": round(sorted(levels.values())[len(levels) // 2], 2),
                    **{name: {
                        "recall": round(stats[name]["found"] / stats["injected"], 3) if stats["injected"] else None,
                        "false_per_week": round(stats[name]["false"] / trials, 2),
                        "shown_per_week": round(stats[name]["shown"] / trials, 2),
                        "quiet_share": round(stats[name]["quiet_weeks"] / trials, 3),
                    } for name in VARIANTS},
                }
    return {"evidence_type": "synthetic", "method": "R08 ui/civic_akim/pulse.py alarms() as is (r08); the same alarms "
            f"kept only if surprise ≤ {p}: poisson (base known) or binomial (base estimated from the past weeks)",
            "spikes_per_week": N_SPIKES, "trials": trials, "seed": seed, "results": results}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--p", type=float, default=GUARD_P, help="порог неожиданности (по умолчанию 0,01)")
    ap.add_argument("--out", default=str(HERE / "results_pulse.json"))
    args = ap.parse_args(argv)
    report = run(args.trials, p=args.p)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for key, r in report["results"].items():
        print(f"{key:24s} med={r['median_level']:5.2f}  " + " | ".join(
            f"{v} recall={r[v]['recall']} false/wk={r[v]['false_per_week']:4.2f} quiet={r[v]['quiet_share']:.2f}"
            for v in VARIANTS))


if __name__ == "__main__":
    main()
