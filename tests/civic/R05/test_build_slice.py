"""R05 slice builder: determinism, claim->source linkage, refusal of unsupported values."""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PKG = os.path.join(REPO, "data", "civic", "astana")
sys.path.insert(0, os.path.join(PKG, "tools"))

import build_slice as bs  # noqa: E402
import civic_v1 as cv  # noqa: E402

FETCHED = {
    "id": "src-test-news", "url": "https://example.org/astana/news/42", "role": "official_announcement",
    "publisher": "Example publisher", "publisher_basis": "stated_on_page", "title": "Test",
    "published_on": "2026-09-28", "retrieved_at": "2026-10-06T09:00:00Z", "access_status": "fetched",
    "access_attempts": [{"at": "2026-10-06T09:00:00Z", "outcome": "fetched"}],
    "sha256": "0" * 64, "license": None, "license_status": "unknown", "supports": [], "notes": "test fixture",
}
NOT_FETCHED = dict(FETCHED, id="src-test-blocked", access_status="not_fetched", retrieved_at=None, sha256=None)

INTAKE = {
    "intake_version": "r05-intake-v1",
    "id": "ast-r05-test-street-repair",
    "kind": "roadworks",
    "title": "Ремонт тестовой улицы",
    "description": "Тестовая запись.",
    "geometry": None,
    "geometry_precision": "unknown",
    "claims": [
        {"field": "schedule.planned_start", "value": "2026-10-01", "source_id": "src-test-news",
         "claim_type": "stated", "quote": "работы начнутся 1 октября", "locator": "абзац 1"},
        {"field": "schedule.original_planned_end", "value": "2026-11-15", "source_id": "src-test-news",
         "claim_type": "expected", "quote": "завершим к 15 ноября", "locator": "абзац 2"},
        {"field": "schedule.current_planned_end", "value": "2026-11-15", "source_id": "src-test-news",
         "claim_type": "expected", "quote": "завершим к 15 ноября", "locator": "абзац 2"},
        {"field": "budget.amount_kzt", "value": 250000000, "source_id": "src-test-news",
         "claim_type": "stated", "quote": "250 млн тенге", "locator": "абзац 3"},
        {"field": "budget.basis", "value": "planned", "source_id": "src-test-news",
         "claim_type": "stated", "quote": "выделено 250 млн тенге", "locator": "абзац 3"},
    ],
    "evidence_notes": "Источник сообщает плановые сроки; фактическое состояние не сообщается.",
    "reviewed_at": "2026-10-06T09:30:00Z",
}


class TempPackage:
    def __init__(self, sources, intakes, demo=None, as_of="2026-10-06"):
        self.dir = tempfile.mkdtemp(prefix="r05pkg-")
        shutil.copy(os.path.join(PKG, "geofence.json"), self.dir)
        os.makedirs(os.path.join(self.dir, "intake", "real"))
        os.makedirs(os.path.join(self.dir, "intake", "demo"))
        with open(os.path.join(self.dir, "slice_config.json"), "w", encoding="utf-8") as fh:
            json.dump({"as_of": as_of, "historical_cutoff_days": 365, "status_max_age_days": 45}, fh)
        with open(os.path.join(self.dir, "sources.json"), "w", encoding="utf-8") as fh:
            json.dump({"schema": "r05-sources-v1", "sources": sources}, fh, ensure_ascii=False)
        for i, rec in enumerate(intakes):
            with open(os.path.join(self.dir, "intake", "real", f"{i:03d}.json"), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False)
        if demo is not None:
            with open(os.path.join(self.dir, "intake", "demo", "d.json"), "w", encoding="utf-8") as fh:
                json.dump({"records": demo}, fh, ensure_ascii=False)

    def __enter__(self):
        return self.dir

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)


