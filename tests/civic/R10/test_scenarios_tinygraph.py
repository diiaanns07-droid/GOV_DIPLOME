"""R07 scenario engine acceptance on R10's own tiny graphs (CONTRACT section 5, acceptance M01).

Data: scenarios/tiny_graphs.json (2 synthetic Astana graphs), scenarios/expected.json (hand-computed
status/length per plan per OD pair, each with a written derivation), scenarios/bruteforce.py
(exhaustive simple-path enumerator, deliberately not Dijkstra).

Part (a) ALWAYS runs: graphs are well-formed, every hand-written value equals the brute force,
every hand path is a valid route summing to its length, each error case is invalid for exactly its
stated reason, and the case set provably catches typical engine bugs (bug-injected brute force).

Part (b) runs the product engine.civic_scenarios:compare(payload, graph) from R10_CODE_ROOT
(default: this checkout) in an isolated `python -I` subprocess via r10lib/modrun.py, which records
the imported module file and the checkout SHA. Without the module every product test is
NOT_RUN. Output is read through ONE adapter, extract_routes(); if the shape cannot be read the
test is NOT_RUN (needs an R07 INTEGRATION note), never PASS.
Not covered here: in-process mutation of the caller's payload/graph (subprocess hides it).
"""

from __future__ import annotations

import copy
from decimal import Decimal
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10lib import modrun  # noqa: E402

HERE = Path(__file__).resolve().parent
SCN = HERE / "scenarios"
REPO_ROOT = HERE.parents[2]
MODULE = "engine.civic_scenarios"
TARGET = "engine.civic_scenarios:compare"
CALL_TIMEOUT = 60.0

_spec = importlib.util.spec_from_file_location("r10_scenarios_bruteforce", SCN / "bruteforce.py")
bruteforce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bruteforce)

GRAPH_DOC = json.loads((SCN / "tiny_graphs.json").read_text(encoding="utf-8"))
GRAPHS = {g["id"]: g for g in GRAPH_DOC["graphs"]}
EXPECTED = json.loads((SCN / "expected.json").read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in EXPECTED["cases"]}
RESULT_CASES = [c for c in EXPECTED["cases"] if c["expect"] == "result"]
ERROR_CASES = [c for c in EXPECTED["cases"] if c["expect"] == "error"]
TOL = EXPECTED["length_tolerance_m"]

GRAPH_KEYS = {"id", "city", "digest", "mode", "evidence_type", "nodes", "edges"}
ACCESS = {"allowed", "denied", "unknown"}
STATUSES = {"ok", "unreachable", "unknown"}
LON_RANGE, LAT_RANGE = (71.40, 71.46), (51.12, 51.18)
FORBIDDEN_KEY_PARTS = ("co2", "congestion", "traffic", "emission", "travel_time")
CRASH_TYPES = {"TypeError", "KeyError", "AttributeError", "IndexError", "ZeroDivisionError",
               "RecursionError", "UnboundLocalError", "NameError", "AssertionError", "OverflowError",
               "ImportError", "ModuleNotFoundError", "SyntaxError", "NoJSON", "Timeout"}
VOLATILE_KEY = re.compile(r"(timing|elapsed|duration|generated_at|computed_at|_ms$)", re.IGNORECASE)
SHAPE_SKIP = "NOT_RUN: compare() output shape not interpretable; needs R07 INTEGRATION doc"

# Which product test owns which result case (a self-check keeps this complete).
CASE_OWNERS = {
    "test_zero_closure_plan_equals_baseline": ["g1-zero-closure"],
    "test_short_route_closure_detour_and_bridge_unreachable": ["g1-detour", "g1-bridge"],
    "test_tie_asserts_length_only": ["g1-tie-branch"],
    "test_closure_window_is_half_open": ["g1-window-boundaries"],
    "test_same_instant_with_different_offsets_same_routes": ["g1-offset-plus05", "g1-offset-z", "g1-offset-plus06"],
    "test_closure_and_plan_order_do_not_change_routes": ["g1-permutation-1", "g1-permutation-2"],
    "test_unknown_access_is_neither_ok_nor_proven_unreachable": ["g2-access", "g2-unknown-closed"],
    "test_oneway_direction_is_respected": ["g2-oneway-reverse", "g2-oneway-forward"],
}

