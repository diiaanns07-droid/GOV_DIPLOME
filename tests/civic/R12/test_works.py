"""R12 · раунд 15 · «Календарь работ» и «копаем один раз»: привязка работ к рёбрам OSM, три вида конфликтов, API.

    python3 -m pytest -q tests/civic/R12/test_works.py

Работы — СИНТЕТИКА фикстуры R12 (data/civic/astana/geo/works_fixture.json, demo: true) на настоящем графе OSM Астаны.
"""
import copy
import json
import random
import time
from datetime import date, timedelta

import pytest

from engine.civic_geo import api, geo, works as W
from engine.civic_geo.graph import get_graph
from engine.civic_geo.works_calendar import (FIXTURE_PATH, build_calendar, load_fixture, load_world, parse_period,
                                             CalendarError)

TODAY = date(2026, 10, 15)          # anchor фикстуры
PERIOD = (date(2026, 7, 1), date(2027, 12, 31))


@pytest.fixture(scope="module")
def real():
    return get_graph()


@pytest.fixture(scope="module")
def fixture_works():
    return load_fixture(TODAY)


@pytest.fixture()
def cal(real, fixture_works):
    return build_calendar(fixture_works, *PERIOD, {}, TODAY, real)


def by_pair(conflicts):
    return {(c["kind"], tuple(c["works"])): c for c in conflicts}


# ---------- привязка: только рёбра графа, форма OSM (CONTRACT §8) ----------
def test_every_fixture_line_lies_on_its_osm_edges(real, fixture_works):
    """Линия работы ≤ 5 м от формы её рёбер (проверка каждые 2 м, geo.max_offset_m)."""
    checked = 0
    for w in W.bind_all(fixture_works, real):
        if w.approximate:
            continue
        refs = [e.geometry for e in w.edges]
        for line in w.lines:
            assert geo.max_offset_m(line, refs) <= 5.0, (w.id, geo.max_offset_m(line, refs))
            checked += 1
        assert w.length_m > 100, w.id
    assert checked >= 14


def test_bind_by_street_and_two_points_stays_on_that_street(real):
    w = W.bind_work({"id": "t-1", "kind": "dig", "street": "ул. Сыганак", "from": [71.381544, 51.130024],
                     "to": [71.372275, 51.131209], "starts_on": "2027-07-01", "ends_on": "2027-07-20"}, real)
    assert w.bind == "street" and not w.approximate
    assert {e.name for e in w.edges} == {"улица Сыганак"}
    assert w.street_ru == "улица Сыганак" and w.street_kk == "Сығанақ көшесі"
    assert 600 < w.length_m < 720


def test_bind_by_line_snaps_to_the_street(real):
    """Линия из редактора (3 точки «от руки» рядом с улицей) → рёбра улицы, а не нарисованная линия."""
    hand = [[71.3815, 51.13006], [71.3770, 51.13063], [71.37228, 51.13125]]
    w = W.bind_work({"id": "t-2", "kind": "surface", "geometry": {"type": "LineString", "coordinates": hand},
                     "starts_on": "2027-05-01", "ends_on": "2027-05-10"}, real)
    assert w.bind == "line" and not w.approximate
    assert all(e.name == "улица Сыганак" for e in w.edges)
    refs = [e.geometry for e in w.edges]
    assert all(geo.max_offset_m(line, refs) <= 5.0 for line in w.lines)


def test_point_only_is_approximate_place_not_a_line(real, fixture_works):
    approx = [w for w in W.bind_all(fixture_works, real) if w.approximate]
    assert [w.id for w in approx] == ["w-demo-r12-15"]
    pub = approx[0].to_public()
    assert pub["geometry"]["type"] == "Point" and pub["radius_m"] == W.APPROX_RADIUS_M and pub["segments"] == []


def test_unknown_segments_become_approximate_with_issue(real):
    w = W.bind_work({"id": "t-3", "segments": ["osm-w1-999999"], "point": [71.38, 51.13], "kind": "dig",
                     "starts_on": "2027-01-01", "ends_on": "2027-01-05"}, real)
    assert w.approximate and "unknown_segment" in w.issues


def test_legacy_record_fields_still_work(real):
    """Запись раунда 14 без полей v2: work_kind и start/planned_end → вид и даты."""
    w = W.bind_work({"id": "nb-1", "type": "work", "work_kind": "roadworks", "start": "2026-10-03",
                     "planned_end": "2026-10-17", "status": "in_progress"}, real)
    assert w.kind == "surface" and w.start == date(2026, 10, 3) and w.end == date(2026, 10, 17)
    assert w.approximate and w.bind == "none"


