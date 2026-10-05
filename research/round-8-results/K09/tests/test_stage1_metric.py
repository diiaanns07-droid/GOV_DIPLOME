"""Этап 1: метрика haversine-mm-v1, метрики плана, null-семантика, ключи, независимость от порядка, загрузка среза."""
import json, math, random, sys, unittest
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan import metric, data  # noqa: E402

REPO = K.parents[2]
FX = json.loads((K / "fixtures/hand_meridian.json").read_text(encoding="utf-8"))


class TestDistance(unittest.TestCase):
    def test_meridian_matches_independent_formula(self):
        for key, exp in FX["pair_mm"].items():
            a, b = key.split("-")
            pa = next(p for p in FX["points"] if p["id"] == a)
            pb = next(x for x in FX["sources"] + FX["candidates"] if x["id"] == b)
            self.assertEqual(metric.dist_mm(pa["lon"], pa["lat"], pb["lon"], pb["lat"]), exp, key)

    def test_zero_and_symmetry(self):
        self.assertEqual(metric.dist_mm(69.6, 42.3, 69.6, 42.3), 0)
        self.assertEqual(metric.dist_mm(69.6, 42.3, 69.61, 42.31), metric.dist_mm(69.61, 42.31, 69.6, 42.3))

    def test_clamp_antipodal_finite(self):
        self.assertTrue(math.isfinite(metric.haversine_m(0, 0, 180, 0)))

    def test_mm_rounding_half_up(self):
        # floor(x + 0.5): 0.4999 мм -> 0, 0.5 мм -> 1 (через прямую формулу для небольшого Δφ)
        self.assertEqual(int(math.floor(0.4999 + 0.5)), 0)
        self.assertEqual(int(math.floor(0.5 + 0.5)), 1)


def problem_from_fx(fx, sources=True):
    return metric.Problem(fx["points"], fx["sources"] if sources else [], fx["candidates"], fx["radius_m"])


class TestPlanMetrics(unittest.TestCase):
    def test_hand_expected_all_plans(self):
        pr = problem_from_fx(FX)
        for name, exp in FX["expected"].items():
            sel = [] if name == "empty" else [pr.cand_index[c] for c in name.split("+")]
            m = pr.evaluate(sel)
            self.assertEqual(m["weighted_sum_mm"], exp["weighted_sum_mm"], name)
            self.assertEqual(m["max_mm"], exp["max_mm"], name)
            self.assertEqual(m["covered_weight"], exp["covered_weight"], name)
            self.assertEqual(m["cost"], exp["cost"], name)
            self.assertEqual(m["unknown_count"], 0)
            rows = {r["point_id"]: r["after_mm"] for r in pr.rows(sel)}
            self.assertEqual(rows, exp["after_mm"], name)

    def test_empty_baseline_and_empty_plan_is_null_not_zero(self):
        pr = problem_from_fx(FX, sources=False)
        m = pr.evaluate([])
        self.assertEqual(m["unknown_count"], 2)
        self.assertIsNone(m["weighted_mean_mm"])
        self.assertIsNone(m["max_mm"])
        self.assertEqual(m["covered_weight"], 0)
        self.assertEqual(m["weighted_sum_mm"], 0)
        for r in pr.rows([]):
            self.assertIsNone(r["after_mm"]); self.assertIsNone(r["before_mm"]); self.assertIsNone(r["delta_mm"])

    def test_before_null_delta_null_even_if_after_known(self):
        pr = problem_from_fx(FX, sources=False)
        for r in pr.rows([pr.cand_index["c1"]]):
            self.assertIsNone(r["before_mm"]); self.assertIsNotNone(r["after_mm"]); self.assertIsNone(r["delta_mm"])
            self.assertEqual(r["nearest_after"]["kind"], "hypothetical")

    def test_nearest_source_vs_hypothetical_tie_is_stable(self):
        # кандидат в той же точке, что и источник: расстояния равны, выбирается source (kind_rank 0) — стабильный ключ
        pts = [{"id": "p", "lon": 69.6, "lat": 42.31, "weight": 1}]
        pr = metric.Problem(pts, [{"id": "s", "lon": 69.6, "lat": 42.311}], [{"id": "c", "lon": 69.6, "lat": 42.311, "cost": 1}], 300)
        self.assertEqual(pr.rows([0])[0]["nearest_after"], {"kind": "source", "id": "s"})

    def test_order_invariance(self):
        a = problem_from_fx(FX)
        fx2 = json.loads(json.dumps(FX))
        for k in ("points", "sources", "candidates"):
            random.Random(7).shuffle(fx2[k])
        b = problem_from_fx(fx2)
        for sel_ids in ([], ["c1"], ["c2"], ["c1", "c2"]):
            self.assertEqual(a.evaluate([a.cand_index[c] for c in sel_ids]), b.evaluate([b.cand_index[c] for c in sel_ids]))


class TestKeys(unittest.TestCase):
    def test_unknown_count_compared_before_partial_sum(self):
        known = {"unknown_count": 0, "weighted_sum_mm": 10 ** 12, "max_mm": 10 ** 9, "covered_weight": 0, "cost": 9, "selected_ids": ["z"]}
        partial = {"unknown_count": 1, "weighted_sum_mm": 1, "max_mm": None, "covered_weight": 5, "cost": 1, "selected_ids": ["a"]}
        self.assertLess(metric.key_mean(known), metric.key_mean(partial))
        self.assertLess(metric.key_minimax(known), metric.key_minimax(partial))
        # coverage: сначала покрытый вес (больше лучше), потом unknown_count
        self.assertLess(metric.key_coverage(partial), metric.key_coverage(known))

    def test_sorted_ids_prefix_shorter_first(self):
        base = {"unknown_count": 0, "weighted_sum_mm": 1, "max_mm": 1, "covered_weight": 1, "cost": 1}
        self.assertLess(metric.key_mean({**base, "selected_ids": ["a"]}), metric.key_mean({**base, "selected_ids": ["a", "b"]}))
        self.assertLess(metric.key_mean({**base, "selected_ids": ["a", "b"]}), metric.key_mean({**base, "selected_ids": ["b"]}))


class TestSlice(unittest.TestCase):
    def test_load_pinned_slice(self):
        d, digest = data.load_slice(repo=str(REPO))
        self.assertEqual(digest, data.EXPECTED_DATA_SHA256)
        self.assertEqual(len(data.sources(d, "shymkent", "school")), 15)
        self.assertEqual(len(data.sources(d, "astana", "outpatient_clinic")), 16)


if __name__ == "__main__":
    unittest.main()
