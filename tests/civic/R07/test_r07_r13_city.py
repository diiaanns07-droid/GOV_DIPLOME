"""R07 round 13 на городском снимке OSM (osm-astana-walking-20260506): пример RUN, независимая
перекрёстная проверка длин, фрагмент сети и отсутствие пути.

Ожидания примера получены движком — поэтому длины дополнительно пересчитываются отдельной простой
Дейкстрой по JSON графа (float, без engine.routing и без миллиметровых округлений).
"""
import heapq
import json
from pathlib import Path

import pytest

from engine.civic_scenarios import compare
from engine.civic_scenarios.example import CASE, run
from engine.civic_scenarios.registry import load_graph, load_graph_dict
from engine.civic_scenarios.snap import snap_point

GRAPH_ID = "osm-astana-walking-20260506"
STATION = (71.5330, 51.1105)      # у вокзала Нурлы Жол — в снимке это изолированный фрагмент пешей сети


@pytest.fixture(scope="module")
def city():
    return load_graph(GRAPH_ID), load_graph_dict(GRAPH_ID), json.loads(CASE.read_text("utf-8"))


def independent_length(graph, source, target, closed=()):
    adj = {}
    for e in graph["edges"]:
        if e["access"] != "allowed" or e["id"] in closed:
            continue
        adj.setdefault(e["from"], []).append((e["to"], e["length_m"]))
        if not e["oneway"]:
            adj.setdefault(e["to"], []).append((e["from"], e["length_m"]))
    best, heap = {source: 0.0}, [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == target:
            return d
        if d > best[u]:
            continue
        for v, w in adj.get(u, ()):
            if d + w < best.get(v, float("inf")):
                best[v] = d + w
                heapq.heappush(heap, (d + w, v))
    return None


def test_run_example_matches_expected(city):
    _, _, case = city
    got = run(case)
    assert {k: got[k] for k in case["expected"]} == case["expected"]


def test_example_lengths_match_independent_dijkstra(city):
    _, graph, case = city
    p = case["payload"]
    o, d = p["origin_node_ids"][0], p["destination_node_ids"][0]
    want = case["expected"]
    assert independent_length(graph, o, d) == pytest.approx(want["baseline_length_m"], abs=0.05)
    for plan in p["plans"]:
        closed = {e for c in plan["closures"] for e in c["edge_ids"]}
        assert independent_length(graph, o, d, closed) == pytest.approx(want["plan_length_m"][plan["id"]], abs=0.05)


def test_places_snap_with_shown_distance(city):
    pg, _, case = city
    for key, place in case["places"].items():
        s = snap_point(pg, *place["input"])
        assert s["status"] == "ok" and s["distance_m"] <= s["max_m"] == 150 and s["main_component"] is True
        assert s["node_id"] == case["expected"]["snap"][key]["node_id"]


def test_fragment_snap_then_compare_is_no_route_not_zero(city):
    pg, _, case = city
    s = snap_point(pg, *STATION)
    assert s["status"] == "ok" and s["main_component"] is False and s["component_edges"] < 100
    p = dict(case["payload"], destination_node_ids=[s["node_id"]],
             plans=[{"id": "A", "closures": []}])
    row = compare(p, pg)["baseline"]["routes"][0]
    assert row["status"] in ("unreachable", "unknown") and row["length_m"] is None and row["edge_ids"] == []


def test_far_from_network_is_refused(city):
    pg, _, _ = city
    s = snap_point(pg, 71.30, 51.30)          # степь у края выгрузки, без пешей сети рядом
    assert s["status"] == "too_far" and s["node_id"] is None
    assert snap_point(pg, 72.5, 51.1)["status"] == "outside_graph"
