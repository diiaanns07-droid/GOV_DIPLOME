"""Stage 1 tests of plan_oracle (SYNTHETIC inputs, not city data). Run: python3 -m unittest -v test_plan_oracle

Hand-derived example on the meridian lon = 10 (distance = R * dphi exactly, independent of haversine);
u = distance of 0.001 deg latitude. Source S at lat 0. Points P1 lat .010 (w1), P2 lat .020 (w2).
Candidates A lat .012 cost 5, B lat .019 cost 3, C lat .040 cost 1. budget 7, max_selected 2, radius 300 m.
  plan  cost  after(P1,P2)   wsum = 1*P1 + 2*P2   max
  {}     0    10u, 20u       50u                  20u
  C      1    10u, 20u(tie)  50u                  20u   P2 tie C vs S -> nearest stays "source"
  B      3     9u,  1u       11u                   9u
  BC     4     9u,  1u       11u                   9u
  A      5     2u,  8u       18u                   8u
  AC     6     2u,  8u       18u                   8u
  AB     8 > budget 7 -> infeasible
  mean -> B (11u, cost 3 < BC 4); minimax -> A (8u, cost 5 < AC 6);
  coverage (300 m = 2.7u): A covers P1 (w1), B covers P2 (w2) -> B (covered 2, then wsum 11u, cost 3)
  Pareto (cost, wsum): (0, 50u) {}, (3, 11u) B;  C, BC, A, AC dominated.  (u-multiples are exact per point in mm.)
"""
import json, math, unittest
import plan_oracle as O

R = 6371008.8
LON = 10.0


def mm_closed(dlat_deg):                       # closed form on the sphere, independent of haversine
    return math.floor(R * math.radians(abs(dlat_deg)) * 1000 + 0.5)


CTX = {"city_id": "synthetic-meridian", "bbox": [9.99, -0.01, 10.01, 0.05], "source_snapshot": "synthetic-v1",
       "records": [{"id": "S", "lon": LON, "lat": 0.0, "group": "school"},
                   {"id": "X", "lon": LON, "lat": 0.0195, "group": "outpatient_clinic"}]}   # other category, ignored


def cand(cid, lat, cost):
    return {"id": cid, "lon": LON, "lat": lat, "category": "school", "kind": "hypothetical", "cost": cost}


def scenario(**kw):
    sc = {"schema_version": "city-plan-v2", "city_id": "synthetic-meridian", "source_snapshot": "synthetic-v1",
          "category": "school",
          "control_points": [{"id": "P1", "lon": LON, "lat": 0.010, "weight": 1}, {"id": "P2", "lon": LON, "lat": 0.020, "weight": 2}],
          "candidates": [cand("A", 0.012, 5), cand("B", 0.019, 3), cand("C", 0.040, 1)],
          "budget": 7, "max_selected": 2, "coverage_radius_m": 300, "required_ids": [], "excluded_ids": [], "selected_ids": []}
    sc.update(kw)
    return sc


class Distance(unittest.TestCase):
    def test_mm_rounding_and_closed_form(self):
        for k in (1, 2, 8, 9, 10, 20):
            d = O.haversine_m(LON, 0.0, LON, k * 0.001)
            self.assertEqual(O.to_mm(d), mm_closed(k * 0.001))
        self.assertEqual(O.to_mm(0.0), 0)
        self.assertEqual(O.to_mm(0.0004999), 0); self.assertEqual(O.to_mm(0.0005), 1)   # floor(x + 0.5)

    def test_clamp(self):
        self.assertAlmostEqual(O.haversine_m(0, -74.6, 180, 74.6), math.pi * R, delta=1e-6)


