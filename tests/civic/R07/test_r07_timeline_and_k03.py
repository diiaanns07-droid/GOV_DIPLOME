"""R07: stretch-расписание (ручные ожидания) и реальный срез K03 Астаны (walking)."""
import copy
import json
import time
from pathlib import Path

import pytest

from engine.civic_scenarios import ScenarioError, compare, timeline
from engine.civic_scenarios.adapters import k03
from engine.civic_scenarios.http import handle
from engine.civic_scenarios.registry import load_graph, load_graph_dict, manifest

ROOT = Path(__file__).resolve().parents[3]
SYN = json.loads((ROOT / "engine/civic_scenarios/graphs/synthetic-tiny-v1.graph.json").read_text("utf-8"))
SYN_P = json.loads((ROOT / "engine/civic_scenarios/cases/synthetic-tiny-v1.case.json").read_text("utf-8"))["payload"]


def test_timeline_hand_calc():
    # A: e_bc закрыто 10 ч: пары A>C, A>D, A>H по +160 м -> 480 м * 10 ч = 4800 м·ч;
    #    e_ab закрыто 10 ч: A>C, A>D, A>H теряют путь -> 30 пара·ч. B: e_cd+e_gd 3 ч, A>D и A>H -> 6 пара·ч.
    r = timeline(copy.deepcopy(SYN_P), SYN, "2026-10-07T00:00:00+05:00", "2026-10-09T00:00:00+05:00")
    t = {p["id"]: p["totals"] for p in r["plans"]}
    assert t["A"]["extra_length_m_h"] == 4800 and t["A"]["pair_hours_lost_within_model"] == 30
    assert t["B"]["extra_length_m_h"] == 0 and t["B"]["pair_hours_lost_within_model"] == 6
    for p in r["plans"]:
        assert sum(s["duration_h"] for s in p["segments"]) == pytest.approx(48)


def test_timeline_window_clips_and_validates():
    r = timeline(copy.deepcopy(SYN_P), SYN, "2026-10-07T12:00:00+05:00", "2026-10-07T14:00:00+05:00")
    a = next(p for p in r["plans"] if p["id"] == "A")
    assert a["totals"]["extra_length_m_h"] == pytest.approx(480 * 2)
    with pytest.raises(ScenarioError):
        timeline(copy.deepcopy(SYN_P), SYN, "2026-10-07T14:00:00+05:00", "2026-10-07T14:00:00+05:00")
    with pytest.raises(ScenarioError):
        timeline(copy.deepcopy(SYN_P), SYN, "2026-10-07T12:00:00", "2026-10-07T14:00:00+05:00")


# ---------- реальный срез ----------
@pytest.fixture(scope="module")
def k03g():
    return load_graph_dict("k03-astana-pedestrian-r10")


def test_k03_graph_is_walking_derived_and_not_driving(k03g):
    assert k03g["mode"] == "walking" and k03g["evidence_type"] == "derived" and k03g["city"] == "astana"
    nr = manifest()["not_ready"][0]
    assert nr["mode"] == "driving" and nr["status"] == "NOT_READY" and nr["missing_fields"]
    p = _k03_payload(k03g)
    p["mode"] = "driving"
    r = handle("POST", "/api/civic/v1/scenarios/compare", body=p)
    assert r["status"] == 422 and r["body"]["error"]["code"] == "mode_mismatch"


def test_k03_adapter_reproducible_from_pinned_source():
    import subprocess
    try:
        raw = subprocess.run(["git", "show", f"{k03.SOURCE['commit']}:{k03.SOURCE['path']}"], cwd=ROOT,
                             check=True, capture_output=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("git-объект источника недоступен (нужен fetch claude/beautiful-clarke-sbzomj)")
    civic = k03.adapt(raw)
    assert civic["digest"] == load_graph_dict(civic["id"])["digest"]
    with pytest.raises(k03.AdapterNotReady):
        k03.adapt(raw.replace(b'"astana"', b'"astanb"', 1))   # изменённый источник отклоняется


def _k03_payload(g):
    allowed = [e for e in g["edges"] if e["access"] == "allowed" and not e["source"]["out_of_bbox"]]
    allowed.sort(key=lambda e: e["id"])
    nodes = sorted({e["from"] for e in allowed})
    return {"schema_version": "civic-scenario-v1", "city": "astana", "graph_id": g["id"], "graph_digest": g["digest"],
            "mode": "walking", "analysis_at": "2026-10-07T09:00:00+05:00",
            "origin_node_ids": nodes[:5], "destination_node_ids": nodes[100:140],
            "plans": [{"id": "A", "closures": [{"edge_ids": [e["id"] for e in allowed[:30]],
                                                "start_at": "2026-10-07T08:00:00+05:00", "end_at": "2026-10-07T20:00:00+05:00"}]},
                      {"id": "B", "closures": [{"edge_ids": [e["id"] for e in allowed[30:60]],
                                                "start_at": "2026-10-07T08:00:00+05:00", "end_at": "2026-10-07T20:00:00+05:00"}]}]}


def test_k03_compare_invariants_and_speed(k03g):
    pg = load_graph("k03-astana-pedestrian-r10")
    p = _k03_payload(k03g)
    t0 = time.perf_counter()
    r = compare(p, pg)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, elapsed   # 5 x 40 пар, 2309 узлов: ожидаемо << 1 с
    assert any(w["code"] == "graph_is_slice" for w in r["warnings"])
    for pl in r["plans"]:
        ch = pl["vs_baseline"]["summary"]["changes"]
        assert ch["shorter"] == 0 and ch["gained"] == 0
        for row in pl["routes"]:
            assert not set(row["edge_ids"]) & set(pl["active_closed_edge_ids"])
            if row["status"] == "ok":
                assert all(pg.edges[e][3] == "allowed" for e in row["edge_ids"])
            else:
                assert row["length_m"] is None
    # нулевой сценарий на реальном графе совпадает с baseline
    z = copy.deepcopy(p)
    z["plans"] = [{"id": "A", "closures": []}]
    rz = compare(z, pg)
    assert rz["plans"][0]["routes"] == rz["baseline"]["routes"]
