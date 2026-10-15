"""«Картина недели» (R08, раунд 15): GET /api/civic/v2/akim/week?date=YYYY-MM-DD&district=<id> — отчёт для совещания.

ПЕРИОД: 7 календарных дней по Астане, последний — date (по умолчанию сегодня): «9–15 октября». Для прошлой даты неделя
закрыта (до 23:59:59 date), для сегодняшней — до текущего момента («по состоянию на 14:32»). Сравнение — с теми же
7 днями неделей раньше и до того же часа (как «Новые сегодня» в «Картине дня»: утром не всегда «меньше»).

ЧИСЛА:
- поступило, исправлено (служба сообщила), проверено жителями, вернули жители — за период, теми же правилами, что
  «Картина дня» (summary.py: status_at, fixed_moment, verified_at, reopen_moments); по дням — новые за каждый день,
  сумма столбиков = «поступило за неделю»;
- «в работе» и «просрочено» — на конец периода, ровно числа «Картины дня» этого дня;
- главная проблема, темы, районы, горячие места, пульс — тепловая карта R07 за 7 дней на конец периода (как на карте);
- ведомства, кризис, жители вместе, поручения встреч, прогноз — блоки соседей «Картины дня» 2.0 (только для недели,
  которая заканчивается сегодня: у соседей нет истории «на дату»; для прошлой недели — пометка past_date).
Тексты ru / kk — шаблоны без LLM (как text.py).
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta

from . import text as T
from .summary import (ASTANA_TZ, NEIGHBOR_BLOCKS, AkimError, change, districts, fixed_moment, iso, parse_time,
                      reopen_moments, verified_at)

WEEK = timedelta(days=7)
TOPICS_TOP = 6
HOT_TOP = 5
OBJECTS_TOP = 5


def _counts(recs: list[dict], start: datetime, end: datetime, day0: datetime) -> dict:
    """Поступило / исправлено / проверено жителями / вернули — за [start, end]; новые по дням от day0 (7 дней)."""
    new = fixed = verified = reopened = reopened_res = 0
    by_day = [0] * 7
    for r in recs:
        created = parse_time(r.get("created_at"))
        if created is None:
            continue
        if start <= created <= end:
            new += 1
            i = (created - day0).days
            if 0 <= i < 7:
                by_day[i] += 1
        f = fixed_moment(r, end)
        if f is not None and start <= f <= end:
            fixed += 1
            if verified_at(r, end) is not None:
                verified += 1
        for t, by_resident in reopen_moments(r, end):
            if start <= t <= end:
                reopened += 1
                reopened_res += int(by_resident)
    return {"new": new, "fixed": fixed, "verified": verified, "reopened": reopened,
            "reopened_by_residents": reopened_res, "by_day": by_day}


def _period_ru(a: Date, b: Date) -> str:
    """«9–15 окт», «28 сен – 4 окт»."""
    if a.month == b.month:
        return f"{a.day}–{b.day}{T.NBSP}{T.month_short(b.month, 'ru')}"
    return f"{a.day}{T.NBSP}{T.month_short(a.month, 'ru')} – {b.day}{T.NBSP}{T.month_short(b.month, 'ru')}"


def _period_kk(a: Date, b: Date) -> str:
    """«9–15 қазан», «28 қыркүйек – 4 қазан» (в словаре R11 у kk полные названия месяцев)."""
    if a.month == b.month:
        return f"{a.day}–{b.day}{T.NBSP}{T.month_short(b.month, 'kk')}"
    return f"{a.day}{T.NBSP}{T.month_short(a.month, 'kk')} – {b.day}{T.NBSP}{T.month_short(b.month, 'kk')}"


def build(svc, *, date=None, district=None, now: datetime) -> dict:
    s = svc.summary(date=date, district=district, now=now)
    day = Date.fromisoformat(s["date"])
    as_of = parse_time(s["as_of"])
    day0 = datetime(day.year, day.month, day.day, tzinfo=ASTANA_TZ) - timedelta(days=6)
    all_records, _skipped = svc._load_records()
    recs = [r for r in all_records if not r.get("duplicate_of")
            and (s["district"] is None or svc._district_of(r) == s["district"]["id"])]
    cur = _counts(recs, day0, as_of, day0)
    prev = _counts(recs, day0 - WEEK, as_of - WEEK, day0 - WEEK)
    k = s["kpi"]
    days = []
    for i in range(7):
        d = (day0 + timedelta(days=i)).date()
        days.append({"date": d.isoformat(), "weekday": d.isoweekday(), "new": cur["by_day"][i], "prev": prev["by_day"][i],
                     "partial": s["is_today"] and d == day})
    totals = {
        "new": change(cur["new"], prev["new"]),
        "fixed": {**change(cur["fixed"], prev["fixed"]), "verified": cur["verified"],
                  "awaiting": cur["fixed"] - cur["verified"], "reopened": cur["reopened"],
                  "reopened_by_residents": cur["reopened_by_residents"]},
        "in_progress": {f: k["in_progress"].get(f) for f in ("value", "prev", "abs", "pct", "ratio", "trend", "mode", "waiting")},
        "overdue": {f: k["overdue"].get(f) for f in ("value", "prev", "abs", "pct", "ratio", "trend", "mode")},
        "verification_available": bool(k.get("verification_available")),
    }
    topics = s.get("topics") or {}
    objects = s.get("objects") or {}
    result = {
        "generated_at": s["generated_at"], "date": s["date"], "is_today": s["is_today"], "as_of": s["as_of"],
        "period": {"from": day0.date().isoformat(), "to": day.isoformat(),
                   "prev_from": (day0 - WEEK).date().isoformat(), "prev_to": (day - timedelta(days=7)).isoformat(),
                   "ru": _period_ru(day0.date(), day), "kk": _period_kk(day0.date(), day)},
        "district": s["district"],
        "complaints_available": s["complaints_available"],
        "totals": totals,
        "days": days,
        "main_problem": s.get("main_problem"),
        "topics": {"available": bool(topics.get("available")), "items": list(topics.get("items") or [])[:TOPICS_TOP],
                   "more": max(0, len(topics.get("items") or []) - TOPICS_TOP)},
        "districts": s.get("districts"),
        "hot": {"available": bool((s.get("hot") or {}).get("available")),
                "items": list((s.get("hot") or {}).get("items") or [])[:HOT_TOP]},
        "pulse": s.get("pulse"),
        "decisions": s.get("decisions"),
        "overdue": s.get("overdue"),
        "objects": {"available": bool(objects.get("available")), "late": list(objects.get("late") or [])[:OBJECTS_TOP],
                    "late_count": objects.get("late_count", 0), "stale_count": objects.get("stale_count", 0),
                    "demo": bool(objects.get("demo"))},
        **{name: s.get(name) for name in NEIGHBOR_BLOCKS},
        "demo": s.get("demo"),
        "sources": s.get("sources"),
    }
    result["text"] = {"ru": text_ru(result), "kk": text_kk(result)}
    return result


# ---------------------------------------------------------------- текст недели

def _people_ru(n: int) -> str:
    return f"{T.fmt_num(n)} {T.plural_ru(n, 'человек', 'человека', 'человек')}"


def text_ru(w: dict) -> list[str]:
    """Абзацы сводки недели (ru). Каждая фраза — только из чисел ответа."""
    out = []
    t, d = w["totals"], w.get("district")
    place = f" в районе {d['ru']}" if d else ""
    if w.get("complaints_available") is False:
        out.append("Данные об обращениях пока не подключены.")
    else:
        n = t["new"]["value"]
        noun = T.plural_ru(n, "обращение", "обращения", "обращений")
        line = f"За неделю {w['period']['ru']}{place} поступило {T.fmt_num(n)} {noun}"
        line += ("." if t["new"]["trend"] == "flat" and n == 0 else
                 f" — {T.delta_ru(t['new']).replace('неделю назад', 'неделей раньше').removeprefix('это ')}.")
        out.append(line)
        f = t["fixed"]
        if f["value"]:
            fixed = f"Службы сообщили об исправлении {T.fmt_num(f['value'])} {T.plural_ru(f['value'], 'обращения', 'обращений', 'обращений')}"
            if t["verification_available"]:
                fixed += f", жители подтвердили {T.fmt_num(f['verified'])}"
                if f["reopened_by_residents"]:
                    fixed += f", вернули в работу {T.fmt_num(f['reopened_by_residents'])}"
            out.append(fixed + ".")
        over = t["overdue"]["value"] or 0
        out.append("Просроченных обращений нет." if not over else
                   f"Просрочено {T.fmt_num(over)} {T.plural_ru(over, 'обращение', 'обращения', 'обращений')}.")
    m = w.get("main_problem")
    if m:
        out.append(f"Главная проблема недели — «{m['category_ru']}» в районе {m['district_ru']}: "
                   f"{_people_ru(m['value'])} сообщили о нерешённом.")
    tg = w.get("together") or {}
    if tg.get("available") and (tg.get("done_week") or tg.get("upcoming")):
        parts = []
        if tg.get("done_week"):
            parts.append(f"провели {T.fmt_num(tg['done_week'])} {T.plural_ru(tg['done_week'], 'дело', 'дела', 'дел')} "
                         f"({_people_ru(tg['people_done'])})")
        if tg.get("upcoming"):
            parts.append(f"готовят ещё {T.fmt_num(tg['upcoming'])}")
        out.append("Жители вместе: " + ", ".join(parts) + ".")
    ag = w.get("agencies") or {}
    if ag.get("available") and (ag.get("joint") is not None or ag.get("handoffs_week") is not None):
        bits = []
        if ag.get("joint") is not None:
            bits.append(f"совместных обращений в работе — {T.fmt_num(ag['joint'])}")
        if ag.get("handoffs_week") is not None:
            bits.append(f"передач между службами за неделю — {T.fmt_num(ag['handoffs_week'])}")
        out.append("Ведомства вместе: " + ", ".join(bits) + ".")
    cr = w.get("crisis") or {}
    if cr.get("available") and cr.get("active"):
        a = cr["active"]
        out.append(f"Идёт кризисный штаб «{a['title_ru']}»: выполнено {T.fmt_num(a['tasks_done'])} из "
                   f"{T.fmt_num(a['tasks_total'])} задач служб.")
    mt = w.get("meetings") or {}
    if mt.get("available") and mt.get("orders", {}).get("total"):
        o = mt["orders"]
        line = f"Поручения встреч с жителями: выполнено {T.fmt_num(o['done'])} из {T.fmt_num(o['total'])}"
        if o.get("overdue"):
            line += f", просрочено {T.fmt_num(o['overdue'])}"
        out.append(line + ".")
    return out


def text_kk(w: dict) -> list[str]:
    out = []
    t, d = w["totals"], w.get("district")
    place = f" {d['kk']} ауданында" if d else ""
    if w.get("complaints_available") is False:
        out.append("Өтініштер туралы деректер әзірге қосылмаған.")
    else:
        n = t["new"]["value"]
        out.append(f"{w['period']['kk']} аралығында{place} {T.fmt_num(n)} өтініш түсті"
                   f"{T.delta_kk(t['new']).replace('бір апта бұрын', 'алдыңғы аптада')}.")
        f = t["fixed"]
        if f["value"]:
            fixed = f"Қызметтер {T.fmt_num(f['value'])} өтініштің түзетілгенін хабарлады"
            if t["verification_available"]:
                fixed += f", тұрғындар {T.fmt_num(f['verified'])} растады"
                if f["reopened_by_residents"]:
                    fixed += f", {T.fmt_num(f['reopened_by_residents'])} қайта жұмысқа қайтарылды"
            out.append(fixed + ".")
        over = t["overdue"]["value"] or 0
        out.append("Мерзімі өткен өтініш жоқ." if not over else f"Мерзімі өткен өтініш: {T.fmt_num(over)}.")
    m = w.get("main_problem")
    if m:
        out.append(f"Аптаның басты мәселесі — {m['district_kk']} ауданындағы «{m['category_kk']}»: "
                   f"{T.fmt_num(m['value'])} адам шешілмеген мәселе туралы хабарлады.")
    tg = w.get("together") or {}
    if tg.get("available") and (tg.get("done_week") or tg.get("upcoming")):
        parts = []
        if tg.get("done_week"):
            parts.append(f"{T.fmt_num(tg['done_week'])} іс атқарылды ({T.fmt_num(tg['people_done'])} адам)")
        if tg.get("upcoming"):
            parts.append(f"тағы {T.fmt_num(tg['upcoming'])} іс дайындалуда")
        out.append("Тұрғындар бірге: " + ", ".join(parts) + ".")
    ag = w.get("agencies") or {}
    if ag.get("available") and (ag.get("joint") is not None or ag.get("handoffs_week") is not None):
        bits = []
        if ag.get("joint") is not None:
            bits.append(f"жұмыстағы бірлескен өтініштер — {T.fmt_num(ag['joint'])}")
        if ag.get("handoffs_week") is not None:
            bits.append(f"аптада қызметтер арасында берілгені — {T.fmt_num(ag['handoffs_week'])}")
        out.append("Ведомстволар бірге: " + ", ".join(bits) + ".")
    cr = w.get("crisis") or {}
    if cr.get("available") and cr.get("active"):
        a = cr["active"]
        out.append(f"«{a['title_kk']}» дағдарыс штабы жұмыс істеп тұр: қызметтердің {T.fmt_num(a['tasks_total'])} "
                   f"тапсырмасының {T.fmt_num(a['tasks_done'])} орындалды.")
    mt = w.get("meetings") or {}
    if mt.get("available") and mt.get("orders", {}).get("total"):
        o = mt["orders"]
        line = f"Тұрғындармен кездесу тапсырмалары: {T.fmt_num(o['total'])} тапсырманың {T.fmt_num(o['done'])} орындалды"
        if o.get("overdue"):
            line += f", {T.fmt_num(o['overdue'])} мерзімі өтті"
        out.append(line + ".")
    return out


__all__ = ["AkimError", "build", "text_kk", "text_ru"]
