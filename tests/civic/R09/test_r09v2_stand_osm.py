"""R09: реальные объекты OSM (LOCAL-1) на стенде — id и подписи по CONTRACT §4, корректная геометрия."""

import sys
from pathlib import Path

import pytest

from ui.civic_feedback.v2 import record as rec

STAND = Path(__file__).resolve().parent / "stand"
DATA = Path(__file__).resolve().parents[3] / "data" / "civic" / "astana" / "osm-objects" / "raw"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="нет data/civic/astana/osm-objects (LOCAL-1)")


@pytest.fixture(scope="module")
def objects():
    sys.path.insert(0, str(STAND))
    from osm_objects import OsmObjects
    return OsmObjects()


def test_targets_follow_contract(objects):
    assert len(objects.items) > 3000
    ids = set()
    for item in objects.items:
        target = rec.parse_target(item["target"])     # строгая проверка формата id (без legacy)
        assert target["id"] not in ids
        ids.add(target["id"])
        assert item["target"]["label_ru"] and item["target"]["label_kk"]


def test_geometry_is_closed_and_in_astana(objects):
    for item in objects.items:
        g = item["geometry"]
        if g["type"] == "Point":
            assert rec.in_astana(*g["coordinates"])
            continue
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            ring = poly[0]
            assert ring[0] == ring[-1] and len(ring) >= 4


def test_named_stop_labels_ru_kk(objects):
    stop = next(i for i in objects.items if i["kind"] == "stop" and "«" in i["target"]["label_ru"])
    assert stop["target"]["label_ru"].startswith("Остановка «")
    assert stop["target"]["label_kk"].endswith("» аялдамасы")


def test_nearby_prefers_tapped_stop_over_surrounding_yard(objects):
    stop = next(i for i in objects.items if i["kind"] == "stop")
    found = objects.nearby(*stop["geometry"]["coordinates"])
    assert found[0][2] is stop and found[0][1] == 0


def test_relation_stitching():
    sys.path.insert(0, str(STAND))
    from osm_objects import _stitch
    a, b, c = [0, 0], [1, 0], [1, 1]
    assert _stitch([[a, b], [c, b], [c, a]]) == [[a, b, c, a]]
    assert _stitch([[a, b], [b, c]]) is None   # не замыкается — объект пропускается
