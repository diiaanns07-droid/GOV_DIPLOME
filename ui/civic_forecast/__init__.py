"""R13 · прогноз проблемных территорий для API и «Картины дня» (раунд 14). ПРОТОТИП НА СИНТЕТИКЕ.

    from ui.civic_forecast import forecast, forecast_response, attention_next_month
    forecast(month="2026-11", district="nura", k=10)
      → [{target:{kind,id,label_ru,label_kk}, risk, level, main_category, district, point,
          top_reasons:[{key, params, ru, kk}]}]
    forecast_response(month=None, district=None, k=10, context=None)  → dict для шлюза R01 (GET /api/civic/v2/forecast)
    attention_next_month(district=None, k=5, today=None)               → блок R08 «На что обратить внимание в следующем месяце»
    week_block(district=None, k=5, today=None)                         → раунд 15: блок R08 «Прогноз на неделю: где вероятнее
                                                                          рост жалоб» (3–5 территорий, причина одной строкой,
                                                                          «прототип», «Как считаем» с числами backtest)

Скорость: прогноз берётся из ui/civic_forecast/data/forecast_cache.json (сборка: python3 -m ml.civic_forecast build-cache) —
ответ за миллисекунды. Месяца нет в кэше — считается на лету (несколько секунд) и запоминается в памяти процесса.
Ответ всегда несёт evidence_type: "synthetic" и demo: true — интерфейс обязан это показать («Пример», «прототип»).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
import threading

from ml.civic_forecast.reasons import render
from ml.civic_forecast.targets import DISTRICT_NAMES

from .build import CACHE_PATH

MONTH_RE = re.compile(r"^(20[0-9]{2})-(0[1-9]|1[0-2])$")
MAX_K = 50
ASTANA = timezone(timedelta(hours=5))
_lock = threading.Lock()
_cache = None
_computed = {}


class ForecastError(ValueError):
    """Ошибка параметров: шлюз R01 отвечает 400 (status/code — его соглашение)."""

    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.status, self.code, self.message, self.field = 400, "bad_request", message, field


def _load():
    global _cache
    with _lock:
        if _cache is None:
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.is_file() else {"months": {}}
            _relabel(_cache)
        return _cache


def _relabel(cache: dict) -> None:
    """Подписи территорий — по текущему правилу targets.label (кэш собран раньше; модель и числа не меняются)."""
    try:
        from ml.civic_forecast.targets import label, load_targets
        by_id = {t["id"]: t for t in load_targets()}
    except Exception:
        return
    for block in (cache.get("months") or {}).values():
        for tid, item in (block.get("items") or {}).items():
            target = by_id.get(tid)
            if target and isinstance(item.get("target"), dict):
                item["target"]["label_ru"], item["target"]["label_kk"] = label(target, "ru"), label(target, "kk")


def _month_block(month: str) -> tuple[dict, bool]:
    data = _load()
    if month in data["months"]:
        return data["months"][month], False
    with _lock:
        if month not in _computed:
            from ml.civic_forecast.history import add_months, generate
            from .build import score_month
            history = generate()
            last = history.months[-1]
            if not (history.months[12] < month <= add_months(last, 1)):
                raise ForecastError(f"Прогноз есть для месяцев {history.months[13]} … {add_months(last, 1)}.", "month")
            _computed[month] = score_month(history, month)
        return _computed[month], True


def next_month(today=None) -> str:
    today = today or datetime.now(ASTANA).date()
    return f"{today.year + (today.month == 12):04d}-{today.month % 12 + 1:02d}"


def _check(month, district, k):
    if month is not None and (not isinstance(month, str) or not MONTH_RE.match(month)):
        raise ForecastError("month: месяц в формате ГГГГ-ММ.", "month")
    if district not in (None, "", "all") and district not in DISTRICT_NAMES:
        raise ForecastError("district: неизвестный район.", "district")
    if isinstance(k, str):
        k = int(k) if k.isdigit() else -1
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_K:
        raise ForecastError(f"k: целое 1–{MAX_K}.", "k")
    return k


def forecast(month=None, district=None, k=10):
    """Топ-k территорий с риском и причинами (ru и kk). month по умолчанию — следующий месяц."""
    k = _check(month, district, k)
    block, _ = _month_block(month or _default_month())
    ids = block["rank_city"] if district in (None, "", "all") else block["rank_district"][district]
    out = []
    for tid in ids[:k]:
        item = dict(block["items"][tid])
        reasons = item.pop("reasons")
        item["top_reasons"] = [{"key": r["key"], "params": r["params"], "ru": render(r, "ru"), "kk": render(r, "kk")}
                               for r in reasons]
        out.append(item)
    return out


def _default_month():
    data = _load()
    wanted = next_month()
    if wanted in data["months"]:
        return wanted
    return max(data["months"]) if data["months"] else wanted


def forecast_response(month=None, district=None, k=10, context=None):
    """Ответ для шлюза R01: GET /api/civic/v2/forecast?month&district&k (без обёртки ok/data)."""
    k = _check(month, district, k)
    month = month or _default_month()
    block, computed = _month_block(month)
    data = _load()
    return {
        "month": month, "asof": block["asof"], "district": district or None, "k": k,
        "model": block["model"], "threshold": block["threshold"],
        "evidence_type": "synthetic", "demo": True,
        "note_ru": "Прототип: модель обучена на синтетической истории. Не реальная оценка риска.",
        "note_kk": "Прототип: модель синтетикалық тарихи деректерде оқытылған. Нақты тәуекел бағасы емес.",
        "generated_at": data.get("generated_at"), "computed_now": computed,
        # Для прошедшего месяца: доля подтвердившихся в top-10/20/30 (на синтетике); для будущего — null.
        "check": block.get("check"),
        "items": forecast(month, district, k),
        # Раунд 15: блок «Прогноз на неделю» (экран R08 и web/civic/meetings/forecast-week.js) — тем же запросом.
        "week": week_block(district, min(k, 5)),
    }


def attention_next_month(district=None, k=5, today=None):
    """Для «Картины дня» R08: что может стать проблемой в следующем месяце (кратко, с одной-двумя причинами)."""
    month = next_month(today)
    data = _load()
    if month not in data["months"]:
        month = _default_month()
    items = forecast(month, district, k)
    return {"month": month, "evidence_type": "synthetic", "demo": True,
            "items": [{"target": i["target"], "risk": i["risk"], "level": i["level"], "main_category": i["main_category"],
                       "district": i["district"], "reasons": i["top_reasons"][:2]} for i in items]}


# ---------------------------------------------------------------------------------------------------------------------
# Раунд 15: «Прогноз на неделю» для «Картины дня» и Ситуационного центра R08 (IDEA §5: кейс Gton «Предиктивная
# аналитика»). Модель месячная (раунд 14): берём прогноз месяца, на который приходится большая часть ближайших 7 дней,
# и показываем 3–5 территорий с самым высоким риском. Причина — одной строкой: факт из истории жалоб (СИНТЕТИКА) и, если
# есть, климатическая норма месяца из реальной погоды Open-Meteo (это норма прошлых лет, не прогноз погоды).
RESULTS_PATH = CACHE_PATH.parents[3] / "ml" / "civic_forecast" / "results.json"  # корень репозитория
WEATHER_KEYS = {"forecast.reason.climate_snow", "forecast.reason.climate_thaw", "forecast.reason.heating",
                "forecast.reason.heat", "forecast.reason.thaw_last"}
SEASONS = {12: "зима", 1: "зима", 2: "зима", 3: "весна", 4: "весна", 5: "весна", 6: "лето", 7: "лето", 8: "лето",
           9: "осень", 10: "осень", 11: "осень"}
SEASON_KK = {"зима": "қыс", "весна": "көктем", "лето": "жаз", "осень": "күз"}
SEASON_RU = {"зима": "зимой", "весна": "весной", "лето": "летом", "осень": "осенью"}
_results = None


def _backtest() -> dict | None:
    """Числа проверки на истории (раунд 14, ml/civic_forecast/results.json): доля верных среди первых 10/20/30."""
    global _results
    if _results is None:
        try:
            _results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _results = {}
    return _results or None


def _round2(value) -> float | None:
    return round(float(value), 2) if isinstance(value, (int, float)) else None


def week_method(today=None) -> dict:
    """«Как считаем» для блока недели: метод, данные, честные числа backtest (общие и для текущего сезона)."""
    today = today or datetime.now(ASTANA).date()
    season = SEASONS[today.month]
    res = _backtest() or {}
    summary, meta = res.get("summary") or {}, res.get("meta") or {}
    mean = summary.get("mean") or {}
    by_season = (summary.get("by_season") or {}).get(season) or {}
    gbm, base = mean.get("gbm") or {}, mean.get("last_month") or {}
    s_gbm, s_base = by_season.get("gbm") or {}, by_season.get("last_month") or {}
    p10, b10 = _round2(gbm.get("10")), _round2(base.get("10"))
    sp10, sb10 = _round2(s_gbm.get("10")), _round2(s_base.get("10"))
    pct = lambda v: f"{round(v * 100)} %" if v is not None else "—"  # noqa: E731
    return {
        "model": "gradient boosting + сезонная поправка (ml/civic_forecast)",
        "evidence_type": "synthetic",
        "data": {"complaints": "synthetic", "weather": "real", "weather_source": (meta.get("weather") or {}).get("source"),
                 "history": meta.get("months"), "territories": meta.get("targets")},
        "backtest": {"precision_at_10": p10, "precision_at_20": _round2(gbm.get("20")), "precision_at_30": _round2(gbm.get("30")),
                     "baseline_last_month_at_10": b10, "season": season, "season_precision_at_10": sp10,
                     "season_baseline_at_10": sb10, "runs": summary.get("n_month_runs")},
        "text_ru": (f"Модель учится на истории жалоб по {meta.get('targets', '—')} территориям Астаны (синтетика, "
                    f"{'—'.join(meta.get('months') or ['—'])}) и на реальной погоде Open-Meteo. Порядок — по вероятности, что "
                    f"жалоб в следующем месяце будет {meta.get('threshold', 4)} и больше, а не по их числу сейчас: модель учитывает тренд, "
                    "сезон, категории, вид места, погоду и стройки рядом. Проверка на прошлых месяцах: "
                    f"из 10 территорий с самым высоким риском рост жалоб подтвердился в среднем у {pct(p10)} "
                    f"(«как в прошлом месяце» — {pct(b10)}); {SEASON_RU[season]} — {pct(sp10)} против {pct(sb10)}. Это прототип: на "
                    "настоящих обращениях модель ещё не проверялась."),
        "text_kk": (f"Модель Астананың {meta.get('targets', '—')} аумағы бойынша шағымдар тарихынан (синтетика, "
                    f"{'—'.join(meta.get('months') or ['—'])}) және Open-Meteo нақты ауа райы деректерінен үйренеді. Реті — "
                    f"қазіргі шағым санымен емес, келесі айда {meta.get('threshold', 4)} және одан көп шағым болу ықтималдығымен: модель "
                    "үрдісті, жыл мезгілін, санаттарды, орын түрін, ауа райын және маңайдағы құрылысты ескереді. Өткен "
                    f"айларда тексергенде: тәуекелі ең жоғары 10 аумақтың орта есеппен {pct(p10)}-ында шағым шынымен көбейген "
                    f"(«өткен айдағыдай» әдісі — {pct(b10)}); {SEASON_KK[season]} мезгілінде — {pct(sp10)}, салыстыру "
                    f"әдісінде — {pct(sb10)}. Бұл — прототип: нақты өтініштерде модель әлі тексерілмеген."),
    }


def week_block(district=None, k=5, today=None, now=None) -> dict:
    """Блок «Прогноз на неделю: где вероятнее рост жалоб» для R08 (вызов в процессе) и экрана (GET /forecast → week).

    -> {"title_ru", "title_kk", "period": {from, to}, "month", "label": "prototype", "evidence_type": "synthetic",
        "demo": true, "items": [{rank, target, district, point, risk, level, main_category, reason_ru, reason_kk,
        reason_source, reasons: [{key, ru, kk}], weather_ru?, weather_kk?}], "method": {...}, "note_ru", "note_kk"}
    Причина: первая по весу из истории жалоб (synthetic); погода — отдельной короткой строкой, если есть (real).
    """
    if isinstance(k, bool) or not isinstance(k, int):
        k = 5
    k = max(3, min(5, k))
    if today is None and isinstance(now, datetime):  # R08 зовёт с now (ui/civic_akim/neighbors.py)
        today = (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(ASTANA).date()
    today = today or datetime.now(ASTANA).date()
    start, end = today, today + timedelta(days=6)
    # Месяц недели — тот, где больше её дней; нет его в кэше — ближайший из кэша (прогноз считается заранее).
    days = [start + timedelta(days=i) for i in range(7)]
    months = [f"{d.year:04d}-{d.month:02d}" for d in days]
    month = max(set(months), key=months.count)
    data = _load()
    if month not in data.get("months", {}):
        month = _default_month()
    items = []
    for rank, item in enumerate(forecast(month, district, k), start=1):
        reasons = item.get("top_reasons") or []
        history = [r for r in reasons if r["key"] not in WEATHER_KEYS]
        weather = [r for r in reasons if r["key"] in WEATHER_KEYS]
        main = (history or weather or [None])[0]
        row = {"rank": rank, "target": item["target"], "district": item["district"], "point": item.get("point"),
               "risk": item["risk"], "level": item["level"], "main_category": item.get("main_category"),
               "reason_ru": main["ru"] if main else None, "reason_kk": main["kk"] if main else None,
               "reason_source": ("history" if main and main["key"] not in WEATHER_KEYS else "weather") if main else None,
               # та же причина списком — так её читает «Картина дня» R08 (blocks.forecast: reasons[0].ru / .kk)
               "reasons": [{"key": main["key"], "ru": main["ru"], "kk": main["kk"]}] if main else []}
        if weather and main is not weather[0]:
            row["weather_ru"], row["weather_kk"] = weather[0]["ru"], weather[0]["kk"]
        items.append(row)
    # Одна и та же сезонная причина у всех («В октябре начинается отопительный сезон…») — показываем её один раз над
    # списком, а не пять раз подряд; у пунктов остаётся только своя, отличающаяся.
    season = {(i.get("weather_ru"), i.get("weather_kk")) for i in items if i.get("weather_ru")}
    shared = None
    if len(season) == 1 and all(i.get("weather_ru") for i in items):
        shared = season.pop()
        for i in items:
            i.pop("weather_ru", None)
            i.pop("weather_kk", None)
    method = week_method(today)
    return {
        "module": "R13", "horizon": "week", "title_ru": "Прогноз на неделю: где вероятнее рост жалоб",
        "title_kk": "Апталық болжам: шағым қай жерде көбеюі мүмкін",
        "period": {"from": start.isoformat(), "to": end.isoformat()}, "month": month, "district": district or None,
        "label": "prototype", "evidence_type": "synthetic", "demo": True, "items": items,
        "season_ru": shared[0] if shared else None, "season_kk": shared[1] if shared else None,  # общая сезонная причина
        "method": method, "method_ru": method["text_ru"], "method_kk": method["text_kk"],  # «Как считаем» для R08
        "note_ru": "Прототип: история жалоб — синтетическая, погода — реальная (Open-Meteo). Не реальная оценка риска.",
        "note_kk": "Прототип: шағымдар тарихы — синтетикалық, ауа райы — нақты (Open-Meteo). Нақты тәуекел бағасы емес.",
    }


# Имена, под которыми блок ищет R08 (ui/civic_akim/neighbors.py R13_WEEK_FUNCS) — тот же блок.
week_forecast = forecast_week = week_block

__all__ = ["ForecastError", "attention_next_month", "forecast", "forecast_response", "forecast_week", "next_month",
           "week_block", "week_forecast", "week_method"]
