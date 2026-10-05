"""K10 round 8: unit tests of k10plan.oracle on hand-built SYNTHETIC geometry (stdlib unittest).

    python3 -m unittest discover -s tests -p "test_*.py" -v      # from research/round-8-results/K10

Expected values are derived by hand from CORE_SPEC, not copied from oracle output.
Geometry: points on the equator; x metres east = x / M lon degrees, M = 2*pi*R/360.
"""
import copy
import json
import math
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from k10plan import oracle as O  # noqa: E402

M = 2 * math.pi * O.R_EARTH_M / 360


def x(m):
    return m / M


def ctx(records=()):
    return {"city_id": "synthetic-equator", "bbox": [-0.5, -0.5, 0.5, 0.5], "source_snapshot": "synthetic:test",
            "synthetic": True, "records": [{"id": i, "lon": x(xm), "lat": 0.0, "group": g} for i, xm, g in records]}


def scen(cps, cands, budget=1000, max_sel=5, radius=500, req=(), exc=(), sel=(), cat="school"):
    return {"schema_version": "city-plan-v2", "city_id": "synthetic-equator", "source_snapshot": "synthetic:test",
            "category": cat, "control_points": [{"id": i, "lon": x(xm), "lat": 0.0, "weight": w} for i, xm, w in cps],
            "candidates": [{"id": i, "lon": x(xm), "lat": 0.0, "category": cat, "kind": "hypothetical", "cost": c}
                           for i, xm, c in cands],
            "budget": budget, "max_selected": max_sel, "coverage_radius_m": radius,
            "required_ids": list(req), "excluded_ids": list(exc), "selected_ids": list(sel)}


def run(c, s, opts=None):
    return O.optimize_plans(c, O.validate_plan_scenario(s, c), opts)


def ev(c, s, ids):
    return O.evaluate_plan(c, O.validate_plan_scenario(s, c), ids)


class Geometry(unittest.TestCase):
    def test_one_degree_on_equator(self):
        d = O.haversine_m(0, 0, 1, 0)
        self.assertAlmostEqual(d, 111195.0802335, places=6)
        self.assertEqual(O.to_mm(d), 111195080)

    def test_antipodes_clamped_finite(self):
        self.assertAlmostEqual(O.haversine_m(0, 0, 180, 0), math.pi * O.R_EARTH_M, places=6)
        # (0, 0.08) - (180, -0.08): the intermediate value is 1.0000000000000002 before the clamp
        self.assertAlmostEqual(O.haversine_m(0, 0.08, 180, -0.08), math.pi * O.R_EARTH_M, places=6)

    def test_mm_rounding_half_up(self):
        self.assertEqual(O.to_mm(0.0005), 1)
        self.assertEqual(O.to_mm(0.0004999), 0)
        self.assertEqual(O.to_mm(0.0), 0)


class StrictJson(unittest.TestCase):
    def code(self, text):
        try:
            O.parse_strict(text)
            return "accepted"
        except O.PlanError as e:
            return e.code

    def test_rejections(self):
        self.assertEqual(self.code('{"a":1,"a":2}'), "duplicate_key")
        self.assertEqual(self.code('{"a":{"b":1,"b":1}}'), "duplicate_key")
        for t in ('{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e999}', '{"a":-1e999}', '{"a":1' + "0" * 400 + "}"):
            self.assertEqual(self.code(t), "non_finite", t[:20])
        self.assertEqual(self.code('{"a":1} x'), "bad_json")
        self.assertEqual(self.code('{"a":1,}'), "bad_json")
        self.assertEqual(self.code('{"a":"' + "x" * (256 * 1024) + '"}'), "too_large")
        self.assertEqual(self.code('{"a":1.5e3,"b":[1,2]}'), "accepted")


