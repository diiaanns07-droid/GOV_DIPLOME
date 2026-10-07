"""R10 independent acceptance of R05 data/civic/astana (round 11, Astana, civic-v1).

Expectations come from CONTRACT.txt (PACK 9c2f5c0, section 1) and prompts/R05.txt, not from the
R05 implementation. Product code runs only inside r05_driver.py, started here as
    python3 -I -B r05_driver.py <R10_R05_ROOT> [<R10_R05_LICFETCH>]      (cwd = R10_R05_ROOT)
and this file asserts on the JSON it prints.

    R10_R05_ROOT=<detached worktree of the pinned R05 SHA> \
    [R10_R05_SHA=<expected full sha>] [R10_R05_LICFETCH=<manifest.json of R10's licence re-fetch>] \
    python3 -I -B tests/civic/R10/standalone/standalone_r05.py -v
(script form: under -I the cwd is not on sys.path, so "-m unittest standalone_r05" cannot import it.)

Without R10_R05_ROOT every test is skipped with "NOT_RUN: ...".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "r05_driver.py")
ROOT = os.environ.get("R10_R05_ROOT")
EXPECTED_SHA = os.environ.get("R10_R05_SHA")
LICFETCH = os.environ.get("R10_R05_LICFETCH")
PACK_FIXTURE_SHA256 = "e2ba1de7d263f69629d12c01dea35c774f0be321a1fb9f7685787c33caad88f2"

# R10's reading of CONTRACT §1 for tests/civic/R10/test_fixture_contract.py BAD_VARIANTS:
# the contract text does not define an ordering of schedule dates, nor forbid a basis with a null amount.
CONTRACT_SILENT = {"end before start", "budget unknown masked as zero with claimed basis"}
# Extra variants whose rejection follows from the contract text itself.
CONTRACT_TEXT_REJECT = {
    "html_in_title": "title/description: plain text, без HTML",
    "source_ref_missing_license_key": "source_refs: [{id,url,publisher,published_on,retrieved_at,access_status,license,fields}]",
}

_OBS: dict = {}


def obs() -> dict:
    if not ROOT:
        raise unittest.SkipTest("NOT_RUN: R10_R05_ROOT is not set (detached worktree of the pinned R05 SHA)")
    if "data" not in _OBS:
        proc = subprocess.run([sys.executable, "-I", "-B", DRIVER, ROOT, LICFETCH or ""], cwd=ROOT,
                              capture_output=True, text=True, timeout=600)
        _OBS["proc"] = proc
        if proc.returncode != 0:
            raise AssertionError(f"driver exit {proc.returncode}: {proc.stderr[-2000:]}")
        _OBS["data"] = json.loads(proc.stdout)
    return _OBS["data"]


class R05Validator(unittest.TestCase):
    def test_01_pack_fixture(self):
        """[R10-R05-01] PACK fixture: accepted by R05 contract/demo profiles and R10; real profile refuses synthetic."""
        d = obs()
        if EXPECTED_SHA:
            self.assertEqual(d["meta"]["head"], EXPECTED_SHA)
        pf = d["pack_fixture"]
        self.assertEqual(pf["sha256"], PACK_FIXTURE_SHA256)
        self.assertTrue(pf["same_as_r10_copy"])
        self.assertTrue(pf["r10"]["accept"], pf["r10"])
        self.assertTrue(pf["r05_contract"]["accept"], pf["r05_contract"])
        self.assertTrue(pf["r05_demo"]["accept"], pf["r05_demo"])
        self.assertIn("synthetic_in_real", pf["r05_real"]["errors"])

    def test_02_bad_variants(self):
        """[R10-R05-02] R10 BAD_VARIANTS: every contract violation rejected by R05; disagreements only where CONTRACT is silent."""
        d = obs()
        missed, disagree = [], []
        for row in d["bad_variants"]:
            r05, r10 = row["r05_contract"]["accept"], row["r10"]["accept"]
            if row["desc"] not in CONTRACT_SILENT and r05:
                missed.append(row["desc"])
            if r05 != r10:
                disagree.append(row["desc"])
        self.assertEqual(missed, [], "R05 contract profile accepted a contract violation")
        self.assertTrue(set(disagree) <= CONTRACT_SILENT, disagree)

    def test_03_contract_text_variants(self):
        """[R10-R05-03] Extra variants from contract text (HTML in title, source_ref without license key) rejected by R05."""
        d = obs()
        for key in CONTRACT_TEXT_REJECT:
            with self.subTest(key):
                self.assertFalse(d["extra_variants"][key]["r05_contract"]["accept"], d["extra_variants"][key])

    def test_04_observed_needs_fetched_source(self):
        """[R10-R05-04] evidence_type=observed without a fetched source is refused for real data (real profile + import)."""
        d = obs()
        sem, ev, imp = d["real_semantics"], d["extra_variants"], d["import"]
        self.assertFalse(sem["observed_without_any_source"]["accept"])
        self.assertFalse(sem["observed_only_unfetched_source"]["accept"])
        self.assertFalse(ev["observed_supported_only_by_unfetched_source"]["r05_real"]["accept"])
        self.assertEqual(imp["smuggle_observed_without_source"]["items"], [])


class R05FalseFacts(unittest.TestCase):
    def test_05_expected_end_is_not_actual_end(self):
        """[R10-R05-05] 'завершим в июне' never becomes actual_end (validator, builder, schedule_diff)."""
        d = obs()
        sem = d["real_semantics"]
        self.assertFalse(sem["expected_end_recorded_as_actual_end"]["accept"])
        self.assertFalse(sem["actual_end_after_as_of"]["accept"])
        self.assertIn("intake_error", d["pipeline"]["expected_date_as_actual_end"])
        sdiff = d["schedule_diff"]
        self.assertFalse(sdiff["auto_applied"])
        self.assertTrue(sdiff["all_require_editor"])
        actual = [f for f in sdiff["findings"] if f["field"] == "schedule.actual_end"]
        self.assertTrue(actual and all(f["kind"] == "rejected_actual" for f in actual), sdiff["findings"])
        self.assertFalse(any(f["field"] == "schedule.original_planned_end" for f in sdiff["findings"]))

    def test_06_old_announcement_not_current(self):
        """[R10-R05-06] Old announcement does not become current status: stale status rejected, old completion -> historical."""
        d = obs()
        self.assertFalse(d["real_semantics"]["old_announcement_status_in_progress"]["accept"])
        old = d["pipeline"]["old_planned_announcement"]
        self.assertNotIn("ast-r05-roadworks-r10-old", old.get("import_items", []), old)
        done = d["pipeline"]["old_completed_report"]
        self.assertEqual([o["id"] for o in done["historical"]], ["ast-r05-roadworks-r10-done"])
        self.assertEqual(done["current"], [])

    def test_07_future_announcement_not_current(self):
        """[R10-R05-07] Future announcement ('начнутся 1 ноября') must not yield status in_progress/completed as current."""
        d = obs()
        sem = d["real_semantics"]
        problems = []
        if sem["future_announcement_status_in_progress"]["accept"]:
            problems.append("validator(real) accepts status=in_progress with planned_start 2026-11-01 > as_of 2026-10-06")
        if sem["future_start_status_completed"]["accept"]:
            problems.append("validator(real) accepts status=completed with planned_start 2026-12-01 > as_of")
        fut = d["pipeline"]["future_announcement_in_progress"]
        cur = [o for o in fut.get("current", []) if o["status"] == "in_progress"]
        if cur and "ast-r05-roadworks-r10-future" in fut.get("import_items", []):
            problems.append("builder+import_helper accept claim status=in_progress with claim_type=expected")
        self.assertEqual(problems, [])

    def test_08_budget_and_geometry_provenance(self):
        """[R10-R05-08] Budget from unfetched source, 0 as unknown, 2GIS geometry, claims on unfetched sources are refused."""
        d = obs()
        sem = d["real_semantics"]
        for key in ("budget_from_unfetched_source", "budget_zero_as_unknown", "geometry_copied_from_2gis"):
            with self.subTest(key):
                self.assertFalse(sem[key]["accept"], sem[key])
        self.assertIn("not fetched", d["pipeline"]["claim_from_unfetched_source"].get("intake_error", ""))
        self.assertTrue(sem["baseline_expected_end_status_unknown"]["accept"], "control record must pass")
        self.assertTrue(d["pipeline"]["fresh_planned_announcement"]["validation_valid"], "control pipeline must pass")


class R05Import(unittest.TestCase):
    def test_09_import_creates_drafts_only(self):
        """[R10-R05-09] Import plan only creates drafts; no publish/archive action; create_body has no server-owned fields."""
        imp = obs()["import"]
        self.assertEqual(imp["counts"]["rejected"], 0)
        self.assertEqual(imp["first_actions"], ["create"])
        self.assertEqual(imp["first_publication_after"], ["draft"])
        self.assertEqual(imp["any_publish_or_archive_action"], [])
        self.assertEqual(imp["create_body_server_owned_keys"], [])
        self.assertIn(imp["real_suggested_publication"], ([], ["draft"]))

    def test_10_reimport_idempotent(self):
        """[R10-R05-10] Same inputs -> same slice; committed files equal a rebuild; re-import is skip_unchanged."""
        imp = obs()["import"]
        self.assertTrue(imp["build_deterministic"])
        self.assertTrue(all(imp["committed_equals_build"].values()), imp["committed_equals_build"])
        self.assertTrue(imp["digests_stable_across_loads"])
        self.assertEqual(imp["reimport_actions"], ["skip_unchanged"])

    def test_11_no_overwrite_no_auto_archive(self):
        """[R10-R05-11] Changed package never overwrites published/hand-edited records; absent record -> report_missing."""
        imp = obs()["import"]
        self.assertEqual(imp["changed_published_actions"], ["editor_review"])
        self.assertEqual(imp["changed_hand_edited_actions"], ["editor_review"])
        self.assertEqual(imp["missing_record_actions"], ["report_missing"])

    def test_12_smuggled_records_rejected(self):
        """[R10-R05-12] Hash-consistent real slice carrying synthetic / swapped-coordinate records: rejected at import."""
        imp = obs()["import"]
        self.assertEqual(imp["smuggle_synthetic_into_real"]["items"], [])
        self.assertEqual(imp["smuggle_swapped_coords_with_geofence"]["items"], [])

    def test_13_fail_closed_without_geofence(self):
        """[R10-R05-13] Without geofence.json the import must not silently accept swapped [lat,lon] coordinates."""
        res = obs()["import"]["smuggle_swapped_coords_without_geofence"]
        self.assertTrue("package_error" in res or res.get("items") == [], res)


class R05Geofence(unittest.TestCase):
    def test_14_geofence_plausible(self):
        """[R10-R05-14] Geofence is a plausible Astana area: bbox ~71.2-71.8E/50.9-51.35N, closed 2D rings, not swapped, ODbL."""
        g = obs()["geofence"]
        lo_lon, lo_lat, hi_lon, hi_lat = g["computed_bbox"]
        self.assertEqual(g["computed_bbox"], g["declared_city_bbox"])
        self.assertTrue(71.0 <= lo_lon <= 71.4 and 71.6 <= hi_lon <= 72.0, g["computed_bbox"])
        self.assertTrue(50.8 <= lo_lat <= 51.05 and 51.2 <= hi_lat <= 51.5, g["computed_bbox"])
        self.assertEqual((g["open_rings"], g["short_rings"], g["positions_not_2d"]), (0, 0, 0))
        self.assertTrue(g["positions_lon_gt_lat"])
        m = g["margin_deg"]
        self.assertEqual([round(v, 6) for v in g["outer_bbox"]],
                         [round(lo_lon - m, 6), round(lo_lat - m, 6), round(hi_lon + m, 6), round(hi_lat + m, 6)])
        self.assertIn("ODbL", g["license"])
        self.assertIn("OpenStreetMap", g["input"]["attribution"])

    def test_15_geofence_points_and_rebuild(self):
        """[R10-R05-15] Landmarks inside, other cities and swapped point outside (R05 == R10 ray casting); rebuild reproduces file."""
        g = obs()["geofence"]
        for name in ("baiterek", "khan_shatyr", "ak_orda"):
            self.assertEqual(g["points"][name]["r05"], "inside", name)
            self.assertTrue(g["points"][name]["r10_inside_district"], name)
        for name in ("almaty_city", "karaganda", "kokshetau", "baiterek_swapped"):
            self.assertEqual(g["points"][name]["r05"], "outside", name)
            self.assertFalse(g["points"][name]["r10_inside_district"], name)
        self.assertTrue(g["rebuild_equals_committed"])
        self.assertEqual(g["input"]["sha256"], g["input_sha256_actual"])


class R05Sources(unittest.TestCase):
    def test_16_sources_match_fetch_audit(self):
        """[R10-R05-16] Every source has url/publisher/retrieved_at/access_status/license; status matches the fetch audit."""
        s = obs()["sources"]
        self.assertEqual(s["missing_required_keys"], {})
        self.assertEqual(s["audit_mismatches"], [])
        self.assertEqual(s["denied_hosts_marked_fetched"], [])
        self.assertEqual(s["validation_sources"]["total"], s["count"])
        self.assertEqual(s["validation_sources"]["fetched"], s["by_status"].get("fetched", 0))

    def test_17_no_unbacked_real_records_and_licence_register(self):
        """[R10-R05-17] No real record without fetched source; demo slice synthetic+labelled; licence register consistent."""
        s = obs()["sources"]
        self.assertEqual(s["real_records_violating_provenance"], [])
        self.assertTrue(s["demo_flag"])
        self.assertEqual(s["demo_bad"], [])
        self.assertEqual(s["license_register_inconsistencies"], [])
        self.assertTrue(all(s["attribution_has"].values()), s["attribution_has"])

    def test_18_licence_texts_refetched(self):
        """[R10-R05-18] Licence texts R05 marks fetched (raw.githubusercontent.com) re-fetched by R10: identical sha256."""
        s = obs()["sources"]
        if not s["licfetch"]:
            self.skipTest("NOT_RUN: R10_R05_LICFETCH not set (no R10 re-fetch manifest)")
        for url, row in s["licfetch"]["files"].items():
            with self.subTest(url):
                self.assertEqual(row["r05_status"], "fetched")
                self.assertEqual(row["r10_sha256"], row["r05_sha256"])

    def test_19_official_licence_pages(self):
        """[R10-R05-19] Official pages (openstreetmap.org/copyright, ODbL, OSMF, openfreemap.org, openmaptiles.org, Overture docs, gov.kz)."""
        s = obs()["sources"]
        denied = (s["licfetch"] or {}).get("denied") or {}
        if not s["licfetch"] or denied:
            self.skipTest("NOT_RUN: official licence pages not reachable from R10 environment (proxy 403): "
                          + ", ".join(sorted(denied)) if denied else "NOT_RUN: no re-fetch manifest")
        self.fail("official pages reachable: compare their text manually before marking VERIFIED")

    def test_20_delivery_current(self):
        """[R10-R05-20] DELIVERY.json (CONTRACT §7) reflects the delivered head: integration notes exist, checks current."""
        dl = obs()["sources"]["delivery"]
        self.assertEqual(dl["r10_check_delivery"], [])
        self.assertNotIn("to be written", dl["integration_notes"] or "")


if __name__ == "__main__":
    unittest.main()
