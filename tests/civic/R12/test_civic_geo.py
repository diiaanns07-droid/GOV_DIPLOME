"""R12 · engine/civic_geo: геометрия, граф, участок улицы, targets, API, отчёт точности.

    python3 -m pytest -q tests/civic/R12/test_civic_geo.py

Маленькая фикстура (tests/civic/R12/fixtures) — СИНТЕТИКА. Тесты с пометкой real_graph читают настоящий
граф OSM Астаны (только чтение, ~2 с на загрузку).
"""
import json
import time
from pathlib import Path

import pytest

from engine.civic_geo import accuracy, api, build_geo_data, geo, segment
from engine.civic_geo.build_way_tags import kazakh_name
from engine.civic_geo.graph import StreetGraph, get_graph, load_raw_graph
from engine.civic_geo.objects import Cells, FeatureSet, get_layers
from engine.civic_geo.targets import TargetError, load_categories, targets

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures"


@pytest.fixture(scope="module")
def tiny():
    return StreetGraph(load_raw_graph(path=FIX / "tiny.graph.json"), json.loads((FIX / "tiny.way_tags.json").read_text("utf-8")))


@pytest.fixture(scope="module")
def tiny_layers(tmp_path_factory):
    out = tmp_path_factory.mktemp("geo")
    result = build_geo_data.build(FIX / "osm-objects" / "raw", walking_raw=None, evidence_type="synthetic")
    build_geo_data.write(result, out, FIX / "osm-objects" / "raw")
    return out, result


# ---------- geo ----------
def test_haversine_one_degree_latitude():
    assert abs(geo.haversine_m([71.43, 51.0], [71.43, 52.0]) - 111195) < 5


def test_project_and_cut_keep_original_vertices():
    line = [[71.43, 51.16], [71.4325, 51.1599], [71.435, 51.16]]
    pr = geo.project_on_polyline([71.4325, 51.1605], line)
    assert pr.index == 0 and 60 < pr.distance_m < 70  # 0.0006° широты ≈ 66.7 м
    total = geo.polyline_length_m(line)
    part = geo.cut_polyline(line, 10, total - 10)
    assert part[1] == line[1], "средняя вершина OSM должна остаться без изменений"
    back = geo.cut_polyline(line, total - 10, 10)
    assert back == list(reversed(part))
    assert abs(geo.polyline_length_m(part) - (total - 20)) < 0.05


def test_point_in_polygon_with_hole_and_distance():
    outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    assert geo.point_in_polygon([2, 2], [outer, hole])
    assert not geo.point_in_polygon([5, 5], [outer, hole])
    assert not geo.point_in_polygon([11, 5], [outer])


def test_simplify_and_max_offset():
    line = [[71.43 + i * 0.0001, 51.16 + (0.0000005 if i % 2 else 0)] for i in range(20)]
    s = geo.simplify(line, 1.0)
    assert s[0] == line[0] and s[-1] == line[-1] and len(s) == 2
    assert geo.max_offset_m(s, [line]) < 0.1
    shifted = [[p[0], p[1] + 0.0001] for p in line]  # ~11 м севернее
    assert 10 < geo.max_offset_m(shifted, [line]) < 12


def test_bbox_center_inside_concave_polygon():
    ring = [[0, 0], [10, 0], [10, 1], [1, 1], [1, 10], [0, 10], [0, 0]]  # буква «Г»
    c = geo.bbox_center(ring)
    assert geo.point_in_ring(c, ring) or c in ring


# ---------- graph ----------
def test_nearest_edge_distance_and_group(tiny):
    d, e, pr = tiny.nearest([71.4312, 51.16], 30)[0]
    assert e.id in ("osm-w900001-0", "osm-w900003-0") and d < 7
    roads = tiny.nearest([71.4312, 51.16], 30, accept=lambda e: e.group == "road")
    assert roads[0][1].id == "osm-w900001-0" and roads[0][0] < 0.5
    assert tiny.by_id["osm-w900001-0"].label_kk() == "Тестілік көшесі"
    assert tiny.nearest([71.50, 51.20], 60) == []


