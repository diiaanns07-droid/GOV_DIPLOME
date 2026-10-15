"""Блоки ответа аналитика: каждое намерение → один блок с числами, строками ru/kk, списком и действиями.

Всё, что видит аким, собирает этот файл из данных модулей-соседей (sources.py). Числа — только из ответов соседей
(значения полей, а не вычисления «на глаз»); проценты и «в N раз» — те, что уже посчитала «Картина дня» R08.
Языковая модель сюда не заходит: она может лишь выбрать порядок блоков и переписать вводную фразу без чисел (llm.py).

Блок: {id, kind, status: ok|empty|not_ready|error, title{ru,kk}, numbers[{value, label{ru,kk}, fact}],
       lines{ru:[…], kk:[…]}, items[{label{ru,kk}, value, value_text{ru,kk}, level, color, target}],
       source{role, name{ru,kk}, demo}, actions[{kind: map.focus|open, …, label{ru,kk}}], facts[…]}
"""
from __future__ import annotations

from datetime import datetime

from . import sources as S
from .texts import (MODULES, both, quoted, category_name, count_ru, district_name, fmt_num, fmt_pct, period, plural_ru,
                    service_name)

MAX_ITEMS = 5
SHOW_ON_MAP = both("Показать на карте", "Картадан көрсету")


class Block:
    def __init__(self, kind: str, role: str):
        self.kind, self.role = kind, role
        self.status = "ok"
        self.title = both("", "")
        self.numbers: list[dict] = []
        self.lines = {"ru": [], "kk": []}
        self.items: list[dict] = []
        self.actions: list[dict] = []
        self.facts: list[dict] = []
        self.demo = False
        self.note = None

    def line(self, ru: str, kk: str) -> None:
        self.lines["ru"].append(ru)
        self.lines["kk"].append(kk)

    def fact(self, value, what_ru: str, what_kk: str, fn: str) -> str:
        fid = f"{self.kind}.{len(self.facts) + 1}"
        self.facts.append({"id": fid, "value": value, "what": both(what_ru, what_kk), "role": self.role, "fn": fn})
        return fid

    def number(self, value, label_ru: str, label_kk: str, fn: str, tone: str = "neutral") -> None:
        fid = self.fact(value, label_ru, label_kk, fn)
        self.numbers.append({"value": value, "text": fmt_num(value), "label": both(label_ru, label_kk),
                             "fact": fid, "tone": tone})

    def focus(self, target: dict | None, days: int | None = None, label: dict | None = None) -> None:
        """Действие «Показать на карте»: только цели тепловой карты (объект, участок улицы, двор/ячейка)."""
        if not isinstance(target, dict) or not target.get("kind") or not target.get("id"):
            return
        action = {"kind": "map.focus", "target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk")
                                                   if target.get(k) is not None},
                  "label": label or SHOW_ON_MAP}
        if days:
            action["days"] = days
        self.actions.append(action)

    def open(self, section: str, ru: str, kk: str, opener: dict | None = None) -> None:
        """«Открыть …»: раздел оболочки; opener — функция экрана соседа, которая откроет нужную запись
        (BirgeAgencies.openCrisis, BirgeWorksCalendar.openConflict). Экран R03 вызывает только известные имена."""
        action = {"kind": "open", "section": section, "label": both(ru, kk)}
        if opener:
            action["opener"] = opener
        self.actions.append(action)

    def to_dict(self) -> dict:
        return {"id": self.kind, "kind": self.kind, "status": self.status, "title": self.title,
                "numbers": self.numbers, "lines": self.lines, "items": self.items, "actions": self.actions,
                "source": {"role": self.role, "name": MODULES.get(self.role, both(self.role, self.role)),
                           "demo": self.demo},
                "facts": self.facts, **({"note": self.note} if self.note else {})}


def _not_ready(block: Block, status: str, ru_what: str, kk_what: str) -> Block:
    """Соседа нет или он сломался: честно, без чисел и без ошибки для акима."""
    block.status = status
    if status == "not_ready":
        block.line(f"Пока нет данных: раздел {quoted(ru_what)} ещё не подключён в этой сборке.",
                   f"Әзірге дерек жоқ: {quoted(kk_what)} бөлімі бұл жинақта әлі қосылмаған.")
    else:
        block.line(f"Раздел {quoted(ru_what)} сейчас не ответил. Попробуйте ещё раз через минуту.",
                   f"{quoted(kk_what)} бөлімі қазір жауап бермеді. Бір минуттан кейін қайталаңыз.")
    return block


def _where(p) -> dict:
    """«в районе Нура» / «Нұра ауданында»; без района — «по городу» / «қала бойынша»."""
    if p.district:
        return both("в районе " + district_name(p.district, "ru"), district_name(p.district, "kk") + " ауданында")
    return both("по городу", "қала бойынша")


def _topic(p) -> dict:
    if p.category:
        return both("«" + category_name(p.category, "ru") + "»", "«" + category_name(p.category, "kk") + "»")
    return both("все темы", "барлық тақырып")


def _target_label(target: dict | None, lang: str) -> str:
    if not isinstance(target, dict):
        return ""
    return str(target.get("label_" + lang) or target.get("label_ru") or target.get("id") or "")


def _people(n) -> dict:
    return both(count_ru(n, "человек", "человека", "человек"), f"{fmt_num(n)} адам")


def _change(row: dict) -> dict | None:
    """Изменение, уже посчитанное R08 (mode pct | abs | ratio) → «на 50 % больше, чем неделю назад»."""
    trend, mode = row.get("trend"), row.get("mode")
    if trend not in ("up", "down") or row.get("prev") is None:
        return None if trend not in ("same", "flat") else both("как неделю назад", "бір апта бұрынғыдай")
    more = trend == "up"
    if mode == "ratio" and row.get("ratio"):
        r = fmt_num(float(row["ratio"]))
        return both(f"в {r} раза {'больше' if more else 'меньше'}, чем неделю назад",
                    f"бір апта бұрынғыдан {r} есе {'көп' if more else 'аз'}")
    if mode == "pct" and row.get("pct") is not None:
        p = fmt_pct(row["pct"])
        return both(f"на {p} {'больше' if more else 'меньше'}, чем неделю назад",
                    f"бір апта бұрынғыдан {p} {'көп' if more else 'аз'}")
    if row.get("abs") is not None:
        a = row["abs"]
        return both(f"на {fmt_num(a)} {'больше' if more else 'меньше'}, чем неделю назад",
                    f"бір апта бұрынғыдан {fmt_num(a)} {'көп' if more else 'аз'}")
    return None


# ---------------------------------------------------------------- горячие места (R07)

