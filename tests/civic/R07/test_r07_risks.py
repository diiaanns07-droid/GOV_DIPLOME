"""R07: риски семантики — время, смещения, digest, ошибки ввода, инварианты."""
import copy
import json
import random
from pathlib import Path

import pytest

from engine.civic_scenarios import ScenarioError, compare, graph_digest, prepare_graph

ROOT = Path(__file__).resolve().parents[3]
GRAPH = json.loads((ROOT / "engine/civic_scenarios/graphs/synthetic-tiny-v1.graph.json").read_text("utf-8"))
PAYLOAD = json.loads((ROOT / "engine/civic_scenarios/cases/synthetic-tiny-v1.case.json").read_text("utf-8"))["payload"]


def P(**over):
    p = copy.deepcopy(PAYLOAD)
    p.update(over)
    return p


def strip(result):
    """Результат без дайджестов, зависящих от байтов входа."""
    r = copy.deepcopy(result)
    r.pop("result_digest")
    r["input"].pop("payload_digest")
    r["input"].pop("analysis_at")
    return r


def routes(result, pid=None):
    src = result["baseline"] if pid is None else next(p for p in result["plans"] if p["id"] == pid)
    return [(r["origin_node_id"], r["destination_node_id"], r["status"], r["length_m"]) for r in src["routes"]]


def err(payload, graph=GRAPH):
    with pytest.raises(ScenarioError) as e:
        compare(payload, graph)
    return e.value


# ---------- инварианты ----------
def test_zero_scenario_equals_baseline():
    p = P(plans=[{"id": "A", "closures": []}, {"id": "B", "closures": [
        {"edge_ids": ["e_bc"], "start_at": "2026-10-08T00:00:00+05:00", "end_at": "2026-10-09T00:00:00+05:00"}]}])
    r = compare(p, GRAPH)
    assert routes(r, "A") == routes(r) == routes(r, "B")
    for pl in r["plans"]:
        assert pl["vs_baseline"]["summary"]["changes"]["unchanged"] == pl["vs_baseline"]["summary"]["comparable_pairs"]
        assert any(w["code"] == "no_active_closures" for w in pl["warnings"])


def test_closure_permutation_does_not_change_result():
    base = compare(P(), GRAPH)
    rnd = random.Random(7)
    for _ in range(5):
        p = P()
        for pl in p["plans"]:
            rnd.shuffle(pl["closures"])
            for c in pl["closures"]:
                rnd.shuffle(c["edge_ids"])
        rnd.shuffle(p["plans"])
        r = compare(p, GRAPH)
        assert strip(r) == strip(base)
        assert r["input"]["scenario_digest"] == base["input"]["scenario_digest"]


def test_duplicate_and_overlapping_closures_are_idempotent():
    p = P(plans=[{"id": "A", "closures": [
        {"edge_ids": ["e_bc", "e_bc"], "start_at": "2026-10-07T08:00:00+05:00", "end_at": "2026-10-07T18:00:00+05:00"},
        {"edge_ids": ["e_bc"], "start_at": "2026-10-07T07:00:00+05:00", "end_at": "2026-10-07T10:00:00+05:00"}]}])
    assert routes(compare(p, GRAPH), "A") == routes(compare(P(), GRAPH), "A")


def test_closure_never_shortens_routes():
    r = compare(P(), GRAPH)
    for pl in r["plans"]:
        assert pl["vs_baseline"]["summary"]["changes"]["shorter"] == 0
        assert pl["vs_baseline"]["summary"]["changes"]["gained"] == 0


def test_input_not_mutated_between_runs():
    p, g = P(), copy.deepcopy(GRAPH)
    p0, g0 = copy.deepcopy(p), copy.deepcopy(g)
    r1 = compare(p, g)
    r2 = compare(p, g)
    assert p == p0 and g == g0
    assert r1 == r2 and r1["result_digest"] == r2["result_digest"]


def test_prepared_graph_reuse_gives_same_result():
    pg = prepare_graph(GRAPH)
    assert compare(P(), pg) == compare(P(), GRAPH)
    other = P(plans=[{"id": "A", "closures": []}])
    compare(other, pg)
    assert compare(P(), pg) == compare(P(), GRAPH)


