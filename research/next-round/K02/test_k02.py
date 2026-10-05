"""K02: регрессионные тесты прототипа. Запуск: python -m unittest research/next-round/K02/test_k02.py (из корня)."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kk_numeral_guard import qualitative_comment_v2  # noqa: E402
from agent.evidence import EvidenceError  # noqa: E402

CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
ANCHOR = "Решение требует обсуждения с жителями."


class PrototypeCases(unittest.TestCase):
    def test_cases(self):
        for case in CASES:
            with self.subTest(case["id"]):
                comment, _ = qualitative_comment_v2(case["text"] + " " + ANCHOR)
                kept = case["text"] in comment.split("\n")
                self.assertEqual(kept, case["expected"] == "qualitative", case["text"])

    def test_kazakh_only_comment_is_accepted(self):
        self.assertEqual(qualitative_comment_v2("Іс әлі ұзақ.")[0], "Іс әлі ұзақ.")

    def test_all_numeric_still_raises(self):
        with self.assertRaises(EvidenceError):
            qualitative_comment_v2("Он екі мектеп салынады. Үш аудан ғана жақсарады.")


if __name__ == "__main__":
    unittest.main()
