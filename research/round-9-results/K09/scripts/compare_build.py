#!/usr/bin/env python3
"""Этап 1 r9: сверка настоящего plan.js (выход adapter/build_plan_adapter.cjs) с Python-оракулом r8 K09.

Сравниваются математические результаты, а не внутренние digest:
статус и причины (с картой кодов), feasible_count, три победителя (ids, cost, unknown, wsum, max, covered), Парето,
чувствительность к бюджету, evaluatePlan (метрики, допустимость, строки по точкам), число исходных записей.

  python3 scripts/compare_build.py results/stage1/tasks.jsonl results/stage1/build_d865dd4.jsonl results/stage1/compare_d865dd4.json
"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

K = Path(__file__).resolve().parents[1]
REPO = K.parents[2]
sys.path.insert(0, str(REPO / "research/round-8-results/K09"))
from k09plan import data, suite, exact  # noqa: E402
from k09plan.metric import Problem  # noqa: E402

BUILD_SHA = "d865dd4a124291e10dd0b7bb1d9eada20d34c268"
SLICES = {"shymkent_school": ("shymkent", "school", "real_slice_records"),
          "astana_clinic": ("astana", "outpatient_clinic", "real_slice_records"),
          "astana_clinic_nobase": ("astana", "outpatient_clinic", "empty_synthetic_condition")}
OBJS = ("mean", "minimax", "coverage")
# различие API: коды причин (K09 r8 -> BUILD)
REASON_MAP = {"required_count_exceeds_max_selected": "required_exceeds_max_selected", "required_cost_exceeds_budget": "required_cost_exceeds_budget"}
FEAS_MAP = {"count_exceeds_max_selected": "too_many", "cost_exceeds_budget": "over_budget", "missing_required": "missing_required", "contains_excluded": "has_excluded"}


def all_infeasible_reasons(pr, sc):
    req = [pr.cand_index[c] for c in sc["required_ids"]]
    out = set()
    if len(req) > sc["max_selected"]:
        out.add("required_exceeds_max_selected")
    if sum(pr.cost[i] for i in req) > sc["budget"]:
        out.add("required_cost_exceeds_budget")
    return out


def feas_codes(pr, sc, ids):
    s = set(ids); codes = []
    if sum(pr.cost[pr.cand_index[c]] for c in s) > sc["budget"]: codes.append("over_budget")
    if len(s) > sc["max_selected"]: codes.append("too_many")
    if set(sc["required_ids"]) - s: codes.append("missing_required")
    if set(sc["excluded_ids"]) & s: codes.append("has_excluded")
    return codes


def main():
    tasks_p, build_p, out_p = map(Path, sys.argv[1:4])
    d, sha = data.load_slice(repo=str(REPO), sha=BUILD_SHA)
    ctxs = {s: suite.make_context(d, sha, *SLICES[s]) for s in SLICES}
    tasks = [json.loads(l) for l in tasks_p.read_text(encoding="utf-8").splitlines() if l]
    build = {}
    for l in build_p.read_text(encoding="utf-8").splitlines():
        if l:
            b = json.loads(l); build[b["task_id"]] = b
    checks = defaultdict(Counter)        # (set) -> Counter(field -> n checked)
    mism = []
    t_build = defaultdict(list)

    def chk(tset, field, ok, tid, ours=None, theirs=None):
        checks[tset][field + (":ok" if ok else ":MISMATCH")] += 1
        if not ok:
            mism.append({"task": tid, "field": field, "k09": ours, "build": theirs})

    for t in tasks:
        tid, tset, ctx, sc = t["task_id"], t["set"], ctxs[t["slice"]], t["scenario"]
        b = build.get(tid)
        if b is None:
            chk(tset, "present", False, tid); continue
        if "validation_error" in b:
            chk(tset, "validated", False, tid, None, b["validation_error"]); continue
        chk(tset, "n_sources", b["n_sources"] == len(ctx["sources"]), tid, len(ctx["sources"]), b["n_sources"])
        pr = Problem(sc["control_points"], ctx["sources"], sc["candidates"], sc["coverage_radius_m"])
        args = (sc["budget"], sc["max_selected"], sc["required_ids"], sc["excluded_ids"])
        r = exact.optimize(pr, *args)
        chk(tset, "status", r["status"] == b["status"], tid, r["status"], b["status"])
        if r["status"] == "infeasible":
            ok = REASON_MAP[r["reason"]] in b["reason_codes"] and set(b["reason_codes"]) == all_infeasible_reasons(pr, sc)
            chk(tset, "infeasible_reasons", ok, tid, r["reason"], b["reason_codes"])
        else:
            chk(tset, "feasible_count", r["feasible_count"] == b["feasible_count"], tid, r["feasible_count"], b["feasible_count"])
            for o in OBJS:
                e, g = r["objectives"][o], b["objectives"][o]
                ours = [e["selected_ids"], e["cost"], e["unknown_count"], e["weighted_sum_mm"], e["max_mm"], e["covered_weight"]]
                theirs = [g["ids"], g["cost"], g["unknown_count"], g["weighted_sum_mm"], g["max_mm"], g["covered_weight"]]
                chk(tset, f"objective.{o}", ours == theirs, tid, ours, theirs)
            op = [[p["cost"], p["weighted_sum_mm"], p["selected_ids"]] for p in r["pareto"]]
            bp = [[p["cost"], p["weighted_sum_mm"], p["ids"]] for p in b["pareto"]]
            chk(tset, "pareto", op == bp, tid, op, bp)
            t_build[(tset, t["scenario"]["candidates"].__len__(), sc["max_selected"])].append(b["t_optimize_ms"])
        sens = exact.budget_sensitivity(pr, *args)
        os_ = [[x["budget"], x["status"]] + ([x["objectives"][o]["selected_ids"] for o in OBJS] if x["status"] == "optimal" else []) for x in sens]
        bs_ = [[x["budget"], x["status"]] + ([x["ids"][o] for o in OBJS] if x["status"] == "optimal" else []) for x in b["sensitivity"]]
        chk(tset, "sensitivity", os_ == bs_, tid, os_, bs_)
        evb = {tuple(e["ids"]): e for e in b["evals"]}
        for ids in t["selections"]:
            e = evb.get(tuple(sorted(set(ids))))
            if e is None:
                chk(tset, "eval.present", False, tid, ids, None); continue
            idx = [pr.cand_index[c] for c in ids]
            m = pr.evaluate(idx)
            mo = [m["unknown_count"], m["weighted_sum_mm"], m["weighted_mean_mm"], m["max_mm"], m["covered_weight"], pr.total_weight, m["cost"]]
            mb = [e["metrics"][k] for k in ("unknown_count", "weighted_sum_mm", "weighted_mean_mm", "max_mm", "covered_weight", "total_weight", "cost")]
            chk(tset, "eval.metrics", mo == mb, tid, mo, mb)
            fc = feas_codes(pr, sc, ids)
            chk(tset, "eval.feasibility", (not fc) == e["feasible"] and sorted(fc) == sorted(e["reason_codes"]), tid, fc, e["reason_codes"])
            rows_o = {x["point_id"]: [x["before_mm"], x["after_mm"], x["delta_mm"],
                                      None if x["nearest_after"] is None else x["nearest_after"]["kind"] + ":" + x["nearest_after"]["id"]] for x in pr.rows(idx)}
            rows_b = {x[0]: x[1:] for x in e["rows"]}
            chk(tset, "eval.rows", rows_o == rows_b, tid, None if rows_o == rows_b else "rows differ", None)
    summary = {"build_sha": BUILD_SHA, "tasks": len(tasks), "mismatches": len(mism),
               "checks_by_set": {s: dict(sorted(c.items())) for s, c in checks.items()},
               "build_optimize_ms": {f"{s}|nc{nc}|ms{ms}": {"n": len(v), "p50": sorted(v)[len(v) // 2], "max": max(v)}
                                     for (s, nc, ms), v in sorted(t_build.items())},
               "mismatch_examples": mism[:50]}
    out_p.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("tasks", "mismatches", "checks_by_set")}, ensure_ascii=False, indent=1))
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
