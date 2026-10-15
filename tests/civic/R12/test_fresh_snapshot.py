"""R12 · R10 B-103: светофоры и переходы — из свежего снимка OSM (raw/, LOCAL-10), без дублей и без потерянных ссылок.

    python3 -m pytest -q tests/civic/R12/test_fresh_snapshot.py

Узел из обоих снимков стоит по свежему; узел только из старого снимка пешеходной сети — «выбывший»: не в поиске рядом
и не цель новой жалобы, но его id находится (на него ссылаются демо-мир R02 и пример QR). Первые тесты — на маленькой
СИНТЕТИКЕ (точки в Астане, id выдуманы), остальные — на настоящих данных geo/objects.json (только чтение).
"""
import gzip
import json
from pathlib import Path

import pytest

from engine.civic_geo import build_geo_data, geo, target_geometry, target_info
from engine.civic_geo.objects import FeatureSet, get_layers
from engine.civic_geo.targets import targets

FRESH_FILES = {"traffic_signals.json.gz", "crossings.json.gz"}
QR_EXAMPLE = "osm-node-10185771782"     # пример QR (web/civic/qr/print.js, словари R11): светофор Богенбай Батыра / Щорса
QR_EXAMPLE_FRESH = "osm-node-14140558124"  # тот же светофор в свежем снимке 12.10.2026 (0 м)


def _node(nid, lon, lat, **tags):
    return {"type": "node", "id": nid, "lon": lon, "lat": lat, "tags": tags}


