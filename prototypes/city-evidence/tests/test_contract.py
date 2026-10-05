"""New-build contract tests (k05-obs-v1.2+k12r4). Run: python3 -m unittest discover -s tests -v"""
import copy
import json
import math
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tools"))
import contract as K  # noqa: E402

AS_OF = "2026-10-05"


def example(city):
    p = APP / "inputs" / "r4" / "K05" / "examples" / city / "square_place_record_counts.json"
    return K.loads_strict(p.read_text(encoding="utf-8"))


class StrictJson(unittest.TestCase):
    def test_rejects_nan_and_infinity_tokens(self):
        for tok in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaisesRegex(K.ContractError, "JSON_NONFINITE"):
                K.loads_strict('{"value": %s}' % tok)

    def test_rejects_overflow_1e999(self):
        with self.assertRaisesRegex(K.ContractError, "JSON_NONFINITE"):
            K.loads_strict('{"value": 1e999}')

    def test_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(K.ContractError, "JSON_DUPLICATE_KEY"):
            K.loads_strict('{"value_status": "reported", "value_status": "missing"}')

    def test_export_refuses_nan(self):
        with self.assertRaises(ValueError):
            K.dumps_strict({"value": math.nan})


class RecordRules(unittest.TestCase):
    def setUp(self):
        self.obs = next(o for o in example("shymkent") if o["value_status"] == "reported")

    def test_nan_and_infinity_values_rejected(self):
        for v in (math.nan, math.inf, -math.inf):
            o = copy.deepcopy(self.obs)
            o["value"] = v
            errs, _ = K.validate(o, AS_OF)
            self.assertTrue(any(e.startswith("VALUE_NOT_FINITE") for e in errs), (v, errs))

    def test_count_unit_domain_and_bad_dates(self):  # K12 checks survive under v1.2
        o = copy.deepcopy(self.obs)
        o["period"] = "2025-02-30"
        errs, _ = K.validate(o, AS_OF)
        self.assertTrue(any(e.startswith("PERIOD_INVALID_DATE") for e in errs), errs)

    def test_missing_spatial_unit_rejected(self):
        o = copy.deepcopy(self.obs)
        del o["spatial_unit"]
        errs, _ = K.validate(o, AS_OF)
        self.assertTrue(any(e.startswith("SPATIAL_UNIT") for e in errs), errs)

    def test_duplicate_obs_id_with_other_value_rejected(self):
        a = copy.deepcopy(self.obs)
        b = copy.deepcopy(self.obs)
        b["value"] = a["value"] + 1
        errs, _ = K.validate_all([a, b], AS_OF)
        self.assertTrue(any("DUPLICATE_OBS_ID" in e for e in errs), errs)

    def test_v11_district_record_cannot_be_summed_with_bbox(self):
        legacy = {k: v for k, v in copy.deepcopy(self.obs).items() if k != "spatial_unit"}
        with self.assertRaisesRegex(ValueError, "LEGACY_UNIT"):
            K.C4.aggregate_sum([self.obs, legacy])


class RealInputs(unittest.TestCase):
    def test_both_cities_validate_without_errors(self):
        for city in ("shymkent", "astana"):
            obs = example(city)
            errs, _ = K.validate_all(obs, AS_OF)
            self.assertEqual(errs, [], city)
            self.assertTrue(all(o["spatial_unit"]["type"] == "bbox" for o in obs))

    def test_example_values_equal_independent_recount_from_k10(self):
        for city in ("shymkent", "astana"):
            fc = json.loads((APP / "inputs/k10/data" / city / "places_social.geojson").read_text(encoding="utf-8"))
            for o in example(city):
                g = o["indicator_id"].split(".")[1]
                t = o["method"]["parameters"]["confidence_min"]
                n = sum(1 for f in fc["features"] if f["properties"]["k10_group"] == g
                        and f["properties"]["confidence"] is not None and f["properties"]["confidence"] >= t)
                self.assertEqual(o["value"], n, (city, o["indicator_id"]))
                self.assertEqual(o["source"]["sha256"],
                                 __import__("hashlib").sha256((APP / "inputs/k10/data" / city / "places_social.geojson").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
