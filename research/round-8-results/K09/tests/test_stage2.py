"""Этап 2: exact против наивного перебора, Парето, чувствительность, G1/G2, разрыв, seeded suite, валидатор.

Наивный оракул в этом файле считает расстояния своей формулой, перебирает itertools.combinations и строит ключи
кортежами здесь же — не через exact.optimize и не через Problem.
"""
import itertools, json, math, random, sys, unittest
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan import metric, data, exact, greedy, gap, suite, validate, api  # noqa: E402

REPO = K.parents[2]
FX = json.loads((K / "fixtures/hand_meridian.json").read_text(encoding="utf-8"))
CFG = json.loads((K / "config/experiment_config.json").read_text(encoding="utf-8"))
SLICE, SLICE_SHA = data.load_slice(repo=str(REPO))


def ctx_of(slice_id):
    s = next(x for x in CFG["baselines"]["slices"] if x["id"] == slice_id)
    return suite.make_context(SLICE, SLICE_SHA, s["city"], s["category"], s["baseline"])


# ---------- независимый наивный оракул ----------
def naive_mm(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    d = 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, max(0.0, h))))
    return int(math.floor(d * 1000 + 0.5))


def naive_all(points, sources, cands, radius_m, budget, max_sel, required=(), excluded=()):
    """Все допустимые планы с метриками (по наивной формуле)."""
    plans = []
    free = [c for c in cands if c["id"] not in excluded]
    for r in range(0, max_sel + 1):
        for comb in itertools.combinations(free, r):
            ids = sorted(c["id"] for c in comb)
            if not set(required) <= set(ids):
                continue
            cost = sum(c["cost"] for c in comb)
            if cost > budget:
                continue
            after = []
            for p in points:
                ds = [naive_mm(p["lon"], p["lat"], o["lon"], o["lat"]) for o in list(sources) + list(comb)]
                after.append(min(ds) if ds else None)
            unk = sum(v is None for v in after)
            ws = sum(p["weight"] * v for p, v in zip(points, after) if v is not None)
            mx = max(after) if unk == 0 else None
            cov = sum(p["weight"] for p, v in zip(points, after) if v is not None and v <= radius_m * 1000)
            plans.append({"ids": ids, "cost": cost, "unk": unk, "ws": ws, "mx": mx, "cov": cov})
    return plans


def naive_keys(p):
    m = math.inf if p["mx"] is None else p["mx"]
    return {"mean": (p["unk"], p["ws"], m, p["cost"], p["ids"]),
            "minimax": (p["unk"], m, p["ws"], p["cost"], p["ids"]),
            "coverage": (-p["cov"], p["unk"], p["ws"], m, p["cost"], p["ids"])}


def naive_pareto(plans):
    known = [p for p in plans if p["unk"] == 0]
    pairs = {(p["cost"], p["ws"]) for p in known}
    nd = [q for q in pairs if not any(o != q and o[0] <= q[0] and o[1] <= q[1] for o in pairs)]
    out = []
    for c, w in sorted(nd):
        rep = min(p["ids"] for p in known if (p["cost"], p["ws"]) == (c, w))
        out.append({"cost": c, "weighted_sum_mm": w, "selected_ids": rep})
    return out


def pr_fx(fx=FX, sources=True):
    return metric.Problem(fx["points"], fx["sources"] if sources else [], fx["candidates"], fx["radius_m"])


def small_instances():
    """Seeded маленькие задачи из предрегистрированного генератора (n_cand ≤ 8 — наивный перебор быстрый)."""
    out = []
    for sid in ("shymkent_school", "astana_clinic", "astana_clinic_nobase"):
        ctx = ctx_of(sid)
        for nc, npnt, ratio, wts, ms, rad, seed in [(6, 5, 0.25, "uniform", 3, 300, 0), (8, 7, 0.5, "random_1_100", 3, 300, 1),
                                                    (8, 5, 1.0, "one_heavy", 5, 800, 2), (7, 6, 0.5, "random_1_100", 2, 100, 3),
                                                    (8, 9, 0.25, "random_1_100", 4, 300, 4)]:
            sc = suite.make_scenario(ctx, nc, npnt, ratio, wts, ms, rad, seed, "k09-r8-test")
            out.append((sid, ctx, sc))
    return out


