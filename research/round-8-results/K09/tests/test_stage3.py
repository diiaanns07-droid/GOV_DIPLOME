"""Этап 3: план сетки, статистика (Wilson, точный McNemar, квантиль), один сценарий раннера."""
import json, sys, unittest
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan import experiment as X, data, suite  # noqa: E402

CFG = json.loads((K / "config/experiment_config.json").read_text(encoding="utf-8"))


class TestStats(unittest.TestCase):
    def test_wilson_known_values(self):
        lo, hi = X.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.236593, places=5); self.assertAlmostEqual(hi, 0.763407, places=5)
        lo, hi = X.wilson(0, 10)
        self.assertEqual(lo, 0.0); self.assertAlmostEqual(hi, 0.277533, places=5)
        lo, hi = X.wilson(10, 10)
        self.assertAlmostEqual(lo, 0.722467, places=5); self.assertEqual(hi, 1.0)
        self.assertEqual(X.wilson(0, 0), (None, None))

    def test_mcnemar_exact(self):
        self.assertEqual(X.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(X.mcnemar_exact(5, 0), 0.0625)
        self.assertAlmostEqual(X.mcnemar_exact(3, 3), 1.0)
        self.assertAlmostEqual(X.mcnemar_exact(1, 9), 2 * 11 / 1024)

    def test_nearest_rank(self):
        self.assertEqual(X._q([3, 1, 2, 4], 0.5), 2)
        self.assertEqual(X._q([3, 1, 2, 4], 0.9), 4)
        self.assertIsNone(X._q([], 0.5))


class TestPlanAndRun(unittest.TestCase):
    def test_grid_size_and_order(self):
        p = X.scenario_plan(CFG)
        self.assertEqual(sum(1 for x in p if x[0] == "main"), 3 * 3 * 3 * 3 * 3 * 10)
        self.assertEqual(sum(1 for x in p if x[0] != "main"), 3 * 10 * 6)
        self.assertEqual(p, X.scenario_plan(CFG))

    def test_run_one_and_paired_secondary(self):
        d, sha = data.load_slice(repo=str(K.parents[2]))
        sl = CFG["baselines"]["slices"][0]
        ctx = suite.make_context(d, sha, sl["city"], sl["category"], sl["baseline"])
        base = (16, 25, 0.5, "random_1_100", 3, 300, 0)
        s1, r1, t1 = X.run_one(ctx, CFG, "main", sl["id"], base, {}, 1)
        s2, r2, _ = X.run_one(ctx, CFG, "sec_radius", sl["id"], base, {"coverage_radius_m": 300}, 1)
        self.assertEqual(len(r1), 6)
        self.assertEqual(s1["problem_digest"], s2["problem_digest"])         # парный дизайн: тот же экземпляр
        s3, _, _ = X.run_one(ctx, CFG, "sec_radius", sl["id"], base, {"coverage_radius_m": 800}, 1)
        self.assertNotEqual(s1["problem_digest"], s3["problem_digest"])
        self.assertEqual(s1["exact_mean_ids"], s3["exact_mean_ids"])          # радиус не влияет на mean-ключ
        self.assertEqual([{k: v for k, v in r.items() if k not in ("analysis", "scenario_key")} for r in r1],
                         [{k: v for k, v in r.items() if k not in ("analysis", "scenario_key")} for r in r2])
        self.assertTrue(all(v >= 0 for k, v in t1.items() if k.startswith("t_")))


if __name__ == "__main__":
    unittest.main()
