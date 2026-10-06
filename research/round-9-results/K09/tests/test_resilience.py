"""Оракул устойчивости city-resilience-v1: ручная фикстура, наивный перебор, инварианты, валидация, digest."""
import copy, itertools, json, math, random, sys, unittest
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09res import resilience as RS  # noqa: E402
from k09plan import data, suite  # noqa: E402  (r8, только чтение; подключено k09res.r8)

REPO = K.parents[2]
BUILD_SHA = "d865dd4a124291e10dd0b7bb1d9eada20d34c268"
D, DSHA = data.load_slice(repo=str(REPO), sha=BUILD_SHA)
REAL = {"shymkent_school": suite.make_context(D, DSHA, "shymkent", "school", "real_slice_records"),
        "astana_clinic": suite.make_context(D, DSHA, "astana", "outpatient_clinic", "real_slice_records")}

# ---------- ручная фикстура на меридиане lon=69.6 (ожидаемые мм — формула R·|Δφ|, не модуль) ----------
R = 6371008.8


def mer_mm(dlat_deg):
    return int(math.floor(R * math.radians(abs(dlat_deg)) * 1000 + 0.5))


HAND_CTX = {"city_id": "shymkent", "category": "school", "bbox": [69.5, 42.2, 69.7, 42.4], "source_snapshot": "test-hand",
            "sources": [{"id": "s1", "lon": 69.6, "lat": 42.300}, {"id": "s2", "lon": 69.6, "lat": 42.310}]}


def hand_env(cases, budget=100, ms=1):
    return {"schema_version": RS.SCHEMA, "cases": cases, "plan": {
        "schema_version": "city-plan-v2", "city_id": "shymkent", "source_snapshot": "test-hand", "category": "school",
        "control_points": [{"id": "p1", "lon": 69.6, "lat": 42.300, "weight": 1}, {"id": "p2", "lon": 69.6, "lat": 42.310, "weight": 1}],
        "candidates": [{"id": "cA", "lon": 69.6, "lat": 42.305, "category": "school", "kind": "hypothetical", "cost": 100},
                       {"id": "cB", "lon": 69.6, "lat": 42.301, "category": "school", "kind": "hypothetical", "cost": 100}],
        "budget": budget, "max_selected": ms, "coverage_radius_m": 300, "required_ids": [], "excluded_ids": [], "selected_ids": []}}


X = {"id": "X", "label": "без s1", "disabled_source_ids": ["s1"]}
Y = {"id": "Y", "label": "без s2", "disabled_source_ids": ["s2"]}
Z = {"id": "Z", "label": "без обеих записей", "disabled_source_ids": ["s1", "s2"]}
M10, M5, M1, M9 = mer_mm(0.010), mer_mm(0.005), mer_mm(0.001), mer_mm(0.009)


