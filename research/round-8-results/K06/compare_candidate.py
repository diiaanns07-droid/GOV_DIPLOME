"""Stage 3: compare another implementation's optimizePlans output (e.g. the BUILD's JS) with the oracle.

  python3 compare_candidate.py --problems fixtures/gold_cases.json --export problems_for_js.json
      -> writes {"cases": {name: {"context", "scenario"}}} for the other implementation to run
  python3 compare_candidate.py --problems fixtures/gold_cases.json --candidate-json js_out.json [--json report.json]
      -> js_out.json = {"implementation": "...", "commit": "<sha>", "results": {name: <optimizePlans output>}}
  python3 compare_candidate.py --problems ... --self-test     (oracle vs itself + injected faults must be caught)

Accepted field names (adapter): status; objectives.{mean,minimax,coverage}.{selected_ids|selectedIds|ids} and
.metrics.{unknown_count, weighted_sum_mm, max_mm, covered_weight, cost} (camelCase also accepted);
pareto[].{selected_ids|selectedIds|ids, cost, weighted_sum_mm|weightedSumMm}; feasible_count|feasibleCount;
metric_version|metricVersion. "evaluated" and problem_digest are reported but not compared (convention-dependent).
Exit code 1 if any case differs or is missing. A missing case is MISSING, never PASS.
"""
import argparse, copy, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_oracle as O

METRICS = ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost")


def snake(k):
    return re.sub(r"(?<!^)([A-Z])", r"_\1", k).lower()


def norm_keys(o):
    if isinstance(o, dict):
        return {snake(k): norm_keys(v) for k, v in o.items()}
    if isinstance(o, list):
        return [norm_keys(x) for x in o]
    return o


def ids_of(o):
    for k in ("selected_ids", "ids"):
        if k in o:
            return sorted(o[k])
    raise KeyError("selected_ids")


def normalise(r):
    r = norm_keys(r)
    out = {"status": r.get("status"), "metric_version": r.get("metric_version")}
    if r.get("status") != "optimal":
        return out
    out["feasible_count"] = r.get("feasible_count")
    out["objectives"] = {n: {"ids": ids_of(v), **{m: v.get("metrics", {}).get(m) for m in METRICS}}
                         for n, v in (r.get("objectives") or {}).items()}
    out["pareto"] = sorted([p["cost"], p.get("weighted_sum_mm"), ids_of(p)] for p in r.get("pareto") or [])
    return out


def load_problems(path):
    d = json.load(open(path, encoding="utf-8"))
    if "cases" in d and isinstance(d["cases"], list):
        return {c["case"]: (c["context"], c["scenario"]) for c in d["cases"]}
    src = d.get("cases", d)
    return {n: (v["context"], v["scenario"]) for n, v in src.items()}


def compare(problems, candidate):
    res = candidate.get("results", candidate)
    report = {"implementation": candidate.get("implementation"), "commit": candidate.get("commit"), "cases": {}}
    for name, (ctx, sc) in problems.items():
        want = normalise(O.optimize(ctx, sc))
        if name not in res:
            report["cases"][name] = {"status": "MISSING"}
            continue
        try:
            got = normalise(res[name])
        except (KeyError, TypeError, AttributeError) as e:
            report["cases"][name] = {"status": "FAIL", "error": f"unreadable output: {e!r}"}
            continue
        diffs = [k for k in sorted(set(want) | set(got)) if want.get(k) != got.get(k)]
        report["cases"][name] = {"status": "PASS" if not diffs else "FAIL",
                                 **({"diff": {k: {"oracle": want.get(k), "candidate": got.get(k)} for k in diffs}} if diffs else {})}
    st = [v["status"] for v in report["cases"].values()]
    report["summary"] = {s: st.count(s) for s in sorted(set(st))}
    return report


def self_test(problems):
    good = {"implementation": "plan_oracle (self)", "results": {n: O.optimize(c, s) for n, (c, s) in problems.items()}}
    r0 = compare(problems, good)
    assert set(r0["summary"]) == {"PASS"}, r0["summary"]
    faults = 0
    names = [n for n, v in good["results"].items() if v["status"] == "optimal" and v["pareto"]]
    if len(names) < 5:
        return {"self_compare": r0["summary"], "injected_faults": "SKIP: need >= 5 optimal cases with a Pareto front"}
    bad = copy.deepcopy(good)
    n1, n2, n3, n4 = names[0], names[1], names[2], names[3]
    bad["results"][n1]["objectives"]["mean"]["metrics"]["weighted_sum_mm"] += 1            # off by one mm
    bad["results"][n2]["objectives"]["minimax"]["selected_ids"] = ["not_a_plan"]           # wrong winner
    bad["results"][n3]["pareto"] = bad["results"][n3]["pareto"][:-1] if len(bad["results"][n3]["pareto"]) > 1 else []
    bad["results"][n4]["status"] = "optimal_partial"                                        # not 'optimal'
    del bad["results"][names[4]]                                                            # missing
    r1 = compare(problems, bad)
    for n, want in ((n1, "FAIL"), (n2, "FAIL"), (n3, "FAIL"), (n4, "FAIL"), (names[4], "MISSING")):
        assert r1["cases"][n]["status"] == want, (n, r1["cases"][n])
        faults += 1
    camel = {"results": {n1: {"status": "optimal", "metricVersion": "haversine-mm-v1",
                              "feasibleCount": good["results"][n1]["feasible_count"],
                              "objectives": {k: {"selectedIds": v["selected_ids"],
                                                 "metrics": {"unknownCount": v["metrics"]["unknown_count"],
                                                             "weightedSumMm": v["metrics"]["weighted_sum_mm"],
                                                             "maxMm": v["metrics"]["max_mm"],
                                                             "coveredWeight": v["metrics"]["covered_weight"],
                                                             "cost": v["metrics"]["cost"]}}
                                             for k, v in good["results"][n1]["objectives"].items()},
                              "pareto": [{"selectedIds": p["selected_ids"], "cost": p["cost"], "weightedSumMm": p["weighted_sum_mm"]}
                                         for p in good["results"][n1]["pareto"]]}}}
    assert compare({n1: problems[n1]}, camel)["cases"][n1]["status"] == "PASS"
    return {"self_compare": r0["summary"], "injected_faults_caught": faults, "camelCase_adapter": "PASS"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", required=True)
    ap.add_argument("--candidate-json"); ap.add_argument("--export"); ap.add_argument("--json")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    problems = load_problems(a.problems)
    if a.export:
        json.dump({"cases": {n: {"context": c, "scenario": s} for n, (c, s) in problems.items()}},
                  open(a.export, "w", encoding="utf-8"), ensure_ascii=False)
        print(len(problems), "problems ->", a.export)
    if a.self_test:
        print(json.dumps(self_test(problems), indent=1))
    if a.candidate_json:
        rep = compare(problems, json.load(open(a.candidate_json, encoding="utf-8")))
        if a.json:
            json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for n, v in rep["cases"].items():
            if v["status"] != "PASS":
                print(v["status"], n, json.dumps(v.get("diff") or v.get("error") or "", ensure_ascii=False)[:300])
        print(rep["summary"])
        return 0 if set(rep["summary"]) <= {"PASS"} else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
