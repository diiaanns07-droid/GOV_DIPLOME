"""Слова и числа аналитика: названия районов, категорий, служб, формы чисел (ru/kk).

Правила языка — как у «Картины дня» R08 (ui/civic_akim/text.py):
- ru: три формы числа (1 жалоба, 2 жалобы, 5 жалоб; 11–14 — «много»);
- kk: существительное после числа не меняется («15 адам»); падежных окончаний на числах избегаем —
  пишем «Мерзімі өткен: 5», а не «5-ке».
Числа: «1 666» с неразрывным пробелом, проценты «40 %». Названия районов — из словарей R11, категории —
из research/round-14/categories_v2.json, службы — из таблицы R08 (ui.civic_akim.routing); если соседа нет —
запасной словарь ниже (те же id, CONTRACT §3).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CATEGORIES_FILE = ROOT / "research" / "round-14" / "categories_v2.json"
NBSP = " "
LANGS = ("ru", "kk")

# Районы Астаны (id как у R07 geo.districts и R08). Запас, если словарь R11 недоступен.
DISTRICTS = {
    "almaty": {"ru": "Алматы", "kk": "Алматы"},
    "baikonur": {"ru": "Байконур", "kk": "Байқоңыр"},
    "esil": {"ru": "Есиль", "kk": "Есіл"},
    "nura": {"ru": "Нура", "kk": "Нұра"},
    "saraishyk": {"ru": "Сарайшык", "kk": "Сарайшық"},
    "saryarka": {"ru": "Сарыарка", "kk": "Сарыарқа"},
}

# Службы — CONTRACT §3 (те же id, что у R09 SERVICES и таблицы R08). Названия — запас, если R08 нет.
SERVICES = {
    "road": {"ru": "Дорожная служба", "kk": "Жол қызметі"},
    "traffic": {"ru": "Служба светофоров и разметки", "kk": "Бағдаршам және жол таңбасы қызметі"},
    "street_cleaning": {"ru": "Служба уборки улиц", "kk": "Көшелерді тазалау қызметі"},
    "transport": {"ru": "Служба общественного транспорта", "kk": "Қоғамдық көлік қызметі"},
    "lighting": {"ru": "Служба освещения", "kk": "Жарықтандыру қызметі"},
    "landscaping": {"ru": "Служба благоустройства", "kk": "Абаттандыру қызметі"},
    "greenery": {"ru": "Служба озеленения", "kk": "Көгалдандыру қызметі"},
    "waste": {"ru": "Оператор вывоза мусора", "kk": "Қоқыс шығару операторы"},
    "utilities": {"ru": "Служба ЖКХ", "kk": "ТКШ қызметі"},
    "heating": {"ru": "Теплосеть", "kk": "Жылу желісі"},
    "water": {"ru": "Водоканал", "kk": "Сумен жабдықтау қызметі"},
    "power": {"ru": "Электросети", "kk": "Электр желілері"},
    "gas": {"ru": "Газовая служба", "kk": "Газ қызметі"},
    "housing": {"ru": "Управляющая компания дома", "kk": "Үйді басқарушы компания"},
    "ecology": {"ru": "Служба экологии", "kk": "Экология қызметі"},
    "emergency": {"ru": "Служба спасения", "kk": "Құтқару қызметі"},
    "police": {"ru": "Полиция", "kk": "Полиция"},
    "animals": {"ru": "Служба отлова животных", "kk": "Жануарларды аулау қызметі"},
    "parking": {"ru": "Служба парковок", "kk": "Тұрақ қызметі"},
    "akimat": {"ru": "Аппарат акима района", "kk": "Аудан әкімінің аппараты"},
}

# Подписи модулей-источников для «Как получен ответ».
MODULES = {
    "R07": {"ru": "Карта жалоб", "kk": "Шағымдар картасы"},
    "R08": {"ru": "Картина дня", "kk": "Күн қорытындысы"},
    "R12": {"ru": "Календарь работ", "kk": "Жұмыстар күнтізбесі"},
    "R13": {"ru": "Встречи с акимом", "kk": "Әкіммен кездесулер"},
    "R13F": {"ru": "Прогноз проблемных мест", "kk": "Проблемалы жерлер болжамы"},
    "R16": {"ru": "Сделаем вместе", "kk": "Бірге жасайық"},
    "R17": {"ru": "Штаб ведомств", "kk": "Ведомстволар штабы"},
}


@lru_cache(maxsize=1)
def _categories() -> dict:
    try:
        data = json.loads(CATEGORIES_FILE.read_text("utf-8"))
        return {c["id"]: {"ru": c["ru"], "kk": c["kk"], "icon": c.get("icon")} for c in data["categories"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def category_name(category_id: str | None, lang: str) -> str | None:
    if not category_id:
        return None
    item = _categories().get(category_id)
    return item[lang] if item else category_id


def category_ids() -> tuple[str, ...]:
    return tuple(_categories())


@lru_cache(maxsize=1)
def _service_table() -> dict:
    """Названия служб из таблицы R08 (её правит сотрудник); нет R08 — запасной словарь CONTRACT §3."""
    try:
        from ui.civic_akim import routing  # type: ignore
        table = routing.table().get("services") or {}
        merged = {k: dict(v) for k, v in SERVICES.items()}
        for key, names in table.items():
            if isinstance(names, dict) and names.get("ru"):
                merged[key] = {"ru": str(names["ru"]), "kk": str(names.get("kk") or names["ru"])}
        return merged
    except Exception:  # noqa: BLE001 — сосед необязателен
        return {k: dict(v) for k, v in SERVICES.items()}


def service_name(service_id: str | None, lang: str) -> str | None:
    if not service_id:
        return None
    names = _service_table().get(service_id)
    return names[lang] if names else service_id


def district_name(district_id: str | None, lang: str) -> str | None:
    if not district_id:
        return None
    names = DISTRICTS.get(district_id)
    return names[lang] if names else district_id


def names(fn, key) -> dict:
    """{ru, kk} одной функцией: names(district_name, "nura") → {"ru": "Нура", "kk": "Нұра"}."""
    return {lang: fn(key, lang) for lang in LANGS}


# ---------------------------------------------------------------- числа

def fmt_num(value) -> str:
    """1666 → «1 666», 2.5 → «2,5», −12 → «−12»."""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.1f}".replace(".", ",").replace("-", "−")
    n = int(value)
    body = f"{abs(n):,}".replace(",", NBSP)
    return ("−" if n < 0 else "") + body


def fmt_pct(value) -> str:
    return fmt_num(value) + NBSP + "%"


def plural_ru(n, one: str, few: str, many: str) -> str:
    if isinstance(n, float) and not n.is_integer():
        return few
    a = abs(int(n))
    if a % 10 == 1 and a % 100 != 11:
        return one
    if 2 <= a % 10 <= 4 and not 12 <= a % 100 <= 14:
        return few
    return many


def count_ru(n, one: str, few: str, many: str) -> str:
    """«15 жалоб», «1 служба»."""
    return f"{fmt_num(n)} {plural_ru(n, one, few, many)}"


def days_ru(n: int) -> str:
    return count_ru(n, "день", "дня", "дней")


def period(days: int) -> dict:
    """«за 7 дней» / «7 күнде»; 1 — «за сутки» / «соңғы тәулікте»."""
    if days == 1:
        return {"ru": "за сутки", "kk": "соңғы тәулікте"}
    return {"ru": "за " + days_ru(days), "kk": f"{fmt_num(days)} күнде"}


def quoted(text) -> str:
    """«Название» с вложенными кавычками по правилам: «Двор ЖК „BI City Tokyo“», а не «Двор ЖК «BI City Tokyo»»."""
    return "«" + str(text or "").replace("«", "„").replace("»", "“") + "»"


def both(ru: str, kk: str) -> dict:
    return {"ru": ru, "kk": kk}