class TestHand(unittest.TestCase):
    def test_distances_formula(self):
        self.assertEqual((M10, M5, M1, M9), (1111951, 555975, 111195, 1000756))

    def test_single_case_robust_differs_from_nominal(self):
        r = RS.optimize_resilience(HAND_CTX, hand_env([X]))
        self.assertEqual(r["status"], "optimal")
        self.assertEqual(r["nominal"]["selected_ids"], [])                       # на base всё уже 0 → дешевле всего пустой
        self.assertEqual(r["robust"]["selected_ids"], ["cB"])
        self.assertEqual(r["nominal"]["worst_vector"], {"unknown_count": 0, "weighted_sum_mm": M10, "max_mm": M10})
        self.assertEqual(r["robust"]["worst_vector"], {"unknown_count": 0, "weighted_sum_mm": M1, "max_mm": M1})
        self.assertEqual(r["robust"]["worst_case_ids"], ["X"])
        self.assertEqual(r["price_of_robustness_m"], 0.0)
        self.assertFalse(r["same_plan"])
        self.assertEqual(r["feasible_count"], 3)

    def test_two_cases_tie_and_choice(self):
        r = RS.optimize_resilience(HAND_CTX, hand_env([X, Y]))
        self.assertEqual(r["robust"]["selected_ids"], ["cA"])
        self.assertEqual(r["robust"]["worst_vector"]["weighted_sum_mm"], M5)
        self.assertEqual(r["robust"]["worst_case_ids"], ["X", "Y"])              # ничья: перечислены все худшие
        self.assertEqual(r["nominal"]["worst_case_ids"], ["X", "Y"])
        ev = RS.evaluate_resilience(HAND_CTX, hand_env([X, Y]), ["cB"])
        self.assertEqual(ev["worst_vector"], {"unknown_count": 0, "weighted_sum_mm": M9, "max_mm": M9})
        self.assertEqual(ev["worst_case_ids"], ["Y"])

    def test_all_disabled_unknown_separately(self):
        r = RS.optimize_resilience(HAND_CTX, hand_env([X, Y, Z]))
        nz = r["nominal"]
        self.assertEqual(nz["selected_ids"], [])
        self.assertEqual(nz["worst_vector"], {"unknown_count": 2, "weighted_sum_mm": 0, "max_mm": None})
        self.assertEqual(nz["worst_case_ids"], ["Z"])
        zc = next(c for c in nz["per_case"] if c["case_id"] == "Z")
        self.assertIsNone(zc["weighted_mean_mm"]); self.assertIsNone(zc["max_mm"]); self.assertEqual(zc["covered_weight"], 0)
        self.assertEqual(r["robust"]["selected_ids"], ["cA"])
        self.assertEqual(r["robust"]["worst_vector"], {"unknown_count": 0, "weighted_sum_mm": 2 * M5, "max_mm": M5})
        r2 = RS.optimize_resilience(HAND_CTX, hand_env([X, Y, Z], budget=200, ms=2))
        self.assertEqual(r2["robust"]["selected_ids"], ["cA", "cB"])
        self.assertEqual(r2["robust"]["worst_vector"], {"unknown_count": 0, "weighted_sum_mm": M1 + M5, "max_mm": M5})
        self.assertEqual(r2["robust"]["worst_case_ids"], ["Z"])

    def test_duplicate_case_and_order_do_not_matter(self):
        X2 = {"id": "X2", "label": "дубль X", "disabled_source_ids": ["s1"]}
        a = RS.optimize_resilience(HAND_CTX, hand_env([X, Y]))
        b = RS.optimize_resilience(HAND_CTX, hand_env([Y, X2, X]))
        for k in ("nominal", "robust"):
            self.assertEqual(a[k]["selected_ids"], b[k]["selected_ids"]); self.assertEqual(a[k]["worst_vector"], b[k]["worst_vector"])
        self.assertEqual(b["robust"]["worst_case_ids"], ["X", "X2", "Y"])
        c = RS.optimize_resilience(HAND_CTX, hand_env([Y, X]))
        self.assertEqual(a["resilience_problem_digest"], c["resilience_problem_digest"])
        self.assertNotEqual(a["resilience_problem_digest"], b["resilience_problem_digest"])


    def test_case_rows_nearest_inside_case(self):
        ev = RS.evaluate_resilience(HAND_CTX, hand_env([X]), ["cB"])
        base, x = ev["per_case"][0]["rows"], ev["per_case"][1]["rows"]
        self.assertEqual(base[0], {"point_id": "p1", "before_mm": 0, "nearest_before": {"kind": "source", "id": "s1"}, "after_mm": 0,
                                   "nearest_after": {"kind": "source", "id": "s1"}, "delta_mm": 0})
        self.assertEqual(x[0], {"point_id": "p1", "before_mm": M10, "nearest_before": {"kind": "source", "id": "s2"}, "after_mm": M1,
                                "nearest_after": {"kind": "hypothetical", "id": "cB"}, "delta_mm": M10 - M1})
        ez = RS.evaluate_resilience(HAND_CTX, hand_env([Z]), [])
        self.assertEqual(ez["per_case"][1]["rows"][1], {"point_id": "p2", "before_mm": None, "nearest_before": None, "after_mm": None,
                                                       "nearest_after": None, "delta_mm": None})
        tie_ctx = dict(HAND_CTX, sources=[{"id": "s1", "lon": 69.6, "lat": 42.305}, {"id": "s2", "lon": 69.6, "lat": 42.310}])
        et = RS.evaluate_resilience(tie_ctx, hand_env([X]), ["cA"])                    # cA в той же точке, что s1
        self.assertEqual(et["per_case"][0]["rows"][0]["nearest_after"], {"kind": "source", "id": "s1"})
        self.assertEqual(et["per_case"][1]["rows"][0]["nearest_after"], {"kind": "hypothetical", "id": "cA"})

    def test_limit_also_on_trusted_path(self):
        env = hand_env([X]); env["plan"]["candidates"] = [dict(env["plan"]["candidates"][0], id=f"c{i}") for i in range(13)]
        with self.assertRaises(RS.ResError) as cm:
            RS.evaluate_resilience(HAND_CTX, env, [], validated=True)
        self.assertEqual(cm.exception.code, "too_many_candidates")

