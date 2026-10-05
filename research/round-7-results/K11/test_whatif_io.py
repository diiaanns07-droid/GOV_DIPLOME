"""K11 round 7: tests for city-whatif-v1 scenario files (stdlib unittest; isolated fixtures).

    python -m unittest -v research/round-7-results/K11/test_whatif_io.py        (Linux)
    py -3 -m unittest -v research\\round-7-results\\K11\\test_whatif_io.py     (Windows, not run here)

Optional: K11_APP_ROOT=<copy of prototypes/city-evidence> also checks that the fixtures' snapshots match
that copy's web/data.js (otherwise that single test is SKIPPED, which is not a pass).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import whatif_io as W  # noqa: E402

FIX = HERE / "fixtures"
MANIFEST = json.loads((FIX / "MANIFEST.json").read_bytes().decode("utf-8"))
CITY = MANIFEST["cities"]
ACCEPT = [r for r in MANIFEST["files"] if r["expected"] == "accept"]
REJECT = [r for r in MANIFEST["files"] if r["expected"] != "accept"]


def ctx(city):
    return {"expected_snapshot": CITY[city]["source_snapshot"], "bbox": CITY[city]["bbox"]}


class InOtherDirectory:
    """chdir into a fresh unrelated directory (with a Kazakh name) for the duration of a test."""

    def __enter__(self):
        self.old = os.getcwd()
        self.tmp = tempfile.mkdtemp(prefix="k11-басқа-каталог-")
        os.chdir(self.tmp)
        return Path(self.tmp)

    def __exit__(self, *exc):
        os.chdir(self.old)
        shutil.rmtree(self.tmp)


class Fixtures(unittest.TestCase):
    def test_manifest_hashes_and_nfc_names(self):
        import hashlib
        for r in MANIFEST["files"]:
            with self.subTest(file=r["file"]):
                self.assertEqual(unicodedata.normalize("NFC", r["file"]), r["file"])
                data = (FIX / r["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), r["sha256"])

    def test_expected_outcomes_from_other_directory(self):
        with InOtherDirectory():
            for r in MANIFEST["files"]:
                with self.subTest(file=r["file"], expected=r["expected"]):
                    if r["expected"] == "accept":
                        clean, notes = W.load(FIX / r["file"], **ctx(r["city_id"]))
                        self.assertEqual(clean["city_id"], r["city_id"])
                    else:
                        with self.assertRaises(W.ScenarioError) as cm:
                            W.load(FIX / r["file"], **ctx(r["city_id"]))
                        self.assertEqual(cm.exception.code, r["expected"])

    def test_notes_bom_and_untrusted_results(self):
        _, notes = W.load(FIX / "с_BOM_блокнот.json", **ctx("shymkent"))
        self.assertIn("utf8_bom_stripped", notes)
        clean, notes = W.load(FIX / "с_результатами.json", **ctx("shymkent"))
        self.assertIn("untrusted_results_dropped", notes)
        self.assertNotIn("results", clean)

    def test_too_large_rejected_before_parsing(self):
        with InOtherDirectory() as d:
            big = d / "үлкен_файл.json"
            big.write_bytes(b"{" + b" " * (W.MAX_BYTES + 1) + b"}")
            with self.assertRaises(W.ScenarioError) as cm:
                W.load(big, **ctx("shymkent"))
            self.assertEqual(cm.exception.code, "E_TOO_LARGE")

    def test_foreign_city_rejected_when_city_is_selected(self):
        r = next(x for x in ACCEPT if x["city_id"] == "astana")
        with self.assertRaises(W.ScenarioError) as cm:
            W.load(FIX / r["file"], expected_snapshot=CITY["astana"]["source_snapshot"],
                   bbox=CITY["astana"]["bbox"], expected_city="shymkent")
        self.assertEqual(cm.exception.code, "E_CITY")


class SaveAndReopen(unittest.TestCase):
    def test_save_kazakh_name_reopen_elsewhere_relative_and_absolute(self):
        for r in ACCEPT:
            clean, _ = W.load(FIX / r["file"], **ctx(r["city_id"]))
            with InOtherDirectory() as base:
                target_dir = base / "Сценарийлер Қала" / "ұсыныс 1"
                target_dir.mkdir(parents=True)
                path = W.save(target_dir / ("сақталған_" + r["file"]), clean, **ctx(r["city_id"]))
                raw = path.read_bytes()
                with self.subTest(file=r["file"]):
                    self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "no BOM")
                    self.assertNotIn(b"\r", raw, "LF only")
                    self.assertEqual(raw, W.dumps(clean), "canonical bytes")
                    self.assertNotIn(b"\\u04", raw, "Cyrillic/Kazakh kept as UTF-8, not \\u escapes")
                    with InOtherDirectory() as other:
                        rel = os.path.relpath(path, other)
                        a, _ = W.load(rel, **ctx(r["city_id"]))
                        b, _ = W.load(path.resolve(), **ctx(r["city_id"]))
                        self.assertEqual(a, clean)
                        self.assertEqual(b, clean)
                        self.assertEqual(W.dumps(a), raw, "save -> open -> save is byte-stable")

    def test_invalid_scenario_is_not_written(self):
        clean, _ = W.load(FIX / ACCEPT[0]["file"], **ctx(ACCEPT[0]["city_id"]))
        bad = dict(clean, category="hospital")
        with InOtherDirectory() as d:
            target = d / "жарамсыз.json"
            with self.assertRaises(W.ScenarioError):
                W.save(target, bad, **ctx(ACCEPT[0]["city_id"]))
            self.assertFalse(target.exists())
            self.assertEqual([p.name for p in d.iterdir()], [], "no temp file left behind")

    def test_cli_from_other_directory_with_legacy_console_encoding(self):
        """MODELED Windows console: stdout encoded as cp1252 (no Cyrillic). The CLI prints ASCII JSON only."""
        r = ACCEPT[0]
        with InOtherDirectory() as d:
            copy = d / "Көшірме сценарий.json"
            copy.write_bytes((FIX / r["file"]).read_bytes())
            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            p = subprocess.run([sys.executable, str(HERE / "whatif_io.py"), "check", copy.name,
                                "--snapshot", CITY[r["city_id"]]["source_snapshot"],
                                "--bbox", ",".join(map(str, CITY[r["city_id"]]["bbox"]))],
                               cwd=str(d), env=env, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
            p.stdout.decode("ascii")  # must be pure ASCII
            out = json.loads(p.stdout)
            clean, _ = W.load(copy, **ctx(r["city_id"]))
            self.assertEqual(out["control_points"], [x["id"] for x in clean["control_points"]])


class AgainstApp(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("K11_APP_ROOT"), "K11_APP_ROOT not set (SKIP is not PASS)")
    def test_fixture_snapshots_match_app_copy(self):
        root = os.environ["K11_APP_ROOT"]
        for c in W.CITIES:
            with self.subTest(city=c):
                self.assertEqual(W.snapshot_fingerprint(root, c), CITY[c]["source_snapshot"],
                                 "data.js differs from the fixtures' app_sha: regenerate fixtures for this SHA")
                self.assertEqual(W.city_bbox(root, c), CITY[c]["bbox"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
