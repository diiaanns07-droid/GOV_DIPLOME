"""K02 round 4: тесты исправления. Запуск из корня (нужен numpy):
  python -m unittest research/round-4-results/K02/test_fix.py
Проверяет: r3 воспроизводит дефекты, fixed их устраняет и сохраняет прежние гарантии.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import attack_cases  # noqa: E402

R3, FX = attack_cases.load("r3"), attack_cases.load("fixed")
RECS = attack_cases.k05_records()
from engine.optimizer import optimize  # noqa: E402
from engine.simulation import simulate  # noqa: E402

DECISIONS = optimize(top_n=1)["results"][0]["decisions"]
BASE, E2 = simulate(DECISIONS), simulate(DECISIONS, event_id="E2")
CITY = "astana_hackathon"


def plan(cat, *ids, stype="summary"):
    return {"sections": [{"type": stype, "fact_ids": list(ids)}], "catalog_digest": FX.catalog_digest(cat)}


class Attacks(unittest.TestCase):
    def test_r3_all_defects_reproduce(self):
        outcomes = {r["attack"]: r["outcome"] for r in attack_cases.run("r3")}
        self.assertEqual(set(outcomes.values()), {"defect"}, outcomes)
        self.assertEqual(len(outcomes), 10)

    def test_fixed_all_ok(self):
        outcomes = {r["attack"]: r["outcome"] for r in attack_cases.run("fixed")}
        self.assertEqual(set(outcomes.values()), {"ok"}, outcomes)


class K05Real(unittest.TestCase):
    def test_both_cities_ingest_and_stay_apart(self):
        ast = FX.catalog_from_k05(RECS["astana_sample_rows"])
        shy = FX.catalog_from_k05(RECS["shymkent_sample_rows"])
        self.assertEqual(len(ast), 7)
        self.assertEqual(len(shy), 7)
        self.assertTrue(all(f.city == "kz.astana" for f in ast.values()))
        self.assertTrue(all(f.city == "kz.shymkent" for f in shy.values()))
        fid = next(iter(shy))
        with self.assertRaises(FX.PlanError) as ctx:
            FX.validate_plan(plan(shy, fid), ast,  # план по каталогу Шымкента против Астаны
                             city="kz.astana", scenario_id="2026-09-23")
        self.assertEqual(ctx.exception.code, "stale_catalog")
        with self.assertRaises(FX.PlanError) as ctx:
            FX.validate_plan(plan(ast, fid), ast, city="kz.astana", scenario_id="2026-09-23")
        self.assertEqual(ctx.exception.code, "foreign_city")

    def test_real_zero_and_missing_render(self):
        cat = FX.catalog_from_k05(RECS["real_zero"] + RECS["shymkent_official_missing"])
        zero = next(f for f in cat.values() if f.value == 0)
        miss = next(f for f in cat.values() if f.value is None)
        p = {"sections": [{"type": "summary", "fact_ids": [zero.fact_id]}], "catalog_digest": FX.catalog_digest(cat)}
        # разные периоды (2026-09-23 и unknown) — в одном ответе нельзя
        with self.assertRaises(FX.PlanError) as ctx:
            FX.validate_plan({"sections": [{"type": "summary", "fact_ids": [zero.fact_id]},
                                           {"type": "data_gaps", "fact_ids": [miss.fact_id]}],
                              "catalog_digest": FX.catalog_digest(cat)}, cat,
                             city="kz.shymkent", scenario_id="2026-09-23")
        self.assertEqual(ctx.exception.code, "stale_scenario")
        ok = FX.validate_plan(p, cat, city="kz.shymkent", scenario_id="2026-09-23")
        text = FX.render(ok, cat, lang="ru")["verified_text"]
        self.assertIn(": 0 записей (расчёт)", text)
        self.assertNotIn("неполный", text)   # real_zero у K05 — complete=true
        gaps = FX.validate_plan({"sections": [{"type": "data_gaps", "fact_ids": [miss.fact_id]}],
                                 "catalog_digest": FX.catalog_digest(cat)}, cat,
                                city="kz.shymkent", scenario_id="unknown")
        out = FX.render(gaps, cat, lang="kk")
        self.assertIn("дерек жоқ", out["verified_text"])
        self.assertEqual(out["facts_used"][0]["missing_reason"], "source_access_denied")

    def test_incomplete_marked_ru_kk(self):
        cat = FX.catalog_from_k05(RECS["partial_coverage_lower_bound"])
        fid = next(iter(cat))
        ok = FX.validate_plan(plan(cat, fid), cat, city="kz.astana", scenario_id="2026-09-23")
        self.assertIn("неполный охват", FX.render(ok, cat, lang="ru")["verified_text"])
        self.assertIn("толық емес қамту", FX.render(ok, cat, lang="kk")["verified_text"])

    def test_synthetic_stays_labelled(self):
        cat = FX.catalog_from_k05(RECS["synthetic"])
        fid = next(iter(cat))
        ok = FX.validate_plan(plan(cat, fid), cat, city="kz.shymkent", scenario_id="2026-09-23")
        self.assertIn("(синтетика)", FX.render(ok, cat, lang="ru")["verified_text"])

    def test_interval_period_rejected(self):
        rec = dict(RECS["incomplete_sample"][0], period="2025/2026")
        with self.assertRaises(ValueError):
            FX.catalog_from_k05([rec])


class KeptGuarantees(unittest.TestCase):
    """Гарантии r3 сохраняются в fixed."""

    def setUp(self):
        self.cat = FX.build_catalog(BASE)

    def code(self, p, **kw):
        with self.assertRaises(FX.PlanError) as ctx:
            FX.validate_plan(p, self.cat, city=CITY, scenario_id=kw.get("scenario", "base"))
        return ctx.exception.code

    def test_rejections(self):
        self.assertEqual(self.code(plan(self.cat, "astana_hackathon/base/plan.happiness")), "unknown_id")
        self.assertEqual(self.code(plan(self.cat, "Үш аудан ғана жақсарады.")), "not_an_id")
        self.assertEqual(self.code(plan(self.cat, "kz.shymkent/2026-09-23/abai.x")), "foreign_city")
        self.assertEqual(self.code(plan(self.cat, "astana_hackathon/E2/plan.score")), "stale_scenario")
        self.assertEqual(self.code({"sections": [{"type": "summary",
                                                  "fact_ids": ["astana_hackathon/base/plan.score"]}]}),
                         "stale_catalog")

    def test_same_id_other_scenario_is_other_fact(self):
        e2 = FX.build_catalog(E2)
        self.assertNotEqual(FX.catalog_digest(e2), FX.catalog_digest(self.cat))
        self.assertTrue(set(e2).isdisjoint(self.cat))

    def test_true_zero_and_labels(self):
        ru, kk = FX.explain(BASE, lang="ru"), FX.explain(BASE, lang="kk")
        self.assertIn("Критических значений после мер: 0 (учебная модель)", ru["text"])
        self.assertIn("Жоспардың қорытынды Score көрсеткіші: 57,24 (оқу моделі)", kk["text"])
        self.assertEqual(ru["catalog_digest"], kk["catalog_digest"])

    def test_stub_is_not_llm(self):
        self.assertIn("not an LLM", FX.StubSelector.name)


if __name__ == "__main__":
    unittest.main()