# Which single defect R10's own reading finds in each error case, by error_kind.
ERROR_KIND_REASONS = {
    "validation": {"unknown_edge", "unknown_node", "duplicate_plan_id"},
    "graph_validation": {"bad_length"},
    "mismatch": {"city_mismatch"},
    "digest": {"graph_content_digest", "payload_digest"},
}


# ---------------------------------------------------------------- shared data helpers

def _special(value):
    if isinstance(value, dict) and set(value) == {"$float"}:
        return float(value["$float"])
    return value


def build_graph(case: dict) -> dict:
    graph = copy.deepcopy(GRAPHS[case["graph_id"]])
    patch = case.get("graph_patch")
    if patch:
        for key, value in patch.get("graph", {}).items():
            graph[key] = _special(value)
        edges = {e["id"]: e for e in graph["edges"]}
        for eid, fields in patch.get("edges", {}).items():
            for key, value in fields.items():
                edges[eid][key] = _special(value)
        if patch.get("digest") == "recompute":
            graph["digest"] = bruteforce.canonical_digest(graph)
    return graph


def build_payload(case: dict, graph: dict) -> dict:
    payload = copy.deepcopy(case["payload"])
    if payload.get("graph_digest") == "$GRAPH_DIGEST":
        payload["graph_digest"] = graph["digest"]
    return payload


def pair_key(o: str, d: str) -> str:
    return f"{o}>{d}"


def fmt_len(value) -> str:
    return str(int(value)) if float(value).is_integer() else repr(value)


def closed_for(case: dict, state: str) -> set:
    if state == "baseline":
        return set()
    plan = next(p for p in case["payload"]["plans"] if p["id"] == state)
    return bruteforce.closed_edges(plan, case["payload"]["analysis_at"])


def route_problems(graph: dict, origin: str, dest: str, edge_ids, closed: set, length=None) -> list:
    """R10's own walker: is edge_ids a strict-policy route origin->dest that is open and sums to length?"""
    edges = {e["id"]: e for e in graph["edges"]}
    problems, here, total = [], origin, Decimal(0)
    for eid in edge_ids:
        e = edges.get(eid)
        if e is None:
            return problems + [f"edge {eid!r} not in graph"]
        if eid in closed:
            problems.append(f"uses closed edge {eid}")
        if e["access"] != "allowed":
            problems.append(f"uses {e['access']} edge {eid}")
        if e["from"] == here:
            here = e["to"]
        elif e["to"] == here and not e["oneway"]:
            here = e["from"]
        elif e["to"] == here:
            problems.append(f"travels oneway edge {eid} against its direction")
            here = e["from"]
        else:
            return problems + [f"edge {eid} does not continue from node {here}"]
        total += Decimal(repr(e["length_m"]))
    if here != dest:
        problems.append(f"ends at {here}, not {dest}")
    if length is not None and abs(float(total) - float(length)) > TOL:
        problems.append(f"edges sum to {total} m but length_m is {length}")
    return problems


def r10_invalidity(graph: dict, payload: dict) -> list:
    """Reasons R10's reading of CONTRACT section 5 rejects this input (empty list = valid)."""
    reasons = []
    node_ids = {n["id"] for n in graph["nodes"]}
    edge_ids = {e["id"] for e in graph["edges"]}
    for e in graph["edges"]:
        length = e["length_m"]
        if isinstance(length, bool) or not isinstance(length, (int, float)) \
                or not math.isfinite(length) or length < 0:
            reasons.append("bad_length")
    if graph["city"] != payload["city"]:
        reasons.append("city_mismatch")
    if bruteforce.canonical_digest(graph) != graph["digest"]:
        reasons.append("graph_content_digest")
    if payload["graph_digest"] != graph["digest"]:
        reasons.append("payload_digest")
    if any(n not in node_ids for n in payload["origin_node_ids"] + payload["destination_node_ids"]):
        reasons.append("unknown_node")
    if any(eid not in edge_ids for p in payload["plans"] for c in p["closures"] for eid in c["edge_ids"]):
        reasons.append("unknown_edge")
    plan_ids = [p["id"] for p in payload["plans"]]
    if len(set(plan_ids)) != len(plan_ids):
        reasons.append("duplicate_plan_id")
    return reasons


# ---------------------------------------------------------------- product adapter