@pytest.fixture()
def synthetic(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    # Свежий снимок: светофор 1 сдвинут на ~20 м к востоку, светофор 3 — новый узел в 9 м от старого 2.
    fresh = {"elements": [_node(1, 71.43029, 51.16, highway="traffic_signals"),
                          _node(3, 71.43213, 51.16, highway="traffic_signals")]}
    (raw / "traffic_signals.json").write_text(json.dumps(fresh), "utf-8")
    walking = tmp_path / "overpass.json.gz"
    old = {"elements": [_node(1, 71.43, 51.16, highway="traffic_signals"),
                        _node(2, 71.432, 51.16, highway="traffic_signals"),       # удалён, рядом свежий 3
                        _node(4, 71.45, 51.17, highway="traffic_signals"),        # удалён, рядом ничего
                        _node(5, 71.44, 51.165, highway="bus_stop", name="Пример")]}  # остановки — как раньше
    walking.write_bytes(gzip.compress(json.dumps(old).encode("utf-8")))
    return build_geo_data.build(raw, walking_raw=walking, evidence_type="synthetic", street_points=False)


def test_fresh_snapshot_wins_and_old_only_nodes_retire(synthetic):
    items = {o["id"]: o for o in synthetic["objects"]}
    retired = {o["id"]: o for o in synthetic["retired"]}
    assert items["osm-node-1"]["point"] == [71.43029, 51.16] and items["osm-node-1"]["src"] == "traffic_signals.json"
    assert set(retired) == {"osm-node-2", "osm-node-4"} and not set(retired) & set(items)
    assert retired["osm-node-2"]["replaced_by"] == "osm-node-3" and retired["osm-node-2"]["replaced_m"] < 15
    assert "replaced_by" not in retired["osm-node-4"], "дальше 30 м — замены нет"
    assert all(o["retired"] is True and o["src"] == "overpass.json.gz" for o in retired.values())
    assert items["osm-node-5"]["kind"] == "bus_stop", "остановки из снимка пешеходной сети не трогаем"
    assert synthetic["counts"]["traffic_signal"] == 2 and synthetic["retired_counts"] == {"traffic_signal": 2}


def test_retired_nodes_resolve_by_id_but_never_show_up_near(synthetic, tmp_path):
    out = tmp_path / "geo"
    build_geo_data.write(synthetic, out, tmp_path / "raw")
    data = json.loads((out / "objects.json").read_text("utf-8"))
    assert data["retired_count"] == 2 and "B-103" in data["retired_note"]
    assert [o["id"] for o in data["items"]].count("osm-node-2") == 0
    fs = FeatureSet(data["items"], data, data["retired"])
    assert fs.find("osm-node-2").raw["replaced_by"] == "osm-node-3"
    assert fs.by_id.get("osm-node-2") is None, "перечисления by_id — только действующие объекты"
    near = [f.id for _, f in fs.near([71.432, 51.16], 60.0)]
    assert "osm-node-3" in near and "osm-node-2" not in near
    src = json.loads((out / "SOURCE.json").read_text("utf-8"))
    assert src["retired"]["counts"] == {"traffic_signal": 2} and src["retired"]["replaced"] == 1


def test_without_fresh_files_old_snapshot_stays_active(tmp_path):
    (tmp_path / "raw").mkdir()
    walking = tmp_path / "overpass.json.gz"
    walking.write_bytes(gzip.compress(json.dumps({"elements": [_node(2, 71.432, 51.16, highway="traffic_signals")]}).encode()))
    r = build_geo_data.build(tmp_path / "raw", walking_raw=walking, evidence_type="synthetic", street_points=False)
    assert [o["id"] for o in r["objects"]] == ["osm-node-2"] and r["retired"] == []


# ---------- настоящие данные: data/civic/astana/geo/objects.json ----------
@pytest.fixture(scope="module")
def real_objects():
    data = json.loads((build_geo_data.GEO_DIR / "objects.json").read_text("utf-8"))
    raw_dir = build_geo_data.OSM_OBJECTS_DIR / "raw"
    if not all((raw_dir / f).is_file() for f in FRESH_FILES):
        pytest.skip("нет свежего снимка LOCAL-10 (raw/traffic_signals, raw/crossings)")
    return data


def test_real_signals_and_crossings_come_from_the_fresh_snapshot(real_objects):
    street = [o for o in real_objects["items"] if o["kind"] in ("traffic_signal", "crossing")]
    assert street and all(o["src"] in FRESH_FILES for o in street)
    fresh = {}
    for f in FRESH_FILES:
        for el in json.loads(gzip.decompress((build_geo_data.OSM_OBJECTS_DIR / "raw" / f).read_bytes()))["elements"]:
            if el.get("type") == "node":
                fresh[f"osm-node-{el['id']}"] = [el["lon"], el["lat"]]
    # Самый большой сдвиг между снимками (R10: 28,8 м) — объект стоит по свежему.
    o = next(x for x in street if x["id"] == "osm-node-13411167450")
    assert geo.haversine_m(o["point"], fresh[o["id"]]) < 0.5
    assert all(geo.haversine_m(x["point"], fresh[x["id"]]) < 0.5 for x in street)


def test_real_retired_list_is_consistent(real_objects):
    items = {o["id"]: o for o in real_objects["items"]}
    retired = real_objects.get("retired") or []
    assert retired and not {o["id"] for o in retired} & set(items)
    for o in retired:
        assert o["kind"] in ("traffic_signal", "crossing") and o["src"] == "overpass.json.gz"
        if o.get("replaced_by"):
            new = items[o["replaced_by"]]
            assert new["kind"] == o["kind"] and geo.haversine_m(new["point"], o["point"]) <= build_geo_data.REPLACED_M + 0.5


def test_qr_example_still_resolves_and_new_complaints_get_the_fresh_signal():
    info = target_info(QR_EXAMPLE)
    assert info["target"]["object_kind"] == "traffic_signal" and info.get("retired") is True
    assert info["replaced_by"] == QR_EXAMPLE_FRESH
    assert target_geometry({"kind": "object", "id": QR_EXAMPLE_FRESH})["label_ru"] == info["target"]["label_ru"]
    p = info["point"]
    got = targets(p[0], p[1], "roads", subtopic="traffic_light_broken")["candidates"]
    ids = [c["target"]["id"] for c in got]
    assert ids[0] == QR_EXAMPLE_FRESH and QR_EXAMPLE not in ids
    objects, _, _ = get_layers()
    assert QR_EXAMPLE not in [f.id for _, f in objects.near(p, 60.0)]
