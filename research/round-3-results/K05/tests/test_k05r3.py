#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 3: тесты контракта k05-obs-v1.1 на реальных данных K10 обоих городов.

Структура — библиотекой jsonschema (Draft 2020-12), связи полей — k05r3_contract.
Перед запуском: python research/round-3-results/K05/k05r3_adapter.py
Запуск:         python research/round-3-results/K05/tests/test_k05r3.py
"""

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
K05 = HERE.parent
sys.path.insert(0, str(K05))
import k05r3_contract as C  # noqa: E402

SCHEMA = json.loads((K05 / "schema/k05-obs-v1.1.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
CASES = json.loads((K05 / "cases/cases.json").read_text(encoding="utf-8"))
AS_OF = "2026-10-05"
REAL_INDEX = CASES["stale_check"]["release_index_real"]


def load(rel):
    return json.loads((K05 / rel).read_text(encoding="utf-8"))


def codes(msgs):
    return {m.split(":")[0] for m in msgs}


def all_example_obs():
    out = []
    for p in sorted((K05 / "examples").rglob("*.json")):
        if p.name == "sample_object_qa.json":
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        out += d if isinstance(d, list) else [d]
    return out


class TestSchemaLibrary(unittest.TestCase):
    def test_schema_itself_valid(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)

    def test_all_examples_pass_schema(self):
        obs = all_example_obs()
        self.assertGreater(len(obs), 100)
        for o in obs:
            errs = list(VALIDATOR.iter_errors(o))
            self.assertEqual(errs, [], f"{o['obs_id']}: {[e.message for e in errs]}")

    def test_case_observations_pass_schema(self):
        for o in [CASES["real_zero"], CASES["incomplete_sample"], CASES["partial_coverage_lower_bound"],
                  CASES["synthetic"], CASES["boundary_mismatch"]["obs"], *CASES["missing_access_denied"],
                  *CASES["city_mix"], *CASES["period_mix"]]:
            self.assertEqual(list(VALIDATOR.iter_errors(o)), [], o["obs_id"])

    def test_schema_rejects_structural_errors(self):
        base = CASES["real_zero"]
        bad = [
            {k: v for k, v in base.items() if k != "coverage"},
            dict(base, period="осень 2026"),
            dict(base, source={k: v for k, v in base["source"].items() if k not in ("sha256", "url")}),
            dict(base, city_id="kz.almaty"),
            dict(base, geo_unit_id="Еңбекші"),
        ]
        for o in bad:
            self.assertFalse(VALIDATOR.is_valid(o))

    def test_schema_alone_misses_semantic_errors(self):
        # Структурно верно, но 0 при missing — это ловит только семантический валидатор.
        o = dict(CASES["real_zero"], value_status="missing", missing_reason="not_collected")
        self.assertTrue(VALIDATOR.is_valid(o))
        self.assertIn("FALSE_VALUE", codes(C.validate(o, AS_OF)[0]))


class TestCases(unittest.TestCase):
    def test_real_zero(self):
        o = CASES["real_zero"]
        self.assertEqual((o["value"], o["value_status"], o["coverage"]["complete"]), (0, "reported_zero", True))
        self.assertEqual(o["city_id"], "kz.shymkent")
        self.assertEqual(C.validate(o, AS_OF, None, REAL_INDEX), ([], []))

    def test_zero_on_partial_coverage_rejected(self):
        o = copy.deepcopy(CASES["real_zero"])
        o["coverage"].update(complete=False, area_fraction=0.95)
        self.assertIn("ZERO_ON_PARTIAL", codes(C.validate(o, AS_OF)[0]))

    def test_missing_access_denied_both_cities(self):
        cities = set()
        for o in CASES["missing_access_denied"]:
            e, w = C.validate(o, AS_OF)
            self.assertEqual(e, [])
            self.assertIsNone(o["value"])
            self.assertEqual(o["missing_reason"], "source_access_denied")
            cities.add(o["city_id"])
        self.assertEqual(cities, {"kz.astana", "kz.shymkent"})

    def test_number_with_unknown_period_rejected(self):
        o = dict(CASES["real_zero"], period="unknown")
        self.assertIn("PERIOD_UNKNOWN", codes(C.validate(o, AS_OF)[0]))

    def test_incomplete_sample_and_partial_coverage_warn(self):
        e, w = C.validate(CASES["incomplete_sample"], AS_OF)
        self.assertEqual(e, [])
        self.assertIn("PARTIAL_COVERAGE", codes(w))
        self.assertEqual(CASES["incomplete_sample"]["coverage"]["cap_per_group"], 15)
        p = CASES["partial_coverage_lower_bound"]
        self.assertLess(p["coverage"]["area_fraction"], 1)
        self.assertIn("PARTIAL_COVERAGE", codes(C.validate(p, AS_OF)[1]))

    def test_city_and_period_mix_rejected(self):
        with self.assertRaisesRegex(ValueError, "CITY_MIX"):
            C.aggregate_sum(CASES["city_mix"])
        with self.assertRaisesRegex(ValueError, "PERIOD_MIX"):
            C.aggregate_sum(CASES["period_mix"])

    def test_aggregate_keeps_partial_flag(self):
        ast = load("examples/astana/overture_place_record_counts.json")
        school = [o for o in ast if o["indicator_id"] == "overture_place_records.school.conf_ge_0_5"]
        agg = C.aggregate_sum(school)
        self.assertEqual(agg["value_status"], "reported")
        self.assertFalse(agg["coverage_complete"])  # Есиль и Байконур охвачены не полностью
        full = [o for o in school if o["coverage"]["complete"]]
        self.assertTrue(C.aggregate_sum(full)["coverage_complete"])

    def test_aggregate_null_not_filled(self):
        a = CASES["real_zero"]
        b = dict(a, geo_unit_id="kz.shymkent.abai", value=None, value_status="missing",
                 missing_reason="not_collected")
        agg = C.aggregate_sum([a, b])
        self.assertIsNone(agg["value"])
        self.assertEqual(agg["n"], "1/2")

    def test_duplicates(self):
        d = CASES["duplicate_object"]
        self.assertEqual([x["code"] for x in d["fixture_same_id"]], ["DUPLICATE_ID"])
        names = {(w["a"]["name"], w["b"]["name"]) for w in d["astana_real"]}
        self.assertIn(("Ministry of Foreign Affairs, Republic of Kazakhstan", "Сыртқы істер министрлігі"), names)
        self.assertTrue(any("Коррупционерлер" in w["b"]["name"] for w in d["shymkent_real"]))
        self.assertEqual(d["shymkent_colocated"][0]["n"], 4)

    def test_synthetic_flagged_and_not_mixed(self):
        syn = CASES["synthetic"]
        e, w = C.validate(syn, AS_OF)
        self.assertEqual(e, [])
        self.assertIn("NOT_MEASUREMENT", codes(w))
        real = load("examples/shymkent/overture_place_record_counts.json")
        real_karatau = next(o for o in real if o["geo_unit_id"] == "kz.shymkent.karatau"
                            and o["indicator_id"] == syn["indicator_id"])
        with self.assertRaises(ValueError):
            C.aggregate_sum([dict(real_karatau, geo_unit_id="kz.shymkent.abai"), syn])
        # synthetic, выданный за измерение, отклоняется.
        self.assertIn("SYNTHETIC_NS", codes(C.validate(dict(syn, kind="derived"), AS_OF)[0]))

    def test_stale_and_superseded(self):
        s = CASES["stale_check"]
        self.assertNotIn("STALE", codes(C.validate(s["obs"], s["as_of_fresh"], None, s["release_index_real"])[1]))
        self.assertNotIn("SUPERSEDED", codes(C.validate(s["obs"], AS_OF, None, s["release_index_real"])[1]))
        self.assertIn("STALE", codes(C.validate(s["obs"], s["as_of_stale"])[1]))
        self.assertIn("SUPERSEDED", codes(C.validate(s["obs"], AS_OF, None, s["release_index_fixture_newer"])[1]))

    def test_boundary_mismatch_saraishyk(self):
        b = CASES["boundary_mismatch"]
        w = C.validate(b["obs"], AS_OF, b["product_boundary_ref"])[1]
        self.assertIn("BOUNDARY_MISMATCH", codes(w))
        self.assertIn("@16", b["obs"]["boundary_version"])
        self.assertTrue(b["product_boundary_ref"]["kz.astana.saraishyk"].endswith("@17"))
        esil = next(o for o in load("examples/astana/overture_place_record_counts.json")
                    if o["geo_unit_id"] == "kz.astana.esil")
        self.assertIn("BOUNDARY_VERSION_UNKNOWN", codes(C.validate(esil, AS_OF, b["product_boundary_ref"])[1]))

    def test_cities_not_mixed_in_examples(self):
        for city in ("astana", "shymkent"):
            for p in (K05 / "examples" / city).glob("*.json"):
                if p.name == "sample_object_qa.json":
                    continue
                d = json.loads(p.read_text(encoding="utf-8"))
                for o in d if isinstance(d, list) else [d]:
                    self.assertEqual(o["city_id"], f"kz.{city}")
                    self.assertTrue(o["geo_unit_id"].startswith(f"kz.{city}"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
