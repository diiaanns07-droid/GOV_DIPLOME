"""K08 R8: тесты движка плана и генератора отчёта.

Usage: python test_report.py --app-root <prototypes/city-evidence> [-v]
Фикстуры: fixtures/*.json (synthetic demo inputs над реальными срезами). Исходная app-root не меняется.
"""
import argparse
import copy
import itertools
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planlib as P  # noqa: E402
import report as R  # noqa: E402

APP = None
FIX = HERE / "fixtures"


def load(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = P.Context(APP)

    def sc(self, name="shymkent_school_demo"):
        return P.validate_plan_scenario(load(name), self.ctx)


# ---------------- этап 1: движок и отчёт ----------------
class TestSnapshot(Base):
    def test_matches_build_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node недоступен — сверка с JS сборки не выполнена")
        js = ('global.window={};require(process.argv[1]+"/web/data.js");const D=window.CITY_EVIDENCE;delete global.window;'
              'const F=require(process.argv[1]+"/web/facts.js"),X=require(process.argv[1]+"/web/whatif.js");'
              'console.log(JSON.stringify(["shymkent","astana"].map(c=>X.sourceSnapshot(D,c,F))))')
        out = json.loads(subprocess.check_output([node, "-e", js, str(APP)], text=True))
        self.assertEqual(out, [P.source_snapshot(self.ctx, c, "city-whatif-v1") for c in ("shymkent", "astana")])

    def test_schema_specific(self):
        self.assertNotEqual(P.source_snapshot(self.ctx, "astana"), P.source_snapshot(self.ctx, "astana", "city-whatif-v1"))


class TestEngine(Base):
    def brute(self, sc, budget=None):
        """Независимый путь: каждый набор через evaluate_plan (без предвычисления _metrics в цикле)."""
        B = sc["budget"] if budget is None else budget
        ids = [c["id"] for c in sc["candidates"]]
        best = {}
        for r in range(0, len(ids) + 1):
            for comb in itertools.combinations(sorted(ids), r):
                ev = P.evaluate_plan(self.ctx, dict(sc, budget=B), list(comb))
                if not ev["feasibility"]["feasible"]:
                    continue
                for k, f in P.KEYS.items():
                    key = f(ev["metrics"], list(comb))
                    if k not in best or key < best[k][0]:
                        best[k] = (key, list(comb))
        return {k: v[1] for k, v in best.items()}

    def test_optimum_equals_brute(self):
        for name in ("shymkent_school_demo", "astana_clinic_demo"):
            sc = self.sc(name)
            opt = P.optimize_plans(self.ctx, sc)
            self.assertEqual(opt["status"], "optimal")
            self.assertEqual({k: v["selected_ids"] for k, v in opt["objectives"].items()}, self.brute(sc), name)

    def test_infeasible_reason(self):
        opt = P.optimize_plans(self.ctx, self.sc("astana_clinic_infeasible"))
        self.assertEqual(opt["status"], "infeasible")
        self.assertTrue(any("обязательных" in r for r in opt["infeasible_reasons"]))

    def test_order_invariance(self):
        sc = self.sc()
        sh = copy.deepcopy(sc)
        sh["control_points"].reverse(); sh["candidates"].reverse()
        self.assertEqual(P.problem_digest(sc), P.problem_digest(sh))
        self.assertEqual(P.optimize_plans(self.ctx, sc)["objectives"], P.optimize_plans(self.ctx, sh)["objectives"])
        sel = dict(sc, selected_ids=["c2"])
        self.assertEqual(P.problem_digest(sc), P.problem_digest(sel))
        self.assertNotEqual(P.scenario_digest(sc), P.scenario_digest(sel))

    def test_mm_metric_and_empty_plan(self):
        sc = self.sc()
        ev = P.evaluate_plan(self.ctx, sc, [])
        for r in ev["rows"]:
            self.assertIsInstance(r["after_mm"], int); self.assertEqual(r["after_mm"], r["before_mm"]); self.assertEqual(r["delta_mm"], 0)

    def test_pareto_non_dominated(self):
        pf = P.optimize_plans(self.ctx, self.sc())["pareto"]
        for a in pf:
            for b in pf:
                if a is not b:
                    self.assertFalse(b["cost"] <= a["cost"] and b["weighted_sum_mm"] <= a["weighted_sum_mm"]
                                     and (b["cost"], b["weighted_sum_mm"]) != (a["cost"], a["weighted_sum_mm"]))

    def test_sensitivity_budgets(self):
        sc = self.sc()
        self.assertEqual([s["budget"] for s in P.sensitivity(self.ctx, sc)], sorted({0, sc["budget"] // 2, sc["budget"]}))


class TestReport(Base):
    def build(self, name):
        meta = R.build_report(P.plan_result(self.ctx, self.sc(name)), "2026-10-05T00:00:00Z")
        return meta, R.render_html(meta)

    def test_metadata_provenance(self):
        meta, _ = self.build("shymkent_school_demo")
        s = meta["source"]
        for k in ("source_snapshot", "release", "bbox", "places_file", "inputs", "data_js_sha256", "attribution"):
            self.assertTrue(s.get(k), k)
        self.assertEqual(s["source_snapshot"], meta["scenario"]["source_snapshot"])
        self.assertEqual(meta["metric_version"], "haversine-mm-v1")
        self.assertTrue(meta["source_records"])
        for r in meta["source_records"]:
            self.assertTrue(r["sources"] and all(x.get("license") for x in r["sources"]))
            self.assertIn("flags", r["qa"])
        self.assertTrue(all(c["kind"] == "hypothetical" for c in meta["scenario"]["candidates"]))

    def test_html_self_contained(self):
        for name in ("shymkent_school_demo", "astana_clinic_demo", "astana_clinic_infeasible"):
            _, h = self.build(name)
            self.assertNotRegex(h.lower(), r"<script|<iframe|<object|<embed|<link|<img|javascript:|\son\w+=")
            self.assertNotRegex(h, r"(src|href)=")
            self.assertIn("default-src 'none'", h)
            for w in ("условные единицы", "параметр анализа", "Не решение акимата", "Ограничения", "haversine-mm-v1"):
                self.assertIn(w, h)

    def test_no_forbidden_claims(self):
        _, h = self.build("astana_clinic_demo")
        body = h.split("<h2>Ограничения</h2>")[0].split("<h2>Допущения</h2>")[0].lower()
        for w in ("минут", "пешком за", "изохрон", "населени", "экономи", "тенге", "доказывает"):
            self.assertNotIn(w, body, w)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    a, rest = ap.parse_known_args()
    APP = Path(a.app_root).resolve()
    unittest.main(argv=[sys.argv[0]] + rest)
