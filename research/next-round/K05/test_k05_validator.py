#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты K05 (unittest, без pytest). Запуск: python research/next-round/K05/test_k05_validator.py"""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import k05_validator as V  # noqa: E402

AS_OF = "2026-10-05"


def load(name):
    return json.loads((HERE / "examples" / name).read_text(encoding="utf-8"))


class TestContract(unittest.TestCase):
    def test_real_zero_accepted(self):
        obs = load("real_zero_osm_admin_level9.json")
        self.assertEqual(obs["value"], 0)
        self.assertEqual(obs["value_status"], "reported_zero")
        self.assertEqual(V.validate(obs, AS_OF), ([], []))

    def test_missing_is_null_not_zero(self):
        for obs in load("missing_real_context_astana.json"):
            self.assertIsNone(obs["value"])
            self.assertEqual(V.validate(obs, AS_OF)[0], [])

    def test_legacy_zero_with_missing_rejected(self):
        obs = dict(load("missing_real_context_astana.json")[0], value=0)
        errors, _ = V.validate(obs, AS_OF)
        self.assertTrue(any(e.startswith("FALSE_VALUE") for e in errors))

    def test_stale_warns(self):
        errors, warnings = V.validate(load("stale_osm_admin_level6.json"), AS_OF)
        self.assertEqual(errors, [])
        self.assertTrue(any(w.startswith("STALE") for w in warnings))
        # Тот же объект без политики давности не помечается.
        self.assertEqual(V.validate(load("real_count_osm_admin_level6.json"), AS_OF), ([], []))

    def test_synthetic_flagged_and_not_mixed(self):
        syn = load("synthetic_city_data_esil_T1.json")
        errors, warnings = V.validate(syn, AS_OF)
        self.assertEqual(errors, [])
        self.assertTrue(any(w.startswith("NOT_MEASUREMENT") for w in warnings))
        real = load("real_count_osm_admin_level6.json")
        with self.assertRaises(ValueError):
            V.aggregate_sum([real, dict(syn, unit="count")])

    def test_invalid_cases_all_rejected(self):
        for obs in load("invalid/invalid_cases.json"):
            self.assertTrue(V.validate(obs, AS_OF)[0], obs["obs_id"])

    def test_aggregate_does_not_fill_null(self):
        z = load("real_zero_osm_admin_level9.json")
        m = load("missing_real_context_astana.json")[0]
        self.assertEqual(V.aggregate_sum([z, z])["value_status"], "reported_zero")
        agg = V.aggregate_sum([dict(z, geo_unit_id="kz.astana.esil"), m])
        self.assertIsNone(agg["value"])
        self.assertEqual(agg["coverage"], "1/2")

    def test_city_mix_rejected_in_aggregate(self):
        z = load("real_zero_osm_admin_level9.json")
        with self.assertRaises(ValueError):
            V.aggregate_sum([z, dict(z, city_id="kz.shymkent", geo_unit_id="kz.shymkent")])

    def test_legacy_ok_meta_keeps_numbers(self):
        rc = {"esil": {"schools": 0, "parks": 3}}
        meta = {"status": "ok", "generated_at": "2026-09-23T11:40:00+00:00", "districts_source": "osm"}
        obs = {o["indicator_id"]: o for o in V.legacy_real_context_to_observations(rc, meta)}
        self.assertEqual(obs["osm_poi_count.schools"]["value_status"], "reported_zero")
        self.assertEqual(obs["osm_poi_count.parks"]["value"], 3)
        for o in obs.values():
            self.assertEqual(V.validate(o, AS_OF)[0], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