# ---------- конфликты ----------
EXPECTED = {
    ("dig_after_surface", ("w-demo-r12-01", "w-demo-r12-02")): "high",
    ("same_segment_overlap", ("w-demo-r12-07", "w-demo-r12-08")): "high",
    ("dig_after_surface", ("w-demo-r12-09", "w-demo-r12-10")): "medium",
    ("same_segment_overlap", ("w-demo-r12-03", "w-demo-r12-04")): "medium",
    ("parallel_closures", ("w-demo-r12-05", "w-demo-r12-06")): "medium",
}


def test_all_three_conflict_kinds_on_fixture_and_nothing_else(cal):
    got = {k: c["severity"] for k, c in by_pair(cal["conflicts"]).items()}
    assert got == EXPECTED
    assert cal["counts"]["by_kind"] == {"dig_after_surface": 2, "same_segment_overlap": 2, "parallel_closures": 1}


def test_scene8_asphalt_may_networks_july_on_real_nura_street(cal):
    c = by_pair(cal["conflicts"])[("dig_after_surface", ("w-demo-r12-01", "w-demo-r12-02"))]
    assert c["street_ru"] == "ул. Сыганак" and c["street_kk"] == "Сығанақ көшесі"
    assert c["surface_ends_on"].endswith("-05-20") and c["dig_starts_on"].endswith("-07-20")
    assert c["gap_days"] == 61
    assert c["advice_ru"].startswith("Сначала замените сети, потом кладите асфальт")
    assert c["advice_kk"].startswith("Алдымен желілерді ауыстырыңыз")
    assert "через 2 месяца" in c["advice_ru"] and "2 айдан кейін" in c["advice_kk"]
    assert c["geometry"]["type"] == "MultiLineString" and c["segments"]
    assert c["id"].startswith("cf-") and c["demo"] is True


def test_conflict_segments_are_osm_edges_and_bbox_covers_geometry(cal, real):
    for c in cal["conflicts"]:
        assert all(s in real.by_id for s in c["segments"])
        refs = [real.by_id[s].geometry for s in c["segments"]]
        for line in c["geometry"]["coordinates"]:
            assert geo.max_offset_m(line, refs) <= 5.0
        x0, y0, x1, y1 = c["bbox"]
        assert all(x0 - 1e-6 <= p[0] <= x1 + 1e-6 and y0 - 1e-6 <= p[1] <= y1 + 1e-6
                   for line in c["geometry"]["coordinates"] for p in line)


def test_advice_has_no_money_and_no_empty_parts(cal):
    for c in cal["conflicts"]:
        for key in ("advice_ru", "advice_kk", "title_ru", "title_kk"):
            text = c[key]
            assert text and "None" not in text and "₸" not in text and "тенге" not in text.lower(), (key, text)


def test_deterministic_ids_and_order(real, fixture_works):
    a = build_calendar(fixture_works, *PERIOD, {}, TODAY, real)
    shuffled = copy.deepcopy(fixture_works)
    random.Random(15).shuffle(shuffled)
    b = build_calendar(shuffled, *PERIOD, {}, TODAY, real)
    assert [c["id"] for c in a["conflicts"]] == [c["id"] for c in b["conflicts"]]
    assert [r["key"] for r in a["rows"]] == [r["key"] for r in b["rows"]]
    assert [w["id"] for w in a["works"]] == [w["id"] for w in b["works"]]


def _pair(surface_end: date, dig_start: date, same=True):
    seg_a = ["osm-w1179911015-0", "osm-w734363112-6"]
    seg_b = seg_a if same else ["osm-w1179911016-15", "osm-w1179911016-16"]
    return [
        {"id": "s", "service": "road", "kind": "surface", "segments": seg_a,
         "starts_on": (surface_end - timedelta(days=10)).isoformat(), "ends_on": surface_end.isoformat()},
        {"id": "d", "service": "water", "kind": "dig", "segments": seg_b,
         "starts_on": dig_start.isoformat(), "ends_on": (dig_start + timedelta(days=10)).isoformat()},
    ]


def test_dig_after_surface_threshold_18_months(real):
    end = date(2027, 5, 20)
    inside = W.find_conflicts(W.bind_all(_pair(end, W.add_months(end, 18)), real), real)
    outside = W.find_conflicts(W.bind_all(_pair(end, W.add_months(end, 18) + timedelta(days=1)), real), real)
    assert [c["kind"] for c in inside] == ["dig_after_surface"]
    assert outside == []


def test_networks_first_then_asphalt_is_not_a_conflict(cal):
    ids = {w for c in cal["conflicts"] for w in c["works"]}
    assert "w-demo-r12-11" not in ids and "w-demo-r12-12" not in ids


