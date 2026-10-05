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
import verify_report as V  # noqa: E402

APP = None
FIX = HERE / "fixtures"
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "h1", "h2", "p", "b", "span", "table", "thead", "tbody",
                "tr", "th", "td", "ul", "li", "div"}
ALLOWED_ATTRS = {"lang", "charset", "http-equiv", "content", "name", "class"}


def markup_audit(h):
    """Разобрать HTML: теги и атрибуты вне белого списка (то, что браузер действительно исполнит/загрузит)."""
    from html.parser import HTMLParser
    bad = []

    class A(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in ALLOWED_TAGS:
                bad.append(("tag", tag))
            for k, v in attrs:
                if k not in ALLOWED_ATTRS:
                    bad.append(("attr", tag, k))
    A(convert_charrefs=True).feed(h)
    return bad


def text_sentences(h):
    """Текст страницы без тегов, разбитый на предложения/пункты."""
    import html as H
    t = H.unescape(re.sub(r"<[^>]+>", "\n", h))
    return [x.strip() for x in re.split(r"[\n.;]", t) if x.strip()]


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
            self.assertEqual(markup_audit(h), [])
            self.assertIn("default-src 'none'", h)
            for w in ("условные единицы", "параметр анализа", "Не решение акимата", "Ограничения", "haversine-mm-v1"):
                self.assertIn(w, h)

    def test_no_forbidden_claims(self):
        for name in ("shymkent_school_demo", "astana_clinic_demo", "astana_clinic_infeasible"):
            _, h = self.build(name)
            # утверждения = предложения без отрицания/оговорки; оговорки («не учитываются», «нельзя», «не тенге») допустимы
            claims = [x.lower() for x in text_sentences(h) if not re.search(r"\bне\b|нельзя|без ", x.lower())]
            for w in ("минут", "пешком за", "изохрон", "населени", "экономи", "тенге", "доказывает", "обеспеченност"):
                self.assertFalse([c for c in claims if w in c], (name, w))


# ---------------- этап 2: сравнение стратегий ----------------
class TestComparison(Base):
    def build(self, sc):
        meta = R.build_report(P.plan_result(self.ctx, sc), "2026-10-05T00:00:00Z")
        return meta, R.render_html(meta)

    def test_identical_plans_collapsed(self):
        meta, h = self.build(self.sc("astana_clinic_demo"))
        self.assertEqual(len(meta["comparison"]["groups"]), 1)
        self.assertEqual(h.count("<h2>По точкам:"), 1)
        self.assertIn("один и тот же набор, а не три решения", h)

    def test_distinct_plans_each_have_point_table(self):
        meta, h = self.build(self.sc("shymkent_school_demo"))
        g = meta["comparison"]["groups"]
        self.assertEqual(sorted(k for x in g for k in x["strategies"]), ["coverage", "manual", "mean", "minimax"])
        self.assertEqual(h.count("<h2>По точкам:"), len(g))
        npts = len(meta["scenario"]["control_points"])
        for sec in h.split("<h2>По точкам:")[1:]:
            self.assertEqual(sec.split("</table>")[0].count("<tr>") - 1, npts)

    def test_metrics_consistent_with_rows(self):
        meta, _ = self.build(self.sc("shymkent_school_demo"))
        for k, p in meta["plans"].items():
            ws = sum(r["weight"] * r["after_mm"] for r in p["rows"] if r["after_mm"] is not None)
            self.assertEqual(ws, p["metrics"]["weighted_sum_mm"], k)
            self.assertEqual(max(r["after_mm"] for r in p["rows"]), p["metrics"]["max_mm"], k)
            cost = sum(c["cost"] for c in meta["scenario"]["candidates"] if c["id"] in p["selected_ids"])
            self.assertEqual(cost, p["metrics"]["cost"], k)

    def test_budget_conditional_and_sources(self):
        _, h = self.build(self.sc("shymkent_school_demo"))
        self.assertIn("условные единицы, не тенге и не смета", h)
        self.assertIn("Исходные записи, использованные как ближайшие", h)
        self.assertRegex(h, r"CDLA-Permissive-2\.0")
        self.assertIn("Атрибуция поставщиков данных среза", h)
        self.assertIn("не LLM", h)

    def test_infeasible_reported(self):
        meta, h = self.build(self.sc("astana_clinic_infeasible"))
        self.assertEqual(meta["optimization"]["status"], "infeasible")
        self.assertIn("Нет допустимых наборов", h)
        self.assertIn("Ограничения не снимались", h)

    def test_user_strings_are_text_not_markup(self):
        raw = load("shymkent_school_demo")
        evil = {"c1": "<script>alert(1)</script>", "c2": "https://evil.example/x", "c3": "\"><img src=x onerror=1>"}
        for c in raw["candidates"]:
            c["id"] = evil.get(c["id"], c["id"])
        raw["control_points"][0]["id"] = "javascript:alert(1)"
        raw["selected_ids"] = [evil["c1"]]
        raw["excluded_ids"] = []
        meta, h = self.build(P.validate_plan_scenario(raw, self.ctx))
        self.assertEqual(markup_audit(h), [])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", h)
        self.assertIn("https://evil.example/x", h)  # как текст, без ссылки


# ---------------- этап 3: roundtrip, устаревший срез, подмена, injection ----------------
INJECTIONS = ["</td></tr></table><script>alert(1)</script>", "\"><svg onload=alert(1)>", "javascript:alert(1)",
              "data:text/html,<b>x</b>", "{{7*7}}${7*7}", "\u202eevil\u202c", "' OR 1=1 --", "<!--x-->",
              "&lt;already&gt;", "https://evil.example/p?a=1&b=2"]


def _copy_app(td, name):
    root = Path(td) / name
    shutil.copytree(APP, root, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    return root


def _edit_data_js(root, fn):
    p = root / "web/data.js"
    txt = p.read_text(encoding="utf-8")
    m = re.search(r"(window\.CITY_EVIDENCE\s*=\s*)(\{.*\})(\s*;?\s*)$", txt, re.S)
    d = json.loads(m.group(2)); fn(d)
    p.write_text(txt[:m.start(2)] + json.dumps(d, ensure_ascii=False) + m.group(3), encoding="utf-8")


class TestRoundtrip(Base):
    def saved(self, name):
        return json.loads((HERE / "reports" / name / "report.json").read_text(encoding="utf-8"))

    def test_saved_reports_verify_ok(self):
        for name in ("shymkent_school_demo", "astana_clinic_demo", "astana_clinic_infeasible"):
            r = V.verify_report(self.saved(name), self.ctx)
            self.assertEqual(r["status"], "ok", (name, r["problems"]))

    def test_strict_json_roundtrip_of_report(self):
        raw = (HERE / "reports/shymkent_school_demo/report.json").read_bytes()
        meta = P.loads_strict(raw)
        self.assertEqual(V.verify_report(meta, self.ctx)["status"], "ok")

    def test_tampering_detected(self):
        base = self.saved("shymkent_school_demo")
        edits = {
            "metric": lambda m: m["plans"]["mean"]["metrics"].__setitem__("weighted_sum_mm", 1),
            "objective": lambda m: m["optimization"]["objectives"]["mean"].__setitem__("selected_ids", ["c4"]),
            "license": lambda m: m["source_records"][0]["sources"][0].__setitem__("license", "CC0-1.0"),
            "release": lambda m: m["source"].__setitem__("release", "2099-01-01.0"),
            "cost_without_recompute": lambda m: m["scenario"]["candidates"][1].__setitem__("cost", 1),
            "explanation": lambda m: m["comparison"]["explanation"].__setitem__(0, "Строительство улучшит здоровье."),
        }
        for k, f in edits.items():
            m = copy.deepcopy(base); f(m)
            r = V.verify_report(m, self.ctx)
            self.assertEqual(r["status"], "tampered", (k, r["problems"][:2]))
            self.assertTrue(r["problems"], k)

    def test_derived_results_untrusted(self):
        raw = load("shymkent_school_demo")
        clean = P.plan_result(self.ctx, P.validate_plan_scenario(raw, self.ctx))
        raw["derived_results"] = {"plans": {"mean": {"selected_ids": ["c6"], "metrics": {"weighted_sum_mm": 0}}}}
        res = P.plan_result(self.ctx, P.validate_plan_scenario(raw, self.ctx))
        self.assertEqual(res["plans"], clean["plans"]); self.assertEqual(res["optimization"], clean["optimization"])

    def test_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = _copy_app(td, "moved")
            def move(d):
                p = next(x for x in d["cities"]["shymkent"]["places"] if x["group"] == "school")
                p["lon"] = round(p["lon"] + 0.0001, 6)
            _edit_data_js(root, move)
            ctx2 = P.Context(root)
            r = V.verify_report(self.saved("shymkent_school_demo"), ctx2)
            self.assertEqual(r["status"], "stale"); self.assertIn("data.js изменён", r["problems"][0])
            self.assertNotEqual(r["report_snapshot"], r["current_snapshot"])
            with self.assertRaises(P.PlanError) as cm:
                P.validate_plan_scenario(load("shymkent_school_demo"), ctx2)
            self.assertEqual(cm.exception.code, "foreign_snapshot")
            # другой город: срез не изменился → ok с предупреждением о файле сборки, не «подмена»
            r2 = V.verify_report(self.saved("astana_clinic_demo"), ctx2)
            self.assertEqual(r2["status"], "ok", r2["problems"]); self.assertTrue(r2["warnings"])

    def test_provenance_to_raw_geojson(self):
        """Лицензия меняется в data.js (snapshot сборки это не ловит: в нём только id/координаты) и отчёт строится заново."""
        meta0 = self.saved("astana_clinic_demo")
        rid = meta0["source_records"][0]["id"]
        with tempfile.TemporaryDirectory() as td:
            root = _copy_app(td, "relicensed")
            def relic(d):
                for p in d["cities"]["astana"]["places"]:
                    if p["id"] == rid:
                        p["sources"][0]["license"] = "CC0-1.0"
            _edit_data_js(root, relic)
            ctx2 = P.Context(root)
            self.assertEqual(P.source_snapshot(ctx2, "astana"), P.source_snapshot(self.ctx, "astana"))  # snapshot не изменился
            meta = R.build_report(P.plan_result(ctx2, P.validate_plan_scenario(load("astana_clinic_demo"), ctx2)), "2026-10-05T00:00:00Z")
            r = V.verify_report(meta, ctx2)
            self.assertEqual(r["status"], "tampered")
            self.assertTrue(any("исходным GeoJSON" in x for x in r["problems"]))
            self.assertEqual(V.verify_report(meta0, ctx2)["status"], "tampered")  # старый отчёт против изменённого data.js

    def test_qa_change_is_stale(self):
        meta0 = self.saved("shymkent_school_demo")
        with tempfile.TemporaryDirectory() as td:
            root = _copy_app(td, "qa")
            p = root / "web/evidence.js"
            txt = p.read_text(encoding="utf-8")
            m = re.search(r"(window\.CITY_OBS\s*=\s*)(\{.*\})(\s*;?\s*)$", txt, re.S)
            d = json.loads(m.group(2))
            rid = meta0["source_records"][0]["id"]
            d["cities"]["shymkent"]["qa"]["category_doubt"][rid] = {"rule": "test_rule", "reason": "test"}
            p.write_text(txt[:m.start(2)] + json.dumps(d, ensure_ascii=False) + m.group(3), encoding="utf-8")
            r = V.verify_report(meta0, P.Context(root))
            self.assertEqual(r["status"], "stale"); self.assertIn("QA", r["problems"][0])

    def test_injection_strings_roundtrip_and_escape(self):
        raw = load("shymkent_school_demo")
        ids = [x[:64] for x in INJECTIONS[:6]]
        for c, new in zip(raw["candidates"], ids):
            c["id"] = new
        raw["excluded_ids"] = []; raw["selected_ids"] = [ids[0]]
        for pnt, new in zip(raw["control_points"], INJECTIONS[6:]):
            pnt["id"] = new[:64]
        sc = P.validate_plan_scenario(raw, self.ctx)
        meta = R.build_report(P.plan_result(self.ctx, sc), "2026-10-05T00:00:00Z")
        h = R.render_html(meta)
        self.assertEqual(markup_audit(h), [])
        text = "\n".join(text_sentences(h))
        self.assertIn("alert(1)", text)
        js = json.dumps(meta, ensure_ascii=False, allow_nan=False)
        back = P.loads_strict(js)
        self.assertEqual(sorted(c["id"] for c in back["scenario"]["candidates"]), sorted(c["id"] for c in sc["candidates"]))
        self.assertEqual(V.verify_report(back, self.ctx)["status"], "ok")

    def test_strict_import_rejections_keep_contract(self):
        good = (FIX / "shymkent_school_demo.json").read_text(encoding="utf-8")
        cases = {
            "nan": good.replace('"budget": 300', '"budget": NaN'),
            "inf": good.replace('"budget": 300', '"budget": Infinity'),
            "1e999": good.replace('"budget": 300', '"budget": 1e999'),
            "dup": good.replace('"budget": 300', '"budget": 300, "budget": 1'),
            "big": good[:-2] + ', "derived_results": "' + "x" * (260 * 1024) + '"}',
        }
        for k, t in cases.items():
            with self.assertRaises(P.PlanError, msg=k):
                P.validate_plan_scenario(P.loads_strict(t), self.ctx)
        for k, f in {"unexpected": lambda o: o.__setitem__("evil", 1), "version": lambda o: o.__setitem__("schema_version", "city-plan-v3"),
                     "float_cost": lambda o: o["candidates"][0].__setitem__("cost", 1.5),
                     "bool_weight": lambda o: o["control_points"][0].__setitem__("weight", True),
                     "extra_cand_field": lambda o: o["candidates"][0].__setitem__("url", "https://x")}.items():
            o = json.loads(good); f(o)
            with self.assertRaises(P.PlanError, msg=k):
                P.validate_plan_scenario(o, self.ctx)

    def test_unknown_report_version_rejected(self):
        m = self.saved("astana_clinic_demo"); m["report_schema"] = "k08-plan-report/v2"
        self.assertEqual(V.verify_report(m, self.ctx)["status"], "rejected")
        m = self.saved("astana_clinic_demo"); m["metric_version"] = "haversine-cm-v0"
        self.assertEqual(V.verify_report(m, self.ctx)["status"], "rejected")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    a, rest = ap.parse_known_args()
    APP = Path(a.app_root).resolve()
    unittest.main(argv=[sys.argv[0]] + rest)
