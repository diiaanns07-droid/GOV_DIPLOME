"""R07 · правки по UX_REVIEW R11 (день 3) и запросам соседей (R01, R08, R09, R10, R12) — серверная часть.

Запуск: python -m pytest tests/civic/R07/test_r07_day3.py -q
"""
import gzip
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ui.civic_heat import HeatService, api, demo_seed, engine, geo, osm_objects
from ui.civic_heat.targets import TargetResolver, cell_family, r09_cell_polygon

ROOT = Path(__file__).resolve().parents[3]
TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=TZ)
TARGETS = demo_seed.load_targets()
SEG = next(k for k, v in TARGETS.items() if v["kind"] == "segment" and v["district"] == "nura")
POINT = geo.anchor_of(TARGETS[SEG]["geometry"])


def rec(i, *, age=0.5, metoo=0, metoo_times=None, status="new", text="Яма на дороге", demo=True, target=None,
        point=None, duplicate_of=None, history=None):
    created = NOW - timedelta(days=age)
    r = {"id": f"c-{i}", "created_at": created.isoformat(), "text": text, "lang": "ru", "category": "roads",
         "point": point or POINT, "target": target or {"kind": "segment", "id": SEG}, "district": "nura",
         "status": status, "status_history": history or [{"at": created.isoformat(), "status": "new"}],
         "metoo": metoo, "duplicate_of": duplicate_of, "demo": demo}
    if metoo_times is not None:
        r["metoo_times"] = metoo_times
    return r


def svc(records, **kw):
    return HeatService(source=lambda since: records, resolver=TargetResolver(graph_path=None, use_r12=False),
                       clock=lambda: NOW, **kw)


# ---------- R09: дубли, время «Я тоже» ----------

def test_duplicates_are_not_counted_their_people_are_in_metoo_of_original():
    out = svc([rec(1, metoo=1), rec(2, duplicate_of="c-1")]).heat()
    assert out["items"][0]["count"] == 2 and out["stats"]["duplicates_skipped"] == 1


def test_metoo_ages_by_its_own_time():
    old = (NOW - timedelta(days=28)).isoformat()
    fresh = (NOW - timedelta(hours=1)).isoformat()
    # жалоба 28 дней назад + «Я тоже» час назад: вес ≈ 0.25 + 1, а не 2 × 0.25
    item = svc([rec(1, age=28, metoo=1, metoo_times=[fresh])]).heat(days=30)["items"][0]
    assert item["weight"] == pytest.approx(0.25 + 0.5 ** (1 / 24 / 14), abs=0.01)
    assert item["daily"][-1] == 1                       # «Я тоже» — в сегодняшнем столбике
    # без времени «Я тоже» стареет вместе с жалобой (старые записи)
    assert svc([rec(1, age=28, metoo=1)]).heat(days=30)["items"][0]["weight"] == pytest.approx(0.5, abs=0.01)
    # «Я тоже» до начала периода в счёт периода не идёт
    item7 = svc([rec(1, age=3, metoo=1, metoo_times=[old])]).heat(days=7)["items"][0]
    assert item7["count"] == 1


def test_metoo_times_provider_from_r09_store():
    calls = []

    def times(ids):
        calls.append(ids)
        return {"c-1": [(NOW - timedelta(hours=2)).isoformat()]}
    item = svc([rec(1, age=20, metoo=1)], metoo_times=times).heat(days=30)["items"][0]
    assert calls == [["c-1"]] and item["weight"] > 0.9


# ---------- R01 / R09: одна id ячейки — два места ----------

def _r09_legacy_id(pt):
    """Формула R09 до fa49fc9 (угол 70.9/50.8) — такие id могут лежать в старых записях."""
    dlon = 150 / (111320 * math.cos(math.radians(51.15)))
    return f"cell-{int((pt[0] - 70.9) // dlon)}-{int((pt[1] - 50.8) // (150 / 111320))}"


def _r09_id(pt):
    """id ячейки так, как его ставит R09 сейчас: функция модуля (сборка R01), без модуля — общая сетка geo.py."""
    try:
        from ui.civic_feedback.v2 import record  # type: ignore

        return record.cell_id(pt[0], pt[1])
    except Exception:
        return geo.cell_id_for(pt)


