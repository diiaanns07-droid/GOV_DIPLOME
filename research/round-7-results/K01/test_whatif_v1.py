"""K01 round-7 tests for whatif_v1.py + fixtures. Needs an extracted prototype:
  K01_APP_ROOT=/path/city-evidence python3 -m unittest test_whatif_v1 -v
"""
import copy, json, math, os, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import whatif_v1 as W  # noqa: E402

APP = os.environ.get("K01_APP_ROOT")
FX = HERE / "fixtures"
EXP = json.loads((FX / "EXPECTED.json").read_text(encoding="utf-8"))


@unittest.skipUnless(APP and (Path(APP) / "web/data.js").exists(), "set K01_APP_ROOT to an extracted prototype")
class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = W.load_slice(APP)

    def test_fixtures_match_expected(self):
        for name, exp in EXP.items():
            if name == "note":
                continue
            with self.subTest(name):
                raw = (FX / name).read_bytes()
                try:
                    sc, notes = W.load_scenario(raw, self.data)
                    got = {"valid": True, "points": len(sc["control_points"]), "has_project": sc["proposed_object"] is not None}
                    self.assertTrue(exp["valid"], f"accepted: {name}")
                    self.assertEqual(got["points"], exp["points"]); self.assertEqual(got["has_project"], exp["has_project"])
                    if exp.get("untrusted_computed_ignored"):
                        self.assertTrue(notes)
                        rows = W.compute(sc, self.data)["rows"]
                        self.assertEqual(rows[0]["delta_m"], 0.0)          # file said 999999
                        self.assertNotEqual(rows[0]["before_m"], 1)
                except W.ScenarioError as e:
                    self.assertFalse(exp["valid"], f"rejected {name}: {e}")
                    self.assertIn(e.code, exp.get("code_one_of", [exp.get("code")]))

    def _base(self):
        return json.loads((FX / "valid_shymkent_school_project.json").read_text(encoding="utf-8"))

    def _rej(self, obj, code, raw=None):
        with self.assertRaises(W.ScenarioError) as cm:
            W.load_scenario(raw if raw is not None else json.dumps(obj).encode(), self.data)
        self.assertEqual(cm.exception.code, code, str(cm.exception))

    def test_snapshot_is_content_bound(self):
        d2 = copy.deepcopy(self.data)
        d2["cities"]["shymkent"]["places"][0]["lon"] += 1e-6
        self.assertNotEqual(W.snapshot_id(d2, "shymkent"), W.snapshot_id(self.data, "shymkent"))
        d3 = copy.deepcopy(self.data); d3["cities"]["shymkent"]["files"]["places_social"]["sha256"] = "0" * 64
        self.assertNotEqual(W.snapshot_id(d3, "shymkent"), W.snapshot_id(self.data, "shymkent"))
        self.assertNotEqual(W.snapshot_id(self.data, "shymkent"), W.snapshot_id(self.data, "astana"))

    def test_size_limit(self):
        b = self._base()
        raw = json.dumps(b).encode()
        pad = raw[:-1] + b" " * (W.MAX_BYTES - len(raw)) + b"}"
        self.assertEqual(len(pad), W.MAX_BYTES)
        W.load_scenario(pad, self.data)                       # exactly 256 KiB accepted
        self._rej(None, "too_large", raw=pad[:-1] + b" }")     # 256 KiB + 1 rejected

    def test_coordinates_ids_category_shape(self):
        b = self._base()
        for mut, code in [
            (lambda o: o["control_points"][0].update(lon=True), "coord"),
            (lambda o: o["control_points"][0].update(lat="42.31"), "coord"),
            (lambda o: o["control_points"][0].update(lon=69.5), "outside_bbox"),
            (lambda o: o["control_points"][1].update(id="cp-1"), "duplicate_id"),
            (lambda o: o["proposed_object"].update(id="cp-2"), "duplicate_id"),
            (lambda o: o["control_points"][0].update(id="x" * 65), "id"),
            (lambda o: o["control_points"][0].update(id="C:\\Users\\a"), "id"),
            (lambda o: o["control_points"][0].update(extra=1), "shape"),
            (lambda o: o.update(control_points=[]), "points"),
            (lambda o: o.update(control_points=[{"id": f"p{i}", "lon": 69.6, "lat": 42.31} for i in range(11)]), "points"),
            (lambda o: o.update(proposed_object=[o["proposed_object"]] * 2), "project"),
            (lambda o: o["proposed_object"].update(kind="planned"), "project"),
            (lambda o: o.update(category="hospital"), "category"),
            (lambda o: o["proposed_object"].update(category="outpatient_clinic"), "category"),
            (lambda o: o.update(source_snapshot="places_social.geojson"), "snapshot"),
            (lambda o: o.update(city_id="almaty"), "city"),
            (lambda o: o.update(schema_version="city-whatif-v2"), "version"),
            (lambda o: o.update(script="<script>alert(1)</script>"), "shape"),
        ]:
            o = copy.deepcopy(b); mut(o)
            with self.subTest(code=code):
                self._rej(o, code)
        self._rej(None, "non_finite", raw=b'{"a": Infinity}')
        self._rej(None, "json", raw=b"{")
        self._rej(None, "encoding", raw=b'{"a":"\xff"}')

    def test_rejected_import_keeps_state(self):
        st = W.ScenarioStore(self.data)
        self.assertTrue(st.import_bytes((FX / "valid_shymkent_school_project.json").read_bytes()))
        before = copy.deepcopy(st.active)
        for name in [n for n in EXP if n.startswith("invalid_")]:
            self.assertFalse(st.import_bytes((FX / name).read_bytes()))
            self.assertEqual(st.active, before, name)
            self.assertIn("не изменён", st.message)
        st.switch("astana", "school")
        self.assertIsNone(st.active)

    def test_export_roundtrip_portable(self):
        sc, _ = W.load_scenario((FX / "valid_shymkent_school_project.json").read_bytes(), self.data)
        txt = W.export(sc, self.data)
        self.assertNotIn(str(Path(APP).resolve()), txt); self.assertNotIn(str(Path.home()), txt)
        for bad in ("/home/", "/tmp/", "C:\\", "file://", "http"):
            self.assertNotIn(bad, txt)
        sc2, notes = W.load_scenario(txt.encode("utf-8"), self.data)   # computed ignored, same scenario
        self.assertEqual(sc2, sc); self.assertTrue(notes)
        self.assertEqual(W.explanation_digest(sc2, self.data), W.explanation_digest(sc, self.data))

    def test_compute_rules(self):
        sc, _ = W.load_scenario((FX / "valid_shymkent_school_project.json").read_bytes(), self.data)
        rows = W.compute(sc, self.data)["rows"]
        for r in rows:
            self.assertLessEqual(r["after_m"], r["before_m"]); self.assertGreaterEqual(r["delta_m"], 0)
            self.assertAlmostEqual(r["delta_m"], r["before_m"] - r["after_m"], places=9)
        # project on a control point -> honest 0
        sc0 = copy.deepcopy(sc); sc0["proposed_object"].update(lon=rows and sc["control_points"][0]["lon"], lat=sc["control_points"][0]["lat"])
        self.assertEqual(W.compute(sc0, self.data)["rows"][0]["after_m"], 0.0)
        # removing the project restores baseline, delta 0
        sc1 = dict(sc, proposed_object=None)
        for a, b in zip(W.compute(sc1, self.data)["rows"], rows):
            self.assertEqual(a["after_m"], b["before_m"]); self.assertEqual(a["delta_m"], 0.0)
        # no source records in the slice -> before null, delta null
        d2 = copy.deepcopy(self.data); d2["cities"]["shymkent"]["places"] = [p for p in d2["cities"]["shymkent"]["places"] if p["group"] != "school"]
        r = W.compute(sc, d2)["rows"][0]
        self.assertIsNone(r["before_m"]); self.assertIsNone(r["delta_m"]); self.assertIsNotNone(r["after_m"]); self.assertIn("не вычисляется", r["note"])
        # digest changes with project position
        self.assertNotEqual(W.explanation_digest(sc, self.data), W.explanation_digest(sc0, self.data))

    def test_haversine_reference(self):
        self.assertEqual(W.haversine_m(69.6, 42.31, 69.6, 42.31), 0.0)
        # 1 degree of latitude on R=6371008.8: pi*R/180
        self.assertAlmostEqual(W.haversine_m(0, 0, 0, 1), math.pi * W.R_EARTH_M / 180, places=6)
        self.assertAlmostEqual(W.haversine_m(0, 0, 180, 0), math.pi * W.R_EARTH_M, places=3)   # antipodal clamp


if __name__ == "__main__":
    unittest.main(verbosity=2)
