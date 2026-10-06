"""Stage 2 tests: resilience_oracle vs independent resilience_gold on fixtures/resilience_gold.json,
must_reject codes, hand-derived example. Run: python3 -m unittest -v test_resilience"""
import json, math, os, unittest
import resilience_oracle as R

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "resilience_gold.json")
U = lambda k: math.floor(6371008.8 * math.radians(k * 0.001) * 1000 + 0.5)    # closed form on the meridian, mm


def view(r):
    """Common math view of oracle output and gold."""
    if r["status"] != "optimal":
        return {"status": r["status"]}
    out = {"status": "optimal", "feasible_count": r["feasible_count"],
           "price": None if r["price_of_robustness_m"] is None else round(r["price_of_robustness_m"], 9)}
    for k in ("nominal", "robust"):
        p = r[k]
        out[k] = {"ids": p["selected_ids"], "W": p["worst_vector"], "worst": p["worst_case_ids"]}
        out[k]["L"] = p["loss_by_case"] if "loss_by_case" in p else {c["case_id"]: c["loss_vector"] for c in p["per_case"]}
    return out


class Gold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as fh:
            cls.doc = json.load(fh)

    def test_oracle_equals_gold(self):
        for c in self.doc["cases"]:
            with self.subTest(case=c["case"]):
                self.assertEqual(view(R.optimize_resilience(c["context"], c["envelope"])), view(c["gold"]))

    def test_must_reject(self):
        ctx = self.doc["must_reject"]["context"]
        for it in self.doc["must_reject"]["items"]:
            with self.subTest(case=it["case"]):
                with self.assertRaises(R.O.PlanError) as e:
                    R.validate_envelope(it["envelope"], ctx)
                self.assertEqual(e.exception.code, it["k06_code"])

    def test_hand_example(self):
        g = {c["case"]: c for c in self.doc["cases"]}["nominal_vs_robust_differ"]
        r = R.optimize_resilience(g["context"], g["envelope"])
        self.assertEqual(r["nominal"]["selected_ids"], ["A"]); self.assertEqual(r["robust"]["selected_ids"], ["B"])
        # robust B: worst case x2 (S2 off): P1 0, P2 1u, P3 2.5u*5 ; base mean B = 5*2.5u/7 ; nominal A base = 5*1.5u/7
        self.assertEqual(r["robust"]["worst_vector"], [0, U(1) + 5 * U(2.5), U(2.5)])
        self.assertEqual(r["robust"]["worst_case_ids"], ["x2"])
        self.assertAlmostEqual(r["price_of_robustness_m"], (5 * U(2.5) - 5 * U(1.5)) / 7 / 1000, places=9)

    def test_strict_text_and_size(self):
        g = self.doc["cases"][0]
        txt = json.dumps(g["envelope"])
        self.assertEqual(R.validate_envelope(txt, g["context"])["cases"][0]["id"], "base")
        for bad in (txt.replace('"budget": 10', '"budget": NaN'), txt[:-1] + ', "plan": {}}', txt.replace('"budget": 10', '"budget": 1e999')):
            with self.assertRaises(R.O.PlanError):
                R.validate_envelope(bad, g["context"])
        with self.assertRaises(R.O.PlanError):
            R.validate_envelope(txt + " " * (256 * 1024), g["context"])

    def test_no_infinity_in_output(self):
        for c in self.doc["cases"]:
            r = R.optimize_resilience(c["context"], c["envelope"])
            self.assertNotIn("Infinity", json.dumps(r))


if __name__ == "__main__":
    unittest.main()
