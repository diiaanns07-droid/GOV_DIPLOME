"""Текстовая сводка «Картины дня» по шаблону — ru и kk, без внешних API и без LLM (работает офлайн).

    «Сегодня 34 новых обращения. Больше всего жалоб — «Снег и гололёд» в районе Нура: за 7 дней
     сообщили 12 человек, это на 40 % больше, чем неделю назад. Просрочено 5 обращений.
     3 объекта отстают от графика.»

Правила языка:
- ru: три формы числа (1 обращение, 2 обращения, 5 обращений; 11–14 — «много»), прилагательное и
  глагол согласуются с числом («1 новое обращение», «сообщил 21 человек», «1 объект отстаёт»).
- kk: существительное после числа не меняется («34 жаңа өтініш», «12 адам»). Падежные окончания
  на числах (3-ке, 10-ға) зависят от звучания числа — поэтому их избегаем: «бір апта бұрын — 9».
- Названия районов и месяцев — из словарей R11 (web/civic/i18n/ru.json, kk.json), категории — из
  categories_v2.json; ничего не переписываем руками. Числа «1 666» с неразрывным пробелом, «40 %».
Казахские фразы — на проверку владельцу (список в research/round-14-results/R08/INTEGRATION.txt).
"""
from __future__ import annotations

import json
from datetime import date as Date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = ROOT / "web" / "civic" / "i18n"
NBSP = " "


