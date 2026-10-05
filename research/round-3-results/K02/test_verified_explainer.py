"""K02 round 3: тесты прототипа. Запуск из корня:
  python -m unittest research/round-3-results/K02/test_verified_explainer.py
Нужен numpy (движок). Сеть и ключ API не нужны.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verified_explainer import (PlanError, StubSelector, build_catalog, catalog_from_observations,  # noqa: E402
                                catalog_view, explain, render, validate_plan)
from engine.optimizer import optimize  # noqa: E402
from engine.simulation import simulate  # noqa: E402

DECISIONS = optimize(top_n=1)["results"][0]["decisions"]
BASE = simulate(DECISIONS)
E2 = simulate(DECISIONS, event_id="E2")
CITY = "astana_hackathon"


def plan(*ids, stype="summary", comment=None):
    return {"sections": [{"type": stype, "fact_ids": list(ids)}], "comment": comment}


class Validation(unittest.TestCase):
    def setUp(self):
        self.cat = build_catalog(BASE)

    def check(self, p, code, **kw):
        with self.assertRaises(PlanError) as ctx:
            validate_plan(p, self.cat, city=CITY, scenario_id="base", **kw)
        self.assertEqual(ctx.exception.code, code, str(ctx.exception))

    def test_unknown_id(self):
        self.check(plan("astana_hackathon/base/plan.happiness"), "unknown_id")

    def test_free_text_instead_of_id(self):
        self.check(plan("Score вырос на пять баллов"), "not_an_id")
        self.check(plan("Үш аудан ғана жақсарады."), "not_an_id")

    def test_foreign_city(self):
        self.check(plan("shymkent_real/2025/district.esil.population"), "foreign_city")

    def test_stale_scenario(self):
        e2 = build_catalog(E2)
        stale = "astana_hackathon/base/plan.score"
        with self.assertRaises(PlanError) as ctx:
            validate_plan(plan(stale), e2, city=CITY, scenario_id="E2")
        self.assertEqual(ctx.exception.code, "stale_scenario")

    def test_section_and_shape(self):
        self.check({"sections": [{"type": "story", "fact_ids": ["astana_hackathon/base/plan.score"]}]}, "bad_section")
        self.check({"sections": [], "comment": None}, "bad_shape")
        self.check({"sections": [{"type": "summary", "fact_ids": ["astana_hackathon/base/plan.score"],
                                  "value": 99}]}, "bad_shape")
        self.check({"sections": [{"type": "summary", "fact_ids": [57.24]}]}, "not_an_id")

    def test_duplicate(self):
        fid = "astana_hackathon/base/plan.score"
        self.check(plan(fid, fid), "duplicate_id")


class NullAndZero(unittest.TestCase):
    def test_null_is_not_zero(self):
        broken = copy.deepcopy(BASE)
        broken["N_crit"] = None
        cat = build_catalog(broken)
        fid = "astana_hackathon/base/plan.n_crit"
        self.assertIsNone(cat[fid].value)
        self.assertEqual(cat[fid].kind, "unknown")
        with self.assertRaises(PlanError) as ctx:
            validate_plan(plan(fid, stype="risks"), cat, city=CITY, scenario_id="base")
        self.assertEqual(ctx.exception.code, "null_as_fact")
        ok = validate_plan(plan(fid, stype="data_gaps"), cat, city=CITY, scenario_id="base")
        for lang, word in (("ru", "нет данных"), ("kk", "дерек жоқ")):
            text = render(ok, cat, lang=lang)["verified_text"]
            self.assertIn(word, text)
            self.assertNotIn(": 0", text)

    def test_true_zero_is_printed(self):
        cat = build_catalog(BASE)
        fid = "astana_hackathon/base/plan.n_crit"
        self.assertEqual(cat[fid].value, 0)
        ok = validate_plan(plan(fid, stype="risks"), cat, city=CITY, scenario_id="base")
        self.assertIn(": 0 (учебная модель)", render(ok, cat, lang="ru")["verified_text"])

    def test_value_cannot_go_to_gaps(self):
        cat = build_catalog(BASE)
        with self.assertRaises(PlanError) as ctx:
            validate_plan(plan("astana_hackathon/base/plan.score", stype="data_gaps"), cat,
                          city=CITY, scenario_id="base")
        self.assertEqual(ctx.exception.code, "value_in_gaps")

    def test_observation_null_real_city(self):
        cat = catalog_from_observations([
            {"city": "shymkent_real", "period": "2025", "path": "district.unknown_1.schools", "value": None,
             "kind": "observed", "unit": "count", "label_ru": "Школы (тест)", "label_kk": "Мектептер (тест)",
             "source": "synthetic-test-row"}])
        fact = next(iter(cat.values()))
        self.assertEqual(fact.kind, "unknown")
        with self.assertRaises(PlanError):
            validate_plan(plan(fact.fact_id), cat, city="shymkent_real", scenario_id="2025")


class Labels(unittest.TestCase):
    def test_ru_kk_labels_and_values(self):
        ru, kk = explain(BASE, lang="ru"), explain(BASE, lang="kk")
        self.assertEqual([f["value"] for f in ru["facts_used"]], [f["value"] for f in kk["facts_used"]])
        self.assertIn("Итоговый Score плана: 57,24 (учебная модель)", ru["text"])
        self.assertIn("Жоспардың қорытынды Score көрсеткіші: 57,24 (оқу моделі)", kk["text"])
        self.assertIn("Ең әлсіз аудан: Нұра", kk["text"])
        self.assertIn("Изменение Score: +4,68", ru["text"])

    def test_values_come_from_engine(self):
        out = explain(BASE, lang="ru")
        by_id = {f["id"]: f for f in out["facts_used"]}
        self.assertEqual(by_id["astana_hackathon/base/plan.score"]["value"], BASE["score"])
        self.assertEqual(by_id["astana_hackathon/base/plan.cost"]["value"], BASE["cost"])

    def test_event_scenario(self):
        out = explain(E2, lang="ru")
        self.assertEqual(out["scenario_id"], "E2")
        self.assertTrue(all(f["id"].startswith("astana_hackathon/E2/") for f in out["facts_used"]))


class Comment(unittest.TestCase):
    class Chatty(StubSelector):
        name = "test_selector_with_comment"

        def select(self, view, question="", lang="ru"):
            p = super().select(view, question, lang)
            p["comment"] = "Score вырос на 99 баллов. Бұл бір маңызды қадам."
            return p

    def test_comment_dropped_by_default(self):
        out = explain(BASE, lang="ru", selector=self.Chatty())
        self.assertNotIn("99", out["text"])
        self.assertFalse(out["comment_shown"])

    def test_comment_separate_does_not_change_facts(self):
        dropped = explain(BASE, lang="kk", selector=self.Chatty())
        shown = explain(BASE, lang="kk", selector=self.Chatty(), comment_policy="separate")
        self.assertEqual(dropped["verified_text"], shown["verified_text"])
        self.assertEqual(dropped["facts_used"], shown["facts_used"])
        self.assertIn("ТЕКСЕРІЛМЕЙДІ", shown["text"])
        self.assertTrue(shown["text"].index("ТЕКСЕРІЛМЕЙДІ") > len(shown["verified_text"]))


class Selector(unittest.TestCase):
    def test_stub_is_labelled_and_deterministic(self):
        view = catalog_view(build_catalog(BASE))
        self.assertIn("not an LLM", StubSelector.name)
        self.assertEqual(StubSelector().select(view), StubSelector().select(view))


if __name__ == "__main__":
    unittest.main()