class TestExactHand(unittest.TestCase):
    def test_single_choice_winners(self):
        r = exact.optimize(pr_fx(), 500, 1)
        self.assertEqual(r["status"], "optimal")
        self.assertEqual(r["objectives"]["mean"]["selected_ids"], ["c2"])      # 155673 < 222390 < 355824
        self.assertEqual(r["objectives"]["minimax"]["selected_ids"], ["c1"])   # max 66717
        self.assertEqual(r["objectives"]["coverage"]["selected_ids"], ["c1"])  # covered 4
        self.assertEqual(r["feasible_count"], 3)                              # {}, {c1}, {c2}

    def test_pair_and_empty(self):
        r = exact.optimize(pr_fx(), 800, 2)
        for k in ("mean", "minimax", "coverage"):
            self.assertEqual(r["objectives"][k]["selected_ids"], ["c1", "c2"])
        self.assertEqual(r["objectives"]["mean"]["weighted_sum_mm"], FX["expected"]["c1+c2"]["weighted_sum_mm"])
        r0 = exact.optimize(pr_fx(), 0, 2)
        self.assertEqual(r0["feasible_count"], 1)
        for k in ("mean", "minimax", "coverage"):
            self.assertEqual(r0["objectives"][k]["selected_ids"], [])
            self.assertEqual(r0["objectives"][k]["cost"], 0)

    def test_pareto_hand(self):
        r = exact.optimize(pr_fx(), 800, 2)
        self.assertEqual([(p["cost"], p["weighted_sum_mm"]) for p in r["pareto"]],
                         [(0, 355824), (300, 222390), (500, 155673), (800, 22239)])

    def test_required_excluded_and_infeasible(self):
        pr = pr_fx()
        r = exact.optimize(pr, 800, 2, excluded_ids=["c2"])
        self.assertEqual(r["objectives"]["mean"]["selected_ids"], ["c1"])
        r = exact.optimize(pr, 800, 2, required_ids=["c2"])
        self.assertTrue(all("c2" in v["selected_ids"] for v in r["objectives"].values()))
        self.assertEqual(r["feasible_count"], 2)
        bad = exact.optimize(pr, 300, 2, required_ids=["c2"])
        self.assertEqual((bad["status"], bad["reason"]), ("infeasible", "required_cost_exceeds_budget"))
        self.assertIsNone(bad["objectives"]["mean"])
        bad = exact.optimize(pr, 800, 1, required_ids=["c1", "c2"])
        self.assertEqual(bad["reason"], "required_count_exceeds_max_selected")
        for g in (greedy.greedy_key, greedy.greedy_ratio):
            self.assertEqual(g(pr, "mean", 300, 2, required_ids=["c2"])["status"], "infeasible")

    def test_empty_baseline_unknown_first(self):
        pr = pr_fx(sources=False)
        r = exact.optimize(pr, 500, 1)
        for k in ("mean", "minimax", "coverage"):
            self.assertEqual(r["objectives"][k]["selected_ids"], ["c2"], k)
            self.assertEqual(r["objectives"][k]["unknown_count"], 0)
        # Парето без partial sum: пустой план (unknown=2) не входит
        self.assertNotIn([], [p["selected_ids"] for p in r["pareto"]])
        r0 = exact.optimize(pr, 0, 1)
        m = r0["objectives"]["mean"]
        self.assertEqual((m["unknown_count"], m["max_mm"], m["weighted_mean_mm"]), (2, None, None))
        self.assertEqual(r0["pareto"], [])

    def test_too_large_is_not_optimal(self):
        cands = [{"id": f"c{i:02d}", "lon": 69.6, "lat": 42.3 + i * 1e-4, "cost": 1} for i in range(17)]
        pr = metric.Problem(FX["points"], FX["sources"], cands, 300)
        r = exact.optimize(pr, 10, 2)
        self.assertEqual(r["status"], "too_large")
        r = exact.optimize(pr, 10, 2, excluded_ids=["c16"])
        self.assertEqual(r["status"], "optimal")

    def test_budget_sensitivity(self):
        s = exact.budget_sensitivity(pr_fx(), 800, 2)
        self.assertEqual([x["budget"] for x in s], [0, 400, 800])
        self.assertEqual([x["objectives"]["mean"]["selected_ids"] for x in s], [[], ["c1"], ["c1", "c2"]])
        s1 = exact.budget_sensitivity(pr_fx(), 1, 2)
        self.assertEqual([x["budget"] for x in s1], [0, 1])          # floor(1/2)=0 — без дублей
        s2 = exact.budget_sensitivity(pr_fx(), 600, 2, required_ids=["c1"])      # [0, 300, 600]; c1 стоит 300
        self.assertEqual([x["status"] for x in s2], ["infeasible", "optimal", "optimal"])
        s3 = exact.budget_sensitivity(pr_fx(), 400, 2, required_ids=["c1"])      # floor(400/2)=200 < 300
        self.assertEqual([x["status"] for x in s3], ["infeasible", "infeasible", "optimal"])
        self.assertEqual(s2[0]["reason"], "required_cost_exceeds_budget")


