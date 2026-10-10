"""R07 раунд 14: тепловая карта объектов — вес, уровни, «исправлено», районы, API, точность, скорость.

Запуск: python -m pytest tests/civic/R07/test_r07_heat.py -q
"""
import gzip
import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ui.civic_heat import HeatService, load_config
from ui.civic_heat import api, demo_seed, engine, geo, osm_objects
from ui.civic_heat.service import HeatError
from ui.civic_heat.targets import TargetResolver, kk_street_from_ru, segment_labels

ROOT = Path(__file__).resolve().parents[3]
TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
CATS = json.loads((ROOT / "research/round-14/categories_v2.json").read_text("utf-8"))
TARGETS = demo_seed.load_targets()
SEG_ID = next(k for k, v in TARGETS.items() if v["kind"] == "segment" and v["district"] == "nura")
STOP_ID = next(k for k, v in TARGETS.items() if v["kind"] == "object")


def rec(i, *, age_days=0.0, target=None, metoo=0, status="new", category="roads", history=None, district="nura", point=None):
    created = NOW - timedelta(days=age_days)
    t = target if target is not None else {"kind": "segment", "id": SEG_ID}
    return {
        "id": f"c-t-{i}", "created_at": created.isoformat(), "text": "текст", "lang": "ru", "category": category,
        "category_source": "resident", "model": None,
        "point": point or geo.anchor_of(TARGETS[SEG_ID]["geometry"]), "target": t, "district": district,
        "status": status, "status_history": history or [{"at": created.isoformat(), "status": "new"}],
        "metoo": metoo, "duplicate_of": None, "demo": True,
    }


def svc_for(records):
    return HeatService(source=lambda since: records, resolver=TargetResolver(graph_path=None, use_r12=False), clock=lambda: NOW)


# ---------- настройки из categories_v2.json ----------

def test_levels_and_colors_come_from_categories_json():
    cfg = load_config()
    assert cfg.half_life_days == CATS["weight_half_life_days"]
    assert [lv.color for lv in cfg.levels] == [x["color"] for x in CATS["heat_levels"]]
    assert cfg.fixed_color == CATS["fixed_state"]["color"] and cfg.fixed_days == CATS["fixed_state"]["days_visible"]
    assert len(cfg.categories) == 12 and cfg.category_ids == {c["id"] for c in CATS["categories"]}


@pytest.mark.parametrize("weight,level", [(0, 0), (0.05, 1), (0.99, 1), (2.49, 1), (2.5, 2), (5.49, 2), (5.5, 3), (9.49, 3), (9.95, 4), (250, 4)])
def test_level_thresholds_with_floor_for_live_complaint(weight, level):
    assert load_config().level_for(weight) == level


# ---------- вес ----------

def test_weight_halves_every_14_days_and_metoo_counts_people():
    out = svc_for([rec(1, age_days=14, metoo=2)]).heat(days=30)
    item = out["items"][0]
    assert item["count"] == 3                      # жалоба + 2 «Я тоже»
    assert item["weight"] == pytest.approx(1.5, abs=1e-3)
    assert item["level"] == 1 and item["color"] == CATS["heat_levels"][1]["color"]


def test_period_filter_and_rejected_are_excluded():
    rs = [rec(1, age_days=2), rec(2, age_days=40), rec(3, age_days=1, status="rejected")]
    item = svc_for(rs).heat(days=30)["items"][0]
    assert item["count"] == 1
    assert svc_for(rs).heat(days=90)["items"][0]["count"] == 2


def test_cooling_lowers_level_but_keeps_people_count():
    fresh = svc_for([rec(i, age_days=0.1) for i in range(10)]).heat(days=90)["items"][0]
    old = svc_for([rec(i, age_days=40) for i in range(10)]).heat(days=90)["items"][0]
    assert fresh["level"] == 4 and old["level"] < fresh["level"]
    assert fresh["count"] == old["count"] == 10


# ---------- «исправлено» ----------

def fixed_history(created_age, fixed_age):
    c = NOW - timedelta(days=created_age)
    f = NOW - timedelta(days=fixed_age)
    return [{"at": c.isoformat(), "status": "new"}, {"at": f.isoformat(), "status": "fixed"}]