@lru_cache(maxsize=2)
def _dict(lang: str) -> dict:
    try:
        return json.loads((I18N_DIR / f"{lang}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def district_name(district_id: str | None, lang: str) -> str | None:
    if not district_id:
        return None
    return _dict(lang).get("district." + district_id) or _dict("ru").get("district." + district_id)


def month_short(month: int, lang: str) -> str:
    return _dict(lang).get(f"dates.month_short.{month}") or _dict("ru").get(f"dates.month_short.{month}") or str(month)


# ---------------------------------------------------------------- числа

def fmt_num(value) -> str:
    """1666 → «1 666» (неразрывный пробел), −12 → «−12». Как BirgeI18n.formatNumber."""
    n = int(value)
    body = f"{abs(n):,}".replace(",", NBSP)
    return ("−" if n < 0 else "") + body


def fmt_pct(value) -> str:
    return fmt_num(value) + NBSP + "%"


def fmt_ratio(value: float) -> str:
    """2.5 → «2,5», 3.0 → «3»."""
    if float(value).is_integer():
        return fmt_num(int(value))
    return f"{value:.1f}".replace(".", ",")


def plural_ru(n, one: str, few: str, many: str) -> str:
    """Форма для русского: 1, 21 — one; 2–4, 22–24 — few; 0, 5–20, 11–14 — many; дробное — few."""
    if isinstance(n, float) and not n.is_integer():
        return few
    a = abs(int(n))
    if a % 10 == 1 and a % 100 != 11:
        return one
    if 2 <= a % 10 <= 4 and not 12 <= a % 100 <= 14:
        return few
    return many


def fmt_date(iso_date: str, lang: str) -> str:
    d = Date.fromisoformat(iso_date)
    return f"{d.day}{NBSP}{month_short(d.month, lang)}"


# ---------------------------------------------------------------- изменение «чем неделю назад»

def delta_ru(ch: dict) -> str:
    """Хвост фразы после запятой: «это на 40 % больше, чем неделю назад»."""
    mode, trend = ch.get("mode"), ch.get("trend")
    if trend == "flat":
        return "столько же, сколько неделю назад"
    if mode == "new":
        return "неделю назад таких жалоб не было"
    word = "больше" if trend == "up" else "меньше"
    if mode == "ratio":
        r = ch["ratio"]
        return f"это в {fmt_ratio(r)} {plural_ru(r, 'раз', 'раза', 'раз')} больше, чем неделю назад"
    if mode == "pct":
        return f"это на {fmt_pct(ch['pct'])} {word}, чем неделю назад"
    return f"это на {fmt_num(ch['abs'])} {word}, чем неделю назад"


def delta_kk(ch: dict) -> str:
    """Казахский хвост. Абсолютную разницу даём как «бір апта бұрын — 9» (без падежа на числе)."""
    mode, trend = ch.get("mode"), ch.get("trend")
    if trend == "flat":
        return ", бұл бір апта бұрынғымен бірдей"
    if mode == "new":
        return ", бір апта бұрын мұндай шағым болмаған"
    if mode == "ratio":
        return f", бұл бір апта бұрынғыдан {fmt_ratio(ch['ratio'])} есе көп"
    if mode == "pct":
        return f", бұл бір апта бұрынғыдан {fmt_pct(ch['pct'])} {'көп' if trend == 'up' else 'аз'}"
    return f" (бір апта бұрын — {fmt_num(ch['prev'])})"


# ---------------------------------------------------------------- предложения

def _new_ru(s: dict) -> str:
    n = s["kpi"]["new_day"]["value"]
    d = s.get("district")
    place = f" в районе {d['ru']}" if d else ""
    if s.get("is_today"):
        if n == 0:
            return f"Сегодня{place} новых обращений нет."
        noun = plural_ru(n, "новое обращение", "новых обращения", "новых обращений")
        return f"Сегодня{place} {fmt_num(n)} {noun}."
    when = fmt_date(s["date"], "ru")
    if n == 0:
        return f"{when}{place} новых обращений не было."
    noun = plural_ru(n, "новое обращение", "новых обращения", "новых обращений")
    return f"{when}{place} — {fmt_num(n)} {noun}."


def _new_kk(s: dict) -> str:
    n = s["kpi"]["new_day"]["value"]
    d = s.get("district")
    place = f" {d['kk']} ауданында" if d else ""
    if s.get("is_today"):
        if n == 0:
            return f"Бүгін{place} жаңа өтініш жоқ."
        return f"Бүгін{place} {fmt_num(n)} жаңа өтініш түсті."
    when = fmt_date(s["date"], "kk")
    if n == 0:
        return f"{when} күні{place} жаңа өтініш болған жоқ."
    return f"{when} күні{place} {fmt_num(n)} жаңа өтініш түсті."


def _main_ru(s: dict) -> str:
    m = s.get("main_problem")
    if not m:
        return ""
    n = m["value"]
    # Район уже назван в первой фразе, если выбран фильтр, — не повторяем.
    place = f" в районе {m['district_ru']}" if m.get("district_ru") and not s.get("district") else ""
    verb = plural_ru(n, "сообщил", "сообщили", "сообщили")
    people = plural_ru(n, "человек", "человека", "человек")
    days = s.get("heat_days", 7)
    return (f"Больше всего жалоб — «{m['category_ru']}»{place}: за {fmt_num(days)} "
            f"{plural_ru(days, 'день', 'дня', 'дней')} {verb} "
            f"{fmt_num(n)} {people}, {delta_ru(m)}.")


def _main_kk(s: dict) -> str:
    m = s.get("main_problem")
    if not m:
        return ""
    place = f", {m['district_kk']} ауданында" if m.get("district_kk") and not s.get("district") else ""
    days = s.get("heat_days", 7)
    return (f"Ең көп шағым — «{m['category_kk']}»{place}: соңғы {fmt_num(days)} күнде "
            f"{fmt_num(m['value'])} адам хабарлады{delta_kk(m)}.")


def _overdue_ru(s: dict) -> str:
    n = s["kpi"]["overdue"]["value"]
    if n == 0:
        return "Просроченных обращений нет."
    return f"Просрочено {fmt_num(n)} {plural_ru(n, 'обращение', 'обращения', 'обращений')}."


def _overdue_kk(s: dict) -> str:
    n = s["kpi"]["overdue"]["value"]
    return "Мерзімі өткен өтініш жоқ." if n == 0 else f"Мерзімі өткен өтініш: {fmt_num(n)}."


def _objects_ru(s: dict) -> str:
    o = s.get("objects") or {}
    if not o.get("available") or not o.get("total"):
        return ""
    parts = []
    late, stale = o.get("late_count", 0), o.get("stale_count", 0)
    if late:
        parts.append(f"{fmt_num(late)} {plural_ru(late, 'объект отстаёт', 'объекта отстают', 'объектов отстают')} от графика.")
    else:
        parts.append("Объектов с отставанием нет.")
    if stale:
        parts.append(f"{fmt_num(stale)} {plural_ru(stale, 'объект давно не обновлялся', 'объекта давно не обновлялись', 'объектов давно не обновлялись')}.")
    return " ".join(parts)


def _objects_kk(s: dict) -> str:
    o = s.get("objects") or {}
    if not o.get("available") or not o.get("total"):
        return ""
    late, stale = o.get("late_count", 0), o.get("stale_count", 0)
    parts = [f"Кестеден қалып жатқан нысан: {fmt_num(late)}." if late else "Кестеден қалып жатқан нысан жоқ."]
    if stale:
        parts.append(f"Көптен бері жаңартылмаған нысан: {fmt_num(stale)}.")
    return " ".join(parts)


def render_parts(summary: dict, lang: str = "ru") -> list[dict]:
    """Фразы сводки с ролью: new, main (главная проблема — интерфейс выделяет её), overdue, objects."""
    if summary.get("complaints_available") is False:  # нет источника жалоб — не выдумываем нули
        no_data = ("Өтініштер туралы дерек әлі қосылмаған." if lang == "kk"
                   else "Данные об обращениях пока не подключены.")
        objects = _objects_kk(summary) if lang == "kk" else _objects_ru(summary)
        return [{"role": "new", "text": no_data}] + ([{"role": "objects", "text": objects}] if objects else [])
    if lang == "kk":
        fns = (("new", _new_kk), ("main", _main_kk), ("overdue", _overdue_kk), ("objects", _objects_kk))
    else:
        fns = (("new", _new_ru), ("main", _main_ru), ("overdue", _overdue_ru), ("objects", _objects_ru))
    return [{"role": role, "text": t} for role, fn in fns if (t := fn(summary))]


def render(summary: dict, lang: str = "ru") -> str:
    """Сводка одним абзацем. lang: ru | kk."""
    return " ".join(p["text"] for p in render_parts(summary, lang))