# ---------- независимый наивный оракул (своя формула, itertools, свои ключи) ----------
def nv_mm(a, b):
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return int(math.floor(2 * R * math.asin(math.sqrt(min(1.0, max(0.0, h)))) * 1000 + 0.5))


def naive(ctx, env):
    plan, cases = env["plan"], [{"id": "base", "disabled_source_ids": []}] + env["cases"]
    pts = plan["control_points"]
    out = []
    free = [c for c in plan["candidates"] if c["id"] not in plan["excluded_ids"]]
    for r in range(plan["max_selected"] + 1):
        for comb in itertools.combinations(free, r):
            ids = sorted(c["id"] for c in comb)
            if not set(plan["required_ids"]) <= set(ids):
                continue
            cost = sum(c["cost"] for c in comb)
            if cost > plan["budget"]:
                continue
            Ls = []
            for cs in cases:
                objs = [s for s in ctx["sources"] if s["id"] not in cs["disabled_source_ids"]] + list(comb)
                after = [min((nv_mm(p, o) for o in objs), default=None) for p in pts]
                unk = sum(a is None for a in after)
                ws = sum(p["weight"] * a for p, a in zip(pts, after) if a is not None)
                mx = max(after) if unk == 0 else math.inf
                Ls.append((cs["id"], (unk, ws, mx)))
            out.append({"ids": ids, "cost": cost, "Ls": Ls})
    return out


def rand_env(rng, ctx, nc, npnt, ncases, ms, req=(), exc=()):
    w, s, e, n = ctx["bbox"]
    pts = [{"id": f"p{i:02d}", "lon": round(rng.uniform(w, e), 6), "lat": round(rng.uniform(s, n), 6), "weight": rng.randint(1, 100)} for i in range(npnt)]
    cands = [{"id": f"c{i:02d}", "lon": round(rng.uniform(w, e), 6), "lat": round(rng.uniform(s, n), 6), "category": ctx["category"],
              "kind": "hypothetical", "cost": rng.randint(100, 1000)} for i in range(nc)]
    src = [x["id"] for x in ctx["sources"]]
    cases = []
    for k in range(ncases):
        kind = rng.choice(["one", "many", "all", "dup"])
        if kind == "all":
            ds = list(src)
        elif kind == "dup" and cases:
            ds = list(cases[-1]["disabled_source_ids"])
        else:
            ds = rng.sample(src, 1 if kind == "one" else rng.randint(2, 6))
        cases.append({"id": f"case{k}", "label": f"случай {k}", "disabled_source_ids": ds})
    costs = sorted((c["cost"] for c in cands), reverse=True)
    return {"schema_version": RS.SCHEMA, "cases": cases, "plan": {
        "schema_version": "city-plan-v2", "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"], "category": ctx["category"],
        "control_points": pts, "candidates": cands, "budget": int(rng.choice([0.4, 0.7, 1.0]) * sum(costs[:max(ms, 1)])), "max_selected": ms,
        "coverage_radius_m": 300, "required_ids": list(req), "excluded_ids": list(exc), "selected_ids": []}}


