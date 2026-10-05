"""Tests of the K06 what-if oracle (FEATURE_SPEC round 7).
  python3 test_whatif_oracle.py [--app-root <city-evidence copy>] [-v]
Control values are obtained independently (closed-form arc length on the sphere, or the 3-D chord formula),
tolerance 1e-6 m. Metamorphic tests run on real slice records when --app-root is given, otherwise SKIP.
"""
import math, os, random, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import whatif_oracle as W

TOL = 1e-6
R = W.R_EARTH_M
APP_ROOT = os.environ.get("K06_APP_ROOT")
ASTANA_BB = [71.418372, 51.163033, 71.447, 51.181]


def cp(i, lon, lat):
    return {"id": f"cp{i}", "lon": lon, "lat": lat}


def scen(cat, pts, prop=None):
    return {"schema_version": "city-whatif-v1", "city_id": "astana", "source_snapshot": "test", "category": cat,
            "control_points": pts, "proposed_object": prop}


def proj(lon, lat, cat="school", pid="proj1"):
    return {"id": pid, "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical"}


class Formula(unittest.TestCase):
    def test_same_point_is_exact_zero(self):
        self.assertEqual(W.haversine_m(71.43, 51.17, 71.43, 51.17), 0.0)

    def test_meridian_degree_closed_form(self):          # R * pi/180, exact on the sphere
        self.assertAlmostEqual(W.haversine_m(0, 0, 0, 1), R * math.pi / 180, delta=TOL)

    def test_parallel_arc_at_equator_closed_form(self):
        self.assertAlmostEqual(W.haversine_m(10, 0, 10.5, 0), R * math.radians(0.5), delta=TOL)

    def test_short_arc_closed_form(self):                # 1e-5 deg along a meridian at Astana ~ 1.112 m
        self.assertAlmostEqual(W.haversine_m(71.43, 51.17, 71.43, 51.17001), R * math.radians(1e-5), delta=TOL)

    def test_city_scale_vs_independent_chord(self):
        for a, b in (((71.4184, 51.1631), (71.4469, 51.1809)), ((69.5934, 42.3067), (69.6176, 42.3246))):
            self.assertAlmostEqual(W.haversine_m(*a, *b), W.chord_distance_m(*a, *b), delta=TOL)

    def test_clamp_rounding_above_one(self):
        # unclamped intermediate value is 1.0000000000000002 -> asin(sqrt(a)) would raise ValueError
        p1, p2 = math.radians(-74.6), math.radians(74.6)
        a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(180) / 2) ** 2
        self.assertGreater(a, 1.0)
        self.assertAlmostEqual(W.haversine_m(0, -74.6, 180, 74.6), math.pi * R, delta=TOL)

    def test_lon_lat_order(self):                        # [lon, lat]: swapping changes the answer
        self.assertNotAlmostEqual(W.haversine_m(71.43, 51.17, 71.44, 51.17), W.haversine_m(51.17, 71.43, 51.17, 71.44), delta=1)

    def test_non_finite_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf"), float("1e999")):
            with self.assertRaises(W.ScenarioError):
                W.haversine_m(bad, 51.17, 71.43, 51.17)


class Scenario(unittest.TestCase):
    # exact tie = identical coordinates (the COLOCATED QA case of real data); a symmetric +-dlat pair is NOT an
    # exact tie in floating point, so it is not used for the id rule
    RECS = [{"id": "b", "lon": 71.430, "lat": 51.1702, "group": "school"},
            {"id": "a", "lon": 71.430, "lat": 51.1702, "group": "school"},
            {"id": "c", "lon": 71.440, "lat": 51.1750, "group": "outpatient_clinic"}]

    def test_tie_is_stable_by_id_and_length_unchanged(self):
        rows = W.compute(scen("school", [cp(1, 71.430, 51.1700)]), self.RECS, ASTANA_BB)
        self.assertEqual(rows[0]["nearest_record_id"], "a")
        self.assertAlmostEqual(rows[0]["before_m"], R * math.radians(0.0002), delta=TOL)   # closed form, meridian
        rev = W.compute(scen("school", [cp(1, 71.430, 51.1700)]), list(reversed(self.RECS)), ASTANA_BB)
        self.assertEqual(rows, rev)

    def test_no_project_after_equals_before_delta_zero(self):
        r = W.compute(scen("school", [cp(1, 71.435, 51.172)]), self.RECS, ASTANA_BB)[0]
        self.assertEqual(r["after_m"], r["before_m"]); self.assertEqual(r["delta_m"], 0.0)

    def test_project_on_control_point_gives_honest_zero(self):
        r = W.compute(scen("school", [cp(1, 71.435, 51.172)], proj(71.435, 51.172)), self.RECS, ASTANA_BB)[0]
        self.assertEqual(r["after_m"], 0.0); self.assertEqual(r["delta_m"], r["before_m"])

    def test_no_source_records(self):
        recs = [x for x in self.RECS if x["group"] != "outpatient_clinic"]
        r = W.compute(scen("outpatient_clinic", [cp(1, 71.435, 51.172)], proj(71.436, 51.172, "outpatient_clinic")), recs, ASTANA_BB)[0]
        self.assertIsNone(r["before_m"]); self.assertIsNone(r["delta_m"])
        self.assertAlmostEqual(r["after_m"], W.haversine_m(71.435, 51.172, 71.436, 51.172), delta=TOL)
        self.assertEqual(r["note"], "В срезе нет исходных записей; улучшение не вычисляется")
        r0 = W.compute(scen("outpatient_clinic", [cp(1, 71.435, 51.172)]), recs, ASTANA_BB)[0]
        self.assertEqual((r0["before_m"], r0["after_m"], r0["delta_m"]), (None, None, None))

    def test_rejections(self):
        bad = [scen("school", []),                                                    # 0 control points
               scen("school", [cp(i, 71.43, 51.17) for i in range(11)]),              # 11 control points
               scen("school", [cp(1, 71.43, 51.17), cp(1, 71.431, 51.171)]),          # duplicate id
               scen("school", [cp(1, 71.50, 51.17)]),                                 # outside bbox
               scen("school", [cp(1, float("nan"), 51.17)]),                          # NaN
               scen("school", [cp(1, 71.43, 51.17)], proj(71.43, 51.171, "outpatient_clinic")),  # category mismatch
               scen("school", [cp(1, 71.43, 51.17)], proj(71.60, 51.171)),            # project outside bbox
               scen("hospital", [cp(1, 71.43, 51.17)])]                               # category not in MVP
        for s in bad:
            with self.assertRaises(W.ScenarioError, msg=str(s)[:120]):
                W.compute(s, self.RECS, ASTANA_BB)


