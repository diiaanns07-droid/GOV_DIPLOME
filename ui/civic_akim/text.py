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


def fmt_date(iso_date: str, lang: str, ref_year: int | None = None) -> str:
    """«5 окт»; год добавляется, если он не текущий (как BirgeI18n.formatDate): «5 окт 2025»."""
    d = Date.fromisoformat(iso_date)
    out = f"{d.day}{NBSP}{month_short(d.month, lang)}"
    return out + f"{NBSP}{d.year}" if ref_year is not None and d.year != ref_year else out


def _ref_year(s: dict) -> int | None:
    """Текущий год по Астане — из момента расчёта сводки (generated_at)."""
    try:
        return int(str(s.get("generated_at") or "")[:4])
    except ValueError:
        return None


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
    when = fmt_date(s["date"], "ru", _ref_year(s))
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
    when = fmt_date(s["date"], "kk", _ref_year(s))
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


def _fixed_ru(s: dict) -> str:
    """«За неделю исправлено 142: жители подтвердили 37, вернули в работу 3.» — только если проверка жителями есть в данных."""
    f = s["kpi"].get("fixed_week") or {}
    if not s["kpi"].get("verification_available") or not f.get("value") and not f.get("reopened"):
        return ""
    n = f["value"]
    out = f"За неделю исправлено {fmt_num(n)}: жители подтвердили {fmt_num(f['verified'])}"
    if f.get("reopened"):
        out += f", вернули в работу {fmt_num(f['reopened'])}"
    return out + "."


def _fixed_kk(s: dict) -> str:
    f = s["kpi"].get("fixed_week") or {}
    if not s["kpi"].get("verification_available") or not f.get("value") and not f.get("reopened"):
        return ""
    out = f"Аптада түзетілгені: {fmt_num(f['value'])}, тұрғындар растағаны: {fmt_num(f['verified'])}"
    if f.get("reopened"):
        out += f", қайта жұмысқа қайтарылғаны: {fmt_num(f['reopened'])}"
    return out + "."


def _decisions_ru(s: dict) -> str:
    n = len((s.get("decisions") or {}).get("items") or [])
    if not n:
        return ""
    return f"Ждут вашего решения: {fmt_num(n)} {plural_ru(n, 'вопрос', 'вопроса', 'вопросов')}."


def _decisions_kk(s: dict) -> str:
    n = len((s.get("decisions") or {}).get("items") or [])
    return f"Сіздің шешіміңізді күтетін мәселе: {fmt_num(n)}." if n else ""


# ---------------------------------------------------------------- «Пульс» (pulse.py)

def _place(a: dict, lang: str) -> str:
    t = a.get("target") or {}
    label = t.get(f"label_{lang}") or t.get("label_ru")
    if not label and t.get("kind"):
        label = _dict(lang).get("heat.kind." + t["kind"]) or _dict("ru").get("heat.kind." + t["kind"])
    return label or (a.get(f"category_{lang}") or "")


def _base_txt(base: float) -> str:
    """Обычный уровень: от 3 — целым («в среднем 10»), меньше — с одной цифрой после запятой («1,5»)."""
    return fmt_num(int(round(base))) if base >= 3 or float(base).is_integer() else fmt_ratio(round(base, 1))


def _city_list(a: dict, lang: str) -> str:
    rows = a.get("districts") or []
    names = ", ".join(r[lang] for r in rows[:3])
    rest = len(rows) - 3
    if rest > 0:
        names += f" и ещё {fmt_num(rest)}" if lang == "ru" else f" және тағы {fmt_num(rest)}"
    return names


