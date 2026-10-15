"""R12 · раунд 15 · «Календарь работ» и «копаем один раз»: привязка работ к рёбрам OSM, три вида конфликтов, API.

    python3 -m pytest -q tests/civic/R12/test_works.py

Работы — СИНТЕТИКА фикстуры R12 (data/civic/astana/geo/works_fixture.json, demo: true) на настоящем графе OSM Астаны.
"""
import copy
from pathlib import Path
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


def test_advice_follows_what_is_already_done(real):
    """Совет на «сегодня»: асфальт ещё впереди — поменять порядок; уже уложен — беречь его; раскопка идёт; всё прошло."""
    end, dig = date(2026, 9, 25), date(2026, 10, 30)  # как пр. Кабанбай Батыра в демо-мире R02: асфальт в сентябре
    works = W.bind_all(_pair(end, dig), real)
    stages = {}
    for today in (date(2026, 9, 1), date(2026, 10, 15), date(2026, 11, 3), date(2026, 12, 1)):
        (c,) = W.find_conflicts(works, real, today)
        stages[c["stage"]] = c
    assert set(stages) == {"planned", "surface_done", "now", "past"}
    assert len({c["id"] for c in stages.values()}) == 1, "id конфликта не зависит от даты"
    assert stages["planned"]["advice_ru"].startswith("Сначала замените сети, потом кладите асфальт.")
    done = stages["surface_done"]
    assert done["advice_ru"].startswith("Новый асфальт уже уложен") and "Перенесите асфальт" not in done["advice_ru"]
    assert "прокол" in done["advice_ru"] and "тесу әдісімен" in done["advice_kk"]
    assert stages["now"]["advice_ru"].startswith("Раскопка уже идёт по новому асфальту")
    assert stages["past"]["advice_ru"].startswith("Новый асфальт вскрыли через 35 дней после укладки")
    for c in stages.values():
        assert "₸" not in c["advice_ru"] and "тенге" not in c["advice_ru"].lower() and "None" not in c["advice_kk"]
    # без today — как раньше: всё впереди
    assert W.find_conflicts(works, real)[0]["stage"] == "planned"


def test_past_conflicts_go_last_with_advice_for_next_time(real):
    past = _pair(date(2025, 5, 20), date(2025, 7, 1))
    soon = [dict(w, id=w["id"] + "2", segments=["osm-w1179911016-15", "osm-w1179911016-16"]) for w in
            _pair(date(2026, 11, 20), date(2027, 1, 10))]
    cs = W.find_conflicts(W.bind_all(past + soon, real), real, date(2026, 10, 15))
    assert [c["stage"] for c in cs] == ["planned", "past"], "прошедший — в конце, даже если он важнее"
    a = {"id": "a", "kind": "closure", "service": "road", "street": "улица Сыганак", "from": [71.381544, 51.130024],
         "to": [71.377997, 51.130475], "starts_on": "2026-08-01", "ends_on": "2026-08-20"}
    b = {"id": "b", "kind": "closure", "service": "traffic", "street": "улица Сыганак", "from": [71.377997, 51.130475],
         "to": [71.372275, 51.131209], "starts_on": "2026-08-10", "ends_on": "2026-08-25"}
    (c,) = W.find_conflicts(W.bind_all([a, b], real), real, date(2026, 10, 15))
    assert c["stage"] == "past" and c["advice_ru"].startswith("Это уже прошло. В следующий раз: не перекрывайте")
    assert c["advice_kk"].startswith("Бұл өтіп кетті. Келесі жолы: ")


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


