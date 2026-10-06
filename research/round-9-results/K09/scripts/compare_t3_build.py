#!/usr/bin/env python3
"""Этап 3 r9: сверка BUILD resilience.js (выход adapter/build_resilience_adapter.cjs) с оракулом K09 на задачах T3.

Сравнивается математика (CORE_SPEC: не digest): статус, nominal и robust ids, стоимость, W и worst_case_ids, вектор base,
потери L в каждом случае, цена устойчивости, feasible_count, same_plan.

  python3 scripts/compare_t3_build.py <envelopes.jsonl> <build.jsonl> <out.json> [--oracle <blind_js_out.jsonl>]
С --oracle дополнительно сверяет третью (слепую) реализацию с оракулом K09.
"""
import json, math, sys
from collections import Counter, defaultdict
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09res import resilience as RS  # noqa: E402
from k09plan import data, suite  # noqa: E402

REPO = K.parents[2]
SHA = "d865dd4a124291e10dd0b7bb1d9eada20d34c268"
SL = {"shymkent_school": ("shymkent", "school"), "astana_clinic": ("astana", "outpatient_clinic")}


def vec(v):
    return None if v is None else [v["unknown_count"], v["weighted_sum_mm"], v["max_mm"]]


def ours_for(ctx, env):
    r = RS.optimize_resilience(ctx, env)
    if r["status"] != "optimal":
        return {"status": r["status"]}
    o = {"status": "optimal", "feasible_count": r["feasible_count"], "same_plan": r["same_plan"], "price": r["price_of_robustness_m"]}
    for k in ("nominal", "robust"):
        p = r[k]
        o[k] = {"ids": p["selected_ids"], "cost": p["cost"], "W": vec(p["worst_vector"]), "worst_case_ids": p["worst_case_ids"],
                "base": vec(p["base_vector"]), "L": [[c["case_id"], c["unknown_count"], c["weighted_sum_mm"], c["max_mm"]] for c in p["per_case"]],
                "covered": [c["covered_weight"] for c in p["per_case"]]}
    return o


