"""R08: все числа «Картины дня», у которых есть пара на карте, совпадают с тепловой картой R07.

Что сверяем (CONTRACT §6–§7, prompt R08 п.1 «все числа сходятся с тепловой картой — тест на это»):
- «Горячие места» = HeatService.top(10, days=7[, district]) — те же цели, порядок, число людей и уровень;
- «Темы» = сумма чисел карты с фильтром категории за 7 дней;
- «Районы» = карта на мелком масштабе (zoom < 12) за 7 дней;
- главная проблема = число района на карте с фильтром её категории;
- «неделю назад» и прошлые даты = та же карта R07, построенная по записям в их тогдашнем состоянии.

Нужен модуль R07 ui/civic_heat (в общей сборке он есть). Без него тест пропускается с причиной.
Данные — демо-набор R07 (все записи demo: true) + несколько смен статуса для проверки истории.
"""
from datetime import datetime, timedelta

import pytest

civic_heat = pytest.importorskip("ui.civic_heat", reason="модуль тепловой карты R07 не подключён в этой сборке")

from r08_helpers import NOW  # noqa: E402
from ui.civic_akim import AkimService  # noqa: E402
from ui.civic_akim.summary import snapshot  # noqa: E402
from ui.civic_heat import HeatService, demo_seed  # noqa: E402

WEEK = timedelta(days=7)
CATS = [c["id"] for c in civic_heat.load_config().categories]


def demo_records():
    """Демо R07 + обращения, которые за эту неделю сменили статус (чтобы «неделю назад» отличалось)."""
    records = demo_seed.demo_records(now=NOW)
    changed = 0
    for r in records:
        created = datetime.fromisoformat(r["created_at"])
        if r["status"] == "new" and NOW - created > timedelta(days=9) and changed < 6:
            fixed_at = NOW - timedelta(days=2 + changed % 3)
            r["status"] = "fixed"
            r["status_history"] = r["status_history"] + [{"at": fixed_at.isoformat(), "status": "fixed"}]
            changed += 1
    assert changed >= 3
    return records


RECORDS = demo_records()


def heat_for(records, now):
    return HeatService(source=lambda since: records, clock=lambda: now)


def akim_for(heat):
    return AkimService(heat=heat, objects=None, proposals=None, clock=lambda: NOW)


def active(items):
    return [it for it in items if it["state"] == "active"]


def map_total(heat, now, **filters):
    return sum(it["count"] for it in active(heat.heat(days=7, now=now, **filters)["items"]))


def map_districts(heat, now, **filters):
    return {it["district"]: it["count"] for it in heat.heat(days=7, zoom=0, now=now, **filters)["items"]
            if it["state"] == "active"}


@pytest.fixture(scope="module")
def heat():
    return heat_for(RECORDS, NOW)


@pytest.fixture(scope="module")
def city(heat):
    return akim_for(heat).summary(now=NOW)


@pytest.fixture(scope="module")
def nura(heat):
    return akim_for(heat).summary(now=NOW, district="nura")


def same_places(summary_hot, top):
    assert len(summary_hot) == len(top) > 0
    for h, it in zip(summary_hot, top):
        assert (h["target"]["kind"], h["target"]["id"]) == (it["target"]["kind"], it["target"]["id"])
        assert (h["count"], h["level"], h["weight"]) == (it["count"], it["level"], it["weight"])
        assert h["target"]["label_ru"] == it["target"]["label_ru"] and h["target"]["label_kk"] == it["target"]["label_kk"]


def test_demo_data_is_marked(city):
    assert city["demo"]["complaints"] is True and all(h["demo"] for h in city["hot"]["items"])


def test_hot_places_equal_heat_top(heat, city, nura):
    same_places(city["hot"]["items"], heat.top(10, days=7, now=NOW))
    same_places(nura["hot"]["items"], heat.top(10, days=7, district="nura", now=NOW))
    assert [h["rank"] for h in city["hot"]["items"]] == list(range(1, len(city["hot"]["items"]) + 1))


def test_topics_equal_map_with_category_filter(heat, city, nura):
    for s, district in ((city, None), (nura, "nura")):
        got = {t["category"]: t["value"] for t in s["topics"]["items"]}
        for c in CATS:
            assert got.get(c, 0) == map_total(heat, NOW, category=c, district=district), (district, c)
        values = [t["value"] for t in s["topics"]["items"]]
        assert values == sorted(values, reverse=True)
    # Сумма тем = все люди на карте без фильтра (каждая жалоба — ровно одна категория).
    assert city["topics"]["total"] == map_total(heat, NOW)


