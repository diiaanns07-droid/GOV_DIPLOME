"""K08 R9 этап 2: проверка адаптера отчёта устойчивости (resilience_report.js поверх BUILD) независимым Python-оракулом.

Usage: python check_stage2.py --app-root <prototypes/city-evidence> [--json OUT]
Оракул: r8 planlib (@7fb81b9, snapshot BUILD) с контекстом, у которого записи случая отфильтрованы; устойчивый план —
полный перебор по ключу (W, L_base, cost, ids) из CORE_SPEC r9, независимо от JS.
"""
import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_compat  # noqa: E402

P = build_compat.use_build_snapshot()
ALLOWED_TAGS = {"html", "head", "meta", "title", "style", "body", "h1", "h2", "h3", "p", "b", "div", "table", "tr", "th", "td", "ul", "li"}
ALLOWED_ATTRS = {"lang", "charset", "name", "content", "http-equiv", "class"}
INF = float("inf")


def audit(h):
    bad = []

    class A(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in ALLOWED_TAGS:
                bad.append(tag)
            bad.extend(f"{tag}@{k}" for k, _ in attrs if k not in ALLOWED_ATTRS)
    A().feed(h)
    return bad


class CaseCtx:
    """Контекст оракула с отфильтрованными записями (исходный Context не меняется)."""

    def __init__(self, ctx, off):
        self.ctx, self.off = ctx, set(off)

    def __getattr__(self, k):
        return getattr(self.ctx, k)

    def records(self, city, cat):
        return [r for r in self.ctx.records(city, cat) if r["id"] not in self.off]


def Lvec(m):
    return (m["unknown_count"], m["weighted_sum_mm"], INF if m["max_mm"] is None else m["max_mm"])


def oracle(ctx, env):
    sc = P.validate_plan_scenario(env["plan"], ctx)
    cases = [("base", [])] + [(c["id"], c["disabled_source_ids"]) for c in env["cases"]]
    cctx = {cid: CaseCtx(ctx, off) for cid, off in cases}
    probs = {cid: P.Problem(cctx[cid], sc) for cid, _ in cases}

    def per_case(ids):
        return {cid: P.evaluate_plan(cctx[cid], sc, ids, probs[cid])["metrics"] for cid, _ in cases}

    def W_of(pc):
        W = max(Lvec(m) for m in pc.values())
        return W, sorted(cid for cid, m in pc.items() if Lvec(m) == W)
    nominal = P.optimize_plans(ctx, sc)
    ids_all = sorted(c["id"] for c in sc["candidates"])
    best = None
    import itertools
    for r in range(len(ids_all) + 1):
        for comb in itertools.combinations(ids_all, r):
            ev = P.evaluate_plan(cctx["base"], sc, list(comb), probs["base"])
            if not ev["feasibility"]["feasible"]:
                continue
            pc = per_case(list(comb))
            W, _ = W_of(pc)
            key = (W, Lvec(pc["base"]), pc["base"]["cost"], list(comb))
            if best is None or key < best[0]:
                best = (key, list(comb))
    out = {"status": nominal["status"]}
    if nominal["status"] == "optimal" and best:
        nom_ids = nominal["objectives"]["mean"]["selected_ids"]
        out["nominal"] = nom_ids
        out["robust"] = best[1]
        out["plans"] = {}
        for k, ids in (("manual", sc["selected_ids"]), ("nominal", nom_ids), ("robust", best[1])):
            pc = per_case(ids)
            W, worst = W_of(pc)
            out["plans"][k] = {"per_case": pc, "W": [None if x == INF else x for x in W], "worst": worst}
        a, b = out["plans"]["robust"]["per_case"]["base"]["weighted_mean_mm"], out["plans"]["nominal"]["per_case"]["base"]["weighted_mean_mm"]
        out["price"] = None if a is None or b is None else (a - b) / 1000
    return out


def run_cli(app, env_path, outdir):
    p = subprocess.run(["node", str(HERE / "resilience_cli.cjs"), "--app-root", str(app), "--in", str(env_path), "--out-dir", str(outdir)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


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

    for name in ("shymkent_school_r9", "astana_clinic_r9"):
        envp = HERE / "fixtures" / f"{name}.json"
        env = json.loads(envp.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            code, _ = run_cli(app, envp, td)
            rep = json.loads((Path(td) / "report.json").read_text(encoding="utf-8"))
            h = (Path(td) / "report.html").read_text(encoding="utf-8")
        o = oracle(ctx, env)
        mism = []
        if rep["search"]["status"] != o["status"]:
            mism.append(f"status {rep['search']['status']} != {o['status']}")
        else:
            for k in ("nominal", "robust"):
                if rep["plans"][k]["selected_ids"] != o[k]:
                    mism.append(f"{k}: {rep['plans'][k]['selected_ids']} != {o[k]}")
            for k in ("manual", "nominal", "robust"):
                jp, op = rep["plans"][k], o["plans"][k]
                if jp["worst_vector"] != op["W"]:
                    mism.append(f"{k}.W {jp['worst_vector']} != {op['W']}")
                if jp["worst_case_ids"] != op["worst"]:
                    mism.append(f"{k}.worst {jp['worst_case_ids']} != {op['worst']}")
                for c in jp["per_case"]:
                    m = op["per_case"][c["case_id"]]
                    for f in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost"):
                        if c[f] != m[f]:
                            mism.append(f"{k}.{c['case_id']}.{f} {c[f]} != {m[f]}")
            if (rep["price_of_robustness_m"] is None) != (o["price"] is None) or (o["price"] is not None and abs(rep["price_of_robustness_m"] - o["price"]) > 1e-9):
                mism.append(f"price {rep['price_of_robustness_m']} != {o['price']}")
        chk(f"R1:{name}", code == 0 and not mism, "manual/nominal/robust, per-case метрики, W, worst_case_ids, цена = независимый Python-оракул",
            mismatches=mism[:20], nominal=rep["plans"]["nominal"]["selected_ids"] if rep["plans"]["nominal"] else None,
            robust=rep["plans"]["robust"]["selected_ids"] if rep["plans"]["robust"] else None, price_m=rep["price_of_robustness_m"])
        # provenance и версии
        excl = {i for c in env["cases"] for i in c["disabled_source_ids"]}
        recs = {r["id"]: r for r in rep["source_records"]}
        prov_ok = excl <= set(recs) and all(recs[i]["sources"] and all(s.get("license") for s in recs[i]["sources"]) for i in excl) \
            and all("flags" in r["qa"] for r in recs.values())
        snap_ok = rep["source"]["source_snapshot"] == env["plan"]["source_snapshot"] == build_compat.build_snapshot(ctx, env["plan"]["city_id"])
        ver_ok = (rep["schema_version"], rep["metric_version"], rep["objective_version"]) == ("city-resilience-v1", "haversine-mm-v1", "worst-lex-v1") \
            and all(rep[k].startswith("sha256:") for k in ("resilience_problem_digest", "resilience_scenario_digest", "exclusions_digest"))
        chk(f"R2:{name}", prov_ok and snap_ok and ver_ok, "источник/лицензия/QA каждой исключённой записи, snapshot плана не подменён, версии и digests")
        # HTML: только разметка белого списка, тексты-предупреждения, все случаи и исключения видны
        t = html.unescape(re.sub(r"<[^>]+>", "\n", h))
        need = ["Условно исключаем из расчёта; это не подтверждение закрытия", "не прогноз кризиса"] + [c["label"] for c in env["cases"]] + sorted(excl)[:3]
        chk(f"R3:{name}", not audit(h) and "default-src 'none'" in h and all(x in t for x in need), "статический HTML: белый список, CSP, подписи как текст, исключения перечислены",
            audit=audit(h), missing=[x for x in need if x not in t])
    # дубли наборов показаны и не влияют на результат
    env = json.loads((HERE / "fixtures/shymkent_school_r9.json").read_text(encoding="utf-8"))
    env2 = json.loads(json.dumps(env))
    env2["cases"] = [c for c in env2["cases"] if c["id"] != "дубль_near_two"]
    with tempfile.TemporaryDirectory() as td:
        p1, p2 = Path(td) / "a.json", Path(td) / "b.json"
        p1.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8"); p2.write_text(json.dumps(env2, ensure_ascii=False), encoding="utf-8")
        run_cli(app, p1, Path(td) / "A"); run_cli(app, p2, Path(td) / "B")
        ra = json.loads((Path(td) / "A/report.json").read_text(encoding="utf-8")); rb = json.loads((Path(td) / "B/report.json").read_text(encoding="utf-8"))
    dup = next(c for c in ra["cases"] if c["id"] == "дубль_near_two")
    chk("R4", dup["same_exclusions_as"] == ["near_two"] and all(ra["plans"][k]["selected_ids"] == rb["plans"][k]["selected_ids"] for k in ("nominal", "robust"))
        and ra["price_of_robustness_m"] == rb["price_of_robustness_m"],
        "одинаковый набор исключений помечен совпадающим; nominal/robust/цена от дубля не зависят")
    # export: только вход, без производных
    out = subprocess.run(["node", "-e", "const RR=require(process.argv[1]);const e=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));"
                          "process.stdout.write(RR.exportResilienceEnvelope(e))", str(HERE / "resilience_report.js"), str(HERE / "fixtures/astana_clinic_r9.json")],
                         capture_output=True, text=True).stdout
    ex = json.loads(out)
    chk("R5", set(ex) == {"schema_version", "plan", "cases"} and "derived_results" not in ex["plan"] and "_ctx" not in ex,
        "exportResilienceEnvelope: только schema_version/plan/cases, без производных")
    rep = {"checker": "K08 R9 check_stage2", "target_app_root": str(app), "results": res,
           "summary": {v: sum(1 for x in res if x["verdict"] == v) for v in ("PASS", "FAIL")}}
    if a.json:
        Path(a.json).write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for x in res:
        print(f"[{x['verdict']}] {x['id']} {x['text']}" + (f" — {x.get('mismatches') or x.get('missing') or x.get('audit') or ''}" if x["verdict"] == "FAIL" else ""))
    print(json.dumps(rep["summary"]))
    return 1 if rep["summary"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
