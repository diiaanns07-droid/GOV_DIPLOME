"""K08 R9 этап 3: устойчивость адаптера отчёта (вход city-resilience-v1) и повторная проверка на BUILD.

Usage: python check_stage3.py --app-root <prototypes/city-evidence> [--json OUT]
Каждый случай — отдельный envelope во временной папке через resilience_cli.cjs (вызывает API BUILD). Ожидания —
из CORE_SPEC r9, не из ответа адаптера. Отчёт всегда пересчитывается из входа.
"""
import argparse
import copy
import html
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_stage2 import audit  # noqa: E402

FIX = HERE / "fixtures"


def cli(app, env_text, out=None, check=False):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "env.json"
        p.write_bytes(env_text.encode("utf-8") if isinstance(env_text, str) else env_text)
        cmd = ["node", str(HERE / "resilience_cli.cjs"), "--app-root", str(app), "--in", str(p)]
        cmd += ["--check"] if check else ["--out-dir", str(Path(td) / "o")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        res = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"status": "crash", "stderr": r.stderr[-300:]}
        if not check and r.returncode == 0:
            res["report"] = json.loads((Path(td) / "o/report.json").read_text(encoding="utf-8"))
            res["html"] = (Path(td) / "o/report.html").read_text(encoding="utf-8")
        res["exit"] = r.returncode
        return res


