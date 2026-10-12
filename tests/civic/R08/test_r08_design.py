"""R08 · дизайн-марафон: данные для вида «Картины дня» — мини-графики под числами (kpi.*.series).

Ряд — 14 значений по дням, последнее = само число на экране; «в работе», «просрочено», «исправлено за 7 дней» —
на конец каждого дня тем же правилом, что и число (status_at / fixed_moment / сроки), но за один проход.
Запуск: python -m pytest tests/civic/R08 -q
"""
import random
from datetime import datetime, timedelta

from r08_helpers import NOW, TZ, rec
from ui.civic_akim import AkimService, deadlines
from ui.civic_akim.summary import OPEN, SERIES_DAYS, WEEK, WORK, fixed_moment, kpi_series, parse_time, status_at


def svc(records):
    return AkimService(heat=False, records=lambda since: records, clock=lambda: NOW, objects=None, proposals=None)


def records(n=160, seed=7):
    rnd = random.Random(seed)
    cats = ["roads", "snow_ice", "lighting", "yards", "waste", "transport"]
    out = []
    for i in range(n):
        hist = []
        r = rnd.random()
        if r < 0.3:
            hist = [(rnd.uniform(0.1, 2), "accepted")]
        elif r < 0.55:
            hist = [(rnd.uniform(0.1, 1), "accepted"), (rnd.uniform(1, 4), "in_progress")]
        elif r < 0.85:
            hist = [(rnd.uniform(0.1, 1), "accepted"), (rnd.uniform(1, 3), "in_progress"), (rnd.uniform(3, 8), "fixed")]
        out.append(rec(i, age_days=rnd.uniform(0, 20), category=rnd.choice(cats), history=hist))
    return out


def reference(recs, moment):
    """Как _kpi.at(): по каждой записи отдельно."""
    work = overdue = fixed = 0
    for r in recs:
        st = status_at(r, moment)
        if st is None:
            continue
        work += st in WORK
        overdue += st in OPEN and moment > deadlines.due(r.get("category"), parse_time(r["created_at"]))
        f = fixed_moment(r, moment)
        fixed += f is not None and moment - WEEK < f <= moment
    return work, overdue, fixed


def test_series_shape_and_last_point_is_the_number():
    s = svc(records()).summary(now=NOW)
    for key in ("new_day", "in_progress", "overdue", "fixed_week"):
        series = s["kpi"][key]["series"]
        assert len(series) == SERIES_DAYS and all(isinstance(x, int) and x >= 0 for x in series)
        assert series[-1] == s["kpi"][key]["value"], key


def test_one_pass_series_equals_per_record_reference():
    recs = records()
    day_start = datetime(2026, 10, 12, tzinfo=TZ)
    ends = [day_start - timedelta(days=k) - timedelta(microseconds=1) for k in range(SERIES_DAYS - 1, 0, -1)] + [NOW]
    got = kpi_series(recs, ends)
    want = [reference(recs, m) for m in ends]
    assert got["work"] == [w for w, _, _ in want]
    assert got["overdue"] == [o for _, o, _ in want]
    assert got["fixed"] == [f for _, _, f in want]


def test_new_series_counts_each_day_once():
    recs = records()
    s = svc(recs).summary(now=NOW)
    first = datetime(2026, 10, 12, tzinfo=TZ) - timedelta(days=SERIES_DAYS - 1)
    in_window = [r for r in recs if first <= parse_time(r["created_at"]) <= NOW]
    assert sum(s["kpi"]["new_day"]["series"]) == len(in_window)


def test_past_day_series_ends_at_that_day():
    s = svc(records()).summary(now=NOW, date="2026-10-05")
    assert s["is_today"] is False
    for key in ("new_day", "in_progress", "overdue", "fixed_week"):
        assert s["kpi"][key]["series"][-1] == s["kpi"][key]["value"], key
