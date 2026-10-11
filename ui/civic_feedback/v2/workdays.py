"""Сроки ответа в рабочих днях РК (POLISH_WAVE п. 6): выходные и праздники срок не съедают.

Календарь — holidays_kz.json (derived: правила закона о праздниках и ст. 85 ТК РК; переносы правительства
и дату Курбан айта нужно сверить — см. поле verify). Год без данных считается только по субботам/воскресеньям.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

CALENDAR = Path(__file__).with_name("holidays_kz.json")


@lru_cache(maxsize=1)
def _holidays() -> frozenset[date]:
    data = json.loads(CALENDAR.read_text(encoding="utf-8"))
    days = set()
    for year in data.get("years", {}).values():
        for item in year.get("holidays", []):
            days.add(date.fromisoformat(item["date"]))
    return frozenset(days)


def calendar_years() -> list[int]:
    data = json.loads(CALENDAR.read_text(encoding="utf-8"))
    return sorted(int(y) for y in data.get("years", {}))


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and day not in _holidays()


def add_working_days(start: datetime, days: int) -> datetime:
    """Срок = момент подачи + N рабочих дней (время суток сохраняется). Подано в субботу -> первый
    рабочий день считается с понедельника: 1 рабочий день от субботы 10:00 = понедельник 10:00."""
    moment, counted = start, 0
    while counted < days:
        moment += timedelta(days=1)
        if is_working_day(moment.date()):
            counted += 1
    return moment


def working_days_between(after: date, until: date) -> int:
    """Число рабочих дней в (after, until] — сколько рабочих дней пройдёт от after до until включительно."""
    count, day = 0, after
    while day < until:
        day += timedelta(days=1)
        if is_working_day(day):
            count += 1
    return count


def deadline_info(due: datetime | None, now: datetime, *, done: bool = False) -> dict | None:
    """Для карточки акимата и «Картины дня»: {state, working_days_left, overdue_working_days, due_at}.
    state: ok (остались рабочие дни) | today (срок сегодня) | overdue (просрочено) | answered (ответ уже дан)."""
    if due is None:
        return None
    info = {"due_at": due.isoformat(), "working_days_left": None, "overdue_working_days": None}
    if done:
        info["state"] = "answered"
        return info
    if now <= due:
        left = working_days_between(now.date(), due.date())
        info["state"] = "today" if left == 0 else "ok"
        info["working_days_left"] = left
    else:
        # Просрочка в рабочих днях, но не меньше 1: «Просрочено на 1 день» даже в тот же день после срока.
        info["state"] = "overdue"
        info["overdue_working_days"] = max(1, working_days_between(due.date(), now.date()))
    return info
