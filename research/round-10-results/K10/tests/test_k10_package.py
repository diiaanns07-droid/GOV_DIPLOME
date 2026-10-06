"""K10 round 10: tests of the Astana school-access package, the strict validator and the transfer check.

    python -m unittest discover -s research/round-10-results/K10/tests -v      (repo root; stdlib only)
The rebuild test needs shapely + pyproj and is skipped without them (the skip is reported, not counted as a pass).
"""
import copy
import json
import random
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K / "scripts"))
import k10case as KC  # noqa: E402

PKG = K / "package"
CASE = json.loads((PKG / "astana.case.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((PKG / "MANIFEST.json").read_text(encoding="utf-8"))
B = MANIFEST["buffer"]["B_m"]
SYN = json.loads((K / "tests/fixtures/shymkent.synthetic-min.case.json").read_text(encoding="utf-8"))


def mutate(f):
    c = copy.deepcopy(CASE)
    f(c)
    return c


MUTATIONS = {
    "unknown top field": (lambda c: c.__setitem__("notes", "x"), "unknown_field"),
    "derived results inside": (lambda c: c.__setitem__("model_assumptions", c["model_assumptions"] + [{"id": "A-x", "text": "x", "plans": []}]), None),
    "result field in a school": (lambda c: c["schools"][0]["field_provenance"].__setitem__("before_mm", 5), "derived_field"),
    "schema": (lambda c: c.__setitem__("schema_version", "school-access-case-v2"), "bad_schema"),
    "city": (lambda c: c.__setitem__("city_id", "almaty"), "bad_city"),
    "inverted bbox": (lambda c: c.__setitem__("bbox", [c["bbox"][2], c["bbox"][1], c["bbox"][0], c["bbox"][3]]), "bad_bbox"),
    "origin outside bbox": (lambda c: c["origins"][0].__setitem__("lon", c["bbox"][2] + 0.01), "outside_bbox"),
    "26 origins": (lambda c: c.__setitem__("origins", c["origins"] + [dict(c["origins"][0], id=f"x{i}") for i in range(3)]), "bad_origins"),
    "17 candidates": (lambda c: c.__setitem__("candidates", [dict(c["candidates"][0], id=f"h{i}") for i in range(17)]), "bad_candidates"),
    "candidate observed": (lambda c: c["candidates"][0].__setitem__("kind", "observed"), "bad_kind"),
    "cost without source": (lambda c: c["candidates"][0].__setitem__("cost", {"value": 1, "currency": "KZT", "period": "2026", "kind": "estimate", "source_ids": ["nope"]}), "bad_cost"),
    "land free without source": (lambda c: c["candidates"][0].__setitem__("land_status", "free"), "bad_land_status"),
    "capacity without source": (lambda c: c["schools"][0].__setitem__("capacity", 500), "bad_capacity"),
    "eligibility value": (lambda c: c["schools"][0].__setitem__("access_eligibility", "public"), "bad_eligibility"),
    "school kind hypothesis": (lambda c: c["schools"][0].__setitem__("kind", "hypothesis"), "bad_kind"),
    "duplicate id across lists": (lambda c: c["origins"][0].__setitem__("id", c["schools"][0]["id"]), "duplicate_id"),
    "unknown source id": (lambda c: c["schools"][0].__setitem__("source_ids", ["no-such-source"]), "unknown_source"),
    "not_fetched with hash": (lambda c: next(s for s in c["sources"] if s["verification_status"] == "not_fetched").__setitem__("content_sha256", "0" * 64), "bad_source"),
    "threshold 0": (lambda c: c["parameters"].__setitem__("threshold_m", 0), "bad_parameters"),
    "threshold float": (lambda c: c["parameters"].__setitem__("threshold_m", 800.5), "bad_parameters"),
    "max_new_objects 2": (lambda c: c["parameters"].__setitem__("max_new_objects", 2), "bad_parameters"),
    "two selected": (lambda c: c.__setitem__("selected_candidate_ids", [c["candidates"][0]["id"], c["candidates"][1]["id"]]), "bad_selection"),
    "unknown selected": (lambda c: c.__setitem__("selected_candidate_ids", ["ast-hyp-z"]), "bad_selection"),
    "method network": (lambda c: c["parameters"].__setitem__("distance_method", "network"), "bad_parameters"),
    "geodesic with policy": (lambda c: c["parameters"].__setitem__("routing_policy_id", "ped-1"), "bad_parameters"),
    "label control char": (lambda c: c["schools"][0].__setitem__("label", "a\u0007b"), "bad_text"),
    "qa not object": (lambda c: c["schools"][0].__setitem__("qa", ["x"]), "bad_qa"),
    "unequal weights": (lambda c: c["origins"][0].__setitem__("weight", 2), "bad_weight"),
    "derived origin without parent": (lambda c: c["origins"][0].__setitem__("parent_source_id", None), "bad_origin"),
    "missing field": (lambda c: c["schools"][0].pop("capacity_source_ids"), "missing_field"),
    "extra record field": (lambda c: c["schools"][0].__setitem__("population", 1200), "unknown_field"),
    "nan coordinate": (lambda c: c["schools"][0].__setitem__("lat", float("nan")), "bad_coordinates"),
    "assumption duplicate id": (lambda c: c["model_assumptions"].append(dict(c["model_assumptions"][0])), "bad_assumptions"),
}


class Package(unittest.TestCase):
    def test_case_valid_with_buffer(self):
        s = KC.validate_case(CASE, (PKG / "astana.case.json").read_bytes(), max_school_buffer_m=B)
        self.assertEqual(s["city_id"], "astana")
        self.assertEqual(s, MANIFEST["validation"])

    def test_mutations_refused_atomically(self):
        for name, (f, code) in MUTATIONS.items():
            with self.subTest(name=name):
                c = mutate(f)
                before = json.dumps(c, sort_keys=True, default=str)
                with self.assertRaises(KC.CaseError) as cm:
                    KC.validate_case(c)
                if code:
                    self.assertEqual(cm.exception.code, code, cm.exception)
                self.assertEqual(json.dumps(c, sort_keys=True, default=str), before)  # the validator never edits input

    def test_school_outside_declared_buffer_refused(self):
        c = mutate(lambda c: c["schools"][0].update(lon=c["bbox"][2] + 0.05))
        with self.assertRaises(KC.CaseError) as cm:
            KC.validate_case(c, max_school_buffer_m=B)
        self.assertEqual(cm.exception.code, "outside_buffer")

    def test_too_large_refused_before_parse(self):
        with self.assertRaises(KC.CaseError) as cm:
            KC.validate_case(CASE, b" " * (KC.LIMITS["bytes"] + 1))
        self.assertEqual(cm.exception.code, "too_large")

    def test_digest_order_independent_and_sensitive(self):
        d0 = KC.case_digest_k10(CASE)
        self.assertEqual(d0, MANIFEST["case_digest_k10"])
        rnd = random.Random(7)
        for _ in range(5):
            c = copy.deepcopy(CASE)
            for k in ("sources", "schools", "origins", "candidates", "model_assumptions"):
                rnd.shuffle(c[k])
            for r in c["schools"]:
                rnd.shuffle(r["source_ids"]); rnd.shuffle(r["qa"])
            self.assertEqual(KC.case_digest_k10(c), d0)
        for name, f in {"coordinate": lambda c: c["schools"][0].update(lon=c["schools"][0]["lon"] + 1e-6),
                        "eligibility": lambda c: c["schools"][0].update(access_eligibility="unknown" if c["schools"][0]["access_eligibility"] != "unknown" else "known_public"),
                        "threshold": lambda c: c["parameters"].update(threshold_m=801), "qa": lambda c: c["schools"][0]["qa"].append({"code": "x", "text": "y"}),
                        "snapshot": lambda c: c.update(snapshot_id="other"), "source hash": lambda c: c["sources"][0].update(content_sha256="1" * 64),
                        "method": lambda c: c["parameters"].update(distance_method="pedestrian-v1", routing_policy_id="p1")}.items():
            with self.subTest(change=name):
                self.assertNotEqual(KC.case_digest_k10(mutate(f)), d0)
        self.assertEqual(KC.case_digest_k10(mutate(lambda c: c["schools"][0].update(label="другая подпись"))), d0)  # labels are presentation

    def test_honesty_invariants(self):
        txt = (PKG / "astana.case.json").read_text(encoding="utf-8") + "".join((PKG / f).read_text(encoding="utf-8") for f in ("schools.json", "evidence.json", "match-review.json", "sources.json"))
        self.assertNotRegex(txt, r'"(phone|email|contact:phone|contact:email)"')
        self.assertNotRegex(txt, r"\+7 ?\(?7172")
        # the training model is named only to say that its numbers are not mixed in (assumption A-realm)
        realm = next(a["text"] for a in CASE["model_assumptions"] if a["id"] == "A-realm")
        self.assertIn("52.56", realm)
        for line in txt.splitlines():
            if "52.56" in line:
                self.assertRegex(line, r"Не учебная модель 52\.56|not 52\.56 training model", "52.56 may appear only as a negation")
        self.assertNotRegex(txt, r'"(score|Score|budget_tenge|population|students)"')
        self.assertFalse(any(s["verification_status"] == "primary_checked" for s in CASE["sources"]))
        mr = json.loads((PKG / "match-review.json").read_text(encoding="utf-8"))
        self.assertEqual(mr["summary"]["verified_against_official_source"], 0)
        for s in CASE["sources"]:
            if s["verification_status"] == "not_fetched":
                self.assertIsNone(s["content_sha256"]); self.assertIsNone(s["retrieved_at"])
        for r in CASE["schools"]:
            self.assertEqual(r["kind"], "observed_secondary")
            self.assertIsNone(r["capacity"])
            self.assertTrue(r["source_ids"])
            self.assertIn("no_official_verification", [q["code"] for q in r["qa"]])
            if r["access_eligibility"] == "known_public":
                self.assertIn("eligibility_inferred_from_name", [q["code"] for q in r["qa"]])
        for r in CASE["origins"]:
            self.assertEqual(r["kind"], "derived"); self.assertEqual(r["weight"], 1)
            self.assertIn("not_population", [q["code"] for q in r["qa"]])
        for r in CASE["candidates"]:
            self.assertEqual(r["kind"], "hypothesis"); self.assertIsNone(r["cost"]); self.assertEqual(r["land_status"], "unknown")
            self.assertIn("not_a_land_plot", [q["code"] for q in r["qa"]])
        self.assertEqual(CASE["selected_candidate_ids"], [])
        self.assertTrue(2 <= len(CASE["candidates"]) <= 3)

    def test_every_slice_record_reviewed(self):
        app = json.loads((K / "inputs/app_slice_astana.json").read_text(encoding="utf-8"))
        slice_ids = {p["id"] for p in app["places_school_and_preschool"] if p["group"] == "school"}
        mr = json.loads((PKG / "match-review.json").read_text(encoding="utf-8"))
        reviewed = {r["record_id"]: r for r in mr["poi_records"] if r["in_app_slice"]}
        self.assertEqual(set(reviewed), slice_ids)
        self.assertEqual(len(slice_ids), 8)
        for r in reviewed.values():
            self.assertEqual(r["decided_by"], "manual_review")
        for r in mr["poi_records"]:
            self.assertIn(r["decision"], {"attach", "conflict_not_target", "not_school", "include_meta_only", "duplicate_of", "unresolved_excluded"})

    def test_rebuild_is_byte_identical(self):
        try:
            import pyproj  # noqa: F401
            import shapely  # noqa: F401
        except ImportError:
            self.skipTest("shapely/pyproj not installed: rebuild NOT_RUN")
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, str(K / "scripts/build_astana_package.py"), "--out", d], check=True, capture_output=True)
            for f in ("sources.json", "schools.json", "evidence.json", "match-review.json", "astana.case.json"):
                self.assertEqual((Path(d) / f).read_bytes(), (PKG / f).read_bytes(), f)


