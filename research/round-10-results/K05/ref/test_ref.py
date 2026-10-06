"""Independent Python reference vs hand-written expectations. Run: python3 ref/test_ref.py"""
import json, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import school_compare_ref as R

DOC = json.load(open(os.path.join(HERE, "..", "fixtures", "hand_cases.json"), encoding="utf-8"))
FIELDS = DOC["metric_fields_order"]


def check_expected(tc, plans, h):
    for pid, exp in h["expected"].items():
        p = plans[pid]
        tc.assertEqual(p["selected_candidate_ids"], exp["ids"], pid)
        rows = {r["origin_id"]: r for r in p["rows"]}
        for k, field in (("after", "after_mm"), ("status", "status"), ("delta", "delta_mm"), ("nearest", "nearest_target_id")):
            for o, v in exp.get(k, {}).items():
                tc.assertEqual(rows[o][field], v, f"{pid} {o} {field}")
        if "metrics" in exp:
            got = [p["metrics"][f] for f in FIELDS]
            for f, g, w in zip(FIELDS, got, exp["metrics"]):
                if isinstance(w, float):
                    tc.assertAlmostEqual(g, w, places=9, msg=f"{pid} {f}")
                else:
                    tc.assertEqual(g, w, f"{pid} {f}")


class Ref(unittest.TestCase):
    def test_hand_cases(self):
        for h in DOC["cases"]:
            with self.subTest(case=h["case"]["case_id"]):
                plans, _ = R.compare(h["case"], h["matrix"])
                check_expected(self, plans, h)


if __name__ == "__main__":
    unittest.main()
