"""Topology/access checks on adversarial tiny OSM fixtures + real extract provenance."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from engine.civic_scenarios import compare, ScenarioError
from engine.civic_scenarios.adapters.osm_city import build_graph, distance, foot_access, GRAPH_ID
from engine.civic_scenarios.registry import load_graph, load_graph_dict, manifest

ROOT = Path(__file__).resolve().parents[2]


def node(i, x, y, **tags):
    return dict(type="node", id=i, lon=x, lat=y, tags=tags)


def way(i, ids, **tags):
    return dict(type="way", id=i, nodes=ids, tags={"highway": "footway", **tags})


def build(elements, box=(-1, -1, 1, 1)):
    return build_graph({"elements": elements, "osm3s": {"timestamp_osm_base": "2026-05-06T00:00:00Z"}}, {}, list(box))


def test_crossing_lines_do_not_create_bridge_connection():
    g = build([node(1, -.01, 0), node(2, .01, 0), node(3, 0, -.01), node(4, 0, .01), way(1, [1, 2]), way(2, [3, 4])])
    assert len(g["nodes"]) == 4
    assert {(e["from"], e["to"]) for e in g["edges"]} == {("osm-n1", "osm-n2"), ("osm-n3", "osm-n4")}


def test_shared_id_is_retained_and_curved_length_preserved():
    points = [node(1, 0, 0), node(2, .0001, .0001), node(3, .0002, 0), node(4, .0003, 0), node(5, .0002, .0001)]
    g = build(points + [way(1, [1, 2, 3, 4]), way(2, [3, 5])])
    edge = next(e for e in g["edges"] if e["from"] == "osm-n1")
    assert edge["to"] == "osm-n3" and len(edge["geometry"]) == 3
    expected = distance([0, 0], [.0001, .0001]) + distance([.0001, .0001], [.0002, 0])
    assert edge["length_m"] == pytest.approx(expected, abs=.001)


@pytest.mark.parametrize("tags,expected", [
    ({"highway": "residential"}, "unknown"),
    ({"highway": "footway"}, "allowed"),
    ({"highway": "footway", "access": "private"}, "denied"),
    ({"highway": "footway", "foot": "yes", "access": "private"}, "allowed"),
    ({"highway": "footway", "foot:conditional": "no @ (Mo-Fr)"}, "unknown"),
    ({"highway": "footway", "access": "destination"}, "denied"),
])
def test_access_does_not_invent_permission(tags, expected):
    assert foot_access(tags) == expected


def test_barrier_splits_and_blocks_incident_segments():
    g = build([node(1, 0, 0), node(2, .0001, 0, barrier="gate"), node(3, .0002, 0), way(1, [1, 2, 3])])
    assert len(g["edges"]) == 2
    assert {e["access"] for e in g["edges"]} == {"unknown"}


def test_foot_direction_overrides_car_oneway():
    nodes = [node(1, 0, 0), node(2, .001, 0)]
    a = build(nodes + [way(1, [1, 2], oneway="yes")])["edges"][0]
    b = build(nodes + [way(1, [1, 2], **{"oneway:foot": "-1"})])["edges"][0]
    assert a["oneway"] is False
    assert b["oneway"] is True and b["from"] == "osm-n2" and b["geometry"][0] == [.001, 0]


def test_crop_marks_boundary_and_never_connects_across_outside_gap():
    g = build([node(1, 0, 0), node(2, .1, 0), node(3, 2, 0), node(4, .2, 0), node(5, .3, 0), way(1, [1, 2, 3, 4, 5])])
    assert len(g["edges"]) == 2
    assert {n["id"] for n in g["nodes"] if n["boundary"]} == {"osm-n2", "osm-n4"}


def test_missing_node_rejects_incomplete_extract():
    with pytest.raises(ValueError, match="missing node"):
        build([node(1, 0, 0), way(1, [1, 2])])


def test_snapshot_is_reproducible_and_citywide():
    folder = ROOT / "data/civic/astana/osm-walking"
    raw = gzip.decompress((folder / "overpass.json.gz").read_bytes())
    source = json.loads((folder / "SOURCE.json").read_text("utf-8"))
    assert hashlib.sha256(raw).hexdigest() == source["raw_sha256"]
    rebuilt = build_graph(json.loads(raw), source)
    graph = load_graph_dict(GRAPH_ID)
    assert rebuilt["digest"] == graph["digest"]
    assert len(graph["edges"]) > 90_000 and len(graph["nodes"]) > 60_000
    assert graph["bbox"][2] - graph["bbox"][0] > .5
    assert graph["bbox"][3] - graph["bbox"][1] > .4
    assert source["snapshot_at"].startswith("2026-05-06")
    assert graph["mode"] == "walking" and graph["evidence_type"] == "derived"
    assert sum(e["access"] == "unknown" for e in graph["edges"]) > 60_000


def test_long_route_and_both_closures_are_computed():
    case = json.loads((ROOT / "engine/civic_scenarios/cases/astana-citywide-v1.case.json").read_text("utf-8"))
    graph = load_graph(GRAPH_ID)
    result = compare(case["payload"], graph)
    base = result["baseline"]["routes"][0]
    assert base["status"] == "ok" and base["length_m"] > 18_000
    for plan in result["plans"]:
        route = plan["routes"][0]
        assert route["status"] == "ok" and route["length_m"] > base["length_m"]
        assert not set(plan["active_closed_edge_ids"]) & set(route["edge_ids"])
        assert all(graph.edges[e][3] == "allowed" for e in route["edge_ids"])
    assert len(graph._adj_cache) <= 2


def test_bad_graph_id_is_validation_error():
    with pytest.raises(ScenarioError):
        load_graph([])
