"""K12 round 4 REVIEW: tests over FIXTURES.json (SYNTHETIC) for the K05 data model.

CurrentK05 — code of claude/optimistic-davinci-1oiqs9 @ d913554 (copied to inputs/): controls must
pass; the reviewed defects are expectedFailure (an "unexpected success" means K05 fixed one).
PatchedK05 — patched/ (= d913554 + patches/k05r3_contract_stress_fixes.patch): every case passes.

Run from research/round-4-results/K12/:  python -m unittest discover -s tests -v
jsonschema is optional (the contract layer alone decides every case in FIXTURES.json).
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

K12 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K12))
import stress_runner as R  # noqa: E402

FX = R.decode(json.loads((K12 / "FIXTURES.json").read_text(encoding="utf-8")))
KNOWN_DEFECTS = {
    "R20", "R21", "R22", "R23",          # NaN / ±Infinity accepted as values
    "R25", "R26", "R27", "R28",          # impossible period dates, reversed interval
    "R30", "R31",                        # negative / fractional count
    "R33",                               # retrieved_at not a timestamp
    "J01", "J02", "J03", "J04", "J05",   # lenient JSON loading
    "A07", "A08", "A09", "A10", "A11", "A12",  # aggregate_sum gaps
    "S01", "S02", "S03",                 # no dataset-level duplicate check
}


def results(impl):
    C, schema = R.load_impl(K12 / impl)
    out = {}
    for c in (R.run_records(C, schema, FX) + R.run_json_text(C, FX)
              + R.run_aggregate(C, FX) + R.run_datasets(C, FX)):
        out[c["id"]] = c
    return out


CURRENT = results("inputs/k05_d913554")
PATCHED = results("patched")


class CurrentK05(unittest.TestCase):
    """Текущий код K05: контроли проходят, известные дефекты — expectedFailure."""


class PatchedK05(unittest.TestCase):
    """Исправленная копия: проходят все случаи."""


def _make(res, cid):
    def test(self):
        self.assertTrue(res[cid]["match"], json.dumps(res[cid], ensure_ascii=False, default=str)[:600])
    return test


for _cid in sorted(CURRENT):
    t = _make(CURRENT, _cid)
    setattr(CurrentK05, f"test_{_cid}", unittest.expectedFailure(t) if _cid in KNOWN_DEFECTS else t)
    setattr(PatchedK05, f"test_{_cid}", _make(PATCHED, _cid))


class Meta(unittest.TestCase):
    def test_defect_list_is_exact(self):
        self.assertEqual({c for c, r in CURRENT.items() if not r["match"]}, KNOWN_DEFECTS)

    def test_every_defect_case_is_marked_new(self):
        sections = FX["record_cases"] + FX["json_text_cases"] + FX["aggregate_cases"] + FX["dataset_cases"]
        new = {c["id"] for c in sections if c.get("new_vs_k05_tests")}
        self.assertEqual(KNOWN_DEFECTS - new, set())

    def test_fixtures_are_labelled_synthetic(self):
        self.assertEqual(FX["kind"], "synthetic")
        self.assertIn("СИНТЕТИКА", FX["notice"])
        for base in FX["bases"].values():
            self.assertTrue(base["obs_id"].startswith("SYNTHETIC-FIXTURE"))
            self.assertTrue(base["note"].startswith("SYNTHETIC"))
            self.assertEqual(base["source"]["source_id"], "k12r4-synthetic-fixture")
        for case in FX["aggregate_cases"]:
            for r in case["records"]:
                self.assertTrue(r["obs_id"].startswith("SYNTHETIC-FIXTURE"))
                unit = r["geo_unit_id"].split(".")
                self.assertTrue(len(unit) == 2 or unit[2].startswith("fixture_"), r["geo_unit_id"])

    def test_inputs_match_manifest(self):
        root = K12 / "inputs/k05_d913554"
        man = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(man["source_commit"], "d913554bf2617a74d921af260ab8c22743ccb4b5")
        for rel, meta in man["files"].items():
            self.assertEqual(hashlib.sha256((root / rel).read_bytes()).hexdigest(), meta["sha256"], rel)

    def test_patched_copy_differs_only_in_contract(self):
        for rel in ("round-3-results/K05/schema/k05-obs-v1.1.schema.json", "next-round/K05/k05_validator.py"):
            self.assertEqual((K12 / "inputs/k05_d913554" / rel).read_bytes(), (K12 / "patched" / rel).read_bytes(), rel)


if __name__ == "__main__":
    unittest.main()
