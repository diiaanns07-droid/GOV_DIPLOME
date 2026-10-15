"""R06 раунд 15, задача 2: работа v2 (CONTRACT §5.6) — служба, вид, участки улиц, даты; миграция 10; чтение для R12/R16.

Все записи — синтетические. Граф улиц R12 подменяется там, где проверяется логика R06 (быстро и без файла графа);
настоящий граф OSM — в test_real_r12_street_section (пропуск, если граф в сборке не загружается).
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from r06r14_helpers import PASSWORD, Staff, call, context, make_service
from ui.civic_store import db as civic_db
from ui.civic_store import v2 as v2mod
from ui.civic_store import works_v2
from ui.civic_store.db import Database, MIGRATIONS

WHY = {"problem": "Течь под дорогой", "reason": "Сначала сети, потом асфальт", "result": "Ровная дорога",
       "inconvenience": "Одна полоса закрыта"}
# Участок улицы Ильяса Омарова (Нура) — рёбра графа OSM R12 (как у демо-проекта освещения R06 раунда 14).
OMAROVA_A, OMAROVA_B = [71.3695148, 51.1376971], [71.3682669, 51.1342208]
OMAROVA_EDGES = [f"osm-w1482578141-{n}" for n in range(9)]
OMAROVA_LINE = {"type": "LineString", "coordinates": [OMAROVA_A, [71.369041, 51.1364283], OMAROVA_B]}


def work(**over):
    body = {"type": "work", "status": "planned", "district": "nura", "lang": "ru", "title": "Замена водопровода",
            "service": "water", "kind": "dig", "starts_on": "2026-11-01", "ends_on": "2026-11-20", "why": dict(WHY)}
    body.update(over)
    return body


@pytest.fixture
def fake_r12(monkeypatch):
    """R12 строит участок по двум точкам; рёбра — из «графа» с тремя рёбрами цепочкой."""
    calls = []

    def segment_between(a, b):
        calls.append((a, b))
        return {"geometry": OMAROVA_LINE, "edge_ids": OMAROVA_EDGES[:3], "street_ru": "улица Ильяса Омарова",
                "street_kk": "Ілияс Омаров көшесі", "length_m": 396.3}

    graph = {
        "osm-w1482578141-0": ([(71.3695148, 51.1376971), (71.369295, 51.1371074)], "улица Ильяса Омарова",
                              "Ілияс Омаров көшесі", "n1", "n2"),
        "osm-w1482578141-1": ([(71.369295, 51.1371074), (71.3692344, 51.1369249)], "улица Ильяса Омарова",
                              "Ілияс Омаров көшесі", "n2", "n3"),
        "osm-w1482578141-2": ([(71.369154, 51.1367237), (71.3692344, 51.1369249)], "улица Ильяса Омарова",
                              "Ілияс Омаров көшесі", "n4", "n3"),   # ребро «задом наперёд» — цепочка всё равно одна
    }
    monkeypatch.setattr(works_v2, "segment_between", segment_between)
    monkeypatch.setattr(works_v2, "edges_lookup", lambda ids: {i: graph[i] for i in ids if i in graph})
    return calls


def create(staff, body, status=201):
    result = staff.call("POST", "/works", body)
    assert result["status"] == status, result
    return result["body"]["data"]["item"] if status == 201 else result["body"]["error"]


# --- миграция 10 на базе, как у FINAL-4 ------------------------------------------------------------------------

FINAL4_ROWS = [
    # id, type, status, work_kind, utility, district, source, ожидаемые service и kind v2
    ("w-old-water", "outage", None, None, "water", "nura", "water", "water", None),
    ("w-old-close", "outage", None, None, "road_closure", "esil", "road", "road", "closure"),
    ("w-old-road", "work", "in_progress", "roadworks", None, "nura", None, "road", "surface"),
    ("w-old-yard", "work", "done", "landscaping", None, "nura", None, "landscaping", "landscape"),
    ("w-old-light", "work", "planned", "lighting", None, "nura", "lighting", "lighting", "lighting"),
    ("w-old-build", "work", "planned", "construction", None, "almaty", None, None, "other"),
    ("w-old-heat-src", "work", "in_progress", "other", None, "esil", "heating", "heating", "other"),
]


def final4_database(path):
    """База кода FINAL-4: миграции 1–9 (они неизменны — проверяет checksum) и записи «Рядом» в столбцах FINAL-4."""
    database = Database(path)
    original = list(civic_db.MIGRATIONS)
    try:
        civic_db.MIGRATIONS[:] = original[:9]
        assert database.migrate() == list(range(1, 10))
    finally:
        civic_db.MIGRATIONS[:] = original
    with sqlite3.connect(path) as conn:
        for rid, rtype, status, work_kind, utility, district, source, _s, _k in FINAL4_ROWS:
            texts = {"title_ru": "Запись FINAL-4 " + rid, "lang": "ru", "why_problem_ru": "п", "why_reason_ru": "п",
                     "why_result_ru": "р", "why_inconvenience_ru": "н"}
            if rtype == "outage":
                texts["zone_ru"] = "ул. Сыганак, 10"
            conn.execute(
                """INSERT INTO civic_nearby_items(id, type, status, work_kind, utility, district, texts_json, start_at,
                       end_at, planned_end, forecast_end, source, geometry_json, demo, revision, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, '2026-10-01T10:00:00+00:00',
                           '2026-10-02T10:00:00+00:00')""",
                (rid, rtype, status, work_kind, utility, district, json.dumps(texts, ensure_ascii=False),
                 "2026-10-12T10:00:00+05:00" if rtype == "outage" else "2026-10-01",
                 "2026-10-12T16:00:00+05:00" if rtype == "outage" else None,
                 None if rtype == "outage" else "2026-10-30", None if rtype == "outage" else "2026-11-05", source,
                 json.dumps({"type": "Point", "coordinates": [71.36, 51.13]}) if rid == "w-old-road" else None))
            conn.execute("""INSERT INTO civic_nearby_history(item_id, revision, at, action, snapshot_json, actor_user_id,
                                actor_label) VALUES (?, 1, '2026-10-01T10:00:00+00:00', 'create', '{}', NULL, 'final4')""",
                         (rid,))
        conn.execute("""INSERT INTO civic_ideas(id, lang, texts_json, geometry_json, district, status, demo, created_at,
                            updated_at) VALUES ('i-old', 'ru', '{"title_ru": "Скамейки"}',
                            '{"type": "Point", "coordinates": [71.36, 51.13]}', 'nura', 'voting', 0,
                            '2026-10-01T10:00:00+00:00', '2026-10-01T10:00:00+00:00')""")
    return path


OLD_COLUMNS = ("id, type, status, work_kind, utility, district, texts_json, start_at, end_at, planned_end, forecast_end, "
               "source, geometry_json, removed, demo, demo_rel_json, revision, created_at, updated_at")


def test_migration_10_keeps_final4_data_and_fills_v2_columns(tmp_path, clock):
    path = final4_database(tmp_path / "final4.sqlite3")
    with sqlite3.connect(path) as conn:
        before = conn.execute(f"SELECT {OLD_COLUMNS} FROM civic_nearby_items ORDER BY id").fetchall()
        history = conn.execute("SELECT * FROM civic_nearby_history ORDER BY id").fetchall()
        ideas = conn.execute("SELECT * FROM civic_ideas").fetchall()
    svc, v2 = make_service(path, clock)  # открытие новым кодом = миграция 10
    with sqlite3.connect(path) as conn:
        assert conn.execute(f"SELECT {OLD_COLUMNS} FROM civic_nearby_items ORDER BY id").fetchall() == before
        assert conn.execute("SELECT * FROM civic_nearby_history ORDER BY id").fetchall() == history
        # прежние колонки идей — байт в байт; новые (initiative_*, world_key) пустые
        cols = [r[1] for r in conn.execute("PRAGMA table_info(civic_ideas)")]
        after_ideas = conn.execute("SELECT * FROM civic_ideas").fetchall()
        assert [row[:len(ideas[0])] for row in after_ideas] == ideas
        assert {c for c in cols} >= {"initiative_id", "initiative_at", "world_key"}
        got = {row[0]: (row[1], row[2]) for row in conn.execute("SELECT id, service, kind FROM civic_nearby_items")}
        assert conn.execute("SELECT version FROM civic_schema_migrations ORDER BY version DESC").fetchone()[0] == 10
    assert got == {rid: (service, kind) for rid, *_rest, service, kind in FINAL4_ROWS}
    # API для R08 («Рядом») — прежние поля те же; новые поля добавлены
    items = {i["id"]: i for i in v2.nearby.items(None)}
    road = items["w-old-road"]
    assert road["source"] is None and road["work_kind"] == "roadworks" and road["planned_end"] == "2026-10-30"
    assert road["service"] == "road" and road["kind"] == "surface" and road["segments"] == []
    assert items["w-old-water"]["source"] == "water" and items["w-old-water"]["kind"] is None
    # повторный запуск — ничего не меняется
    assert Database(path).migrate() == []


def test_migration_10_on_empty_database_and_demo_seed(stack):
    from ui.civic_store.demo_r14 import seed_r14_demo
    svc, v2 = stack
    seed_r14_demo(svc)
    items = {i["id"]: i for i in v2.nearby.items(None)}
    assert items["nb-demo-water-nura"]["service"] == "water" and items["nb-demo-water-nura"]["kind"] is None
    assert items["nb-demo-close-esil"]["kind"] == "closure" and items["nb-demo-close-esil"]["service"] == "road"
    assert items["nb-demo-road-nura"]["service"] == "road" and items["nb-demo-road-nura"]["kind"] == "surface"
    assert items["nb-demo-light-nura"]["kind"] == "lighting"


# --- форма «Работы и отключения» v2 ------------------------------------------------------------------------------

def test_work_v2_with_street_section_built_by_r12(staff, fake_r12):
    made = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}))
    assert fake_r12 == [(OMAROVA_A, OMAROVA_B)]           # участок строит сервер, а не браузер
    assert made["service"] == "water" and made["kind"] == "dig"
    assert made["segments"] == OMAROVA_EDGES[:3]
    assert made["geometry"] == OMAROVA_LINE                 # форма линии — из графа OSM R12
    assert made["street_ru"] == "улица Ильяса Омарова" and made["street_kk"] == "Ілияс Омаров көшесі"
    assert made["place"]["by"] == "street" and made["place"]["from"] == OMAROVA_A
    assert made["start"] == "2026-11-01" and made["planned_end"] == "2026-11-20"
    assert made["work_kind"] == "roadworks"                 # вид раунда 14 для R08 — из вида v2


def test_work_v2_with_segments_from_editor(staff, fake_r12):
    made = create(staff, work(segments=["osm-w1482578141-0", "osm-w1482578141-2", "osm-w1482578141-1"]))
    assert made["segments"] == ["osm-w1482578141-0", "osm-w1482578141-2", "osm-w1482578141-1"]
    line = made["geometry"]
    assert line["type"] == "LineString"                     # три ребра сложились в одну линию по узлам графа
    assert line["coordinates"][0] == [71.3695148, 51.1376971] and line["coordinates"][-1] == [71.369154, 51.1367237]
    assert len(line["coordinates"]) == 4
    assert made["place"]["by"] == "editor" and made["place"]["street_ru"] == "улица Ильяса Омарова"


@pytest.mark.parametrize("over, field", [
    ({"service": "Водоканал АО"}, "service"),               # реальные названия не придумываем — id службы
    ({"kind": "asphalt"}, "kind"),
    ({"segments": ["way/123"]}, "segments"),
    ({"segments": ["osm-w1-0"] * 201}, "segments"),
    ({"segments": ["osm-w999-0"]}, "segments"),             # нет на карте улиц
    ({"segment": {"from": [71.36, 51.13]}}, "segment"),
    ({"segment": {"from": [10, 10], "to": [11, 11]}}, "segment"),
    ({"segment": {"from": OMAROVA_A, "to": OMAROVA_B}, "segments": OMAROVA_EDGES[:1]}, "segments"),
    ({"start": "2026-11-02"}, "starts_on"),                 # start и starts_on различаются
    ({"ends_on": "2026-10-20"}, "planned_end"),             # окончание раньше начала
    ({"geometry": OMAROVA_LINE}, "geometry"),               # линию «от руки» не принимаем
])
def test_bad_work_v2_is_refused(staff, fake_r12, over, field):
    error = create(staff, work(**over), status=422)
    assert any(name == field or name.startswith(field + ".") for name in error["fields"]), error


def test_outage_v2_service_is_source_and_kind_only_for_closure(staff, fake_r12):
    body = {"type": "outage", "utility": "road_closure", "district": "nura", "lang": "ru", "title": "Перекрытие",
            "zone": "ул. Омарова", "service": "road", "kind": "closure", "start": "2026-10-12T22:00",
            "end": "2026-10-13T06:00", "why": dict(WHY), "segment": {"from": OMAROVA_A, "to": OMAROVA_B}}
    made = create(staff, body)
    assert made["source"] == "road" and made["service"] == "road" and made["kind"] == "closure"
    assert made["segments"] == OMAROVA_EDGES[:3]
    water = dict(body, utility="water", kind="closure", segment=None)
    water.pop("segment")
    assert "kind" in create(staff, water, status=422)["fields"]
    clash = dict(body, source="water")
    assert "service" in create(staff, clash, status=422)["fields"]


def test_r12_unavailable_gives_clear_form_error(staff, monkeypatch):
    def unavailable(a, b):
        raise works_v2.SegmentsUnavailable("no engine.civic_geo")
    monkeypatch.setattr(works_v2, "segment_between", unavailable)
    error = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}), status=422)
    assert "Сохраните точку" in error["fields"]["segment"]


def test_old_form_update_keeps_v2_fields(staff, fake_r12):
    made = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}, service="utilities"))
    # Форма FINAL-4: шлёт все свои поля, но не знает service/kind/segments/starts_on и линий.
    old_form = {"type": "work", "status": "in_progress", "work_kind": "roadworks", "district": "nura", "lang": "ru",
                "title": "Замена водопровода", "start": "2026-11-01", "planned_end": "2026-11-25",
                "why": dict(WHY), "geometry": None, "expected_revision": made["revision"]}
    result = staff.call("POST", f"/works/{made['id']}", old_form)
    assert result["status"] == 200, result
    item = result["body"]["data"]["item"]
    assert item["service"] == "utilities" and item["kind"] == "dig"       # выбор сотрудника сохранён
    assert item["segments"] == OMAROVA_EDGES[:3] and item["geometry"] == OMAROVA_LINE
    assert item["planned_end"] == "2026-11-25" and item["status"] == "in_progress"


def test_auto_service_follows_work_kind_on_old_form(staff):
    old_form = {"type": "work", "status": "planned", "work_kind": "roadworks", "district": "nura", "lang": "ru",
                "title": "Ремонт", "planned_end": "2026-11-25", "why": dict(WHY)}
    made = create(staff, old_form)
    assert made["service"] == "road" and made["kind"] == "surface"         # выведены по виду раунда 14
    result = staff.call("POST", f"/works/{made['id']}", dict(old_form, work_kind="lighting",
                                                              expected_revision=made["revision"]))
    item = result["body"]["data"]["item"]
    assert item["service"] == "lighting" and item["kind"] == "lighting"    # выведенное — следует за видом


def test_segments_can_be_removed(staff, fake_r12):
    made = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}))
    body = work(segments=[], geometry={"type": "Point", "coordinates": [71.3690, 51.1360]},
                expected_revision=made["revision"])
    item = staff.call("POST", f"/works/{made['id']}", body)["body"]["data"]["item"]
    assert item["segments"] == [] and item["geometry"]["type"] == "Point" and item["street_ru"] is None


def test_staff_options_list_services_and_kinds(staff):
    options = staff.call("GET", "/works")["body"]["data"]["options"]
    assert options["kinds"] == ["dig", "surface", "closure", "landscape", "lighting", "other"]
    assert "water" in options["services"] and "akimat" in options["services"] and len(options["services"]) == 20


# --- чтение для R12 и R16 ----------------------------------------------------------------------------------------

def test_works_v2_reader_for_r12(stack, staff, fake_r12):
    svc, v2 = stack
    pipes = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}, starts_on="2026-07-01",
                               ends_on="2026-07-20", status="planned"))
    asphalt = create(staff, work(title="Новый асфальт", service="road", kind="surface", starts_on="2026-05-01",
                                 ends_on="2026-05-20", segments=OMAROVA_EDGES[:2]))
    water_off = create(staff, {"type": "outage", "utility": "water", "district": "nura", "lang": "ru",
                               "title": "Не будет воды", "zone": "ул. Омарова, 5", "source": "water",
                               "start": "2026-10-12T10:00", "end": "2026-10-12T16:00", "why": dict(WHY)})
    esil = create(staff, work(district="esil", title="Сквер", service="landscaping", kind="landscape",
                              starts_on="2026-06-01", ends_on="2026-06-30"))
    data = v2.nearby.works_v2()
    ids = [r["id"] for r in data["items"]]
    assert water_off["id"] not in ids                        # отключение воды — не работа на улице
    assert ids == [asphalt["id"], esil["id"], pipes["id"]]   # по дате начала
    record = data["items"][0]
    assert set(record) >= {"id", "service", "kind", "segments", "starts_on", "ends_on", "source"}
    assert record["source"] == "real" and record["starts_on"] == "2026-05-01" and record["ends_on"] == "2026-05-20"
    assert record["segments"] == OMAROVA_EDGES[:2] and record["link"] == "#works/" + asphalt["id"]
    assert "texts" not in record and "revision" not in record and "created_by" not in record
    may = v2.nearby.works_v2(date_from="2026-05-10", date_to="2026-05-31")
    assert [r["id"] for r in may["items"]] == [asphalt["id"]]
    assert [r["id"] for r in v2.nearby.works_v2(district="esil")["items"]] == [esil["id"]]
    assert [r["id"] for r in v2.nearby.works_v2(service="water")["items"]] == [pipes["id"]]
    assert {r["id"] for r in v2.nearby.works_v2(street="омаров")["items"]} == {pipes["id"], asphalt["id"]}
    with_outages = v2.nearby.works_v2(include_outages=True)
    assert water_off["id"] in [r["id"] for r in with_outages["items"]]
    out = [r for r in with_outages["items"] if r["id"] == water_off["id"]][0]
    assert out["starts_on"] == "2026-10-12" and out["ends_on"] == "2026-10-12" and out["kind"] is None


def test_works_v2_module_function_and_errors(stack, staff, fake_r12):
    svc, v2 = stack
    v2mod.bind(svc)
    create(staff, work(segments=OMAROVA_EDGES[:1]))
    data = v2mod.works_v2(date_from="2026-11-01")
    assert data["count"] == 1 and data["module"] == "R06"
    for kwargs in ({"district": "mars"}, {"date_from": "01.11.2026"}, {"service": "Водоканал"}):
        with pytest.raises(v2mod.V2Error) as exc:
            v2mod.works_v2(**kwargs)
        assert exc.value.status == 400


def test_works_near_for_r16_yard(stack, staff, fake_r12):
    svc, v2 = stack
    v2mod.bind(svc)
    line = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}))
    point = create(staff, work(title="Скамейки", service="landscaping", kind="landscape", status="in_progress",
                               geometry={"type": "Point", "coordinates": [71.3750, 51.1360]}))
    create(staff, work(title="Без места"))                  # без места — в «рядом» не попадает
    done = create(staff, work(title="Готово", status="done", geometry={"type": "Point", "coordinates": [71.3691, 51.1366]}))
    yard = [71.3700, 51.1365]                                # ~60 м от линии участка, ~350 м от скамеек
    near = v2mod.works_near(yard)
    assert [r["id"] for r in near["items"]] == [line["id"], point["id"]]
    assert near["items"][0]["distance_m"] < 100 and 250 < near["items"][1]["distance_m"] < 450
    assert [r["id"] for r in v2mod.works_near(yard, radius_m=150)["items"]] == [line["id"]]
    assert done["id"] in [r["id"] for r in v2mod.works_near(yard, include_done=True)["items"]]
    assert v2mod.works_near(lon=yard[0], lat=yard[1])["count"] == 2
    for bad in ({"point": [10, 10]}, {"point": "71,51"}, {"point": yard, "radius_m": 5}):
        with pytest.raises(v2mod.V2Error):
            v2mod.works_near(**bad)


def test_chain_geometry_falls_back_to_multiline():
    edges = [([(0.0, 0.0), (1.0, 0.0)], None, None, "a", "b"), ([(5.0, 5.0), (6.0, 5.0)], None, None, "c", "d")]
    assert works_v2.chain_geometry(edges)["type"] == "MultiLineString"
    loop = [([(0.0, 0.0), (1.0, 0.0)], None, None, "a", "b"), ([(1.0, 0.0), (1.0, 1.0)], None, None, "b", "c")]
    assert works_v2.chain_geometry(loop) == {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]}


def test_distance_to_line_is_metric():
    line = {"type": "LineString", "coordinates": [[71.40, 51.10], [71.41, 51.10]]}
    d = works_v2.distance_to_geometry_m([71.405, 51.101], line)   # 0.001° широты ≈ 111 м
    assert 105 < d < 117
    assert works_v2.distance_to_geometry_m([71.40, 51.10], None) is None


# --- настоящий граф OSM R12 --------------------------------------------------------------------------------------

def test_real_r12_street_section(staff):
    try:
        from engine.civic_geo.graph import get_graph
        get_graph()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"граф улиц R12 не загружается в этой сборке: {exc}")
    made = create(staff, work(segment={"from": OMAROVA_A, "to": OMAROVA_B}))
    assert made["segments"] == OMAROVA_EDGES
    assert made["street_ru"] == "улица Ильяса Омарова" and made["street_kk"] == "Ілияс Омаров көшесі"
    assert made["geometry"]["type"] == "LineString" and len(made["geometry"]["coordinates"]) >= 10
    assert 380 <= made["place"]["length_m"] <= 410
    # список рёбер из редактора — форма из того же графа, вершины OSM без изменений
    again = create(staff, work(segments=OMAROVA_EDGES))
    graph = get_graph()
    first = graph.by_id[OMAROVA_EDGES[0]].geometry[0]
    coords = again["geometry"]["coordinates"]
    assert again["geometry"]["type"] == "LineString" and list(first) in (coords[0], coords[-1])
    with pytest.raises(AssertionError):
        create(staff, work(segment={"from": [71.36, 51.30], "to": [71.37, 51.30]}))  # далеко от улиц — 422
