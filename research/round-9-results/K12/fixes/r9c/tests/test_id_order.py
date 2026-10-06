"""The Python oracles order IDs like plan.js / resilience.js (JavaScript strings: UTF-16 code units), so the JS code and
the oracles agree at exact ties. K12 r9: with IDs U+FB00 (ﬀ) and U+1D538 (𝔸) Python sorted() picks ﬀ, JavaScript picks 𝔸.
Usage: python3 -m unittest tests.test_id_order"""
import importlib.util
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(f"k12_{name}", APP / "tools" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A, B = "ﬀ", "\U0001d538"
EQ = [{"id": "A", "group": "school", "lon": 0.0, "lat": 0.0}, {"id": "B", "group": "school", "lon": 0.02, "lat": 0.0}]


def plan():
    cand = lambda i: {"id": i, "lon": 0.0005, "lat": 0.0005, "category": "school", "kind": "hypothetical", "cost": 5}  # noqa: E731
    return {"schema_version": "city-plan-v2", "category": "school", "control_points": [{"id": "P1", "lon": 0.0, "lat": 0.001, "weight": 1}],
            "candidates": [cand(A), cand(B)], "budget": 5, "max_selected": 1, "coverage_radius_m": 500,
            "required_ids": [], "excluded_ids": [], "selected_ids": []}


class IdOrder(unittest.TestCase):
    def test_plan_oracle_tie_uses_utf16_order(self):
        r = load("plan_oracle").solve(EQ, plan())
        self.assertEqual(r["optimize"]["objectives"]["mean"]["ids"], [B])

    def test_resilience_oracle_tie_uses_utf16_order(self):
        cases = [{"id": A + "1", "label": "x", "disabled_source_ids": ["A", "B"]}, {"id": B + "1", "label": "y", "disabled_source_ids": ["A", "B"]}]
        r = load("resilience_oracle").solve(EQ, plan(), cases)["optimize"]
        self.assertEqual((r["nominal"]["ids"], r["robust"]["ids"]), ([B], [B]))
        w = r["robust"]["worst_case_ids"]
        self.assertEqual(w, sorted(w, key=lambda s: s.encode("utf-16-be")))


if __name__ == "__main__":
    unittest.main()
