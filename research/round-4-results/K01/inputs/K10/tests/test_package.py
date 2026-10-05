"""K10 round 3 package tests (stdlib unittest; also runs under pytest).

Run from the package dir:  python -m unittest discover -s tests -v
Control values are frozen in tests/expected_counts.json (written once from the first
committed build; a different build/release must fail here and be re-reviewed).
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PKG, "scripts"))
import offline_check  # noqa: E402

with open(os.path.join(PKG, "tests", "expected_counts.json"), encoding="utf-8") as _fh:
    EXPECTED = json.load(_fh)
REPORT = offline_check.run()


class PackageIntegrity(unittest.TestCase):
    def test_offline_check_passes(self):
        self.assertEqual(REPORT["errors"], [])
        self.assertTrue(REPORT["ok"])

    def test_release_pinned(self):
        self.assertEqual(REPORT["release"], EXPECTED["release"])

    def test_only_manifest_files_opened(self):
        allowed = {"package_manifest.json"} | {
            f["path"] for c in offline_check.MANIFEST["cities"].values() for f in c["files"].values()}
        self.assertTrue(set(REPORT["files_opened"]) <= allowed, REPORT["files_opened"])

    def test_network_blocked(self):
        with self.assertRaises(offline_check.NetworkBlocked):
            socket.create_connection(("example.org", 443), timeout=1)


class ControlCounts(unittest.TestCase):
    def test_counts_and_graph(self):
        for city, exp in EXPECTED["cities"].items():
            got = REPORT["cities"][city]
            with self.subTest(city=city):
                self.assertEqual(got["bbox"], exp["bbox"])
                self.assertEqual(got["places"]["count"], exp["places"])
                self.assertEqual(got["places"]["by_group"], exp["places_by_group"])
                self.assertEqual(got["segments"]["count"], exp["segments"])
                self.assertEqual(got["connectors"]["count"], exp["connectors"])
                self.assertEqual(got["graph_all_roads"]["components"], exp["road_components"])
                self.assertEqual(got["graph_all_roads"]["largest_component_share_of_length"], exp["road_lcc_share"])

    def test_no_duplicates_and_referential_integrity(self):
        for city, got in REPORT["cities"].items():
            with self.subTest(city=city):
                self.assertEqual(got["connectors"]["missing_referenced"], 0)
        self.assertFalse([e for e in REPORT["errors"] if "duplicate" in e])

    def test_edge_objects(self):
        for city, exp in EXPECTED["cities"].items():
            got = REPORT["cities"][city]
            with self.subTest(city=city):
                self.assertEqual(got["segments"]["crossing_bbox_edge"], exp["segments_crossing_edge"])
                self.assertEqual(got["connectors"]["outside_bbox"], exp["connectors_outside_bbox"])
                self.assertEqual(got["places"]["within_100m_of_bbox_edge"], exp["places_within_100m_of_edge"])
                # the square cuts the network: edge segments exist and are flagged, not dropped
                self.assertGreater(got["segments"]["crossing_bbox_edge"], 0)


class TamperDetection(unittest.TestCase):
    def test_modified_copy_fails(self):
        tmp = tempfile.mkdtemp()
        try:
            dst = os.path.join(tmp, "K10")
            shutil.copytree(PKG, dst, ignore=shutil.ignore_patterns("__pycache__", "results"))
            target = os.path.join(dst, "data", "shymkent", "places_social.geojson")
            with open(target, "rb") as fh:
                data = bytearray(fh.read())
            i = data.index(b'"confidence":') + len(b'"confidence":')
            data[i] = ord("1") if data[i] != ord("1") else ord("0")
            with open(target, "wb") as fh:
                fh.write(bytes(data))
            sys.path.insert(0, os.path.join(dst, "scripts"))
            import importlib.util
            spec = importlib.util.spec_from_file_location("oc_copy", os.path.join(dst, "scripts", "offline_check.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            rep = mod.run()
            self.assertFalse(rep["ok"])
            self.assertTrue(any("sha256 mismatch" in e for e in rep["errors"]), rep["errors"])
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)