def test_same_street_adjacent_closures_by_two_services(real):
    """Вариант same_street (демо-мир R02, cf-w15-04): соседние участки одной улицы перекрыты двумя службами разом."""
    a = {"id": "a", "kind": "closure", "service": "road", "street": "улица Сыганак", "from": [71.381544, 51.130024],
         "to": [71.377997, 51.130475], "starts_on": "2027-08-01", "ends_on": "2027-08-20"}
    b = {"id": "b", "kind": "closure", "service": "traffic", "street": "улица Сыганак", "from": [71.377997, 51.130475],
         "to": [71.372275, 51.131209], "starts_on": "2027-08-10", "ends_on": "2027-08-25"}
    cs = W.find_conflicts(W.bind_all([a, b], real), real)
    assert [(c["kind"], c["variant"], c["severity"]) for c in cs] == [("parallel_closures", "same_street", "medium")]
    assert cs[0]["title_ru"] == "Соседние участки улицы перекрыты одновременно" and cs[0]["overlap_days"] == 11
    assert "одно перекрытие" in cs[0]["advice_ru"] and "бір жабуға" in cs[0]["advice_kk"]
    # одна служба — это одно её перекрытие: не конфликт
    assert W.find_conflicts(W.bind_all([a, dict(b, service="road")], real), real) == []
    # далёкие участки одной улицы — не соседние: не конфликт
    far = dict(b, **{"from": [71.393086, 51.128589], "to": [71.398727, 51.127888]})
    assert W.find_conflicts(W.bind_all([a, far], real), real) == []


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
def test_api_staff_is_checked_by_gateway_explicit_false_denied(monkeypatch):
    """Сотрудника проверяет шлюз R01 (staff=True у маршрута) до вызова; явное staff=False — 401 и в модуле."""
    monkeypatch.setenv("CIVIC_DEMO", "1")
    status, body = api.handle("/works-calendar", {}, staff=False)
    assert status == 401 and body["error"]["code"] == "staff_required"
    status, body = api.handle("/works-conflicts", {}, staff=False)
    assert status == 401
    status, body = api.handle("/works-calendar", {})  # вызов шлюзом R01 после его проверки
    assert status == 200 and "conflicts" in body


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


# ---------- стыки: участок в узле, демо-мир R02 ----------
def test_street_segment_does_not_take_a_zero_length_piece_at_a_node(real):
    """Конец участка ровно в узле графа: соседнее ребро (нулевой кусок) в участок не входит — иначе работы,
    стыкующиеся в узле, ложно «делят» ребро (ложный конфликт same_segment_overlap)."""
    seg = W.segment_on_street("улица Сыганак", [71.381544, 51.130024], [71.377997, 51.130475], real)
    assert "osm-w1179911015-4" not in seg["edge_ids"] and seg["edge_ids"][-1] == "osm-w1179911015-3"
    assert all(abs(p["to_m"] - p["from_m"]) >= 1.0 for p in seg["pieces"])


def test_world_r02_relative_dates_and_outages(tmp_path):
    world = {"works": [
        {"id": "w-1", "type": "work", "kind": "surface", "starts_on": {"season": {"month": 5, "day": 4}},
         "ends_on": {"season": {"month": 5, "day": 22}}},
        {"id": "w-2", "type": "work", "kind": "dig", "starts_on": {"day": -30}, "ends_on": {"day": -9}},
        {"id": "o-1", "type": "outage", "utility": "water", "starts_at": "2026-10-16T08:00:00+05:00"},
        {"id": "o-2", "type": "outage", "utility": "road_closure", "starts_at": "2026-10-17T22:00:00+05:00",
         "ends_at": "2026-10-18T06:00:00+05:00"},
    ]}
    got = {w["id"]: w for w in load_world(TODAY, raw_world=world)}
    assert set(got) == {"w-1", "w-2", "o-2"}  # отключение воды — не работа на улице
    assert (got["w-1"]["starts_on"], got["w-1"]["ends_on"]) == ("2027-05-04", "2027-05-22")  # следующий сезон
    assert (got["w-2"]["starts_on"], got["w-2"]["ends_on"]) == ("2026-09-15", "2026-10-06")
    assert W.work_dates(got["o-2"]) == (date(2026, 10, 17), date(2026, 10, 18))
    assert load_world(date(2027, 2, 1), raw_world=world)[0]["starts_on"] == "2027-05-04"  # январь–март — этот год


