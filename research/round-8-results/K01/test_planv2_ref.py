"""Python oracle self-tests (stdlib unittest): python3 -m unittest test_planv2_ref -v"""
import json, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planv2_ref as R  # noqa: E402

FX = HERE / "fixtures"
CTX = {c: json.loads((FX / "real" / f"context_{c}.json").read_text(encoding="utf-8")) for c in ("shymkent", "astana")}


class Oracle(unittest.TestCase):
    def test_expected_fixtures(self):
        exp = json.loads((FX / "EXPECTED.json").read_text(encoding="utf-8"))["fixtures"]
        for name, e in exp.items():
            with self.subTest(name):
                try:
                    R.import_plan((FX / "synthetic" / name).read_bytes(), CTX[e["context_city"]]); got = (True, None)
                except R.PlanError as err:
                    got = (False, err.code)
                self.assertEqual(got, (e["valid"], e.get("code")))

    def test_v1_files_rejected_by_v2(self):
        for c in ("shymkent", "astana"):
            with self.assertRaises(R.PlanError) as cm:
                R.import_plan((FX / "v1" / f"{c}_v1_from_build_whatif.json").read_bytes(), CTX[c])
            self.assertEqual(cm.exception.code, "unknown_field")

    def test_schema_file_is_strict(self):
        s = R.SCHEMA_DOC
        self.assertFalse(s["additionalProperties"])
        self.assertFalse(s["$defs"]["control_point"]["additionalProperties"])
        self.assertFalse(s["$defs"]["candidate"]["additionalProperties"])
        self.assertEqual(s["$defs"]["candidate"]["properties"]["kind"], {"const": "hypothetical"})

    def test_digest_order_independent_and_selected_excluded_from_problem(self):
        sc, _ = R.import_plan((FX / "synthetic" / "shy_valid_clinic_constraints.json").read_bytes(), CTX["shymkent"])
        sc2 = dict(sc, control_points=sc["control_points"][::-1], candidates=sc["candidates"][::-1], selected_ids=sc["selected_ids"][::-1])
        self.assertEqual(R.problem_digest(sc), R.problem_digest(sc2)); self.assertEqual(R.scenario_digest(sc), R.scenario_digest(sc2))
        sc3 = dict(sc, selected_ids=[])
        self.assertEqual(R.problem_digest(sc), R.problem_digest(sc3)); self.assertNotEqual(R.scenario_digest(sc), R.scenario_digest(sc3))
        self.assertNotEqual(R.problem_digest(sc), R.problem_digest(dict(sc, budget=sc["budget"] + 1)))

    def test_canonical_rejects_exponent_floats(self):
        with self.assertRaises(ValueError):
            R._canon([1e-7])


if __name__ == "__main__":
    unittest.main(verbosity=2)