def hot_spots(ctx) -> Block:
    p, b = ctx.parsed, Block("hot_spots", "R07")
    where, topic, per = _where(p), _topic(p), period(p.days)
    b.title = both(f"Горячие места: {topic['ru']} {where['ru']}, {per['ru']}",
                   f"Шағымы көп орындар: {topic['kk']}, {where['kk']}, {per['kk']}")
    status, data = ctx.call("R07", "ui.civic_heat", "heat", S.heat_targets,
                            {"service": ctx.src.heat, "days": p.days, "district": p.district, "category": p.category})
    if status != "ok":
        return _not_ready(b, status, "Карта жалоб", "Шағымдар картасы")
    items = data["items"]
    b.demo = data["demo"]
    if not items:
        b.status = "empty"
        b.line(f"{per['ru'].capitalize()} {where['ru']} нерешённых жалоб на {topic['ru']} нет.",
               f"{per['kk'].capitalize()} {where['kk']} {topic['kk']} бойынша шешілмеген шағым жоқ.")
        return b
    total = sum(int(it.get("count") or 0) for it in items)
    b.number(total, plural_ru(total, "человек сообщил", "человека сообщили", "человек сообщили"), "адам хабарлады",
             "ui.civic_heat.heat", tone="up")
    b.number(len(items), plural_ru(len(items), "место на карте", "места на карте", "мест на карте"),
             "картадағы орын", "ui.civic_heat.heat")
    top = items[0]
    top_n = int(top.get("count") or 0)
    b.line(f"Больше всего — {quoted(_target_label(top['target'], 'ru'))}: {_people(top_n)['ru']}.",
           f"Ең көбі — {quoted(_target_label(top['target'], 'kk'))}: {_people(top_n)['kk']}.")
    b.fact(top_n, "человек — первое место", "адам — бірінші орын", "ui.civic_heat.heat")
    trend = _week_trend(ctx, total) if p.days == 7 else None
    if trend:
        b.line(trend["ru"], trend["kk"])
    for it in items[:MAX_ITEMS]:
        n = int(it.get("count") or 0)
        b.items.append({"label": both(_target_label(it["target"], "ru"), _target_label(it["target"], "kk")),
                        "value": n, "value_text": _people(n), "level": it.get("level"), "color": it.get("color"),
                        "target": {k: it["target"].get(k) for k in ("kind", "id", "label_ru", "label_kk")},
                        "district": it.get("district"), "approximate": bool(it.get("approximate"))})
    b.focus(top["target"], p.days)
    return b


def _week_trend(ctx, total: int) -> dict | None:
    """Строка «на 50 % больше, чем неделю назад» из «Картины дня» R08 — только если её число совпало с картой.

    R08 считает темы и районы ровно как карта R07 за 7 дней; совпадение value с суммой мест — проверка, что речь
    об одном и том же (иначе строку не показываем, а не подставляем чужое изменение).
    """
    p = ctx.parsed
    status, summary = ctx.summary(p.district)
    if status != "ok":
        return None
    if p.category:
        row = next((t for t in (summary.get("topics") or {}).get("items") or [] if t.get("category") == p.category), None)
    elif p.district:
        row = next((d for d in (summary.get("districts") or {}).get("items") or []
                    if d.get("district") == p.district), None)
    else:
        return None
    if not row or int(row.get("value") or -1) != int(total):
        return None
    change = _change(row)
    if not change:
        return None
    return both(f"За неделю — {_people(total)['ru']}, {change['ru']}.", f"Аптада — {_people(total)['kk']}, {change['kk']}.")


# ---------------------------------------------------------------- рост категорий (R08 темы + пульс)

def category_growth(ctx) -> Block:
    p, b = ctx.parsed, Block("category_growth", "R08")
    where = _where(p)
    b.title = both(f"Что растёт {where['ru']}: за 7 дней против прошлой недели",
                   f"{where['kk'].capitalize()} не өсіп жатыр: 7 күн мен өткен апта")
    status, summary = ctx.summary(p.district)
    if status != "ok":
        return _not_ready(b, status, "Картина дня", "Күн қорытындысы")
    b.demo = bool((summary.get("demo") or {}).get("complaints"))
    topics = (summary.get("topics") or {}).get("items") or []
    if p.category:
        topics = [t for t in topics if t.get("category") == p.category]
    growing = [t for t in topics if t.get("trend") == "up"]
    rows = growing or topics
    if not rows:
        b.status = "empty"
        b.line(f"За 7 дней {where['ru']} жалоб по этой теме нет.", f"7 күнде {where['kk']} бұл тақырып бойынша шағым жоқ.")
        return b
    # Самый заметный рост — по разнице в штуках (проценты на малой базе обманчивы, правило R08).
    rows = sorted(rows, key=lambda t: (-(t.get("abs") or 0) if t.get("trend") == "up" else 0, -(t.get("value") or 0)))
    top = rows[0]
    b.number(int(top.get("value") or 0), f"{top.get('ru')}: человек за 7 дней", f"{top.get('kk')}: 7 күнде адам",
             "ui.civic_akim.summary.topics", tone="up" if top.get("trend") == "up" else "neutral")
    if top.get("prev") is not None:
        b.number(int(top["prev"]), "неделю назад", "бір апта бұрын", "ui.civic_akim.summary.topics")
    change = _change(top)
    if change:
        b.line(f"{quoted(top.get('ru'))}: {_people(top.get('value') or 0)['ru']}, {change['ru']}.",
               f"{quoted(top.get('kk'))}: {_people(top.get('value') or 0)['kk']}, {change['kk']}.")
    if not growing:
        b.line("Ни одна тема не выросла по сравнению с прошлой неделей.",
               "Өткен аптамен салыстырғанда ешбір тақырып өспеді.")
    for t in rows[1:3]:
        ch = _change(t)
        if ch and t.get("trend") == "up":
            b.line(f"Ещё растёт {quoted(t.get('ru'))}: {_people(t.get('value') or 0)['ru']}, {ch['ru']}.",
                   f"{quoted(t.get('kk'))} да өсуде: {_people(t.get('value') or 0)['kk']}, {ch['kk']}.")
    for t in rows[:MAX_ITEMS]:
        n = int(t.get("value") or 0)
        b.items.append({"label": both(t.get("ru") or "", t.get("kk") or ""), "value": n, "value_text": _people(n),
                        "trend": t.get("trend"), "change": _change(t), "category": t.get("category")})
    # Пульс R08 уже написал фразу кодом (ru/kk) — берём её как есть: числа там посчитаны R08.
    spikes = [a for a in (summary.get("pulse") or {}).get("items") or []
              if (not p.category or a.get("category") == p.category) and isinstance(a.get("text"), dict)]
    if spikes:
        b.line(spikes[0]["text"].get("ru", ""), spikes[0]["text"].get("kk", ""))
        b.fact(spikes[0].get("value"), "сообщений за 7 дней (пульс)", "7 күндегі хабарлама (пульс)",
               "ui.civic_akim.summary.pulse")
        b.focus(spikes[0].get("target"), 7)
    b.open("day", "Открыть «Картину дня»", "«Күн қорытындысын» ашу")
    return b


