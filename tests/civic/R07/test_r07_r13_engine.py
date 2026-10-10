"""R07 round 13: привязка точек к сети, пояснения сравнения, колбэк on_result, границы кэша.

Маленькие графы строятся здесь же, ожидания посчитаны вручную. Координаты условные.
"""
import copy
import json
from pathlib import Path

import pytest

from engine.civic_scenarios import ScenarioError, compare, graph_digest, prepare_graph
from engine.civic_scenarios.http import handle
from engine.civic_scenarios.snap import haversine_m, snap_point

ROOT = Path(__file__).resolve().parents[3]
SYN = json.loads((ROOT / "engine/civic_scenarios/graphs/synthetic-tiny-v1.graph.json").read_text("utf-8"))
SYN_P = json.loads((ROOT / "engine/civic_scenarios/cases/synthetic-tiny-v1.case.json").read_text("utf-8"))["payload"]


def graph(nodes, edges, bbox=None, gid="r13-test"):
    g = {"id": gid, "city": "astana", "mode": "walking", "evidence_type": "synthetic",
         "nodes": [{"id": i, "lon": x, "lat": y} for i, (x, y) in nodes.items()],
         "edges": [{"id": e, "from": a, "to": b, "length_m": L, "access": acc, "oneway": False}
                   for e, a, b, L, acc in edges]}
    if bbox:
        g["bbox"] = bbox
    g["digest"] = graph_digest(g)
    return prepare_graph(g)


# Основная сеть M1-M2-M3 (allowed), фрагмент F1-F2 (allowed, не связан), U1-U2 (unknown) рядом с точкой.
LON, LAT = 71.40, 51.10
DEG = 1 / 111_000   # ~1 м по широте
NET = graph(
    {"M1": (LON, LAT), "M2": (LON + 0.002, LAT), "M3": (LON + 0.004, LAT),
     "F1": (LON, LAT + 400 * DEG), "F2": (LON + 0.001, LAT + 400 * DEG),
     "U1": (LON + 0.004, LAT + 30 * DEG), "U2": (LON + 0.005, LAT + 30 * DEG)},
    [("m12", "M1", "M2", 140, "allowed"), ("m23", "M2", "M3", 140, "allowed"),
     ("f12", "F1", "F2", 70, "allowed"), ("u12", "U1", "U2", 70, "unknown")],
    bbox=[LON - 0.01, LAT - 0.01, LON + 0.01, LAT + 0.01])


def test_snap_ok_reports_input_node_and_distance():
    s = snap_point(NET, LON, LAT + 20 * DEG)
    assert s["status"] == "ok" and s["node_id"] == "M1" and s["input"] == [LON, LAT + 20 * DEG]
    assert s["distance_m"] == pytest.approx(20, abs=0.3) and s["max_m"] == 150
    assert s["main_component"] is True and s["component_edges"] == 2


def test_snap_refuses_far_point_and_never_moves_it_silently():
    s = snap_point(NET, LON - 0.0045, LAT - 200 * DEG)          # ~370 м от M1
    assert s["status"] == "too_far" and s["node_id"] is None
    assert s["nearest_allowed_m"] > 150


def test_snap_ignores_unknown_access_but_reports_it():
    # Точка в 2 м от U1 (доступ неизвестен); ближайший allowed — M3 в ~30 м.
    s = snap_point(NET, LON + 0.004, LAT + 28 * DEG)
    assert s["status"] == "ok" and s["node_id"] == "M3"
    assert s["nearer_unverified_m"] == pytest.approx(2, abs=0.5)


def test_snap_fragment_is_flagged_and_main_offered_only_as_choice():
    near_fragment = snap_point(NET, LON, LAT + 330 * DEG)        # F1 в 70 м, M1 в 330 м
    assert near_fragment["node_id"] == "F1" and near_fragment["main_component"] is False
    assert near_fragment["main_alternative"] is None             # основная сеть дальше порога
    both = snap_point(NET, LON, LAT + 330 * DEG, max_m=400)
    assert both["node_id"] == "F1" and both["main_alternative"]["node_id"] == "M1"


def test_snap_outside_bbox_and_bad_input():
    assert snap_point(NET, LON + 0.5, LAT)["status"] == "outside_graph"
    for bad in ((float("nan"), LAT), (LON, 95.0)):
        with pytest.raises(ScenarioError):
            snap_point(NET, *bad)
    with pytest.raises(ScenarioError):
        snap_point(NET, LON, LAT, max_m=5000)


