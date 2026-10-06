"""K06 r9 stage 1: accept/reject policy of plan.js validatePlanScenario vs the K06 r8 oracle validator.
  python3 probe_api_policy.py --app-root <extracted city-evidence> [--json out/api_policy_<sha>.json]
A difference is an API POLICY difference (not a math error). Probes are SYNTHETIC inputs."""
import argparse, copy, json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "r8"))
import plan_oracle as O

ap = argparse.ArgumentParser(); ap.add_argument("--app-root", required=True); ap.add_argument("--json")
a = ap.parse_args()
doc = json.load(open(os.path.join(HERE, "r8", "fixtures", "gold_cases.json"), encoding="utf-8"))
base = next(c for c in doc["cases"] if c["case"] == "budget_full_max3")
ctx, sc0 = base["context"], base["scenario"]


def v(**kw):
    s = copy.deepcopy(sc0); s.update(kw); return s


def cand(i, **kw):
    s = copy.deepcopy(sc0); s["candidates"][i].update(kw); return s


def point(i, **kw):
    s = copy.deepcopy(sc0); s["control_points"][i].update(kw); return s


nopw = copy.deepcopy(sc0); del nopw["control_points"][0]["weight"]
extra_f = copy.deepcopy(sc0); extra_f["url"] = "http://example.invalid/x"
seventeen = copy.deepcopy(sc0)
seventeen["candidates"] = [dict(sc0["candidates"][0], id=f"k{i:02d}") for i in range(17)]
probes = {
    "valid_base": sc0,
    "id_with_space": cand(0, id="c 1"),
    "id_with_colon": cand(0, id="c:1"),
    "id_cyrillic_nfc": cand(0, id="школа_1"),
    "id_65_chars": cand(0, id="x" * 65),
    "weight_missing_default_1": nopw,
    "weight_zero": point(0, weight=0),
    "weight_float_integral": point(0, weight=2.0),
    "cost_zero": cand(0, cost=0),
    "budget_negative": v(budget=-1),
    "radius_99": v(coverage_radius_m=99),
    "radius_5001": v(coverage_radius_m=5001),
    "max_selected_6": v(max_selected=6),
    "required_excluded_overlap": v(required_ids=["c1"], excluded_ids=["c1"]),
    "required_unknown_id": v(required_ids=["nope"]),
    "selected_duplicate": v(selected_ids=["c1", "c1"]),
    "candidate_kind_source": cand(0, kind="source"),
    "candidate_other_category": cand(0, category="outpatient_clinic"),
    "candidate_outside_bbox": cand(0, lon=60.0),
    "unknown_top_field": extra_f,
    "derived_results_present": v(derived_results={"anything": 1}),
    "candidates_17": seventeen,
    "zero_points": v(control_points=[]),
    "foreign_snapshot": v(source_snapshot="other"),
}
k06 = {}
for n, s in probes.items():
    try:
        O.validate(s, ctx); k06[n] = {"accepted": True}
    except O.PlanError as e:
        k06[n] = {"accepted": False, "code": e.code}
with tempfile.TemporaryDirectory() as d:
    pin, pout = os.path.join(d, "p.json"), os.path.join(d, "o.json")
    json.dump({n: {"context": ctx, "scenario": s} for n, s in probes.items()}, open(pin, "w"))
    subprocess.run(["node", os.path.join(HERE, "probe_validate.cjs"), a.app_root, pin, pout], check=True)
    js = json.load(open(pout))
rows = {n: {"k06_oracle": k06[n], "plan_js": js[n], "same_decision": k06[n]["accepted"] == js[n]["accepted"]} for n in probes}
rep = {"note": "accept/reject policy only; SYNTHETIC probes on case budget_full_max3", "probes": rows,
       "differences": [n for n, r in rows.items() if not r["same_decision"]]}
if a.json:
    json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for n, r in rows.items():
    print(("SAME " if r["same_decision"] else "DIFF ") + n, r["k06_oracle"], r["plan_js"])