# ---------------------------------------------------------------- сравнение районов (R07 / R08)

def district_compare(ctx) -> Block:
    p = ctx.parsed
    b = Block("district_compare", "R07" if p.category or p.days != 7 else "R08")
    topic = _topic(p)
    per = period(p.days)
    rows: list[dict] = []
    if p.category or p.days != 7:
        # По теме или за свой период — карта R07 (районы = сумма активных мест, как подписи «Нура · 81»).
        b.title = both(f"Районы: {topic['ru']}, {per['ru']}", f"Аудандар: {topic['kk']}, {per['kk']}")
        status, data = ctx.call("R07", "ui.civic_heat", "districts", S.heat_districts,
                                {"service": ctx.src.heat, "days": p.days, "category": p.category})
        if status != "ok":
            return _not_ready(b, status, "Карта жалоб", "Шағымдар картасы")
        b.demo = data["demo"]
        for it in data["items"]:
            d = it["target"]["id"]
            rows.append({"district": d, "value": int(it.get("count") or 0), "top": it.get("top"),
                         "level": it.get("level"), "color": it.get("color")})
    else:
        b.title = both("Районы: жалобы за 7 дней и изменение за неделю", "Аудандар: 7 күндегі шағымдар және апталық өзгеріс")
        status, summary = ctx.summary(None)
        if status != "ok":
            return _not_ready(b, status, "Картина дня", "Күн қорытындысы")
        b.demo = bool((summary.get("demo") or {}).get("complaints"))
        for it in (summary.get("districts") or {}).get("items") or []:
            rows.append({"district": it.get("district"), "value": int(it.get("value") or 0), "row": it})
    if len(p.districts) >= 2:
        rows = [r for r in rows if r["district"] in p.districts]
    rows = [r for r in rows if r["value"] > 0] or rows
    rows.sort(key=lambda r: -r["value"])
    if not rows or rows[0]["value"] == 0:
        b.status = "empty"
        b.line(f"{per['ru'].capitalize()} жалоб на {topic['ru']} в районах нет.",
               f"{per['kk'].capitalize()} аудандарда {topic['kk']} бойынша шағым жоқ.")
        return b
    first = rows[0]
    fname = {lang: district_name(first["district"], lang) for lang in ("ru", "kk")}
    b.number(first["value"], f"{fname['ru']}: человек", f"{fname['kk']}: адам", "districts", tone="up")
    if len(rows) > 1:
        second = rows[1]
        b.number(second["value"], f"{district_name(second['district'], 'ru')}: человек",
                 f"{district_name(second['district'], 'kk')}: адам", "districts")
    change = _change(first["row"]) if first.get("row") else None
    tail_ru = f", {change['ru']}" if change else ""
    tail_kk = f", {change['kk']}" if change else ""
    b.line(f"Больше всего — {fname['ru']}: {_people(first['value'])['ru']}{tail_ru}.",
           f"Ең көбі — {fname['kk']}: {_people(first['value'])['kk']}{tail_kk}.")
    if len(rows) > 1:
        last = rows[-1]
        b.line(f"Меньше всего — {district_name(last['district'], 'ru')}: {_people(last['value'])['ru']}.",
               f"Ең азы — {district_name(last['district'], 'kk')}: {_people(last['value'])['kk']}.")
    for r in rows[:6]:
        item = {"label": both(district_name(r["district"], "ru"), district_name(r["district"], "kk")),
                "value": r["value"], "value_text": _people(r["value"]), "district": r["district"],
                "level": r.get("level"), "color": r.get("color")}
        if r.get("row"):
            item["change"] = _change(r["row"])
            item["trend"] = r["row"].get("trend")
        top = (r.get("top") or {}).get("target") if isinstance(r.get("top"), dict) else None
        if top:
            item["target"] = {k: top.get(k) for k in ("kind", "id", "label_ru", "label_kk")}
        b.items.append(item)
    top_target = (first.get("top") or {}).get("target") if isinstance(first.get("top"), dict) else None
    if top_target:
        b.focus(top_target, p.days, both(f"Показать на карте: {fname['ru']}", f"Картадан көрсету: {fname['kk']}"))
    return b


# ---------------------------------------------------------------- просрочки (R08)

def _overdue_text(timer: dict) -> dict:
    n = int(timer.get("overdue_by") or 0)
    if timer.get("unit") == "work":
        return both(f"просрочено на {count_ru(n, 'рабочий день', 'рабочих дня', 'рабочих дней')}",
                    f"мерзімі {fmt_num(n)} жұмыс күнге өтті")
    return both(f"просрочено на {count_ru(n, 'день', 'дня', 'дней')}", f"мерзімі {fmt_num(n)} күнге өтті")


def overdue(ctx) -> Block:
    p, b = ctx.parsed, Block("overdue", "R08")
    where = _where(p)
    b.title = both(f"Просрочено {where['ru']}", f"Мерзімі өткен өтініштер: {where['kk']}")
    status, summary = ctx.summary(p.district)
    if status != "ok":
        return _not_ready(b, status, "Картина дня", "Күн қорытындысы")
    b.demo = bool((summary.get("demo") or {}).get("complaints"))
    part = summary.get("overdue") or {}
    items = list(part.get("items") or [])
    count, places = int(part.get("count") or 0), int(part.get("places") or 0)
    if p.service:
        sname = {lang: service_name(p.service, lang) for lang in ("ru", "kk")}
        b.title = both(f"Просрочено у службы {quoted(sname['ru'])} {where['ru']}",
                       f"{quoted(sname['kk'])} — мерзімі өткен, {where['kk']}")
        st, by_service = ctx.call("R08", "ui.civic_akim", "deadlines", S.services_from_deadlines,
                                  {"heat": ctx.src.heat, "district": p.district})
        row = next((r for r in (by_service or {}).get("items", []) if r["service"] == p.service), None) \
            if st == "ok" else None
        count = row["overdue"] if row else 0
        items = [it for it in items if (it.get("service") or {}).get("id") == p.service]
        places = None
    if count == 0:
        b.status = "empty"
        b.line(f"Просроченных обращений {where['ru']} нет — все сроки соблюдены.",
               f"{where['kk'].capitalize()} мерзімі өткен өтініш жоқ — барлық мерзім сақталған.")
        b.number(0, "просрочено", "мерзімі өткен", "ui.civic_akim.summary.overdue")
        return b
    b.number(count, plural_ru(count, "обращение просрочено", "обращения просрочены", "обращений просрочено"),
             "өтініштің мерзімі өткен", "ui.civic_akim.summary.overdue", tone="up")
    if places:
        b.number(places, plural_ru(places, "место", "места", "мест"), "орын", "ui.civic_akim.summary.overdue")
    if items:
        first = items[0]
        svc = first.get("service") or {}
        late = _overdue_text(first.get("timer") or {})
        place_ru = first.get("place_ru") or category_name(first.get("category"), "ru")
        place_kk = first.get("place_kk") or category_name(first.get("category"), "kk")
        b.line(f"Дольше всех: {quoted(place_ru)} — {svc.get('ru') or ''}, {late['ru']}.",
               f"Ең ұзағы: {quoted(place_kk)} — {svc.get('kk') or ''}, {late['kk']}.")
        b.fact(int((first.get("timer") or {}).get("overdue_by") or 0), "дней просрочки — дольше всех",
               "мерзімі өткен күн — ең ұзағы", "ui.civic_akim.summary.overdue")
        if first.get("on_map") and first.get("target"):
            b.focus(dict(first["target"], label_ru=place_ru, label_kk=place_kk), 30)
    for it in items[:MAX_ITEMS]:
        svc = it.get("service") or {}
        late = _overdue_text(it.get("timer") or {})
        b.items.append({"label": both(it.get("place_ru") or category_name(it.get("category"), "ru"),
                                      it.get("place_kk") or category_name(it.get("category"), "kk")),
                        "value": int((it.get("timer") or {}).get("overdue_by") or 0),
                        "value_text": late, "sub": both(svc.get("ru") or "", svc.get("kk") or ""),
                        "target": it.get("target") if it.get("on_map") else None, "district": it.get("district")})
    b.open("inbox", "Открыть «Обращения»", "«Өтініштерді» ашу")
    return b