class Metamorphic(unittest.TestCase):
    """On real slice records of the BUILD given by --app-root (both cities, both MVP categories)."""
    @classmethod
    def setUpClass(cls):
        if not APP_ROOT:
            raise unittest.SkipTest("--app-root not given")
        from make_fixture import load
        cls.D, _ = load(APP_ROOT)

    def each(self):
        rng = random.Random(7)
        for city in self.D["city_order"]:
            c = self.D["cities"][city]; bb = c["bbox"]
            recs = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"]} for p in c["places"]]
            for cat in W.CATEGORIES:
                for _ in range(25):
                    pts = [cp(i, rng.uniform(bb[0], bb[2]), rng.uniform(bb[1], bb[3])) for i in range(rng.randint(1, 10))]
                    prop = proj(rng.uniform(bb[0], bb[2]), rng.uniform(bb[1], bb[3]), cat)
                    yield city, cat, bb, recs, pts, prop, rng

    def test_after_le_before(self):
        for city, cat, bb, recs, pts, prop, _ in self.each():
            for r in W.compute(scen(cat, pts, prop), recs, bb):
                self.assertLessEqual(r["after_m"], r["before_m"]); self.assertGreaterEqual(r["delta_m"], 0.0)

    def test_remove_restores_baseline(self):
        for city, cat, bb, recs, pts, prop, _ in self.each():
            base = W.compute(scen(cat, pts), recs, bb)
            W.compute(scen(cat, pts, prop), recs, bb)
            self.assertEqual(W.compute(scen(cat, pts), recs, bb), base)

    def test_farther_project_changes_nothing(self):
        for city, cat, bb, recs, pts, prop, _ in self.each():
            base = W.compute(scen(cat, pts), recs, bb)
            rows = W.compute(scen(cat, pts, prop), recs, bb)
            for b, r, p in zip(base, rows, pts):
                if W.haversine_m(p["lon"], p["lat"], prop["lon"], prop["lat"]) >= b["before_m"]:
                    self.assertEqual((r["after_m"], r["delta_m"], r["nearest_record_id"]), (b["after_m"], 0.0, b["nearest_record_id"]))

    def test_move_equals_fresh_compute(self):
        for city, cat, bb, recs, pts, prop, rng in self.each():
            moved = dict(prop, lon=rng.uniform(bb[0], bb[2]), lat=rng.uniform(bb[1], bb[3]))
            W.compute(scen(cat, pts, prop), recs, bb)
            self.assertEqual(W.compute(scen(cat, pts, moved), recs, bb), W.compute(scen(cat, pts, moved), list(recs), bb))

    def test_record_order_invariance(self):
        for city, cat, bb, recs, pts, prop, rng in self.each():
            sh = recs[:]; rng.shuffle(sh)
            self.assertEqual(W.compute(scen(cat, pts, prop), recs, bb), W.compute(scen(cat, pts, prop), sh, bb))

    def test_independent_chord_agrees_on_real_records(self):
        for city, cat, bb, recs, pts, prop, _ in self.each():
            for p in pts:
                d, rec = W.nearest(p, [r for r in recs if r["group"] == cat])
                self.assertAlmostEqual(d, W.chord_distance_m(p["lon"], p["lat"], rec["lon"], rec["lat"]), delta=TOL)


if __name__ == "__main__":
    if "--app-root" in sys.argv:
        i = sys.argv.index("--app-root"); APP_ROOT = sys.argv[i + 1]; del sys.argv[i:i + 2]
    unittest.main()
