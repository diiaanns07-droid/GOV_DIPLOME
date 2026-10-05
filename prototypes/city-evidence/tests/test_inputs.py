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
class K03AssignV21(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(APP / "inputs" / "k03v21_root" / "research" / "round-3-results" / "K03"))
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
        m = json.loads((APP / "inputs/k03v21_root/MANIFEST_K03.json").read_text(encoding="utf-8"))
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


class OfflineCheckIsolated(unittest.TestCase):
    """K01 #3/#4: tamper detection runs the COPY's own offline_check in a separate process (no shared modules,
    no socket monkeypatch in this process)."""

    def _run_copy(self, mutate=None):
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(APP / "inputs" / "k10", tmp / "k10", ignore=shutil.ignore_patterns("__pycache__"))
            if mutate:
                mutate(tmp / "k10")
            r = subprocess.run([sys.executable, str(tmp / "k10" / "scripts" / "offline_check.py")],
                               capture_output=True, text=True, encoding="utf-8")
            return r.returncode, r.stdout
        finally:
            shutil.rmtree(tmp)

    def test_clean_copy_passes(self):
        code, out = self._run_copy()
        self.assertEqual(code, 0, out[-400:])

    def test_tampered_data_in_copy_fails(self):
        def mut(d):
            f = d / "data" / "shymkent" / "places_social.geojson"
            f.write_bytes(f.read_bytes().replace(b'"school"', b'"schoo1"', 1))
        code, out = self._run_copy(mut)
        self.assertEqual(code, 1)
        self.assertIn("sha256 mismatch", out)

    def test_tampered_rule_in_copy_is_the_one_executed(self):
        def mut(d):  # break the copy's own k10_rules: the copy's check must fail, proving it does not reuse loaded modules
            f = d / "scripts" / "k10_rules.py"
            f.write_text(f.read_text(encoding="utf-8").replace('return "unknown", []', 'return "allowed", []'),
                         encoding="utf-8", newline="\n")
        code, out = self._run_copy(mut)
        self.assertEqual(code, 1, out[-300:])
        self.assertIn("k10_foot_access", out)

    def test_this_process_socket_untouched(self):
        import socket
        self.assertFalse(getattr(socket.create_connection, "__name__", "") == "_no_net")


class GeometryPassThrough(unittest.TestCase):
    """K06/K10: the demo shows K10 lengths and foot-access classes unchanged; unknown is never turned into allowed."""

    def test_lengths_and_foot_access_unchanged(self):
        data = build_data.build()
        for city in ("shymkent", "astana"):
            fc = json.loads((APP / "inputs/k10/data" / city / "segments.geojson").read_text(encoding="utf-8"))
            src = {f["id"]: f["properties"] for f in fc["features"] if f["properties"]["subtype"] == "road"}
            for sg in data["cities"][city]["segments"]:
                p = src[sg["id"]]
                self.assertLessEqual(abs(sg["length_m"] - p["k10_length_m"]), 0.05 + 1e-9)  # rounded to 0.1 m
                self.assertEqual(sg["foot_access"], p["k10_foot_access"])
                self.assertEqual(sg["connectors"], len(p["connectors"] or []))

    def test_no_routing_or_walking_time_in_ui(self):
        import re
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", (APP / "web" / "app.js").read_text(encoding="utf-8"), flags=re.S).lower()
        for bad in ("dijkstra", "isochrone", "мин пешком", "минут пешком", "недостижим"):
            self.assertNotIn(bad, code)


class EvidenceFresh(unittest.TestCase):
    """K03 r5 C6/C7: a moved place or changed K03 code/layer makes evidence.js stale and this is detected without shapely."""

    def _copy(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        app = tmp / "app"
        shutil.copytree(APP, app, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        return app

    def _run(self, app):
        import subprocess
        return subprocess.run([sys.executable, str(app / "tools/check_evidence_fresh.py")], capture_output=True,
                              text=True, encoding="utf-8")

    def test_current_build_is_fresh(self):
        r = self._run(APP)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_moved_place_is_detected(self):
        app = self._copy()
        p = app / "web/data.js"
        t = p.read_text(encoding="utf-8")
        data = json.loads(t[t.index("{"):t.rstrip().rindex(";")])
        data["cities"]["astana"]["places"][0]["lon"] += 0.001
        p.write_text("window.CITY_EVIDENCE = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
        r = self._run(app)
        self.assertEqual(r.returncode, 1)
        self.assertIn("места data.js", r.stdout)

    def test_changed_k03_layer_is_detected(self):
        app = self._copy()
        f = app / "inputs/k03v21_root/data/astana_districts.geojson"
        f.write_bytes(f.read_bytes() + b"\n")
        r = self._run(app)
        self.assertEqual(r.returncode, 1)
        self.assertIn("слой K03", r.stdout)

    def test_place_records_keep_lonlat_and_rule_from_code(self):
        t = (APP / "web/evidence.js").read_text(encoding="utf-8")
        ev = json.loads(t[t.index("{"):t.rstrip().rindex(";")])
        self.assertEqual(ev["assign_rule"], ev["boundary_binding"]["rule"])
        for c in ev["cities"].values():
            self.assertTrue(all("lonlat" in r for r in c["place_district"].values()))
            self.assertEqual({o["method"]["id"] for o in c["observations"] if o["indicator_id"].startswith("k03_district_status.")},
                             {ev["assign_rule"]})


if __name__ == "__main__":
    unittest.main()
