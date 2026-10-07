"""R07: эталонный синтетический кейс — ожидания посчитаны вручную (fixtures/synthetic_expected.json)."""
import copy
import json
from pathlib import Path

import pytest

from engine.civic_scenarios import compare, prepare_graph

ROOT = Path(__file__).resolve().parents[3]
GRAPH = json.loads((ROOT / "engine/civic_scenarios/graphs/synthetic-tiny-v1.graph.json").read_text("utf-8"))
CASE = json.loads((ROOT / "engine/civic_scenarios/cases/synthetic-tiny-v1.case.json").read_text("utf-8"))
EXP = json.loads((Path(__file__).parent / "fixtures/synthetic_expected.json").read_text("utf-8"))


def rows_by_pair(rows):
    return {f"{r['origin_node_id']}>{r['destination_node_id']}": r for r in rows}


@pytest.fixture(scope="module")
def result():
    return compare(copy.deepcopy(CASE["payload"]), GRAPH)


def plan(result, pid):
    return next(p for p in result["plans"] if p["id"] == pid)


def check(rows, expected):
    got = rows_by_pair(rows)
    for pair, (status, length) in expected.items():
        assert got[pair]["status"] == status, pair
        assert got[pair]["length_m"] == length, pair


def test_baseline_matches_hand_calc(result):
    check(result["baseline"]["routes"], EXP["baseline"])
    got = rows_by_pair(result["baseline"]["routes"])
    for pair, upper in EXP["baseline_unknown_upper_m"].items():
        assert got[pair]["length_if_unknown_allowed_m"] == upper
        assert got[pair]["reason"] == "path_only_via_unknown_access"


def test_plan_a_alternative_is_longer_and_tie_reported(result):
    p = plan(result, "A")
    assert p["active_closed_edge_ids"] == ["e_bc"]
    assert [c["reason"] for c in p["inactive_closures"]] == ["not_started"]
    check(p["routes"], EXP["plan_A"])
    got = rows_by_pair(p["routes"])
    for pair, tie in EXP["plan_A_equal_cost"].items():
        assert got[pair]["equal_cost_alternatives"] is tie
    # при равных путях проверяем стоимость и допустимость, а не конкретную ветку
    d = got["n_a>n_d"]
    assert d["edge_ids"] in (["e_ab", "e_be", "e_ef", "e_fc", "e_cd"], ["e_ab", "e_be", "e_ef", "e_fg", "e_gd"])
    assert "e_bc" not in d["edge_ids"]
    deltas = {f"{x['origin_node_id']}>{x['destination_node_id']}": x for x in p["vs_baseline"]["pairs"]}
    for pair, dm in EXP["plan_A_delta_m"].items():
        assert deltas[pair]["delta_m"] == dm and deltas[pair]["change"] == "longer"


def test_plan_b_only_path_closed_is_unreachable_within_model(result):
    p = plan(result, "B")
    assert p["active_closed_edge_ids"] == ["e_cd", "e_gd"]  # start в другом смещении = analysis_at, включительно
    check(p["routes"], EXP["plan_B"])
    for r in p["routes"]:
        if r["status"] == "unreachable":
            assert r["reason"] == "no_path_within_model" and r["length_m"] is None and r["edge_ids"] == []


def test_a_vs_b_and_means_only_over_comparable(result):
    ab = {f"{x['origin_node_id']}>{x['destination_node_id']}": x for x in result["a_vs_b"]["pairs"]}
    for pair, ch in EXP["a_vs_b_change"].items():
        assert ab[pair]["change"] == ch
    s = plan(result, "A")["vs_baseline"]["summary"]
    oks = [x for x in plan(result, "A")["vs_baseline"]["pairs"] if x["delta_m"] is not None]
    assert s["comparable_pairs"] == len(oks)
    assert s["mean_delta_m_comparable"] == pytest.approx(sum(x["delta_m"] for x in oks) / len(oks))
    sb = plan(result, "B")["vs_baseline"]["summary"]
    # недостижимые пары не входят в среднее как 0
    assert sb["changes"]["lost_within_model"] >= 2
    assert sb["mean_delta_m_comparable"] == 0.0


def test_oneway_respected(result):
    got = rows_by_pair(result["baseline"]["routes"])
    assert got["n_a>n_h"]["status"] == "ok"
    assert got["n_h>n_a"]["status"] == "unreachable"


def test_graph_coverage_reports_unknown_length():
    pg = prepare_graph(GRAPH)
    assert pg.coverage["length_m_by_access"] == {"allowed": 890.0, "denied": 50.0, "unknown": 200.0}
