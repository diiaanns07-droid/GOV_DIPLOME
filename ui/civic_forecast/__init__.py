"""R13 · прогноз проблемных территорий для API и «Картины дня» (раунд 14). ПРОТОТИП НА СИНТЕТИКЕ.

    from ui.civic_forecast import forecast, forecast_response, attention_next_month
    forecast(month="2026-11", district="nura", k=10)
      → [{target:{kind,id,label_ru,label_kk}, risk, level, main_category, district, point,
          top_reasons:[{key, params, ru, kk}]}]
    forecast_response(month=None, district=None, k=10, context=None)  → dict для шлюза R01 (GET /api/civic/v2/forecast)
    attention_next_month(district=None, k=5, today=None)               → блок R08 «На что обратить внимание в следующем месяце»

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
        return _cache


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


__all__ = ["ForecastError", "attention_next_month", "forecast", "forecast_response", "next_month"]