class TestExactVsNaive(unittest.TestCase):
    def test_seeded_small_instances(self):
        n = 0
        for sid, ctx, sc in small_instances():
            for req, exc in [((), ()), (("c01",), ()), ((), ("c00", "c03")), (("c02",), ("c05",))]:
                plans = naive_all(sc["control_points"], ctx["sources"], sc["candidates"], sc["coverage_radius_m"],
                                  sc["budget"], sc["max_selected"], req, exc)
                pr = api.problem_of(ctx, sc)
                r = exact.optimize(pr, sc["budget"], sc["max_selected"], req, exc)
                if not plans:
                    self.assertEqual(r["status"], "infeasible", (sid, req, exc))
                    continue
                self.assertEqual(r["status"], "optimal")
                self.assertEqual(r["feasible_count"], len(plans), (sid, req, exc))
                for k in ("mean", "minimax", "coverage"):
                    best = min(plans, key=lambda p: naive_keys(p)[k])
                    got = r["objectives"][k]
                    self.assertEqual(got["selected_ids"], best["ids"], (sid, k, req, exc))
                    self.assertEqual((got["weighted_sum_mm"], got["max_mm"], got["covered_weight"], got["unknown_count"], got["cost"]),
                                     (best["ws"], best["mx"], best["cov"], best["unk"], best["cost"]))
                self.assertEqual(r["pareto"], naive_pareto(plans), (sid, req, exc))
                n += 1
        self.assertGreaterEqual(n, 40)


class TestDigestAndOrder(unittest.TestCase):
    def test_order_invariance_and_digest(self):
        ctx = ctx_of("astana_clinic")
        sc = suite.make_scenario(ctx, 10, 15, 0.5, "random_1_100", 3, 300, 5, "k09-r8-test")
        sc2 = json.loads(json.dumps(sc))
        ctx2 = dict(ctx, sources=list(reversed(ctx["sources"])))
        rnd = random.Random(11)
        rnd.shuffle(sc2["control_points"]); rnd.shuffle(sc2["candidates"])
        a, b = api.optimize_plans(ctx, sc), api.optimize_plans(ctx2, sc2)
        self.assertEqual(a["problem_digest"], b["problem_digest"])
        self.assertEqual(a["objectives"], b["objectives"])
        self.assertEqual(a["pareto"], b["pareto"])
        pa, pb = api.problem_of(ctx, sc), api.problem_of(ctx2, sc2)
        for obj in ("mean", "minimax", "coverage"):
            for g in (greedy.greedy_key, greedy.greedy_ratio):
                self.assertEqual(g(pa, obj, sc["budget"], 3), g(pb, obj, sc["budget"], 3))
        sc3 = dict(sc, selected_ids=["c01", "c02"])
        self.assertEqual(exact.problem_digest(ctx, sc3), a["problem_digest"])
        self.assertNotEqual(api.scenario_digest(ctx, sc3), api.scenario_digest(ctx, sc))
        self.assertNotEqual(exact.problem_digest(ctx, dict(sc, budget=sc["budget"] + 1)), a["problem_digest"])
        self.assertNotEqual(exact.problem_digest(dict(ctx, source_snapshot="other"), sc), a["problem_digest"])
        self.assertEqual(a["metric_version"], "haversine-mm-v1")


