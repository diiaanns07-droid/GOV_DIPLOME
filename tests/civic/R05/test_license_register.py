"""LICENSE_REGISTER / ATTRIBUTION / sources consistency: no claimed verification without evidence."""

import hashlib
import json
import os
import re
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PKG = os.path.join(REPO, "data", "civic", "astana")


def load(name):
    with open(os.path.join(PKG, name), encoding="utf-8") as fh:
        return json.load(fh)


SOURCES = {s["id"]: s for s in load("sources.json")["sources"]}
REGISTER = load("LICENSE_REGISTER.json")
with open(os.path.join(PKG, "ATTRIBUTION.txt"), encoding="utf-8") as fh:
    ATTRIBUTION = fh.read()


class SourceRegistry(unittest.TestCase):
    def test_fetched_sources_have_proof(self):
        for sid, s in SOURCES.items():
            if s["access_status"] == "fetched":
                self.assertRegex(s["sha256"] or "", r"^[0-9a-f]{64}$", sid)
                self.assertTrue(s["retrieved_at"], sid)
                self.assertTrue(any(a["outcome"] == "fetched" for a in s["access_attempts"]), sid)

    def test_blocked_sources_are_not_marked_fetched_or_unavailable(self):
        # A proxy policy denial is our limitation, not proof that the site is down.
        for sid, s in SOURCES.items():
            outcomes = {a["outcome"] for a in s["access_attempts"]}
            if outcomes and outcomes <= {"egress_denied"}:
                self.assertEqual(s["access_status"], "not_fetched", sid)
                self.assertIsNone(s["retrieved_at"], sid)
                self.assertIsNone(s["sha256"], sid)

    def test_not_fetched_sources_support_nothing(self):
        for sid, s in SOURCES.items():
            if s["access_status"] != "fetched":
                self.assertEqual(s["supports"], [], sid)

    def test_audit_files_exist(self):
        for path in load("sources.json")["network_audit"]["audit_files"]:
            self.assertTrue(os.path.exists(os.path.join(REPO, path)), path)


class LicenseRegister(unittest.TestCase):
    def test_referenced_sources_exist_and_status_matches(self):
        for entry in REGISTER["entries"]:
            for ev in entry["terms_evidence"]:
                if "source_id" in ev:
                    src = SOURCES.get(ev["source_id"])
                    self.assertIsNotNone(src, ev["source_id"])
                    self.assertEqual(ev["access_status"], src["access_status"], (entry["id"], ev["source_id"]))
                    if "sha256" in ev:
                        self.assertEqual(ev["sha256"], src["sha256"], ev["source_id"])

    def test_verified_entries_rest_on_fetched_text(self):
        for entry in REGISTER["entries"]:
            if entry["verification"] == "fetched_official_text":
                fetched = [ev for ev in entry["terms_evidence"]
                           if SOURCES.get(ev.get("source_id"), {}).get("access_status") == "fetched"]
                self.assertTrue(fetched, entry["id"])

    def test_required_notices_present_in_attribution(self):
        for entry in REGISTER["entries"]:
            notice = entry.get("required_notice")
            if notice and "<" not in notice:
                self.assertIn(notice, ATTRIBUTION, entry["id"])

    def test_excerpts_are_short_and_in_fetched_text_hash_scope(self):
        for entry in REGISTER["entries"]:
            for ev in entry["terms_evidence"]:
                if "excerpt" in ev:
                    self.assertLessEqual(len(ev["excerpt"]), 300, entry["id"])
                    self.assertEqual(ev["access_status"], "fetched", entry["id"])

    def test_saved_license_copies_match_app_snapshot(self):
        for entry in REGISTER["entries"]:
            for ev in entry["terms_evidence"]:
                m = re.match(r"^(\S+) @ ([0-9a-f]{40})$", ev.get("local_copy", ""))
                if not (m and ev.get("sha256")):
                    continue
                try:
                    raw = subprocess.run(["git", "-C", REPO, "show", f"{m.group(2)}:{m.group(1)}"],
                                         capture_output=True, check=True, timeout=30).stdout
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    self.skipTest("application snapshot not fetched locally")
                self.assertEqual(hashlib.sha256(raw).hexdigest(), ev["sha256"], ev["local_copy"])

    def test_prohibited_and_unverified_are_not_public_ok(self):
        by_id = {e["id"]: e for e in REGISTER["entries"]}
        self.assertEqual(by_id["lic-proprietary-web-maps"]["public_display"], "prohibited")
        self.assertEqual(by_id["lic-r05-real-objects"]["public_display"], "needs_rights_check")
        self.assertEqual(by_id["lic-r05-demo"]["public_display"], "allowed_only_with_demo_label")


if __name__ == "__main__":
    unittest.main()
