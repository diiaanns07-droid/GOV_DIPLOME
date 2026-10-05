"""K08 R7: тесты эталона происхождения сценария city-whatif-v1.

Usage: python test_whatif_provenance.py --app-root <prototypes/city-evidence> [-v]
Работает на копии app-root во временной папке; исходная папка не меняется.
Тест «нет исходных записей» использует synthetic-копию data.js (записи категории удалены) — помечен как synthetic.
"""
import argparse
import copy
import json
import math
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import whatif_provenance as W  # noqa: E402

APP_ROOT = None
FIELDS = json.loads((HERE / "provenance_fields.json").read_text(encoding="utf-8"))


def scenario(app, city="shymkent", cat="school", cps=None, po="default"):
    snap, _ = app.snapshot(city)
    bb = app.city(city)["bbox"]
    mid = [(bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2]
    cps = cps or [{"id": "cp1", "lon": mid[0], "lat": mid[1]}]
    if po == "default":
        po = {"id": "proj1", "lon": bb[0] + (bb[2] - bb[0]) * 0.1, "lat": bb[1] + (bb[3] - bb[1]) * 0.1, "category": cat, "kind": "hypothetical"}
    return {"schema_version": "city-whatif-v1", "city_id": city, "source_snapshot": snap, "category": cat,
            "control_points": cps, "proposed_object": po}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.TemporaryDirectory()
        cls.root = Path(cls.td.name) / "app"
        shutil.copytree(APP_ROOT, cls.root, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        cls.app = W.App(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()


class TestSnapshot(Base):
    def test_modified_places_bytes_rejected(self):
        root2 = Path(self.td.name) / "app2"
        shutil.copytree(self.root, root2)
        f = self.app.manifest["cities"]["shymkent"]["files"]["places_social"]
        p = root2 / "inputs/k10" / f["path"]
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaises(W.ScenarioError):  # sha256/bytes не совпадают с manifest — не принимать
            W.App(root2).snapshot("shymkent")

    def test_snapshot_not_from_filename(self):
        s, basis = self.app.snapshot("astana")
        self.assertTrue(s.startswith("sha256:") and len(s) == 71)
        self.assertEqual(basis["places_file"]["sha256"], self.app.manifest["cities"]["astana"]["files"]["places_social"]["sha256"])
        self.assertIn("calc", basis)

    def test_cities_differ(self):
        self.assertNotEqual(self.app.snapshot("shymkent")[0], self.app.snapshot("astana")[0])


class TestValidation(Base):
    def rej(self, sc):
        with self.assertRaises(W.ScenarioError):
            W.validate(self.app, sc)

    def test_foreign_snapshot(self):
        sc = scenario(self.app); sc["source_snapshot"] = self.app.snapshot("astana")[0]; self.rej(sc)

    def test_unknown_version_city_category(self):
        for k, v in (("schema_version", "city-whatif-v2"), ("city_id", "almaty"), ("category", "hospital")):
            sc = scenario(self.app); sc[k] = v; self.rej(sc)

    def test_points_bounds_and_count(self):
        bb = self.app.city("shymkent")["bbox"]
        self.rej(scenario(self.app, cps=[{"id": "x", "lon": bb[2] + 0.01, "lat": bb[1]}]))
        self.rej(scenario(self.app, cps=[{"id": f"p{i}", "lon": bb[0], "lat": bb[1]} for i in range(11)]))
        sc = scenario(self.app); sc["control_points"] = []; self.rej(sc)

    def test_duplicate_ids_and_two_projects(self):
        self.rej(scenario(self.app, cps=[{"id": "proj1", "lon": self.app.city("shymkent")["bbox"][0], "lat": self.app.city("shymkent")["bbox"][1]}]))
        sc = scenario(self.app); sc["proposed_object"] = [sc["proposed_object"], dict(sc["proposed_object"], id="p2")]; self.rej(sc)

    def test_project_category_and_kind(self):
        sc = scenario(self.app); sc["proposed_object"]["category"] = "outpatient_clinic"; self.rej(sc)
        sc = scenario(self.app); sc["proposed_object"]["kind"] = "planned"; self.rej(sc)

    def test_strict_json(self):
        good = json.dumps(scenario(self.app))
        for bad in (good.replace('"lon": ', '"lon": NaN, "x": ', 1), good[:-1] + ', "a": 1e999}',
                    good[:-1] + ', "city_id": "astana"}', "[" * 10 + " " * (300 * 1024) + "]" * 10):
            with self.assertRaises(W.ScenarioError):
                W.loads_strict(bad)


class TestCard(Base):
    def test_imported_results_ignored(self):
        sc = scenario(self.app)
        clean = W.build_card(self.app, sc)
        sc["report"] = {"rows": [{"before_m": 1, "after_m": 0, "delta_m": 999999}]}
        self.assertEqual(W.build_card(self.app, sc)["rows"], clean["rows"])

    def test_no_project_delta_zero(self):
        card = W.build_card(self.app, scenario(self.app, po=None))
        for r in card["rows"]:
            self.assertEqual(r["after_m"], r["before_m"]); self.assertEqual(r["delta_m"], 0)

    def test_after_le_before_and_delta(self):
        card = W.build_card(self.app, scenario(self.app))
        for r in card["rows"]:
            self.assertLessEqual(r["after_m"], r["before_m"])
            self.assertAlmostEqual(r["delta_m"], r["before_m"] - r["after_m"])

    def test_same_point_zero(self):
        rec = next(p for p in self.app.city("shymkent")["places"] if p["group"] == "school")
        card = W.build_card(self.app, scenario(self.app, cps=[{"id": "cp1", "lon": rec["lon"], "lat": rec["lat"]}], po=None))
        self.assertEqual(card["rows"][0]["before_m"], 0.0)

    def test_haversine_reference(self):
        # 1° широты по меридиану = R*pi/180; порядок входа [lon, lat]
        self.assertAlmostEqual(W.haversine_m([69.6, 42.0], [69.6, 43.0]), 6371008.8 * math.pi / 180, places=6)
        self.assertEqual(W.haversine_m([69.6, 42.3], [69.6, 42.3]), 0.0)

    def test_tie_stable_by_id(self):
        a = W._nearest([0, 0], [{"id": "b", "lon": 1, "lat": 0}, {"id": "a", "lon": -1, "lat": 0}])
        self.assertEqual(a[1]["id"], "a")

    def test_provenance_present_for_nearest(self):
        for city, cat in (("shymkent", "school"), ("astana", "outpatient_clinic")):
            card = W.build_card(self.app, scenario(self.app, city, cat))
            self.assertEqual(card["source"]["snapshot"], self.app.snapshot(city)[0])
            self.assertTrue(card["scope"]["bbox"] and card["scope"]["records_in_slice"] > 0)
            for r in card["rows"]:
                nb = r["nearest_before"]
                self.assertEqual(nb["kind"], "source_record")
                self.assertTrue(nb["sources"] and all(s.get("license") and s.get("dataset") for s in nb["sources"]))
                self.assertIn("flags", nb["qa"])

    def test_qa_flag_kept_not_removed(self):
        q = self.app.obs["cities"]["shymkent"]["qa"]["category_doubt"]
        rid = next(iter(q))
        rec = next(p for p in self.app.city("shymkent")["places"] if p["id"] == rid)
        card = W.build_card(self.app, scenario(self.app, cat=rec["group"], cps=[{"id": "cp1", "lon": rec["lon"], "lat": rec["lat"]}], po=None))
        nb = card["rows"][0]["nearest_before"]
        self.assertEqual(nb["id"], rid); self.assertTrue(nb["qa"]["flags"])

    def test_no_forbidden_claims(self):
        card = W.build_card(self.app, scenario(self.app))
        text = json.dumps({k: v for k, v in card.items() if k not in ("limitations",)}, ensure_ascii=False).lower()
        for w in FIELDS["forbidden_claims"]:
            self.assertNotIn(w, text, w)
        self.assertIn("не доказательство пользы", card["scenario"]["status"])

    def test_card_fields_cover_registry(self):
        card = W.build_card(self.app, scenario(self.app))
        for f in FIELDS["card_fields"]:
            top = f["path"].split(".")[0].split("[")[0]
            self.assertIn(top, card, f["path"])

    def test_synthetic_no_source_records(self):
        """synthetic: из копии data.js удалены все школы — before=null, after=до проекта, delta=null."""
        root3 = Path(self.td.name) / "app3"
        shutil.copytree(self.root, root3)
        p = root3 / "web/data.js"
        txt = p.read_text(encoding="utf-8")
        m = re.search(r"(window\.CITY_EVIDENCE\s*=\s*)(\{.*\})(\s*;?\s*)$", txt, re.S)
        d = json.loads(m.group(2))
        d["cities"]["shymkent"]["places"] = [x for x in d["cities"]["shymkent"]["places"] if x["group"] != "school"]
        p.write_text(txt[:m.start(2)] + json.dumps(d, ensure_ascii=False) + m.group(3), encoding="utf-8")
        app3 = W.App(root3)
        r = W.build_card(app3, scenario(app3))["rows"][0]
        self.assertIsNone(r["before_m"]); self.assertIsNone(r["delta_m"])
        self.assertTrue(math.isfinite(r["after_m"])); self.assertEqual(r["note"], W.NO_BASE_TEXT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    a, rest = ap.parse_known_args()
    APP_ROOT = Path(a.app_root).resolve()
    unittest.main(argv=[sys.argv[0]] + rest)
