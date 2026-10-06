"""Hand-arithmetic tests of the independent resilience oracle (tools/resilience_oracle.py); run by check_all (step tests)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import resilience_oracle as O  # noqa: E402

SRC = [{"id": "A", "group": "school", "lon": 0.0, "lat": 0.0}, {"id": "B", "group": "school", "lon": 0.02, "lat": 0.0}]


class ResilienceOracle(unittest.TestCase):
    def test_worst_is_lexicographic_max_and_lists_all_ties(self):
        pts = [O.P(1, 0.0, 0.001), O.P(2, 0.02, 0.001)]
        out = O.solve(SRC, O.plan(pts, [], 0, 0), [O.case("a", "x", ["B"]), O.case("b", "y", ["B"])])
        m = out["manual"]
        d_far = O.mm(0.02, 0.001, 0.0, 0.0)  # P2 to A when B is off
        self.assertEqual(m["worst"]["max_mm"], d_far)
        self.assertEqual(m["worst_case_ids"], ["a", "b"])  # duplicate cases both named, result unchanged

    def test_unknown_beats_any_partial_sum(self):
        pts = [O.P(1, 0.0, 0.001)]
        out = O.solve(SRC, O.plan(pts, [O.C("C", 0.09, 0.0, 1)], 1, 1), [O.case("off", "all off", ["A", "B"])])
        o = out["optimize"]
        self.assertEqual(o["robust"]["ids"], ["C"])  # far candidate, but it removes the unknown distance in case "off"
        self.assertEqual(o["nominal"]["ids"], [])    # on the base case it does not help, cost decides
        self.assertIsNotNone(o["price_of_robustness_m"])

    def test_robust_never_worse_in_worst_case(self):
        data = json.loads(O.OUT.read_text(encoding="utf-8"))
        k = lambda w: (w["unknown_count"], w["weighted_sum_mm"], float("inf") if w["max_mm"] is None else w["max_mm"])  # noqa: E731
        for c in data["cases"]:
            o = c["expected"]["optimize"]
            if o["status"] == "optimal":
                self.assertLessEqual(k(o["robust"]["worst"]), k(o["nominal"]["worst"]), c["name"])

    def test_expected_file_fresh(self):
        self.assertEqual(O.OUT.read_text(encoding="utf-8"), json.dumps(O.build(), ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    unittest.main()