def test_fixed_target_is_green_for_7_days_with_zero_weight():
    rs = [rec(i, age_days=5, status="fixed", history=fixed_history(5, 2)) for i in range(4)]
    item = svc_for(rs).heat(days=30)["items"][0]
    assert item["state"] == "fixed" and item["level"] == "fixed" and item["weight"] == 0
    assert item["color"] == CATS["fixed_state"]["color"] and item["count"] == 4
    assert engine.parse_time(item["fixed_until"]) == NOW - timedelta(days=2) + timedelta(days=7)


def test_fixed_disappears_after_7_days():
    rs = [rec(1, age_days=12, status="fixed", history=fixed_history(12, 8))]
    assert svc_for(rs).heat(days=30)["items"] == []


def test_new_complaint_after_fix_makes_target_red_again_counting_only_new():
    old_open = rec(1, age_days=6)                                # не закрыта, но пришла ДО ремонта
    fixed = rec(2, age_days=6, status="fixed", history=fixed_history(6, 3))
    fresh = rec(3, age_days=0.5)
    item = svc_for([old_open, fixed, fresh]).heat(days=30)["items"][0]
    assert item["state"] == "active" and item["count"] == 1 and item["open_ids"] == ["c-t-3"]


# ---------- фильтры, районы, приблизительные цели ----------

def test_category_district_and_bbox_filters():
    stop_t = {"kind": "object", "id": STOP_ID}
    rs = [rec(1, category="roads"), rec(2, category="transport", target=stop_t, district="almaty")]
    s = svc_for(rs)
    assert [i["target"]["id"] for i in s.heat(category="transport")["items"]] == [STOP_ID]
    assert [i["target"]["id"] for i in s.heat(district="nura")["items"]] == [SEG_ID]
    far = (10.0, 10.0, 10.1, 10.1)
    assert s.heat(bbox=",".join(map(str, far)))["items"] == []


def test_districts_mode_sums_match_targets():
    rs = demo_seed.demo_records(now=NOW)
    s = HeatService(source=lambda since: rs, clock=lambda: NOW)
    targets = s.heat(days=30)["items"]
    districts = s.heat(days=30, zoom=10)
    assert districts["mode"] == "districts"
    for d in districts["items"]:
        assert d["target"]["kind"] == "district" and d["geometry"]["type"] == "MultiPolygon"
        same = [t for t in targets if t["district"] == d["district"] and t["state"] == "active"]
        assert d["count"] == sum(t["count"] for t in same)
        assert d["weight"] == pytest.approx(sum(t["weight"] for t in same), abs=0.01)


def test_complaint_without_target_becomes_approximate_place():
    r = rec(1, target={}, point=[71.40, 51.12])
    r["target"] = None
    item = svc_for([r]).heat()["items"][0]
    assert item["approximate"] is True and item["target"]["label_ru"] == "Примерное место"
    assert item["target"]["id"].startswith("cell-")


def test_invalid_records_are_skipped_not_crashing():
    bad = [None, {"id": "x"}, rec(1) | {"created_at": "не дата"}, rec(2) | {"target": None, "point": None}]
    out = svc_for(bad + [rec(3)]).heat()
    assert out["stats"]["skipped_invalid"] == 4 and len(out["items"]) == 1


# ---------- API ----------

@pytest.mark.parametrize("query,field", [({"days": "0"}, "days"), ({"days": "abc"}, "days"), ({"category": "snow"}, "category"),
                                         ({"bbox": "1,2,3"}, "bbox"), ({"bbox": "5,5,1,1"}, "bbox"), ({"zoom": "x"}, "zoom"),
                                         ({"district": "moscow"}, "district")])
def test_api_rejects_bad_params_with_400(query, field):
    status, body = api.handle_get("/api/civic/v2/heat", {k: [v] for k, v in query.items()}, service=svc_for([rec(1)]))
    assert status == 400 and body["field"] == field


