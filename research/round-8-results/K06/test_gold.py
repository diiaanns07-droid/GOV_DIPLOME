"""Stage 2: plan_oracle vs independent gold on fixed-seed cases (fixtures/gold_cases.json).
Run: python3 -m unittest -v test_gold
"""
import json, os, unittest
import plan_oracle as O

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "gold_cases.json")


def comparable(r):
    """Fields compared between implementations (evaluated count is convention-dependent and excluded)."""
    if r["status"] != "optimal":
        return {"status": r["status"], "reasons": sorted(r.get("reasons", []))}
    ob = {}
    for k, v in r["objectives"].items():
        m = v["metrics"]
        ob[k] = {"ids": v["selected_ids"], **{f: m[f] for f in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost")}}
    return {"status": "optimal", "feasible_count": r["feasible_count"], "objectives": ob,
            "pareto": [[p["cost"], p["weighted_sum_mm"], p["selected_ids"]] for p in r["pareto"]]}


def unmap(res, id_map):
    inv = {v: k for k, v in id_map.items()}
    s = json.dumps(res)
    for new, old in inv.items():
        s = s.replace(json.dumps(new), json.dumps(old))
    return json.loads(s)


class Gold(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.load(open(FIX, encoding="utf-8"))
        cls.by_name = {c["case"]: c for c in cls.doc["cases"]}

    def test_oracle_equals_gold(self):
        for c in self.doc["cases"]:
            with self.subTest(case=c["case"]):
                r = O.optimize(c["context"], c["scenario"])
                self.assertEqual(comparable(r), comparable(c["gold"]))

    def test_permutations_same_result(self):
        for c in self.doc["cases"]:
            if "permutation_of" not in c:
                continue
            with self.subTest(case=c["case"]):
                orig = comparable(O.optimize(self.by_name[c["permutation_of"]]["context"], self.by_name[c["permutation_of"]]["scenario"]))
                got = comparable(O.optimize(c["context"], c["scenario"]))
                self.assertEqual(unmap(got, c["id_map"]) if "id_map" in c else got, orig)
                same_problem = not c.get("id_map")      # renaming zero candidates leaves the problem unchanged
                d1 = O.problem_digest(self.by_name[c["permutation_of"]]["context"], self.by_name[c["permutation_of"]]["scenario"])
                d2 = O.problem_digest(c["context"], c["scenario"])
                self.assertEqual(d1 == d2, same_problem)

    def test_named_expectations(self):
        g = lambda n: self.by_name[n]["gold"]
        self.assertEqual({k: v["selected_ids"] for k, v in g("budget_zero")["objectives"].items()},
                         {"mean": [], "minimax": [], "coverage": []})
        self.assertEqual(g("budget_zero")["feasible_count"], 1)
        self.assertEqual(g("required_over_budget")["status"], "infeasible")
        self.assertEqual(g("required_over_count")["reasons"], ["required_count_exceeds_max_selected"])
        nb = g("no_baseline")["objectives"]["mean"]["metrics"]
        self.assertEqual(nb["unknown_count"], 0)             # 2 candidates cover every point -> all known
        nb0 = g("no_baseline_budget_zero")
        self.assertEqual(nb0["objectives"]["mean"]["metrics"]["unknown_count"], 3)
        self.assertEqual(nb0["pareto"], [])                  # no complete plan -> no comparable Pareto point
        self.assertEqual(g("no_candidates")["feasible_count"], 1)
        t = g("tie_identical_candidates")["objectives"]
        self.assertNotIn("c1b", sum((v["selected_ids"] for v in t.values()), []))   # c1 < c1b wins equal plans
        pd = g("pareto_duplicates")["pareto"]
        self.assertEqual(len({(p["cost"], p["weighted_sum_mm"]) for p in pd}), len(pd))
        self.assertIn(["e"], [p["selected_ids"] for p in pd])                         # e < w by ID
        self.assertNotIn(["w"], [p["selected_ids"] for p in pd])

    def test_all_three_objectives_present_when_optimal(self):
        for c in self.doc["cases"]:
            if c["gold"]["status"] == "optimal":
                self.assertEqual(set(c["gold"]["objectives"]), {"mean", "minimax", "coverage"})


if __name__ == "__main__":
    unittest.main()