def test_r09_approximate_cell_is_drawn_where_the_resident_tapped():
    pt = [71.4045, 51.1285]                             # Нура
    tid = _r09_id(pt)
    item = svc([rec(1, target={"kind": "area", "id": tid, "approximate": True}, point=pt)]).heat()["items"][0]
    ring = item["geometry"]["coordinates"][0]
    assert geo.point_in_ring(pt, ring) and item["approximate"] is True
    assert geo.haversine_m(item["anchor"], pt) < 200          # раньше было ~7 км восточнее
    # R01 §9: «примерное место» R07 подписывает сам — адаптер R09CellResolver в оболочке не нужен
    assert item["target"]["label_ru"] == "Примерное место" and item["target"]["label_kk"] == "Шамамен көрсетілген орын"
    # та же id без точки и без флага — общая сетка R07/R12 («Квартал»)
    assert cell_family(tid, None, {}) == "r07" and cell_family(tid, None, {"approximate": True}) == "r09"


def test_old_r09_cell_ids_are_still_drawn_where_the_resident_tapped():
    pt = [71.4045, 51.1285]
    tid = _r09_legacy_id(pt)
    item = svc([rec(1, target={"kind": "area", "id": tid, "approximate": True}, point=pt)]).heat()["items"][0]
    assert geo.point_in_ring(pt, item["geometry"]["coordinates"][0]) and item["approximate"] is True
    assert cell_family(tid, pt, {"approximate": True}) in ("r09", "r09-legacy")


def test_shared_r07_r12_cell_grid_still_works():
    pt = [71.40, 51.12]
    cid = geo.cell_id_for(pt)
    item = svc([rec(1, target={"kind": "area", "id": cid}, point=pt)]).heat()["items"][0]
    assert geo.point_in_ring(pt, item["geometry"]["coordinates"][0]) and item["target"]["label_ru"] == "Квартал"


def test_r09_formula_copy_matches_r09_module_when_available():
    try:
        from ui.civic_feedback.v2 import record  # type: ignore
    except Exception:
        pytest.skip("NOT_RUN: модуля R09 v2 нет в этой ветке — сверка формулы в сборке R01")
    tid = record.cell_id(71.4, 51.12)
    assert r09_cell_polygon(tid)["coordinates"][0] == record.cell_polygon(tid)
    # R09 fa49fc9: сетка общая — ячейка R09 совпадает с ячейкой R07/R12 (geo.py) до 1 м
    ours = geo.cell_polygon(tid)["coordinates"][0]
    assert max(geo.haversine_m(a, b) for a, b in zip(ours, record.cell_polygon(tid))) < 1.0


# ---------- R10 B-007: ж/д платформы — не остановки ----------

@pytest.mark.skipif(not osm_objects.available(), reason="NOT_RUN: нет LOCAL-1")
def test_railway_platforms_are_not_bus_stops():
    raw = json.loads(gzip.open(ROOT / "data/civic/astana/osm-objects/raw/platforms.json.gz").read().decode("utf-8"))
    rail = [e for e in raw["elements"] if e.get("tags", {}).get("railway") == "platform" or e.get("tags", {}).get("train") == "yes"]
    objs = osm_objects.load()
    assert rail and not any(f"osm-{e['type']}-{e['id']}" in objs for e in rail)
    assert not osm_objects.is_bus_platform({"public_transport": "platform", "railway": "platform", "train": "yes"})
    assert osm_objects.is_bus_platform({"public_transport": "platform", "bus": "yes"})


# ---------- R12: файлы geo/*.json с полями point / polygon ----------

def test_r12_point_and_polygon_fields(tmp_path):
    from ui.civic_heat.targets import _load_json_targets
    f = tmp_path / "objects.json"
    f.write_text(json.dumps({"items": [
        {"id": "osm-node-1", "point": [71.4, 51.1], "label_ru": "Остановка «А»", "label_kk": "«А» аялдамасы"},
        {"id": "yard-2", "polygon": [[71.4, 51.1], [71.401, 51.1], [71.401, 51.101], [71.4, 51.1]]}]}), "utf-8")
    got = _load_json_targets(f)
    assert got["osm-node-1"]["geometry"] == {"type": "Point", "coordinates": [71.4, 51.1]}
    assert got["yard-2"]["geometry"]["type"] == "Polygon"


# ---------- R15 S11: подпись из записи жалобы не меняет название настоящего места ----------