class Validation(unittest.TestCase):
    def setUp(self):
        self.c = ctx([("s1", 0, "school")])
        self.s = scen([("P1", 100, 1)], [("a", 200, 5), ("b", 300, 5)])

    def code(self, s):
        try:
            O.validate_plan_scenario(s, self.c)
            return "accepted"
        except O.PlanError as e:
            return e.code

    def test_good_and_derived_results_ignored(self):
        s = copy.deepcopy(self.s)
        s["derived_results"] = {"objectives": {"mean": {"selected_ids": ["b"], "weighted_sum_mm": -1}}}
        v = O.validate_plan_scenario(s, self.c)
        self.assertNotIn("derived_results", v)
        self.assertEqual(run(self.c, s)["objectives"]["mean"]["selected_ids"], [])  # recomputed, forged value ignored

    def test_rejections(self):
        def mut(fn):
            s = copy.deepcopy(self.s)
            fn(s)
            return self.code(s)
        self.assertEqual(mut(lambda s: s.update(required_ids=["a"], excluded_ids=["a"])), "required_excluded_overlap")
        self.assertEqual(mut(lambda s: s.update(selected_ids=["s1"])), "unknown_candidate")  # source id is not a candidate
        self.assertEqual(mut(lambda s: s.update(extra=1)), "unexpected_field")
        self.assertEqual(mut(lambda s: s.update(source_snapshot="sha256:other")), "foreign_snapshot")
        self.assertEqual(mut(lambda s: s.update(city_id="astana")), "bad_city")
        self.assertEqual(mut(lambda s: s["control_points"][0].update(lon=0.6)), "out_of_bbox")
        self.assertEqual(mut(lambda s: s["control_points"][0].update(weight=True)), "bad_value")
        self.assertEqual(mut(lambda s: s["candidates"][0].update(kind="source")), "candidate_not_hypothetical")
        self.assertEqual(mut(lambda s: s.update(max_selected=6)), "bad_value")
        real = dict(self.c, synthetic=False)
        with self.assertRaises(O.PlanError) as e:
            O.validate_plan_scenario(self.s, real)
        self.assertEqual(e.exception.code, "bad_city")  # synthetic city ids only with a synthetic context

    def test_id_lists_sorted(self):
        s = copy.deepcopy(self.s)
        s["selected_ids"] = ["b", "a"]
        self.assertEqual(O.validate_plan_scenario(s, self.c)["selected_ids"], ["a", "b"])


class Evaluate(unittest.TestCase):
    def test_empty_baseline_unknown_and_null_delta(self):
        c = ctx([("o1", 0, "outpatient_clinic")])
        s = scen([("P1", 0, 2), ("P2", 1000, 3)], [("a", 600, 1)])
        r = ev(c, s, [])
        self.assertEqual([row["after_mm"] for row in r["rows"]], [None, None])
        m = r["metrics"]
        self.assertEqual((m["unknown_count"], m["weighted_sum_mm"], m["weighted_mean_mm"], m["max_mm"], m["covered_weight"],
                          m["coverage_fraction"]), (2, 0, None, None, 0, 0.0))
        r = ev(c, s, ["a"])
        self.assertEqual([row["delta_mm"] for row in r["rows"]], [None, None])  # before=null -> delta=null
        self.assertEqual([row["after_mm"] for row in r["rows"]], [600000, 400000])
        self.assertEqual(r["metrics"]["weighted_sum_mm"], 2 * 600000 + 3 * 400000)
        self.assertEqual(r["metrics"]["covered_weight"], 3)  # 400 m <= 500 m

    def test_ties_source_first_then_smaller_id(self):
        c = ctx([("s2", 0, "school"), ("s1", 0, "school")])
        s = scen([("P1", 0, 1)], [("a", 0, 1)])
        row = ev(c, s, ["a"])["rows"][0]
        self.assertEqual(row["nearest_before"], {"kind": "source", "id": "s1"})
        self.assertEqual(row["nearest_after"], {"kind": "source", "id": "s1"})
        self.assertEqual(row["delta_mm"], 0)

    def test_delta_and_hypothetical_ref(self):
        c = ctx([("s1", 0, "school")])
        s = scen([("P1", 1000, 1)], [("a", 900, 1)])
        row = ev(c, s, ["a"])["rows"][0]
        self.assertEqual((row["before_mm"], row["after_mm"], row["delta_mm"]), (1000000, 100000, 900000))
        self.assertEqual(row["nearest_after"], {"kind": "hypothetical", "id": "a"})

    def test_radius_boundary_inclusive(self):
        c = ctx([])
        s = scen([("P1", 0, 1)], [("a", 400, 1)], radius=400)
        r = ev(c, s, ["a"])
        self.assertEqual(r["rows"][0]["after_mm"], 400000)
        self.assertEqual(r["metrics"]["covered_weight"], 1)

    def test_feasibility_reasons(self):
        c = ctx([])
        s = scen([("P1", 0, 1)], [("a", 0, 7), ("b", 0, 7)], budget=10, max_sel=1, req=["a"], exc=["b"])
        f = ev(c, s, ["b"])["feasibility"]
        self.assertEqual(f, {"feasible": False, "reasons": ["required_missing", "excluded_selected"]})
        f = ev(c, s, ["a", "b"])["feasibility"]
        self.assertEqual(f["reasons"], ["count_exceeds_max_selected", "cost_exceeds_budget", "excluded_selected"])