def test_planned_conflict_ids_from_world(real, fixture_works, tmp_path, monkeypatch):
    from engine.civic_geo import works_calendar as WC
    p = tmp_path / "world_v1.json"
    p.write_text(json.dumps({"planned_conflicts": [{"id": "cf-w15-01", "kind": "dig_after_surface",
                                                    "works": ["w-demo-r12-02", "w-demo-r12-01"]}]}), "utf-8")
    monkeypatch.setattr(WC, "WORLD_PATH", p)
    monkeypatch.setattr(WC.planned_ids, "__defaults__", (p,))
    cal = build_calendar(fixture_works, *PERIOD, {}, TODAY, real)
    c = next(c for c in cal["conflicts"] if c["works"] == ["w-demo-r12-01", "w-demo-r12-02"])
    assert c["id"] == "cf-w15-01" and c.get("planned") is True
    w2 = next(w for w in cal["works"] if w["id"] == "w-demo-r12-02")
    assert "cf-w15-01" in w2["conflicts"]


WORLD = FIXTURE_PATH.parents[1] / "demo-world" / "world_v1.json"


@pytest.mark.skipif(not WORLD.is_file(), reason="демо-мира R02 нет в этой сборке (data/civic/astana/demo-world/world_v1.json)")
def test_demo_world_planned_conflicts_are_found(real):
    """Мир R02: поиск R12 находит все задуманные конфликты на тех же работах и не находит лишних."""
    world = json.loads(WORLD.read_text("utf-8"))
    works = load_world(TODAY)
    found = {(c["kind"], tuple(c["works"])) for c in W.find_conflicts(W.bind_all(works, real), real)}
    planned = {(c["kind"], tuple(sorted(c["works"]))) for c in world.get("planned_conflicts") or []}
    assert planned <= found, planned - found
    assert len(found - planned) <= 1, found - planned


def test_seed_world_remembers_works_and_planned_ids(real, monkeypatch):
    """R01: engine.civic_geo.seed_world(db_path, records, now) — R12 не пишет в базу, но календарь берёт мир и id."""
    import engine.civic_geo as geo_pkg
    from datetime import datetime, timezone
    from engine.civic_geo import works_calendar as WC
    fixture = json.loads(FIXTURE_PATH.read_text("utf-8"))["works"]
    world = {"works": [dict(w, starts_on=w["starts_on"], ends_on=w["ends_on"]) for w in fixture],
             "planned_conflicts": [{"id": "cf-w15-01", "kind": "dig_after_surface", "works": ["w-demo-r12-01", "w-demo-r12-02"]}]}
    try:
        rep = geo_pkg.seed_world("/nonexistent.sqlite3", world, datetime(2026, 10, 15, 7, 0, tzinfo=timezone.utc))
        assert rep["inserted"] == 0 and rep["skipped"] == 15 and rep["planned_conflicts"] == 1
        monkeypatch.setenv("CIVIC_DEMO", "1")
        monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
        records, info = WC.load_works(TODAY)
        assert "world" in info["source"] and len(records) == 15
        cal = build_calendar(records, *PERIOD, {}, TODAY, real)
        assert "cf-w15-01" in {c["id"] for c in cal["conflicts"]}
        assert "scene_conflict" not in cal, "сцены в мире нет — экран открывается на первом по срочности"
    finally:
        WC._WORLD.clear()


def test_world_scene8_conflict_opens_first_but_keeps_the_order(real, monkeypatch):
    """Мир R02 называет конфликт сцены 8 (scenes.scene8.conflict): только в режиме мира он приходит как scene_conflict."""
    import engine.civic_geo as geo_pkg
    from datetime import datetime, timezone
    from engine.civic_geo import works_calendar as WC
    fixture = json.loads(FIXTURE_PATH.read_text("utf-8"))["works"]
    world = {"works": fixture, "scenes": {"scene8": {"conflict": "cf-w15-01"}},
             "planned_conflicts": [{"id": "cf-w15-01", "kind": "dig_after_surface", "works": ["w-demo-r12-01", "w-demo-r12-02"]}]}
    try:
        geo_pkg.seed_world(None, world, datetime(2026, 10, 15, 7, 0, tzinfo=timezone.utc))
        monkeypatch.setenv("CIVIC_DEMO", "1")
        monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
        records, _ = WC.load_works(TODAY)
        cal = build_calendar(records, *PERIOD, {}, TODAY, real)
        assert cal["scene_conflict"] == "cf-w15-01"
        plain = build_calendar(records, *PERIOD, {}, TODAY, real)
        assert [c["id"] for c in cal["conflicts"]] == [c["id"] for c in plain["conflicts"]]
        # фильтр без этого конфликта — поля нет
        assert "scene_conflict" not in build_calendar(records, *PERIOD, {"service": "lighting"}, TODAY, real)
        monkeypatch.delenv("CIVIC_DEMO_WORLD")
        assert "scene_conflict" not in build_calendar(records, *PERIOD, {}, TODAY, real)
    finally:
        WC._WORLD.clear()