# ---------------------------------------------------------------- отстающие службы (R17 → запасной расчёт R08)

def _board_rows(board) -> list[dict]:
    """Табло R17 в любом из ожидаемых видов → [{service, open, overdue, median_days, verified_pct}]."""
    rows = S.items_of(board, "services", "rows", "board")
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = r.get("service") or r.get("id") or r.get("service_id")
        if isinstance(sid, dict):
            sid = sid.get("id")
        if not isinstance(sid, str):
            continue
        share = r.get("verified_share")  # R17: доля 0…1 (или None — исправленных ещё не было)
        out.append({"service": sid,
                    "open": _int(r.get("open") if r.get("open") is not None else r.get("in_work")),
                    "overdue": _int(r.get("overdue") if r.get("overdue") is not None else r.get("late")),
                    "median_days": r.get("median_answer_days") if r.get("median_answer_days") is not None
                    else r.get("median_days"),
                    "verified_pct": r.get("verified_pct") if r.get("verified_pct") is not None
                    else (round(float(share) * 100) if isinstance(share, (int, float)) and share <= 1 else share),
                    "demo": bool(r.get("demo"))})
    return out


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def lagging_services(ctx) -> Block:
    p, b = ctx.parsed, Block("lagging_services", "R17")
    where = _where(p)
    b.title = both(f"Какие службы отстают {where['ru']}", f"Қай қызметтер артта қалып жатыр: {where['kk']}")
    # Табло R17 считает за 30 дней (как его экран); период из вопроса — если аким его назвал.
    status, board = ctx.call("R17", "ui.civic_agencies", "board_snapshot", ctx.src.agencies_board,
                             {"days": p.days if p.days_given else 30, "district": p.district})
    rows = _board_rows(board) if status == "ok" and not (isinstance(board, dict) and board.get("empty")) else []
    if rows:
        b.demo = any(r["demo"] for r in rows) or bool(isinstance(board, dict) and board.get("demo"))
        source_note = None
    else:
        # Табло R17 ещё нет: те же сроки и службы, что в «Картине дня» R08 (честная подпись источника).
        b.role = "R08"
        st, data = ctx.call("R08", "ui.civic_akim", "deadlines", S.services_from_deadlines,
                            {"heat": ctx.src.heat, "district": p.district})
        if st != "ok":
            return _not_ready(b, st, "Штаб ведомств", "Ведомстволар штабы")
        rows = data["items"]
        b.demo = bool(data.get("demo"))
        source_note = both("Табло служб ещё не подключено — посчитано по срокам «Картины дня».",
                           "Қызметтер таблосы әлі қосылмаған — «Күн қорытындысы» мерзімдері бойынша есептелді.")
    if p.service:
        rows = [r for r in rows if r["service"] == p.service] or rows
    rows = [r for r in rows if r["open"] or r["overdue"]] or rows  # табло R17 отдаёт все 20 служб, и с нулями
    lagging = sorted((r for r in rows if r["overdue"] > 0),
                     key=lambda r: (-r["overdue"], -r["open"], r["service"]))
    # Обращений просрочено — итог табло R17, если он есть: совместное обращение стоит в строках двух служб,
    # и сумма по строкам была бы больше числа обращений на экране «Штаб ведомств».
    totals = board.get("totals") if b.role == "R17" and isinstance(board, dict) else None
    total_overdue = _int(totals.get("overdue")) if isinstance(totals, dict) and "overdue" in totals and not p.service \
        else sum(r["overdue"] for r in rows)
    if not rows:
        b.status = "empty"
        b.line(f"Открытых обращений у служб {where['ru']} нет.", f"{where['kk'].capitalize()} қызметтерде ашық өтініш жоқ.")
        return b
    b.number(len(lagging), plural_ru(len(lagging), "служба с просрочками", "службы с просрочками", "служб с просрочками"),
             "мерзімі өткен өтініші бар қызмет", "services", tone="up" if lagging else "neutral")
    b.number(total_overdue, plural_ru(total_overdue, "обращение просрочено", "обращения просрочены",
                                      "обращений просрочено"), "өтініштің мерзімі өткен", "services")
    if lagging:
        worst = lagging[0]
        name_ru, name_kk = service_name(worst["service"], "ru"), service_name(worst["service"], "kk")
        b.line(f"Больше всего просрочек — {name_ru}: {fmt_num(worst['overdue'])} из {fmt_num(worst['open'])} открытых.",
               f"Мерзімі өткені ең көп — {name_kk}: {fmt_num(worst['open'])} ашық өтініштің {fmt_num(worst['overdue'])}.")
        if worst.get("median_days") is not None:
            b.line(f"Медиана ответа этой службы — {fmt_num(float(worst['median_days']))} дн.",
                   f"Бұл қызметтің жауап беру медианасы — {fmt_num(float(worst['median_days']))} күн.")
    else:
        busiest = max(rows, key=lambda r: r["open"])
        name = {lang: quoted(service_name(busiest["service"], lang)) for lang in ("ru", "kk")}
        b.line(f"Просрочек нет. Больше всего открытых обращений у службы {name['ru']}: {fmt_num(busiest['open'])}.",
               f"Мерзімі өткен өтініш жоқ. Ашық өтініш ең көп — {name['kk']}: {fmt_num(busiest['open'])}.")
    if source_note:
        b.note = source_note
    for r in (lagging or rows)[:MAX_ITEMS]:
        item = {"label": both(service_name(r["service"], "ru"), service_name(r["service"], "kk")),
                "value": r["overdue"], "service": r["service"],
                "value_text": both(f"просрочено {fmt_num(r['overdue'])} из {fmt_num(r['open'])}",
                                   f"{fmt_num(r['open'])} ішінен {fmt_num(r['overdue'])} мерзімі өткен")}
        if r.get("median_days") is not None:
            item["median_days"] = r["median_days"]
        if r.get("verified_pct") is not None:
            item["verified_pct"] = r["verified_pct"]
        b.items.append(item)
    # Место на карте — самое долгое «Просрочено» R08 у отстающих служб (по порядку отставания), если оно на карте.
    if lagging:
        st, summary = ctx.summary(p.district)
        if st == "ok":
            items = [it for it in (summary.get("overdue") or {}).get("items") or [] if it.get("on_map") and it.get("target")]
            order = [r["service"] for r in lagging]
            worst = min((it for it in items if (it.get("service") or {}).get("id") in order),
                        key=lambda it: order.index(it["service"]["id"]), default=None)
            if worst:
                b.focus(dict(worst["target"], label_ru=worst.get("place_ru"), label_kk=worst.get("place_kk")), 30)
    b.open("agencies", "Открыть «Штаб ведомств»", "«Ведомстволар штабын» ашу")
    return b