# ---------- segment ----------
def test_segment_on_one_edge(tiny):
    r = segment.street_segment(tiny, [71.4305, 51.16002], [71.4320, 51.15998], groups=("road",))
    assert r["edge_ids"] == ["osm-w900001-0"] and r["same_street"]
    assert abs(r["length_m"] - 105) < 2


def test_segment_follows_one_street_and_bend(tiny):
    a, b = [71.4310, 51.1600], [71.4390, 51.1600]
    r = segment.street_segment(tiny, a, b, groups=("road",))
    assert r["names"] == ["улица Тестовая"] and r["same_street"]
    assert r["edge_ids"][:3] == ["osm-w900001-0", "osm-w900001-1", "osm-w900001-2"]
    coords = r["geometry"]["coordinates"]
    assert [round(71.4300 + 0.0025 * 1.5, 7), round(51.16 - 0.00009, 7)] in coords, "изгиб ребра OSM должен войти в линию"
    refs = [tiny.by_id[e].geometry for e in r["edge_ids"]]
    assert geo.max_offset_m(coords, refs) < 0.05


def test_segment_prefers_named_street_over_parallel_footway(tiny):
    # Тротуар без названия идёт в 6 м параллельно; концы ближе к тротуару, но участок дороги — по улице.
    r = segment.street_segment(tiny, [71.4312, 51.16004], [71.4385, 51.16004], groups=("road",))
    assert all(e.startswith("osm-w900001-") for e in r["edge_ids"])


def test_segment_errors(tiny):
    with pytest.raises(segment.GeoError) as e1:
        segment.street_segment(tiny, [71.4312, 51.17], [71.4385, 51.16])
    assert e1.value.code == "not_on_street"
    with pytest.raises(segment.GeoError) as e2:
        segment.street_segment(tiny, [71.4312, 51.16], [71.43121, 51.16])
    assert e2.value.code == "too_short"


def test_snap_polyline_through_waypoints(tiny):
    r = segment.snap_polyline(tiny, [[71.4310, 51.1601], [71.4350, 51.1590], [71.4350, 51.1615]], groups=("road",))
    assert "улица Тестовая" in r["names"] and "улица Поперечная" in r["names"]


# ---------- data ----------
def test_build_geo_data_from_fixture(tiny_layers):
    out, result = tiny_layers
    counts = result["counts"]
    assert counts["bus_stop"] == 1, "платформа рядом с тем же именем — дубль; ж/д платформа — не остановка"
    assert counts["playground"] == 1 and counts["park"] == 1 and counts["waste"] == 1 and counts["yard"] == 1
    assert result["skipped"]["outside_city"] == 1  # площадка в Алматы
    objects = json.loads((out / "objects.json").read_text("utf-8"))
    park = next(o for o in objects["items"] if o["kind"] == "park")
    assert park["id"] == "osm-relation-4001" and park["name_kk"] == "Тест саябағы" and park["polygon"]
    stop = next(o for o in objects["items"] if o["kind"] == "bus_stop")
    assert stop["name_ru"] == "Тестовая" and stop["name_kk"] == "Тестілік"
    src = json.loads((out / "SOURCE.json").read_text("utf-8"))
    assert src["license"]["id"] == "ODbL-1.0" and src["inputs"][0]["sha256"]


def test_kazakh_name_rules():
    assert kazakh_name({"name": "Қабанбай Батыр даңғылы", "name:ru": "проспект Кабанбай Батыра"}) == "Қабанбай Батыр даңғылы"
    assert kazakh_name({"name": "улица Мира"}) is None
    assert kazakh_name({"name": "Мира", "name:kk": "Бейбітшілік"}) == "Бейбітшілік"


def test_cells_are_stable_and_about_150m():
    c = Cells()
    cid = c.cell_id([71.43, 51.16])
    ring = c.polygon(cid)[0]
    assert geo.point_in_ring([71.43, 51.16], ring)
    assert 145 < geo.haversine_m(ring[0], ring[1]) < 155 and 145 < geo.haversine_m(ring[1], ring[2]) < 155
    assert c.cell_id([71.43, 51.16]) == cid