class Transfer(unittest.TestCase):
    def test_synthetic_fixture_is_valid_and_labelled(self):
        KC.validate_case(SYN)
        self.assertTrue(all(r["kind"] == "synthetic" for k in ("schools", "origins", "candidates") for r in SYN[k]))
        self.assertIn("SYNTHETIC", SYN["title"])

    def test_switch_replaces_everything(self):
        self.assertEqual([f for f in KC.transfer_check(SYN, CASE) if not f["code"].endswith("_info")], [])
        self.assertEqual([f for f in KC.transfer_check(CASE, SYN) if not f["code"].endswith("_info")], [])

    def test_checker_has_teeth(self):
        codes = {f["code"] for f in KC.transfer_check(CASE, CASE)}
        self.assertTrue({"same_city", "same_snapshot", "same_bbox", "same_digest", "shared_record_ids", "shared_coordinates", "shared_source_ids"} <= codes)
        leaky = copy.deepcopy(CASE)
        leaky["schools"].append(copy.deepcopy(SYN["schools"][0]))  # a Shymkent school left in the Astana case
        leaky["sources"].append(copy.deepcopy(SYN["sources"][0]))
        codes = {f["code"] for f in KC.transfer_check(SYN, leaky)}
        self.assertIn("shared_record_ids", codes)
        self.assertIn("far_from_bbox", codes)


if __name__ == "__main__":
    unittest.main()
