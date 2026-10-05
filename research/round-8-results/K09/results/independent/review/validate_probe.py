import sys, json
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09")
from k09plan import data, suite, validate, api, exact
cfg = json.load(open("/home/user/GOV_DIPLOME/research/round-8-results/K09/config/experiment_config.json"))
d, sha = data.load_slice(repo="/home/user/GOV_DIPLOME")
ctx = suite.make_context(d, sha, "shymkent", "school", "real_slice_records")
sc = suite.make_scenario(ctx, 6, 5, 0.5, "uniform", 3, 300, 0, "x")
txt = json.dumps(sc)

# 1. 400-digit integer longitude -> OverflowError escapes validate_plan_scenario
bad = txt.replace(json.dumps(sc["control_points"][0]["lon"]), "1" + "0" * 400, 1)
try:
    print("1:", api.validate_plan_scenario(bad, ctx))
except Exception as e:
    print("1: EXCEPTION", type(e).__name__, str(e)[:60])

# 2. deeply nested JSON within 256 KiB -> RecursionError escapes parse_import
deep = '{"derived_results": ' + "[" * 100000 + "]" * 100000 + "}"
print("2: size", len(deep))
try:
    print("2:", api.validate_plan_scenario(deep, ctx))
except Exception as e:
    print("2: EXCEPTION", type(e).__name__, str(e)[:70])

# 3. integral float weight/cost (JSON 1.0) rejected; JS JSON.parse cannot distinguish 1.0 from 1
s3 = txt.replace('"weight": 1', '"weight": 1.0', 1)
print("3:", api.validate_plan_scenario(s3, ctx)[1])

# 4. problem_digest depends on number spelling 69 vs 69.0 (same problem)
a = json.loads(txt); b = json.loads(txt)
a["control_points"][0]["lon"] = 69.6; b["control_points"][0]["lon"] = 69.6
a["control_points"][0]["lat"] = 42.31; b["control_points"][0]["lat"] = 42.31
a["candidates"][0]["lon"] = 69.6; b["candidates"][0]["lon"] = 69.6
a["control_points"][1]["lat"] = 42.32; b["control_points"][1]["lat"] = 42.32
# integer-valued coordinate: use bbox-like integer? choose a weight-free field: budget is int already; use lon written as 70 vs 70.0 in a wide-bbox context
ctx2 = dict(ctx, bbox=[69, 42, 71, 43])
a["control_points"][0]["lon"] = 70; b["control_points"][0]["lon"] = 70.0
print("4: validate a,b:", validate.validate(a, ctx2), validate.validate(b, ctx2))
print("4: digest equal?", exact.problem_digest(ctx2, a) == exact.problem_digest(ctx2, b))
r1 = api.optimize_plans(ctx2, a, with_sensitivity=False); r2 = api.optimize_plans(ctx2, b, with_sensitivity=False)
print("4: objectives equal?", r1["objectives"] == r2["objectives"])

# 5. nobase and real astana contexts share the same source_snapshot
c_real = suite.make_context(d, sha, "astana", "outpatient_clinic", "real_slice_records")
c_nob = suite.make_context(d, sha, "astana", "outpatient_clinic", "empty_synthetic_condition")
print("5: same snapshot:", c_real["source_snapshot"] == c_nob["source_snapshot"], "sources:", len(c_real["sources"]), len(c_nob["sources"]))
s5 = suite.make_scenario(c_nob, 6, 5, 0.5, "uniform", 3, 300, 0, "x")
print("5: nobase scenario validates under REAL context:", validate.validate(s5, c_real))
r_real = api.optimize_plans(c_real, s5, with_sensitivity=False)["objectives"]["mean"]
r_nob = api.optimize_plans(c_nob, s5, with_sensitivity=False)["objectives"]["mean"]
print("5: mean plan real vs nobase:", r_real["selected_ids"], r_real["weighted_sum_mm"], "|", r_nob["selected_ids"], r_nob["weighted_sum_mm"])
