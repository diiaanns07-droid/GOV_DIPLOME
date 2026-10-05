"""Input-integrity and adapter tests (unittest). Run: python3 -m unittest discover -s tests -v
K03 tests need shapely+pyproj (see requirements-build.txt) and are skipped without them."""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tools"))
import build_data  # noqa: E402

HAS_GEO = importlib.util.find_spec("shapely") is not None and importlib.util.find_spec("pyproj") is not None


class InputIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(APP / "inputs" / "k10", self.tmp / "k10")
        self._k10 = build_data.K10
        build_data.K10 = self.tmp / "k10"

    def tearDown(self):
        build_data.K10 = self._k10
        shutil.rmtree(self.tmp)

    def test_pinned_inputs_build(self):
        data = build_data.build()
        self.assertEqual(data["cities"]["shymkent"]["counts"]["places"], 55)
        self.assertEqual(data["cities"]["astana"]["counts"]["segments"], 1326)

    def test_corrupted_file_is_rejected(self):
        f = self.tmp / "k10" / "data" / "astana" / "places_social.geojson"
        f.write_bytes(f.read_bytes().replace(b'"school"', b'"schoo1"', 1))
        with self.assertRaisesRegex(build_data.InputError, "sha256"):
            build_data.build()

    def test_missing_file_is_rejected(self):
        (self.tmp / "k10" / "data" / "shymkent" / "segments.geojson").unlink()
        with self.assertRaisesRegex(build_data.InputError, "нет файла"):
            build_data.build()

    def test_missing_manifest_is_rejected(self):
        (self.tmp / "k10" / "package_manifest.json").unlink()
        with self.assertRaisesRegex(build_data.InputError, "package_manifest"):
            build_data.build()


@unittest.skipUnless(HAS_GEO, "shapely/pyproj not installed (pip install -r requirements-build.txt)")
class K03AssignV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(APP / "inputs" / "k03v2_root" / "research" / "round-3-results" / "K03"))
        import boundary_validator as BV
        cls.BV, cls.L = BV, BV.Layers()

    def test_selftest_passes(self):
        ok, cases = self.BV.selftest(self.L)
        self.assertTrue(ok, [c for c in cases if not c["passed"]])
        self.assertTrue({"matched", "ambiguous", "unmatched", "outside", "invalid"} <= {c["got"] for c in cases})

    def test_k03_r4_boundary_fixtures(self):
        import math
        fx = json.loads((APP / "inputs/r4/K03/fixtures.json").read_text(encoding="utf-8"))["fixtures"]
        bad = []
        for f in fx:
            if not isinstance(f["lon"], (int, float)) or math.isnan(f["lon"]):
                continue
            r = self.BV.assign(self.L, f["lon"], f["lat"])
            if r["status"] != f["expected_status"] or (f["expected_district"] and r.get("district") != f["expected_district"]):
                bad.append((f["id"], f["expected_status"], r["status"]))
            if r["status"] in ("ambiguous", "unmatched"):
                self.assertIsNone(r.get("district"), f["id"])
        self.assertEqual(bad, [])

    def test_patched_copy_is_marked(self):
        m = json.loads((APP / "inputs/k03v2_root/MANIFEST_K03V2.json").read_text(encoding="utf-8"))
        self.assertNotEqual(m["modified"][0]["original_sha256"], m["modified"][0]["patched_sha256"])


class EvidenceFile(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(APP / "tools"))
        import contract as K
        self.K = K
        t = (APP / "web" / "evidence.js").read_text(encoding="utf-8")
        self.ev = K.loads_strict(t[t.index("{"):t.rstrip().rindex(";")])

    def test_committed_evidence_passes_contract(self):
        self.assertEqual(self.ev["contract"], self.K.CONTRACT_ID)
        for city, e in self.ev["cities"].items():
            errs, _ = self.K.validate_all(e["observations"], "2026-10-05")
            self.assertEqual(errs, [], city)

    def test_zero_on_partial_slice_still_an_error(self):
        import copy
        o = copy.deepcopy(next(x for x in self.ev["cities"]["astana"]["observations"]
                               if x["indicator_id"] == "overture_place_records.school.conf_ge_0_0"))
        o.update(value=0, value_status="reported_zero")
        o["coverage"]["complete"] = False
        errs, _ = self.K.validate(o, "2026-10-05")
        self.assertTrue(any(e.startswith("ZERO_ON_PARTIAL") for e in errs), errs)

    def test_shymkent_colocated_group_of_ten(self):
        groups = self.ev["cities"]["shymkent"]["qa"]["colocated"]
        big = [g for g in groups if len(g["ids"]) == 10]
        self.assertEqual(len(big), 1)
        self.assertEqual((big[0]["lon"], big[0]["lat"]), (69.5958, 42.3167))
        data = (APP / "web" / "data.js").read_text(encoding="utf-8")
        for i in big[0]["ids"]:
            self.assertIn(i, data)  # flagged, never removed

    def test_city_level_unknowns_are_null(self):
        for e in self.ev["cities"].values():
            for o in e["observations"]:
                if o["geo_unit_id"].count(".") == 1:  # kz.<city>
                    self.assertIsNone(o["value"])
                    self.assertEqual(o["value_status"], "missing")
                    self.assertIsNotNone(o["missing_reason"])


if __name__ == "__main__":
    unittest.main()
