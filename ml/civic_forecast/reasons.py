"""Причины прогноза R13 понятными словами (ru / kk). Каждая причина — проверяемый факт, не «мнение модели»:
сколько было жалоб, как долго держится проблема, стройка по плану, климатическая НОРМА месяца по прошлым годам
(это не прогноз погоды — так и написано).

Причина хранится как {key, params} (ключи переданы R11, research/round-14-results/R13/INTEGRATION.txt);
render(reason, lang) превращает её в фразу здесь же, чтобы API отдавал готовый текст и без словарей R11.
"""

from __future__ import annotations

import json
from pathlib import Path

from .history import History, add_months

REPO = Path(__file__).resolve().parents[2]
_CATS = {c["id"]: c for c in json.loads((REPO / "research" / "round-14" / "categories_v2.json")
                                       .read_text(encoding="utf-8"))["categories"]}

MONTH_LOC_RU = ("январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре",
                "ноябре", "декабре")
MONTH_NOM_RU = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
                "ноябрь", "декабрь")
MONTH_NOM_KK = ("қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан",
                "қараша", "желтоқсан")
MONTH_LOC_KK = ("қаңтарда", "ақпанда", "наурызда", "сәуірде", "мамырда", "маусымда", "шілдеде", "тамызда",
                "қыркүйекте", "қазанда", "қарашада", "желтоқсанда")


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _num(n) -> str:
    return f"{n:,}".replace(",", " ") if isinstance(n, int) else str(n)


def _month_period(start: str, end: str, lang: str) -> str:
    names = MONTH_NOM_KK if lang == "kk" else MONTH_NOM_RU
    a = f"{names[int(start[5:]) - 1]} {start[:4]}"
    b = f"{names[int(end[5:]) - 1]} {end[:4]}"
    return a if start == end else f"{a} — {b}"


def render(reason: dict, lang: str = "ru") -> str:
    """Готовая фраза причины. lang: ru | kk (другое → ru)."""
    k, p = reason["key"], reason["params"]
    kk = lang == "kk"
    cat = (_CATS[p["category"]]["kk"] if kk else _CATS[p["category"]]["ru"]) if p.get("category") else ""
    mi = (int(p["month"][5:]) - 1) if p.get("month") else 0
    n = p.get("n", 0)
    if k == "forecast.reason.same_month_ly":
        if kk:
            return f"«{cat}»: өткен жылы {MONTH_LOC_KK[mi]} {_num(n)} шағым"
        return f"«{cat}»: {_num(n)} {_plural_ru(n, 'жалоба', 'жалобы', 'жалоб')} в {MONTH_LOC_RU[mi]} прошлого года"
    if k == "forecast.reason.recent_3m":
        if kk:
            return f"Соңғы 3 айда — {_num(n)} шағым"
        return f"За последние 3 месяца — {_num(n)} {_plural_ru(n, 'жалоба', 'жалобы', 'жалоб')}"
    if k == "forecast.reason.growth":
        if kk:
            return f"Шағым көбейді: соңғы 3 айда {_num(p['now'])}, оның алдындағы 3 айда {_num(p['before'])}"
        return f"Жалоб стало больше: {_num(p['now'])} за 3 месяца против {_num(p['before'])} до этого"
    if k == "forecast.reason.streak":
        if kk:
            return f"Мәселе {_num(n)} ай қатарынан сақталып тұр"
        return f"Проблема держится {_num(n)} {_plural_ru(n, 'месяц', 'месяца', 'месяцев')} подряд"
    if k == "forecast.reason.construction":
        period = _month_period(p["start"], p["end"], lang)
        return f"Жанында жоспарлы құрылыс: {period}" if kk else f"Рядом стройка по плану: {period}"
    if k == "forecast.reason.climate_snow":
        if kk:
            return f"{MONTH_LOC_KK[mi].capitalize()} әдетте қар жауады: айына {p['cm']} см ({p['years']} жылдың нормасы)"
        return f"В {MONTH_LOC_RU[mi]} обычно снег: {p['cm']} см за месяц (норма за {p['years']} г.)"
    if k == "forecast.reason.climate_thaw":
        if kk:
            return f"{MONTH_LOC_KK[mi].capitalize()} әдетте {_num(n)} күн жылымық болады — көктайғақ пен шұңқыр көбейеді"
        return f"В {MONTH_LOC_RU[mi]} обычно {_num(n)} {_plural_ru(n, 'день', 'дня', 'дней')} с оттепелью — гололёд и ямы"
    if k == "forecast.reason.heating":
        if kk:
            return f"{MONTH_LOC_KK[mi].capitalize()} жылыту маусымы басталады — жылу мен су бойынша шағым көбейеді"
        return f"В {MONTH_LOC_RU[mi]} начинается отопительный сезон — больше жалоб на тепло и воду"
    if k == "forecast.reason.heat":
        if kk:
            return f"{MONTH_LOC_KK[mi].capitalize()} әдетте {_num(n)} ыстық күн (+28 °C жоғары) — қоқыс пен иіс"
        return f"В {MONTH_LOC_RU[mi]} обычно {_num(n)} {_plural_ru(n, 'жаркий день', 'жарких дня', 'жарких дней')} (выше +28 °C) — мусор и запахи"
    if k == "forecast.reason.thaw_last":
        if kk:
            return f"Өткен айда {_num(n)} күн жылымық болды — көктемде шұңқыр көбейеді"
        return f"В прошлом месяце {_num(n)} {_plural_ru(n, 'день', 'дня', 'дней')} с оттепелью — весной растут ямы"
    raise KeyError(k)


