"""Генератор протокола T3: число задач, детерминизм, парность геометрии, правила семейств исключений."""
import json, sys, unittest
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09res import t3 as T, resilience as RS  # noqa: E402
from k09plan import data, suite  # noqa: E402

CFG = json.loads((K / "config/t3_config.json").read_text(encoding="utf-8"))
ATTR = json.loads((K / "config/t3_attribute_sets.json").read_text(encoding="utf-8"))["slices"]
D, SHA = data.load_slice(repo=str(K.parents[2]), sha=CFG["data_build_sha"])
CTX = {s["id"]: suite.make_context(D, SHA, s["city"], s["category"], "real_slice_records") for s in CFG["slices"]}


class TestT3(unittest.TestCase):
    def test_counts(self):
        plan = T.task_plan(CFG, ATTR)
        self.assertEqual(len(plan), CFG["task_counts"]["total"])
        self.assertEqual(len(set(plan)), len(plan))
        self.assertEqual(sum(1 for p in plan if p[0] == "stress"), CFG["task_counts"]["stress"])
        self.assertEqual(sum(1 for p in plan if p[3] == "attribute"), CFG["task_counts"]["attribute"])

    def test_paired_geometry_and_limits(self):
        ctx = CTX["astana_clinic"]
        a = T.make_env(ctx, CFG, "L", 1.0, 3, 4, [{"id": "x", "label": "x", "disabled_source_ids": [ctx["sources"][0]["id"]]}])
        b = T.make_env(ctx, CFG, "S", 0.5, 3, 4, [{"id": "y", "label": "y", "disabled_source_ids": [ctx["sources"][1]["id"]]}])
        self.assertEqual(a["plan"]["control_points"][:5], b["plan"]["control_points"])
        self.assertEqual(a["plan"]["candidates"][:4], b["plan"]["candidates"])
        self.assertEqual(len(a["plan"]["candidates"]), 12)
        RS.validate_resilience(a, ctx); RS.validate_resilience(b, ctx)

    def test_families(self):
        ctx = CTX["shymkent_school"]
        s7 = T.exclusion_cases(ctx, CFG, "single", 7, 0, ATTR["shymkent_school"]["cases"])
        self.assertEqual(len({c["disabled_source_ids"][0] for c in s7}), 7)
        p3 = T.exclusion_cases(ctx, CFG, "pair", 3, 0, [])
        self.assertTrue(all(len(set(c["disabled_source_ids"])) == 2 for c in p3))
        c3 = T.exclusion_cases(ctx, CFG, "cluster", 3, 0, [])
        self.assertTrue(all(len(c["disabled_source_ids"]) == 3 for c in c3))
        self.assertEqual(c3, T.exclusion_cases(ctx, CFG, "cluster", 3, 0, []))
        al = T.exclusion_cases(ctx, CFG, "all_disabled", 1, 0, [])
        self.assertEqual(len(al[0]["disabled_source_ids"]), 15)
        at = T.exclusion_cases(ctx, CFG, "attribute", 3, 0, ATTR["shymkent_school"]["cases"])
        self.assertEqual([c["id"] for c in at], ["low_confidence", "qa_flagged", "low_or_qa"])
        self.assertEqual([c["id"] for c in ATTR["astana_clinic"]["cases"]], ["low_confidence"])

    def test_run_one_smoke(self):
        spec = ("main", "shymkent_school", "S", "cluster", 3, 1.0, 3, 0)
        row, t = T.run_one(CTX["shymkent_school"], CFG, ATTR, spec)
        row2, _ = T.run_one(CTX["shymkent_school"], CFG, ATTR, spec)
        self.assertEqual(row, row2); self.assertEqual(row["status"], "optimal"); self.assertEqual(row["k_cases"], 3)
        row3, _ = T.run_one(CTX["astana_clinic"], CFG, ATTR, ("main", "astana_clinic", "S", "all_disabled", 1, 0.5, 3, 1))
        self.assertIn(row3["W_improvement"], ("none", "unknown", "wsum", "max"))


if __name__ == "__main__":
    unittest.main()