# ---------- время ----------
def _plan_a_at(at):
    return next(p for p in compare(P(analysis_at=at), GRAPH)["plans"] if p["id"] == "A")["active_closed_edge_ids"]


def test_interval_start_inclusive_end_exclusive():
    assert _plan_a_at("2026-10-07T08:00:00+05:00") == ["e_bc"]
    assert _plan_a_at("2026-10-07T07:59:59+05:00") == []
    assert _plan_a_at("2026-10-07T17:59:59.999+05:00") == ["e_bc"]
    assert _plan_a_at("2026-10-07T18:00:00+05:00") == []


def test_same_instant_different_offsets():
    a = compare(P(analysis_at="2026-10-07T09:00:00+05:00"), GRAPH)
    b = compare(P(analysis_at="2026-10-07T04:00:00Z"), GRAPH)
    c = compare(P(analysis_at="2026-10-07T06:00:00+02:00"), GRAPH)
    assert strip(a) == strip(b) == strip(c)
    assert a["input"]["analysis_at_utc"] == "2026-10-07T04:00:00Z"


@pytest.mark.parametrize("bad", ["2026-10-07T09:00:00", "2026-10-07", "07.10.2026 09:00", "2026-13-07T09:00:00Z", 1730000000, None])
def test_analysis_at_requires_offset(bad):
    assert err(P(analysis_at=bad)).code == "invalid_payload"


def test_empty_or_reversed_interval_rejected():
    for s, e in [("2026-10-07T09:00:00+05:00", "2026-10-07T04:00:00Z"), ("2026-10-07T10:00:00+05:00", "2026-10-07T09:00:00+05:00")]:
        p = P(plans=[{"id": "A", "closures": [{"edge_ids": ["e_bc"], "start_at": s, "end_at": e}]}])
        assert err(p).code == "invalid_payload"


# ---------- ошибки ввода ----------
def test_unknown_edge_and_node():
    p = P(plans=[{"id": "A", "closures": [{"edge_ids": ["e_bc", "e_nope"], "start_at": "2026-10-07T08:00:00+05:00",
                                             "end_at": "2026-10-07T18:00:00+05:00"}]}])
    e = err(p)
    assert e.code == "unknown_edge" and e.fields["edge_ids"] == ["e_nope"] and e.http_status == 422
    assert err(P(origin_node_ids=["n_zz"])).code == "unknown_node"
    assert err(P(destination_node_ids=["n_a", "n_a"])).code == "invalid_payload"


def test_plan_ids_and_shape():
    assert err(P(plans=[{"id": "A", "closures": []}, {"id": "A", "closures": []}])).code == "invalid_payload"
    assert err(P(plans=[{"id": "C", "closures": []}])).code == "invalid_payload"
    assert err(P(plans=[])).code == "invalid_payload"
    assert err(P(plans=[{"id": "A", "closures": [], "metrics": {"delta": 0}}])).code == "invalid_payload"


def test_client_cannot_inject_metrics_or_paths():
    for k, v in [("graph_path", "/etc/passwd"), ("graph_url", "http://x"), ("result", {}), ("baseline", [])]:
        assert err(P(**{k: v})).code == "invalid_payload"


def test_mode_city_graph_checks():
    assert err(P(mode="driving")).code == "mode_mismatch"   # walking-граф не выдаётся за автомобильный
    assert err(P(city="shymkent")).code == "city_mismatch"
    g = copy.deepcopy(GRAPH)
    g["city"] = "shymkent"
    g["digest"] = graph_digest(g)
    assert err(P(graph_digest=g["digest"]), g).code == "city_mismatch"   # срез другого города
    assert err(P(graph_id="other")).code == "graph_mismatch"
    assert err(P(schema_version="civic-scenario-v0")).code == "invalid_payload"


def test_changed_digest_detected():
    g = copy.deepcopy(GRAPH)
    g["edges"][0]["length_m"] = 1          # подмена содержимого без обновления digest
    e = err(P(), g)
    assert e.code == "graph_digest_mismatch" and e.http_status == 409
    e2 = err(P(graph_digest="0" * 64))      # клиент считает по старой версии графа
    assert e2.code == "graph_digest_mismatch"