class Search(unittest.TestCase):
    def test_three_objectives_differ(self):
        # P1 0 m w5, P2 1000 m w4, P3 1500 m w4, P4 5000 m w1; radius 300; one candidate
        c = ctx([("src", 20000, "school")])
        s = scen([("P1", 0, 5), ("P2", 1000, 4), ("P3", 1500, 4), ("P4", 5000, 1)],
                 [("a", 0, 1), ("b", 1250, 2), ("c", 2500, 3), ("e", 1000, 4)], budget=10, max_sel=1, radius=300)
        o = run(c, s)["objectives"]
        self.assertEqual(o["mean"]["selected_ids"], ["e"])       # sum 5*1000+0+4*500+4000 = 11000 m
        self.assertEqual(o["minimax"]["selected_ids"], ["c"])    # worst point 2500 m
        self.assertEqual(o["coverage"]["selected_ids"], ["b"])   # P2+P3 within 300 m: weight 8
        self.assertEqual(o["coverage"]["covered_weight"], 8)

    def test_unknown_count_compared_before_sum(self):
        c = ctx([])
        s = scen([("P1", 0, 1), ("P2", 100, 1)], [("far", 40000, 1)], budget=1)
        o = run(c, s)["objectives"]
        for k in ("mean", "minimax", "coverage"):
            self.assertEqual(o[k]["selected_ids"], ["far"], k)  # empty plan has wsum 0 but unknown_count 2

    def test_cost_then_ids_break_ties(self):
        c = ctx([("s", 0, "school")])
        s = scen([("P1", 1000, 1)], [("b", 0, 3), ("a", 0, 3), ("cheap", 0, 1)], budget=10, max_sel=1)
        o = run(c, s)["objectives"]
        self.assertEqual(o["mean"]["selected_ids"], [])  # nothing beats the source at 1000 m; empty plan costs 0
        s = scen([("P1", 2000, 1)], [("b", 1000, 3), ("a", 1000, 3)], budget=10, max_sel=1)
        o = run(c, s)["objectives"]
        self.assertEqual(o["mean"]["selected_ids"], ["a"])  # equal metrics and cost -> smaller id

    def test_key_order_prefix_first(self):
        base = {"unknown_count": 0, "weighted_sum_mm": 5, "max_mm": 5, "covered_weight": 0, "cost": 2}
        k1 = O._keys(dict(base, selected_ids=["a"]))["mean"]
        k2 = O._keys(dict(base, selected_ids=["a", "b"]))["mean"]
        self.assertLess(k1, k2)
        k3 = O._keys(dict(base, max_mm=None, unknown_count=0, selected_ids=[]))["minimax"]
        self.assertEqual(k3[1], float("inf"))

    def test_infeasible_reasons(self):
        c = ctx([])
        s = scen([("P1", 0, 1)], [("a", 0, 5), ("b", 0, 5), ("c", 0, 5)], budget=9, max_sel=1, req=["a", "b"])
        r = run(c, s)
        self.assertEqual(r["status"], "infeasible")
        self.assertEqual(r["infeasible_reasons"], ["required_count_exceeds_max_selected", "required_cost_exceeds_budget"])
        self.assertIsNone(r["objectives"])
        self.assertEqual(r["pareto"], [])

    def test_empty_plan_and_sensitivity_budgets(self):
        c = ctx([("s", 0, "school")])
        s = scen([("P1", 1000, 1)], [("a", 1000, 3)], budget=1, max_sel=1)
        r = run(c, s)
        self.assertEqual(r["status"], "optimal")
        self.assertEqual(r["objectives"]["mean"]["selected_ids"], [])
        self.assertEqual([q["budget"] for q in r["sensitivity"]], [0, 1])  # [0, floor(1/2)=0, 1] without duplicates
        s["budget"] = 0
        self.assertEqual([q["budget"] for q in run(c, s)["sensitivity"]], [0])

    def test_evaluated_counts(self):
        c = ctx([("s", 0, "school")])
        cands = [(f"k{i:02d}", 100 * i, 1) for i in range(16)]
        s = scen([("P1", 50, 1)], cands, budget=1000000, max_sel=5)
        t = time.time()
        r = run(c, s, {"sensitivity": False})
        self.assertEqual(r["evaluated"], sum(math.comb(16, k) for k in range(6)))  # 6885
        self.assertLess(time.time() - t, 30)
        s = scen([("P1", 50, 1)], cands, budget=1000000, max_sel=3, req=["k00"], exc=["k01", "k02"])
        self.assertEqual(run(c, s, {"sensitivity": False})["evaluated"], sum(math.comb(13, k) for k in range(3)))
        s = scen([("P1", 50, 1)], cands, max_sel=0)
        r = run(c, s, {"sensitivity": False})
        self.assertEqual((r["evaluated"], r["objectives"]["mean"]["selected_ids"]), (1, []))

    def test_pareto_dominance_and_collapse(self):
        c = ctx([("s", 0, "school")])
        s = scen([("P1", 3000, 1)], [("t2", 3000, 50), ("t1", 3000, 50), ("u", 0, 10), ("v", 2000, 60)],
                 budget=100, max_sel=1)
        p = run(c, s)["pareto"]
        self.assertEqual([(q["cost"], q["weighted_sum_mm"], q["selected_ids"]) for q in p],
                         [(0, 3000000, []), (50, 0, ["t1"])])  # u dominated by empty plan, v by t1, t2 collapsed

    def test_pareto_skips_unknown(self):
        c = ctx([])
        s = scen([("P1", 0, 1)], [("a", 100, 5)], budget=10)
        r = run(c, s)
        self.assertEqual([q["selected_ids"] for q in r["pareto"]], [["a"]])
        self.assertIsNotNone(r["pareto_note"])

    def test_digest_order_independent(self):
        c = ctx([("s", 0, "school")])
        s1 = scen([("P1", 0, 1), ("P2", 500, 2)], [("a", 100, 5), ("b", 200, 6)], req=["a"], sel=["a", "b"])
        s2 = copy.deepcopy(s1)
        s2["control_points"].reverse()
        s2["candidates"].reverse()
        s2["selected_ids"] = ["b", "a"]
        v1, v2 = O.validate_plan_scenario(s1, c), O.validate_plan_scenario(s2, c)
        self.assertEqual(O.problem_digest(v1), O.problem_digest(v2))
        self.assertEqual(O.scenario_digest(v1), O.scenario_digest(v2))
        s3 = copy.deepcopy(s1)
        s3["selected_ids"] = []
        v3 = O.validate_plan_scenario(s3, c)
        self.assertEqual(O.problem_digest(v1), O.problem_digest(v3))   # selected_ids not in problem_digest
        self.assertNotEqual(O.scenario_digest(v1), O.scenario_digest(v3))
        s4 = copy.deepcopy(s1)
        s4["control_points"][0]["weight"] = 3
        self.assertNotEqual(O.problem_digest(v1), O.problem_digest(O.validate_plan_scenario(s4, c)))
        self.assertEqual(run(c, s1), run(c, s2))

    def test_inputs_not_mutated(self):
        c = ctx([("s", 0, "school")])
        s = scen([("P1", 0, 1)], [("a", 100, 5)], sel=["a"])
        c0, s0 = json.dumps(c, sort_keys=True), json.dumps(s, sort_keys=True)
        v = O.validate_plan_scenario(s, c)
        O.optimize_plans(c, v)
        O.evaluate_plan(c, v, ["a"])
        self.assertEqual((json.dumps(c, sort_keys=True), json.dumps(s, sort_keys=True)), (c0, s0))


if __name__ == "__main__":
    unittest.main()