# ---------------------------------------------------------------- кризис (R17 → запасной: пульс R08)

def _incident_rows(answer) -> list[dict]:
    return [r for r in S.items_of(answer, "incidents") if isinstance(r, dict)]


def _incident_rows(answer) -> list[dict]:
    return [r for r in S.items_of(answer, "incidents") if isinstance(r, dict)]


def _incident_progress(inc: dict) -> tuple[int, int, list[str], list[str]]:
    """(сделано задач, всего, службы, службы с незаконченными задачами) — из progress R17 или из задач §5.5."""
    progress = [r for r in inc.get("progress") or [] if isinstance(r, dict)]
    if progress:
        done = sum(_int(r.get("done")) for r in progress)
        total = sum(_int(r.get("total")) for r in progress)
        services = [r["service"] for r in progress if isinstance(r.get("service"), str)]
        working = [r["service"] for r in progress if isinstance(r.get("service"), str) and _int(r.get("done")) < _int(r.get("total"))]
        return done, total, services, working
    tasks = [t for t in inc.get("tasks") or [] if isinstance(t, dict)]
    services = list(dict.fromkeys(t["service"] for t in tasks if isinstance(t.get("service"), str)))
    working = list(dict.fromkeys(t["service"] for t in tasks if isinstance(t.get("service"), str) and t.get("status") != "done"))
    return sum(1 for t in tasks if t.get("status") == "done"), len(tasks), services, working


# Вид кризиса R17 (§5.5) → тема жалоб на карте, по которой искать самое горячее место зоны.
CRISIS_CATEGORY = {"blizzard": "snow_ice", "heat_outage": "utilities", "water_outage": "utilities", "flood": "utilities"}


