"""K10 round 9: unit tests of k10res.oracle_res on hand-built SYNTHETIC geometry (stdlib unittest).

    python3 -m unittest discover -s tests -p "test_res_oracle.py" -v        # from research/round-9-results/K10

Positions are whole metres east on the equator (lon = x / M, not rounded), so distances are whole millimetres and the
expected values below are derived by hand from research/round-9/CORE_SPEC.txt.
"""
import copy
import json
import math
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from k10res import oracle_res as R  # noqa: E402

M = 2 * math.pi * R.O.R_EARTH_M / 360


def ctx(records):
    return {"city_id": "synthetic-equator", "bbox": [-0.5, -0.5, 0.5, 0.5], "source_snapshot": "synthetic:t", "synthetic": True,
            "records": [{"id": i, "lon": x / M, "lat": 0.0, "group": g} for i, x, g in records]}


def plan(cps, cands, budget=100, max_sel=1, radius=300, sel=(), req=(), exc=()):
    return {"schema_version": "city-plan-v2", "city_id": "synthetic-equator", "source_snapshot": "synthetic:t", "category": "school",
            "control_points": [{"id": i, "lon": x / M, "lat": 0.0, "weight": w} for i, x, w in cps],
            "candidates": [{"id": i, "lon": x / M, "lat": 0.0, "category": "school", "kind": "hypothetical", "cost": c} for i, x, c in cands],
            "budget": budget, "max_selected": max_sel, "coverage_radius_m": radius,
            "required_ids": list(req), "excluded_ids": list(exc), "selected_ids": list(sel)}


def env(p, cases):
    return {"schema_version": "city-resilience-v1", "plan": p,
            "cases": [{"id": i, "label": lab, "disabled_source_ids": list(d)} for i, lab, d in cases]}


def opt(c, e):
    return R.optimize_resilience(c, R.validate_resilience(e, c))


C1 = [("S", 0, "school"), ("far", 20000, "school"), ("K", 500, "outpatient_clinic")]
P1 = [("P1", 0, 2), ("P2", 2000, 1)]
CANDS = [("A", 2000, 1), ("B", 1000, 1)]


class Validation(unittest.TestCase):
    def code(self, e, c=None):
        try:
            R.validate_resilience(e, c or ctx(C1))
            return "accepted"
        except R.ResError as x:
            return x.code

    def test_base_added_and_cases_sorted(self):
        v = R.validate_resilience(env(plan(P1, CANDS), [("z", "z", ["S"]), ("a", "a", ["far", "S"])]), ctx(C1))
        self.assertEqual([c["id"] for c in v["cases"]], ["base", "a", "z"])
        self.assertEqual(v["cases"][0]["disabled_source_ids"], [])
        self.assertEqual(v["cases"][1]["disabled_source_ids"], ["S", "far"])

    def test_refusals(self):
        good = env(plan(P1, CANDS), [("x", "x", ["S"])])
        def mut(fn):
            e = copy.deepcopy(good)
            fn(e)
            return self.code(e)
        self.assertEqual(self.code(good), "accepted")
        self.assertEqual(mut(lambda e: e["plan"].update(derived_results={})), "derived_not_allowed")
        self.assertEqual(mut(lambda e: e.update(extra=1)), "unexpected_field")
        self.assertEqual(mut(lambda e: e["cases"][0].update(id="base")), "reserved_case_id")
        self.assertEqual(mut(lambda e: e["cases"].append(dict(e["cases"][0]))), "duplicate_case_id")
        self.assertEqual(mut(lambda e: e["cases"][0].update(disabled_source_ids=["A"])), "candidate_id_not_source")
        self.assertEqual(mut(lambda e: e["cases"][0].update(disabled_source_ids=["K"])), "unknown_source_id")  # other category
        self.assertEqual(mut(lambda e: e["cases"][0].update(disabled_source_ids=[])), "bad_disabled")
        self.assertEqual(mut(lambda e: e["cases"][0].update(label="ж" * 121)), "bad_label")
        self.assertEqual(mut(lambda e: e["cases"][0].update(label="ж" * 120)), "accepted")
        self.assertEqual(mut(lambda e: e["cases"][0].update(label="a\nb")), "bad_label")
        self.assertEqual(mut(lambda e: e["cases"][0].update(id="café")), "accepted")      # NFC
        self.assertEqual(mut(lambda e: e["cases"][0].update(id="café")), "bad_id")       # not NFC
        self.assertEqual(mut(lambda e: e["cases"][0].update(id="\u1100\u1161")), "bad_id")    # letters only, NFC form is U+AC00
        self.assertEqual(mut(lambda e: e["cases"][0].update(id="\uac00")), "accepted")
        self.assertEqual(mut(lambda e: e["plan"]["control_points"][0].update(id="P 1")), "bad_id")
        self.assertEqual(mut(lambda e: e.update(cases=[dict(e["cases"][0], id=f"k{i}") for i in range(7)])), "accepted")
        self.assertEqual(mut(lambda e: e.update(cases=[dict(e["cases"][0], id=f"k{i}") for i in range(8)])), "bad_case_count")

    def test_candidate_limit_12(self):
        many = [(f"c{i:02d}", 100 * i, 1) for i in range(13)]
        self.assertEqual(self.code(env(plan(P1, many[:12]), [("x", "x", ["S"])])), "accepted")
        self.assertEqual(self.code(env(plan(P1, many), [("x", "x", ["S"])])), "too_many_candidates")