class HandExample(unittest.TestCase):
    def setUp(self):
        self.res = O.optimize(CTX, scenario())

    def u(self, k):
        return mm_closed(k * 0.001)

    def test_counts(self):
        self.assertEqual(self.res["status"], "optimal")
        self.assertEqual(self.res["evaluated"], 8)          # 2**3 subsets
        self.assertEqual(self.res["feasible_count"], 6)     # all but AB (cost 8) and ABC (3 > max 2)

    def test_winners(self):
        ob = self.res["objectives"]
        self.assertEqual(ob["mean"]["selected_ids"], ["B"])
        self.assertEqual(ob["minimax"]["selected_ids"], ["A"])
        self.assertEqual(ob["coverage"]["selected_ids"], ["B"])
        m = ob["mean"]["metrics"]
        self.assertEqual(m["weighted_sum_mm"], self.u(9) + 2 * self.u(1))
        self.assertEqual(m["max_mm"], self.u(9))
        self.assertEqual(m["covered_weight"], 2)
        self.assertEqual(ob["minimax"]["metrics"]["max_mm"], self.u(8))

    def test_pareto(self):
        self.assertEqual([(p["cost"], p["weighted_sum_mm"], p["selected_ids"]) for p in self.res["pareto"]],
                         [(0, self.u(10) + 2 * self.u(20), []), (3, self.u(9) + 2 * self.u(1), ["B"])])

    def test_tie_keeps_source(self):
        r = O.evaluate(CTX, scenario(), ["C"])["rows"][1]
        self.assertEqual(r["after_mm"], r["before_mm"]); self.assertEqual(r["nearest"], {"kind": "source", "id": "S"})
        self.assertEqual(r["delta_mm"], 0)

    def test_evaluate_manual_plan_and_feasibility(self):
        e = O.evaluate(CTX, scenario(), ["A", "B"])
        self.assertFalse(e["feasible"]); self.assertEqual(e["reasons"], ["cost_exceeds_budget"])
        self.assertEqual(e["metrics"]["weighted_sum_mm"], self.u(2) + 2 * self.u(1))
        self.assertEqual(e["metrics"]["covered_weight"], 3); self.assertEqual(e["metrics"]["coverage_fraction"], 1.0)
        self.assertEqual(e["metrics"]["weighted_mean_mm"], (self.u(2) + 2 * self.u(1)) / 3)

    def test_no_baseline_unknowns(self):
        ctx = dict(CTX, records=[])
        e = O.evaluate(ctx, scenario(), [])
        self.assertEqual(e["metrics"]["unknown_count"], 2)
        self.assertIsNone(e["metrics"]["max_mm"]); self.assertIsNone(e["metrics"]["weighted_mean_mm"])
        self.assertEqual(e["metrics"]["covered_weight"], 0)
        self.assertTrue(all(r["after_mm"] is None and r["delta_mm"] is None for r in e["rows"]))
        e2 = O.evaluate(ctx, scenario(), ["B"])
        self.assertTrue(all(r["after_mm"] is not None and r["delta_mm"] is None for r in e2["rows"]))  # before=null -> delta=null

    def test_sensitivity_budgets(self):
        s = O.sensitivity(CTX, scenario())
        self.assertEqual([x["budget"] for x in s], [0, 3, 7])
        self.assertEqual(s[0]["objectives"], {"mean": [], "minimax": [], "coverage": []})
        self.assertEqual(s[1]["objectives"]["minimax"], ["B"])


class Digest(unittest.TestCase):
    def test_order_independent_and_selected_excluded(self):
        a = scenario(selected_ids=["A"])
        b = json.loads(json.dumps(a)); b["candidates"].reverse(); b["control_points"].reverse(); b["selected_ids"] = ["B"]
        self.assertEqual(O.problem_digest(CTX, a), O.problem_digest(CTX, b))
        self.assertNotEqual(O.problem_digest(CTX, a, include_selected=True), O.problem_digest(CTX, b, include_selected=True))
        self.assertNotEqual(O.problem_digest(CTX, a), O.problem_digest(CTX, scenario(budget=6)))


class Validation(unittest.TestCase):
    def bad(self, code, **kw):
        with self.assertRaises(O.PlanError) as e:
            O.validate(scenario(**kw), CTX)
        self.assertEqual(e.exception.code, code)

    def test_rejections(self):
        self.bad("bad_version", schema_version="city-whatif-v1")
        self.bad("foreign_city", city_id="astana")
        self.bad("foreign_snapshot", source_snapshot="other")
        self.bad("bad_points", control_points=[])
        self.bad("duplicate_id", candidates=[cand("A", 0.01, 1), cand("A", 0.02, 1)])
        self.bad("outside_bbox", candidates=[cand("A", 0.2, 1)])
        self.bad("out_of_range", budget=1_000_001)
        self.bad("out_of_range", coverage_radius_m=99)
        self.bad("out_of_range", max_selected=6)
        self.bad("unknown_candidate", required_ids=["Z"])
        self.bad("required_excluded_overlap", required_ids=["A"], excluded_ids=["A"])
        self.bad("bad_candidate", candidates=[dict(cand("A", 0.01, 1), kind="source")])
        self.bad("bad_integer", budget=1.5)
        sc = scenario(); sc["url"] = "http://x"
        with self.assertRaises(O.PlanError):
            O.validate(sc, CTX)

    def test_derived_results_allowed_but_ignored(self):
        sc = scenario(derived_results={"objectives": {"mean": {"selected_ids": ["C"]}}})
        self.assertEqual(O.optimize(CTX, sc)["objectives"]["mean"]["selected_ids"], ["B"])

    def test_strict_json(self):
        for text in ('{"a": 1, "a": 2}', '{"a": NaN}', '{"a": Infinity}', '{"a": 1e999}', '{"a": -Infinity}'):
            with self.assertRaises(O.PlanError):
                O.parse_strict(text)
        with self.assertRaises(O.PlanError):
            O.parse_strict("[" + "1," * 140000 + "1]")
        self.assertEqual(O.parse_strict('{"a": 1.5}'), {"a": 1.5})


if __name__ == "__main__":
    unittest.main()