def _graph_with(edit):
    g = copy.deepcopy(GRAPH)
    edit(g)
    g["digest"] = graph_digest(g)
    return g


@pytest.mark.parametrize("edit", [
    lambda g: g["edges"][0].update(length_m=-1),
    lambda g: g["edges"][0].update(length_m=float("inf")),
    lambda g: g["edges"][0].update(length_m="100"),
    lambda g: g["edges"][0].update(length_m=True),
    lambda g: g["edges"][0].update(to="n_missing"),
    lambda g: g["edges"][0].update(access="maybe"),
    lambda g: g["edges"][0].update(oneway="no"),
    lambda g: g["edges"].append(dict(g["edges"][0])),
    lambda g: g["nodes"].append(dict(g["nodes"][0])),
    lambda g: g["nodes"][0].update(lat=95),
    lambda g: g.update(mode="bus"),
])
def test_invalid_graph_rejected(edit):
    g = copy.deepcopy(GRAPH)
    edit(g)  # digest намеренно не пересчитан: структурная ошибка должна победить
    with pytest.raises(ScenarioError) as e:
        prepare_graph(g)
    assert e.value.code == "invalid_graph"
    with pytest.raises(ScenarioError) as e2:   # и с честно пересчитанным digest (кроме inf — его не сериализовать)
        prepare_graph(_graph_with(edit)) if not _has_inf(g) else prepare_graph(g)
    assert e2.value.code == "invalid_graph"


def _has_inf(g):
    return any(isinstance(e.get("length_m"), float) and abs(e["length_m"]) == float("inf") for e in g["edges"])


def test_zero_length_edge_allowed_with_warning():
    g = _graph_with(lambda g: g["edges"][0].update(length_m=0))
    r = compare(P(graph_digest=g["digest"]), g)
    assert any(w["code"] == "zero_length_edges" for w in r["warnings"])
    got = {(x["origin_node_id"], x["destination_node_id"]): x for x in r["baseline"]["routes"]}
    assert got[("n_a", "n_c")]["length_m"] == 100


def test_denied_and_unknown_never_used_for_ok():
    r = compare(P(), GRAPH)
    for pl in [r["baseline"]] + r["plans"]:
        for row in pl["routes"]:
            assert "e_ax" not in row["edge_ids"] and "e_du" not in row["edge_ids"]


def test_closing_unknown_edge_warns():
    p = P(plans=[{"id": "A", "closures": [{"edge_ids": ["e_du"], "start_at": "2026-10-07T08:00:00+05:00",
                                             "end_at": "2026-10-07T18:00:00+05:00"}]}])
    pl = compare(p, GRAPH)["plans"][0]
    assert any(w["code"] == "closure_on_non_allowed_edge" for w in pl["warnings"])
    got = {(x["origin_node_id"], x["destination_node_id"]): x for x in pl["routes"]}
    assert got[("n_a", "n_u")]["status"] == "unreachable"  # единственный (unknown) путь закрыт гипотезой


def test_boundary_slice_turns_unreachable_into_unknown():
    # граница среза: X стоит на краю — «нет пути» нельзя объявлять доказанным
    g = _graph_with(lambda g: [n.update(boundary=True) for n in g["nodes"] if n["id"] in ("n_h", "n_a")])
    r = compare(P(graph_digest=g["digest"]), g)
    got = {(x["origin_node_id"], x["destination_node_id"]): x for x in r["baseline"]["routes"]}
    assert got[("n_h", "n_a")]["status"] == "unknown"
    assert got[("n_h", "n_a")]["reason"] == "path_may_exist_outside_graph"
    assert any(w["code"] == "graph_is_slice" for w in r["warnings"])


def test_limits():
    many = [f"n{i}" for i in range(200)]
    assert err(P(destination_node_ids=many)).code == "too_large"
    big = P(plans=[{"id": "A", "closures": [{"edge_ids": ["e_bc"], "start_at": "2026-10-07T08:00:00+05:00",
                                               "end_at": "2026-10-07T18:00:00+05:00"}] * 101}])
    assert err(big).code == "too_large"