FAKE = "Любой текст жителя"


@pytest.mark.skipif(not osm_objects.available(), reason="NOT_RUN: нет LOCAL-1")
def test_record_label_cannot_rename_real_object_segment_or_yard():
    r = TargetResolver(graph_path=None, use_r12=False)
    for target in ({"kind": "object", "id": "osm-node-4109037549"}, {"kind": "area", "id": "yard-1148721825"},
                   {"kind": "segment", "id": SEG}):
        clean = r.resolve(dict(target))
        got = TargetResolver(graph_path=None, use_r12=False).resolve(dict(target, label_ru=FAKE, label_kk=FAKE))
        assert (got["label_ru"], got["label_kk"]) == (clean["label_ru"], clean["label_kk"]), target
        assert FAKE not in (got["label_ru"], got["label_kk"])


def test_record_label_reaches_neither_heat_nor_day_summary():
    pt = POINT
    items = svc([rec(1, target={"kind": "segment", "id": SEG, "label_ru": FAKE, "label_kk": FAKE})]).heat()["items"]
    assert FAKE not in json.dumps(items, ensure_ascii=False)
    # ячейка «примерного места» своего названия не имеет — подпись записи допустима, но обрезана
    cell = svc([rec(2, target={"kind": "area", "id": geo.cell_id_for(pt), "approximate": True,
                               "label_ru": "Примерное место у дома 5" + "!" * 200})]).heat()["items"][0]
    assert cell["target"]["label_ru"].startswith("Примерное место у дома 5") and len(cell["target"]["label_ru"]) <= 80
    # казахская подпись R09/R12 «Шамамен орны …» — к слову словаря R11
    r09 = svc([rec(3, target={"kind": "area", "id": geo.cell_id_for(pt), "approximate": True,
                              "label_ru": "Примерное место — ул. Сауран", "label_kk": "Шамамен орны — Сауран көшесі"})]).heat()["items"][0]
    assert r09["target"]["label_kk"] == "Шамамен көрсетілген орын — Сауран көшесі"


# ---------- R01 I-01: файлы R12 (голое имя, name_kk = null) не перебивают подписи слоя OSM ----------

@pytest.mark.skipif(not osm_objects.available(), reason="NOT_RUN: нет LOCAL-1")
def test_r12_registry_does_not_strip_osm_labels(tmp_path, monkeypatch):
    from ui.civic_heat import targets as tg
    geo_dir = tmp_path / "geo"
    geo_dir.mkdir()
    (geo_dir / "objects.json").write_text(json.dumps({"items": [
        {"id": "osm-node-4109037549", "kind": "bus_stop", "name_ru": "Хан Шатыр", "name_kk": None, "point": [71.4036, 51.1326]},
        {"id": "osm-node-1", "kind": "bus_stop", "name_ru": "Тестовая", "name_kk": None, "point": [71.41, 51.12]},
        {"id": "osm-node-2", "kind": "playground", "name_ru": None, "name_kk": None, "point": [71.41, 51.12]}]}), "utf-8")
    (geo_dir / "yards.json").write_text(json.dumps({"items": [
        {"id": "yard-1148721825", "kind": "yard", "name_ru": "Двор или квартал", "name_kk": None,
         "polygon": [[[71.4, 51.1], [71.401, 51.1], [71.401, 51.101], [71.4, 51.1]]]}]}), "utf-8")
    monkeypatch.setattr(tg, "R12_GEO_DIR", geo_dir)
    r = tg.TargetResolver(graph_path=None, use_r12=False)
    stop = r.resolve({"kind": "object", "id": "osm-node-4109037549"})
    assert (stop["label_ru"], stop["label_kk"]) == ("Остановка «Хан Шатыр»", "«Хан Шатыр» аялдамасы")
    yard = r.resolve({"kind": "area", "id": "yard-1148721825"})
    assert yard["label_ru"] == "Двор ЖК «Evolution»" and yard["geometry"]["type"] == "Polygon"
    # объекта нет в слое OSM R07 — берётся R12, но подпись по типу и на двух языках, а не «Нысан»
    only_r12 = r.resolve({"kind": "object", "id": "osm-node-1"})
    assert (only_r12["label_ru"], only_r12["label_kk"]) == ("Остановка «Тестовая»", "«Тестовая» аялдамасы")
    unnamed = r.resolve({"kind": "object", "id": "osm-node-2"})
    assert unnamed["label_kk"] != "Нысан" and unnamed["label_ru"] != "Объект"


