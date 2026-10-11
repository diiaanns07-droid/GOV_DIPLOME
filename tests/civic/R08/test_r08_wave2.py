"""Волна мелочей (п. 4, 6, 12) и волна 2 (п. 1, 5, 8) в «Картине дня»: рабочие дни, проверка жителями,
просрочки по местам со службой, «Нужно решение акима», «Пульс», уточнение у горячего места.

Без тепловой карты R07 (heat=False), кроме «Пульса» — ему цели карты передаются списком.
"""
from datetime import date, datetime, timedelta

import pytest

from r08_helpers import NOW, TZ, rec
from ui.civic_akim import AkimService, decisions, deadlines, pulse, text, workdays
from ui.civic_akim.summary import (AkimService as _S, parse_time, reopen_moments, status_at, verified_at)  # noqa: F401


def svc(records, **kw):
    kw.setdefault("objects", None)
    kw.setdefault("proposals", None)
    return AkimService(heat=False, records=lambda since: records, clock=lambda: NOW, **kw)


def summary(records, **kw):
    return svc(records).summary(now=NOW, **kw)


def at(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


# ---------------------------------------------------------------- рабочие дни (волна мелочей п. 6)

@pytest.mark.parametrize("day,off", [
    (date(2026, 1, 7), True),    # Рождество, среда
    (date(2026, 3, 9), True),    # 8 марта — воскресенье → перенос на понедельник
    (date(2026, 3, 23), True),   # Наурыз
    (date(2026, 3, 24), True),   # 21 марта (сб) → вторник
    (date(2026, 3, 25), True),   # 22 марта (вс) → среда
    (date(2026, 3, 26), False),
    (date(2026, 5, 11), True),   # 9 мая (сб) → понедельник
    (date(2026, 5, 27), True),   # Курбан айт (ожидаемая дата)
    (date(2026, 8, 31), True),   # 30 августа (вс) → понедельник
    (date(2026, 10, 26), True),  # 25 октября (вс) → понедельник
    (date(2026, 10, 27), False),
    (date(2026, 10, 10), True),  # обычная суббота
    (date(2026, 10, 12), False),
])
def test_kz_days_off_2026(day, off):
    assert workdays.is_workday(day) is (not off)


def test_add_workdays_skips_weekend_and_holiday():
    # пт 23 октября + 2 рабочих: пн 26 — праздник (перенос 25 октября), значит вт 27 и ср 28
    assert workdays.add_workdays(date(2026, 10, 23), 2) == date(2026, 10, 28)
    assert workdays.add_workdays(date(2026, 10, 10), 1) == date(2026, 10, 12)  # подано в субботу
    assert workdays.workdays_between(date(2026, 10, 9), date(2026, 10, 12)) == 1
    assert workdays.workdays_between(date(2026, 10, 12), date(2026, 10, 9)) == 0


def test_timer_working_and_calendar_days():
    # Дороги, 7 рабочих: подано пт 2 октября → срок вт 13 октября 23:59
    t = deadlines.timer("roads", at(2026, 10, 2, 18), NOW)
    assert (t["unit"], t["state"], t["left"]) == ("work", "ok", 1)
    t = deadlines.timer("roads", at(2026, 10, 2, 18), at(2026, 10, 13, 9))
    assert (t["state"], t["left"]) == ("today", 0)
    t = deadlines.timer("roads", at(2026, 10, 2, 18), at(2026, 10, 17, 12))  # суббота после срока
    assert (t["state"], t["overdue_by"]) == ("overdue", 3)  # ср, чт, пт
    # Снег — аварийная категория: 2 календарных дня от момента подачи, выходные не ждём
    t = deadlines.timer("snow_ice", at(2026, 10, 9, 20), at(2026, 10, 11, 21))
    assert (t["unit"], t["state"], t["overdue_by"]) == ("calendar", "overdue", 1)
    assert deadlines.unit("utilities") == "calendar" and deadlines.unit("yards") == "work"


def test_weekend_does_not_eat_deadline_in_kpi():
    # Подано в пятницу 18:00, срок 3 рабочих дня (освещение): в понедельник ещё не просрочено.
    r = rec(1, at=at(2026, 10, 9, 18), category="lighting")
    assert summary([r])["kpi"]["overdue"]["value"] == 0
    r = rec(2, at=at(2026, 10, 6, 18), category="lighting")  # вт → срок пт 9 октября
    assert summary([r])["kpi"]["overdue"]["value"] == 1


# ---------------------------------------------------------------- список просрочек (п. 6 + п. 7)

def test_overdue_list_groups_places_and_names_service():
    stop = {"kind": "stop", "id": "stop-1"}
    records = [
        rec(1, age_days=20, category="transport", target=stop, metoo=2),
        rec(2, age_days=15, category="transport", target=stop),
        rec(3, age_days=30, category="roads"),
        rec(4, age_days=1, category="roads"),                          # в сроке — не попадает
        rec(5, age_days=30, category="roads", history=[(1, "fixed")]),  # исправлено — не попадает
    ]
    records[2]["subtopic"] = "marking"
    o = summary(records)["overdue"]
    assert o["count"] == 3 and o["places"] == 2
    first, second = o["items"]
    assert first["id"] == "c-r08-3" and first["service"]["ru"] == "Служба светофоров и разметки"
    assert first["subtopic"]["ru"] == "Стёрлась разметка"
    assert second["complaints"] == 2 and second["people"] == 4 and second["id"] == "c-r08-1"
    assert second["service"]["ru"] == "Служба общественного транспорта"
    assert all(i["timer"]["state"] == "overdue" for i in o["items"])
    assert "text" not in first  # тексты жителей в ответ не попадают


# ---------------------------------------------------------------- проверка жителями (п. 4 + волна 2 п. 1)

def _fixed(i, *, check=None, check_after=1.0, fixed_ago=2, **kw):
    r = rec(i, age_days=fixed_ago + 1, history=[(0.5, "in_progress"), (1, "fixed")], **kw)
    if check:
        fixed_at = parse_time(r["status_history"][-1]["at"])
        r["status_history"].append({"at": (fixed_at + timedelta(days=check_after)).isoformat(),
                                    "event": "resident_check", "answer": check})
    return r


def test_verified_vs_awaiting_and_reopened():
    yes = _fixed(1, check="yes")
    waiting = _fixed(2)
    cant = _fixed(3, check="cant")
    reopened = _fixed(4)
    fixed_at = parse_time(reopened["status_history"][-1]["at"])
    back = fixed_at + timedelta(hours=20)
    reopened["status_history"] += [{"at": back.isoformat(), "event": "resident_check", "answer": "no"},
                                   {"at": back.isoformat(), "status": "in_progress"}]
    reopened["status"] = "in_progress"
    old_check = _fixed(5, check="yes", check_after=0.2, fixed_ago=12)  # исправлено 12 дней назад — не эта неделя
    s = summary([yes, waiting, cant, reopened, old_check])
    f = s["kpi"]["fixed_week"]
    assert (f["value"], f["verified"], f["awaiting"]) == (3, 1, 2)
    assert (f["reopened"], f["reopened_by_residents"]) == (1, 1)
    assert s["kpi"]["verification_available"] is True
    assert verified_at(yes, NOW) is not None and verified_at(waiting, NOW) is None
    assert reopen_moments(reopened, NOW)[0][1] is True
    assert "жители подтвердили 1, вернули в работу 1" in s["text"]["ru"]
    assert "тұрғындар растағаны: 1" in s["text"]["kk"]


def test_verified_status_and_verification_field_forms():
    a = _fixed(1)
    a["status"] = "verified"
    a["status_history"].append({"at": (NOW - timedelta(hours=3)).isoformat(), "status": "verified"})
    b = _fixed(2)
    b["verification"] = {"state": "verified", "at": (NOW - timedelta(hours=1)).isoformat()}
    f = summary([a, b])["kpi"]["fixed_week"]
    assert (f["value"], f["verified"]) == (2, 2)
    assert status_at(a, NOW) == "verified"


def test_no_verification_data_means_no_claim():
    """Пока R09 не даёт проверку жителями — не пишем «подтвердили 0» ни в числах-подписях, ни в сводке."""
    s = summary([_fixed(1), _fixed(2)])
    assert s["kpi"]["verification_available"] is False
    assert "подтвердили" not in s["text"]["ru"] and "растағаны" not in s["text"]["kk"]


def test_week_ago_verification_not_leaking_from_future():
    r = _fixed(1, check="yes", check_after=1.5, fixed_ago=3)  # подтверждено 1,5 дня назад
    assert verified_at(r, NOW - timedelta(days=2)) is None
    assert verified_at(r, NOW) is not None


# ---------------------------------------------------------------- «Нужно решение акима» (волна 2 п. 5)

def _delay(code="needs_decision", options=2, kk=True):
    d = {"reason_code": code, "problem_ru": "Проблема", "blocker_ru": "Блокер", "decision_ru": "Решить",
         "options": [{"ru": f"Вариант {i + 1}", **({"kk": f"Нұсқа {i + 1}"} if kk else {})} for i in range(options)]}
    if kk:
        d.update(problem_kk="Мәселе", blocker_kk="Кедергі", decision_kk="Шешу")
    return d


def test_decision_criterion():
    overdue_need = rec(1, age_days=20, category="roads", status="in_progress", metoo=4)
    overdue_need["delay"] = _delay()
    overdue_weather = rec(2, age_days=20, category="roads", status="in_progress")
    overdue_weather["delay"] = _delay("weather")
    fresh_need = rec(3, age_days=1, category="roads", status="in_progress")
    fresh_need["delay"] = _delay()
    fixed_need = rec(4, age_days=20, category="roads", history=[(1, "fixed")])
    fixed_need["delay"] = _delay()
    passport_form = rec(5, age_days=40, category="yards", status="accepted", district="esil")
    passport_form["passport"] = {"delay": {"needs_decision": True, "problem_ru": "Нет хозяина", "options": []}}
    d = summary([overdue_need, overdue_weather, fresh_need, fixed_need, passport_form])["decisions"]
    assert [i["id"] for i in d["items"]] == ["c-r08-5", "c-r08-1"]  # самая давняя просрочка первой
    one = d["items"][1]
    assert one["people"] == 5 and one["service"]["ru"] == "Дорожная служба"
    assert [o["ru"] for o in one["options"]] == ["Вариант 1", "Вариант 2"] and not one["options_missing"]
    assert one["problem_kk"] == "Мәселе" and not one["problem_kk_missing"]
    assert d["items"][0]["options_missing"] is True  # вариантов нет — это видно, а не спрятано
    assert d["demo"] is False and d["source"] == "complaints"


def test_decision_kk_missing_falls_back_with_flag():
    r = rec(1, age_days=20, category="roads", status="in_progress")
    r["delay"] = _delay(kk=False)
    item = summary([r])["decisions"]["items"][0]
    assert item["problem_kk"] == "Проблема" and item["problem_kk_missing"] is True
    assert item["options"][0]["kk_missing"] is True


def test_decisions_max_three_and_district_filter():
    records = []
    for i in range(5):
        r = rec(i, age_days=20 + i, category="roads", status="in_progress", district="nura" if i < 4 else "esil")
        r["delay"] = _delay()
        records.append(r)
    d = summary(records)["decisions"]
    assert d["count"] == 5 and len(d["items"]) == 3
    assert [i["id"] for i in summary(records, district="esil")["decisions"]["items"]] == ["c-r08-4"]


def test_decision_example_only_for_demo_complaints():
    """Пример из фикстуры — только когда жалобы сами демо (R07), и он проходит тот же критерий."""
    assert summary([rec(1, age_days=1)])["decisions"]["items"] == []  # свои записи без причин — пусто
    ex = decisions.fixture_records(NOW.date())
    built = decisions.build(ex, NOW, status_at=status_at, parse_time=parse_time)
    ids = [i["id"] for i in built]
    assert "c-demo-decision-4" not in ids, "погода — не решение акима"
    assert len(ids) == 3 and all(i["demo"] for i in built)
    s = svc([rec(1, age_days=1)])
    s.source_names["complaints"] = "r07-demo"
    d = s.summary(now=NOW)["decisions"]
    assert d["demo"] is True and d["source"] == "example" and len(d["items"]) == 3
    assert d["items"][0]["timer"]["state"] == "overdue"


@pytest.mark.parametrize("shift", range(0, 14))
def test_decision_example_stays_overdue_any_day(shift):
    today = NOW + timedelta(days=shift)
    ex = decisions.fixture_records(today.date())
    assert len(decisions.build(ex, today, status_at=status_at, parse_time=parse_time)) == 3


# ---------------------------------------------------------------- «Пульс» (волна 2 п. 8)

CATS = deadlines.load_categories()["categories"]
NAMES = {"nura": {"ru": "Нура", "kk": "Нұра"}, "esil": {"ru": "Есиль", "kk": "Есіл"}}


def _flow(district, category, weekly, *, start=0):
    """Записи: weekly[k] жалоб в неделю k назад (0 — последние 7 дней)."""
    out = []
    for k, n in enumerate(weekly):
        for j in range(n):
            out.append(rec(f"{district}-{category}-{k}-{j}", at=NOW - timedelta(days=7 * k + 0.5 + j * 0.3),
                           category=category, district=district))
    return out


def _alarms(records, items_now=(), items_prev=()):
    return pulse.alarms(records, NOW, parse_time=parse_time, district_of=lambda r: r.get("district"),
                        categories=CATS, district_names=NAMES, items_now=list(items_now), items_prev=list(items_prev))


def test_pulse_spike_against_four_week_mean():
    recs = _flow("nura", "snow_ice", [12, 3, 4, 3, 2, 1]) + _flow("nura", "roads", [5, 5, 4, 6, 5, 1])
    a = _alarms(recs)
    assert a["base_weeks"] == 4
    assert [x["kind"] for x in a["items"]] == ["spike"]
    x = a["items"][0]
    assert (x["category"], x["district"], x["value"], x["base"], x["ratio"]) == ("snow_ice", "nura", 12, 3.0, 4.0)
    assert x["text"]["ru"] == ("«Снег и гололёд» в районе Нура: 12 сообщений за 7 дней — в 4 раза больше обычного "
                               "(в среднем 3 в неделю за 4 недели).")
    assert "Нұра ауданында «Қар және көктайғақ»" in x["text"]["kk"] and "4 есе көп" in x["text"]["kk"]


def test_pulse_small_numbers_and_short_history_are_quiet():
    assert _alarms(_flow("nura", "snow_ice", [4, 1, 0, 1, 0, 1]))["items"] == []  # меньше 5 сообщений
    short = _alarms(_flow("nura", "snow_ice", [12, 2]))  # данных только за 2 недели
    assert short["items"] == [] and short["note"] == "too_little_history"


def test_pulse_new_topic_and_city_merge():
    recs = (_flow("nura", "smell_air", [6, 0, 0, 0, 0, 1]) + _flow("nura", "snow_ice", [10, 2, 2, 2, 2, 1])
            + _flow("esil", "snow_ice", [9, 3, 3, 3, 3, 1]))
    kinds = {x["kind"]: x for x in _alarms(recs)["items"]}
    assert set(kinds) == {"spike_new", "spike_city"}
    city = kinds["spike_city"]
    assert city["value"] == 19 and [d["district"] for d in city["districts"]] == ["nura", "esil"]
    assert city["text"]["ru"].startswith("«Снег и гололёд» — всплеск в 2 районах (Нура, Есиль)")
    assert "таких не было" in kinds["spike_new"]["text"]["ru"]


def test_pulse_metoo_and_new_hot_place():
    target = {"kind": "segment", "id": "seg-1"}
    r = rec("m", age_days=3, category="roads", target=target, district="nura")
    r["metoo_times"] = [(NOW - timedelta(hours=h)).isoformat() for h in (1, 2, 3, 5, 8, 30)]
    r["metoo"] = 6
    item = {"target": {**target, "label_ru": "Участок ул. Примерной", "label_kk": "Примерная көшесінің бөлігі"},
            "count": 7, "district": "nura", "by_category": {"roads": 7}, "state": "active"}
    a = _alarms([r], items_now=[item], items_prev=[])
    kinds = {x["kind"]: x for x in a["items"]}
    assert kinds["metoo"]["value"] == 5 and kinds["metoo"]["text"]["ru"] == "Быстро растёт «Я тоже»: Участок ул. Примерной — +5 за сутки."
    assert kinds["new_hot"]["target"]["id"] == "seg-1"
    # неделю назад место уже было на карте — не «новое»
    assert "new_hot" not in {x["kind"] for x in _alarms([r], items_now=[item], items_prev=[item])["items"]}


def test_pulse_at_most_five():
    recs = []
    for cat in ("snow_ice", "roads", "waste", "lighting", "yards", "parking", "transport"):
        recs += _flow("nura", cat, [10, 1, 1, 1, 1, 1])
    assert len(_alarms(recs)["items"]) == pulse.MAX_ALARMS


def test_pulse_in_summary_without_heat_is_unavailable():
    assert summary([rec(1, age_days=1)])["pulse"] == {"available": False, "items": []}


# ---------------------------------------------------------------- уточнение у горячего места (волна мелочей п. 12)

def test_hot_place_subtopic_is_majority_of_open_reports():
    t = {"kind": "traffic_signal", "id": "ts-1"}
    a = rec(1, age_days=2, category="roads", target=t, metoo=5)
    a["subtopic"] = "traffic_light_timing"
    b = rec(2, age_days=2, category="roads", target=t, metoo=1)
    b["subtopic"] = "traffic_light_broken"
    c = rec(3, age_days=2, category="roads", target=t, metoo=9, history=[(1, "fixed")])  # решено — не считаем
    c["subtopic"] = "traffic_light_broken"
    sub = _S._subtopic_of([a, b, c], NOW)
    assert (sub["id"], sub["people"], sub["category"]) == ("traffic_light_timing", 6, "roads")
    assert sub["ru"] == "Светофор: долго красный или зелёный" and sub["kk"]
    assert _S._subtopic_of([rec(4, age_days=1)], NOW) is None


def test_text_has_no_holes_with_new_parts():
    r = rec(1, age_days=20, category="roads", status="in_progress")
    r["delay"] = _delay()
    s = summary([r, _fixed(2, check="yes")])
    for lang in ("ru", "kk"):
        t = s["text"][lang]
        assert "None" not in t and "{" not in t and "  " not in t
    assert "Ждут вашего решения: 1 вопрос." in s["text"]["ru"]
    assert "Сіздің шешіміңізді күтетін мәселе: 1." in s["text"]["kk"]
    roles = [p["role"] for p in s["text_parts"]["ru"]]
    assert roles.index("fixed") < roles.index("decisions")


def test_api_payload_has_no_private_fields():
    import json as _j
    r = rec(1, age_days=20, category="roads", status="in_progress")
    r["delay"] = _delay()
    body = _j.dumps(summary([r, _fixed(2, check="yes")]), ensure_ascii=False)
    assert "секретный текст" not in body and "_items_now" not in body