def test_api_routes():
    s = svc_for([rec(1)])
    st, body = api.handle_get("/api/civic/v2/heat", {"days": ["7"]}, service=s)
    assert st == 200 and set(body) >= {"generated_at", "items"}
    assert set(body["items"][0]) >= {"target", "geometry", "weight", "level", "count", "fixed_until"}
    st, meta = api.handle_get("/api/civic/v2/heat/meta", {}, service=s)
    assert st == 200 and [c["id"] for c in meta["categories"]] == [c["id"] for c in CATS["categories"]]
    st, one = api.handle_get("/api/civic/v2/heat/target", {"kind": "segment", "id": SEG_ID}, service=s)
    assert st == 200 and one["item"]["target"]["id"] == SEG_ID
    assert api.handle_get("/api/civic/v2/heat/target", {"kind": "segment", "id": "nope"}, service=s)[0] == 404
    assert api.handle_get("/api/civic/v2/nope", {}, service=s)[0] == 404


def test_api_never_returns_resident_text_or_point():
    st, body = api.handle_get("/api/civic/v2/heat", {}, service=svc_for([rec(1)]))
    dump = json.dumps(body, ensure_ascii=False)
    assert "текст" not in dump and '"point"' not in dump and '"text"' not in dump


def test_api_survives_broken_source():
    def boom(since):
        raise RuntimeError("база недоступна")
    st, body = api.handle_get("/api/civic/v2/heat", {}, service=HeatService(source=boom, clock=lambda: NOW))
    assert st == 500 and body["error"] == "heat_failed"


# ---------- кэш и скорость ----------

def test_cache_and_invalidation():
    rs = [rec(1)]
    s = svc_for(rs)
    a = s.heat()
    assert s.heat() is a                           # из кэша
    rs.append(rec(2))
    s.invalidate()
    b = s.heat()
    assert b is not a and b["items"][0]["count"] == 2


def test_citywide_under_300ms_with_5000_complaints():
    rnd = random.Random(7)
    ids = sorted(TARGETS)
    rs = []
    for i in range(5000):
        tid = ids[rnd.randrange(len(ids))]
        t = TARGETS[tid]
        rs.append(rec(i, age_days=rnd.uniform(0, 89), target={"kind": t["kind"], "id": tid}, metoo=rnd.randrange(3),
                      district=t["district"], category=rnd.choice([c["id"] for c in CATS["categories"]])))
    for i in range(1500):  # жалобы без цели → ячейки по всему городу
        rs.append(rec(10000 + i, target=None, point=[rnd.uniform(71.3, 71.6), rnd.uniform(51.05, 51.25)], district=None))
        rs[-1]["target"] = None
    s = HeatService(source=lambda since: rs, clock=lambda: NOW)
    s.heat(days=7)                                  # прогрев: границы районов и фикстуры
    started = time.perf_counter()
    out = s.heat(days=90)
    took = (time.perf_counter() - started) * 1000
    assert out["stats"]["complaints"] == 6500 and took < 300, f"{took:.0f} мс"


# ---------- демо-набор ----------

def test_demo_seed_is_deterministic_synthetic_and_v2():
    a = demo_seed.demo_records(now=NOW)
    b = demo_seed.demo_records(now=NOW)
    assert a == b and len(a) > 80
    required = {"id", "created_at", "text", "lang", "category", "category_source", "model", "point", "target",
                "district", "status", "status_history", "metoo", "duplicate_of", "demo"}
    for r in a:
        assert required <= set(r) and r["demo"] is True and r["category"] in {c["id"] for c in CATS["categories"]}
        assert r["target"]["id"] in TARGETS and engine.parse_time(r["created_at"]) <= NOW


def test_demo_map_shows_every_level_and_a_fixed_target():
    out = HeatService(source=lambda since: demo_seed.demo_records(now=NOW), clock=lambda: NOW).heat(days=30)
    levels = {i["level"] for i in out["items"]}
    assert {1, 2, 3, 4, "fixed"} <= levels
    assert out["stats"]["unresolved_targets"] == 0


# ---------- точность (CONTRACT §8) ----------