def pulse_ru(a: dict) -> str:
    cat, dist, n = a.get("category_ru") or "Другое", a.get("district_ru"), a["value"]
    where = f"«{cat}» в районе {dist}" if dist else f"«{cat}»"
    reports = plural_ru(n, "сообщение", "сообщения", "сообщений")
    if a["kind"] == "spike_city":
        k = len(a.get("districts") or [])
        r = a["ratio"]
        return (f"«{cat}» — всплеск в {fmt_num(k)} {plural_ru(k, 'районе', 'районах', 'районах')} ({_city_list(a, 'ru')}): "
                f"{fmt_num(n)} {reports} за 7 дней, в {fmt_ratio(r)} {plural_ru(r, 'раз', 'раза', 'раз')} больше обычного.")
    if a["kind"] == "spike":
        r = a["ratio"]
        return (f"{where}: {fmt_num(n)} {reports} за 7 дней — в {fmt_ratio(r)} {plural_ru(r, 'раз', 'раза', 'раз')} "
                f"больше обычного (в среднем {_base_txt(a['base'])} в неделю за {fmt_num(a['weeks'])} {plural_ru(a['weeks'], 'неделю', 'недели', 'недель')}).")
    if a["kind"] == "spike_new":
        return f"{where}: {fmt_num(n)} {reports} за 7 дней — за прошлые {fmt_num(a['weeks'])} {plural_ru(a['weeks'], 'неделю', 'недели', 'недель')} таких не было."
    if a["kind"] == "new_hot":
        people = plural_ru(n, "человек", "человека", "человек")
        return f"Новое горячее место: {_place(a, 'ru')} — {fmt_num(n)} {people} за 7 дней, неделю назад его на карте не было."
    return f"Чаще жмут «Я тоже»: {_place(a, 'ru')} — +{fmt_num(n)} за неделю (неделей раньше — {fmt_num(a.get('prev') or 0)})."


def pulse_kk(a: dict) -> str:
    cat, dist, n = a.get("category_kk") or "Басқа", a.get("district_kk"), a["value"]
    where = f"{dist} ауданында «{cat}»" if dist else f"«{cat}»"
    if a["kind"] == "spike_city":
        k = len(a.get("districts") or [])
        return (f"«{cat}» — {fmt_num(k)} ауданда күрт өсу ({_city_list(a, 'kk')}): 7 күнде {fmt_num(n)} хабарлама, "
                f"әдеттегіден {fmt_ratio(a['ratio'])} есе көп.")
    if a["kind"] == "spike":
        return (f"{where}: 7 күнде {fmt_num(n)} хабарлама — әдеттегіден {fmt_ratio(a['ratio'])} есе көп "
                f"(соңғы {fmt_num(a['weeks'])} аптада аптасына орта есеппен {_base_txt(a['base'])}).")
    if a["kind"] == "spike_new":
        return f"{where}: 7 күнде {fmt_num(n)} хабарлама — алдыңғы {fmt_num(a['weeks'])} аптада мұндай болмаған."
    if a["kind"] == "new_hot":
        return f"Жаңа ыстық нүкте: {_place(a, 'kk')} — 7 күнде {fmt_num(n)} адам, бір апта бұрын картада болмаған."
    return f"«Мен де» жиі басылады: {_place(a, 'kk')} — аптасына +{fmt_num(n)} (алдыңғы аптада — {fmt_num(a.get('prev') or 0)})."


def render_parts(summary: dict, lang: str = "ru") -> list[dict]:
    """Фразы сводки с ролью: new, main (главная проблема — интерфейс выделяет её), overdue, fixed, decisions, objects."""
    if summary.get("complaints_available") is False:  # нет источника жалоб — не выдумываем нули
        no_data = ("Өтініштер туралы деректер әлі қосылмаған." if lang == "kk"
                   else "Данные об обращениях пока не подключены.")
        objects = _objects_kk(summary) if lang == "kk" else _objects_ru(summary)
        return [{"role": "new", "text": no_data}] + ([{"role": "objects", "text": objects}] if objects else [])
    if lang == "kk":
        fns = (("new", _new_kk), ("main", _main_kk), ("overdue", _overdue_kk), ("fixed", _fixed_kk),
               ("decisions", _decisions_kk), ("objects", _objects_kk))
    else:
        fns = (("new", _new_ru), ("main", _main_ru), ("overdue", _overdue_ru), ("fixed", _fixed_ru),
               ("decisions", _decisions_ru), ("objects", _objects_ru))
    return [{"role": role, "text": t} for role, fn in fns if (t := fn(summary))]


def render(summary: dict, lang: str = "ru") -> str:
    """Сводка одним абзацем. lang: ru | kk."""
    return " ".join(p["text"] for p in render_parts(summary, lang))
