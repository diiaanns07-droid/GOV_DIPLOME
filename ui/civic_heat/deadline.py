"""Срок ответа жителю в рабочих днях — для карточки акимата (волна 1, п. 6: «Осталось 2 рабочих дня» / «Просрочено на 1 день»).

Срок ставит R09 (поле записи due_at; R09 же считает его в рабочих днях с праздниками РК 2026). R07 только показывает,
сколько рабочих дней осталось до этого срока. Календарь праздников — тоже R09: если в сборке есть модуль
ui.civic_feedback.v2.workdays с функцией is_workday(date) или множеством DAYS_OFF / HOLIDAYS (даты), берём его.
(в R09 — is_working_day). Без него — календарь «Картины дня» R08 (ui.civic_akim.workdays.days_off), без обоих — честный
запасной вариант: рабочие дни = понедельник–пятница (праздники не учтены; в ответе calendar="weekdays").
Свой список праздников R07 не ведёт: в 2026 году календарь РК менялся (перенос Дня Конституции), держать два списка опасно.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

_calendar = None


def _load_calendar():
    """(is_workday, имя календаря). Ищется один раз."""
    global _calendar
    if _calendar is not None:
        return _calendar
    try:
        from ui.civic_feedback.v2 import workdays as r09  # type: ignore[import-not-found]
    except Exception:
        r09 = None
    fn = (getattr(r09, "is_working_day", None) or getattr(r09, "is_workday", None)) if r09 else None
    if callable(fn):
        _calendar = (fn, "r09")
        return _calendar
    off = None
    for name in ("DAYS_OFF", "HOLIDAYS"):
        val = getattr(r09, name, None) if r09 else None
        if val:
            off = {d if isinstance(d, date) else date.fromisoformat(str(d)) for d in val}
            break
    if off is not None:
        _calendar = (lambda d: d.weekday() < 5 and d not in off, "r09")
        return _calendar
    # Календарь «Картины дня» R08 (ui/civic_akim/workdays.py: праздники РК, переносы) — тот же, что у R09 на 2026
    try:
        from ui.civic_akim import workdays as r08  # type: ignore[import-not-found]
    except Exception:
        r08 = None
    days_off = getattr(r08, "days_off", None) if r08 else None
    if callable(days_off):
        _calendar = (lambda d: d.weekday() < 5 and d not in days_off(d.year), "r08")
    else:
        _calendar = (lambda d: d.weekday() < 5, "weekdays")
    return _calendar


def set_calendar(is_workday=None, name: str = "custom") -> None:
    """Для тестов и для R01: подставить календарь (None — найти заново)."""
    global _calendar
    _calendar = None if is_workday is None else (is_workday, name)


def workdays_between(start: date, end: date) -> int:
    """Рабочие дни в (start, end]: сколько рабочих дней пройдёт от start до конца дня end."""
    is_workday, _ = _load_calendar()
    n = 0
    d = start + timedelta(days=1)
    while d <= end:
        if is_workday(d):
            n += 1
        d += timedelta(days=1)
    return n


def response_due(due_at: datetime, now: datetime, tz) -> dict:
    """{at, workdays_left, overdue_days, calendar}.
    workdays_left — сколько рабочих дней от сегодняшнего (не считая его) до дня срока включительно: срок завтра → 1,
    срок сегодня → 0 («срок сегодня»). Срок прошёл → overdue_days: на сколько РАБОЧИХ дней просрочено (минимум 1) —
    так же считают R09 (lifecycle.deadline_info) и R08."""
    _, name = _load_calendar()
    due_local = due_at.astimezone(tz)
    now_local = now.astimezone(tz)
    out = {"at": due_local.isoformat(timespec="seconds"), "calendar": name, "workdays_left": None, "overdue_days": None}
    if now_local > due_local:
        out["overdue_days"] = max(1, workdays_between(due_local.date(), now_local.date()))
    else:
        out["workdays_left"] = workdays_between(now_local.date(), due_local.date())
    return out