class RepositoryPackage(unittest.TestCase):
    def test_build_is_deterministic(self):
        a, b = bs.build(), bs.build()
        self.assertEqual(bs.canonical(a), bs.canonical(b))

    def test_committed_outputs_match_build(self):
        out = bs.build()
        for name, data in out.items():
            with open(os.path.join(PKG, name), encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), data, f"{name} is stale: run build_slice.py")

    def test_package_valid_and_separated(self):
        out = bs.build()
        self.assertTrue(out["validation.json"]["valid"])
        self.assertFalse(out["objects.json"]["slice"]["demo"])
        self.assertTrue(out["demo_synthetic.json"]["slice"]["demo"])
        for item in out["objects.json"]["items"] + out["historical.json"]["items"]:
            self.assertNotEqual(item["evidence_type"], "synthetic")
            self.assertEqual(item["publication"], "draft")
        for item in out["demo_synthetic.json"]["items"]:
            self.assertEqual(item["evidence_type"], "synthetic")
            self.assertTrue(item["id"].startswith("demo-astana-"))
            self.assertIsNone(item["budget"]["amount_kzt"])

    def test_no_real_object_without_fetched_source(self):
        # With the network closed in round 11 the real slice must not invent records.
        reg = {s["id"]: s for s in json.load(open(os.path.join(PKG, "sources.json"), encoding="utf-8"))["sources"]}
        for item in bs.build()["objects.json"]["items"]:
            fetched = [r for r in item["source_refs"] if reg[r["id"]]["access_status"] == "fetched" and r["fields"]]
            self.assertTrue(fetched, item["id"])


