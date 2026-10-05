#!/usr/bin/env python3
"""Сверка k09plan со слепыми независимыми реализациями (JS, написаны по CORE_SPEC и текстовому описанию G1/G2).

  python3 scripts/compare_blind.py results/independent
Ожидает в каталоге: inputs.json, blind_exact_out.json, blind_greedy_out.json. Пишет compare_report.json.
Ожидаемые значения пересчитываются здесь модулем k09plan из тех же inputs (не берутся из файлов).
"""
import json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan import exact, greedy, api  # noqa: E402

OBJ = ("mean", "minimax", "coverage")
FIELDS = ("selected_ids", "weighted_sum_mm", "max_mm", "covered_weight", "unknown_count", "cost")


def ours(task):
    ctx, sc = task["context"], task["scenario"]
    pr = api.problem_of(ctx, sc)
    args = (sc["budget"], sc["max_selected"], sc["required_ids"], sc["excluded_ids"])
    r = exact.optimize(pr, *args)
    e = {"status": r["status"], "reason": r.get("reason"), "feasible_count": r["feasible_count"]}
    if r["status"] == "optimal":
        e["objectives"] = {k: {f: v[f] for f in FIELDS} for k, v in r["objectives"].items()}
        e["pareto"] = r["pareto"]
    e["budget_sensitivity"] = [{"budget": x["budget"], "status": x["status"],
                                "objectives": {k: (None if v is None else v["selected_ids"]) for k, v in x["objectives"].items()}}
                               for x in exact.budget_sensitivity(pr, *args)]
    g = {}
    for name, fn in (("G1", greedy.greedy_key), ("G2", greedy.greedy_ratio)):
        g[name] = {}
        for o in OBJ:
            x = fn(pr, o, *args)
            g[name][o] = None if x["status"] == "infeasible" else x["plan"]["selected_ids"]
    return e, g


def main():
    d = Path(sys.argv[1] if len(sys.argv) > 1 else K / "results/independent")
    tasks = json.loads((d / "inputs.json").read_text(encoding="utf-8"))["tasks"]
    bx = json.loads((d / "blind_exact_out.json").read_text(encoding="utf-8"))
    bg = json.loads((d / "blind_greedy_out.json").read_text(encoding="utf-8"))
    mism, checked = [], {"exact_fields": 0, "pareto": 0, "sensitivity": 0, "greedy": 0}
    for t in tasks:
        tid = t["task_id"]
        e, g = ours(t)
        b = bx.get(tid)
        if b is None:
            mism.append({"task": tid, "what": "blind_exact missing"}); continue
        for f in ("status", "feasible_count"):
            checked["exact_fields"] += 1
            if b.get(f) != e[f]: mism.append({"task": tid, "what": f, "ours": e[f], "blind": b.get(f)})
        if e["status"] != "optimal":
            checked["exact_fields"] += 1
            if b.get("reason") != e["reason"]: mism.append({"task": tid, "what": "reason", "ours": e["reason"], "blind": b.get("reason")})
        else:
            for o in OBJ:
                for f in FIELDS:
                    checked["exact_fields"] += 1
                    bv = (b.get("objectives") or {}).get(o, {}).get(f)
                    if bv != e["objectives"][o][f]:
                        mism.append({"task": tid, "what": f"{o}.{f}", "ours": e["objectives"][o][f], "blind": bv})
            checked["pareto"] += 1
            if b.get("pareto") != e["pareto"]: mism.append({"task": tid, "what": "pareto", "ours": e["pareto"], "blind": b.get("pareto")})
        if "budget_sensitivity" in b or "budget_sensitivity" in e:
            checked["sensitivity"] += 1
            bs = [{"budget": x["budget"], "status": x["status"], "objectives": x.get("objectives")} for x in b.get("budget_sensitivity", [])]
            es = [{"budget": x["budget"], "status": x["status"],
                   "objectives": x["objectives"] if x["status"] == "optimal" else {k: None for k in OBJ}} for x in e["budget_sensitivity"]]
            bs = [dict(x, objectives=x["objectives"] if x["status"] == "optimal" else {k: None for k in OBJ}) for x in bs]
            if bs != es: mism.append({"task": tid, "what": "budget_sensitivity", "ours": es, "blind": bs})
        gb = bg.get(tid)
        for name in ("G1", "G2"):
            for o in OBJ:
                checked["greedy"] += 1
                bv = None if gb is None else (gb.get(name) or {}).get(o)
                if bv != g[name][o]: mism.append({"task": tid, "what": f"{name}.{o}", "ours": g[name][o], "blind": bv})
    rep = {"tasks": len(tasks), "checked": checked, "mismatches": len(mism), "details": mism}
    (d / "compare_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "details"}, ensure_ascii=False))
    for m in mism[:30]:
        print(m)
    sys.exit(1 if mism else 0)


if __name__ == "__main__":
    main()
