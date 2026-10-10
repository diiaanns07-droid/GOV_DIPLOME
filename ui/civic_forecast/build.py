"""Сборка прогноза R13 для API: модель + причины → ui/civic_forecast/data/forecast_cache.json.

    python3 -m ml.civic_forecast build-cache [--months 2026-10,2026-11]

По умолчанию — прогноз на месяц после конца истории (2026-11) и на последний месяц истории (2026-10, чтобы
было с чем сравнить «как было»). В кэше: рейтинг всех территорий по городу и по районам (top-50), карточки с
причинами {key, params}; тексты ru/kk собираются при выдаче (ml/civic_forecast/reasons.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ml.civic_forecast import weather as wx
from ml.civic_forecast.features import THRESHOLD
from ml.civic_forecast.history import SEED, History, add_months, generate
from ml.civic_forecast.model import Forecaster, expected_counts, seasonal_ratios, sklearn_available, top_k
from ml.civic_forecast.reasons import explain
from ml.civic_forecast.targets import DISTRICT_NAMES, label

CACHE_PATH = Path(__file__).with_name("data") / "forecast_cache.json"
CITY_TOP, DISTRICT_TOP = 60, 50
LEVELS = ((0.5, "high"), (0.25, "medium"), (0.0, "low"))


def level_of(risk: float) -> str:
    return next(name for limit, name in LEVELS if risk >= limit)


def score_month(history: History, month: str, model_kind: str | None = None) -> dict:
    """Прогноз на месяц month по истории до месяца перед ним. Возвращает блок кэша."""
    if month == add_months(history.months[-1], 1):
        asof = len(history.months) - 1
    else:
        asof = history.months.index(month) - 1
    kind = model_kind or ("gbm" if sklearn_available() else "fallback")
    model = Forecaster(kind, threshold=THRESHOLD).fit(history, asof - 1)
    scores = model.score(history, asof)
    season = seasonal_ratios(history, upto=asof)
    _, parts = expected_counts(history, asof, season, components=True)
    normals = wx.normals(history.weather_table, int(month[5:]), month)
    by_id = {t["id"]: t for t in history.targets}
    city = top_k(scores, history, asof, CITY_TOP)
    districts = {}
    for d in DISTRICT_NAMES:
        sub = {tid: s for tid, s in scores.items() if by_id[tid]["district"] == d}
        districts[d] = top_k(sub, history, asof, DISTRICT_TOP)
    items = {}
    for tid in dict.fromkeys(city + [x for ids in districts.values() for x in ids]):
        t = by_id[tid]
        reasons, main_cat = explain(history, t, asof, parts[tid], normals)
        items[tid] = {
            "target": {"kind": t["target_kind"], "id": tid, "label_ru": label(t, "ru"), "label_kk": label(t, "kk")},
            "territory_kind": t["kind"], "point": t["point"], "district": t["district"],
            "risk": round(scores[tid], 3), "level": level_of(scores[tid]), "main_category": main_cat,
            "reasons": reasons,
        }
    # Прошедший месяц (есть в истории): сколько жалоб было на самом деле и подтвердился ли прогноз (синтетика).
    check = None
    if month in history.months:
        fi = history.months.index(month)
        for tid, item in items.items():
            actual = sum(history.counts[tid][fi])
            item["actual_complaints"] = actual
            item["confirmed"] = actual >= THRESHOLD
        check = {f"precision_at_{k}": round(sum(sum(history.counts[t][fi]) >= THRESHOLD for t in city[:k]) / k, 2)
                 for k in (10, 20, 30)}
    return {"month": month, "asof": history.months[asof], "model": kind, "threshold": THRESHOLD, "check": check,
            "rank_city": city, "rank_district": districts, "items": items,
            "weather_normals": {k: normals.get(k) for k in ("snowfall_cm", "thaw_days", "hot_days", "years")}}


def build_cache(months=None, path: Path = CACHE_PATH, seed: int = SEED) -> dict:
    history = generate(seed=seed)
    months = months or [history.months[-1], add_months(history.months[-1], 1)]
    data = {
        "schema": "r13-forecast-cache-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence_type": "synthetic", "demo": True,
        "note": "Прогноз обучен на СИНТЕТИЧЕСКОЙ истории (ml/civic_forecast/history.py). Территории — реальные OSM (R12).",
        "history": {"first": history.months[0], "last": history.months[-1], "seed": seed,
                    "weather": history.weather_meta.get("evidence_type")},
        "months": {m: score_month(history, m) for m in months},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"path": str(path), "months": months, "bytes": path.stat().st_size,
            "model": {m: data["months"][m]["model"] for m in months}}
