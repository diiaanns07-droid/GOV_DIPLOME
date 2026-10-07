"""R05 -> R02 import helper: integrity, demo flag, idempotent plan that never publishes."""

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

import import_helper as ih  # noqa: E402


def copy_package():
    d = tempfile.mkdtemp(prefix="r05imp-")
    for name in ("objects.json", "historical.json", "demo_synthetic.json", "geofence.json"):
        shutil.copy(os.path.join(PKG, name), d)
    return d


class PackageLoading(unittest.TestCase):
    def test_demo_needs_explicit_flag(self):
        base = ih.load_package(PKG)
        self.assertTrue(all(not i["demo"] for i in base["items"]))
        self.assertEqual(base["package"]["sources"], [ih.SOURCE_REAL])
        with_demo = ih.load_package(PKG, include_demo=True)
        demo = [i for i in with_demo["items"] if i["demo"]]
        self.assertEqual(len(demo), 9)
        self.assertTrue(all(i["source"] == ih.SOURCE_DEMO for i in demo))
        self.assertEqual(with_demo["rejected"], [])

    def test_create_body_has_no_server_owned_fields(self):
        item = ih.load_package(PKG, include_demo=True)["items"][0]
        for key in ("id", "revision", "updated_at", "publication"):
            self.assertNotIn(key, item["create_body"])
        self.assertEqual(item["create_body"]["schema_version"], "civic-v1")

    def test_hand_edited_slice_refused(self):
        d = copy_package()
        try:
            path = os.path.join(d, "demo_synthetic.json")
            data = json.load(open(path, encoding="utf-8"))
            data["items"][0]["title"] = "Ремонт улицы"  # silently turns a demo into a 'real-looking' record
            json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
            with self.assertRaisesRegex(ih.PackageError, "does not match"):
                ih.load_package(d, include_demo=True)
        finally:
            shutil.rmtree(d)

    def test_edited_as_of_refused(self):
        d = copy_package()
        try:
            path = os.path.join(d, "objects.json")
            data = json.load(open(path, encoding="utf-8"))
            data["slice"]["as_of"] = None  # would silently switch off the freshness checks
            json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
            with self.assertRaisesRegex(ih.PackageError, "does not match"):
                ih.load_package(d)
        finally:
            shutil.rmtree(d)

    def test_stale_inputs_refused(self):
        d = copy_package()
        try:
            shutil.copy(os.path.join(PKG, "slice_config.json"), d)
            shutil.copy(os.path.join(PKG, "sources.json"), d)
            ih.load_package(d)  # consistent: fine
            path = os.path.join(d, "sources.json")
            reg = json.load(open(path, encoding="utf-8"))
            reg["sources"][0]["notes"] = "changed after the slice was built"
            json.dump(reg, open(path, "w", encoding="utf-8"), ensure_ascii=False)
            with self.assertRaisesRegex(ih.PackageError, "changed since the slice was built"):
                ih.load_package(d)
        finally:
            shutil.rmtree(d)

    def test_bom_and_bad_json_are_package_errors(self):
        d = copy_package()
        try:
            path = os.path.join(d, "objects.json")
            raw = open(path, "rb").read()
            open(path, "wb").write(b"\xef\xbb\xbf" + raw)
            ih.load_package(d)  # BOM is tolerated
            open(path, "wb").write(b"{not json")
            with self.assertRaises(ih.PackageError):
                ih.load_package(d)
        finally:
            shutil.rmtree(d)

    def test_demo_slice_cannot_pose_as_real(self):
        d = copy_package()
        try:
            shutil.copy(os.path.join(d, "demo_synthetic.json"), os.path.join(d, "objects.json"))
            with self.assertRaisesRegex(ih.PackageError, "slice.demo"):
                ih.load_package(d)
        finally:
            shutil.rmtree(d)

    def test_digest_ignores_server_owned_fields(self):
        obj = json.load(open(os.path.join(PKG, "demo_synthetic.json"), encoding="utf-8"))["items"][0]
        other = dict(obj, revision=7, updated_at="2030-01-01T00:00:00Z", publication="archived")
        self.assertEqual(ih.content_digest(obj), ih.content_digest(other))
        changed = copy.deepcopy(obj)
        changed["schedule"]["current_planned_end"] = "2026-12-31"
        self.assertNotEqual(ih.content_digest(obj), ih.content_digest(changed))


class ImportPlan(unittest.TestCase):
    def setUp(self):
        self.items = ih.load_package(PKG, include_demo=True)["items"]

    def test_first_import_creates_drafts_only(self):
        actions = ih.plan(self.items, {})
        self.assertEqual({a["action"] for a in actions}, {"create"})
        self.assertTrue(all(a["publication_after"] == "draft" for a in actions))

    def test_reimport_is_idempotent(self):
        existing = {i["external_id"]: {"digest": i["digest"], "publication": "draft", "source": i["source"]}
                    for i in self.items}
        self.assertEqual({a["action"] for a in ih.plan(self.items, existing)}, {"skip_unchanged"})

    def test_published_record_is_not_overwritten(self):
        it = self.items[0]
        existing = {it["external_id"]: {"digest": "old", "publication": "published", "source": it["source"],
                                        "schedule": dict(it["schedule"], current_planned_end="2026-10-01")}}
        act = [a for a in ih.plan([it], existing) if a["external_id"] == it["external_id"]][0]
        self.assertEqual(act["action"], "editor_review")
        self.assertTrue(act["schedule_changes"])

    def test_hand_edited_draft_is_not_overwritten(self):
        it = self.items[0]
        existing = {it["external_id"]: {"digest": "old", "publication": "draft", "edited_after_import": True,
                                        "source": it["source"]}}
        self.assertEqual(ih.plan([it], existing)[0]["action"], "editor_review")

    def test_untouched_import_draft_is_refreshed(self):
        it = self.items[0]
        existing = {it["external_id"]: {"digest": "old", "publication": "draft", "edited_after_import": False,
                                        "source": it["source"]}}
        self.assertEqual(ih.plan([it], existing)[0]["action"], "update_import_draft")

    def test_unknown_edit_state_fails_closed(self):
        it = self.items[0]
        existing = {it["external_id"]: {"digest": "old", "publication": "draft", "source": it["source"]}}
        self.assertEqual(ih.plan([it], existing)[0]["action"], "editor_review")

    def test_historical_record_is_not_reported_missing(self):
        existing = {"ast-r05-moved": {"digest": "x", "publication": "published", "source": ih.SOURCE_REAL}}
        actions = ih.plan([], existing, [ih.SOURCE_REAL], [(ih.SOURCE_REAL, "ast-r05-moved")])
        self.assertEqual(actions, [])

    def test_missing_records_are_reported_not_archived(self):
        existing = {"ast-r05-gone": {"digest": "x", "publication": "published", "source": ih.SOURCE_REAL}}
        actions = ih.plan(self.items, existing, [ih.SOURCE_REAL, ih.SOURCE_DEMO])
        gone = [a for a in actions if a["external_id"] == "ast-r05-gone"]
        self.assertEqual(gone[0]["action"], "report_missing")
        self.assertFalse(any(a["action"] in ("publish", "archive") for a in actions))


if __name__ == "__main__":
    unittest.main()