def crisis(ctx) -> Block:
    p, b = ctx.parsed, Block("crisis", "R17")
    b.title = both("Кризисный штаб", "Дағдарыс штабы")
    status, answer = ctx.call("R17", "ui.civic_agencies", "active_incidents", ctx.src.agencies_incidents,
                              {"status": "active", "district": None})
    incidents = [r for r in _incident_rows(answer) if r.get("status", "active") == "active"] if status == "ok" else []
    if p.district:
        incidents = [r for r in incidents if ((r.get("zone") or {}).get("district") in (None, p.district))] or incidents
    if incidents:
        inc = incidents[0]
        b.demo = bool(inc.get("demo"))
        title = both(str(inc.get("title_ru") or "Кризис"), str(inc.get("title_kk") or inc.get("title_ru") or "Дағдарыс"))
        zone_d = (inc.get("zone") or {}).get("district")
        zone_label = inc.get("zone_label") if isinstance(inc.get("zone_label"), dict) else None
        b.title = both(f"Кризисный штаб: {title['ru']}", f"Дағдарыс штабы: {title['kk']}")
        done, total, services, working = _incident_progress(inc)
        updates = [u for u in inc.get("updates") or [] if isinstance(u, dict) and u.get("public", True)]
        b.number(done, f"задач выполнено из {fmt_num(total)}", f"тапсырма орындалды ({fmt_num(total)} ішінен)",
                 "ui.civic_agencies.active_incidents", tone="neutral")
        b.number(len(services), plural_ru(len(services), "служба в штабе", "службы в штабе", "служб в штабе"),
                 "штабтағы қызмет", "ui.civic_agencies.active_incidents")
        if zone_label:
            zone_ru, zone_kk = str(zone_label.get("ru") or ""), str(zone_label.get("kk") or "")
        else:
            zone_ru = f"район {district_name(zone_d, 'ru')}" if zone_d else "зона на карте"
            zone_kk = f"{district_name(zone_d, 'kk')} ауданы" if zone_d else "картадағы аймақ"
        b.line(f"{quoted(title['ru'])} — штаб открыт, {zone_ru}. "
               f"Выполнено {fmt_num(done)} из {fmt_num(total)} задач служб.",
               f"{quoted(title['kk'])} — штаб ашық, {zone_kk}. Қызметтердің {fmt_num(total)} тапсырмасының "
               f"{fmt_num(done)} орындалды.")
        if working:
            b.line("Ещё работают: " + ", ".join(service_name(sv, "ru") for sv in working) + ".",
                   "Әлі жұмыс істеп жатыр: " + ", ".join(service_name(sv, "kk") for sv in working) + ".")
        if updates:
            b.line(f"Жителям зоны отправлено обновлений: {fmt_num(len(updates))}.",
                   f"Аймақ тұрғындарына жіберілген жаңарту: {fmt_num(len(updates))}.")
            b.fact(len(updates), "обновлений жителям", "тұрғындарға жаңарту", "ui.civic_agencies.active_incidents")
        progress = {r.get("service"): r for r in inc.get("progress") or [] if isinstance(r, dict)}
        for sv in services[:MAX_ITEMS]:
            row = progress.get(sv) or {}
            if row:
                text = both(f"сделано {fmt_num(_int(row.get('done')))} из {fmt_num(_int(row.get('total')))}",
                            f"{fmt_num(_int(row.get('total')))} ішінен {fmt_num(_int(row.get('done')))} орындалды")
            else:
                text = both("в штабе", "штабта")
            b.items.append({"label": both(service_name(sv, "ru") or "", service_name(sv, "kk") or ""),
                            "value": _int(row.get("done")) if row else None, "value_text": text, "service": sv})
        for target in ((inc.get("zone") or {}).get("targets") or [])[:1]:
            if isinstance(target, dict):
                b.focus(target, 7)
            elif isinstance(target, str) and target.startswith(("yard-", "cell-")):
                b.focus({"kind": "area", "id": target}, 7)
        if not any(a["kind"] == "map.focus" for a in b.actions) and zone_d:
            # Зона — район целиком: «Показать на карте» ведёт к самому горячему месту района по теме кризиса
            # (буран — «Снег и гололёд»), те же числа, что на карте R07.
            category = CRISIS_CATEGORY.get(str(inc.get("kind") or ""))
            st, data = ctx.call("R07", "ui.civic_heat", "heat", S.heat_targets,
                                {"service": ctx.src.heat, "days": 7, "district": zone_d, "category": category})
            if st == "ok" and data["items"]:
                top = data["items"][0]["target"]
                b.focus(top, 7, both(f"Показать на карте: {_target_label(top, 'ru')}",
                                     f"Картадан көрсету: {_target_label(top, 'kk')}"))
        b.open("crisis", "Открыть кризисный штаб", "Дағдарыс штабын ашу",
               opener={"global": "BirgeAgencies", "fn": "openCrisis", "arg": {"incident": str(inc.get("id") or "")}})
        return b
    # Штаба нет (или R17 ещё не подключён): честно говорим и показываем пульс «Картины дня» по снегу.
    b.role = "R08"
    b.title = both("Кризис: штаб не открыт", "Дағдарыс: штаб ашылмаған")
    if status in ("not_ready", "error"):
        b.note = both("Кризисный штаб пока не подключён в этой сборке — показан пульс «Картины дня».",
                      "Дағдарыс штабы бұл жинақта әлі қосылмаған — «Күн қорытындысының» пульсі көрсетілген.")
    else:
        b.note = both("Активного кризиса нет: штаб не открыт. Показан пульс «Картины дня».",
                      "Белсенді дағдарыс жоқ: штаб ашылмаған. «Күн қорытындысының» пульсі көрсетілген.")
    st, summary = ctx.summary(p.district)
    if st != "ok":
        b.status = "not_ready" if status == "not_ready" else "empty"
        b.line(b.note["ru"], b.note["kk"])
        return b
    b.demo = bool((summary.get("demo") or {}).get("complaints"))
    category = p.category or "snow_ice"
    spikes = [a for a in (summary.get("pulse") or {}).get("items") or [] if a.get("category") == category]
    if not spikes:
        b.status = "empty"
        b.line("Штаб не открыт, и пульс «Картины дня» всплеска по этой теме не видит.",
               "Штаб ашылмаған, «Күн қорытындысының» пульсі бұл тақырып бойынша секіріс көрмейді.")
        return b
    spike = spikes[0]
    b.number(int(spike.get("value") or 0), "сообщений за 7 дней (пульс)", "7 күндегі хабарлама (пульс)",
             "ui.civic_akim.summary.pulse", tone="up")
    if spike.get("ratio"):
        b.number(float(spike["ratio"]), "раза больше обычного", "есе әдеттегіден көп", "ui.civic_akim.summary.pulse",
                 tone="up")
    if isinstance(spike.get("text"), dict):
        b.line(spike["text"].get("ru", ""), spike["text"].get("kk", ""))
    for d in (spike.get("districts") or [])[:MAX_ITEMS]:
        b.items.append({"label": both(d.get("ru") or district_name(d.get("district"), "ru"),
                                      d.get("kk") or district_name(d.get("district"), "kk")),
                        "value": int(d.get("value") or 0), "district": d.get("district"),
                        "value_text": both(f"{fmt_num(d.get('value') or 0)} сообщ.", f"{fmt_num(d.get('value') or 0)} хабарлама")})
    b.focus(spike.get("target"), 7)
    if status == "ok":
        # Штаб подключён, но открыт не был: кнопка ведёт к форме нового штаба с шаблоном «Буран» (R17 crisis_link).
        b.open("crisis", "Открыть кризисный штаб", "Дағдарыс штабын ашу",
               opener={"global": "BirgeAgencies", "fn": "openCrisis",
                       "arg": {"template": "blizzard" if category == "snow_ice" else "other", "district": p.district}})
    else:
        b.open("day", "Открыть «Картину дня»", "«Күн қорытындысын» ашу")
    return b


# ---------------------------------------------------------------- конфликты работ (R12)

def work_conflicts(ctx) -> Block:
    p, b = ctx.parsed, Block("work_conflicts", "R12")
    where = _where(p)
    b.title = both(f"Конфликты работ «копаем дважды» {where['ru']}", f"Жұмыстар қайшылығы «екі рет қазу»: {where['kk']}")
    status, answer = ctx.call("R12", "engine.civic_geo", "conflicts_summary", ctx.src.works_conflicts,
                              {"district": p.district})
    if status != "ok":
        return _not_ready(b, status, "Календарь работ", "Жұмыстар күнтізбесі")
    if isinstance(answer, dict) and isinstance(answer.get("conflicts"), int):
        # R12 conflicts_summary: числа «Календаря работ» и первые конфликты.
        total, high = _int(answer.get("conflicts")), _int(answer.get("high"))
        rows = [r for r in answer.get("top") or [] if isinstance(r, dict)]
        b.demo = bool(answer.get("demo"))
    else:
        rows = [r for r in S.items_of(answer, "conflicts") if isinstance(r, dict)]
        total, high = len(rows), sum(1 for r in rows if r.get("severity") == "high")
        b.demo = any(r.get("demo") for r in rows) or bool(isinstance(answer, dict) and answer.get("demo"))
    if not total:
        b.status = "empty"
        if isinstance(answer, dict) and answer.get("source") == "none":
            b.line("В «Календаре работ» пока нет записей о работах — конфликтов искать не в чем.",
                   "«Жұмыстар күнтізбесінде» әзірге жұмыс жазбалары жоқ — қайшылық іздейтін ештеңе жоқ.")
        else:
            b.line(f"Конфликтов работ {where['ru']} не найдено.", f"{where['kk'].capitalize()} жұмыстар қайшылығы табылмады.")
        return b
    b.number(total, plural_ru(total, "конфликт работ", "конфликта работ", "конфликтов работ"),
             "жұмыстар қайшылығы", "works_conflicts", tone="up")
    b.number(high, "серьёзных", "маңызды", "works_conflicts")
    kinds = {"dig_after_surface": both("раскопка после нового асфальта", "жаңа асфальттан кейін қазу"),
             "parallel_closures": both("соседние улицы перекрыты одновременно", "көрші көшелер бір мезгілде жабылған"),
             "same_segment_overlap": both("работы на одном участке в одни дни", "бір учаскедегі жұмыстар бір күндерде")}
    first = rows[0] if rows else {}
    if first.get("advice_ru"):
        b.line(str(first["advice_ru"]), str(first.get("advice_kk") or first["advice_ru"]))
    elif first.get("title_ru"):
        street_ru, street_kk = first.get("street_ru"), first.get("street_kk")
        b.line(f"Самый важный: {first['title_ru']}" + (f" — {street_ru}" if street_ru else "") + ".",
               f"Ең маңыздысы: {first.get('title_kk') or first['title_ru']}" + (f" — {street_kk}" if street_kk else "") + ".")
    for r in rows[:MAX_ITEMS]:
        label = both(str(r["title_ru"]), str(r.get("title_kk") or r["title_ru"])) if r.get("title_ru") \
            else kinds.get(r.get("kind"), both(str(r.get("kind") or ""), str(r.get("kind") or "")))
        sub = both(str(r.get("street_ru") or ""), str(r.get("street_kk") or r.get("street_ru") or "")) \
            if r.get("street_ru") else None
        item = {"label": label, "value": None, "severity": r.get("severity"), "id": r.get("id"),
                "value_text": both("серьёзный" if r.get("severity") == "high" else "средний",
                                   "маңызды" if r.get("severity") == "high" else "орташа")}
        if sub:
            item["sub"] = sub
        b.items.append(item)
    b.open("works-calendar", "Открыть «Календарь работ»", "«Жұмыстар күнтізбесін» ашу",
           opener={"global": "BirgeWorksCalendar", "fn": "openConflict", "arg": str(first.get("id") or "")}
           if first.get("id") else None)
    return b


