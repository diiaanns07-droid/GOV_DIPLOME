"""Self-tests of the K12 round-5 harness (stdlib only, SYNTHETIC mini inputs; no BUILD needed).
Run from research/round-5-results/K12/:  python -m unittest discover -s tests -v"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

K12 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K12))
import k12r5_negative_build as H  # noqa: E402


def js(var, obj):
    return f"// synthetic\nwindow.{var} = {json.dumps(obj)};\n"


def mini(places=None, release="2026-09-23.1", obs_release="2026-09-23.1", total=None):
    places = places if places is not None else [{"id": "a", "lon": 1.5, "lat": 1.5, "confidence": 0.9}]
    data = {"cities": {"x": {"bbox": [1, 1, 2, 2], "release": release, "places": places,
                             "segments": [{"id": "s", "length_m": 10.0}]}}}
    ids = sorted({p["id"] for p in places})
    ev = {"cities": {"x": {"place_district": {i: {} for i in ids}, "city_mismatch": [],
                           "observations": [{"obs_id": "x/total", "indicator_id": "places.total",
                                             "value": len(places) if total is None else total, "release": obs_release}]}}}
    return js("CITY_EVIDENCE", data), js("CITY_OBS", ev)


class StrictJSON(unittest.TestCase):
    def test_rejects_nonfinite_and_duplicate_keys(self):
        for text, code in (('{"v": NaN}', "JSON_NONFINITE"), ('{"v": Infinity}', "JSON_NONFINITE"),
                           ('{"v": -Infinity}', "JSON_NONFINITE"), ('{"v": 1e999}', "JSON_NONFINITE"),
                           ('{"v": 1, "v": 2}', "JSON_DUPLICATE_KEY")):
            with self.subTest(text=text), self.assertRaisesRegex(H.StrictJSONError, code):
                H.loads_strict(text)

    def test_accepts_normal_and_huge_integer(self):
        self.assertEqual(H.loads_strict('{"v": 1.5, "w": [1, 2]}'), {"v": 1.5, "w": [1, 2]})
        self.assertEqual(H.loads_strict('{"v": 1' + "0" * 400 + "}")["v"], 10 ** 400)


class ArtifactChecks(unittest.TestCase):
    def test_clean_mini_artifacts(self):
        self.assertEqual(H.check_artifacts(*mini()), [])

    def test_each_contamination_is_detected(self):
        d, e = mini()
        cases = {
            "JSON_NONFINITE": (d.replace('"confidence": 0.9', '"confidence": NaN'), e),
            "DUPLICATE_PLACE_ID": mini(places=[{"id": "a", "lon": 1.5, "lat": 1.5}, {"id": "a", "lon": 1.6, "lat": 1.6}]),
            "PLACE_OUTSIDE_BBOX": mini(places=[{"id": "a", "lon": 5.0, "lat": 1.5}]),
            "RELEASE_MISMATCH": mini(obs_release="2026-08-20.0"),
            "PLACES_TOTAL": mini(total=7),
        }
        for code, (dt, et) in cases.items():
            with self.subTest(code=code):
                self.assertTrue(any(code in p for p in H.check_artifacts(dt, et)), H.check_artifacts(dt, et))


class Rehash(unittest.TestCase):
    def test_rehash_makes_both_manifests_consistent(self):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)
            data = app / "inputs/k10/data/x/places_social.geojson"
            data.parent.mkdir(parents=True)
            data.write_text(json.dumps({"features": [{"id": 1}]}), encoding="utf-8")
            pm = app / "inputs/k10/package_manifest.json"
            pm.write_text(json.dumps({"cities": {"x": {"files": {"places_social": {
                "path": "data/x/places_social.geojson", "sha256": "0", "bytes": 0, "features": 0}}}}}), encoding="utf-8")
            (app / "source_manifest.json").write_text(json.dumps({"files": [
                {"copied_to": "inputs/k10/package_manifest.json", "sha256": "0", "bytes": 0},
                {"copied_to": "inputs/k10/data/x/places_social.geojson", "sha256": "0", "bytes": 0}]}), encoding="utf-8")
            data.write_text(json.dumps({"features": [{"id": 1}, {"id": 2}]}), encoding="utf-8")
            H.rehash(app, [data])
            fm = json.loads(pm.read_text(encoding="utf-8"))["cities"]["x"]["files"]["places_social"]
            self.assertEqual((fm["sha256"], fm["bytes"], fm["features"]),
                             (hashlib.sha256(data.read_bytes()).hexdigest(), data.stat().st_size, 2))
            sm = {e["copied_to"]: e for e in json.loads((app / "source_manifest.json").read_text(encoding="utf-8"))["files"]}
            for rel in ("inputs/k10/package_manifest.json", "inputs/k10/data/x/places_social.geojson"):
                self.assertEqual(sm[rel]["sha256"], hashlib.sha256((app / rel).read_bytes()).hexdigest(), rel)

    def test_case_ids_unique_and_kinds_known(self):
        ids = [c["id"] for c in H.CASES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({c["kind"] for c in H.CASES} <= {"control_clean", "integrity", "semantic"})


if __name__ == "__main__":
    unittest.main()