# ---------- LOCAL-5: реальные работы из CSV (файла в репозитории нет — тест на ТЕСТОВОЙ таблице) ----------
def test_real_works_csv_binding_and_coverage(real):
    """Синтетическая таблица с пометкой «ТЕСТ»: участок между перекрёстками, примерное место, без места, без дат."""
    from engine.civic_geo.real_works import load_real_works
    works, cov = load_real_works(Path(__file__).parent / "fixtures" / "real_works_TEST.csv", real)
    assert cov["status"] == "OK" and cov["total"] == 4
    assert (cov["on_segments"], cov["approximate"], cov["no_place"], cov["no_dates"]) == (1, 2, 1, 1)
    first = works[0]
    assert first["source"] == "real" and first["demo"] is False and first["place_bind"] == "street_between"
    assert first["kind"] == "surface" and first["service"] == "road" and first["status"] == "planned"
    assert (first["starts_on"], first["ends_on"]) == ("2027-05-01", "2027-05-20")
    assert first["source_ref"] == "https://example.org/test-1" and first["source_name"] == "example.org"
    edges = [real.by_id[e] for e in first["segments"]]
    assert edges and all(e.name == "улица Сыганак" for e in edges)
    second = works[1]
    assert second["place_bind"] == "street_only" and second.get("point") and not second.get("segments")
    assert (second["starts_on"], second["ends_on"], second.get("dates_approx")) == ("2027-06-01", "2027-06-30", True)
    assert second["kind"] == "dig" and second["service"] == "water"
    third = works[2]
    assert third["place_bind"] == "none" and third["source_ref"] is None  # javascript: — не ссылка
    assert third["ends_on"] == "2027-07-15" and third.get("delayed") is True
    assert works[3]["starts_on"] is None and works[3]["kind"] == "closure"
    bound = W.bind_all(works, real)
    assert [w.approximate for w in bound] == [False, True, True, True]


def test_real_works_missing_file_is_not_run(tmp_path):
    from engine.civic_geo.real_works import load_real_works
    works, cov = load_real_works(tmp_path / "records.csv")
    assert works == [] and cov["status"] == "NOT_RUN" and "нет файла" in cov["reason"]


def test_real_works_do_not_hide_the_demo_scene(real, monkeypatch):
    """Настоящие работы LOCAL-5 добавляются к демо, а не вместо него (сцена 8 остаётся в календаре)."""
    from engine.civic_geo import real_works as RW, works_calendar as WC
    csv_path = Path(__file__).parent / "fixtures" / "real_works_TEST.csv"
    monkeypatch.setattr(RW, "REAL_PATH", csv_path)
    monkeypatch.setattr(RW.load_real_works, "__defaults__", (csv_path, None))
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    records, info = WC.load_works(TODAY)
    assert info["source"].endswith("fixture+real") and info["real"]["total"] == 4
    ids = {r["id"] for r in records}
    assert "w-demo-r12-01" in ids and sum(1 for i in ids if i.startswith("w-real-")) == 4


def test_conflicts_summary_for_neighbours_has_numbers_and_advice(real, monkeypatch):
    """R08 / R17 / R03: сводка — те же числа, что календарь, и совет первого конфликта (R03 читает advice_ru)."""
    from engine.civic_geo import works_calendar as WC
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    monkeypatch.setattr(WC, "read_r06", lambda: (None, "module_missing"))
    got = WC.conflicts_summary()
    assert got["conflicts"] >= 1 and got["high"] >= 1 and got["source"] == "fixture" and got["demo"] is True
    top = got["top"][0]
    assert top["advice_ru"] and top["advice_kk"] and top["stage"] in ("planned", "surface_done", "now")
    assert set(top) >= {"id", "kind", "severity", "title_ru", "street_ru", "when_from", "works"}
    assert len(got["top"]) <= 3