def test_snap_tie_breaks_by_node_id():
    g = graph({"b": (LON + 0.001, LAT), "a": (LON - 0.001, LAT), "c": (LON + 0.003, LAT)},
              [("ab", "a", "b", 100, "allowed"), ("bc", "b", "c", 100, "allowed")])
    assert snap_point(g, LON, LAT)["node_id"] == "a"
    assert haversine_m((LON, LAT), (LON + 0.001, LAT)) == pytest.approx(haversine_m((LON, LAT), (LON - 0.001, LAT)))


# ---------------------------------------------------------------- compare
def P(**over):
    p = copy.deepcopy(SYN_P)
    p.update(over)
    return p


def closure(ids, start="2026-10-07T08:00:00+05:00", end="2026-10-07T18:00:00+05:00"):
    return {"edge_ids": ids, "start_at": start, "end_at": end}


def test_closure_off_baseline_routes_is_explained_noop():
    r = compare(P(plans=[{"id": "A", "closures": [closure(["e_fg"])]}]), SYN)   # F-G не на базовых путях
    plan = r["plans"][0]
    assert plan["closed_on_baseline_routes"] == []
    assert any(w["code"] == "closure_not_on_baseline_routes" for w in plan["warnings"])
    # сопоставимы A>C, A>D, A>H, A>A, H>H — все без изменений
    assert [x["delta_m"] for x in plan["vs_baseline"]["pairs"] if x["delta_m"] is not None] == [0.0] * 5


def test_identical_plans_flagged():
    same = [closure(["e_bc"])]
    r = compare(P(plans=[{"id": "A", "closures": same}, {"id": "B", "closures": copy.deepcopy(same)}]), SYN)
    assert r["a_vs_b"]["identical_active_closures"] is True
    assert any(w["code"] == "plans_identical_at_analysis_at" for w in r["warnings"])
    assert r["a_vs_b"]["summary"]["changes"]["unchanged"] == r["a_vs_b"]["summary"]["comparable_pairs"]
    diff_time = [{"id": "A", "closures": same}, {"id": "B", "closures": [closure(["e_bc"], "2026-10-08T08:00:00+05:00", "2026-10-08T09:00:00+05:00")]}]
    assert compare(P(plans=diff_time), SYN)["a_vs_b"]["identical_active_closures"] is False


def test_all_paths_closed_is_unreachable_not_zero():
    r = compare(P(plans=[{"id": "A", "closures": [closure(["e_ab"])]}]), SYN)   # A отрезан (A-X запрещён)
    rows = {(x["origin_node_id"], x["destination_node_id"]): x for x in r["plans"][0]["routes"]}
    for dest in ("n_c", "n_d", "n_h"):
        assert rows[("n_a", dest)]["status"] == "unreachable" and rows[("n_a", dest)]["length_m"] is None
    assert rows[("n_a", "n_a")]["length_m"] == 0      # тот же узел — это 0 по определению, не «нет пути»
    summary = r["plans"][0]["vs_baseline"]["summary"]
    assert summary["changes"]["lost_within_model"] == 3
    assert summary["mean_delta_m_comparable"] == 0.0   # среднее только по сопоставимым (A>A, H>H)


# ---------------------------------------------------------------- on_result
def test_on_result_called_once_after_success_only():
    calls = []
    ok = handle("POST", "/api/civic/v1/scenarios/compare", body=P(), on_result=lambda p, r: calls.append((p, r)))
    assert ok["status"] == 200 and len(calls) == 1
    payload, result = calls[0]
    assert payload == P() and result["result_digest"] == ok["body"]["data"]["result_digest"]
    assert "timing_ms" not in result and "timing_ms" in ok["body"]["data"]
    bad = handle("POST", "/api/civic/v1/scenarios/compare", body=P(analysis_at="2026-10-07"), on_result=calls.append)
    assert bad["status"] == 422 and len(calls) == 1


def test_on_result_failure_does_not_break_compare():
    def boom(payload, result):
        raise RuntimeError("cache down")
    r = handle("POST", "/api/civic/v1/scenarios/compare", body=P(), on_result=boom)
    assert r["status"] == 200 and r["body"]["ok"] is True


def test_two_different_inputs_give_two_result_digests():
    a = compare(P(), SYN)["result_digest"]
    b = compare(P(analysis_at="2026-10-07T19:00:00+05:00"), SYN)["result_digest"]   # A уже не действует
    assert a != b and compare(P(), SYN)["result_digest"] == a


def test_adjacency_cache_is_bounded():
    pg = prepare_graph(SYN)
    ids = sorted(pg.edges)
    for i in range(80):
        pg.adjacency(("allowed",), frozenset({ids[i % len(ids)], ids[(i * 7) % len(ids)], str(i)}))
    assert len(pg._adj_cache) <= 64
