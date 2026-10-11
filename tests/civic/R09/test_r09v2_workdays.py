"""R09 · POLISH_WAVE п. 6: сроки ответа в рабочих днях РК 2026 (праздники и переносы)."""

import json
from datetime import date, datetime, timedelta, timezone

from ui.civic_feedback.v2 import record as rec
from ui.civic_feedback.v2 import workdays

TZ = timezone(timedelta(hours=5))


def at(y, m, d, h=10):
    return datetime(y, m, d, h, 0, tzinfo=TZ)


def test_calendar_is_derived_and_says_what_to_verify():
    data = json.loads(workdays.CALENDAR.read_text(encoding="utf-8"))
    assert data["evidence_type"] == "derived" and "постановлени" in data["verify"]
    assert workdays.calendar_years() == [2026]


def test_weekends_and_holidays_are_not_working_days():
    assert not workdays.is_working_day(date(2026, 10, 24))      # суббота
    assert not workdays.is_working_day(date(2026, 10, 26))      # перенос Дня Республики (25 окт — вс)
    assert not workdays.is_working_day(date(2026, 12, 16))      # День Независимости
    for d in (date(2026, 3, 23), date(2026, 3, 24), date(2026, 3, 25)):   # Наурыз + переносы с сб и вс
        assert not workdays.is_working_day(d)
    assert workdays.is_working_day(date(2026, 10, 27))


def test_due_skips_weekend_and_holiday():
    assert workdays.add_working_days(at(2026, 10, 23), 1) == at(2026, 10, 27)   # пт -> вт (пн 26 — праздник)
    assert workdays.add_working_days(at(2026, 10, 24), 1) == at(2026, 10, 27)   # сб -> вт
    assert workdays.add_working_days(at(2026, 12, 15), 3) == at(2026, 12, 21)   # 16 дек праздник: 17, 18, 21
    assert rec.due_at("2026-10-23T10:00:00+05:00", "snow_ice") == "2026-10-27T10:00:00+05:00"


def test_deadline_info_for_akimat():
    due = at(2026, 10, 27)
    assert workdays.deadline_info(due, at(2026, 10, 22, 12)) == {
        "due_at": due.isoformat(), "working_days_left": 2, "overdue_working_days": None, "state": "ok"}
    assert workdays.deadline_info(due, at(2026, 10, 27, 9))["state"] == "today"
    late = workdays.deadline_info(due, at(2026, 10, 27, 11))
    assert late["state"] == "overdue" and late["overdue_working_days"] == 1     # «Просрочено на 1 день»
    assert workdays.deadline_info(due, at(2026, 10, 30, 11))["overdue_working_days"] == 3
    assert workdays.deadline_info(due, at(2026, 10, 30), done=True)["state"] == "answered"
    assert workdays.deadline_info(None, at(2026, 10, 30)) is None