def test_adjacent_carriageway_gives_medium(real):
    cs = W.find_conflicts(W.bind_all(_pair(date(2027, 5, 20), date(2027, 7, 1), same=False), real), real)
    assert [(c["kind"], c["severity"]) for c in cs] == [("dig_after_surface", "medium")]


def test_cancelled_and_same_service_are_ignored(real, fixture_works):
    recs = copy.deepcopy(fixture_works)
    for r in recs:
        if r["id"] == "w-demo-r12-02":
            r["status"] = "cancelled"
        if r["id"] == "w-demo-r12-04":
            r["service"] = "heating"  # та же служба, что у 03 — свои работы она планирует сама
    got = by_pair(build_calendar(recs, *PERIOD, {}, TODAY, real)["conflicts"])
    assert ("dig_after_surface", ("w-demo-r12-01", "w-demo-r12-02")) not in got
    assert ("same_segment_overlap", ("w-demo-r12-03", "w-demo-r12-04")) not in got


def test_parallel_closures_need_time_overlap(real, fixture_works):
    recs = copy.deepcopy(fixture_works)
    for r in recs:
        if r["id"] == "w-demo-r12-06":
            r["starts_on"], r["ends_on"] = "2027-09-01", "2027-09-10"  # после перекрытия Айтеке Би
    got = by_pair(build_calendar(recs, *PERIOD, {}, TODAY, real)["conflicts"])
    assert not any(k[0] == "parallel_closures" for k in got)


def test_same_street_closures_are_not_parallel(real):
    a = {"id": "a", "kind": "closure", "street": "улица Сыганак", "from": [71.381544, 51.130024],
         "to": [71.377997, 51.130475], "starts_on": "2027-08-01", "ends_on": "2027-08-20"}
    b = {"id": "b", "kind": "closure", "street": "улица Сыганак", "from": [71.376426, 51.130671],
         "to": [71.372275, 51.131209], "starts_on": "2027-08-01", "ends_on": "2027-08-20"}
    assert W.find_conflicts(W.bind_all([a, b], real), real) == []


# ---------- календарь ----------
def test_empty_period_has_no_rows_and_no_conflicts(real, fixture_works):
    cal = build_calendar(fixture_works, date(2030, 1, 1), date(2030, 6, 30), {}, TODAY, real)
    assert cal["rows"] == [] and cal["works"] == [] and cal["conflicts"] == []
    assert cal["counts"]["works"] == 0 and cal["months"][0] == "2030-01" and len(cal["months"]) == 6


def test_rows_by_street_conflicts_first(cal):
    rows = cal["rows"]
    assert rows[0]["conflicts"] >= 1
    first_plain = next(i for i, r in enumerate(rows) if r["conflicts"] == 0)
    assert all(r["conflicts"] == 0 for r in rows[first_plain:])
    syg = next(r for r in rows if r["street_ru"] == "ул. Сыганак")
    assert syg["works"] == ["w-demo-r12-01", "w-demo-r12-02"] and syg["street_kk"] == "Сығанақ көшесі"
    assert rows[-1]["key"] in ("place:none",) or rows[-1]["conflicts"] == 0


def test_service_filter_keeps_partner_work_as_context(real, fixture_works):
    cal = build_calendar(fixture_works, *PERIOD, {"service": "water"}, TODAY, real)
    ids = {w["id"]: w for w in cal["works"]}
    assert "w-demo-r12-02" in ids and not ids["w-demo-r12-02"].get("context")
    assert ids["w-demo-r12-01"].get("context") is True  # асфальт дорожной службы — вторая сторона конфликта
    assert {c["kind"] for c in cal["conflicts"]} == {"dig_after_surface"}


def test_district_and_street_filters(real, fixture_works):
    assert build_calendar(fixture_works, *PERIOD, {"district": "esil"}, TODAY, real)["works"] == []
    cal = build_calendar(fixture_works, *PERIOD, {"street": "Сығанақ"}, TODAY, real)
    assert {w["id"] for w in cal["works"]} == {"w-demo-r12-01", "w-demo-r12-02"}


def test_services_have_names_and_colors_without_green_or_red(cal):
    for s in cal["services"]:
        assert s["name_ru"] and s["name_kk"] and s["color"].startswith("#") and len(s["color"]) == 7
        r, g, b = (int(s["color"][i:i + 2], 16) for i in (1, 3, 5))
        assert not (g > r + 60 and g > b + 60), s  # зелёный — только «исправлено»
        assert not (r > g + 120 and r > b + 120), s  # красный — только конфликт


