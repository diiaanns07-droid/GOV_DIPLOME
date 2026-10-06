"""Stage 3: metamorphic properties of city-resilience-v1 (on the K06 reference) and mutation checks
proving that the gold fixture detects a broken worst vector and broken tie-breaks.
Run: python3 -m unittest -v test_resilience_metamorphic
"""
import copy, json, os, random, unittest
import resilience_oracle as R

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "resilience_gold.json")


def robust_view(r):
    return (r["status"], r["robust"]["selected_ids"] if r["robust"] else None,
            r["robust"]["worst_vector"] if r["robust"] else None)


def wkey(v):                                   # external worst vector -> comparable (null max = +inf)
    return (v[0], v[1], float("inf") if v[2] is None else v[2])


class Metamorphic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as fh:
            doc = json.load(fh)
        cls.cases = [c for c in doc["cases"] if c["gold"]["status"] == "optimal"]
        cls.rng = random.Random(42)

    def test_permutations_do_not_change_robust(self):
        for c in self.cases:
            e = copy.deepcopy(c["envelope"])
            for k in ("control_points", "candidates"):
                self.rng.shuffle(e["plan"][k])
            self.rng.shuffle(e["cases"])
            for cs in e["cases"]:
                self.rng.shuffle(cs["disabled_source_ids"])
            ctx = dict(c["context"], records=self.rng.sample(c["context"]["records"], len(c["context"]["records"])))
            a, b = R.optimize_resilience(c["context"], c["envelope"]), R.optimize_resilience(ctx, e)
            self.assertEqual(robust_view(a), robust_view(b), c["case"])
            self.assertEqual(a["robust"]["worst_case_ids"], b["robust"]["worst_case_ids"])
            self.assertEqual(a["resilience_problem_digest"], b["resilience_problem_digest"])

    def test_duplicate_case_changes_nothing_but_the_list(self):
        for c in self.cases:
            if len(c["envelope"]["cases"]) >= 7:
                continue
            e = copy.deepcopy(c["envelope"])
            src = e["cases"][0]
            e["cases"].append({"id": "zz_dup", "label": "дубль", "disabled_source_ids": list(src["disabled_source_ids"])})
            a, b = R.optimize_resilience(c["context"], c["envelope"]), R.optimize_resilience(c["context"], e)
            self.assertEqual(robust_view(a), robust_view(b), c["case"])
            if src["id"] in a["robust"]["worst_case_ids"]:
                self.assertIn("zz_dup", b["robust"]["worst_case_ids"])

    def test_adding_a_case_never_improves_min_worst_and_keeps_nominal(self):
        for c in self.cases:
            if len(c["envelope"]["cases"]) >= 7:
                continue
            src_ids = sorted(r["id"] for r in c["context"]["records"] if r["group"] == c["envelope"]["plan"]["category"])
            e = copy.deepcopy(c["envelope"])
            e["cases"].append({"id": "zz_new", "label": "новый случай", "disabled_source_ids": src_ids[:max(1, len(src_ids) // 2)]})
            a, b = R.optimize_resilience(c["context"], c["envelope"]), R.optimize_resilience(c["context"], e)
            self.assertGreaterEqual(wkey(b["robust"]["worst_vector"]), wkey(a["robust"]["worst_vector"]), c["case"])
            self.assertEqual(a["nominal"]["selected_ids"], b["nominal"]["selected_ids"])
            self.assertEqual(a["nominal"]["per_case"][0], b["nominal"]["per_case"][0])          # base row unchanged

    def test_robust_vs_nominal_order(self):
        for c in self.cases:
            r = R.optimize_resilience(c["context"], c["envelope"])
            self.assertLessEqual(wkey(r["robust"]["worst_vector"]), wkey(r["nominal"]["worst_vector"]))
            self.assertGreaterEqual(wkey(r["robust"]["per_case"][0]["loss_vector"]), wkey(r["nominal"]["per_case"][0]["loss_vector"]))
            if r["price_of_robustness_m"] is not None:
                self.assertGreaterEqual(r["price_of_robustness_m"], 0.0)
            ev = R.evaluate_resilience(c["context"], c["envelope"], r["robust"]["selected_ids"])
            self.assertEqual(ev["worst_vector"], r["robust"]["worst_vector"]); self.assertTrue(ev["feasible"])


class Mutations(unittest.TestCase):
    """Broken variants of the reference must disagree with the stored gold on at least one fixture case."""
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as fh:
            cls.cases = json.load(fh)["cases"]

    def mismatches(self):
        from test_resilience import view
        return [c["case"] for c in self.cases if view(R.optimize_resilience(c["context"], c["envelope"])) != view(c["gold"])]

    def with_patch(self, name, fn):
        orig = getattr(R, name)
        setattr(R, name, fn(orig))
        try:
            return self.mismatches()
        finally:
            setattr(R, name, orig)

    def test_baseline_has_no_mismatch(self):
        self.assertEqual(self.mismatches(), [])

    def test_componentwise_max_instead_of_lex_max(self):
        def mut(orig):
            def per_case(problems, env, ids):
                per, W, worst = orig(problems, env, ids)
                Ls = [R._L(p["metrics"]) for p in per]
                Wc = tuple(max(L[i] for L in Ls) for i in range(3))      # NOT a real case: forbidden by the spec
                return per, Wc, worst
            return per_case
        self.assertTrue(self.with_patch("_per_case", mut))

    def test_only_first_worst_case_listed(self):
        def mut(orig):
            def per_case(problems, env, ids):
                per, W, worst = orig(problems, env, ids)
                return per, W, worst[:1]
            return per_case
        bad = self.with_patch("_per_case", mut)
        self.assertIn("equal_worst_cases", bad)

    def test_unknown_max_as_zero(self):
        def mut(orig):
            return lambda m: (m["unknown_count"], m["weighted_sum_mm"], 0 if m["max_mm"] is None else m["max_mm"])
        self.assertTrue(self.with_patch("_L", mut))

    def test_tie_breaks(self):
        # reversed ID tie-break: run the reference on IDs renamed in reverse order, then map the answer back
        def mut_ids(orig):
            def opt(ctx, env):
                e = copy.deepcopy(env)
                ids = sorted(c["id"] for c in e["plan"]["candidates"])
                ren = {cid: f"r{len(ids) - i:03d}" for i, cid in enumerate(ids)}     # strictly reverses ID order
                return orig(ctx, e) if not ren else _rename_back(orig(ctx, _rename(e, ren)), ren)
            return opt
        bad = self.with_patch("optimize_resilience", mut_ids)
        self.assertIn("id_tiebreak", bad)

        def mut_cost(orig):
            def opt(ctx, env):
                e = copy.deepcopy(env)
                for c in e["plan"]["candidates"]:
                    c["cost"] = 1
                e["plan"]["budget"] = max(e["plan"]["budget"], len(e["plan"]["candidates"]))
                return orig(ctx, e)
            return opt
        self.assertIn("cost_tiebreak", self.with_patch("optimize_resilience", mut_cost))


def _rename(env, ren):
    e = copy.deepcopy(env)
    for c in e["plan"]["candidates"]:
        c["id"] = ren[c["id"]]
    for k in ("required_ids", "excluded_ids", "selected_ids"):
        e["plan"][k] = [ren[x] for x in e["plan"][k]]
    return e


def _rename_back(r, ren):
    inv = {v: k for k, v in ren.items()}
    s = json.dumps(r)
    for new, old in inv.items():
        s = s.replace(json.dumps(new), json.dumps(old))
    return json.loads(s)


if __name__ == "__main__":
    unittest.main()