def load(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    app = Path(a.app_root).resolve()
    res = []

    def chk(cid, ok, text, **kw):
        res.append({"id": cid, "verdict": "PASS" if ok else "FAIL", "text": text, **kw})

    sh, asn = load("shymkent_school_r9"), load("astana_clinic_r9")
    D = lambda o: json.dumps(o, ensure_ascii=False)  # noqa: E731

    # T1 кириллица и HTML в подписях/ID: только текст, JSON roundtrip точный
    e = copy.deepcopy(sh)
    e["cases"][0]["label"] = "<script>alert('x')</script> «Школы» — проверка"
    e["cases"][1]["id"] = "случай_Ә_ң_ғ"
    e["cases"][1]["label"] = "</td></tr><img src=x onerror=alert(1)> Қазақша жазу"
    r = cli(app, D(e))
    t = html.unescape(re.sub(r"<[^>]+>", "\n", r.get("html", "")))
    chk("T1", r["exit"] == 0 and not audit(r["html"]) and e["cases"][0]["label"] in t and e["cases"][1]["label"] in t and "случай_Ә_ң_ғ" in t
        and [c["label"] for c in r["report"]["input"]["cases"]][:2] == [e["cases"][0]["label"], e["cases"][1]["label"]],
        "кириллица/казахские буквы в ID и подписях, HTML в подписях — только текст, точный JSON roundtrip")

    # T2 поддельные результаты: derived/report/результаты во входе не принимаются
    forged = {"derived_in_plan": lambda o: o["plan"].__setitem__("derived_results", {"manual": {"metrics": {"weighted_sum_mm": 0}}}),
              "results_top": lambda o: o.__setitem__("results", {"robust": ["c1"]}),
              "price_top": lambda o: o.__setitem__("price_of_robustness_m", -100),
              "case_result": lambda o: o["cases"][0].__setitem__("worst_case_ids", ["base"])}
    codes = {}
    for k, f in forged.items():
        o = copy.deepcopy(sh); f(o)
        codes[k] = cli(app, D(o), check=True).get("code")
    chk("T2", codes == {"derived_in_plan": "derived_not_accepted", "results_top": "unknown_field", "price_top": "unknown_field", "case_result": "unknown_field"},
        "поддельные производные/результаты во входе отклоняются типизированно", codes=codes)
    rep_as_input = cli(app, D(cli(app, D(sh))["report"]), check=True)
    chk("T3", rep_as_input["status"] == "rejected", "report.json не принимается как вход (отчёт всегда пересчитывается)", code=rep_as_input.get("code"))

    # T4 перепутанный срез/город/пространство имён
    mix = {}
    o = copy.deepcopy(sh); o["plan"]["source_snapshot"] = asn["plan"]["source_snapshot"]; mix["foreign_snapshot"] = cli(app, D(o), check=True).get("code")
    o = copy.deepcopy(asn); o["cases"][0]["disabled_source_ids"] = sh["cases"][0]["disabled_source_ids"]; mix["other_city_ids"] = cli(app, D(o), check=True).get("code")
    o = copy.deepcopy(sh); o["cases"][0]["disabled_source_ids"] = ["c1"]; mix["candidate_id"] = cli(app, D(o), check=True).get("code")
    o = copy.deepcopy(sh); o["plan"]["city_id"] = "astana"; mix["city_swapped"] = cli(app, D(o), check=True).get("code")
    o = copy.deepcopy(asn); o["plan"]["category"] = "school"
    for c in o["plan"]["candidates"]:
        c["category"] = "school"
    mix["category_swapped"] = cli(app, D(o), check=True).get("code")
    chk("T4", mix["foreign_snapshot"] == "bad_plan:foreign_snapshot" and mix["other_city_ids"] == "unknown_source" and mix["candidate_id"] == "candidate_not_source"
        and mix["city_swapped"] in ("bad_plan:foreign_snapshot", "bad_plan:outside_bbox") and mix["category_swapped"] == "unknown_source",
        "чужой срез, ID другого города, кандидат вместо исходной записи, подмена города/категории — отклоняются", codes=mix)

    # T5 порядок случаев и ID внутри исключений не меняет результат и digests
    base = cli(app, D(sh))["report"]
    diffs = []
    rnd = random.Random(8)
    for k in range(3):
        o = copy.deepcopy(sh)
        rnd.shuffle(o["cases"])
        for c in o["cases"]:
            rnd.shuffle(c["disabled_source_ids"])
        rnd.shuffle(o["plan"]["candidates"]); rnd.shuffle(o["plan"]["control_points"])
        r2 = cli(app, D(o))["report"]
        for f in ("resilience_problem_digest", "resilience_scenario_digest", "exclusions_digest", "price_of_robustness_m"):
            if r2[f] != base[f]:
                diffs.append(f"{k}:{f}")
        for p in ("manual", "nominal", "robust"):
            for f in ("selected_ids", "worst_vector", "worst_case_ids"):
                if r2["plans"][p][f] != base["plans"][p][f]:
                    diffs.append(f"{k}:{p}.{f}")
            if sorted(r2["plans"][p]["per_case"], key=lambda x: x["case_id"]) != sorted(base["plans"][p]["per_case"], key=lambda x: x["case_id"]):
                diffs.append(f"{k}:{p}.per_case")
    chk("T5", not diffs, "перестановка случаев, ID исключений, кандидатов и точек: результат и digests те же", diffs=diffs[:10])
    o = copy.deepcopy(sh); o["plan"]["selected_ids"] = ["c2"]
    r3 = cli(app, D(o))["report"]
    chk("T6", r3["resilience_problem_digest"] == base["resilience_problem_digest"] and r3["resilience_scenario_digest"] != base["resilience_scenario_digest"],
        "selected_ids входит только в resilience_scenario_digest")

    # T7 строгий импорт и границы CORE_SPEC r9
    good = D(sh)
    cases_bad = {
        "nan": good.replace('"budget": 300', '"budget": NaN'),
        "dup_key": good.replace('"budget": 300', '"budget": 300, "budget": 1'),
        "1e999": good.replace('"budget": 300', '"budget": 1e999'),
        "big": good[:-1] + ', "x": "' + "я" * 140000 + '"}',
    }
    st = {k: cli(app, v, check=True).get("code") for k, v in cases_bad.items()}
    def mut(f):
        o = copy.deepcopy(sh); f(o); return cli(app, D(o), check=True).get("code")
    bb = sh["plan"]["candidates"][0]
    st["13_candidates"] = mut(lambda o: o["plan"].__setitem__("candidates", [dict(bb, id=f"k{i}") for i in range(13)]) or o["plan"].update(required_ids=[], excluded_ids=[], selected_ids=[]))
    st["8_user_cases"] = mut(lambda o: o.__setitem__("cases", [dict(o["cases"][0], id=f"c{i}") for i in range(8)]))
    st["base_reserved"] = mut(lambda o: o["cases"][0].__setitem__("id", "base"))
    st["label_121"] = mut(lambda o: o["cases"][0].__setitem__("label", "ж" * 121))
    st["label_120_ok"] = mut(lambda o: o["cases"][0].__setitem__("label", "ж" * 120))
    st["label_ctrl"] = mut(lambda o: o["cases"][0].__setitem__("label", "a\u0007b"))
    st["empty_exclusions"] = mut(lambda o: o["cases"][0].__setitem__("disabled_source_ids", []))
    st["dup_exclusion"] = mut(lambda o: o["cases"][0].__setitem__("disabled_source_ids", o["cases"][0]["disabled_source_ids"][:1] * 2))
    st["case_dup_id"] = mut(lambda o: o["cases"][1].__setitem__("id", o["cases"][0]["id"]))
    st["bad_version"] = mut(lambda o: o.__setitem__("schema_version", "city-resilience-v2"))
    want = {"nan": "bad_json", "dup_key": "bad_json", "1e999": "bad_json", "big": "too_large", "13_candidates": "too_many_candidates",
            "8_user_cases": "bad_cases", "base_reserved": "reserved_id", "label_121": "bad_label", "label_120_ok": None, "label_ctrl": "bad_label",
            "empty_exclusions": "bad_exclusions", "dup_exclusion": "duplicate_id", "case_dup_id": "duplicate_id", "bad_version": "bad_version"}
    chk("T7", st == want, "строгий JSON (NaN/дубликат/1e999/>256 KiB) и границы r9 — типизированные отказы; 120 символов принимаются", codes=st,
        diff={k: (st.get(k), v) for k, v in want.items() if st.get(k) != v})

    # T8 устаревший срез: изменённые координаты записи в копии data.js → snapshot плана чужой, отказ до вычислений
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "app"
        shutil.copytree(app, root, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        p = root / "web/data.js"
        txt = p.read_text(encoding="utf-8")
        m = re.search(r"(window\.CITY_EVIDENCE\s*=\s*)(\{.*\})(\s*;?\s*)$", txt, re.S)
        d = json.loads(m.group(2))
        rec = next(x for x in d["cities"]["shymkent"]["places"] if x["group"] == "school")
        rec["lon"] = round(rec["lon"] + 0.0001, 6)
        p.write_text(txt[:m.start(2)] + json.dumps(d, ensure_ascii=False) + m.group(3), encoding="utf-8")
        stale = cli(root, good, check=True)
    chk("T8", stale.get("code") == "bad_plan:foreign_snapshot", "срез изменился после создания envelope → bad_plan:foreign_snapshot", code=stale.get("code"))

    # T9 исходный контекст не мутируется: base-метрики ручного плана = evaluatePlan v2 без исключений
    r = cli(app, good)["report"]
    v2 = subprocess.run(["node", "-e", """
const fs=require('fs'),path=require('path'),vm=require('vm');const W=path.join(process.argv[1],'web');const c={};vm.createContext(c);c.window=c;
vm.runInContext(fs.readFileSync(path.join(W,'data.js'),'utf8'),c);const F=require(path.join(W,'facts.js')),PL=require(path.join(W,'plan.js'));
const env=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const ctx=PL.makeContext(c.CITY_EVIDENCE,env.plan.city_id,F);
const sc=PL.validatePlanScenario(env.plan,ctx);const n0=ctx.places.length;
const RR=require(process.argv[3]);RR.buildResilienceReport(RR.validateResilience(JSON.stringify(env),{PL,F,X:require(path.join(W,'whatif.js')),data:c.CITY_EVIDENCE,obs:null}),{PL,F,data:c.CITY_EVIDENCE,obs:null});
const e=PL.evaluatePlan(ctx,sc,sc.selected_ids);console.log(JSON.stringify({n0,n1:ctx.places.length,m:e.metrics}));""",
                         str(app), str(FIX / "shymkent_school_r9.json"), str(HERE / "resilience_report.js")], capture_output=True, text=True)
    v = json.loads(v2.stdout)
    mb = next(c for c in r["plans"]["manual"]["per_case"] if c["case_id"] == "base")
    chk("T9", v["n0"] == v["n1"] and all(mb[k] == v["m"][k] for k in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost")),
        "контекст BUILD не мутируется; base = evaluatePlan v2 без исключений")

    rep = {"checker": "K08 R9 check_stage3", "target_app_root": str(app), "results": res,
           "summary": {v: sum(1 for x in res if x["verdict"] == v) for v in ("PASS", "FAIL")}}
    if a.json:
        Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for x in res:
        print(f"[{x['verdict']}] {x['id']} {x['text']}" + (f" — {x.get('diff') or x.get('codes') or x.get('diffs') or x.get('code') or ''}" if x["verdict"] == "FAIL" else ""))
    print(json.dumps(rep["summary"]))
    return 1 if rep["summary"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
