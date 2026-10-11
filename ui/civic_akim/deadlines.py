"""Сроки исправления по категориям — по ним «Картина дня» считает «Просрочено».

Просрочено = обращение ещё не исправлено (статус new / accepted / in_progress),
а срок его категории уже прошёл (due() ниже).

Срок в РАБОЧИХ днях (волна мелочей п. 6: выходные и праздники РК не съедают срок, workdays.py):
срок = конец N-го рабочего дня после дня подачи. Исключение — аварийные категории (CALENDAR_DAYS):
нет тепла или воды, снег и гололёд, мусор, газ и дым — службы работают без выходных, и срок у них
в КАЛЕНДАРНЫХ днях от момента подачи. Интерфейс пишет это словами: «Осталось 2 рабочих дня»,
«Просрочено на 1 день».

ВАЖНО: это ДЕМО-НОРМАТИВ R08, акиматом не утверждён. Числа выбраны по смыслу:
  - срочное (нет тепла или воды, гололёд, мусор) — 1–2 дня;
  - опасное и тёмное (фонари, шум, запахи) — 3 дня;
  - ремонт (ямы, остановки, тротуары) — 5–10 дней;
  - благоустройство и парковки — 14 дней.
Закон РК об обращениях даёт до 15 рабочих дней на ответ — ни один срок здесь его не превышает.

Не путать со сроком ПЕРВОГО ОТВЕТА у R09 (ui/civic_feedback/v2/categories.py, RESPONSE_DAYS):
там «новое → принято», здесь «подано → исправлено». Аким смотрит на то, что не решено вовремя.
Ключи обязаны совпадать со списком категорий в categories_v2.json — проверяет validate().
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from . import workdays

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = ROOT / "research" / "round-14" / "categories_v2.json"

DEADLINE_DAYS = {
    "roads": 7,          # ямы, разбитый асфальт
    "snow_ice": 2,       # снег и гололёд — люди падают уже сегодня
    "sidewalks": 10,
    "transport": 5,      # павильон, расписание
    "lighting": 3,       # тёмный двор — вопрос безопасности
    "yards": 14,         # площадки, деревья — сезонные работы
    "waste": 2,
    "utilities": 1,      # нет тепла или воды
    "smell_air": 3,
    "noise_safety": 3,
    "parking": 14,
    "other": 10,
}

# Аварийные категории: срок в календарных днях (службы дежурят и в выходные). Остальные — в рабочих.
CALENDAR_DAYS = frozenset({"utilities", "snow_ice", "waste", "smell_air"})


@lru_cache(maxsize=1)
def load_categories(path: str | None = None) -> dict:
    """categories_v2.json — единственный источник списка категорий (CONTRACT §3)."""
    return json.loads(Path(path or CATEGORIES_PATH).read_text("utf-8"))


def category_ids() -> tuple[str, ...]:
    return tuple(c["id"] for c in load_categories()["categories"])


def validate() -> None:
    known, have = set(category_ids()), set(DEADLINE_DAYS)
    if known != have:
        raise ValueError(f"DEADLINE_DAYS не совпадает с categories_v2.json: нет {sorted(known - have)}, "
                         f"лишние {sorted(have - known)}")


def deadline_days(category: str | None) -> int:
    """Срок для категории; неизвестная категория считается «Другое»."""
    return DEADLINE_DAYS.get(category or "other", DEADLINE_DAYS["other"])


def unit(category: str | None) -> str:
    """work — рабочие дни, calendar — календарные."""
    return "calendar" if (category or "other") in CALENDAR_DAYS else "work"


def due(category: str | None, created: datetime) -> datetime:
    """Когда истекает срок исправления обращения, поданного в момент created (время Астаны)."""
    n = deadline_days(category)
    if unit(category) == "calendar":
        return created + timedelta(days=n)
    last = workdays.add_workdays(created.date(), n)
    return datetime(last.year, last.month, last.day, 23, 59, 59, tzinfo=created.tzinfo)


def timer(category: str | None, created: datetime, moment: datetime) -> dict:
    """Таймер для карточки и «Картины дня»: {state: ok|today|overdue, left, overdue_by, unit, due}.

    left — сколько дней осталось после сегодняшнего (0 и state=today — срок сегодня);
    overdue_by — на сколько дней просрочено (не меньше 1). Дни — рабочие или календарные, как unit.
    """
    u, end = unit(category), due(category, created)
    today, last = moment.date(), end.date()
    out = {"unit": u, "due": end.isoformat(timespec="seconds"), "days": deadline_days(category),
           "left": 0, "overdue_by": 0}
    if moment <= end:
        left = workdays.workdays_between(today, last) if u == "work" else (last - today).days
        out.update(state="today" if left == 0 else "ok", left=left)
    else:
        late = workdays.workdays_between(last, today) if u == "work" else (today - last).days
        out.update(state="overdue", overdue_by=max(1, late))
    return out
