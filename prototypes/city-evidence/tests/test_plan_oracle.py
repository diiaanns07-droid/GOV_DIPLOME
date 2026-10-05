"""Hand-arithmetic tests of the independent city-plan-v2 oracle (tools/plan_oracle.py); also run by check_all (step tests)."""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import plan_oracle as O  # noqa: E402

DEG_MM = math.floor(2 * math.pi * O.R / 360 * 1000 + 0.5)  # 1 degree of a great circle in mm


def sc(points, cands, budget, max_sel, radius=500, req=(), exc=(), sel=(), cat="school"):
    return O.sc_(points, cands, budget, max_sel, radius, req, exc, sel, cat)


class PlanOracle(unittest.TestCase):
    def test_metric_mm(self):
        self.assertEqual(O.mm((0, 0), (1, 0)), DEG_MM)
        self.assertEqual(DEG_MM, 111195080)
        self.assertEqual(O.mm((5, 5), (5, 5)), 0)

    def test_weighted_metrics_by_hand(self):
        src = [{"id": "s", "group": "school", "lon": 0.0, "lat": 0.0}]
        pts = [O.P(1, 0.001, 0, 2), O.P(2, 0.003, 0, 1)]
        r = O.solve(src, sc(pts, [], 0, 0))["manual"]
        d1, d2 = O.mm((0.001, 0), (0, 0)), O.mm((0.003, 0), (0, 0))
        self.assertEqual(r["weighted_sum_mm"], 2 * d1 + d2)
        self.assertEqual(r["max_mm"], d2)
        self.assertEqual(r["covered_weight"], 3)  # both within 500 m (111 m and 334 m)

    def test_infeasible_reasons(self):
        pts = [O.P(1, 0, 0)]
        c = [O.C("A", 0, 0.001, 10), O.C("B", 0, 0.002, 10)]
        self.assertEqual(O.solve([], sc(pts, c, 5, 2, req=["A"]))["optimize"]["reasons"], ["required_cost_exceeds_budget"])
        self.assertEqual(O.solve([], sc(pts, c, 50, 1, req=["A", "B"]))["optimize"]["reasons"], ["required_exceeds_max_selected"])

    def test_unknown_ranks_before_partial_sum(self):
        # no source records: a plan that leaves a point unknown must lose even with a smaller partial sum
        pts = [O.P(1, 0, 0), O.P(2, 0.05, 0)]
        c = [O.C("Near1", 0, 0.0001, 1), O.C("Mid", 0.025, 0, 1)]
        o = O.solve([], sc(pts, c, 1, 1))["optimize"]
        self.assertEqual(o["objectives"]["mean"]["ids"], ["Mid"])
        self.assertEqual(o["objectives"]["mean"]["unknown_count"], 0)

    def test_equal_pairs_collapse_in_pareto(self):
        pts = [O.P(1, 0, 0)]
        c = [O.C("B", 0, 0.001, 5), O.C("A", 0.001, 0, 5)]  # same distance on the equator, same cost
        o = O.solve([], sc(pts, c, 5, 1))["optimize"]
        self.assertEqual([p["ids"] for p in o["pareto"]], [["A"]])
        self.assertEqual(o["objectives"]["mean"]["ids"], ["A"])

    def test_expected_file_fresh(self):
        fresh = json.dumps(O.build(), ensure_ascii=False, indent=1) + "\n"
        self.assertEqual(O.OUT.read_text(encoding="utf-8"), fresh)


if __name__ == "__main__":
    unittest.main()
