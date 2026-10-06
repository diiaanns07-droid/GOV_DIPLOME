"""K06 round 9 stage 1: compare the BUILD's plan.js output (from run_plan_js.cjs) with K06's independent expectations.

  python3 compare_plan_js.py --problems r8/fixtures/gold_cases.json --plan-js-json js_out.json [--json report.json]

Expectations are NOT taken from the app: each case is checked against (a) the stored independent gold
(r8/gold_bruteforce.py output frozen in the fixture) and (b) a fresh run of the K06 oracle (r8/plan_oracle.py).
Classification per case:
  PASS          math equal (status, feasible_count, three winners with their metrics, Pareto set)
  MATH          optimal/infeasible status or any of those values differ
  API_POLICY    math equal, but a policy/format detail differs (infeasible reason codes, field names, error codes)
  REJECTED      the app refused input that the spec allows (validation policy) - counted separately from MATH
  MISSING/ERROR no result / exception in the app
Exit 1 if any MATH, REJECTED, MISSING or ERROR.
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "r8"))
import plan_oracle as O                              # r8 K06 oracle (byte copy, see r8/MANIFEST.json)

METRICS = ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost")
# reason-code vocabulary: K06 oracle/gold name -> plan.js name (same meaning; naming is an API policy)
REASON_MAP = {"required_count_exceeds_max_selected": "required_exceeds_max_selected",
              "required_cost_exceeds_budget": "required_cost_exceeds_budget"}


def math_view(r):
    """Implementation-neutral math summary. Accepts K06 shape (objectives.X.selected_ids + metrics) and plan.js shape
    (objectives.X.ids + flat metric fields; pareto[].ids)."""
    if r.get("status") != "optimal":
        return {"status": r.get("status")}
    ob = {}
    for n, v in (r.get("objectives") or {}).items():
        m = v.get("metrics", v)
        ob[n] = {"ids": sorted(v.get("selected_ids", v.get("ids", []))), **{k: m.get(k) for k in METRICS}}
    par = sorted([p["cost"], p["weighted_sum_mm"], sorted(p.get("selected_ids", p.get("ids", [])))] for p in r.get("pareto") or [])
    return {"status": "optimal", "feasible_count": r.get("feasible_count"), "objectives": ob, "pareto": par}


def reason_codes(r):
    return sorted((x["code"] if isinstance(x, dict) else x) for x in r.get("reasons") or [])


def classify(name, want_oracle, want_gold, got):
    if got is None:
        return {"class": "MISSING"}
    if got.get("status") == "rejected_by_validation":
        return {"class": "REJECTED", "error_code": got.get("error_code"), "error": got.get("error")}
    if got.get("status") == "error":
        return {"class": "ERROR", "error": got.get("error")}
    mo, mg, mj = math_view(want_oracle), math_view(want_gold), math_view(got)
    if mo != mg:
        return {"class": "ORACLE_GOLD_DISAGREE", "oracle": mo, "gold": mg}       # would be a K06 bug
    if mj != mo:
        diff = {k: {"expected": mo.get(k), "plan_js": mj.get(k)} for k in sorted(set(mo) | set(mj)) if mo.get(k) != mj.get(k)}
        return {"class": "MATH", "diff": diff}
    notes = []
    if got.get("status") == "infeasible":
        exp = sorted(REASON_MAP.get(c, c) for c in reason_codes(want_oracle))
        if exp != reason_codes(got):
            return {"class": "API_POLICY", "note": f"reason codes {reason_codes(got)} vs expected (mapped) {exp}"}
        notes.append("reason codes equal after the documented name mapping")
    if got.get("metric_version") != "haversine-mm-v1":
        return {"class": "API_POLICY", "note": f"metric_version {got.get('metric_version')}"}
    return {"class": "PASS", **({"notes": notes} if notes else {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", required=True); ap.add_argument("--plan-js-json", required=True); ap.add_argument("--json")
    a = ap.parse_args()
    doc = json.load(open(a.problems, encoding="utf-8"))
    js = json.load(open(a.plan_js_json, encoding="utf-8"))
    rep = {"tested_implementation": js.get("implementation"), "tested_commit": js.get("commit"),
           "expectations": "K06 r8 gold (independent brute force) + K06 r8 oracle; never derived from the app", "cases": {}}
    for c in doc["cases"]:
        rep["cases"][c["case"]] = classify(c["case"], O.optimize(c["context"], c["scenario"]), c["gold"], js["results"].get(c["case"]))
    counts = {}
    for v in rep["cases"].values():
        counts[v["class"]] = counts.get(v["class"], 0) + 1
    rep["summary"] = counts
    if a.json:
        json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for n, v in rep["cases"].items():
        if v["class"] != "PASS":
            print(v["class"], n, json.dumps({k: x for k, x in v.items() if k != "class"}, ensure_ascii=False)[:400])
    print(counts)
    bad = {"MATH", "REJECTED", "MISSING", "ERROR", "ORACLE_GOLD_DISAGREE"}
    return 1 if bad & set(counts) else 0


if __name__ == "__main__":
    sys.exit(main())
