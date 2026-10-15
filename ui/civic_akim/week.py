"""«Картина недели» (раунд 15): GET /api/civic/v2/akim/week?date=2026-10-14&district=nura — отчёт для совещания.

ОПРЕДЕЛЕНИЯ (одним местом):
- Неделя — 7 × 24 часа до момента «на»: для сегодняшней даты (по умолчанию) — до текущего момента, для прошедшей — до
  конца того дня (23:59:59 по Астане, UTC+5). То же окно, что «за неделю» в «Картине дня» и «за 7 дней» на Ситуационном
  центре и карте R07: одно слово «неделя» — одно число (CONTRACT §0, приёмка R10 C5 / B-122). Будущая дата — 400.
- «Поступило» и «исправлено» (+ «подтвердили жители») — ровно числа «Картины дня» на этот момент (summary.kpi.new_week
  и fixed_week: их код, не пересчёт). По дням — 7 суток по Астане (date − 6 … date); первый столбик забирает и начало
  окна в предыдущих сутках (вечер, если отчёт строится днём) — сумма столбиков = числу недели. Сравнение — с 7 × 24 ч
  неделей раньше (как у «Картины дня»).
- «В работе», «Просрочено», темы, районы, горячие места, главная проблема, «Нужно решение акима» — «Картина дня»
  на эту дату (summary(date=…)): ровно то, что аким видит (для сегодняшней — сейчас).
- Ведомства (R17), «Жители вместе» (R16), поручения встреч и прогноз (R13) — состояние на момент формирования
  отчёта (соседи отдают текущее состояние; на листе это подписано датой формирования), только для сегодняшней недели.
Числа считает код; текст — шаблон ru/kk без языковой модели (как text.py «Картины дня»).
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta

from . import board as board_mod, neighbors, text
from .summary import ASTANA_TZ, WEEK, AkimError, fixed_moment, iso, parse_time

NBSP = text.NBSP


def _range_text(first: Date, last: Date, lang: str) -> str:
    """«9–15 окт» / «28 сен – 4 окт» (как подписи дат R11, месяц коротко)."""
    if first.month == last.month:
        return f"{first.day}–{last.day}{NBSP}{text.month_short(last.month, lang)}"
    return f"{first.day}{NBSP}{text.month_short(first.month, lang)} – {last.day}{NBSP}{text.month_short(last.month, lang)}"


def _by_days(recs: list[dict], first: Date, as_of: datetime) -> dict:
    """Поступило / исправлено по суткам Астаны за окно (as_of − 7 дней, as_of] — те же условия, что summary._kpi
    (new_week, fixed_week); начало окна в сутках до first — в первом столбике."""
    since = as_of - WEEK
    days, fixed_days = [0] * 7, [0] * 7

    def slot(moment: datetime) -> int:
        return max(0, min(6, (moment.astimezone(ASTANA_TZ).date() - first).days))

    for r in recs:
        created = parse_time(r.get("created_at"))
        if created is not None and since < created <= as_of:
            days[slot(created)] += 1
        f = fixed_moment(r, as_of)
        if f is not None and since < f <= as_of:
            fixed_days[slot(f)] += 1
    return {"days": days, "fixed_days": fixed_days}


def _sentences(w: dict, lang: str) -> list[str]:
    """Сводка недели одним абзацем (3–7 фраз). Пустые блоки соседей — без фраз о них."""
    k, d = w["kpi"], w.get("district")
    rng = w["week"]["label_" + lang]
    out = []
    n, ch = k["new"]["value"], k["new"]
    if lang == "ru":
        place = f" в районе {d['ru']}" if d else ""
        if n == 0:
            out.append(f"{rng}{place} новых обращений не было.")
        else:
            noun = text.plural_ru(n, "обращение", "обращения", "обращений")
            out.append(f"{rng}{place} поступило {text.fmt_num(n)} {noun}{_delta_week_ru(ch)}.")
        f = k["fixed"]["value"]
        if f:
            line = f"Исправлено {text.fmt_num(f)}"
            if k.get("verification_available"):
                line += f", из них жители подтвердили {text.fmt_num(k['fixed']['verified'])}"
            out.append(line + ".")
        out.append(f"На {w['week']['as_of_label_ru']} в работе {text.fmt_num(k['in_progress']['value'])}, "
                   f"просрочено {text.fmt_num(k['overdue']['value'])}.")
    else:
        place = f" {d['kk']} ауданында" if d else ""
        if n == 0:
            out.append(f"{rng} аралығында{place} жаңа өтініш болған жоқ.")
        else:
            out.append(f"{rng} аралығында{place} {text.fmt_num(n)} өтініш түсті{_delta_week_kk(ch)}.")
        f = k["fixed"]["value"]
        if f:
            line = f"Түзетілгені: {text.fmt_num(f)}"
            if k.get("verification_available"):
                line += f", оның ішінде тұрғындар растағаны: {text.fmt_num(k['fixed']['verified'])}"
            out.append(line + ".")
        out.append(f"{w['week']['as_of_label_kk']} жағдайы бойынша жұмыста: {text.fmt_num(k['in_progress']['value'])}, "
                   f"мерзімі өткені: {text.fmt_num(k['overdue']['value'])}.")
    main = w.get("_summary")
    if main is not None:
        sentence = text._main_ru(main) if lang == "ru" else text._main_kk(main)
        if sentence:
            out.append(sentence)
    if not w["week"]["current"]:
        return out  # соседи отдают текущее состояние — в текст прошедшей недели его не вписываем
    sv = w["services"]
    if sv.get("available") and sv.get("lagging"):
        rows = {it["service"]: it for it in sv["items"]}
        parts = [f"{rows[s][lang]} — {text.fmt_num(rows[s]['overdue'] or 0)}" for s in sv["lagging"] if s in rows]
        if parts:
            # R17 «просрочено» — правило R09 (нет ответа в срок), не срок исправления из числа «Просрочено» выше.
            out.append(("Больше всего просроченных ответов у служб: " if lang == "ru" else "Жауап мерзімі өткені ең көп қызметтер: ")
                       + "; ".join(parts) + ".")
    tg = w["together"]
    if tg.get("available") and (tg.get("counts") or {}).get("done"):
        c = tg["counts"]
        people = c.get("neighbors_done")
        if lang == "ru":
            deeds = text.plural_ru(c["done"], "дело", "дела", "дел")
            line = f"Жители сделали вместе {text.fmt_num(c['done'])} {deeds}"
            if people:
                line += f", участвовали {text.fmt_num(people)} {text.plural_ru(people, 'сосед', 'соседа', 'соседей')}"
            out.append(line + ".")
        else:
            line = f"Тұрғындар бірге {text.fmt_num(c['done'])} іс атқарды"
            if people:
                line += f", {text.fmt_num(people)} көрші қатысты"
            out.append(line + ".")
    mt = w["meetings"]
    if mt.get("available") and (mt.get("counts") or {}).get("total"):
        c = mt["counts"]
        if lang == "ru":
            out.append(f"Поручения встреч с жителями: сделано {text.fmt_num(c['done'])} из {text.fmt_num(c['total'])}"
                       + (f", просрочено {text.fmt_num(c['overdue'])}." if c.get("overdue") else "."))
        else:
            out.append(f"Тұрғындармен кездесу тапсырмалары: орындалғаны {text.fmt_num(c['done'])}/{text.fmt_num(c['total'])}"
                       + (f", мерзімі өткені: {text.fmt_num(c['overdue'])}." if c.get("overdue") else "."))
    return out


def _delta_week_ru(ch: dict) -> str:
    mode, trend = ch.get("mode"), ch.get("trend")
    if trend == "flat":
        return " — столько же, сколько неделей раньше"
    if mode == "new":
        return " (неделей раньше — ни одного)"
    if mode == "ratio":
        r = ch["ratio"]
        return f" — в {text.fmt_ratio(r)} {text.plural_ru(r, 'раз', 'раза', 'раз')} больше, чем неделей раньше"
    word = "больше" if trend == "up" else "меньше"
    if mode == "pct":
        return f" — на {text.fmt_pct(ch['pct'])} {word}, чем неделей раньше"
    return f" — на {text.fmt_num(ch['abs'])} {word}, чем неделей раньше"


def _delta_week_kk(ch: dict) -> str:
    mode, trend = ch.get("mode"), ch.get("trend")
    if trend == "flat":
        return ", алдыңғы аптамен бірдей"
    if mode == "new":
        return " (алдыңғы аптада бірде-бір болмаған)"
    if mode == "ratio":
        return f", бұл алдыңғы аптадан {text.fmt_ratio(ch['ratio'])} есе көп"
    if mode == "pct":
        return f", бұл алдыңғы аптадан {text.fmt_pct(ch['pct'])} {'көп' if trend == 'up' else 'аз'}"
    return f" (алдыңғы аптада — {text.fmt_num(ch['prev'])})"


def build(service, *, date=None, district=None, now: datetime | None = None) -> dict:
    now = now or service._clock()
    day, district = service._params(date, district, now)   # та же проверка даты и района, что у «Картины дня»
    local_now = now.astimezone(ASTANA_TZ)
    current = day >= local_now.date()
    day_start = datetime(day.year, day.month, day.day, tzinfo=ASTANA_TZ)
    as_of = local_now if current else day_start + timedelta(days=1) - timedelta(seconds=1)   # как summary()
    first = day - timedelta(days=6)
    s = service.summary(date=day, district=district, now=now)

    all_records, _ = service._load_records()
    recs = [r for r in all_records if not r.get("duplicate_of")]
    scoped = [r for r in recs if district is None or service._district_of(r) == district]
    by_days = _by_days(scoped, first, as_of)
    kpi_s = s.get("kpi") or {}
    keys = ("value", "prev", "abs", "pct", "ratio", "trend", "mode")
    new_w, fixed_w = kpi_s.get("new_week") or {}, kpi_s.get("fixed_week") or {}
    since = as_of - WEEK
    settings = service.neighbors
    all_demo = service.source_names.get("complaints") == "r07-demo"
    week = {
        "start": first.isoformat(), "end": day.isoformat(), "current": current, "as_of": iso(as_of),
        "from": iso(since), "window": "7x24h", "days_counted": 7,
        # Окно начинается накануне первого дня (отчёт строится днём) — первый столбик «по дням» начинается с этого часа.
        "first_from": iso(since) if (since + timedelta(seconds=1)).astimezone(ASTANA_TZ).date() < first else None,
        "label_ru": _range_text(first, day, "ru"), "label_kk": _range_text(first, day, "kk"),
        "as_of_label_ru": text.fmt_date(day.isoformat(), "ru"), "as_of_label_kk": text.fmt_date(day.isoformat(), "kk"),
        "prev_start": (first - timedelta(days=7)).isoformat(), "prev_end": (day - timedelta(days=7)).isoformat(),
    }
    out = {
        "generated_at": iso(now), "week": week, "district": s.get("district"),
        "complaints_available": s.get("complaints_available"),
        "kpi": {
            # Числа недели — числа «Картины дня» на этот момент (их код), по дням — те же записи по суткам.
            "new": {**{k: new_w.get(k) for k in keys}, "series": by_days["days"]},
            "fixed": {**{k: fixed_w.get(k) for k in keys}, "verified": fixed_w.get("verified"),
                      "series": by_days["fixed_days"]},
            "in_progress": {k: (kpi_s.get("in_progress") or {}).get(k) for k in keys},
            "overdue": {k: (kpi_s.get("overdue") or {}).get(k) for k in keys},
            "verification_available": bool(kpi_s.get("verification_available")),
        },
        "main_problem": s.get("main_problem"),
        "hot": board_mod._hot(s), "topics": board_mod._topics(s), "districts": board_mod._districts(s),
        "overdue_places": {k: (s.get("overdue") or {}).get(k) for k in ("count", "places", "items")},
        "decisions": board_mod.compact_decisions(s),
        "services": neighbors.agencies_board(settings, district=district, now=now, all_demo=all_demo),
        "together": neighbors.together(settings, district=district, now=now, all_demo=all_demo),
        "meetings": neighbors.meetings(settings, district=district, now=now, all_demo=all_demo),
        "forecast": neighbors.forecast(settings, district=district, now=now),
    }
    blocks = ("services", "together", "meetings", "forecast")
    out["demo"] = {**{k: bool(v) for k, v in (s.get("demo") or {}).items()},
                   **{b: bool(out[b].get("demo")) for b in blocks}}
    out["demo"]["any"] = any(out["demo"].values())
    out["sources"] = {**(s.get("sources") or {}), **{b: out[b].get("source", "none") for b in blocks},
                      "demo_world": settings.demo_world}
    out["_summary"] = s
    out["text"] = {"ru": _sentences(out, "ru"), "kk": _sentences(out, "kk")}
    del out["_summary"]
    return out


__all__ = ["build", "AkimError"]
