"""Input-integrity and adapter tests (unittest). Run: python3 -m unittest discover -s tests -v
K03 tests need shapely+pyproj (see requirements-build.txt) and are skipped without them."""
import importlib.util
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


@unittest.skipUnless(HAS_GEO, "shapely/pyproj not installed")
class K03Assignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(APP / "inputs" / "k03_root" / "research" / "round-3-results" / "K03"))
        import boundary_validator as BV
        cls.BV, cls.L = BV, BV.Layers()

    def test_k03_selftest_passes(self):
        ok, cases = self.BV.selftest(self.L)
        self.assertTrue(ok, [c for c in cases if not c["passed"]])
        statuses = {c["got"] for c in cases}
        self.assertTrue({"matched", "ambiguous", "unmatched", "outside", "invalid"} <= statuses)

    def test_ambiguous_point_gets_no_district(self):
        r = self.BV.assign(self.L, 71.447389, 51.1311552)  # tri-point Almaty/Esil/Saraishyk (K03 selftest)
        self.assertEqual(r["status"], "ambiguous")
        self.assertIsNone(r.get("district"))


class K05Contract(unittest.TestCase):
    def test_zero_on_partial_slice_is_an_error(self):
        sys.path.insert(0, str(APP / "inputs" / "k05_root" / "round-3-results" / "K05"))
        import k05r3_contract as C
        import json
        t = (APP / "web" / "evidence.js").read_text(encoding="utf-8")
        ev = json.loads(t[t.index("{"):t.rstrip().rindex(";")])
        o = next(x for x in ev["cities"]["astana"]["observations"] if x["indicator_id"] == "places.school")
        bad = dict(o, value=0, value_status="reported_zero")
        errs, _ = C.validate(bad, as_of="2026-10-05")
        self.assertTrue(any(e.startswith("ZERO_ON_PARTIAL") for e in errs), errs)
        errs_ok, _ = C.validate(o, as_of="2026-10-05")
        self.assertEqual(errs_ok, [])


if __name__ == "__main__":
    unittest.main()