# ---------- ночь, ревью кода: кэш целей и заглушки имён R12 ----------

def test_record_label_of_one_complaint_does_not_stick_to_the_cell_cache():
    r = TargetResolver(graph_path=None, use_r12=False)
    cid = geo.cell_id_for(POINT)
    first = r.resolve({"kind": "area", "id": cid, "approximate": True, "label_ru": "Примерное место у дома 5"})
    assert first["label_ru"] == "Примерное место у дома 5" and first["approximate"] is True
    plain = r.resolve({"kind": "area", "id": cid})
    assert plain["label_ru"] == "Квартал" and plain["approximate"] is False
    again = r.resolve({"kind": "area", "id": cid, "approximate": True})
    assert again["label_ru"] == "Примерное место"          # без подписи записи — своя, а не чужая


def test_point_fallback_is_not_cached_by_id():
    r = TargetResolver(graph_path=None, use_r12=False, use_osm_objects=False)
    a = r.resolve({"kind": "object", "id": "osm-node-1"}, point=[71.40, 51.12])
    b = r.resolve({"kind": "object", "id": "osm-node-1"}, point=[71.45, 51.15])
    assert geo.point_in_ring([71.45, 51.15], b["geometry"]["coordinates"][0]) and a["geometry"] != b["geometry"]


def test_r12_placeholder_names_are_not_wrapped_as_real_names(tmp_path, monkeypatch):
    from ui.civic_heat import targets as tg
    geo_dir = tmp_path / "geo"
    geo_dir.mkdir()
    (geo_dir / "yards.json").write_text(json.dumps({"items": [
        {"id": "yard-1", "kind": "yard", "name_ru": "Двор или квартал", "name_kk": None,
         "polygon": [[[71.4, 51.1], [71.401, 51.1], [71.401, 51.101], [71.4, 51.1]]]}]}), "utf-8")
    (geo_dir / "objects.json").write_text(json.dumps({"items": [
        {"id": "osm-node-2", "kind": "bus_stop", "name_ru": "Остановка", "name_kk": None, "point": [71.41, 51.12]}]}), "utf-8")
    monkeypatch.setattr(tg, "R12_GEO_DIR", geo_dir)
    r = tg.TargetResolver(graph_path=None, use_r12=False, use_osm_objects=False)
    yard = r.resolve({"kind": "area", "id": "yard-1"})
    stop = r.resolve({"kind": "object", "id": "osm-node-2"})
    assert "«" not in yard["label_ru"] and "«" not in yard["label_kk"], yard
    assert (stop["label_ru"], stop["label_kk"]) == ("Остановка", "Аялдама")


# ---------- R10 B-037: в общей сборке у примеров R07 нет кнопок (их нет в хранилище R09) ----------

def test_r07_examples_are_not_actionable_with_a_live_source_but_are_on_the_demo_stand():
    example = dict(rec(1), id="c-demo-0001", demo=True)
    r09_demo = dict(rec(2), id="c-5a1b2c3d4e5f6a7b", demo=True)      # демо-жалоба самого R09 — настоящая запись
    item = svc([example, r09_demo]).heat()["items"][0]
    assert item["open_ids"] == ["c-5a1b2c3d4e5f6a7b"] and item["examples_open"] == 1
    only_examples = svc([example]).heat()["items"][0]
    assert only_examples["open_ids"] == [] and only_examples["examples_open"] == 1
    # свой стенд (source=None, чистое демо): примеры — сами жалобы, действия с ними работают
    stand = HeatService(resolver=TargetResolver(graph_path=None, use_r12=False), clock=lambda: demo_seed.ANCHOR)
    hot = next(i for i in stand.heat()["items"] if i["state"] == "active")
    assert hot["open_ids"] and all(x.startswith("c-demo-") for x in hot["open_ids"]) and hot["examples_open"] == 0


# ---------- R07 №4: «Что пишут жители» — тексты только примеров или сотруднику ----------

