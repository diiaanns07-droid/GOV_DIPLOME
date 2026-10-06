"""Stage 1 self-check: corrupted plan.js outputs must be classified correctly by compare_plan_js.
  python3 mutation_check_stage1.py --problems r8/fixtures/gold_cases.json --plan-js-json out/plan_js_d865dd4_gold96.json"""
import argparse, copy, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_plan_js as C
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "r8"))
import plan_oracle as O

ap = argparse.ArgumentParser(); ap.add_argument("--problems", required=True); ap.add_argument("--plan-js-json", required=True)
a = ap.parse_args()
doc = json.load(open(a.problems, encoding="utf-8")); js = json.load(open(a.plan_js_json, encoding="utf-8"))["results"]
cases = {c["case"]: c for c in doc["cases"]}
opt = [n for n, r in js.items() if r["status"] == "optimal" and len(r["pareto"]) > 1]
inf = [n for n, r in js.items() if r["status"] == "infeasible"]
muts = {
    "wsum_off_by_one_mm": (opt[0], lambda r: r["objectives"]["mean"].__setitem__("weighted_sum_mm", r["objectives"]["mean"]["weighted_sum_mm"] + 1), "MATH"),
    "wrong_minimax_ids": (opt[1], lambda r: r["objectives"]["minimax"].__setitem__("ids", ["zz_not_a_candidate"]), "MATH"),
    "pareto_point_dropped": (opt[2], lambda r: r["pareto"].pop(), "MATH"),
    "max_null_instead_of_value": (opt[3], lambda r: r["objectives"]["coverage"].__setitem__("max_mm", None), "MATH"),
    "feasible_count_off": (opt[4], lambda r: r.__setitem__("feasible_count", r["feasible_count"] + 1), "MATH"),
    "optimal_reported_infeasible": (opt[5], lambda r: r.__setitem__("status", "infeasible"), "MATH"),
    "partial_search_called_incomplete": (opt[6], lambda r: r.__setitem__("status", "incomplete"), "MATH"),
    "reason_code_renamed": (inf[0], lambda r: r["reasons"][0].__setitem__("code", "some_other_code"), "API_POLICY"),
    "rejected_input": (opt[7], lambda r: (r.clear(), r.update({"status": "rejected_by_validation", "error_code": "bad_id"})), "REJECTED"),
}
res = {}
for name, (case, f, want) in muts.items():
    r = copy.deepcopy(js[case]); f(r)
    c = cases[case]
    got = C.classify(case, O.optimize(c["context"], c["scenario"]), c["gold"], r)["class"]
    res[name] = {"case": case, "expected_class": want, "got": got, "ok": got == want}
print(json.dumps(res, indent=1))
sys.exit(0 if all(v["ok"] for v in res.values()) else 1)