class TestNaive(unittest.TestCase):
    def test_seeded_against_naive(self):
        rng = random.Random("k09-r9-res-naive")
        n = 0
        for t in range(36):
            ctx = REAL["shymkent_school" if t % 2 else "astana_clinic"]
            req = ("c01",) if t % 5 == 0 else ()
            exc = ("c00",) if t % 7 == 0 else ()
            env = rand_env(rng, ctx, rng.randint(3, 7), rng.randint(2, 7), rng.randint(1, 4), rng.randint(1, 3), req, exc)
            plans = naive(ctx, env)
            r = RS.optimize_resilience(ctx, env)
            if not plans:
                self.assertEqual(r["status"], "infeasible"); continue
            self.assertEqual(r["feasible_count"], len(plans))
            nom = min(plans, key=lambda p: (p["Ls"][0][1], p["cost"], p["ids"]))
            rob = min(plans, key=lambda p: (max(L for _, L in p["Ls"]), p["Ls"][0][1], p["cost"], p["ids"]))
            self.assertEqual(r["nominal"]["selected_ids"], nom["ids"], t)
            self.assertEqual(r["robust"]["selected_ids"], rob["ids"], t)
            W = max(L for _, L in rob["Ls"])
            self.assertEqual(r["robust"]["worst_vector"], {"unknown_count": W[0], "weighted_sum_mm": W[1], "max_mm": None if W[2] == math.inf else W[2]})
            self.assertEqual(r["robust"]["worst_case_ids"], sorted(cid for cid, L in rob["Ls"] if L == W))
            for k, (cid, L) in enumerate(rob["Ls"]):
                pc = r["robust"]["per_case"][k]
                self.assertEqual((pc["case_id"], pc["unknown_count"], pc["weighted_sum_mm"]), (cid, L[0], L[1]))
            n += 1
        self.assertGreaterEqual(n, 25)

    def test_invariants_real_slices(self):
        rng = random.Random("k09-r9-res-inv")
        for t in range(30):
            ctx = REAL["shymkent_school" if t % 2 else "astana_clinic"]
            env = rand_env(rng, ctx, rng.randint(4, 10), rng.randint(5, 15), rng.randint(1, 7), 3)
            r = RS.optimize_resilience(ctx, env)
            vec = lambda v: (v["unknown_count"], v["weighted_sum_mm"], math.inf if v["max_mm"] is None else v["max_mm"])
            self.assertLessEqual(vec(r["robust"]["worst_vector"]), vec(r["nominal"]["worst_vector"]))
            self.assertLessEqual(vec(r["nominal"]["base_vector"]), vec(r["robust"]["base_vector"]))
            if r["price_of_robustness_m"] is not None:
                self.assertGreaterEqual(r["price_of_robustness_m"], 0.0)
            if r["same_plan"]:
                self.assertEqual(r["price_of_robustness_m"], 0.0)
            ev = RS.evaluate_resilience(ctx, env, r["robust"]["selected_ids"])
            self.assertEqual(ev["worst_vector"], r["robust"]["worst_vector"])
            env2 = copy.deepcopy(env)
            random.Random(t).shuffle(env2["cases"]); random.Random(t).shuffle(env2["plan"]["candidates"]); random.Random(t).shuffle(env2["plan"]["control_points"])
            for c in env2["cases"]:
                random.Random(t).shuffle(c["disabled_source_ids"])
            r2 = RS.optimize_resilience(ctx, env2)
            self.assertEqual(r2["resilience_problem_digest"], r["resilience_problem_digest"])
            for k in ("nominal", "robust"):
                self.assertEqual(r2[k]["selected_ids"], r[k]["selected_ids"]); self.assertEqual(r2[k]["worst_case_ids"], r[k]["worst_case_ids"])


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.ctx = REAL["astana_clinic"]
        self.env = rand_env(random.Random(3), self.ctx, 6, 5, 2, 2)
        self.src = [s["id"] for s in self.ctx["sources"]]

    def code(self, env):
        try:
            RS.validate_resilience(env, self.ctx)
        except RS.ResError as e:
            return e.code
        return "accepted"

    def test_accepts_valid_and_rejects(self):
        self.assertEqual(self.code(self.env), "accepted")
        E = lambda: copy.deepcopy(self.env)
        cases = []
        e = E(); e["extra"] = 1; cases.append(("unknown_field", e))
        e = E(); e["schema_version"] = "city-plan-v2"; cases.append(("bad_version", e))
        e = E(); e["cases"][0]["id"] = "base"; cases.append(("reserved_case_id", e))
        e = E(); e["cases"][1]["id"] = e["cases"][0]["id"]; cases.append(("duplicate_case_id", e))
        e = E(); e["cases"][0]["disabled_source_ids"] = ["c00"]; cases.append(("candidate_not_source", e))
        e = E(); e["cases"][0]["disabled_source_ids"] = ["nope"]; cases.append(("unknown_source", e))
        e = E(); e["cases"][0]["disabled_source_ids"] = []; cases.append(("bad_exclusions", e))
        e = E(); e["cases"][0]["disabled_source_ids"] = [self.src[0], self.src[0]]; cases.append(("duplicate_exclusion", e))
        e = E(); e["cases"] = []; cases.append(("bad_cases", e))
        e = E(); e["cases"] = [dict(self.env["cases"][0], id=f"k{i}") for i in range(8)]; cases.append(("bad_cases", e))
        e = E(); e["cases"][0]["label"] = ""; cases.append(("bad_label", e))
        e = E(); e["cases"][0]["label"] = "x" * 121; cases.append(("bad_label", e))
        e = E(); e["cases"][0]["label"] = "a\u0007b"; cases.append(("bad_label", e))
        e = E(); e["cases"][0]["extra"] = 1; cases.append(("bad_case_shape", e))
        e = E(); e["plan"]["derived_results"] = {}; cases.append(("derived_not_accepted", e))
        e = E(); e["plan"]["control_points"][0]["weight"] = 0; cases.append(("bad_plan", e))
        e = E(); e["plan"]["candidates"][0]["id"] = "c:0"; e["plan"]["selected_ids"] = []; cases.append(("bad_id", e))
        for want, env in cases:
            self.assertEqual(self.code(env), want, want)
        self.assertEqual(self.code(dict(E(), cases=[dict(self.env["cases"][0], label="x" * 120)])), "accepted")
        self.assertEqual(self.code(dict(E(), cases=[dict(self.env["cases"][0], disabled_source_ids=list(self.src))])), "accepted")

    def test_too_many_candidates_before_precompute(self):
        env = rand_env(random.Random(4), self.ctx, 13, 5, 1, 2)
        called = []
        orig = RS.CaseModel
        RS.CaseModel = lambda *a, **k: called.append(1) or orig(*a, **k)
        try:
            for fn in (lambda: RS.optimize_resilience(self.ctx, env), lambda: RS.evaluate_resilience(self.ctx, env, [])):
                with self.assertRaises(RS.ResError) as cm:
                    fn()
                self.assertEqual(cm.exception.code, "too_many_candidates")
        finally:
            RS.CaseModel = orig
        self.assertEqual(called, [])
        env12 = rand_env(random.Random(4), self.ctx, 12, 5, 1, 2)
        self.assertEqual(RS.optimize_resilience(self.ctx, env12)["subsets_total"], 4096)

    def test_text_import_strict(self):
        txt = json.dumps(self.env)
        self.assertEqual(RS.validate_resilience(txt, self.ctx)["schema_version"], RS.SCHEMA)
        for bad, code in [('{"a":1,"a":2}', "duplicate_json_key"), ('{"a": NaN}', "non_finite_literal"), ('{"a": 1e999}', "non_finite_number"),
                          (" " * (256 * 1024 + 1), "import_too_large")]:
            with self.assertRaises(RS.ResError) as cm:
                RS.validate_resilience(bad, self.ctx)
            self.assertEqual(cm.exception.code, code)

    def test_mutation_after_validation_does_not_bypass(self):
        env = copy.deepcopy(self.env)
        clean = RS.validate_resilience(env, self.ctx)
        env["plan"]["candidates"].extend(copy.deepcopy(env["plan"]["candidates"]) * 3)
        self.assertEqual(len(clean["plan"]["candidates"]), 6)

    def test_infeasible_required_and_manual(self):
        env = copy.deepcopy(self.env)
        env["plan"]["required_ids"] = ["c00", "c01", "c02"]; env["plan"]["max_selected"] = 2
        r = RS.optimize_resilience(self.ctx, env)
        self.assertEqual(r["status"], "infeasible"); self.assertIn("required_exceeds_max_selected", r["reasons"])
        self.assertIsNone(r["price_of_robustness_m"]); self.assertEqual(r["price_null_reason"], "infeasible")
        ev = RS.evaluate_resilience(self.ctx, self.env, ["c00", "c01", "c02"])
        self.assertFalse(ev["feasible"]); self.assertIn("too_many", ev["infeasible_reasons"])

    def test_digests(self):
        a = RS.resilience_problem_digest(self.ctx, self.env)
        e2 = copy.deepcopy(self.env); e2["plan"]["selected_ids"] = ["c00"]
        self.assertEqual(RS.resilience_problem_digest(self.ctx, e2), a)
        self.assertNotEqual(RS.resilience_scenario_digest(self.ctx, e2), RS.resilience_scenario_digest(self.ctx, self.env))
        e3 = copy.deepcopy(self.env); e3["cases"][0]["label"] = "другое имя"
        self.assertNotEqual(RS.resilience_problem_digest(self.ctx, e3), a)
        self.assertNotEqual(RS.exclusions_digest(e3), RS.exclusions_digest(dict(self.env, cases=self.env["cases"][:1])))


if __name__ == "__main__":
    unittest.main()
