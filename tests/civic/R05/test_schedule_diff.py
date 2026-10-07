"""Stretch: changed published deadlines are detected and only proposed to an editor."""

import os
import subprocess
import sys
import unittest
import json

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TOOLS = os.path.join(REPO, "data", "civic", "astana", "tools")
FIX = os.path.join(os.path.dirname(__file__), "fixtures")
sys.path.insert(0, TOOLS)

import schedule_diff as sd  # noqa: E402


def snap(text, published_on="2026-10-01", retrieved="2026-10-02T08:00:00Z"):
    return sd.make_snapshot(text, source_id="src-synthetic", url="https://example.org/synthetic",
                            retrieved_at=retrieved, published_on=published_on)


def by_kind(report, kind):
    return [f for f in report["findings"] if f["kind"] == kind]


class Extraction(unittest.TestCase):
    def test_roles_and_precision(self):
        cases = {
            "Работы планируется завершить до 30 октября 2026 года.": ("expected_end", "day", "2026-10-30"),
            "Ремонт начнётся 5 октября 2026 года.": ("start", "day", "2026-10-05"),
            "Работы завершены 18 ноября 2026 года.": ("reported_actual_end", "day", "2026-11-18"),
            "Сдать объект до 15.11.2026.": ("expected_end", "day", "2026-11-15"),
            "Работы завершат до 15 ноября.": ("expected_end", "day_without_year", None),
        }
        for text, (role, prec, value) in cases.items():
            d = sd.extract_dates(text)
            self.assertEqual(len(d), 1, text)
            self.assertEqual((d[0]["role"], d[0]["precision"], d[0].get("value")), (role, prec, value), text)

    def test_month_only_is_not_a_day(self):
        d = sd.extract_dates("Работы завершат в ноябре 2026 года.")
        self.assertEqual(d[0]["precision"], "month")
        self.assertIsNone(d[0]["value"])

    def test_ranges(self):
        d = sd.extract_dates("Перекрытие с 28 сентября по 3 октября 2026 года.")[0]
        self.assertEqual((d["start"], d["end"]), ("2026-09-28", "2026-10-03"))

    def test_snapshot_keeps_only_short_dated_sentences(self):
        text = "Вводный абзац без дат. " * 40 + "Работы завершат до 30 октября 2026 года. Ещё текст без дат."
        s = snap(text)
        self.assertEqual(s["excerpts"], ["Работы завершат до 30 октября 2026 года."])
        self.assertTrue(all(len(e) <= 300 for e in s["excerpts"]))
        self.assertEqual(len(s["text_sha256"]), 64)


class Diff(unittest.TestCase):
    def setUp(self):
        self.v1 = snap(open(os.path.join(FIX, "synthetic_source_v1.txt"), encoding="utf-8").read())
        self.v2 = snap(open(os.path.join(FIX, "synthetic_source_v2.txt"), encoding="utf-8").read(),
                       published_on="2026-10-20", retrieved="2026-10-21T08:00:00Z")

    def test_unchanged_versions_report_nothing(self):
        r = sd.diff(self.v1, self.v1)
        self.assertEqual(r["findings"], [])
        self.assertFalse(r["content_changed"])

    def test_moved_deadline_is_proposed_not_applied(self):
        r = sd.diff(self.v1, self.v2)
        self.assertTrue(r["content_changed"])
        self.assertFalse(r["auto_applied"])
        self.assertTrue(all(f["requires_editor_confirmation"] for f in r["findings"]))
        fields = {f["field"] for f in r["findings"]}
        self.assertNotIn("schedule.original_planned_end", fields)
        self.assertNotIn("schedule.actual_end", fields)
        end = [f for f in r["findings"] if f["field"] == "schedule.current_planned_end"]
        self.assertTrue(end)
        self.assertIn("2026-11-20", json.dumps(end))

    def test_record_mismatch_flagged(self):
        record = {"id": "demo-x", "schedule": {"planned_start": "2026-10-01", "original_planned_end": "2026-10-30",
                                               "current_planned_end": "2026-10-30", "actual_end": None}}
        v = snap("Срок завершения работ перенесён на 20 ноября 2026 года.", published_on="2026-10-20")
        r = sd.diff(self.v1, v, record)
        mism = by_kind(r, "differs_from_record")
        self.assertEqual(mism[0]["old"], "2026-10-30")
        self.assertEqual(mism[0]["new"], "2026-11-20")

    def test_future_completion_rejected_as_actual(self):
        v = snap("Работы завершены 30 ноября 2026 года.", published_on="2026-10-20")
        r = sd.diff(self.v1, v)
        self.assertTrue(by_kind(r, "rejected_actual"))
        self.assertFalse(by_kind(r, "candidate_actual"))

    def test_reported_completion_is_only_a_candidate(self):
        v = snap("Работы завершены 18 октября 2026 года.", published_on="2026-10-20")
        r = sd.diff(self.v1, v)
        cand = by_kind(r, "candidate_actual")
        self.assertEqual(cand[0]["new"], "2026-10-18")
        self.assertTrue(cand[0]["requires_editor_confirmation"])

    def test_imprecise_new_date_reported(self):
        v = snap("Работы завершат в ноябре 2026 года.", published_on="2026-10-20")
        r = sd.diff(self.v1, v)
        self.assertTrue(by_kind(r, "imprecise_date"))

    def test_two_end_dates_are_ambiguous(self):
        v = snap("Первый этап завершат до 1 ноября 2026 года. Второй этап завершат до 1 декабря 2026 года.")
        r = sd.diff(self.v1, v)
        self.assertTrue(by_kind(r, "ambiguous"))

    def test_different_sources_refused(self):
        other = dict(self.v2, source_id="src-other")
        with self.assertRaises(ValueError):
            sd.diff(self.v1, other)

    def test_cli_roundtrip(self):
        out = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "schedule_diff.py"), "snapshot",
                              "--text", os.path.join(FIX, "synthetic_source_v1.txt"), "--source-id", "src-synthetic",
                              "--url", "https://example.org/synthetic", "--retrieved-at", "2026-10-02T08:00:00Z",
                              "--published-on", "2026-10-01"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout)["excerpts"], self.v1["excerpts"])


if __name__ == "__main__":
    unittest.main()
