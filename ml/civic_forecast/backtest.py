"""Проверка прогноза «как будто в прошлом» (R13). Показатель Gton: доля подтвердившихся прогнозов = precision@K.

Для каждого прогнозного месяца F (по умолчанию 2025-07 … 2026-10):
  1. модель обучается только на том, что было известно к концу месяца F−1 (метки — месяцы ≤ F−1);
  2. ранжирует все территории по риску «≥ N жалоб в F»;
  3. precision@K = доля территорий из top-K, у которых в F действительно ≥ N жалоб (K = 10, 20, 30).
Сравнение: gbm, fallback (без зависимостей), last_month и same_month_ly (простые базовые прогнозы),
gbm_no_weather (та же модель без погодных признаков — вклад погоды). Доля «проблемных» = точность случайного выбора.

    python3 -m ml.civic_forecast backtest [--seeds 2026,2027,2028] [--out ml/civic_forecast]

ВАЖНО: история синтетическая (history.py). Цифры показывают, что конвейер и методика работают и что модель
извлекает закономерности, ЗАЛОЖЕННЫЕ генератором. Это не точность на реальных обращениях акимата.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from .features import FeatureBuilder, MIN_ASOF, THRESHOLD
from .history import SEED, generate
from .model import Forecaster, sklearn_available, top_k

KS = (10, 20, 30)
FIRST_FORECAST = "2025-07"
SEASON = {12: "зима", 1: "зима", 2: "зима", 3: "весна", 4: "весна", 5: "весна",
          6: "лето", 7: "лето", 8: "лето", 9: "осень", 10: "осень", 11: "осень"}


def run_one(history, *, threshold=THRESHOLD, first_forecast=FIRST_FORECAST, models=None, log=None) -> dict:
    models = models or (["gbm", "gbm_no_weather"] if sklearn_available() else []) + ["fallback", "last_month", "same_month_ly"]
    fb = FeatureBuilder(history, threshold)
    start = history.months.index(first_forecast)
    per_month = []
    for fi in range(start, len(history.months)):
        asof = fi - 1
        if asof - 1 < MIN_ASOF:
            continue
        labels = dict(zip(fb.ids, fb.labels(asof)))
        row = {"month": history.months[fi], "positives": sum(labels.values()), "prevalence": sum(labels.values()) / len(labels),
               "precision": {}, "seconds": {}}
        for name in models:
            t0 = time.perf_counter()
            kind = "gbm" if name.startswith("gbm") else name
            model = Forecaster(kind, threshold=threshold, weather=(name != "gbm_no_weather")).fit(history, asof - 1)
            scores = model.score(history, asof)
            row["precision"][name] = {k: sum(labels[t] for t in top_k(scores, history, asof, k)) / k for k in KS}
            row["seconds"][name] = round(time.perf_counter() - t0, 2)
        per_month.append(row)
        if log:
            log(f"{row['month']}: " + ", ".join(f"{m} {row['precision'][m][10]:.2f}/{row['precision'][m][20]:.2f}/"
                                                 f"{row['precision'][m][30]:.2f}" for m in models))
    return {"models": models, "months": per_month}


def summarize(runs: list[dict]) -> dict:
    """Средние по всем месяцам и seed, по сезонам; выигрыши gbm/fallback у лучшего базового по месяцам."""
    models = runs[0]["models"]
    rows = [r for run in runs for r in run["months"]]
    mean = {m: {k: statistics.mean(r["precision"][m][k] for r in rows) for k in KS} for m in models}
    spread = {m: {k: (min(r["precision"][m][k] for r in rows), max(r["precision"][m][k] for r in rows)) for k in KS}
              for m in models}
    seasons = {}
    for r in rows:
        seasons.setdefault(SEASON[int(r["month"][5:])], []).append(r)
    by_season = {s: {m: {k: statistics.mean(r["precision"][m][k] for r in rs) for k in KS} for m in models}
                 for s, rs in seasons.items()}
    baselines = [m for m in ("last_month", "same_month_ly") if m in models]
    duel = {}
    for m in [x for x in models if x not in baselines]:
        duel[m] = {}
        for k in KS:
            best = [max(r["precision"][b][k] for b in baselines) for r in rows]
            mine = [r["precision"][m][k] for r in rows]
            duel[m][k] = {"wins": sum(a > b for a, b in zip(mine, best)), "ties": sum(a == b for a, b in zip(mine, best)),
                          "losses": sum(a < b for a, b in zip(mine, best)),
                          "mean_gain": statistics.mean(a - b for a, b in zip(mine, best))}
    return {"models": models, "n_month_runs": len(rows), "prevalence": statistics.mean(r["prevalence"] for r in rows),
            "positives_mean": statistics.mean(r["positives"] for r in rows), "mean": mean, "range": spread,
            "by_season": by_season, "vs_best_baseline": duel,
            "fit_seconds_mean": {m: statistics.mean(r["seconds"][m] for r in rows) for m in models}}


NAMES = {"gbm": "Градиентный бустинг (scikit-learn)", "gbm_no_weather": "Бустинг без погодных признаков",
         "fallback": "Запасная: сезонная наивная + взвешенная частота", "last_month": "Базовый: как в прошлом месяце",
         "same_month_ly": "Базовый: как в тот же месяц год назад"}


def results_markdown(summary: dict, meta: dict) -> str:
    s = summary
    lines = [
        "# R13 · Прогноз проблемных территорий — результаты проверки (backtest)", "",
        "> **НА СИНТЕТИКЕ.** История жалоб сгенерирована (`ml/civic_forecast/history.py`, evidence synthetic, demo).",
        "> Цифры показывают, что конвейер и методика проверки работают и модель находит закономерности, заложенные",
        "> генератором. Это **не** точность на реальных обращениях: её можно измерить только на данных акимата в пилоте.", "",
        f"- Территорий: {meta['targets']} (реальные объекты OSM из данных R12); история {meta['months'][0]} … {meta['months'][1]}.",
        f"- Погода: {meta['weather']['evidence_type']} — {meta['weather']['source']}.",
        f"- Цель: у территории в следующем месяце ≥ {meta['threshold']} жалоб. Доля таких территорий в среднем "
        f"{s['prevalence'] * 100:.1f} % (≈ {s['positives_mean']:.0f} в месяц) — столько даёт случайный выбор.",
        f"- Прогнозные месяцы: {meta['forecast_months'][0]} … {meta['forecast_months'][1]}, seed истории: {', '.join(map(str, meta['seeds']))} "
        f"({s['n_month_runs']} прогнозов «месяц × seed»). Модель каждый раз обучается только на прошлом.",
        "- Показатель Gton «60–70 % прогнозов подтверждаются» = precision@K: доля территорий из top-K, где проблема подтвердилась.", "",
        "## Precision@K — среднее (мин … макс по месяцам)", "",
        "| Модель | @10 | @20 | @30 |", "|---|---|---|---|",
    ]
    for m in s["models"]:
        cells = [f"**{s['mean'][m][k]:.2f}** ({s['range'][m][k][0]:.2f} … {s['range'][m][k][1]:.2f})" for k in KS]
        lines.append(f"| {NAMES.get(m, m)} | " + " | ".join(cells) + " |")
    lines.append(f"| Случайный выбор | {s['prevalence']:.2f} | {s['prevalence']:.2f} | {s['prevalence']:.2f} |")
    lines += ["", "## Против лучшего базового прогноза (по каждому месяцу)", "",
              "| Модель | K | лучше | так же | хуже | средний выигрыш |", "|---|---|---|---|---|---|"]
    for m, by_k in s["vs_best_baseline"].items():
        for k in KS:
            d = by_k[k]
            lines.append(f"| {NAMES.get(m, m)} | {k} | {d['wins']} | {d['ties']} | {d['losses']} | {d['mean_gain']:+.3f} |")
    lines += ["", "## По сезонам (precision@20)", "", "| Сезон | " + " | ".join(NAMES.get(m, m) for m in s["models"]) + " |",
              "|---|" + "---|" * len(s["models"])]
    for season in ("зима", "весна", "лето", "осень"):
        if season in s["by_season"]:
            lines.append(f"| {season} | " + " | ".join(f"{s['by_season'][season][m][20]:.2f}" for m in s["models"]) + " |")
    verdict = []
    if "gbm" in s["vs_best_baseline"]:
        g = s["vs_best_baseline"]["gbm"]
        better = [k for k in KS if g[k]["mean_gain"] > 0 and g[k]["wins"] > g[k]["losses"]]
        verdict.append(f"- Бустинг лучше лучшего базового прогноза при K = {', '.join(map(str, better))}." if better
                       else "- Бустинг НЕ лучше лучшего базового прогноза ни при одном K.")
        worse = [k for k in KS if k not in better]
        if worse and better:
            verdict.append(f"- При K = {', '.join(map(str, worse))} выигрыша нет или он не устойчив по месяцам.")
    best_model = max((m for m in s["models"] if m not in ("last_month", "same_month_ly")),
                     key=lambda m: statistics.mean(s["mean"][m][k] for k in KS), default=None)
    if best_model:
        reached = [k for k in KS if s["mean"][best_model][k] >= 0.6]
        verdict.append(f"- Ориентир Gton «60–70 % подтверждаются»: лучшая модель ({NAMES.get(best_model, best_model)}) "
                       + (f"достигает его при K = {', '.join(map(str, reached))}" if reached else "его НЕ достигает")
                       + " — " + ", ".join(f"@{k} {s['mean'][best_model][k]:.2f}" for k in KS)
                       + f" при доле проблемных территорий {s['prevalence'] * 100:.1f} %.")
    if "gbm_no_weather" in s["mean"] and "gbm" in s["mean"]:
        diff = statistics.mean(s["mean"]["gbm"][k] - s["mean"]["gbm_no_weather"][k] for k in KS)
        verdict.append(f"- Погодные признаки дают в среднем {diff:+.3f} к precision. Причина: в прогнозе на месяц вперёд "
                       "известна только НОРМА месяца, а она повторяет сезон, который модель и так видит по истории; "
                       "фактическая погода будущего месяца (то, что реально двигает жалобы в генераторе) неизвестна. "
                       "Погода поможет, если подключить прогноз погоды на месяц или пересчитывать прогноз чаще (на неделю).")
    if "gbm" in s["mean"] and "fallback" in s["mean"]:
        gap = statistics.mean(s["mean"]["gbm"][k] - s["mean"]["fallback"][k] for k in KS)
        if abs(gap) < 0.02:
            verdict.append(f"- Бустинг и запасная модель почти равны ({gap:+.3f}): на этой синтетике сложная модель не нужна; "
                           "в пилоте начинать с запасной (прозрачная, без зависимостей), бустинг — если на реальных данных он выиграет.")
    verdict.append("- Сравнение идёт с ЛУЧШИМ из двух базовых прогнозов в каждом месяце (выбранным задним числом) — это строже, "
                   "чем с каждым из них по отдельности.")
    f = s["vs_best_baseline"].get("fallback")
    if f:
        better = [k for k in KS if f[k]["mean_gain"] > 0]
        verdict.append("- Запасная модель без зависимостей " + (f"лучше базовых при K = {', '.join(map(str, better))}." if better
                                                                else "не лучше базовых — она нужна только как работающий запасной вариант."))
    lines += ["", "## Вывод (честно)", ""] + verdict + [
        "- На реальных данных точность будет другой: реальная история короче и шумнее, есть сезоны без данных,",
        "  а связь с погодой и стройками нужно ещё проверить. План пилота — в ml/civic_forecast/README.md.", "",
        f"Время обучения одной модели (среднее): " + ", ".join(f"{NAMES.get(m, m)} {sec:.2f} с" for m, sec in s["fit_seconds_mean"].items()) + ".",
        f"Среда: {meta['env']}. Команда: `python3 -m ml.civic_forecast backtest --seeds {','.join(map(str, meta['seeds']))}`.", ""]
    return "\n".join(lines)


def main(seeds=(SEED,), out_dir: Path | None = None, threshold=THRESHOLD, first_forecast=FIRST_FORECAST, log=print):
    import platform
    runs, meta = [], None
    for seed in seeds:
        h = generate(seed=seed)
        log(f"seed {seed}: история {h.months[0]}…{h.months[-1]}, территорий {len(h.targets)}")
        runs.append(run_one(h, threshold=threshold, first_forecast=first_forecast, log=log))
        meta = {"targets": len(h.targets), "months": [h.months[0], h.months[-1]], "weather": h.weather_meta,
                "threshold": threshold, "forecast_months": [first_forecast, h.months[-1]], "seeds": list(seeds)}
    summary = summarize(runs)
    try:
        import sklearn
        sk = f"scikit-learn {sklearn.__version__}"
    except ImportError:
        sk = "без scikit-learn"
    meta["env"] = f"Python {platform.python_version()}, {sk}, {platform.system()}"
    if out_dir:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "RESULTS.md").write_text(results_markdown(summary, meta), encoding="utf-8")
        (out_dir / "results.json").write_text(json.dumps({"meta": meta, "summary": summary, "runs": runs},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
    return summary, meta


def rerender(out_dir: Path) -> str:
    """Перестроить RESULTS.md из results.json без пересчёта (после правки текста отчёта)."""
    out_dir = Path(out_dir)
    data = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    summary = data["summary"]
    # JSON превращает ключи K в строки — вернуть числа.
    for key in ("mean", "range", "by_season"):
        if key == "by_season":
            summary[key] = {s: {m: {int(k): v for k, v in d.items()} for m, d in ms.items()} for s, ms in summary[key].items()}
        else:
            summary[key] = {m: {int(k): v for k, v in d.items()} for m, d in summary[key].items()}
    summary["vs_best_baseline"] = {m: {int(k): v for k, v in d.items()} for m, d in summary["vs_best_baseline"].items()}
    text = results_markdown(summary, data["meta"])
    (out_dir / "RESULTS.md").write_text(text, encoding="utf-8")
    return text