# ---------------------------------------------------------------- инициативы жителей (R16)

def initiatives(ctx) -> Block:
    p, b = ctx.parsed, Block("initiatives", "R16")
    where = _where(p)
    b.title = both(f"Инициативы жителей {where['ru']}", f"Тұрғындар бастамалары: {where['kk']}")
    status, answer = ctx.call("R16", "ui.civic_together", "initiatives_summary", ctx.src.together_initiatives,
                              {"district": p.district, "status": "published"})
    if status != "ok":
        return _not_ready(b, status, "Сделаем вместе", "Бірге жасайық")
    if isinstance(answer, dict) and "upcoming" in answer:
        # R16 initiatives_summary: ближайшие дела, сколько соседей придёт, поддержка акимата, сделано вместе.
        upcoming, joined = _int(answer.get("upcoming")), _int(answer.get("joined_upcoming"))
        supported, done = _int(answer.get("supported")), _int(answer.get("done"))
        neighbors_done = _int(answer.get("neighbors_done"))
        rows = [r for r in answer.get("next") or [] if isinstance(r, dict)]
        b.demo = bool(answer.get("demo"))
    else:
        all_rows = [r for r in S.items_of(answer, "initiatives") if isinstance(r, dict)]
        if p.district:
            all_rows = [r for r in all_rows if r.get("district") in (None, p.district)]
        rows = [r for r in all_rows if r.get("status", "published") == "published"]
        done_rows = [r for r in all_rows if r.get("status") == "done"]
        upcoming, joined = len(rows), sum(_int(r.get("joined")) for r in rows)
        supported = sum(1 for r in rows if (r.get("support") or {}).get("by_akimat"))
        done, neighbors_done = len(done_rows), sum(_int(r.get("joined")) for r in done_rows)
        rows = sorted(rows, key=lambda r: -_int(r.get("joined")))
        b.demo = any(r.get("demo") for r in all_rows)
    if not upcoming and not done:
        b.status = "empty"
        b.line(f"Опубликованных инициатив {where['ru']} пока нет.", f"{where['kk'].capitalize()} жарияланған бастама әзірге жоқ.")
        return b
    b.number(upcoming, plural_ru(upcoming, "инициатива впереди", "инициативы впереди", "инициатив впереди"),
             "алдағы бастама", "initiatives")
    b.number(joined, plural_ru(joined, "житель придёт", "жителя придут", "жителей придут"), "тұрғын келеді",
             "initiatives", tone="up")
    if done:
        b.number(done, plural_ru(done, "сделана вместе", "сделаны вместе", "сделано вместе"), "бірге жасалды",
                 "initiatives")
    b.line(f"Поддержано акиматом: {fmt_num(supported)}. Уже сделано вместе: {fmt_num(done)}"
           + (f", пришли {count_ru(neighbors_done, 'сосед', 'соседа', 'соседей')}." if neighbors_done else "."),
           f"Әкімдік қолдады: {fmt_num(supported)}. Бірге жасалды: {fmt_num(done)}"
           + (f", {fmt_num(neighbors_done)} көрші келді." if neighbors_done else "."))
    for r in rows[:MAX_ITEMS]:
        n = _int(r.get("joined"))
        target = r.get("target") if isinstance(r.get("target"), dict) else None
        title = str(r.get("title") or "")
        b.items.append({"label": both(title, str(r.get("title_kk") or title)), "value": n,
                        "value_text": both(f"придут {fmt_num(n)}", f"{fmt_num(n)} адам келеді"),
                        "status": r.get("status"), "target": target})
    first_target = rows[0].get("target") if rows and isinstance(rows[0].get("target"), dict) else None
    if first_target and first_target.get("kind") in ("object", "segment", "area"):
        b.focus(first_target)
    b.open("together", "Открыть «Сделаем вместе»", "«Бірге жасайық» ашу")
    return b


# ---------------------------------------------------------------- поручения встреч (R13)

