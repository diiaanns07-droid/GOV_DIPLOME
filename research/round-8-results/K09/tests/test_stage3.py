"""Этап 3: план сетки, статистика (Wilson, точный McNemar, квантиль), один сценарий раннера."""
import json, math, sys, unittest
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
        for b, c in [(5, 0), (1, 9), (40, 3), (3, 3)]:
            self.assertAlmostEqual(X.mcnemar_log10(b, c), math.log10(X.mcnemar_exact(b, c)), places=3)
        self.assertLess(X.mcnemar_log10(1493, 34), -300)                    # p ниже наименьшего float, log10 конечен

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



CFG2 = json.loads((K / "config/experiment_config_v2.json").read_text(encoding="utf-8"))


class TestV2(unittest.TestCase):
    def setUp(self):
        self.d, self.sha = data.load_slice(repo=str(K.parents[2]))
        self.ctx = {s["id"]: suite.make_context(self.d, self.sha, s["city"], s["category"], s["baseline"]) for s in CFG2["baselines"]["slices"]}

    def test_paired_nested_geometry(self):
        cv = CFG2["config_version"]
        a = suite.make_scenario_v2(self.ctx["astana_clinic"], 16, 25, 0.5, "uniform", 3, 300, 4, cv)
        b = suite.make_scenario_v2(self.ctx["astana_clinic_nobase"], 6, 5, 1.0, "random_1_100", 3, 800, 4, cv)
        geo = lambda xs: [(x["id"], x["lon"], x["lat"]) for x in xs]
        self.assertEqual(geo(a["control_points"])[:5], geo(b["control_points"]))           # те же точки (вложенно)
        self.assertEqual([(c["id"], c["lon"], c["lat"], c["cost"]) for c in a["candidates"][:6]],
                         [(c["id"], c["lon"], c["lat"], c["cost"]) for c in b["candidates"]])
        c = suite.make_scenario_v2(self.ctx["astana_clinic"], 16, 25, 0.5, "random_1_100", 3, 300, 4, cv)
        d = suite.make_scenario_v2(self.ctx["astana_clinic"], 6, 15, 0.25, "random_1_100", 3, 300, 4, cv)
        self.assertEqual([p["weight"] for p in c["control_points"]][:15], [p["weight"] for p in d["control_points"]])
        self.assertNotEqual(a["source_snapshot"], b["source_snapshot"])

    def test_budget_relative_to_top_costs(self):
        cv = CFG2["config_version"]
        for br in CFG2["factors"]["budget_ratio"]:
            sc = suite.make_scenario_v2(self.ctx["shymkent_school"], 10, 5, br, "uniform", 3, 300, 2, cv)
            top3 = sum(sorted((c["cost"] for c in sc["candidates"]), reverse=True)[:3])
            self.assertEqual(sc["budget"], int(br * top3))
        s1, _, _ = X.run_one(self.ctx["shymkent_school"], CFG2, "main", "shymkent_school", (10, 5, 1.0, "uniform", 3, 300, 2), {}, 1)
        self.assertEqual(s1["budget_binding"], 0)                                    # 1.0 — контроль без ограничения

    def test_secondary_ms_keeps_budget(self):
        cv = CFG2["config_version"]
        base = (16, 25, 0.5, "random_1_100", 3, 300, 1)
        s3, _, _ = X.run_one(self.ctx["astana_clinic"], CFG2, "sec_max_selected", "astana_clinic", base, {"max_selected": 5}, 1)
        s0, _, _ = X.run_one(self.ctx["astana_clinic"], CFG2, "main", "astana_clinic", base, {}, 1)
        self.assertEqual(s3["budget"], s0["budget"]); self.assertEqual(s3["max_selected"], 5)

    def test_run_one_three_algorithms_and_contrasts(self):
        sl = "astana_clinic_nobase"
        rows, scen = [], []
        for slc in ("astana_clinic", sl):
            for br in (0.25, 1.0):
                s, r, t = X.run_one(self.ctx[slc], CFG2, "main", slc, (6, 5, br, "uniform", 3, 300, 0), {}, 1)
                rows += r; scen.append(s)
                self.assertIn("t_exact_full_output_s", t)
        self.assertEqual({r["algorithm"] for r in rows}, {"G1", "G2", "G2id"})
        summ = X.summarize(rows, scen, CFG2)
        pc = summ["paired_contrasts"]["slice:astana_clinic_vs_astana_clinic_nobase"]["G1/mean"]
        self.assertEqual(pc["pairs"], 2)
        self.assertIn("g2_vs_g2id_mcnemar", summ)

if __name__ == "__main__":
    unittest.main()
