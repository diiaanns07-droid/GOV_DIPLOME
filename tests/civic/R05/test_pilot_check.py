"""Pilot analysis reports placement honestly and never moves coordinates."""

import copy
import json
import os
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PKG = os.path.join(REPO, "data", "civic", "astana")
sys.path.insert(0, os.path.join(PKG, "tools"))

import civic_v1 as cv  # noqa: E402
import pilot_check as pc  # noqa: E402

REF = json.load(open(os.path.join(PKG, "pilot_reference.json"), encoding="utf-8"))
FENCE = cv.load_geofence(os.path.join(PKG, "geofence.json"))


class PilotCheck(unittest.TestCase):
    def test_no_real_objects_means_no_concentration_claim(self):
        report = pc.analyse(cv.load_items(os.path.join(PKG, "objects.json")), REF, FENCE)
        self.assertEqual(report["real_items"], 0)
        self.assertTrue(report["pilot_by_confirmed_concentration"].startswith("not_possible"))

    def test_outside_object_reported_and_not_moved(self):
        items = cv.load_items(os.path.join(PKG, "demo_synthetic.json"))
        far = copy.deepcopy(items[0])
        far["id"] = "demo-astana-far"
        far["geometry"] = {"type": "Point", "coordinates": [71.55, 51.10]}
        before = copy.deepcopy(far)
        report = pc.analyse([far], REF, FENCE)
        self.assertEqual(report["rows"][0]["placement"], "outside_graph")
        self.assertEqual(far, before)

    def test_graph_reference_is_inside_city(self):
        b = REF["graph"]["declared_bbox"]
        for lon, lat in ((b[0], b[1]), (b[2], b[3])):
            self.assertEqual(cv.fence_position(lon, lat, FENCE), "inside")


if __name__ == "__main__":
    unittest.main()
