"""Stage 3: metamorphic properties of city-plan-v2 optimisation, checked on the oracle.
Base problems: optimal cases of fixtures/gold_cases.json (synthetic + real-record cases). Run:
  python3 -m unittest -v test_metamorphic
Properties (all follow from the spec, none needs a gold answer):
  M1 larger budget (same constraints)        -> best key of every objective is not worse (feasible set grows)
  M2 larger max_selected                     -> same
  M3 adding a free candidate                 -> not worse; removing all candidates -> only the empty plan
  M4 adding a source record                  -> no after_mm of any fixed plan increases
  M5 a costlier duplicate of a candidate      -> never in any winner while the original is allowed
  M6 Pareto front                            -> mutually non-dominated, weakly dominates every complete feasible plan
  M7 scaling all weights by k                -> same winners for mean and minimax and coverage
  M8 winner metrics                          -> equal to evaluate() of the same selection
"""
import copy, json, os, unittest
from itertools import combinations
import plan_oracle as O

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "gold_cases.json")


def keys(res):
    return {n: O.objective_keys(v["metrics"], v["selected_ids"])[n] for n, v in res["objectives"].items()}


class Metamorphic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        doc = json.load(open(FIX, encoding="utf-8"))
        cls.cases = [c for c in doc["cases"] if c["gold"]["status"] == "optimal" and "permutation_of" not in c]

    def opt(self, ctx, sc):
        return O.optimize(ctx, sc)

    def test_M1_budget_monotone(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            base = keys(self.opt(ctx, sc))
            for b in (sc["budget"] + 100, sc["budget"] + 1000, 1_000_000):
                r = self.opt(ctx, dict(sc, budget=min(b, 1_000_000)))
                for n, k in keys(r).items():
                    self.assertLessEqual(k, base[n], f"{c['case']} {n} budget {b}")

    def test_M2_max_selected_monotone(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            if sc["max_selected"] == 5:
                continue
            base, r = keys(self.opt(ctx, sc)), keys(self.opt(ctx, dict(sc, max_selected=sc["max_selected"] + 1)))
            for n in base:
                self.assertLessEqual(r[n], base[n], c["case"])

    def test_M3_add_candidate_and_empty(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            if len(sc["candidates"]) >= 16 or not sc["control_points"]:
                continue
            p = sc["control_points"][0]
            new = {"id": "zz_added", "lon": p["lon"], "lat": p["lat"], "category": sc["category"], "kind": "hypothetical", "cost": 1}
            base, r = keys(self.opt(ctx, sc)), keys(self.opt(ctx, dict(sc, candidates=sc["candidates"] + [new])))
            for n in base:
                self.assertLessEqual(r[n], base[n], c["case"])
            if not sc["required_ids"]:
                e = self.opt(ctx, dict(sc, candidates=[], excluded_ids=[], selected_ids=[]))
                self.assertEqual(e["feasible_count"], 1)
                self.assertEqual({v["selected_ids"] == [] for v in e["objectives"].values()}, {True})

    def test_M4_more_sources_never_increase_distance(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            q = sc["control_points"][-1]
            ctx2 = dict(ctx, records=ctx["records"] + [{"id": "zz_src", "lon": q["lon"], "lat": q["lat"], "group": sc["category"]}])
            for sel in ([], sc["candidates"][:1] and [sc["candidates"][0]["id"]]):
                a, b = O.evaluate(ctx, sc, sel)["rows"], O.evaluate(ctx2, sc, sel)["rows"]
                for ra, rb in zip(a, b):
                    self.assertIsNotNone(rb["after_mm"])
                    if ra["after_mm"] is not None:
                        self.assertLessEqual(rb["after_mm"], ra["after_mm"])
                self.assertEqual(b[-1]["after_mm"], 0)

    def test_M5_costlier_duplicate_never_wins(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            allowed = [x for x in sc["candidates"] if x["id"] not in sc["excluded_ids"] and x["id"] not in sc["required_ids"]]
            if not allowed or len(sc["candidates"]) >= 16:
                continue
            orig = allowed[0]
            dup = dict(orig, id="zz_dup", cost=min(orig["cost"] + 1, 1_000_000))
            r = self.opt(ctx, dict(sc, candidates=sc["candidates"] + [dup]))
            for n, v in r["objectives"].items():
                self.assertNotIn("zz_dup", v["selected_ids"], f"{c['case']} {n}")

    def test_M6_pareto_dominance(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            if len(sc["candidates"]) > 9:
                continue
            front = [(p["cost"], p["weighted_sum_mm"]) for p in self.opt(ctx, sc)["pareto"]]
            for a in front:
                for b in front:
                    if a != b:
                        self.assertFalse(b[0] <= a[0] and b[1] <= a[1], f"{c['case']} {b} dominates {a}")
            ids = [x["id"] for x in sc["candidates"]]
            for k in range(len(ids) + 1):
                for sel in combinations(ids, k):
                    e = O.evaluate(ctx, sc, list(sel))
                    if e["feasible"] and e["metrics"]["unknown_count"] == 0:
                        pt = (e["metrics"]["cost"], e["metrics"]["weighted_sum_mm"])
                        self.assertTrue(any(f[0] <= pt[0] and f[1] <= pt[1] for f in front), f"{c['case']} {sel}")

    def test_M7_weight_scaling(self):
        for c in self.cases:
            sc, ctx = c["scenario"], c["context"]
            k = 100 // max(p["weight"] for p in sc["control_points"])
            if k < 2:
                continue
            sc2 = copy.deepcopy(sc)
            for p in sc2["control_points"]:
                p["weight"] *= k
            a, b = self.opt(ctx, sc)["objectives"], self.opt(ctx, sc2)["objectives"]
            self.assertEqual({n: v["selected_ids"] for n, v in a.items()}, {n: v["selected_ids"] for n, v in b.items()}, c["case"])

    def test_M8_winner_metrics_equal_evaluate(self):
        for c in self.cases:
            r = self.opt(c["context"], c["scenario"])
            for n, v in r["objectives"].items():
                self.assertEqual(O.evaluate(c["context"], c["scenario"], v["selected_ids"])["metrics"], v["metrics"])


if __name__ == "__main__":
    unittest.main()