def test_text_groups_show_demo_texts_and_hide_real_ones_from_public():
    recs = [rec(1, metoo=2, text="Павильон сломан, нет крыши"), rec(2, text="павильон сломан нет крыши!"),
            rec(3, text="Нет расписания"), rec(4, text="Мой телефон 8 701 …", demo=False)]
    s = svc(recs)
    pub = s.target("segment", SEG)["texts"]
    first = pub["groups"][0]
    # две формулировки одной жалобы — одна группа: 1 + 2 «Я тоже» + 1 = 4 человека, показан самый свежий вариант
    assert first["people"] == 4 and first["demo"] is True and first["text"].lower().startswith("павильон сломан")
    assert len(pub["groups"]) == 2 and pub["hidden_people"] == 1
    assert "телефон" not in json.dumps(pub, ensure_ascii=False)
    staff = s.target("segment", SEG, include_real_texts=True)["texts"]
    assert any("телефон" in g["text"] for g in staff["groups"])


def test_api_passes_staff_flag_only_from_gateway():
    s = svc([rec(1, text="Реальный текст жителя", demo=False)])
    st, body = api.handle_get("/api/civic/v2/heat/target", {"kind": ["segment"], "id": [SEG]}, service=s)
    assert st == 200 and body["item"]["texts"]["groups"] == [] and body["item"]["texts"]["hidden_people"] == 1
    st, body = api.handle_get("/api/civic/v2/heat/target", {"kind": ["segment"], "id": [SEG], "staff": ["1"]}, service=s)
    assert body["item"]["texts"]["groups"] == []          # параметр в адресе НЕ даёт доступа
    st, body = api.handle_get("/api/civic/v2/heat/target", {"kind": ["segment"], "id": [SEG]}, service=s, staff=True)
    assert body["item"]["texts"]["groups"][0]["text"] == "Реальный текст жителя"
    st, body = api.handle_get("/api/civic/v2/heat", {}, service=s, staff=True)
    assert "Реальный текст" not in json.dumps(body, ensure_ascii=False)   # в /heat текстов нет никогда


# ---------- R08: публичные records() и generation ----------

def test_records_and_generation_for_day_summary():
    recs = [rec(1)]
    s = svc(recs)
    assert s.records() == recs
    g = s.generation
    s.invalidate()
    assert s.generation == g + 1


# ---------- R11 №9: демо-числа правдоподобны ----------

def _weekly(records, now):
    ages = [(now - engine.parse_time(r["created_at"])).total_seconds() / 86400 for r in records]
    return sum(1 for a in ages if a < 7), sum(1 for a in ages if 7 <= a < 14)


def test_demo_numbers_are_plausible():
    recs = demo_seed.demo_records(now=demo_seed.ANCHOR)
    now = demo_seed.ANCHOR
    last, prev = _weekly(recs, now)
    assert 0.85 <= last / prev <= 1.4, (last, prev)            # неделя к неделе, а не «в 6,9 раза»
    items = HeatService(source=lambda s: recs, clock=lambda: now).heat(days=30)["items"]
    active = [i for i in items if i["state"] == "active"]
    levels = [i["level"] for i in active]
    assert levels.count(4) >= 2 and levels.count(3) + levels.count(4) >= 5      # карта не пустая
    assert active[0]["district"] == "nura"                                       # демо показывает Нуру
    assert 3 <= sum(1 for i in items if i["state"] == "fixed") <= 10            # «исправлено» есть, но не всё зелёное
    by_d = engine.districts_summary(HeatService(source=lambda s: recs, clock=lambda: now).heat(days=7)["items"],
                                    HeatService().config)
    counts = sorted(d["count"] for d in by_d if d["district"] != "nura")
    nura = next(d["count"] for d in by_d if d["district"] == "nura")
    assert nura <= 5 * counts[len(counts) // 2], (nura, counts)                 # не «Нура 149 · Есиль 1»
    assert all(r["demo"] is True for r in recs)


def test_demo_numbers_with_r08_day_summary_if_available():
    try:
        from ui.civic_akim.summary import AkimService  # type: ignore
    except Exception:
        pytest.skip("NOT_RUN: модуля R08 нет в ветке R07 — проверено сборкой R01 и tune_demo_seed.py")
    sys.path.append(str(Path(__file__).parent))
    import tune_demo_seed
    k, d, items = tune_demo_seed.measure(demo_seed.DEFAULT_SEED)
    assert tune_demo_seed.problems(k, d, items) == []