ORIGIN_KEYS = ("origin_node_id", "origin", "from_node_id", "source_node_id")
DEST_KEYS = ("destination_node_id", "destination", "to_node_id", "target_node_id")
ROUTE_LIST_KEYS = ("routes", "pairs", "od_pairs", "results")


def _unwrap(result):
    if isinstance(result, dict) and result.get("ok") is True and isinstance(result.get("data"), dict):
        return result["data"]
    return result


def _rows(block):
    if isinstance(block, dict):
        block = next((block[k] for k in ROUTE_LIST_KEYS if isinstance(block.get(k), list)), None)
    if not isinstance(block, list):
        return None
    out = {}
    for row in block:
        if not isinstance(row, dict) or "status" not in row:
            return None
        o = next((row[k] for k in ORIGIN_KEYS if k in row), None)
        d = next((row[k] for k in DEST_KEYS if k in row), None)
        if not isinstance(o, str) or not isinstance(d, str) or (o, d) in out:
            return None
        edges = row.get("edge_ids", row.get("route_edge_ids"))
        out[(o, d)] = {"status": row["status"], "length_m": row.get("length_m", row.get("length")),
                       "edge_ids": edges if isinstance(edges, list) else None}
    return out


def extract_routes(result) -> dict:
    """The one place that reads compare() output: {'baseline'|plan_id: {(o, d): route}}.

    Documented shape (R07 README): result.baseline.routes[] and result.plans[] = {id, routes[]},
    each route {origin_node_id, destination_node_id, status, length_m, edge_ids}. Anything that
    cannot be read raises SkipTest(SHAPE_SKIP): unreadable output is NOT_RUN, never PASS.
    """
    r = _unwrap(result)
    if not isinstance(r, dict):
        raise unittest.SkipTest(SHAPE_SKIP)
    plans = r.get("plans")
    if isinstance(plans, list):
        items = [(p.get("id", p.get("plan_id")), p) for p in plans if isinstance(p, dict)]
    elif isinstance(plans, dict):
        items = list(plans.items())
    else:
        items = []
    states = {"baseline": _rows(r.get("baseline"))}
    for pid, plan in items:
        states[pid] = _rows(plan)
    if not items or any(not isinstance(k, str) or v is None for k, v in states.items()):
        raise unittest.SkipTest(SHAPE_SKIP)
    return states


def rejection(reply: dict):
    """(rejected, crashed, detail) for a modrun reply."""
    if not reply.get("ok"):
        etype = reply.get("error_type", "?")
        return True, etype in CRASH_TYPES, f"{etype}: {str(reply.get('error'))[:300]}"
    res = reply["result"]
    if isinstance(res, dict) and (res.get("ok") is False or ("error" in res and "baseline" not in res)):
        return True, False, json.dumps(res, ensure_ascii=False, default=str)[:300]
    return False, False, "returned " + json.dumps(res, ensure_ascii=False, default=str)[:300]


def walk_keys(value, path="$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield f"{path}.{key}", str(key), item
            yield from walk_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from walk_keys(item, f"{path}[{i}]")


def string_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from string_values(item)


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if not VOLATILE_KEY.search(str(k))}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


# ---------------------------------------------------------------- (a) always-run self-checks