# ---------- targets ----------
def _layers(path):
    from engine.civic_geo import objects as o
    o.clear_cache()
    return get_layers(path)


def test_targets_by_category(tiny, tiny_layers):
    layers = _layers(tiny_layers[0])
    stop = targets(71.4328, 51.1602, "transport", graph=tiny, layers=layers)["candidates"]
    assert stop[0]["target"]["kind"] == "object" and stop[0]["target"]["label_ru"] == "Остановка «Тестовая»"
    assert stop[0]["target"]["label_kk"] == "«Тестілік» аялдамасы"
    road = targets(71.4312, 51.16001, "roads", graph=tiny, layers=layers)["candidates"]
    assert road[0]["target"] == {"kind": "segment", "id": "osm-w900001-0", "label_ru": "Участок: улица Тестовая",
                                 "label_kk": "Учаске: Тестілік көшесі"}
    assert road[0]["geometry"]["type"] == "LineString" and road[0]["distance_m"] < 1.5  # 0.00001° ≈ 1.1 м
    yard = targets(71.4320, 51.1610, "utilities", graph=tiny, layers=layers)["candidates"]
    assert yard[0]["target"]["kind"] == "area" and yard[0]["target"]["id"] == "yard-3001" and not yard[0]["approximate"]
    play = targets(71.43115, 51.1611, "yards", graph=tiny, layers=layers)["candidates"]
    assert play[0]["target"]["id"] == "osm-way-2001"
    far = targets(71.4600, 51.1900, "other", graph=tiny, layers=layers)["candidates"]
    assert len(far) == 1 and far[0]["approximate"] and far[0]["target"]["id"].startswith("cell-")
    assert far[0]["target"]["label_ru"].startswith("Примерное место")
    for cat in load_categories():
        got = targets(71.4320, 51.1601, cat, graph=tiny, layers=layers)["candidates"]
        assert 1 <= len(got) <= 3
        for c in got:
            assert set(c["target"]) >= {"kind", "id", "label_ru", "label_kk"}
            assert c["target"]["kind"] in ("object", "segment", "area")
    with pytest.raises(TargetError):
        targets(71.43, 51.16, "nope", graph=tiny, layers=layers)


def test_categories_come_from_package_file():
    cats = load_categories()
    assert len(cats) == 12 and cats["roads"]["target_kinds"] == ["segment"]


# ---------- api ----------
def test_api_validation_without_loading_graph():
    assert api.targets_response({"lon": "x", "lat": "51"})[0] == 400
    assert api.targets_response({"lon": "10", "lat": "10", "category": "roads"})[1]["error"]["code"] == "outside_city"
    assert api.targets_response({"lon": ["nan"], "lat": ["51.1"]})[0] == 400
    assert api.segment_response({"from": "71.4", "to": "71.4,51.1"})[1]["error"]["code"] == "bad_point"


# ---------- real graph (OSM Astana) ----------
@pytest.fixture(scope="module")
def real():
    return get_graph()


def test_real_graph_demo_closure_follows_seifullin(real):
    """Было: «перекрытая улица» из 3 точек от руки. Стало: линия по оси улицы Сакена Сейфуллина."""
    hand = [[71.4251, 51.1712], [71.4289, 51.1716], [71.4326, 51.1719]]
    before = geo.max_offset_m(hand, [e.geometry for e in real.edges if e.name == "улица Сакена Сейфуллина"
                                     and e.bbox[0] < 71.434 and e.bbox[2] > 71.424])
    r = segment.snap_polyline(real, hand, groups=("road", "service"))
    assert r["names"] == ["улица Сакена Сейфуллина"] and r["same_street"]
    ok, off, _ = accuracy.check_line_on_edges(real, r["geometry"]["coordinates"], r["edge_ids"])
    assert ok and off < 0.5
    assert before > 5, f"линия от руки должна отклоняться от улицы больше чем на 5 м (было {before:.1f})"