def main():
    env_p, b_p, out_p = map(Path, sys.argv[1:4])
    third = Path(sys.argv[sys.argv.index("--oracle") + 1]) if "--oracle" in sys.argv else None
    d, sha = data.load_slice(repo=str(REPO), sha=SHA)
    ctxs = {s: suite.make_context(d, sha, c, cat, "real_slice_records") for s, (c, cat) in SL.items()}
    tasks = [json.loads(l) for l in env_p.read_text(encoding="utf-8").splitlines() if l]
    build = {}
    if b_p.exists() and b_p.stat().st_size:
        for l in b_p.read_text(encoding="utf-8").splitlines():
            if l:
                b = json.loads(l); build[b["task_key"]] = b
    blind = {}
    if third:
        for l in third.read_text(encoding="utf-8").splitlines():
            if l:
                b = json.loads(l); blind[b["task_key"]] = b
    checks, mism, times = Counter(), [], defaultdict(list)

    def chk(src, field, ok, key, a=None, b=None):
        checks[f"{src}:{field}:{'ok' if ok else 'MISMATCH'}"] += 1
        if not ok:
            mism.append({"src": src, "task": key, "field": field, "k09": a, "other": b})

    for t in tasks:
        key = t["task_key"]
        o = ours_for(ctxs[t["slice"]], t["envelope"])
        if build:
            b = build.get(key)
            if b is None or "error" in b:
                chk("build", "present", False, key, None, None if b is None else b.get("error"))
            else:
                chk("build", "status", o["status"] == b["status"], key, o["status"], b["status"])
                if o["status"] == "optimal" and b["status"] == "optimal":
                    chk("build", "feasible_count", o["feasible_count"] == b["feasible_count"], key, o["feasible_count"], b["feasible_count"])
                    chk("build", "same_plan", o["same_plan"] == b["same_plan"], key, o["same_plan"], b["same_plan"])
                    pb = b["price_of_robustness_m"]
                    okp = (o["price"] is None and pb is None) or (o["price"] is not None and pb is not None and abs(o["price"] - pb) <= 1e-9 * max(1.0, abs(pb)))
                    chk("build", "price", okp, key, o["price"], pb)
                    for k in ("nominal", "robust"):
                        ob, bb = o[k], b[k]
                        chk("build", f"{k}.ids", ob["ids"] == bb["ids"], key, ob["ids"], bb["ids"])
                        chk("build", f"{k}.cost", ob["cost"] == bb["cost"], key, ob["cost"], bb["cost"])
                        chk("build", f"{k}.W", ob["W"] == vec(bb["W"]), key, ob["W"], vec(bb["W"]))
                        chk("build", f"{k}.worst_case_ids", ob["worst_case_ids"] == bb["worst_case_ids"], key, ob["worst_case_ids"], bb["worst_case_ids"])
                        bl = [[c["case_id"]] + vec(c["loss"]) for c in bb["per_case"]]
                        chk("build", f"{k}.per_case_L", ob["L"] == bl, key, ob["L"], bl)
                        chk("build", f"{k}.per_case_covered", ob["covered"] == [c["covered_weight"] for c in bb["per_case"]], key)
                        if "rows" in bb["per_case"][0]:
                            ev = RS.evaluate_resilience(ctxs[t["slice"]], t["envelope"], ob["ids"])
                            nk = lambda x: None if x is None else x["kind"] + ":" + x["id"]
                            ours_rows = [{r["point_id"]: [r["before_mm"], nk(r["nearest_before"]), r["after_mm"], nk(r["nearest_after"]), r["delta_mm"]] for r in pc["rows"]}
                                         for pc in ev["per_case"]]
                            their_rows = [{r[0]: r[1:] for r in c["rows"]} for c in bb["per_case"]]
                            chk("build", f"{k}.per_case_rows", ours_rows == their_rows, key, None if ours_rows == their_rows else "rows differ")
                    times[(t["task_key"].split("|")[0], t["task_key"].split("|")[2], len(t["envelope"]["cases"]) + 1)].append(b["t_ms"])
        if third:
            j = blind.get(key)
            if j is None:
                chk("blind", "present", False, key); continue
            chk("blind", "status", o["status"] == j["status"], key, o["status"], j["status"])
            if o["status"] == "optimal" and j["status"] == "optimal":
                for k in ("nominal", "robust"):
                    chk("blind", f"{k}.ids", o[k]["ids"] == j[k]["ids"], key, o[k]["ids"], j[k]["ids"])
                    chk("blind", f"{k}.W", o[k]["W"] == vec(j[k]["W"]), key, o[k]["W"], vec(j[k]["W"]))
                    chk("blind", f"{k}.worst_case_ids", o[k]["worst_case_ids"] == j[k]["worst_case_ids"], key, o[k]["worst_case_ids"], j[k]["worst_case_ids"])
                    chk("blind", f"{k}.base", o[k]["base"] == vec(j[k]["base"]), key, o[k]["base"], vec(j[k]["base"]))
                pj = j.get("price_of_robustness_m")
                okp = (o["price"] is None and pj is None) or (o["price"] is not None and pj is not None and abs(o["price"] - pj) <= 1e-9 * max(1.0, abs(pj)))
                chk("blind", "price", okp, key, o["price"], pj)
                chk("blind", "feasible_count", o["feasible_count"] == j.get("feasible_count"), key, o["feasible_count"], j.get("feasible_count"))

    q = lambda v, p: sorted(v)[max(0, math.ceil(p * len(v)) - 1)]
    summary = {"tasks": len(tasks), "mismatches": len(mism), "checks": dict(sorted(checks.items())),
               "build_optimize_ms": {f"{a}|{s}|cases{c}": {"n": len(v), "p50": round(q(v, 0.5), 3), "p90": round(q(v, 0.9), 3), "max": round(max(v), 3)}
                                     for (a, s, c), v in sorted(times.items())},
               "mismatch_examples": mism[:40]}
    out_p.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("tasks", "mismatches", "checks")}, ensure_ascii=False, indent=1))
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