def tie_problem():
    """Два кандидата в одной точке и с одной стоимостью: c07 и c03 — выбрать должен c03 (меньший id)."""
    pts = [{"id": "p1", "lon": 69.6, "lat": 42.31, "weight": 2}, {"id": "p2", "lon": 69.6, "lat": 42.32, "weight": 1}]
    cands = [{"id": "c07", "lon": 69.6, "lat": 42.315, "cost": 100}, {"id": "c03", "lon": 69.6, "lat": 42.315, "cost": 100},
             {"id": "c05", "lon": 69.6, "lat": 42.40, "cost": 100}]
    return metric.Problem(pts, [], cands, 300)


def trap_problem():
    """Классическая ловушка: G1(mean) сначала берёт «средний» a, затем добавляет b; exact берёт пару b+c."""
    pts = [{"id": "p1", "lon": 0.0, "lat": 0.0, "weight": 2}, {"id": "p2", "lon": 0.0, "lat": 0.01, "weight": 2},
           {"id": "p3", "lon": 0.0, "lat": 0.005, "weight": 1}]
    cands = [{"id": "a", "lon": 0.0, "lat": 0.005, "cost": 1}, {"id": "b", "lon": 0.0, "lat": 0.0, "cost": 1},
             {"id": "c", "lon": 0.0, "lat": 0.01, "cost": 1}]
    return metric.Problem(pts, [], cands, 300)


class TestGreedy(unittest.TestCase):
    def test_hand_g1(self):
        pr = pr_fx()
        self.assertEqual(greedy.greedy_key(pr, "mean", 500, 1)["plan"]["selected_ids"], ["c2"])
        self.assertEqual(greedy.greedy_key(pr, "minimax", 500, 1)["plan"]["selected_ids"], ["c1"])
        self.assertEqual(greedy.greedy_key(pr, "coverage", 500, 1)["plan"]["selected_ids"], ["c1"])
        g = greedy.greedy_key(pr, "mean", 800, 2)
        self.assertEqual((g["steps"], g["plan"]["selected_ids"]), (["c2", "c1"], ["c1", "c2"]))
        self.assertEqual(greedy.greedy_key(pr, "mean", 0, 2)["plan"]["selected_ids"], [])

    def test_hand_g2(self):
        pr = pr_fx()
        # mean: прирост/стоимость c1 = 133434/300 ≈ 444.8 > c2 = 200151/500 ≈ 400.3 -> берёт c1; затем лучший одиночный c2 лучше
        g = greedy.greedy_ratio(pr, "mean", 500, 1)
        self.assertEqual((g["steps"], g["plan"]["selected_ids"], g["replaced_by_best_single"]), (["c1"], ["c2"], True))
        g = greedy.greedy_ratio(pr, "mean", 800, 2)
        self.assertEqual((g["steps"], g["plan"]["selected_ids"], g["replaced_by_best_single"]), (["c1", "c2"], ["c1", "c2"], False))

    def test_ties_smaller_id(self):
        pr = tie_problem()
        for obj in ("mean", "minimax", "coverage"):
            self.assertEqual(greedy.greedy_key(pr, obj, 100, 1)["plan"]["selected_ids"], ["c03"], obj)
            self.assertEqual(greedy.greedy_ratio(pr, obj, 100, 1)["plan"]["selected_ids"], ["c03"], obj)
            self.assertEqual(exact.optimize(pr, 100, 1)["objectives"][obj]["selected_ids"], ["c03"], obj)

    def test_trap_gap_defined(self):
        pr = trap_problem()
        e = exact.optimize(pr, 2, 2)["objectives"]["mean"]
        g = greedy.greedy_key(pr, "mean", 2, 2)
        self.assertEqual(g["steps"], ["a", "b"])
        self.assertEqual(e["selected_ids"], ["b", "c"])
        x = gap.gap("mean", g["plan"], e)
        self.assertFalse(x["hit"]); self.assertGreater(x["abs"], 0)
        self.assertEqual(x["abs"], g["plan"]["weighted_sum_mm"] - e["weighted_sum_mm"])
        self.assertAlmostEqual(x["rel"], x["abs"] / e["weighted_sum_mm"])

    def test_suite_feasible_deterministic_never_better(self):
        n = 0
        for sid, ctx, sc in small_instances():
            pr = api.problem_of(ctx, sc)
            ex = exact.optimize(pr, sc["budget"], sc["max_selected"], with_pareto=False)
            for obj in ("mean", "minimax", "coverage"):
                for g in (greedy.greedy_key, greedy.greedy_ratio):
                    r1 = g(pr, obj, sc["budget"], sc["max_selected"])
                    self.assertEqual(r1, g(pr, obj, sc["budget"], sc["max_selected"]))
                    p = r1["plan"]
                    self.assertLessEqual(p["cost"], sc["budget"]); self.assertLessEqual(len(p["selected_ids"]), sc["max_selected"])
                    self.assertEqual(p, pr.evaluate([pr.cand_index[c] for c in p["selected_ids"]]))
                    x = gap.gap(obj, p, ex["objectives"][obj])
                    self.assertFalse(x["greedy_better_than_exact"], (sid, obj, g.__name__))
                    if x["abs"] is not None:
                        self.assertGreaterEqual(x["abs"], 0)
                    n += 1
        self.assertEqual(n, 15 * 3 * 2)

    def test_greedy_respects_required_excluded(self):
        sid, ctx, sc = small_instances()[1]
        pr = api.problem_of(ctx, sc)
        for obj in ("mean", "minimax", "coverage"):
            for g in (greedy.greedy_key, greedy.greedy_ratio):
                p = g(pr, obj, sc["budget"], sc["max_selected"], ["c01"], ["c00", "c03"])["plan"]
                self.assertIn("c01", p["selected_ids"]); self.assertNotIn("c00", p["selected_ids"]); self.assertNotIn("c03", p["selected_ids"])