def test_real_targets_latency_under_50ms(real):
    api.warm_up()
    import random
    rnd = random.Random(1)
    cats = list(load_categories())
    worst = 0.0
    for _ in range(300):
        q = {"lon": str(rnd.uniform(71.36, 71.52)), "lat": str(rnd.uniform(51.08, 51.20)), "category": rnd.choice(cats)}
        t = time.perf_counter()
        status, body = api.targets_response(q)
        worst = max(worst, (time.perf_counter() - t) * 1000)
        assert status == 200 and 1 <= len(body["candidates"]) <= 3
    assert worst < 50, f"самый медленный ответ {worst:.1f} мс"


def test_real_accuracy_report_all_pass(real):
    from engine.civic_geo import objects as o
    o.clear_cache()
    r = accuracy.report(real)
    assert r["result"] == "PASS", accuracy.format_report(r)
    assert r["summary"]["line_within_5m_of_street"]["PASS"] >= 2


def test_freehand_line_fails_the_check(real):
    ok, off, detail = accuracy.check_line_on_edges(real, [[71.4251, 51.1712], [71.4326, 51.1719]], [])
    assert not ok and "от руки" in detail
    ok, off, _ = accuracy.check_line_on_edges(real, [[71.4251, 51.1712], [71.4326, 51.1719]],
                                              ["osm-w693873790-4", "osm-w693873790-5"])
    assert not ok and off > 5


# ---------- соседи: одна сетка ячеек с R07, target_geometry ----------
def test_cell_grid_matches_r07_constants():
    """R07 (ui/civic_heat/geo.py): CELL_ORIGIN=(71.0, 50.8), CELL_LAT0=51.15, 111320/110574 м на градус."""
    import math
    import random
    dlon = 150.0 / (111320.0 * math.cos(math.radians(51.15)))
    dlat = 150.0 / 110574.0
    c = Cells()
    rnd = random.Random(7)
    for _ in range(2000):
        p = (rnd.uniform(71.2, 71.8), rnd.uniform(50.9, 51.36))
        assert c.cell_id(p) == f"cell-{math.floor((p[0] - 71.0) / dlon)}-{math.floor((p[1] - 50.8) / dlat)}"
    assert c.polygon("cell-143-245")[0][0] == [71.307178, 51.132357]  # как в fixtures/targets_demo.json R07


def test_target_geometry_for_each_kind():
    from engine.civic_geo import target_geometry
    seg = target_geometry({"kind": "segment", "id": "osm-w693873790-4"})
    assert seg["geometry"]["type"] == "LineString" and seg["label_ru"] == "Участок: улица Сакена Сейфуллина"
    cell = target_geometry({"kind": "area", "id": "cell-143-245"})
    assert cell["approximate"] and cell["geometry"]["type"] == "Polygon"
    assert target_geometry({"kind": "area", "id": "cell-x"}) is None
    assert target_geometry({"kind": "object", "id": "osm-node-0"}) is None
    assert target_geometry({"kind": "segment", "id": "osm-w0-0"}) is None
    assert target_geometry({}) is None


def test_targets_without_category_offer_one_of_each_kind(tiny, tiny_layers):
    layers = _layers(tiny_layers[0])
    got = targets(71.4328, 51.1602, None, graph=tiny, layers=layers)["candidates"]
    kinds = [c["target"]["kind"] for c in got]
    assert len(kinds) == len(set(kinds)) and "object" in kinds and "segment" in kinds


def test_r01_style_functions_raise_status_code_message():
    import engine.civic_geo as g
    with pytest.raises(Exception) as e:
        g.targets(71.43, 51.16, "nope")
    assert (e.value.status, e.value.code) == (400, "unknown_category")
    with pytest.raises(Exception) as e2:
        g.street_snap(71.30, 51.30)
    assert e2.value.status == 400 and e2.value.code == "not_on_street" and "улиц" in e2.value.message
    assert g.segment_between([71.4251, 51.1712], "71.4326,51.1719", "road")["names"] == ["улица Сакена Сейфуллина"]