class IntakeNormalisation(unittest.TestCase):
    def test_claims_become_linked_fields(self):
        with TempPackage([FETCHED], [INTAKE]) as pkg:
            out = bs.build(pkg)
        self.assertTrue(out["validation.json"]["valid"], json.dumps(out["validation.json"]["slices"], ensure_ascii=False))
        obj = out["objects.json"]["items"][0]
        self.assertEqual(obj["status"], "unknown")             # nothing said about the current state
        self.assertIsNone(obj["schedule"]["actual_end"])
        self.assertEqual(obj["budget"], {"amount_kzt": 250000000, "basis": "planned", "source_id": "src-test-news"})
        self.assertEqual(obj["publication"], "draft")
        self.assertEqual(obj["updated_at"], "2026-10-06T09:30:00Z")
        ref = obj["source_refs"][0]
        self.assertEqual(ref["fields"], sorted(["budget.amount_kzt", "budget.basis", "schedule.current_planned_end",
                                                "schedule.original_planned_end", "schedule.planned_start"]))
        self.assertEqual(set(ref), set(cv.SOURCE_REF_KEYS))
        self.assertEqual(len(out["evidence_index.json"]["rows"]), 5)

    def test_unfetched_source_cannot_back_a_claim(self):
        rec = copy.deepcopy(INTAKE)
        rec["claims"][0]["source_id"] = "src-test-blocked"
        with TempPackage([FETCHED, NOT_FETCHED], [rec]) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "not fetched"):
                bs.build(pkg)

    def test_expected_date_cannot_become_actual_end(self):
        rec = copy.deepcopy(INTAKE)
        rec["claims"].append({"field": "schedule.actual_end", "value": "2026-11-15", "source_id": "src-test-news",
                              "claim_type": "expected", "quote": "завершим к 15 ноября", "locator": "абзац 2"})
        with TempPackage([FETCHED], [rec]) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "reported_actual"):
                bs.build(pkg)

    def test_completed_needs_reported_actual(self):
        rec = copy.deepcopy(INTAKE)
        rec["claims"].append({"field": "status", "value": "completed", "source_id": "src-test-news",
                              "claim_type": "expected", "quote": "будет завершено", "locator": "абзац 4"})
        with TempPackage([FETCHED], [rec]) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "reported_actual"):
                bs.build(pkg)

    def test_conflicting_values_refused(self):
        rec = copy.deepcopy(INTAKE)
        rec["claims"].append({"field": "schedule.planned_start", "value": "2026-10-05", "source_id": "src-test-news",
                              "claim_type": "stated", "quote": "с 5 октября", "locator": "абзац 5"})
        with TempPackage([FETCHED], [rec]) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "conflicting"):
                bs.build(pkg)

    def test_approximate_geometry_needs_basis(self):
        rec = copy.deepcopy(INTAKE)
        rec["geometry"] = {"type": "Point", "coordinates": [71.43, 51.17]}
        rec["geometry_precision"] = "approximate"
        with TempPackage([FETCHED], [rec]) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "geometry_basis"):
                bs.build(pkg)
        rec["geometry_basis"] = "Точка у начала участка по названию улицы в источнике; линия не известна."
        with TempPackage([FETCHED], [rec]) as pkg:
            out = bs.build(pkg)
        self.assertEqual(out["objects.json"]["items"][0]["geometry_precision"], "approximate")
        self.assertTrue(out["validation.json"]["valid"])

    def test_stale_in_progress_rejected_by_validation(self):
        rec = copy.deepcopy(INTAKE)
        rec["claims"].append({"field": "status", "value": "in_progress", "source_id": "src-test-news",
                              "claim_type": "stated", "quote": "работы ведутся", "locator": "абзац 1"})
        old = dict(FETCHED, published_on="2026-06-01", retrieved_at="2026-10-06T09:00:00Z")
        with TempPackage([old], [rec]) as pkg:
            out = bs.build(pkg)
        self.assertFalse(out["validation.json"]["valid"])
        codes = {i["code"] for v in out["validation.json"]["slices"]["objects.json"]["issues"].values() for i in v}
        self.assertIn("stale_status", codes)

    def test_old_completed_work_goes_to_historical(self):
        rec = copy.deepcopy(INTAKE)
        rec["id"] = "ast-r05-test-old-repair"
        rec["claims"] = [
            {"field": "status", "value": "completed", "source_id": "src-test-news", "claim_type": "reported_actual",
             "quote": "ремонт завершён", "locator": "абзац 1"},
            {"field": "schedule.actual_end", "value": "2024-08-20", "source_id": "src-test-news",
             "claim_type": "reported_actual", "quote": "завершён 20 августа 2024 года", "locator": "абзац 1"},
        ]
        old = dict(FETCHED, published_on="2024-08-21")
        with TempPackage([old], [rec, INTAKE]) as pkg:
            out = bs.build(pkg)
        self.assertEqual([o["id"] for o in out["historical.json"]["items"]], ["ast-r05-test-old-repair"])
        self.assertEqual([o["id"] for o in out["objects.json"]["items"]], ["ast-r05-test-street-repair"])

    def test_ids_and_order_stable_across_input_order(self):
        rec2 = copy.deepcopy(INTAKE)
        rec2["id"] = "ast-r05-a-first"
        with TempPackage([FETCHED], [INTAKE, rec2]) as pkg:
            a = bs.build(pkg)
        with TempPackage([FETCHED], [rec2, INTAKE]) as pkg:
            b = bs.build(pkg)
        self.assertEqual([o["id"] for o in a["objects.json"]["items"]], ["ast-r05-a-first", "ast-r05-test-street-repair"])
        self.assertEqual(a["objects.json"]["items"], b["objects.json"]["items"])

    def test_demo_and_real_ids_never_collide(self):
        demo = [{"id": "demo-astana-x", "kind": "event", "title": "Демо: событие", "description": "синтетика",
                 "status": "planned", "geometry": None, "geometry_precision": "unknown"}]
        with TempPackage([FETCHED], [INTAKE], demo=demo) as pkg:
            out = bs.build(pkg)
        self.assertEqual(out["validation.json"]["ids_shared_between_real_and_demo"], [])
        self.assertTrue(out["validation.json"]["valid"])

    def test_demo_record_cannot_set_budget_or_sources(self):
        demo = [{"id": "demo-astana-x", "kind": "event", "title": "Демо", "budget": {"amount_kzt": 1}}]
        with TempPackage([FETCHED], [], demo=demo) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "may not set"):
                bs.build(pkg)


if __name__ == "__main__":
    unittest.main()