class TestGap(unittest.TestCase):
    M = {"unknown_count": 0, "weighted_sum_mm": 0, "max_mm": 0, "covered_weight": 0, "cost": 0, "selected_ids": []}

    def test_zero_denominators_give_null(self):
        e = dict(self.M)
        g = dict(self.M, weighted_sum_mm=5, max_mm=5, cost=1, selected_ids=["c1"])
        for obj in ("mean", "minimax"):
            x = gap.gap(obj, g, e)
            self.assertEqual(x["abs"], 5); self.assertIsNone(x["rel"])
        x = gap.gap("coverage", g, e)
        self.assertEqual(x["abs"], 0); self.assertIsNone(x["rel"])

    def test_null_max_and_unknown_worse(self):
        e = dict(self.M, unknown_count=1, max_mm=None, weighted_sum_mm=10)
        g = dict(self.M, unknown_count=1, max_mm=None, weighted_sum_mm=12)
        x = gap.gap("minimax", g, e)
        self.assertIsNone(x["abs"]); self.assertIsNone(x["rel"])
        x = gap.gap("mean", g, e)
        self.assertEqual(x["abs"], 2)
        g2 = dict(g, unknown_count=2)
        x = gap.gap("mean", g2, e)
        self.assertTrue(x["unknown_worse"]); self.assertIsNone(x["abs"]); self.assertFalse(x["hit"])

    def test_hit(self):
        x = gap.gap("mean", dict(self.M, weighted_sum_mm=7), dict(self.M, weighted_sum_mm=7))
        self.assertTrue(x["hit"]); self.assertEqual(x["abs"], 0); self.assertEqual(x["rel"], 0.0)    # знаменатель 7 > 0


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.ctx = ctx_of("shymkent_school")
        self.sc = suite.make_scenario(self.ctx, 16, 25, 0.5, "random_1_100", 5, 300, 9, "k09-r8-test")

    def codes(self, sc):
        return {e["code"] for e in validate.validate(sc, self.ctx)}

    def test_suite_scenarios_valid(self):
        for sid, ctx, sc in small_instances():
            self.assertEqual(validate.validate(sc, ctx), [], sid)
        self.assertEqual(validate.validate(self.sc, self.ctx), [])
        sc, errs = api.validate_plan_scenario(json.dumps(self.sc), self.ctx)
        self.assertEqual((sc, errs), (self.sc, []))

    def test_rejections(self):
        s = json.loads(json.dumps(self.sc))
        cases = []
        cases.append(("unexpected_fields", dict(s, extra=1)))
        cases.append(("foreign_or_stale_snapshot", dict(s, source_snapshot="x")))
        cases.append(("city_mismatch", dict(s, city_id="astana")))
        p = json.loads(json.dumps(s)); p["control_points"][0]["weight"] = 0; cases.append(("weight_int_1_100", p))
        p = json.loads(json.dumps(s)); p["control_points"][0]["weight"] = True; cases.append(("weight_int_1_100", p))
        p = json.loads(json.dumps(s)); p["control_points"][0]["lat"] = 10.0; cases.append(("outside_bbox", p))
        p = json.loads(json.dumps(s)); p["candidates"].append(dict(p["candidates"][0], id="c99")); cases.append(("candidates_count_0_16", p))
        p = json.loads(json.dumps(s)); p["candidates"][1]["id"] = p["candidates"][0]["id"]; cases.append(("duplicate_id", p))
        p = json.loads(json.dumps(s)); p["candidates"][0]["id"] = self.ctx["sources"][0]["id"]; cases.append(("candidate_id_collides_with_source", p))
        p = json.loads(json.dumps(s)); p["candidates"][0]["kind"] = "source"; cases.append(("kind_not_hypothetical", p))
        cases.append(("required_excluded_overlap", dict(s, required_ids=["c01"], excluded_ids=["c01"])))
        cases.append(("unknown_candidate_ref", dict(s, selected_ids=["zz"])))
        cases.append(("max_selected_int_0_5", dict(s, max_selected=6)))
        cases.append(("radius_int_100_5000", dict(s, coverage_radius_m=50)))
        cases.append(("budget_int_0_1e6", dict(s, budget=-1)))
        p = json.loads(json.dumps(s)); p["control_points"] = []; cases.append(("control_points_count_1_25", p))
        for code, sc in cases:
            self.assertIn(code, self.codes(sc), code)

    def test_parse_import(self):
        ok = json.dumps(self.sc)
        for raw, code in [(ok.replace('"budget": ', '"budget": NaN, "x": ', 1), "non_finite_literal"),
                          ('{"a": 1e999}', "non_finite_number"), ('{"a": 1, "a": 2}', "duplicate_json_key"),
                          ("[1]", "root_not_object"), ("{", "invalid_json"), (" " * (256 * 1024 + 1), "import_too_large")]:
            with self.assertRaises(validate.PlanError) as cm:
                validate.parse_import(raw)
            self.assertEqual(cm.exception.code, code, raw[:40])
        self.assertEqual(validate.parse_import(ok), self.sc)

    def test_evaluate_plan_feasibility(self):
        sc = dict(self.sc, required_ids=["c00"], excluded_ids=["c01"])
        r = api.evaluate_plan(self.ctx, sc, ["c01"])
        self.assertEqual(set(r["feasibility"]["reasons"]), {"missing_required", "contains_excluded"})
        r = api.evaluate_plan(self.ctx, sc, ["c00"])
        self.assertTrue(r["feasibility"]["feasible"]); self.assertEqual(len(r["rows"]), 25)