def meeting_orders(ctx) -> Block:
    p, b = ctx.parsed, Block("meeting_orders", "R13")
    where = _where(p)
    b.title = both(f"Поручения после встреч с жителями {where['ru']}",
                   f"Тұрғындармен кездесулерден кейінгі тапсырмалар: {where['kk']}")
    status, answer = ctx.call("R13", "ui.civic_meetings", "board_block", ctx.src.meetings_list, {"district": p.district})
    if status != "ok":
        return _not_ready(b, status, "Встречи с акимом", "Әкіммен кездесулер")
    today = ctx.now.date().isoformat()
    if isinstance(answer, dict) and isinstance(answer.get("counts"), dict):
        # R13 board_block: счётчики всех поручений и открытые (сначала просроченные).
        counts = answer["counts"]
        total, done, late_n = _int(counts.get("total")), _int(counts.get("done")), _int(counts.get("overdue"))
        shown = [o for o in answer.get("orders") or [] if isinstance(o, dict)]
        b.demo = bool(answer.get("demo"))
    else:
        meetings = [m for m in S.items_of(answer, "meetings") if isinstance(m, dict)]
        if p.district:
            meetings = [m for m in meetings if m.get("district") in (None, p.district)]
        orders = [o for m in meetings for o in (m.get("orders") or []) if isinstance(o, dict)]
        late = [o for o in orders if o.get("status") != "done" and isinstance(o.get("due"), str) and o["due"][:10] < today]
        total, done, late_n = len(orders), sum(1 for o in orders if o.get("status") == "done"), len(late)
        shown = late + [o for o in orders if o not in late and o.get("status") != "done"]
        b.demo = any(m.get("demo") for m in meetings)
    if not total:
        b.status = "empty"
        b.line(f"Поручений по итогам встреч {where['ru']} пока нет.",
               f"{where['kk'].capitalize()} кездесулер бойынша тапсырма әзірге жоқ.")
        return b
    b.number(total, plural_ru(total, "поручение", "поручения", "поручений"), "тапсырма", "meetings")
    b.number(done, "выполнено", "орындалды", "meetings", tone="neutral")
    b.number(late_n, "просрочено", "мерзімі өткен", "meetings", tone="up" if late_n else "neutral")
    b.line(f"Выполнено {fmt_num(done)} из {fmt_num(total)}; просрочено {fmt_num(late_n)}.",
           f"{fmt_num(total)} тапсырманың {fmt_num(done)} орындалды; мерзімі өткені — {fmt_num(late_n)}.")
    for o in shown[:MAX_ITEMS]:
        b.items.append({"label": both(str(o.get("text_ru") or ""), str(o.get("text_kk") or o.get("text_ru") or "")),
                        "value": None, "status": o.get("status"), "due": o.get("due"),
                        "sub": both(service_name(o.get("service"), "ru") or "", service_name(o.get("service"), "kk") or "")})
    b.open("meetings", "Открыть «Встречи с акимом»", "«Әкіммен кездесулерді» ашу")
    return b


# ---------------------------------------------------------------- прогноз (R13, прототип на синтетике)

def forecast(ctx) -> Block:
    p, b = ctx.parsed, Block("forecast", "R13F")
    where = _where(p)
    status, data = ctx.call("R13", "ui.civic_forecast", "forecast_response", ctx.src.forecast,
                            {"month": None, "district": p.district, "k": 5})
    if status != "ok" or not isinstance(data, dict):
        b.title = both("Прогноз проблемных мест", "Проблемалы жерлер болжамы")
        return _not_ready(b, status if status != "ok" else "error", "Прогноз", "Болжам")
    month = str(data.get("month") or "")
    b.title = both(f"Прогноз на {month} {where['ru']}", f"{month} болжамы: {where['kk']}")
    b.demo = True
    items = [it for it in data.get("items") or [] if isinstance(it, dict)]
    if p.category:
        items = [it for it in items if it.get("main_category") == p.category] or items
    if not items:
        b.status = "empty"
        b.line("Прогноз не нашёл мест с высоким риском.", "Болжам тәуекелі жоғары жерді таппады.")
        return b
    high = sum(1 for it in items if it.get("level") == "high")
    b.number(high, plural_ru(high, "место с высоким риском", "места с высоким риском", "мест с высоким риском"),
             "тәуекелі жоғары орын", "ui.civic_forecast.forecast_response", tone="up" if high else "neutral")
    first = items[0]
    reasons = first.get("top_reasons") or []
    b.line(f"Первое в списке — {quoted(_target_label(first.get('target'), 'ru'))}.",
           f"Тізімде бірінші — {quoted(_target_label(first.get('target'), 'kk'))}.")
    if reasons and isinstance(reasons[0], dict):
        b.line(str(reasons[0].get("ru") or ""), str(reasons[0].get("kk") or reasons[0].get("ru") or ""))
    b.note = both(str(data.get("note_ru") or "Прототип на синтетике."), str(data.get("note_kk") or data.get("note_ru") or ""))
    for it in items[:MAX_ITEMS]:
        b.items.append({"label": both(_target_label(it.get("target"), "ru"), _target_label(it.get("target"), "kk")),
                        "value": None, "level": it.get("level"),
                        "value_text": both("высокий риск" if it.get("level") == "high" else "средний риск",
                                           "жоғары тәуекел" if it.get("level") == "high" else "орташа тәуекел"),
                        "target": it.get("target")})
    b.focus(first.get("target"))
    return b


# ---------------------------------------------------------------- сводка дня (R08)

def day_summary(ctx) -> Block:
    p, b = ctx.parsed, Block("day_summary", "R08")
    where = _where(p)
    b.title = both(f"Картина дня {where['ru']}", f"Күн қорытындысы: {where['kk']}")
    status, summary = ctx.summary(p.district)
    if status != "ok":
        return _not_ready(b, status, "Картина дня", "Күн қорытындысы")
    b.demo = bool((summary.get("demo") or {}).get("any"))
    kpi = summary.get("kpi") or {}
    if kpi.get("new_day"):
        b.number(int(kpi["new_day"].get("value") or 0), "новых обращений сегодня", "бүгінгі жаңа өтініш",
                 "ui.civic_akim.summary.kpi", tone="up" if kpi["new_day"].get("trend") == "up" else "neutral")
    if kpi.get("in_progress"):
        b.number(int(kpi["in_progress"].get("value") or 0), "в работе", "жұмыста", "ui.civic_akim.summary.kpi")
    if kpi.get("overdue"):
        b.number(int(kpi["overdue"].get("value") or 0), "просрочено", "мерзімі өткен", "ui.civic_akim.summary.kpi",
                 tone="up" if (kpi["overdue"].get("value") or 0) > 0 else "neutral")
    parts = summary.get("text_parts") or {}
    for ru, kk in zip(parts.get("ru") or [], parts.get("kk") or []):
        if isinstance(ru, dict) and isinstance(kk, dict) and ru.get("role") != "new":
            b.line(str(ru.get("text") or ""), str(kk.get("text") or ""))
        if len(b.lines["ru"]) >= 3:
            break
    hot = ((summary.get("hot") or {}).get("items") or [])
    if hot:
        b.focus(hot[0].get("target"), 7)
    b.open("day", "Открыть «Картину дня»", "«Күн қорытындысын» ашу")
    return b


BUILDERS = {
    "hot_spots": hot_spots,
    "category_growth": category_growth,
    "district_compare": district_compare,
    "overdue": overdue,
    "lagging_services": lagging_services,
    "crisis": crisis,
    "work_conflicts": work_conflicts,
    "initiatives": initiatives,
    "meeting_orders": meeting_orders,
    "forecast": forecast,
    "day_summary": day_summary,
}
INTENTS = tuple(BUILDERS)


def now_astana(now: datetime | None) -> datetime:
    return (now or datetime.now(S.ASTANA_TZ)).astimezone(S.ASTANA_TZ)