class TinyGraphSelfCheck(unittest.TestCase):
    """R10's own data must be right before it can judge the product."""

    def test_graph_files_are_well_formed_with_documented_digest(self):
        """[M01] R10 tiny graphs: unique ids, existing endpoints, finite non-negative lengths, Astana coordinates, documented digest"""
        features = {"oneway": 0, "unknown": 0, "denied": 0}
        for gid, g in GRAPHS.items():
            with self.subTest(graph=gid):
                self.assertEqual(set(g), GRAPH_KEYS, "graph must carry exactly the contract fields")
                self.assertEqual((g["city"], g["mode"], g["evidence_type"]), ("astana", "walking", "synthetic"))
                self.assertTrue(6 <= len(g["nodes"]) <= 10, f"{len(g['nodes'])} nodes")
                node_ids = [n["id"] for n in g["nodes"]]
                self.assertEqual(len(node_ids), len(set(node_ids)), "duplicate node id")
                for n in g["nodes"]:
                    self.assertTrue(LON_RANGE[0] <= n["lon"] <= LON_RANGE[1] and LAT_RANGE[0] <= n["lat"] <= LAT_RANGE[1],
                                    f"node {n['id']} ({n['lon']}, {n['lat']}) outside Astana test box")
                edge_ids = [e["id"] for e in g["edges"]]
                self.assertEqual(len(edge_ids), len(set(edge_ids)), "duplicate edge id")
                for e in g["edges"]:
                    self.assertEqual(set(e), {"id", "from", "to", "length_m", "access", "oneway"}, e["id"])
                    self.assertIn(e["from"], node_ids, e["id"])
                    self.assertIn(e["to"], node_ids, e["id"])
                    self.assertNotIsInstance(e["length_m"], bool)
                    self.assertTrue(isinstance(e["length_m"], (int, float)) and math.isfinite(e["length_m"])
                                    and e["length_m"] >= 0, f"{e['id']} length {e['length_m']!r}")
                    self.assertIn(e["access"], ACCESS)
                    self.assertIsInstance(e["oneway"], bool)
                    features["oneway"] += e["oneway"]
                    features["unknown"] += e["access"] == "unknown"
                    features["denied"] += e["access"] == "denied"
                self.assertEqual(g["digest"], bruteforce.canonical_digest(g),
                                 "digest must equal sha256 of canonical JSON without 'digest' (tiny_graphs.json digest_rule)")
        self.assertTrue(all(features.values()), f"graphs must include oneway/unknown/denied edges: {features}")

    def test_hand_expectations_equal_bruteforce(self):
        """[M01] every hand-written status/length/tie flag equals the exhaustive simple-path enumeration"""
        for case in RESULT_CASES:
            graph = GRAPHS[case["graph_id"]]
            got = bruteforce.evaluate(graph, case["payload"])
            p = case["payload"]
            pairs = {pair_key(o, d) for o in p["origin_node_ids"] for d in p["destination_node_ids"]}
            self.assertEqual(set(case["expected"]), {"baseline"} | {pl["id"] for pl in p["plans"]}, case["id"])
            for state, entries in case["expected"].items():
                self.assertEqual(set(entries), pairs, f"{case['id']}/{state}: expected pairs != payload pairs")
                for key, exp in entries.items():
                    with self.subTest(case=case["id"], state=state, pair=key):
                        bf = got[state][key]
                        self.assertEqual(bf["status"], exp["status"], exp["derivation"])
                        if exp["status"] == "ok":
                            self.assertEqual(bf["length"], Decimal(repr(exp["length_m"])), exp["derivation"])
                        else:
                            self.assertIsNone(exp["length_m"])
                        self.assertEqual(len(bf["minimal_paths"]) >= 2, bool(exp.get("tie")),
                                         f"tie flag wrong; minimal paths {bf['minimal_paths']}")

    def test_hand_paths_are_valid_routes_summing_to_length(self):
        """[M01] each hand-written path_edges is an open strict route of the stated length, and every derivation states its number"""
        for case in RESULT_CASES:
            graph = GRAPHS[case["graph_id"]]
            for state, entries in case["expected"].items():
                closed = closed_for(case, state)
                for key, exp in entries.items():
                    with self.subTest(case=case["id"], state=state, pair=key):
                        self.assertTrue(exp.get("derivation"), "derivation missing")
                        if exp["status"] != "ok":
                            self.assertNotIn("path_edges", exp)
                            continue
                        o, d = key.split(">")
                        self.assertEqual(route_problems(graph, o, d, exp["path_edges"], closed, exp["length_m"]), [])
                        self.assertIn(fmt_len(exp["length_m"]), exp["derivation"], "derivation must show the length")
                        minimal = bruteforce.evaluate(graph, case["payload"])[state][key]["minimal_paths"]
                        self.assertIn(exp["path_edges"], minimal, "hand path is not a shortest path")

    def test_error_cases_are_invalid_for_exactly_their_stated_reason(self):
        """[M01] each error case has exactly one defect of its kind; every result case is valid input"""
        covered = set()
        for case in ERROR_CASES:
            with self.subTest(case=case["id"]):
                graph = build_graph(case)
                reasons = r10_invalidity(graph, build_payload(case, graph))
                self.assertEqual(len(reasons), 1, f"{case['id']}: defects {reasons} (want exactly one)")
                self.assertIn(reasons[0], ERROR_KIND_REASONS[case["error_kind"]])
                covered.add(reasons[0])
        self.assertEqual(covered, set().union(*ERROR_KIND_REASONS.values()), "an error class has no case")
        for case in RESULT_CASES:
            graph = build_graph(case)
            self.assertEqual(r10_invalidity(graph, build_payload(case, graph)), [], case["id"])

    def test_case_set_catches_typical_engine_bugs(self):
        """[M01] a brute force with one injected bug (unknown as allowed, oneway ignored, closures ignored, string time compare, end inclusive, denied as allowed) disagrees with the expectations"""
        for variant in bruteforce.VARIANTS:
            with self.subTest(variant=variant):
                caught = []
                for case in RESULT_CASES:
                    got = bruteforce.evaluate(GRAPHS[case["graph_id"]], case["payload"], variant)
                    for state, entries in case["expected"].items():
                        for key, exp in entries.items():
                            bf = got[state][key]
                            length = None if bf["length"] is None else float(bf["length"])
                            if bf["status"] not in {exp["status"], *exp.get("also_acceptable", [])} or \
                                    (exp["status"] == "ok" and length != exp["length_m"]):
                                caught.append(f"{case['id']}/{state}/{key}")
                self.assertTrue(caught, f"no case detects bug variant {variant!r}")

    def test_every_result_case_has_an_owning_product_test(self):
        """[M01] product tests cover every result case and every same-result group exactly"""
        owned = [cid for ids in CASE_OWNERS.values() for cid in ids]
        self.assertEqual(sorted(owned), sorted(c["id"] for c in RESULT_CASES))
        for name in CASE_OWNERS:
            self.assertTrue(hasattr(ScenarioEngineProduct, name), name)
        for group in EXPECTED["same_result_groups"]:
            self.assertTrue(set(group["cases"]) <= set(CASES), group)
        self.assertIn(EXPECTED["repeat_case"]["case"], CASES)


