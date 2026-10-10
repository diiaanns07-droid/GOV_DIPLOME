"""R08 раунд 14: «Картина дня» — окна времени, KPI, сроки, восстановление статуса «на момент», объекты, предложения.

Эти тесты не зависят от тепловой карты R07 (heat=False). Совпадение с картой — test_r08_heat_match.py.
Запуск: python -m pytest tests/civic/R08 -q
"""
from datetime import date, datetime, timedelta

import pytest

from r08_helpers import NOW, TZ, rec
from ui.civic_akim import AkimError, AkimService, deadlines, sources
from ui.civic_akim.summary import change, districts, fixed_moment, snapshot, status_at

CATS = deadlines.load_categories()


def svc(records, **kw):
    kw.setdefault("objects", None)
    kw.setdefault("proposals", None)
    return AkimService(heat=False, records=lambda since: records, clock=lambda: NOW, **kw)


def summary(records, **kw):
    return svc(records).summary(now=NOW, **kw)


def at(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


# ---------------------------------------------------------------- сроки

def test_deadlines_cover_exactly_the_12_categories():
    deadlines.validate()
    assert set(deadlines.DEADLINE_DAYS) == {c["id"] for c in CATS["categories"]}
    assert deadlines.DEADLINE_DAYS["snow_ice"] == 2 and deadlines.DEADLINE_DAYS["roads"] == 7
    assert all(1 <= v <= 15 for v in deadlines.DEADLINE_DAYS.values()), "не больше 15 дней — срок по закону"
    assert deadlines.deadline_days("неизвестная") == deadlines.DEADLINE_DAYS["other"]


# ---------------------------------------------------------------- изменение

@pytest.mark.parametrize("value,prev,mode,trend,pct,ratio", [
    (14, 10, "pct", "up", 40, None),
    (6, 10, "pct", "down", 40, None),
    (3, 1, "abs", "up", None, None),       # база < 10 — только разница в штуках
    (25, 10, "ratio", "up", 150, 2.5),
    (20, 10, "ratio", "up", 100, 2.0),
    (5, 0, "new", "up", None, None),       # неделю назад не было
    (0, 0, "abs", "flat", None, None),
    (7, 7, "abs", "flat", None, None),
    (0, 12, "abs", "down", None, None),    # «−100 %» не пишем: было 12, стало 0
    (1001, 1000, "abs", "up", None, None),  # 0,1 % округлилось бы до «0 %»
])
def test_change_modes(value, prev, mode, trend, pct, ratio):
    ch = change(value, prev)
    assert (ch["mode"], ch["trend"], ch["pct"], ch["ratio"]) == (mode, trend, pct, ratio)
    assert ch["abs"] == abs(value - prev) and ch["value"] == value and ch["prev"] == prev


# ---------------------------------------------------------------- статус «на момент»

def test_status_at_and_snapshot_follow_history():
    r = rec(1, age_days=10, history=[(1, "accepted"), (8, "in_progress")])
    created = NOW - timedelta(days=10)
    assert status_at(r, created - timedelta(minutes=1)) is None
    assert status_at(r, created + timedelta(hours=1)) == "new"
    assert status_at(r, created + timedelta(days=3)) == "accepted"
    assert status_at(r, NOW) == "in_progress"
    snap = snapshot(r, created + timedelta(days=3))
    assert snap["status"] == "accepted" and [h["status"] for h in snap["status_history"]] == ["new", "accepted"]
    assert r["status"] == "in_progress" and len(r["status_history"]) == 3, "исходная запись не меняется"
    assert snapshot(r, created - timedelta(seconds=1)) is None


def test_status_without_history_trusts_status_field():
    r = rec(2, age_days=3, status="accepted")  # в истории только «new», но статус — accepted
    assert status_at(r, NOW) == "accepted"


def test_fixed_moment_and_reopen():
    fixed = rec(3, age_days=5, history=[(1, "in_progress"), (3, "fixed")])
    assert fixed_moment(fixed, NOW) == NOW - timedelta(days=2)
    assert fixed_moment(fixed, NOW - timedelta(days=3)) is None, "тогда ещё не был исправлен"
    reopened = rec(4, age_days=6, history=[(1, "fixed"), (2, "in_progress")])
    assert fixed_moment(reopened, NOW) is None


# ---------------------------------------------------------------- новые

def test_new_day_compares_same_time_window_a_week_ago():
    records = [
        rec(1, at=at(2026, 10, 12, 9, 0)),     # сегодня до 10:00 — да
        rec(2, at=at(2026, 10, 12, 0, 0)),     # ровно полночь — да
        rec(3, at=at(2026, 10, 11, 23, 59)),   # вчера — нет
        rec(4, at=at(2026, 10, 5, 9, 30)),     # неделю назад до 10:00 — в сравнение
        rec(5, at=at(2026, 10, 5, 0, 10)),     # неделю назад после полуночи — в сравнение
        rec(6, at=at(2026, 10, 5, 11, 0)),     # неделю назад ПОСЛЕ 10:00 — не сравниваем
    ]
    k = summary(records)["kpi"]["new_day"]
    assert (k["value"], k["prev"]) == (2, 2)


def test_new_week_windows_do_not_overlap():
    records = [
        rec(1, age_days=0.1), rec(2, age_days=6.9),
        rec(3, age_days=7),        # ровно 7 дней — уже прошлая неделя
        rec(4, age_days=13.9),
        rec(5, age_days=14),       # ровно 14 — ни туда, ни сюда
        rec(6, age_days=20),
    ]
    k = summary(records)["kpi"]["new_week"]
    assert (k["value"], k["prev"]) == (2, 2)


# ---------------------------------------------------------------- в работе, просрочено, исправлено

def test_in_progress_waiting_and_week_ago():
    records = [
        rec(1, age_days=10, history=[(1, "accepted"), (8, "in_progress")]),  # сейчас в работе; неделю назад принято
        rec(2, age_days=10, history=[(5, "accepted")]),                     # сейчас принято; неделю назад новое
        rec(3, age_days=2),                                                 # ждёт ответа; неделю назад не было
        rec(4, age_days=10, history=[(1, "in_progress"), (2, "fixed")]),    # исправлено — не в работе
        rec(5, age_days=1, history=[(0.5, "rejected")]),                    # отклонено — нигде
    ]
    k = summary(records)["kpi"]["in_progress"]
    assert (k["value"], k["prev"], k["waiting"]) == (2, 1, 1)


def test_overdue_uses_category_deadlines():
    records = [
        rec(1, age_days=3, category="snow_ice"),                                  # срок 2 → просрочено
        rec(2, age_days=1, category="snow_ice"),                                  # ещё в сроке
        rec(3, age_days=8, category="roads", history=[(1, "accepted")]),          # срок 7, принято → просрочено
        rec(4, age_days=6, category="roads"),                                     # в сроке
        rec(5, age_days=1.5, category="utilities", history=[(0.1, "in_progress")]),  # срок 1 → просрочено
        rec(6, age_days=10, category="yards"),                                    # срок 14 → в сроке
        rec(7, age_days=5, category="snow_ice", history=[(1, "fixed")]),          # исправлено
        rec(8, age_days=5, category="snow_ice", history=[(1, "rejected")]),       # отклонено
        rec(9, age_days=30, category="другое-неизвестное"),                       # как «Другое» (10) → просрочено
    ]
    k = summary(records)["kpi"]["overdue"]
    assert k["value"] == 4
    # Неделю назад: №3 было 1 день от роду, №9 — 23 дня (уже просрочено), остальных не было.
    assert k["prev"] == 1


def test_fixed_week_counts_only_fixed_and_not_reopened():
    records = [
        rec(1, age_days=5, history=[(1, "in_progress"), (3, "fixed")]),  # исправлено 2 дня назад
        rec(2, age_days=20, history=[(1, "fixed")]),                    # давно
        rec(3, age_days=6, history=[(1, "fixed"), (2, "in_progress")]),  # открыто снова
        rec(4, age_days=10, history=[(1, "fixed")]),                    # 9 дней назад — прошлая неделя
        rec(5, age_days=3, status="fixed"),                             # без истории: время подачи
    ]
    k = summary(records)["kpi"]["fixed_week"]
    assert (k["value"], k["prev"]) == (2, 1)


def test_duplicates_excluded_and_district_filter():
    records = [rec(1, age_days=0.1), rec(2, age_days=0.1, district="esil"),
               rec(3, age_days=0.1, duplicate_of="c-r08-1")]
    s = summary(records)
    assert s["kpi"]["new_day"]["value"] == 2 and s["stats"]["duplicates"] == 1
    assert summary(records, district="nura")["kpi"]["new_day"]["value"] == 1
    assert summary(records, district="esil")["kpi"]["new_day"]["value"] == 1
    assert summary(records, district="all")["kpi"]["new_day"]["value"] == 2
    assert summary(records, district="nura")["district"] == {"id": "nura", "ru": "Нура", "kk": "Нұра"}


def test_past_date_uses_state_at_end_of_that_day():
    r = rec(1, at=at(2026, 10, 9, 12, 0), history=[(0.125, "accepted"), (2, "fixed")])
    s = summary([r], date="2026-10-09")
    assert s["is_today"] is False and s["as_of"] == "2026-10-09T23:59:59+05:00"
    k = s["kpi"]
    assert k["new_day"]["value"] == 1 and k["in_progress"]["value"] == 1 and k["fixed_week"]["value"] == 0
    assert s["text"]["ru"].startswith("9 окт — 1 новое обращение.")
    assert s["text"]["kk"].startswith("9 қазан күні 1 жаңа өтініш түсті.")
    # А сегодня то же обращение уже исправлено.
    assert summary([r])["kpi"]["fixed_week"]["value"] == 1


@pytest.mark.parametrize("params,field", [
    ({"date": "2026-13-01"}, "date"), ({"date": "вчера"}, "date"),
    ({"date": "2026-10-13"}, "date"),          # завтра — картины ещё нет
    ({"district": "moon"}, "district"),
])
def test_bad_params(params, field):
    with pytest.raises(AkimError) as e:
        summary([], **params)
    assert e.value.field == field


def test_default_date_is_today_in_astana():
    # 12 окт 01:30 по Астане = 11 окт 20:30 UTC: «сегодня» — 12-е, а не 11-е.
    late_utc = NOW.replace(hour=1, minute=30)
    s = AkimService(heat=False, records=lambda since: [], objects=None, proposals=None).summary(now=late_utc)
    assert s["date"] == "2026-10-12"


def test_empty_data_has_no_blank_numbers():
    s = summary([])
    assert s["empty"] is True
    assert all(s["kpi"][k]["value"] == 0 for k in ("new_day", "new_week", "in_progress", "overdue", "fixed_week"))
    assert s["text"]["ru"] == "Сегодня новых обращений нет. Просроченных обращений нет."
    assert s["text"]["kk"] == "Бүгін жаңа өтініш жоқ. Мерзімі өткен өтініш жоқ."


def test_invalid_records_are_skipped_not_fatal():
    records = [rec(1, age_days=0.1), {"id": "x", "created_at": None}, {"created_at": "вчера"}, "мусор", None]
    s = summary(records)
    assert s["kpi"]["new_day"]["value"] == 1 and s["stats"]["skipped_invalid"] == 4


def test_without_heat_map_blocks_say_unavailable():
    s = summary([rec(1, age_days=0.1)])
    for block in ("hot", "topics", "districts"):
        assert s[block]["available"] is False
    assert s["main_problem"] is None and s["sources"]["heat"] == "none"


def test_districts_are_real_astana_districts():
    assert set(districts()) == {"almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"}


def test_new_complaint_shows_up_after_cache():
    records = [rec(1, age_days=0.1)]
    s = svc(records)
    assert s.summary(now=NOW)["kpi"]["new_day"]["value"] == 1
    records.append(rec(2, age_days=0.05))
    s.invalidate()
    assert s.summary(now=NOW)["kpi"]["new_day"]["value"] == 2


# ---------------------------------------------------------------- объекты (R06)

def obj(i, **kw):
    base = {"id": f"o{i}", "title_ru": f"Объект {i}", "district": "nura", "stage": "construction",
            "planned_end": "2026-11-01", "forecast_end": "2026-11-01", "updated_at": "2026-10-10T10:00:00+05:00"}
    base.update(kw)
    return base


def test_normalize_object_counts_delay_and_stale_by_contract():
    n = sources.normalize_object(obj(1, forecast_end="2026-11-24"), NOW)
    assert n["delay_days"] == 23 and n["stale"] is False and n["title_kk"] == "Объект 1"
    assert sources.normalize_object(obj(2, delay_days=5), NOW)["delay_days"] == 5, "число R06 главнее"
    assert sources.normalize_object(obj(3, forecast_end="2026-10-20"), NOW)["delay_days"] == 0, "раньше срока — не отставание"
    assert sources.normalize_object(obj(4, updated_at="2026-09-27T10:00:00+05:00"), NOW)["stale"] is True   # 15 дней
    assert sources.normalize_object(obj(5, updated_at="2026-09-28T10:00:00+05:00"), NOW)["stale"] is False  # ровно 14
    assert sources.normalize_object(obj(6, stale=True), NOW)["stale"] is True
    broken = sources.normalize_object({"id": "o7", "planned_end": "не дата"}, NOW)
    assert broken["delay_days"] == 0 and broken["title_ru"] == "o7"


def test_objects_block_sorted_filtered_and_safe():
    objects = [obj(1, forecast_end="2026-11-10"), obj(2, forecast_end="2026-12-01"),
               obj(3, district="esil", forecast_end="2026-12-30"),
               obj(4, stage="operating", forecast_end="2026-12-30"),
               obj(5, updated_at="2026-09-01T10:00:00+05:00")]
    s = AkimService(heat=False, records=lambda since: [], objects=lambda d, today: objects, proposals=None,
                    clock=lambda: NOW).summary(now=NOW, district="nura")
    o = s["objects"]
    assert [x["id"] for x in o["late"]] == ["o2", "o1"] and o["late_count"] == 2
    assert [x["id"] for x in o["stale"]] == ["o5"] and o["total"] == 3
    assert "2 объекта отстают от графика. 1 объект давно не обновлялся." in s["text"]["ru"]
    assert "Кестеден қалып жатқан нысан: 2. Көптен бері жаңартылмаған нысан: 1." in s["text"]["kk"]

    def broken(d, today):
        raise RuntimeError("R06 упал")
    s2 = AkimService(heat=False, records=lambda since: [], objects=broken, proposals=None, clock=lambda: NOW).summary(now=NOW)
    assert s2["objects"]["available"] is False


def test_fixture_dates_move_with_today():
    base = sources.fixture_objects(date(2026, 10, 12))
    moved = sources.fixture_objects(date(2026, 10, 14))
    assert all(o["demo"] for o in base)
    for a, b in zip(base, moved):
        assert date.fromisoformat(b["planned_end"]) - date.fromisoformat(a["planned_end"]) == timedelta(days=2)
        assert datetime.fromisoformat(b["updated_at"]) - datetime.fromisoformat(a["updated_at"]) == timedelta(days=2)
    # «Отстаёт на N дней» от сдвига не меняется.
    assert [sources.normalize_object(o, NOW)["delay_days"] for o in base] == \
           [sources.normalize_object(o, NOW + timedelta(days=2))["delay_days"] for o in moved]


def test_fixture_objects_have_no_invented_coordinates():
    for o in sources.fixture_objects(date(2026, 10, 12)) + sources.fixture_proposals(date(2026, 10, 12)):
        assert not o.get("geometry") and not o.get("point"), "точки на карте — только реальные объекты OSM"


# ---------------------------------------------------------------- предложения (R06)

def test_proposals_new_and_votes():
    props = [
        {"id": "p1", "district": "nura", "status": "proposal", "created_at": "2026-10-11T10:00:00+05:00", "votes_up": 10, "votes_down": 1},
        {"id": "p2", "district": "nura", "status": "proposal", "created_at": "2026-10-01T10:00:00+05:00", "votes_up": 30, "votes_down": 2},
        {"id": "p3", "district": "esil", "status": "proposal", "created_at": "2026-10-12T09:00:00+05:00", "votes_up": 5, "votes_down": 0},
        {"id": "p4", "district": "nura", "status": "approved", "created_at": "2026-10-11T10:00:00+05:00", "votes_up": 99, "votes_down": 0},
        {"id": "p5", "district": "nura", "status": "proposal", "created_at": "2026-10-12T11:00:00+05:00", "votes_up": 1, "votes_down": 0},
    ]
    s = AkimService(heat=False, records=lambda since: [], objects=None, proposals=lambda d, today: props,
                    clock=lambda: NOW).summary(now=NOW)
    p = s["proposals"]
    assert (p["new_count"], p["open_count"], p["votes_up"], p["votes_down"]) == (2, 3, 45, 3)
    assert [x["id"] for x in p["top"]] == ["p2", "p1", "p3"] and p["top"][1]["is_new"] is True
    nura = AkimService(heat=False, records=lambda since: [], objects=None, proposals=lambda d, today: props,
                       clock=lambda: NOW).summary(now=NOW, district="nura")["proposals"]
    assert (nura["new_count"], nura["open_count"]) == (1, 2)


def test_default_sources_are_marked_demo():
    s = AkimService(heat=False, records=lambda since: [], clock=lambda: NOW).summary(now=NOW)
    assert s["sources"]["objects"] in ("fixture", "r06") and s["sources"]["proposals"] in ("fixture", "r06")
    if s["sources"]["objects"] == "fixture":
        assert s["objects"]["demo"] is True and s["demo"]["any"] is True


def test_no_complaint_source_is_not_zero():
    """Без источника жалоб — «нет данных», а не «Сегодня новых обращений нет»."""
    s = AkimService(heat=False, records=None, objects=None, proposals=None, clock=lambda: NOW).summary(now=NOW)
    assert s["complaints_available"] is False and s["empty"] is False
    assert s["text"]["ru"] == "Данные об обращениях пока не подключены."
    assert s["text"]["kk"] == "Өтініштер туралы дерек әлі қосылмаған."
    assert summary([])["complaints_available"] is True
