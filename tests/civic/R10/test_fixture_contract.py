"""Smoke: the PACK fixture conforms to civic-v1, and R10's validator rejects known-bad variants.

Runs without any server. Proves two things before product code exists:
1) fixtures/pack_civic_object.json is byte-identical to PACK_SHA's fixture and conforms;
2) each hand-written broken variant is rejected for the expected reason
   (so a later PASS of a product payload means something).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10lib import contract  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "pack_civic_object.json"
PACK_FIXTURE_SHA256 = "e2ba1de7d263f69629d12c01dea35c774f0be321a1fb9f7685787c33caad88f2"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FixtureConforms(unittest.TestCase):
    def test_fixture_bytes_match_pack(self):
        digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        self.assertEqual(digest, PACK_FIXTURE_SHA256, "fixture differs from PACK_SHA 9c2f5c0 copy")

    def test_fixture_is_valid_civic_v1(self):
        self.assertEqual(contract.check_object(load_fixture()), [])

    def test_fixture_is_honestly_synthetic(self):
        obj = load_fixture()
        self.assertEqual(obj["evidence_type"], "synthetic")
        self.assertIsNone(obj["budget"]["amount_kzt"], "unknown budget must stay null, not 0")
        self.assertEqual(obj["budget"]["basis"], "unknown")
        self.assertIsNone(obj["schedule"]["actual_end"])
        self.assertEqual(obj["source_refs"], [])

    def test_fixture_schedule_change_is_explainable(self):
        # original 2026-10-20 -> current 2026-10-22: a public history entry with a reason must exist
        sched = load_fixture()["schedule"]
        self.assertNotEqual(sched["original_planned_end"], sched["current_planned_end"])


def mutate(path, value):
    obj = load_fixture()
    target = obj
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[key]
    if value is KeyError:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value
    return obj


# (description, path, bad value, substring expected in a problem message)
BAD_VARIANTS = [
    ("swapped lat/lon", "geometry", {"type": "Point", "coordinates": [51.17, 71.43]}, "swapped"),
    ("other city point (Shymkent)", "geometry", {"type": "Point", "coordinates": [69.59, 42.32]}, "outside Astana"),
    ("unclosed polygon", "geometry", {"type": "Polygon", "coordinates": [[[71.4, 51.1], [71.5, 51.1], [71.5, 51.2], [71.4, 51.2]]]}, "not closed"),
    ("geometry as string", "geometry", "71.43,51.17", "GeoJSON"),
    ("impossible date", "schedule.current_planned_end", "2026-02-30", "not YYYY-MM-DD"),
    ("datetime instead of date", "schedule.planned_start", "2026-10-14T00:00:00+06:00", "not YYYY-MM-DD"),
    ("end before start", "schedule.current_planned_end", "2026-10-01", "before planned_start"),
    ("actual_end on planned object", "schedule.actual_end", "2026-10-21", "actual_end"),
    ("negative budget", "budget.amount_kzt", -5, "finite >= 0"),
    ("budget unknown masked as zero with claimed basis", "budget.basis", "contract", "basis claims"),
    ("bool budget", "budget.amount_kzt", True, "finite >= 0"),
    ("unknown kind", "kind", "pothole", "kind="),
    ("unknown status", "status", "active", "status="),
    ("unknown evidence", "evidence_type", "verified", "evidence_type="),
    ("revision zero", "revision", 0, "revision"),
    ("revision string", "revision", "2", "revision"),
    ("naive timestamp", "updated_at", "2026-10-06T12:00:00", "updated_at"),
    ("wrong schema", "schema_version", "civic-v2", "schema_version"),
    ("wrong city", "city", "shymkent", "city="),
    ("missing schedule", "schedule", KeyError, "missing fields"),
    ("leaked internal notes", "internal_notes", "call contractor at home", "allowlist"),
    ("leaked password hash", "password_hash", "pbkdf2$...", "sensitive"),
]


class ValidatorRejectsBadVariants(unittest.TestCase):
    def test_each_bad_variant_is_rejected_for_its_reason(self):
        for desc, path, value, needle in BAD_VARIANTS:
            with self.subTest(desc):
                problems = contract.check_object(mutate(path, value))
                self.assertTrue(any(needle in p for p in problems),
                                f"{desc}: expected problem containing {needle!r}, got {problems}")

    def test_observed_without_source_is_flagged(self):
        problems = contract.check_object(mutate("evidence_type", "observed"))
        self.assertTrue(any("observed without" in p for p in problems), problems)

    def test_draft_in_public_projection_is_flagged(self):
        obj = mutate("publication", "draft")
        self.assertEqual(contract.check_object(obj), [])
        self.assertTrue(any("publication" in p for p in contract.check_object(obj, public=True)))

    def test_nan_and_infinity_rejected(self):
        for bad in (float("nan"), float("inf")):
            problems = contract.check_object(mutate("budget.amount_kzt", bad))
            self.assertTrue(any("finite" in p for p in problems), problems)


class EnvelopeAndHistoryShapes(unittest.TestCase):
    def test_envelopes(self):
        self.assertEqual(contract.check_envelope({"ok": True, "data": {}}, 200), [])
        self.assertEqual(contract.check_envelope(
            {"ok": False, "error": {"code": "not_found", "message": "x"}}, 404), [])
        self.assertTrue(contract.check_envelope({"valid": False, "errors": ["x"]}, 400))
        self.assertTrue(contract.check_envelope("<html>", 500))

    def test_history_entry_allowlist(self):
        good = {"id": "h1", "object_id": "o1", "revision": 3, "at": "2026-10-06T12:00:00+06:00",
                "changed_fields": ["schedule.current_planned_end"], "reason": "Подрядчик",
                "public_actor_label": "Редактор"}
        self.assertEqual(contract.check_history_entry(good, object_id="o1"), [])
        leaky = dict(good, actor_username="r10_editor_alpha", old_values={"internal_notes": "x"})
        self.assertTrue(contract.check_history_entry(leaky, object_id="o1"))

    def test_traceback_detector(self):
        self.assertTrue(contract.has_traceback('Traceback (most recent call last):\n  File "/x.py"'))
        self.assertFalse(contract.has_traceback('{"ok":false,"error":{"code":"bad_json"}}'))


if __name__ == "__main__":
    unittest.main()