class Compute(unittest.TestCase):
    def test_robust_differs_and_price(self):
        r = opt(ctx(C1), env(plan(P1, CANDS, sel=["A"]), [("noS", "noS", ["S"])]))
        self.assertEqual((r["nominal"]["selected_ids"], r["robust"]["selected_ids"]), (["A"], ["B"]))
        self.assertEqual(r["nominal"]["worst_vector"], [0, 4000000, 2000000])   # without S: 2*2000 + 0
        self.assertEqual(r["robust"]["worst_vector"], [0, 3000000, 1000000])    # without S: 2*1000 + 1000
        self.assertAlmostEqual(r["price_of_robustness_m"], 1000 / 3, places=9)   # B base: (0*2 + 1000)/3 m
        self.assertEqual(r["robust"]["worst_case_ids"], ["noS"])
        self.assertFalse(r["plans_identical"])

    def test_cases_inside_each_case(self):
        e = R.validate_resilience(env(plan(P1, CANDS), [("noS", "noS", ["S"])]), ctx(C1))
        ev = R.evaluate_resilience(ctx(C1), e, [])
        base, nos = ev["per_case"]
        self.assertEqual(base["rows"][0]["nearest_before"], {"kind": "source", "id": "S"})
        self.assertEqual(nos["rows"][0]["nearest_before"], {"kind": "source", "id": "far"})
        self.assertEqual(nos["rows"][0]["before_mm"], 20000000)
        self.assertEqual((base["baseline_records"], nos["baseline_records"]), (2, 1))

    def test_unknown_dominates_and_null_max(self):
        e = R.validate_resilience(env(plan(P1, CANDS, max_sel=0, budget=0), [("none", "none", ["S", "far"])]), ctx(C1))
        ev = R.evaluate_resilience(ctx(C1), e, [])
        self.assertEqual(ev["worst_vector"], [2, 0, None])        # unknown first; null max outside, +inf inside
        self.assertEqual(ev["worst_case_ids"], ["none"])
        self.assertIsNone(ev["per_case"][1]["metrics"]["weighted_mean_mm"])
        self.assertEqual(R.loss(ev["per_case"][1]["metrics"])[2], float("inf"))

    def test_ties_list_all_worst_and_duplicates_do_not_matter(self):
        c = ctx(C1)
        one = opt(c, env(plan(P1, CANDS), [("noS", "noS", ["S"])]))
        two = opt(c, env(plan(P1, CANDS), [("noS", "noS", ["S"]), ("again", "again", ["S"])]))
        self.assertEqual(two["robust"]["worst_case_ids"], ["again", "noS"])
        for k in ("nominal", "robust"):
            self.assertEqual(one[k]["selected_ids"], two[k]["selected_ids"])
            self.assertEqual(one[k]["worst_vector"], two[k]["worst_vector"])
        self.assertEqual(one["price_of_robustness_m"], two["price_of_robustness_m"])

    def test_tie_breaks_base_then_cost_then_ids(self):
        # far-only case makes every plan's worst equal at P1/P2 -> W ties; base loss then cost then ids decide
        c = ctx([("S", 0, "school"), ("T", 0, "school")])
        p = plan([("P1", 0, 1)], [("b", 0, 2), ("a", 0, 2), ("cheap", 0, 1)], budget=10)
        r = opt(c, env(p, [("noS", "noS", ["S"])]))  # T still at 0: W = L_base = (0,0,0) for every plan
        self.assertEqual(r["robust"]["selected_ids"], [])           # cost 0 wins
        p2 = plan([("P1", 0, 1)], [("b", 0, 2), ("a", 0, 2)], budget=10, req=[])
        r2 = opt(ctx([("S", 5000, "school")]), env(p2, [("noS", "noS", ["S"])]))
        self.assertEqual(r2["robust"]["selected_ids"], ["a"])      # equal W, base, cost -> smaller id

    def test_robust_uses_base_after_worst(self):
        # a (cost 1) and b (cost 5) have the same worst vector; b has the better base loss and must win before cost
        c = ctx([("S", 0, "school"), ("F", 20000, "school")])
        p = plan([("P1", 0, 1), ("P2", 4000, 1)], [("a", 1000, 1), ("b", 3000, 5)], budget=10)
        r = opt(c, env(p, [("noS", "noS", ["S"])]))
        # a: base 0+3000, noS 1000+3000 ; b: base 0+1000, noS 3000+1000 -> W equal (0, 4000000, 3000000)
        self.assertEqual(r["robust"]["selected_ids"], ["b"])
        self.assertEqual(r["robust"]["worst_vector"], [0, 4000000, 3000000])
        ev_a = R.evaluate_resilience(c, R.validate_resilience(env(p, [("noS", "noS", ["S"])]), c), ["a"])
        self.assertEqual(ev_a["worst_vector"], [0, 4000000, 3000000])

    def test_infeasible_and_price_null(self):
        r = opt(ctx(C1), env(plan(P1, CANDS, budget=0, req=["A"]), [("noS", "noS", ["S"])]))
        self.assertEqual((r["status"], r["infeasible_reasons"]), ("infeasible", ["required_cost_exceeds_budget"]))
        self.assertIsNone(r["price_of_robustness_m"])
        self.assertIsNotNone(r["price_reason"])
        self.assertIsNone(r["robust"])

    def test_identical_plans_price_zero(self):
        r = opt(ctx(C1), env(plan(P1, CANDS), [("nofar", "nofar", ["far"])]))
        self.assertTrue(r["plans_identical"])
        self.assertEqual(r["price_of_robustness_m"], 0.0)
        self.assertEqual(r["robust"]["worst_case_ids"], ["base", "nofar"])

    def test_digests(self):
        c = ctx(C1)
        e1 = env(plan(P1, CANDS, sel=["A"]), [("a", "A", ["S", "far"]), ("b", "B", ["S"])])
        e2 = copy.deepcopy(e1)
        e2["cases"].reverse()
        e2["cases"][1]["disabled_source_ids"].reverse()
        v1, v2 = R.validate_resilience(e1, c), R.validate_resilience(e2, c)
        self.assertEqual(R.resilience_problem_digest(v1), R.resilience_problem_digest(v2))
        e3 = copy.deepcopy(e1)
        e3["plan"]["selected_ids"] = []
        v3 = R.validate_resilience(e3, c)
        self.assertEqual(R.resilience_problem_digest(v1), R.resilience_problem_digest(v3))
        self.assertNotEqual(R.resilience_scenario_digest(v1), R.resilience_scenario_digest(v3))
        for fn in (lambda e: e["cases"][0].update(label="A2"), lambda e: e["cases"][1].update(disabled_source_ids=["far"])):
            e4 = copy.deepcopy(e1)
            fn(e4)
            self.assertNotEqual(R.resilience_problem_digest(v1), R.resilience_problem_digest(R.validate_resilience(e4, c)))
        self.assertEqual(R.optimize_resilience(c, v1), R.optimize_resilience(c, v2))

    def test_no_mutation_and_limit_speed(self):
        c = ctx(C1)
        cands = [(f"c{i:02d}", 150 * i, 1 + i) for i in range(12)]
        e = env(plan(P1 + [("P3", 900, 3)], cands, budget=1000, max_sel=5), [(f"k{i}", "k", ["S"] if i % 2 else ["far"]) for i in range(7)])
        c0, e0 = json.dumps(c, sort_keys=True), json.dumps(e, sort_keys=True)
        t = time.time()
        r = opt(c, e)
        self.assertLess(time.time() - t, 30)
        self.assertEqual(r["evaluated"], sum(math.comb(12, k) for k in range(6)))   # 1586 <= 4096
        self.assertEqual((json.dumps(c, sort_keys=True), json.dumps(e, sort_keys=True)), (c0, e0))


if __name__ == "__main__":
    unittest.main()