def test_districts_equal_map_district_mode(heat, city):
    on_map = map_districts(heat, NOW)
    got = {d["district"]: d["value"] for d in city["districts"]["items"]}
    assert set(got) == {"almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"}
    for d_id, value in got.items():
        assert value == on_map.get(d_id, 0), d_id
    assert sum(on_map.values()) > 0


def test_main_problem_equals_map(heat, city):
    m = city["main_problem"]
    assert m and m["value"] == map_districts(heat, NOW, category=m["category"]).get(m["district"])
    # Это действительно самая большая пара «тема × район».
    best = max(v for c in CATS for v in map_districts(heat, NOW, category=c).values())
    assert m["value"] == best
    assert f"сообщили {m['value']} человек" in city["text"]["ru"] or f"сообщил {m['value']} человек" in city["text"]["ru"] \
        or f"сообщили {m['value']} человека" in city["text"]["ru"]
    assert f"{m['value']} адам хабарлады" in city["text"]["kk"]


def test_week_ago_equals_heat_built_on_records_as_they_were(city):
    moment = NOW - WEEK
    past = heat_for([s for s in (snapshot(r, moment) for r in RECORDS) if s], moment)
    for t in city["topics"]["items"]:
        assert t["prev"] == map_total(past, moment, category=t["category"]), t["category"]
    prev_d = map_districts(past, moment)
    for d in city["districts"]["items"]:
        assert d["prev"] == prev_d.get(d["district"], 0), d["district"]


def test_past_date_equals_heat_at_end_of_that_day(heat):
    day = (NOW - timedelta(days=1)).date()
    s = akim_for(heat).summary(date=day.isoformat(), now=NOW)
    as_of = datetime.fromisoformat(s["as_of"])
    past = heat_for([x for x in (snapshot(r, as_of) for r in RECORDS) if x], as_of)
    same_places(s["hot"]["items"], past.top(10, days=7, now=as_of))
    for t in s["topics"]["items"]:
        assert t["value"] == map_total(past, as_of, category=t["category"])
    got = {d["district"]: d["value"] for d in s["districts"]["items"]}
    on_map = map_districts(past, as_of)
    assert all(got[d] == on_map.get(d, 0) for d in got)


def test_snapshot_now_does_not_change_the_map(heat):
    """Снимок «на сейчас» ничего не искажает: карта по снимку = живая карта."""
    snap = heat_for([s for s in (snapshot(r, NOW) for r in RECORDS) if s], NOW)
    a = [(it["target"]["id"], it["count"], it["level"], it["weight"]) for it in heat.heat(days=7, now=NOW)["items"]]
    b = [(it["target"]["id"], it["count"], it["level"], it["weight"]) for it in snap.heat(days=7, now=NOW)["items"]]
    assert a == b


def test_new_complaint_moves_both_map_and_day_picture():
    records = demo_seed.demo_records(now=NOW)
    heat = heat_for(records, NOW)
    akim = akim_for(heat)
    before = akim.summary(now=NOW)
    target_id = before["hot"]["items"][0]["target"]["id"]
    demo_seed.add_demo_complaint(records, target_id, now=NOW - timedelta(minutes=1))
    heat.invalidate()  # так делает R09 после новой жалобы; наш кэш привязан к поколению кэша карты
    after = akim.summary(now=NOW)
    assert after["kpi"]["new_day"]["value"] == before["kpi"]["new_day"]["value"] + 1
    top_after = {h["target"]["id"]: h["count"] for h in after["hot"]["items"]}
    assert top_after[target_id] == before["hot"]["items"][0]["count"] + 1
    same_places(after["hot"]["items"], heat.top(10, days=7, now=NOW))


def test_kpi_new_counts_come_from_same_records_as_map(heat, city):
    day_start = NOW.replace(hour=0, minute=0)
    expected = sum(1 for r in RECORDS if day_start <= datetime.fromisoformat(r["created_at"]) <= NOW)
    assert city["kpi"]["new_day"]["value"] == expected > 0


def test_summary_is_fast_on_thousands_of_records():
    import time
    big = []
    for k in range(16):  # ~2000 записей, те же цели
        for r in demo_seed.demo_records(now=NOW, seed=1000 + k):
            r = dict(r, id=f"{r['id']}-{k}")
            big.append(r)
    heat = heat_for(big, NOW)
    started = time.perf_counter()
    s = akim_for(heat).summary(now=NOW)
    took = time.perf_counter() - started
    assert s["stats"]["records"] == len(big) >= 1900
    assert took < 5.0, f"картина дня считалась {took:.1f} с"