class TestReviewFixes(unittest.TestCase):
    """Исправления по обзору (results/independent/review/findings.json)."""

    def setUp(self):
        self.ctx = ctx_of("astana_clinic")
        self.sc = suite.make_scenario(self.ctx, 6, 5, 0.5, "uniform", 3, 300, 1, "k09-r8-test")

    def test_no_uncaught_exceptions(self):
        s = json.loads(json.dumps(self.sc)); s["control_points"][0]["lon"] = 10 ** 400
        self.assertIn("bad_coordinates", {e["code"] for e in validate.validate(s, self.ctx)})
        deep = '{"a": ' + "[" * 100000 + "]" * 100000 + "}"
        with self.assertRaises(validate.PlanError) as cm:
            validate.parse_import(deep)
        self.assertEqual(cm.exception.code, "invalid_json")
        sc, errs = api.validate_plan_scenario(deep, self.ctx)
        self.assertIsNone(sc); self.assertEqual(errs[0]["code"], "invalid_json")

    def test_integral_float_accepted_fraction_rejected(self):
        s = json.loads(json.dumps(self.sc)); s["control_points"][0]["weight"] = 1.0; s["candidates"][0]["cost"] = 300.0
        self.assertEqual(validate.validate(s, self.ctx), [])
        s["control_points"][0]["weight"] = 1.5
        self.assertIn("weight_int_1_100", {e["code"] for e in validate.validate(s, self.ctx)})

    def test_digest_canonical_numbers(self):
        s = json.loads(json.dumps(self.sc))
        s["candidates"][0]["cost"] = float(s["candidates"][0]["cost"]); s["budget"] = float(s["budget"])
        self.assertEqual(exact.problem_digest(self.ctx, s), exact.problem_digest(self.ctx, self.sc))

    def test_nobase_snapshot_differs(self):
        real, nob = ctx_of("astana_clinic"), ctx_of("astana_clinic_nobase")
        self.assertNotEqual(real["source_snapshot"], nob["source_snapshot"])
        sc = suite.make_scenario(nob, 6, 5, 0.5, "uniform", 3, 300, 1, "k09-r8-test")
        self.assertIn("foreign_or_stale_snapshot", {e["code"] for e in validate.validate(sc, real)})
        self.assertEqual(validate.validate(sc, nob), [])
        self.assertEqual(real["source_snapshot"], suite.slice_snapshot(SLICE_SHA, "astana", "outpatient_clinic"))  # реальный срез не изменился

    def test_g2id_tie_rule(self):
        # пустой baseline: любой кандидат снимает все unknown; G2 берёт самый дешёвый, G2id — меньший id
        pts = [{"id": "p1", "lon": 69.6, "lat": 42.31, "weight": 1}]
        cands = [{"id": "a", "lon": 69.6, "lat": 42.40, "cost": 500}, {"id": "b", "lon": 69.6, "lat": 42.311, "cost": 100}]
        pr = metric.Problem(pts, [], cands, 300)
        g2 = greedy.greedy_ratio(pr, "mean", 1000, 1)
        g2id = greedy.greedy_ratio(pr, "mean", 1000, 1, unknown_tie="id")
        self.assertEqual(g2["steps"], ["b"]); self.assertEqual(g2id["steps"], ["a"])
        self.assertEqual(g2id["plan"]["selected_ids"], ["b"]); self.assertTrue(g2id["replaced_by_best_single"])  # спасает лучший одиночный

class TestSuite(unittest.TestCase):
    def test_seeded_reproducible_and_independent_of_hashseed(self):
        ctx = ctx_of("astana_clinic")
        a = suite.make_scenario(ctx, 10, 15, 0.5, "uniform", 3, 300, 3, "k09-r8-exp-v1")
        b = suite.make_scenario(ctx, 10, 15, 0.5, "uniform", 3, 300, 3, "k09-r8-exp-v1")
        c = suite.make_scenario(ctx, 10, 15, 0.5, "uniform", 3, 300, 4, "k09-r8-exp-v1")
        self.assertEqual(a, b); self.assertNotEqual(a, c)
        self.assertEqual(sum(x["weight"] for x in suite.make_scenario(ctx, 6, 5, 1.0, "one_heavy", 3, 300, 0, "v")["control_points"]), 104)

    def test_nobase_context_has_no_sources(self):
        self.assertEqual(ctx_of("astana_clinic_nobase")["sources"], [])
        self.assertEqual(len(ctx_of("astana_clinic")["sources"]), 16)


if __name__ == "__main__":
    unittest.main()
