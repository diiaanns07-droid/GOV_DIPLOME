"""Рабочие дни Казахстана для сроков (волна мелочей п. 6: «выходные не съедают срок»).

Выходные — суббота и воскресенье. Праздничные дни — Закон РК «О праздниках» и Трудовой кодекс РК (ст. 84):
1–2 января, 7 января (православное Рождество), 8 марта, 21–23 марта (Наурыз), 1, 7, 9 мая, 6 июля,
30 августа, 25 октября, 16 декабря и первый день Курбан айта (дату объявляет ДУМК, она плавающая).
Если праздник выпал на субботу или воскресенье, выходной переносится на следующий рабочий день
(кроме религиозных праздников) — так перенос считается здесь.

ОГРАНИЧЕНИЕ (честно): Правительство каждый год может дополнительно переносить рабочие дни постановлением;
такие переносы здесь НЕ учтены — сверить с постановлением на 2026 год. Даты Курбан айта: 2025-06-06,
2026-05-27 (ожидаемая); для других лет — без него.

ОДИН КАЛЕНДАРЬ С R09: если в сборке есть ui.civic_feedback.v2.workdays (R09, holidays_kz.json) и в нём есть
этот год — берём его (житель, сотрудник и аким видят одни и те же рабочие дни; правка календаря — в одном месте
у R09). Иначе — правила ниже. Для 2026 оба дают одни и те же дни (тест test_r08_wave2).
"""
from __future__ import annotations

from datetime import date as Date, timedelta
from functools import lru_cache

FIXED = ((1, 1), (1, 2), (1, 7), (3, 8), (3, 21), (3, 22), (3, 23), (5, 1), (5, 7), (5, 9),
         (7, 6), (8, 30), (10, 25), (12, 16))
RELIGIOUS = {(1, 7)}  # перенос с выходного не делается
KURBAN_AIT = {2025: Date(2025, 6, 6), 2026: Date(2026, 5, 27)}


@lru_cache(maxsize=16)
def days_off(year: int) -> frozenset:
    """Праздничные и перенесённые выходные дни года (будни, в которые не работают, плюс сами праздники)."""
    holidays = [Date(year, m, d) for m, d in FIXED]
    off = set(holidays)
    religious = {Date(year, m, d) for m, d in RELIGIOUS}
    if year in KURBAN_AIT:
        off.add(KURBAN_AIT[year])
        religious.add(KURBAN_AIT[year])
    for h in sorted(holidays):
        if h.weekday() >= 5 and h not in religious:
            d = h + timedelta(days=1)
            while d.weekday() >= 5 or d in off:
                d += timedelta(days=1)
            off.add(d)
    return frozenset(off)


@lru_cache(maxsize=1)
def _r09():
    """(is_working_day, годы календаря) R09 или None."""
    try:
        from ui.civic_feedback.v2 import workdays as r09  # type: ignore
        return r09.is_working_day, frozenset(r09.calendar_years())
    except Exception:  # модуля нет или календарь не читается — свои правила
        return None


def is_workday(d: Date) -> bool:
    r09 = _r09()
    if r09 is not None and d.year in r09[1]:
        return bool(r09[0](d))
    return own_is_workday(d)


def own_is_workday(d: Date) -> bool:
    return d.weekday() < 5 and d not in days_off(d.year)


def source() -> str:
    return "r09" if _r09() is not None else "r08"


def add_workdays(start: Date, n: int) -> Date:
    """N-й рабочий день ПОСЛЕ start (сам день подачи не считается — как срок по закону об обращениях)."""
    d, left = start, max(0, int(n))
    while left:
        d += timedelta(days=1)
        if is_workday(d):
            left -= 1
    return d


def workdays_between(a: Date, b: Date) -> int:
    """Сколько рабочих дней в (a, b]; 0, если b ≤ a."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if is_workday(d):
            n += 1
    return n