# ---------------------------------------------------------------- (b) product checks

class ScenarioEngineProduct(unittest.TestCase):
    """R07 engine.civic_scenarios:compare against R10 expectations; NOT_RUN when the module is absent."""

    root: Path
    skip_reason: str | None = None
    _replies: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get("R10_CODE_ROOT") or REPO_ROOT).resolve()
        cls._replies = {}
        if not modrun.module_available(cls.root, MODULE):
            cls.skip_reason = f"NOT_RUN: engine.civic_scenarios not present in {cls.root}"
            return
        probe = cls.reply("g1-zero-closure")
        rejected, _crashed, detail = rejection(probe)
        if rejected and "digest" in detail.lower():
            cls.skip_reason = ("NOT_RUN: product rejected R10's graph digest (sha256 of canonical JSON without "
                               f"'digest', see scenarios/tiny_graphs.json digest_rule): {detail[:200]}; "
                               "the digest rule must be documented in R07 INTEGRATION")

    def setUp(self):
        if self.skip_reason:
            raise unittest.SkipTest(self.skip_reason)

    @classmethod
    def call(cls, case: dict) -> dict:
        graph = build_graph(case)
        try:
            return modrun.call_module(cls.root, TARGET, build_payload(case, graph), graph, timeout=CALL_TIMEOUT)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error_type": "Timeout", "error": f"no answer within {CALL_TIMEOUT}s"}

    @classmethod
    def reply(cls, case_id: str) -> dict:
        if case_id not in cls._replies:
            cls._replies[case_id] = cls.call(CASES[case_id])
        return cls._replies[case_id]

    def evidence(self, reply: dict) -> str:
        return f"[root={self.root} sha={reply.get('root_sha')} module={reply.get('module_file')}]"

    def routes(self, case_id: str) -> dict:
        reply = self.reply(case_id)
        rejected, _crashed, detail = rejection(reply)
        self.assertFalse(rejected, f"{case_id}: valid input rejected: {detail} {self.evidence(reply)}")
        return extract_routes(reply["result"])

    def check_case(self, case_id: str) -> dict:
        """Status/length per plan per pair; reported ok routes must be valid open strict routes."""
        case, states = CASES[case_id], self.routes(case_id)
        graph, ev = build_graph(case), self.evidence(self.reply(case_id))
        for state, entries in case["expected"].items():
            self.assertIn(state, states, f"{case_id}: no '{state}' block in result {ev}")
            got_pairs = {pair_key(o, d) for o, d in states[state]}
            self.assertEqual(got_pairs, set(entries), f"{case_id}/{state}: OD pairs differ {ev}")
            closed = closed_for(case, state)
            for key, exp in entries.items():
                got = states[state][tuple(key.split(">"))]
                where = f"{case_id}/{state}/{key}"
                with self.subTest(pair=where):
                    allowed = {exp["status"], *exp.get("also_acceptable", [])}
                    self.assertIn(got["status"], STATUSES, f"{where}: status outside ok|unreachable|unknown {ev}")
                    self.assertIn(got["status"], allowed,
                                  f"{where}: product said {got['status']} (length {got['length_m']}), "
                                  f"expected {exp['status']} because {exp['derivation']} {ev}")
                    if got["status"] != "ok":
                        self.assertIsNone(got["length_m"], f"{where}: {got['status']} route carries a length "
                                                            f"{got['length_m']!r} (no path must never look like a distance) {ev}")
                        continue
                    self.assertIsInstance(got["length_m"], (int, float), f"{where}: ok without numeric length {ev}")
                    self.assertAlmostEqual(got["length_m"], exp["length_m"], delta=TOL,
                                           msg=f"{where}: product length {got['length_m']}, expected "
                                               f"{exp['length_m']} = {exp['derivation']} {ev}")
                    if got["edge_ids"] is not None:  # tie: validity only, never the exact branch
                        o, d = key.split(">")
                        self.assertEqual(route_problems(graph, o, d, got["edge_ids"], closed, got["length_m"]), [],
                                         f"{where}: reported route {got['edge_ids']} is not a valid open route {ev}")
        for group in case.get("equal_states", []):
            first = {k: (v["status"], v["length_m"]) for k, v in states[group[0]].items()}
            for other in group[1:]:
                self.assertEqual({k: (v["status"], v["length_m"]) for k, v in states[other].items()}, first,
                                 f"{case_id}: plan {other} differs from {group[0]} {ev}")
        return states

    def check_same_result_group(self, cases: list):
        base = self.check_case(cases[0])
        for cid in cases[1:]:
            other = self.check_case(cid)
            for state in base:
                self.assertEqual({k: (v["status"], v["length_m"]) for k, v in other[state].items()},
                                 {k: (v["status"], v["length_m"]) for k, v in base[state].items()},
                                 f"{cid}/{state} differs from {cases[0]}/{state}")

    # -- main path and semantics

    def test_zero_closure_plan_equals_baseline(self):
        """[M01] plan with no closures, and plan whose closure already ended, both equal baseline exactly"""
        self.check_case("g1-zero-closure")

    def test_short_route_closure_detour_and_bridge_unreachable(self):
        """[M01] closing the short route gives the long alternative (+170 m exactly); closing a bridge gives unreachable, not 0"""
        self.check_case("g1-detour")
        self.check_case("g1-bridge")

    def test_tie_asserts_length_only(self):
        """[M01] equal-length alternatives: only the length is asserted; closing one tie branch keeps 550.3 m"""
        self.check_case("g1-tie-branch")

    def test_closure_window_is_half_open(self):
        """[M01] closure is active at start_at (inclusive) and inactive at end_at (exclusive)"""
        self.check_case("g1-window-boundaries")

    def test_same_instant_with_different_offsets_same_routes(self):
        """[M01] analysis_at as +05:00, Z and +06:00 for one instant gives identical routes (absolute-time comparison)"""
        self.check_same_result_group(CASE_OWNERS["test_same_instant_with_different_offsets_same_routes"])

    def test_closure_and_plan_order_do_not_change_routes(self):
        """[M01] permuting closures, edge_ids inside a closure, and plans leaves routes unchanged"""
        self.check_same_result_group(CASE_OWNERS["test_closure_and_plan_order_do_not_change_routes"])

    def test_unknown_access_is_neither_ok_nor_proven_unreachable(self):
        """[M01] strict mode: unknown-access-only target is 'unknown'; unknown shortcut never shortens an ok route; denied never ok"""
        self.check_case("g2-access")
        self.check_case("g2-unknown-closed")

    def test_oneway_direction_is_respected(self):
        """[M01] oneway edge usable only from->to: reverse trip takes the 120/180 m detour; closing o2's exit isolates it"""
        self.check_case("g2-oneway-reverse")
        self.check_case("g2-oneway-forward")

    # -- invalid input

    def test_invalid_inputs_are_rejected_without_crash(self):
        """[M01] unknown edge/node, negative/NaN/Infinity length, city mismatch, stale or wrong digest, duplicate plan ids -> validation error, never a result or crash"""
        for case in ERROR_CASES:
            with self.subTest(case=case["id"]):
                reply = self.reply(case["id"])
                rejected, crashed, detail = rejection(reply)
                self.assertTrue(rejected, f"{case['id']}: invalid input accepted ({case['purpose']}): "
                                          f"{detail} {self.evidence(reply)}")
                self.assertFalse(crashed, f"{case['id']}: crashed instead of a validation error: {detail} "
                                          f"{self.evidence(reply)}")

    # -- reproducibility and honesty of the result

    def test_repeat_call_gives_identical_output(self):
        """[M01] same payload and graph twice (fresh interpreters) -> identical result apart from timing fields"""
        cid = EXPECTED["repeat_case"]["case"]
        first, second = self.reply(cid), self.call(CASES[cid])
        for reply in (first, second):
            self.assertFalse(rejection(reply)[0], f"{cid}: {rejection(reply)[2]} {self.evidence(reply)}")
        extract_routes(first["result"])
        self.assertEqual(strip_volatile(second["result"]), strip_volatile(first["result"]),
                         f"{cid}: two identical calls returned different results {self.evidence(first)}")

    def test_input_objects_not_mutated(self):
        """[M01] compare() must not mutate the caller's payload/graph (needs an in-process run)"""
        raise unittest.SkipTest("NOT_RUN: input mutation is only observable in-process; R10 runs compare() in a "
                                "fresh `python -I` subprocess per call (see test_repeat_call_gives_identical_output)")

    def test_result_echoes_schema_version_input_digest_and_parameters(self):
        """[M01] result carries a civic-scenario schema_version, the graph digest, an input digest that tracks the payload, and analysis_at/mode"""
        cid = EXPECTED["repeat_case"]["case"]
        reply, case = self.reply(cid), CASES[cid]
        extract_routes(reply["result"])
        res, ev = _unwrap(reply["result"]), self.evidence(reply)
        graph = build_graph(case)
        keys = list(walk_keys(res))
        schema = [v for _p, k, v in keys if k.endswith("schema_version") and isinstance(v, str)]
        self.assertTrue(any(v.startswith("civic-scenario") for v in schema),
                        f"no civic-scenario schema_version in result (found {schema}) {ev}")
        values = set(string_values(res))
        self.assertIn(graph["digest"], values, f"graph digest not echoed {ev}")
        self.assertIn("walking", values, f"mode not echoed {ev}")
        at_forms = {case["payload"]["analysis_at"], "2026-10-15T04:00:00Z", "2026-10-15T04:00:00+00:00"}
        self.assertTrue(values & at_forms, f"analysis_at not echoed {ev}")

        def input_digests(result):
            return {p: v for p, _k, v in walk_keys(_unwrap(result))
                    if re.search(r"(input|payload|scenario|request).*digest|digest.*(input|payload)", p, re.I)
                    and isinstance(v, str) and v != graph["digest"]}
        mine = input_digests(res)
        self.assertTrue(mine, f"no input/payload digest key in result {ev}")
        other_reply = self.reply("g1-bridge")
        self.assertFalse(rejection(other_reply)[0], rejection(other_reply)[2])
        other = input_digests(other_reply["result"])
        changed = [p for p in mine if p in other and other[p] != mine[p]]
        self.assertTrue(changed, f"input digest identical for different payloads ({mine} vs {other}) {ev}")

    def test_no_traffic_co2_or_congestion_claims(self):
        """[M01] no result key claims traffic, congestion, CO2, emissions or travel time (contract: length only)"""
        ran = 0
        for case in RESULT_CASES:
            reply = self.reply(case["id"])
            if rejection(reply)[0]:
                continue
            ran += 1
            bad = [p for p, k, _v in walk_keys(_unwrap(reply["result"]))
                   if any(part in k.lower() for part in FORBIDDEN_KEY_PARTS)]
            self.assertEqual(bad, [], f"{case['id']}: forbidden claim keys {bad[:10]} {self.evidence(reply)}")
        self.assertTrue(ran, "no result case produced a result to inspect")


if __name__ == "__main__":
    unittest.main()
