"""Unit tests of the Python what-if reference (tools/whatif_ref.py) on hand geometry.
Usage: python3 -m unittest tests.test_whatif   (also run by tools/check_all.py, step tests)"""
import json
import math
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import whatif_ref as W  # noqa: E402

PLACES = [
    {"id": "b", "group": "school", "lon": 1.0, "lat": 0.0},
    {"id": "a", "group": "school", "lon": -1.0, "lat": 0.0},
    {"id": "c", "group": "outpatient_clinic", "lon": 0.0, "lat": 0.5},
]
DEG = 2 * math.pi * W.R_EARTH / 360  # 1 degree of a great circle


def prop(lon, lat, cat="school"):
    return {"id": "X", "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical"}


class WhatIfReference(unittest.TestCase):
    def test_one_degree_on_equator(self):
        assert abs(W.haversine(0, 0, 1, 0) - DEG) < 1e-6
        assert abs(DEG - 111195.0802) < 1e-3
        assert W.haversine(10, 20, 10, 20) == 0.0
        assert abs(W.haversine(0, 0, 180, 0) - math.pi * W.R_EARTH) < 1e-6  # clamp keeps antipodes finite

    def test_no_project_after_equals_before_tie_by_id(self):
        r = W.compute(PLACES, "school", [{"id": "P", "lon": 0, "lat": 0}], None)["rows"][0]
        assert r["before"] == r["after"] and r["delta"] == 0
        assert r["nearest_before"] == "a"  # equal distance to a and b -> smaller ID
        assert r["nearest_after"] == "source"

    def test_project_nearer_farther_same_point(self):
        pts = [{"id": "P", "lon": 0, "lat": 0}]
        near = W.compute(PLACES, "school", pts, prop(0.25, 0))["rows"][0]
        assert abs(near["after"] - DEG / 4) < 1e-6 and abs(near["delta"] - (DEG - DEG / 4)) < 1e-6
        assert near["nearest_after"] == "proposed"
        far = W.compute(PLACES, "school", pts, prop(0, 2))["rows"][0]
        assert far["after"] == far["before"] and far["delta"] == 0 and far["nearest_after"] == "source"
        same = W.compute(PLACES, "school", pts, prop(0, 0))["rows"][0]
        assert same["after"] == 0.0 and abs(same["delta"] - DEG) < 1e-6

    def test_empty_category_delta_null(self):
        only_clinic = [p for p in PLACES if p["group"] != "school"]
        res = W.compute(only_clinic, "school", [{"id": "P", "lon": 0, "lat": 0}], prop(0, 1))
        r = res["rows"][0]
        assert res["candidates"] == 0
        assert r["before"] is None and r["delta"] is None and abs(r["after"] - DEG) < 1e-6
        r0 = W.compute(only_clinic, "school", [{"id": "P", "lon": 0, "lat": 0}], None)["rows"][0]
        assert r0["before"] is None and r0["after"] is None and r0["delta"] is None

    def test_category_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            W.compute(PLACES, "school", [{"id": "P", "lon": 0, "lat": 0}], prop(0, 0, "outpatient_clinic"))

    def test_expected_file_fresh(self):
        data = W.load_data()
        fresh = json.dumps({"generator": "tools/whatif_ref.py", "formula": "haversine:R=6371008.8",
                            "cases": W.cases(data)}, ensure_ascii=False, indent=1) + "\n"
        assert W.OUT.read_text(encoding="utf-8") == fresh


if __name__ == "__main__":
    unittest.main()
