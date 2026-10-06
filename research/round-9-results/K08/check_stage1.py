"""K08 R9 этап 1: проверка reportHtml / exportPlanScenario НАСТОЯЩЕГО BUILD против независимых ожиданий r8.

Usage: python check_stage1.py --app-root <prototypes/city-evidence> [--json OUT]
Запускает build_adapter.cjs (вызывает web/plan.js сборки) и сравнивает с r8 Python-оракулом (planlib @ 7fb81b9,
snapshot по формуле BUILD — build_compat.py). Вердикт каждой проверки PASS/FAIL; FAIL — с минимальным воспроизведением.
Фикстуры: r8 fixtures/*.json (synthetic demo inputs над реальными срезами) + max-size (кириллица) + без исходных записей (synthetic).
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_compat  # noqa: E402

P = build_compat.use_build_snapshot()
R8FIX = build_compat.R8 / "fixtures"
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "h1", "h2", "h3", "p", "div", "table", "tr", "th", "td", "pre"}  # div: обёртка таблиц в proposal (только class)
ALLOWED_ATTRS = {"lang", "charset", "name", "content", "http-equiv", "class"}
INJ = {"names": "<script>alert(1)</script>", "city_label": "<img src=x onerror=alert(1)>", "attribution": "</p><a href=//evil.example>x</a>",
       "explanation": "<iframe src=//evil.example></iframe>", "release": "\"><svg onload=alert(1)>"}


def markup_audit(h):
    bad = []

    class A(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in ALLOWED_TAGS:
                bad.append(("tag", tag))
            bad.extend(("attr", tag, k) for k, _ in attrs if k not in ALLOWED_ATTRS)
    A().feed(h)
    return bad


def page_text(h):
    return html.unescape(re.sub(r"<[^>]+>", "\n", h))


def jobs(ctx):
    js = []
    for name in ("shymkent_school_demo", "astana_clinic_demo", "astana_clinic_infeasible"):
        sc = json.loads((R8FIX / f"{name}.json").read_text(encoding="utf-8"))
        sc["source_snapshot"] = "@build"
        js.append({"name": name, "scenario": sc, "forge": True})
    # max-size: 25 точек, 16 кандидатов, ID по 64 кириллических символа (Unicode NFC, допустимо в BUILD)
    bb = ctx.city("astana")["bbox"]
    pid = lambda k: ("точка_" + "ж" * 64)[:60] + f"{k:04d}"  # noqa: E731
    cid = lambda k: ("кандидат_" + "щ" * 64)[:60] + f"{k:04d}"  # noqa: E731
    pts = [{"id": pid(k), "lon": round(bb[0] + (bb[2] - bb[0]) * (0.05 + 0.9 * (k % 5) / 4), 6),
            "lat": round(bb[1] + (bb[3] - bb[1]) * (0.05 + 0.9 * (k // 5) / 4), 6), "weight": 100} for k in range(25)]
    cands = [{"id": cid(k), "lon": round(bb[0] + (bb[2] - bb[0]) * (0.1 + 0.8 * (k % 4) / 3), 6),
              "lat": round(bb[1] + (bb[3] - bb[1]) * (0.1 + 0.8 * (k // 4) / 3), 6), "category": "school", "kind": "hypothetical",
              "cost": 1000000} for k in range(16)]
    js.append({"name": "astana_school_maxsize", "scenario": {"schema_version": "city-plan-v2", "city_id": "astana", "source_snapshot": "@build",
               "category": "school", "control_points": pts, "candidates": cands, "budget": 1000000, "max_selected": 5,
               "coverage_radius_m": 5000, "required_ids": [], "excluded_ids": [], "selected_ids": [cands[0]["id"]]}})
    # synthetic: в копии среза удалены все записи категории → before = null
    sc = json.loads((R8FIX / "shymkent_school_demo.json").read_text(encoding="utf-8"))
    sc.update(source_snapshot="@build", selected_ids=[], excluded_ids=[])
    js.append({"name": "synthetic_no_sources", "scenario": sc, "drop_category_sources": True})
    sc2 = dict(sc, selected_ids=["c1"])
    js.append({"name": "synthetic_no_sources_with_c1", "scenario": sc2, "drop_category_sources": True})
    # injection в полях, которые отчёт получает от сайта (имена записей, подписи, атрибуция, объяснение)
    sc3 = json.loads((R8FIX / "shymkent_school_demo.json").read_text(encoding="utf-8"))
    sc3["source_snapshot"] = "@build"
    names = {r["id"]: INJ["names"] for r in ctx.city("shymkent")["places"]}
    js.append({"name": "injection_labels", "scenario": sc3, "names": names, "city_label": INJ["city_label"],
               "attribution": INJ["attribution"], "explanation": INJ["explanation"], "release": INJ["release"]})
    return js


def run_adapter(app, job_list, work):
    jp, op = Path(work) / "jobs.json", Path(work) / "out.json"
    jp.write_text(json.dumps(job_list, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["node", str(HERE / "build_adapter.cjs"), "--app-root", str(app), "--jobs", str(jp), "--out", str(op)], check=True,
                   capture_output=True, text=True)
    return json.loads(op.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    app = Path(a.app_root).resolve()
    ctx = P.Context(app)
    res = []

    def chk(cid, ok, text, **kw):
        res.append({"id": cid, "verdict": "PASS" if ok else "FAIL", "text": text, **kw})

    if not shutil.which("node"):
        print("node недоступен: проверки BUILD NOT_RUN"); return 2
    with tempfile.TemporaryDirectory() as td:
        out = run_adapter(app, jobs(ctx), td)
    J = {j["name"]: j for j in out["jobs"]}
    errs = {k: v["error"] for k, v in J.items() if "error" in v}
    chk("S0", not errs, "адаптер вызвал API BUILD без исключений", errors=errs)

    # S1 snapshot
    snaps = {c: next(j["snapshot"] for j in out["jobs"] if j.get("snapshot") and json.loads(j["export_text"])["city_id"] == c)
             for c in ("shymkent", "astana")}
    chk("S1", all(snaps[c] == build_compat.build_snapshot(ctx, c) for c in snaps), "source_snapshot BUILD = независимый пересчёт r8 (формула BUILD)", snapshots=snaps)

    # S2 export/import roundtrip + подделка + чужой срез
    rt = {k: (v["import"]["ok"] and v["import"]["same"]) for k, v in J.items() if "import" in v}
    chk("S2", all(rt.values()), "exportPlanScenario → importPlanScenario: сценарий тот же", roundtrip=rt)
    forged = {k: v["forge"] for k, v in J.items() if "forge" in v}
    chk("S3", all(not f["accepted"] and f["code"] == "forged_derived" for f in forged.values()), "изменённые derived_results отклоняются (forged_derived)", forged=forged)
    foreign = {k: v["foreign"] for k, v in J.items() if "foreign" in v}
    chk("S4", all(not f["accepted"] and f["code"] == "foreign_snapshot" for f in foreign.values()), "чужой source_snapshot отклоняется", foreign=foreign)

    # S5/S6 значения = независимый r8-оракул (только реальные срезы; synthetic jobs — свои проверки ниже)
    mism = []
    for name in ("shymkent_school_demo", "astana_clinic_demo", "astana_clinic_infeasible", "astana_school_maxsize"):
        j = J[name]
        sc_raw = json.loads(j["export_text"]); sc_raw.pop("derived_results", None)
        sc = P.validate_plan_scenario(sc_raw, ctx)
        ev = P.evaluate_plan(ctx, sc, sc["selected_ids"])
        bm = j["manual"]["metrics"]
        for k in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"):
            if bm[k] != ev["metrics"][k]:
                mism.append(f"{name}.manual.{k}: build {bm[k]} r8 {ev['metrics'][k]}")
        rows_b = {r["id"]: r for r in j["manual"]["rows"]}
        for r in ev["rows"]:
            b = rows_b[r["id"]]
            for k in ("before_mm", "after_mm", "delta_mm", "nearest_before", "nearest_after"):
                if b[k] != r[k]:
                    mism.append(f"{name}.row {r['id'][:20]}.{k}: build {b[k]} r8 {r[k]}")
        opt = P.optimize_plans(ctx, sc)
        if j["result"]["status"] != opt["status"]:
            mism.append(f"{name}.status: build {j['result']['status']} r8 {opt['status']}")
        elif opt["status"] == "optimal":
            for o in ("mean", "minimax", "coverage"):
                bo, ro = j["result"]["objectives"][o], opt["objectives"][o]
                if bo["ids"] != ro["selected_ids"] or bo["weighted_sum_mm"] != ro["metrics"]["weighted_sum_mm"] or bo["cost"] != ro["metrics"]["cost"] \
                        or bo["max_mm"] != ro["metrics"]["max_mm"] or bo["covered_weight"] != ro["metrics"]["covered_weight"]:
                    mism.append(f"{name}.{o}: build {bo['ids']} r8 {ro['selected_ids']}")
            bp = [(p["cost"], p["weighted_sum_mm"], p["ids"]) for p in j["result"]["pareto"]]
            rp = [(p["cost"], p["weighted_sum_mm"], p["selected_ids"]) for p in opt["pareto"]]
            if bp != rp:
                mism.append(f"{name}.pareto: build {bp[:3]} r8 {rp[:3]}")
            if j["result"]["feasible_count"] != opt["feasible_count"]:  # evaluated у BUILD = подмножества свободных кандидатов, сравнивается только feasible_count
                mism.append(f"{name}.feasible_count: build {j['result']['feasible_count']} r8 {opt['feasible_count']}")
    chk("S5", not mism, "ручной план, строки, три цели и Парето BUILD = независимый r8-оракул (4 фикстуры)", mismatches=mism[:20])

    # S6 null: без исходных записей before=null, delta=null; не 0
    ns, ns1 = J["synthetic_no_sources"], J["synthetic_no_sources_with_c1"]
    ok = all(r["before_mm"] is None and r["after_mm"] is None and r["delta_mm"] is None for r in ns["manual"]["rows"]) \
        and ns["manual"]["metrics"]["max_mm"] is None and ns["manual"]["metrics"]["weighted_mean_mm"] is None \
        and all(r["before_mm"] is None and r["after_mm"] is not None and r["delta_mm"] is None for r in ns1["manual"]["rows"])
    exp = json.loads(ns["export_text"])["derived_results"]["manual"]
    ok = ok and all(r["after_mm"] is None for r in exp["rows"]) and exp["metrics"]["max_mm"] is None
    txt = page_text(ns1["report_html"])
    chk("S6", ok and "не вычисляется" in txt and "нет данных" in txt,
        "synthetic без исходных записей: before/delta = null (не 0) в API, экспорте и отчёте («не вычисляется», «нет данных»)")

    # S7 размер: максимальный сценарий с кириллическими ID экспортируется ≤256 KiB и импортируется
    mx = J["astana_school_maxsize"]
    chk("S7", mx["export_bytes"] <= 262144 and mx["import"]["ok"], f"max-size экспорт {mx['export_bytes']} байт ≤ 262144 и импортируется",
        export_bytes=mx["export_bytes"], report_bytes=len(mx["report_html"].encode()))

    # S8 разметка отчёта: белый список, CSP, нет внешних загрузок
    audits = {k: markup_audit(v["report_html"]) for k, v in J.items() if "report_html" in v}
    csp = all("default-src 'none'" in v["report_html"] for v in J.values() if "report_html" in v)
    chk("S8", csp and not any(audits.values()), "reportHtml: только белый список тегов/атрибутов, CSP default-src 'none', без script/src/href",
        audits={k: v for k, v in audits.items() if v})

    # S9 injection в подписях, именах, атрибуции, объяснении — только текст
    inj = J["injection_labels"]
    t = page_text(inj["report_html"])
    chk("S9", not markup_audit(inj["report_html"]) and all(v in t for v in INJ.values()),
        "строки с HTML в имени записи/городе/выпуске/атрибуции/объяснении выводятся текстом")

    # S10 provenance-полнота против ожиданий r8 (report.py r8): источник/лицензия/QA ближайших записей, bbox, пакет/файл
    h = J["shymkent_school_demo"]["report_html"]
    t = page_text(h)
    snap_ok = J["shymkent_school_demo"]["snapshot"] in t
    rec_ids = {r["nearest_before"]["id"] for r in J["shymkent_school_demo"]["manual"]["rows"] if r["nearest_before"]}
    lic_per_record = any(rid in t for rid in rec_ids)
    has_bbox = any(str(x) in t for x in ctx.city("shymkent")["bbox"])
    has_qa = "сомнение в категории" in t or "ad_or_business_page" in t
    has_file = (ctx.city("shymkent").get("files") or {}).get("places_social", {}).get("sha256", "-")[:16] in t
    missing = [n for n, v in (("id ближайших исходных записей", lic_per_record), ("bbox среза", has_bbox),
                              ("QA-флаги ближайших записей", has_qa), ("sha256 файла мест", has_file)) if not v]
    chk("S10", snap_ok and not missing, "отчёт несёт source_snapshot и provenance ближайших записей (r8-ожидание)",
        missing=missing, repro="reportHtml(m) для shymkent_school_demo: в тексте нет перечисленных полей; names показывает только имя записи")

    rep = {"checker": "K08 R9 check_stage1", "target_app_root": str(app), "plan_schema": out["plan_schema"], "metric": out["metric"],
           "results": res, "summary": {v: sum(1 for x in res if x["verdict"] == v) for v in ("PASS", "FAIL")}}
    if a.json:
        Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for x in res:
        print(f"[{x['verdict']}] {x['id']} {x['text']}" + (f" — {x.get('missing') or x.get('mismatches') or ''}" if x["verdict"] == "FAIL" else ""))
    print(json.dumps(rep["summary"]))
    return 1 if rep["summary"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