def explain(history: History, target: dict, asof: int, parts: dict, normals: dict, *, max_reasons: int = 3) -> tuple[list, str | None]:
    """(причины по убыванию веса, главная категория). parts — вклад категорий в ожидаемые жалобы (fallback)."""
    tid = target["id"]
    rows = history.counts[tid]
    fmonth = add_months(history.months[asof], 1)
    ly = asof + 1 - 12
    tot = [sum(r) for r in rows]
    main_cat = max(parts, key=parts.get) if parts else None
    data, climate = [], []
    for ci, cat in enumerate(history.categories):
        n = rows[ly][ci]
        if n >= 2:
            data.append((n * (1.5 if cat == main_cat else 1.0),
                         {"key": "forecast.reason.same_month_ly", "params": {"category": cat, "n": n, "month": history.months[ly]}}))
    last3, prev3 = sum(tot[asof - 2:asof + 1]), sum(tot[asof - 5:asof - 2])
    if last3 >= 3:
        data.append((last3 / 3, {"key": "forecast.reason.recent_3m", "params": {"n": last3}}))
    if last3 - prev3 >= 3 and last3 >= 2 * max(prev3, 1):
        data.append(((last3 - prev3) / 2 + 0.5, {"key": "forecast.reason.growth", "params": {"now": last3, "before": prev3}}))
    streak = 0
    for k in range(asof, -1, -1):
        if tot[k] < 4:
            break
        streak += 1
    if streak >= 2:
        data.append((streak * 1.2, {"key": "forecast.reason.streak", "params": {"n": streak}}))
    for c in history.construction_active(tid, fmonth):
        data.append((3.5, {"key": "forecast.reason.construction", "params": {"start": c.start, "end": c.end}}))
        break
    mo = int(fmonth[5:])
    if main_cat == "snow_ice" and (normals.get("snowfall_cm") or 0) >= 5:
        climate.append((1.5, {"key": "forecast.reason.climate_snow",
                              "params": {"month": fmonth, "cm": round(normals["snowfall_cm"]), "years": normals["years"]}}))
    if main_cat in ("snow_ice", "roads", "sidewalks") and (normals.get("thaw_days") or 0) >= 5 and mo in (11, 12, 1, 2, 3, 4):
        climate.append((1.3, {"key": "forecast.reason.climate_thaw", "params": {"month": fmonth, "n": round(normals["thaw_days"])}}))
    if main_cat == "roads" and mo in (3, 4, 5):
        thaw_last = history.weather[history.months[asof]].get("thaw_days") or 0
        if thaw_last >= 5:
            climate.append((1.4, {"key": "forecast.reason.thaw_last", "params": {"n": round(thaw_last)}}))
    if main_cat == "utilities" and mo == 10:
        climate.append((1.5, {"key": "forecast.reason.heating", "params": {"month": fmonth}}))
    if main_cat in ("waste", "smell_air") and (normals.get("hot_days") or 0) >= 2:
        climate.append((1.2, {"key": "forecast.reason.heat", "params": {"month": fmonth, "n": round(normals["hot_days"])}}))
    data.sort(key=lambda x: -x[0])
    climate.sort(key=lambda x: -x[0])
    chosen = [r for _, r in data[:max_reasons - (1 if climate else 0)]] + [r for _, r in climate[:1]]
    return chosen[:max_reasons], main_cat