def test_segment_targets_are_exact_osm_edges_and_inside_astana():
    graph = json.loads((ROOT / "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json").read_text("utf-8"))
    edges = {e["id"]: e["geometry"] for e in graph["edges"]}
    outer = json.loads((ROOT / "data/civic/astana/geofence.json").read_text("utf-8"))["outer_bbox"]
    for tid, t in TARGETS.items():
        bb = geo.bbox_of(t["geometry"])
        assert outer[0] <= bb[0] and bb[2] <= outer[2] and outer[1] <= bb[1] and bb[3] <= outer[3], tid
        if t["kind"] == "segment":
            src = edges[tid]
            got = t["geometry"]["coordinates"]
            assert len(src) == len(got)
            # Форма = форма ребра OSM; расхождение только от округления до 6 знаков (< 0.2 м), норма ≤ 5 м.
            assert max(geo.haversine_m(p, q) for p, q in zip(src, got)) < 0.2, tid


def _raw_osm_index():
    out = {}
    for f in sorted((ROOT / "data/civic/astana/osm-objects/raw").glob("*.json.gz")):
        for el in json.loads(gzip.open(f).read().decode("utf-8"))["elements"]:
            out.setdefault((el["type"], el["id"]), (f.name, el))
    return out


@pytest.mark.skipif(not osm_objects.available(), reason="NOT_RUN: нет data/civic/astana/osm-objects (LOCAL-1)")
def test_object_and_yard_targets_are_real_osm_elements():
    raw = _raw_osm_index()
    seen = {"bus_stop": 0, "yard": 0, "playground": 0, "waste_disposal": 0}
    for tid, t in TARGETS.items():
        if t["kind"] == "segment" or tid.startswith("cell-"):
            continue
        osm = t["osm"]
        fname, el = raw[(osm["type"], osm["id"])]
        assert t["district"] == "nura", tid
        tags = el.get("tags", {})
        if t["subtype"] == "bus_stop":
            assert tags.get("highway") == "bus_stop" and tags.get("name"), tid   # только остановки с названием
        if t["subtype"] == "yard":
            assert tags.get("landuse") == "residential" and tid == f"yard-{el['id']}"
        if t["subtype"] == "playground":
            assert tags.get("leisure") == "playground"
        if t["subtype"] == "waste_disposal":
            assert tags.get("amenity") == "waste_disposal"
        # Форма — из OSM как есть (точка или контур), расхождение только от округления
        if el["type"] == "node":
            assert geo.haversine_m([el["lon"], el["lat"]], t["geometry"]["coordinates"]) < 0.2
        else:
            ring = t["geometry"]["coordinates"][0]
            src = [[p["lon"], p["lat"]] for p in el["geometry"]]
            assert len(ring) == len(src) and max(geo.haversine_m(a, b) for a, b in zip(src, ring)) < 0.2, tid
        seen[t["subtype"]] += 1
    assert seen["bus_stop"] >= 4 and seen["yard"] >= 5 and seen["playground"] >= 1 and seen["waste_disposal"] >= 1


@pytest.mark.skipif(not osm_objects.available(), reason="NOT_RUN: нет data/civic/astana/osm-objects (LOCAL-1)")
def test_resolver_finds_any_real_osm_object_by_contract_id():
    r = TargetResolver(graph_path=None, use_r12=False)
    stop = r.resolve({"kind": "object", "id": "osm-node-4109037549"})
    assert stop["label_ru"] == "Остановка «Хан Шатыр»" and stop["label_kk"] == "«Хан Шатыр» аялдамасы"
    assert stop["subtype"] == "bus_stop" and stop["geometry"]["type"] == "Point" and stop["approximate"] is False
    yard = r.resolve({"kind": "area", "id": "yard-1148721825"})
    assert yard["geometry"]["type"] == "Polygon" and yard["label_ru"] == "Двор ЖК «Evolution»"
    # Безымянный объект: подпись по ближайшей улице посчитана заранее — граф улиц не грузится (graph_path=None)
    labels = json.loads((ROOT / "ui/civic_heat/fixtures/osm_street_labels.json").read_text("utf-8"))["labels"]
    some = sorted(k for k in labels if k.startswith("osm-node-"))[0]
    got = r.resolve({"kind": "object", "id": some})
    assert [got["label_ru"], got["label_kk"]] == labels[some]
    assert r.resolve({"kind": "object", "id": "osm-node-1"}, point=[71.4, 51.12])["approximate"] is True