def test_period_parsing_defaults_and_limits():
    start, end = parse_period({}, TODAY)
    assert start == date(2026, 9, 1) and end == date(2027, 9, 30)
    assert parse_period({"from": "2027-05", "to": "2027-07"}, TODAY) == (date(2027, 5, 1), date(2027, 7, 31))
    with pytest.raises(CalendarError):
        parse_period({"from": "2027-05-01", "to": "2027-04-01"}, TODAY)
    with pytest.raises(CalendarError):
        parse_period({"from": "2026-01", "to": "2028-12"}, TODAY)
    with pytest.raises(CalendarError):
        parse_period({"from": "май"}, TODAY)


def test_fixture_dates_move_whole_years_for_a_late_show():
    late = load_fixture(date(2028, 2, 1))
    w1 = next(w for w in late if w["id"] == "w-demo-r12-01")
    assert w1["starts_on"] == "2028-05-04" and w1["ends_on"] == "2028-05-20"


def test_world_relative_dates(tmp_path):
    p = tmp_path / "world.json"
    p.write_text(json.dumps({"works": [{"id": "w-1", "kind": "dig", "starts_in_days": 30, "ends_in_days": 45},
                                       {"id": "w-2", "kind": "surface", "starts_ago_days": 20, "days": 5}]}), "utf-8")
    got = {w["id"]: w for w in load_world(TODAY, p)}
    assert got["w-1"]["starts_on"] == "2026-11-14" and got["w-1"]["ends_on"] == "2026-11-29"
    assert got["w-2"]["starts_on"] == "2026-09-25" and got["w-2"]["ends_on"] == "2026-09-29"
    assert got["w-1"]["demo"] is True


def test_sixty_works_and_conflicts_under_300_ms(real, fixture_works):
    recs = []
    for k in range(4):
        for r in fixture_works:
            x = copy.deepcopy(r)
            x["id"] = f"{r['id']}-{k}"
            for key in ("starts_on", "ends_on"):
                x[key] = (date.fromisoformat(x[key]) + timedelta(days=37 * k)).isoformat()
            recs.append(x)
    recs = recs[:60]
    W._bind_cache.clear()
    t = time.perf_counter()
    cal = build_calendar(recs, date(2026, 9, 1), date(2028, 8, 31), {}, TODAY, real)
    ms = (time.perf_counter() - t) * 1000
    assert len(recs) == 60 and cal["counts"]["conflicts"] > 5
    assert ms < 300, ms


# ---------- маршруты (raw, strip_prefix; сотрудник — staff=True от шлюза) ----------
def test_api_requires_staff(monkeypatch):
    monkeypatch.setenv("CIVIC_DEMO", "1")
    status, body = api.handle("/works-calendar", {})
    assert status == 401 and body["error"]["code"] == "staff_required"
    status, body = api.handle("/works-conflicts", {}, staff=None)
    assert status == 401


def test_api_calendar_and_conflicts_with_fixture_in_demo(monkeypatch):
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    status, body = api.handle("/works-calendar", {"from": ["2026-07"], "to": ["2027-12"]}, staff=True)
    assert status == 200, body
    assert "fixture" in body["source"] and body["counts"]["conflicts"] >= 5 and body["demo"] is True
    status, conf = api.handle("/works-conflicts", {"from": ["2026-07"], "to": ["2027-12"], "district": ["nura"]}, staff=True)
    assert status == 200 and len(conf["conflicts"]) >= 5
    assert all(set(c["works"]) <= set(conf["works"]) for c in conf["conflicts"])


def test_api_without_demo_and_without_r06_is_empty_not_error(monkeypatch):
    monkeypatch.delenv("CIVIC_DEMO", raising=False)
    status, body = api.handle("/works-calendar", {}, staff=True)
    assert status == 200 and body["works"] == [] and body["conflicts"] == []


@pytest.mark.parametrize("query,code", [
    ({"from": ["2027-13"]}, "bad_date"), ({"district": ["mars"]}, "bad_district"),
    ({"service": ["unknown"]}, "bad_service"), ({"from": ["2026-01"], "to": ["2029-01"]}, "period_too_long"),
    ({"street": ["x" * 81]}, "bad_street"),
])
def test_api_bad_params(query, code):
    status, body = api.handle("/works-calendar", query, staff=True)
    assert status == 400 and body["error"]["code"] == code


def test_fixture_file_is_synthetic_and_on_known_edges(real):
    data = json.loads(FIXTURE_PATH.read_text("utf-8"))
    assert data["anchor"] == "2026-10-15" and "СИНТЕТИКА" in data["about"]
    for w in data["works"]:
        assert w["demo"] is True and w["source"] == "demo" and w["district"] == "nura"
        assert all(s in real.by_id for s in w.get("segments") or [])
