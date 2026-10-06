#!/usr/bin/env python3
"""Этап 1 r9: задачи из результатов r8 K09 для сверки с настоящим plan.js (JSONL для adapter/build_plan_adapter.cjs).

Наборы:
- ind34 — 34 задачи слепой проверки r8 (results/independent/inputs.json): required/excluded, infeasible, ms=0, бюджет 0, дубль;
- v1    — все 2610 сценариев предрегистрированной сетки r8 v1 (config/experiment_config.json);
- v2    — все 3420 сценариев r8 v2 (config/experiment_config_v2.json).
selections для evaluatePlan: три точных плана r8 (mean/minimax/coverage), планы G1/G2 (mean) и пустой план.
Модули r8 используются только для чтения (research/round-8-results/K09/k09plan), r8 не меняется.

  python3 scripts/make_build_tasks.py --out results/stage1/tasks.jsonl
"""
import argparse, json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
REPO = K.parents[2]
R8 = REPO / "research/round-8-results/K09"
sys.path.insert(0, str(R8))
from k09plan import data, suite, experiment as X, exact, greedy  # noqa: E402
from k09plan.metric import Problem  # noqa: E402

BUILD_SHA = "d865dd4a124291e10dd0b7bb1d9eada20d34c268"
SLICES = {"shymkent_school": ("shymkent", "school", "real_slice_records"),
          "astana_clinic": ("astana", "outpatient_clinic", "real_slice_records"),
          "astana_clinic_nobase": ("astana", "outpatient_clinic", "empty_synthetic_condition")}
SC_KEYS = ("control_points", "candidates", "budget", "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids")


def selections(pr, sc):
    sel = []
    r = exact.optimize(pr, sc["budget"], sc["max_selected"], sc["required_ids"], sc["excluded_ids"], with_pareto=False)
    if r["status"] == "optimal":
        sel += [r["objectives"][o]["selected_ids"] for o in ("mean", "minimax", "coverage")]
    for fn in (greedy.greedy_key, greedy.greedy_ratio):
        g = fn(pr, "mean", sc["budget"], sc["max_selected"], sc["required_ids"], sc["excluded_ids"])
        if g["status"] != "infeasible":
            sel.append(g["plan"]["selected_ids"])
    sel.append([])
    if sc["selected_ids"]:
        sel.append(sorted(sc["selected_ids"]))
    out = []
    for s in sel:
        if s not in out:
            out.append(s)
    return out


def task(tid, slice_id, ctx, sc):
    city, cat, base = SLICES[slice_id]
    pr = Problem(sc["control_points"], ctx["sources"], sc["candidates"], sc["coverage_radius_m"])
    return {"task_id": tid, "set": tid.split(":")[0], "slice": slice_id, "city": city, "category": cat, "baseline": base,
            "scenario": {k: sc[k] for k in SC_KEYS}, "selections": selections(pr, sc)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(K / "results/stage1/tasks.jsonl"))
    ap.add_argument("--sets", default="ind34,v1,v2")
    a = ap.parse_args()
    d, sha = data.load_slice(repo=str(REPO), sha=BUILD_SHA)
    assert sha == data.EXPECTED_DATA_SHA256, "data.js в BUILD отличается от r8"
    ctxs = {s: suite.make_context(d, sha, *SLICES[s]) for s in SLICES}
    tasks = []
    sets = a.sets.split(",")
    if "ind34" in sets:
        inp = json.loads((R8 / "results/independent/inputs.json").read_text(encoding="utf-8"))["tasks"]
        for t in inp:
            sid = t["task_id"].split("#")[0]
            sid = "astana_clinic" if sid == "tie" else sid
            tasks.append(task(f"ind34:{t['task_id']}", sid, ctxs[sid], t["scenario"]))
    for name, cfgfile in (("v1", "experiment_config.json"), ("v2", "experiment_config_v2.json")):
        if name not in sets:
            continue
        cfg = json.loads((R8 / "config" / cfgfile).read_text(encoding="utf-8"))
        for an, sid, params, ov in X.scenario_plan(cfg):
            sc = X.make(ctxs[sid], cfg, params)
            sc.update(ov)
            nc, npnt, br, w, ms, rad, seed = params
            key = f"{an}|{sid}|nc{nc}|np{npnt}|br{br}|{w}|ms{sc['max_selected']}|r{sc['coverage_radius_m']}|s{seed}"
            tasks.append(task(f"{name}:{key}", sid, ctxs[sid], sc))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(t, ensure_ascii=False, separators=(",", ":")) + "\n" for t in tasks), encoding="utf-8")
    print(f"{len(tasks)} tasks -> {out}")


if __name__ == "__main__":
    main()