def test_complex_names_and_kazakh_stop_names():
    assert osm_objects.clean_complex_name('ЖК "Семейный"') == "Семейный"
    assert osm_objects.clean_complex_name("Жилой комплекс Зелёный Квартал") == "Зелёный Квартал"
    ru, kk = osm_objects.labels("bus_stops", {"name": "Ұлттық кардиохирургиялық орталық", "name:ru": "Национальный кардиологический центр"})
    assert ru == "Остановка «Национальный кардиологический центр»" and kk == "«Ұлттық кардиохирургиялық орталық» аялдамасы"


def test_anchor_lies_inside_target():
    # Значок с числом должен стоять НА объекте: точка — сама точка, многоугольник — внутри контура, линия — на линии.
    for tid, t in TARGETS.items():
        g = t["geometry"]
        a = geo.anchor_of(g)
        if g["type"] == "Polygon":
            assert geo.point_in_polygon(a, g["coordinates"]), tid
        elif g["type"] == "LineString":
            assert min(geo.haversine_m(a, p) for p in g["coordinates"]) <= geo.line_length_m(g["coordinates"]) / 2 + 0.5, tid
        else:
            assert a == g["coordinates"], tid
    # Маленький квадрат 15×15 м далеко от нуля координат — классический случай потери точности
    sq = [[71.4, 51.13], [71.40021, 51.13], [71.40021, 51.13014], [71.4, 51.13014], [71.4, 51.13]]
    c = geo.ring_centroid(sq)
    assert abs(c[0] - 71.400105) < 1e-7 and abs(c[1] - 51.13007) < 1e-7
    # Контур буквой «П»: центр тяжести снаружи, значок всё равно встаёт внутрь
    u = [[71.4 + x * 0.0002, 51.13 + y * 0.0002] for x, y in [(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3), (0, 0)]]
    assert not geo.point_in_polygon(geo.ring_centroid(u), [u])
    assert geo.point_in_polygon(geo.anchor_of({"type": "Polygon", "coordinates": [u]}), [u])


def test_cell_grid_is_about_150m_and_roundtrips():
    cid = geo.cell_id_for([71.405, 51.128])
    ring = geo.cell_polygon(cid)["coordinates"][0]
    assert 140 < geo.haversine_m(ring[0], ring[1]) < 160 and 140 < geo.haversine_m(ring[1], ring[2]) < 160
    assert geo.cell_id_for(geo.anchor_of(geo.cell_polygon(cid))) == cid


def test_daily_series_uses_astana_days():
    # 23:30 по Астане вчера → вчерашний столбик, хотя по UTC это ещё «позавчера».
    late = datetime(2026, 10, 10, 23, 30, tzinfo=TZ)
    r = rec(1)
    r["created_at"] = late.isoformat()
    item = svc_for([r]).heat()["items"][0]
    assert item["daily"][-1] == 0 and item["daily"][-2] == 1


def test_kazakh_labels_do_not_inflect_variable_names():
    ru, kk = segment_labels("улица Сыганак", "Сығанақ көшесі", "проспект Туран", "улица Достык", "Тұран даңғылы", None)
    assert ru == "Участок ул. Сыганак от пр. Туран до ул. Достык"
    assert kk == "Сығанақ көшесінің Тұран даңғылы – Достык көшесі аралығы"
    assert segment_labels("улица Е-308", "Е-308 көшесі")[1] == "Е-308 көшесінің бөлігі"
    assert segment_labels("E-900", None)[1] == "E-900: көше бөлігі"
    assert kk_street_from_ru("Центральная улица") == "Центральная көшесі"
    assert segment_labels("Объездная Астаны", None)[0] == "Участок: Объездная Астаны"


def test_bad_period_raises_typed_error():
    with pytest.raises(HeatError):
        svc_for([]).heat(days=400)
