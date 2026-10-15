"""«Картина недели» (раунд 15): GET /api/civic/v2/akim/week?date=2026-10-14&district=nura — отчёт для совещания.

ОПРЕДЕЛЕНИЯ (одним местом):
- Неделя — понедельник 00:00 … следующий понедельник 00:00 по Астане (UTC+5), в которой лежит date
  (по умолчанию — сегодня). Идущая неделя считается до текущего момента (as_of = сейчас), прошедшая — до конца
  воскресенья. Будущая дата — ошибка 400 (как у «Картины дня»).
- «Поступило» — обращения без дублей, поданные за [начало недели, as_of]; по дням — 7 столбиков (будущие дни идущей
  недели — null). Сравнение — с тем же отрезком неделей раньше: в среду 10:00 — с прошлым пн…ср 10:00.
- «Исправлено» — обращения, которые за неделю (последний раз) получили «исправлено» и не открыты снова на as_of;
  «подтвердили жители» — те из них, где жители ответили «Да, исправлено» (summary.verified_at).
- «В работе», «Просрочено», темы, районы, горячие места, главная проблема, «Нужно решение акима» — «Картина дня»
  на последний день недели (summary(date=…)): ровно то, что аким видел в тот вечер (для идущей недели — сейчас).
- Ведомства (R17), «Жители вместе» (R16), поручения встреч и прогноз (R13) — состояние на момент формирования
  отчёта (соседи отдают текущее состояние; на листе это подписано датой формирования).
Числа считает код; текст — шаблон ru/kk без языковой модели (как text.py «Картины дня»).
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta

from . import board as board_mod, neighbors, text
from .summary import ASTANA_TZ, WEEK, AkimError, change, fixed_moment, iso, parse_time, verified_at

NBSP = text.NBSP


def _week_bounds(day: Date) -> tuple[datetime, datetime]:
    start_day = day - timedelta(days=day.weekday())
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=ASTANA_TZ)
    return start, start + WEEK


def _range_text(start: datetime, last: Date, lang: str) -> str:
    """«12–18 окт» / «28 сен – 4 окт» (как подписи дат R11, месяц коротко)."""
    a = start.date()
    if a.month == last.month:
        return f"{a.day}–{last.day}{NBSP}{text.month_short(last.month, lang)}"
    return f"{a.day}{NBSP}{text.month_short(a.month, lang)} – {last.day}{NBSP}{text.month_short(last.month, lang)}"


def _counts(recs: list[dict], start: datetime, as_of: datetime) -> dict:
    """Поступило / исправлено / подтвердили жители за [start, as_of] и по дням."""
    days = [0] * 7
    fixed_days = [0] * 7
    new = fixed = verified = 0
    for r in recs:
        created = parse_time(r.get("created_at"))
        if created is not None and start <= created <= as_of:
            new += 1
            days[min(6, (created - start).days)] += 1
        f = fixed_moment(r, as_of)
        if f is not None and start <= f <= as_of:
            fixed += 1
            fixed_days[min(6, max(0, (f - start).days))] += 1
            if verified_at(r, as_of) is not None:
                verified += 1
    return {"new": new, "fixed": fixed, "verified": verified, "days": days, "fixed_days": fixed_days}


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
            out.append(("Больше всего просрочек у служб: " if lang == "ru" else "Мерзімі өткен өтініштер ең көп қызметтер: ")
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
    start, end = _week_bounds(day)
    current = now.astimezone(ASTANA_TZ) < end
    as_of = now.astimezone(ASTANA_TZ) if current else end - timedelta(seconds=1)
    last_day = as_of.date()
    s = service.summary(date=last_day, district=district, now=now)

    all_records, _ = service._load_records()
    recs = [r for r in all_records if not r.get("duplicate_of")]
    scoped = [r for r in recs if district is None or service._district_of(r) == district]
    cur, prev = _counts(scoped, start, as_of), _counts(scoped, start - WEEK, as_of - WEEK)
    shown_days = (last_day - start.date()).days + 1
    kpi_s = s.get("kpi") or {}
    settings = service.neighbors
    all_demo = service.source_names.get("complaints") == "r07-demo"
    week = {
        "start": start.date().isoformat(), "end": (end - timedelta(days=1)).date().isoformat(),
        "current": current, "as_of": iso(as_of), "days_counted": shown_days,
        "label_ru": _range_text(start, (end - timedelta(days=1)).date(), "ru"),
        "label_kk": _range_text(start, (end - timedelta(days=1)).date(), "kk"),
        "as_of_label_ru": text.fmt_date(last_day.isoformat(), "ru"),
        "as_of_label_kk": text.fmt_date(last_day.isoformat(), "kk"),
        "prev_start": (start - WEEK).date().isoformat(), "prev_end": (start - timedelta(days=1)).date().isoformat(),
    }
    out = {
        "generated_at": iso(now), "week": week, "district": s.get("district"),
        "complaints_available": s.get("complaints_available"),
        "kpi": {
            "new": {**change(cur["new"], prev["new"]),
                    "series": [v if i < shown_days else None for i, v in enumerate(cur["days"])],
                    "prev_series": prev["days"]},
            "fixed": {**change(cur["fixed"], prev["fixed"]), "verified": cur["verified"],
                      "series": [v if i < shown_days else None for i, v in enumerate(cur["fixed_days"])]},
            "in_progress": {k: (kpi_s.get("in_progress") or {}).get(k) for k in ("value", "prev", "abs", "pct", "ratio", "trend", "mode")},
            "overdue": {k: (kpi_s.get("overdue") or {}).get(k) for k in ("value", "prev", "abs", "pct", "ratio", "trend", "mode")},
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
