#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K05 round 4: тесты k05-obs-v1.2 на квадратах K10 round 3 (оба города).

Структура — jsonschema (Draft 2020-12), семантика — k05r4_contract.
Перед запуском: python research/round-4-results/K05/k05r4_adapter.py
Запуск:         python research/round-4-results/K05/tests/test_k05r4.py
"""

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
K05 = HERE.parent
ROOT = K05.parents[2]
sys.path.insert(0, str(K05))
import k05r4_contract as C  # noqa: E402

SCHEMA = json.loads((K05 / "schema/k05-obs-v1.2.schema.json").read_text(encoding="utf-8"))
SCHEMA_V11 = json.loads((ROOT / "research/round-3-results/K05/schema/k05-obs-v1.1.schema.json").read_text(encoding="utf-8"))
V = jsonschema.Draft202012Validator(SCHEMA)
CASES = json.loads((K05 / "cases/cases.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((K05 / "inputs/k10_r3/tests/expected_counts.json").read_text(encoding="utf-8"))["cities"]
AS_OF = "2026-10-05"


def load(rel):
    return json.loads((K05 / rel).read_text(encoding="utf-8"))


def codes(msgs):
    return {m.split(":")[0] for m in msgs}


def city_obs(city):
    return load(f"examples/{city}/square_place_record_counts.json") + [
        load(f"examples/{city}/square_not_collected_missing.json")]


class TestSchema(unittest.TestCase):
    def test_schema_valid_and_v11_untouched(self):
        jsonschema.Draft202012Validator.check_schema(SCHEMA)
        self.assertEqual(SCHEMA_V11["$id"], "k05-obs-v1.1")
        self.assertNotIn("spatial_unit", SCHEMA_V11["properties"])

    def test_examples_pass_schema(self):
        for city in ("shymkent", "astana"):
            for o in city_obs(city):
                self.assertEqual([e.message for e in V.iter_errors(o)], [], o["obs_id"])

    def test_schema_requires_spatial_unit(self):
        o = copy.deepcopy(CASES["real_zero"])
        del o["spatial_unit"]
        self.assertFalse(V.is_valid(o))
        o = copy.deepcopy(CASES["real_zero"])
        o["spatial_unit"]["bbox"] = [1, 2, 3]
        self.assertFalse(V.is_valid(o))


class TestCounts(unittest.TestCase):
    def test_counts_match_k10_expected(self):
        for city in ("shymkent", "astana"):
            got = {o["indicator_id"].split(".")[1]: o["value"] for o in city_obs(city)
                   if o["indicator_id"].endswith("conf_ge_0_0") and o["value_status"] != "missing"}
            self.assertEqual(got, EXPECTED[city]["places_by_group"])

    def test_all_examples_semantically_valid(self):
        for city in ("shymkent", "astana"):
            for o in city_obs(city):
                e, w = C.validate(o, AS_OF)
                self.assertEqual(e, [], o["obs_id"])
                self.assertIn("CROSSES_DISTRICTS", codes(w))
                self.assertEqual(o["city_id"], f"kz.{city}")
                self.assertEqual(o["spatial_unit"]["type"], "bbox")


class TestCases(unittest.TestCase):
    def test_real_zero_in_complete_square(self):
        o = CASES["real_zero"]
        self.assertEqual((o["value"], o["value_status"], o["coverage"]["complete"]), (0, "reported_zero", True))
        self.assertEqual(C.validate(o, AS_OF)[0], [])

    def test_missing_is_not_zero(self):
        for o in CASES["missing_not_zero"]:
            self.assertIsNone(o["value"])
            self.assertEqual(o["missing_reason"], "not_collected")
            self.assertEqual(C.validate(o, AS_OF)[0], [])
            self.assertIn("FALSE_VALUE", codes(C.validate(dict(o, value=0), AS_OF)[0]))

    def test_period_mix(self):
        with self.assertRaisesRegex(ValueError, "PERIOD_MIX"):
            C.aggregate_sum(CASES["period_mix"])

    def test_no_transfer_of_legacy_district_sums(self):
        sq, e02 = CASES["geometry_mix_legacy_district"]
        self.assertNotIn("spatial_unit", e02)
        with self.assertRaisesRegex(ValueError, "LEGACY_UNIT"):
            C.aggregate_sum([sq, e02])
        district = dict(sq, geo_unit_id="kz.shymkent.enbekshi",
                        spatial_unit={"type": "district_polygon", "crs": "EPSG:4326"})
        with self.assertRaisesRegex(ValueError, "SPATIAL_MIX"):
            C.aggregate_sum([sq, district])

    def test_overlapping_boxes_rejected(self):
        with self.assertRaisesRegex(ValueError, "OVERLAP"):
            C.aggregate_sum(CASES["geometry_overlap"])

    def test_unknown_period_and_spatial(self):
        self.assertIn("PERIOD_UNKNOWN", codes(C.validate(CASES["unknown_period_numeric"], AS_OF)[0]))
        self.assertIn("SPATIAL_UNKNOWN", codes(C.validate(CASES["unknown_spatial_numeric"], AS_OF)[0]))

    def test_unknown_confidence_flagged(self):
        self.assertIn("CONFIDENCE_UNKNOWN", {w["code"] for w in CASES["unknown_confidence_qa"]["warnings"]})

    def test_repeated_object(self):
        self.assertEqual([e["code"] for e in CASES["repeated_object_qa"]["errors"]], ["DUPLICATE_ID"])

    def test_real_colocated_cluster_shymkent(self):
        col = [w for w in CASES["real_possible_duplicates"]["shymkent"] if w["code"] == "COLOCATED"]
        self.assertEqual(max(w["n"] for w in col), 10)

    def test_city_mismatch(self):
        self.assertIn("CITY_MISMATCH", {e["code"] for e in CASES["city_mismatch_feature_qa"]["errors"]})
        self.assertIn("CITY_MISMATCH", codes(C.validate(CASES["city_mismatch_obs"], AS_OF)[0]))
        with self.assertRaisesRegex(ValueError, "CITY_MIX"):
            C.aggregate_sum(CASES["city_mix_aggregate"])

    def test_disjoint_boxes_same_city_sum(self):
        a = CASES["real_zero"]
        b = copy.deepcopy(a)
        b.update(geo_unit_id="kz.shymkent.other_box", value=2, value_status="reported")
        b["spatial_unit"]["bbox"] = [69.70, 42.40, 69.72, 42.42]
        self.assertEqual(C.aggregate_sum([a, b])["value"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
