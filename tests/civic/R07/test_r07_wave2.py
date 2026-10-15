"""R07 раунд 14, волны 1–2: проверка жителями (heat_states), «вернули жители», срок ответа в рабочих днях,
уточнения (subtopics) и «нет свежих данных» у районов.

Запуск: python -m pytest tests/civic/R07/test_r07_wave2.py -q
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ui.civic_heat import HeatService, deadline, engine, geo, demo_seed
from ui.civic_heat.targets import TargetResolver

ROOT = Path(__file__).resolve().parents[3]
TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=TZ)          # понедельник
CATS = json.loads((ROOT / "research/round-14/categories_v2.json").read_text("utf-8"))
STATES = CATS["heat_states"]
TARGETS = demo_seed.load_targets()
SEG_ID = next(k for k, v in TARGETS.items() if v["kind"] == "segment" and v["district"] == "nura")


def at(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


def rec(i, *, age=1.0, status="new", history=None, metoo=0, **extra):
    r = {
        "id": f"c-w2-{i}", "created_at": at(age), "text": "т", "lang": "ru", "category": "roads", "category_source": "resident",
        "point": geo.anchor_of(TARGETS[SEG_ID]["geometry"]), "target": {"kind": "segment", "id": SEG_ID}, "district": "nura",
        "status": status, "status_history": history or [{"at": at(age), "status": "new"}], "metoo": metoo,
        "duplicate_of": None, "demo": True,
    }
    r.update(extra)
    return r


def fixed_rec(i, *, age=5.0, fixed=2.0, **extra):
    return rec(i, age=age, status="fixed", history=[{"at": at(age), "status": "new"}, {"at": at(fixed), "status": "fixed"}], **extra)


def heat(records, **kw):
    svc = HeatService(source=lambda since: records, resolver=TargetResolver(graph_path=None, use_r12=False), clock=lambda: NOW)
    return svc.heat(**{"days": 30, **kw})


def only(records, **kw):
    items = heat(records, **kw)["items"]
    assert len(items) == 1, items
    return items[0]


# ---------- волна 2, п. 1: «служба сообщила» → «проверено жителями» / «вернули жители» ----------

def test_reported_fixed_is_light_green_dashed_until_residents_check():
    it = only([fixed_rec(1), fixed_rec(2)])
    assert it["state"] == "fixed" and it["fixed_kind"] == "reported" and it["color"] == STATES["reported_fixed"]["color"]
    assert STATES["reported_fixed"]["dashed"] is True
    # 7 дней от ремонта (fixed_state.days_visible)
    assert it["fixed_until"] == (NOW - timedelta(days=2) + timedelta(days=7)).isoformat()
    assert heat([fixed_rec(1)])["stats"]["fixed_reported"] == 1


@pytest.mark.parametrize("fields", [
    {"resident_check": {"answer": "confirmed", "at": at(1)}},
    {"resident_checks": [{"answer": "yes", "at": at(1)}, {"answer": "cant_check", "at": at(0.5)}]},
    {"verification": "verified", "verified_at": at(1)},
    {"verified": True, "verified_at": at(1)},
    {"history_extra": {"at": at(1), "status": "verified"}},
    {"history_extra": {"at": at(1), "resident_check": "yes"}},
])
def test_verified_by_residents_is_green_for_7_days_from_the_answer(fields):
    extra = dict(fields)
    h = extra.pop("history_extra", None)
    r = fixed_rec(1, **extra)
    if h:
        r["status_history"].append(h)
    it = only([r, fixed_rec(2)])
    assert it["fixed_kind"] == "verified" and it["color"] == STATES["verified_fixed"]["color"]
    assert it["fixed_until"] == (NOW - timedelta(days=1) + timedelta(days=STATES["verified_fixed"]["days_visible"])).isoformat()
    assert it["checks"]["yes"] == 1


def test_verified_false_by_default_is_not_a_no():
    """R09 может хранить verified: false у непроверенных — это не «проблема осталась»."""
    it = only([fixed_rec(1, verified=False, resident_confirmed=False)])
    assert it["fixed_kind"] == "reported" and not it.get("reopened")


def test_answer_before_repair_does_not_count():
    it = only([fixed_rec(1, resident_check={"answer": "yes", "at": at(3)})])   # ответ раньше ремонта (2 дня назад)
    assert it["fixed_kind"] == "reported"


def test_cant_check_alone_keeps_reported():
    it = only([fixed_rec(1, resident_check={"answer": "cant_check", "at": at(1)})])
    assert it["fixed_kind"] == "reported" and it["checks"] == {"yes": 0, "no": 0, "cant": 1}


def test_verified_green_disappears_after_days_visible():
    r = fixed_rec(1, age=20, fixed=12, resident_check={"answer": "yes", "at": at(8)})
    assert heat([r])["items"] == []


def test_reopened_by_residents_turns_hot_again_with_history_kept():
    """Сценарий волны 2: исправили → житель: «Проблема осталась» → снова в работе, цвет по весу, отметка."""
    hist = [{"at": at(3), "status": "new"}, {"at": at(2.5), "status": "in_progress"}, {"at": at(1), "status": "fixed"},
            {"at": at(0.5), "status": "in_progress", "resident_check": "not_fixed"}]
    r = rec(1, age=3, status="in_progress", history=hist, metoo=3)
    it = only([r])
    assert it["state"] == "active" and it["reopened"] is True and it["reopened_at"] == at(0.5)
    assert it["count"] == 4 and it["status"] == "in_progress"
    assert it["color"] == CATS["heat_levels"][it["level"]]["color"]        # цвет по весу (heat_states.reopened.color = null)
    assert it["open_ids"] == ["c-w2-1"] and it["checks"]["no"] == 1
    assert heat([r])["stats"]["reopened"] == 1


def test_reopened_counts_from_the_moment_of_return():
    """Жалоба 20 дней назад, за 7 дней её бы не было; житель вернул вчера — она снова в периоде и «свежая»."""
    hist = [{"at": at(20), "status": "new"}, {"at": at(5), "status": "fixed"}, {"at": at(1), "status": "reopened"}]
    r = rec(1, age=20, status="in_progress", history=hist, metoo=1)
    it = only([r], days=7)
    assert it["reopened"] and it["count"] == 2
    assert it["weight"] == pytest.approx(2 * 0.5 ** (1 / 14), abs=1e-3)


def test_resident_no_on_still_fixed_record_reopens_it():
    """R09 ещё не сменил статус, а житель ответил «осталось» — карта честно показывает, что проблема есть."""
    it = only([fixed_rec(1, resident_check={"answer": "not_fixed", "at": at(1)})])
    assert it["state"] == "active" and it["reopened"] and it["status"] == "in_progress"


def test_later_yes_after_no_counts_as_verified_and_latest_answer_wins():
    r = fixed_rec(1, resident_checks=[{"answer": "no", "at": at(1.5)}, {"answer": "yes", "at": at(1)}])
    assert only([r])["fixed_kind"] == "verified"
    r2 = fixed_rec(2, resident_checks=[{"answer": "yes", "at": at(1.5)}, {"answer": "no", "at": at(1)}])
    assert only([r2])["reopened"]


def test_reopened_repair_does_not_close_examples():
    """Ремонт, который жители вернули, не закрывает примеры R07 (общая сборка: их статус не поменять)."""
    hist = [{"at": at(3), "status": "new"}, {"at": at(1), "status": "fixed"}, {"at": at(0.5), "status": "reopened"}]
    real = rec(1, age=3, status="in_progress", history=hist)
    example = rec(2, age=2, status="new", id="c-demo-0001")
    svc = HeatService(source=lambda since: [real, example], resolver=TargetResolver(graph_path=None, use_r12=False),
                      clock=lambda: NOW, examples_actionable=False)
    it = svc.heat(days=30)["items"][0]
    assert it["count"] == 2 and it["examples_open"] == 1 and it["open_ids"] == ["c-w2-1"]


def test_new_repair_after_reopen_is_reported_again():
    hist = [{"at": at(3), "status": "new"}, {"at": at(2), "status": "fixed"}, {"at": at(1.5), "status": "reopened"},
            {"at": at(1), "status": "fixed"}]
    it = only([rec(1, age=3, status="fixed", history=hist)])
    assert it["state"] == "fixed" and it["fixed_kind"] == "reported"


def test_legend_carries_heat_states_from_json():
    lg = heat([rec(1)])["legend"]
    assert lg["states"]["reported_fixed"] == {k: STATES["reported_fixed"][k] for k in ("color", "ru", "kk", "dashed")}
    assert lg["states"]["verified_fixed"]["color"] == STATES["verified_fixed"]["color"]
    assert lg["states"]["no_data"]["color"] == STATES["no_data"]["color"]


# ---------- волна 1, п. 6: срок ответа в рабочих днях ----------

def test_due_counts_workdays_and_skips_weekend():
    deadline.set_calendar(lambda d: d.weekday() < 5, "weekdays")
    try:
        # понедельник 12:00 → срок пятница 10:00: вт, ср, чт, пт = 4 рабочих дня
        it = only([rec(1, age=0.1, due_at=(NOW + timedelta(days=4) - timedelta(hours=2)).isoformat())])
        assert it["due"]["workdays_left"] == 4 and it["due"]["overdue_days"] is None
        # срок в следующий понедельник: вт–пт (4) + пн (1) = 5, суббота и воскресенье не съедают срок
        it = only([rec(1, age=0.1, due_at=(NOW + timedelta(days=7)).isoformat())])
        assert it["due"]["workdays_left"] == 5
        # просрочено на 1 день
        it = only([rec(1, age=3, due_at=(NOW - timedelta(days=1)).isoformat())])
        assert it["due"]["overdue_days"] == 1 and it["due"]["workdays_left"] is None
    finally:
        deadline.set_calendar(None)


def test_due_uses_holiday_calendar_when_given():
    holiday = date(2026, 10, 13)
    deadline.set_calendar(lambda d: d.weekday() < 5 and d != holiday, "test")
    try:
        it = only([rec(1, age=0.1, due_at=(NOW + timedelta(days=2)).isoformat())])
        assert it["due"]["workdays_left"] == 1 and it["due"]["calendar"] == "test"
    finally:
        deadline.set_calendar(None)


def test_due_only_for_new_complaints_and_earliest_wins():
    soon = (NOW + timedelta(days=1)).isoformat()
    later = (NOW + timedelta(days=6)).isoformat()
    it = only([rec(1, age=0.2, due_at=later), rec(2, age=0.1, due_at=soon),
               rec(3, age=0.3, status="in_progress", due_at=(NOW - timedelta(days=3)).isoformat())])
    assert it["due"]["at"] == soon
    accepted = only([rec(1, age=0.2, status="accepted", due_at=soon)])
    assert accepted["due"] is None
    assert only([rec(1)])["due"] is None               # без due_at (примеры R07) — строки нет


def test_without_r09_calendar_falls_back_to_weekdays():
    deadline.set_calendar(None)
    assert deadline._load_calendar()[1] in ("weekdays", "r09")


# ---------- волна 1, п. 12: уточнения ----------

def test_subtopics_are_counted_by_people_and_top_has_labels():
    rs = [rec(1, subtopic="traffic_light_timing", metoo=4), rec(2, subtopic="traffic_light_broken"),
          rec(3, subtopic={"id": "traffic_light_timing"}), rec(4), rec(5, subtopic="no-such-id", metoo=9)]
    it = only(rs)
    assert it["subtopics"]["traffic_light_timing"] == 6 and it["subtopics"]["traffic_light_broken"] == 1
    top = it["top_subtopic"]
    sub = next(s for c in CATS["categories"] for s in c.get("subtopics", []) if s["id"] == "traffic_light_timing")
    assert top == {"id": "traffic_light_timing", "ru": sub["ru"], "kk": sub["kk"], "count": 6}   # неизвестный id не берётся


def test_meta_lists_subtopics_from_json():
    svc = HeatService(source=lambda since: [], resolver=TargetResolver(graph_path=None, use_r12=False), clock=lambda: NOW)
    subs = svc.meta()["subtopics"]
    assert len(subs) == sum(len(c.get("subtopics", [])) for c in CATS["categories"])
    assert {"id", "ru", "kk", "category"} <= set(subs[0])


# ---------- волна 2, мелочи: «нет свежих данных» ----------

def test_districts_without_complaints_are_grey_no_data():
    items = heat([rec(1)], zoom=10)["items"]
    by_state = {}
    for it in items:
        by_state.setdefault(it["state"], []).append(it)
    assert [it["district"] for it in by_state["active"]] == ["nura"]
    grey = by_state["no_data"]
    assert len(grey) == len(geo.districts()) - 1
    assert all(it["color"] == STATES["no_data"]["color"] and it["count"] == 0 and it["level"] == 0 for it in grey)


def test_no_data_respects_district_filter():
    items = heat([rec(1)], zoom=10, district="esil")["items"]
    assert [(it["district"], it["state"]) for it in items] == [("esil", "no_data")]


def test_target_mode_has_no_grey_objects():
    """На крупном масштабе серых объектов нет: карта по умолчанию не становится сложнее."""
    assert all(it["state"] != "no_data" for it in heat([rec(1)])["items"])


# ---------- волна 1, п. 12: светофоры, переходы, перекрёстки — настоящие узлы OSM ----------

import gzip  # noqa: E402

from ui.civic_heat import osm_objects  # noqa: E402
from ui.civic_heat.targets import kk_and, node_labels  # noqa: E402

SNAPSHOT = ROOT / "data/civic/astana/osm-walking/overpass.json.gz"
GRAPH = ROOT / "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json"


def _fresh_nodes(set_name: str) -> dict:
    path = osm_objects.OSM_OBJECTS_DIR / "raw" / f"{set_name}.json.gz"
    if not path.exists():
        return {}
    return {e["id"]: e for e in json.loads(gzip.open(path).read().decode("utf-8"))["elements"] if e.get("type") == "node"}


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="NOT_RUN: нет снимка osm-walking")
def test_street_demo_targets_are_real_osm_nodes():
    raw = json.loads(gzip.open(SNAPSHOT).read().decode("utf-8"))
    nodes = {e["id"]: e for e in raw["elements"] if e["type"] == "node"}
    street = {tid: t for tid, t in TARGETS.items() if t.get("subtype") in ("traffic_signal", "crossing", "intersection")}
    assert {t["subtype"] for t in street.values()} == {"traffic_signal", "crossing", "intersection"}
    graph = json.loads(GRAPH.read_text("utf-8")) if GRAPH.exists() else None
    fresh = {"traffic_signal": _fresh_nodes("traffic_signals"), "crossing": _fresh_nodes("crossings")}
    for tid, t in street.items():
        n = nodes[t["osm"]["id"]]
        # R10 B-103: узел есть в свежем снимке LOCAL-10 — точка оттуда (источник osm-objects/<набор>), иначе — пешеходная сеть
        newer = fresh.get(t["subtype"], {}).get(n["id"])
        if newer is not None:
            assert t["source"] == "osm-objects/" + {"traffic_signal": "traffic_signals", "crossing": "crossings"}[t["subtype"]]
            n = dict(n, lon=newer["lon"], lat=newer["lat"])
        assert tid == f"osm-node-{n['id']}" and t["geometry"]["coordinates"] == [round(n["lon"], 7), round(n["lat"], 7)]
        hw = (n.get("tags") or {}).get("highway", "")
        if t["subtype"] == "traffic_signal":
            assert "traffic_signals" in hw and t["label_ru"].startswith("Светофор")
        if t["subtype"] == "crossing":
            assert hw == "crossing" and "переход" in t["label_ru"].lower()
        if t["subtype"] == "intersection" and graph:
            edges = [e for e in graph["edges"] if f"osm-n{n['id']}" in (e["from"], e["to"])]
            assert len(edges) >= 3 and len({e.get("name") for e in edges if e.get("name")}) >= 2
            assert t["label_ru"].startswith("Перекрёсток ") and t["label_kk"].endswith("қиылысы")
        assert t["district"] == geo.district_of(t["geometry"]["coordinates"])
        assert t["role"].startswith("city_") or t["district"] == "nura"


def test_street_nodes_resolve_with_own_subtype_and_label():
    r = TargetResolver(graph_path=None, use_r12=False)
    tid = next(t for t, v in TARGETS.items() if v.get("subtype") == "traffic_signal")
    got = r.resolve({"kind": "object", "id": tid})
    assert got["subtype"] == "traffic_signal" and got["label_ru"] == TARGETS[tid]["label_ru"]
    objs = osm_objects.load()
    sub = {}
    for v in objs.values():
        sub[v["subtype"]] = sub.get(v["subtype"], 0) + 1
    assert sub.get("traffic_signal", 0) > 500 and sub.get("crossing", 0) > 1000 and sub.get("intersection", 0) > 1000
    # любой узел из фикстуры — цель с подписью (жалобу R09/R12 на светофор не в демо тоже покажем по имени улиц)
    other = next(k for k, v in objs.items() if v["subtype"] == "intersection" and k not in TARGETS)
    got = r.resolve({"kind": "object", "id": other})
    assert got and got["subtype"] == "intersection" and got["label_ru"].startswith("Перекрёсток")
    assert osm_objects.plain_labels("intersection") == ("Перекрёсток", "Қиылыс")
    assert osm_objects.plain_labels("traffic_signal") == ("Светофор", "Бағдаршам")


def test_crossroads_labels_ru_kk():
    ru, kk = node_labels("intersection", [("проспект Кабанбай Батыра", "Қабанбай батыр даңғылы"), ("улица Сыганак", "Сығанақ көшесі")])
    assert ru == "Перекрёсток пр. Кабанбай Батыра и ул. Сыганак"
    assert kk == "Қабанбай батыр даңғылы мен Сығанақ көшесінің қиылысы"
    ru, kk = node_labels("traffic_signal", [("улица Сыганак", "Сығанақ көшесі")])
    assert ru == "Светофор у ул. Сыганак" and kk == "Сығанақ көшесі маңындағы бағдаршам"
    assert node_labels("crossing", []) is None
    assert (kk_and("Орынбор"), kk_and("Достық көшесі"), kk_and("Тұрар Рысқұлов")) == ("бен", "мен", "пен")


def test_demo_has_signal_with_subtopic_for_day_summary():
    """«Перекрёсток … — светофор, N жалоб» (волна 1, п. 12): у светофора в демо есть уточнение для R08 (top_subtopic)."""
    svc = HeatService(resolver=TargetResolver(graph_path=None, use_r12=False), clock=lambda: NOW)
    items = svc.heat(days=30)["items"]
    sig = next(it for it in items if it["target"].get("subtype") == "traffic_signal")
    assert sig["top_subtopic"]["id"].startswith("traffic_light") and sig["count"] >= 4
    assert any(it.get("reopened") for it in items)                                   # «вернули жители» в демо есть
    assert {it.get("fixed_kind") for it in items if it["state"] == "fixed"} >= {"reported", "verified"}


# ---------- формат R09 (lifecycle.py, claude/modest-shannon-0ki93p): resolution + votes ----------

def test_r09_resolution_verified_reported_reopened():
    fixed_h = [{"at": at(5), "status": "new"}, {"at": at(2), "status": "fixed"}]
    v = rec(1, age=5, status="fixed", history=list(fixed_h),
            resolution={"round": 1, "state": "verified", "reported_at": at(2), "verified_at": at(1), "reopened_at": None,
                        "votes": {"yes": 3, "no": 0, "cant": 1}})
    it = only([v])
    assert it["fixed_kind"] == "verified" and it["checks"] == {"yes": 3, "no": 0, "cant": 1}
    r = rec(2, age=5, status="fixed", history=list(fixed_h), resolution={"round": 1, "state": "reported", "reported_at": at(2), "votes": {}})
    assert only([r])["fixed_kind"] == "reported"
    back = rec(3, age=5, status="in_progress", history=fixed_h + [{"at": at(1), "status": "in_progress", "reopened_by_residents": True}],
               resolution={"round": 1, "state": "reopened", "reported_at": at(2), "reopened_at": at(1), "votes": {"yes": 0, "no": 2, "cant": 0}})
    it = only([back])
    assert it["reopened"] and it["reopened_at"] == at(1) and it["checks"]["no"] == 2


def test_history_reopened_by_residents_without_resolution():
    h = [{"at": at(4), "status": "new"}, {"at": at(2), "status": "fixed"}, {"at": at(1), "status": "in_progress", "reopened_by_residents": True}]
    assert only([rec(1, age=4, status="in_progress", history=h)])["reopened"]


def test_r09_calendar_is_working_day_is_used(monkeypatch):
    import sys
    import types
    fake = types.ModuleType("ui.civic_feedback.v2.workdays")
    holiday = date(2026, 10, 13)
    fake.is_working_day = lambda d: d.weekday() < 5 and d != holiday
    pkg = types.ModuleType("ui.civic_feedback.v2")
    pkg.workdays = fake
    monkeypatch.setitem(sys.modules, "ui.civic_feedback.v2", pkg)
    monkeypatch.setitem(sys.modules, "ui.civic_feedback.v2.workdays", fake)
    deadline.set_calendar(None)
    try:
        assert deadline._load_calendar()[1] == "r09"
        it = only([rec(1, age=0.1, due_at=(NOW + timedelta(days=2)).isoformat())])
        assert it["due"]["workdays_left"] == 1 and it["due"]["calendar"] == "r09"
        # просрочка — в рабочих днях, как у R09 deadline_info: срок пт 12:00, сейчас пн 12:00 → 1 рабочий день
        it = only([rec(2, age=4, due_at=(NOW - timedelta(days=3)).isoformat())])
        assert it["due"]["overdue_days"] == 1
    finally:
        deadline.set_calendar(None)
