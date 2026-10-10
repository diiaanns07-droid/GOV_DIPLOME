"""R06 раунд 14: признак «форма места взята из OSM» (geometry_source) — просьба R12 (INTEGRATION §6)."""

import json
import sqlite3

import pytest

from r06r14_helpers import NURA_POINT, call

LINE = {"type": "LineString", "coordinates": [[71.3695148, 51.1376971], [71.369295, 51.1371074],
                                               [71.3692344, 51.1369249]]}


def test_editor_can_mark_line_as_osm_graph_and_public_sees_it(staff):
    item = staff.create_object(publish=False, geometry=LINE, geometry_source="osm-graph")
    assert item["geometry_source"] == "osm-graph"
    published = staff.v1("POST", f"/staff/objects/{item['id']}/publish",
                         {"expected_revision": item["revision"], "reason": "Публикация"})["body"]["data"]["item"]
    public = call(staff.svc, "GET", f"/objects/{published['id']}", prefix="/api/civic/v1")["body"]["data"]["item"]
    assert public["geometry_source"] == "osm-graph"
    v2 = call(staff.v2, "GET", f"/objects/{published['id']}")["body"]["data"]["item"]
    assert v2["geometry_source"] == "osm-graph"


@pytest.mark.parametrize("geometry,source,field", [
    ({"type": "Point", "coordinates": NURA_POINT}, "osm-graph", "geometry_source"),  # линия графа — только LineString
    (LINE, "osm-area", "geometry_source"),
    (LINE, "drawn-by-hand", "geometry_source"),
])
def test_wrong_source_for_shape_is_422(staff, geometry, source, field):
    from r06r14_helpers import SAMPLE
    body = {**SAMPLE, "geometry": geometry, "geometry_source": source}
    result = staff.v1("POST", "/staff/objects", body)
    assert result["status"] == 422 and field in result["body"]["error"]["fields"]


def test_no_geometry_means_no_source(staff):
    item = staff.create_object(publish=False, geometry=None, geometry_source="manual")
    assert item["geometry"] is None and item["geometry_source"] is None


def test_old_rows_without_key_read_as_null_and_can_be_published(staff, db_path):
    item = staff.create_object(publish=False)
    # Запись «до раунда 14»: в data_json нет ключа geometry_source.
    conn = sqlite3.connect(db_path)
    data = json.loads(conn.execute("SELECT data_json FROM civic_objects WHERE id = ?", (item["id"],)).fetchone()[0])
    data.pop("geometry_source")
    conn.execute("PRAGMA trusted_schema = ON")
    conn.execute("UPDATE civic_objects SET data_json = ? WHERE id = ?", (json.dumps(data, ensure_ascii=False), item["id"]))
    conn.commit()
    conn.close()
    published = staff.v1("POST", f"/staff/objects/{item['id']}/publish",
                         {"expected_revision": item["revision"], "reason": "Публикация"})
    assert published["status"] == 200, published
    assert published["body"]["data"]["item"]["geometry_source"] is None


def test_meta_lists_sources(staff):
    meta = staff.v1("GET", "/staff/meta")["body"]["data"]
    assert meta["enums"]["geometry_source"] == ["osm-graph", "osm-object", "osm-area", "manual", "import"]
