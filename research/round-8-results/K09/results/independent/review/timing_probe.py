import sys, json, time, statistics
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09")
from k09plan import data, suite, exact, api
from k09plan.metric import Problem
cfg = json.load(open("/home/user/GOV_DIPLOME/research/round-8-results/K09/config/experiment_config.json"))
d, sha = data.load_slice(repo="/home/user/GOV_DIPLOME")
def tmin(fn, r=3):
    b = None
    for _ in range(r):
        t = time.perf_counter(); fn(); dt = time.perf_counter() - t
        b = dt if b is None or dt < b else b
    return b
for ratio in (0.5, 1.0):
    ex, full, fc = [], [], []
    for sl in cfg["baselines"]["slices"]:
        ctx = suite.make_context(d, sha, sl["city"], sl["category"], sl["baseline"])
        for seed in range(10):
            sc = suite.make_scenario(ctx, 16, 25, ratio, "random_1_100", 3, 300, seed, cfg["config_version"])
            sc["max_selected"] = 5
            pr = Problem(sc["control_points"], ctx["sources"], sc["candidates"], 300)
            r = exact.optimize(pr, sc["budget"], 5, with_pareto=False); fc.append(r["feasible_count"])
            ex.append(tmin(lambda: exact.optimize(pr, sc["budget"], 5, with_pareto=False)))
            full.append(tmin(lambda: api.optimize_plans(ctx, sc)))
    print(f"ratio={ratio} ms=5 nc=16 np=25: exact-only median {1e3*statistics.median(ex):.1f} ms, max {1e3*max(ex):.1f};"
          f" optimize_plans (pareto+sensitivity) median {1e3*statistics.median(full):.1f} ms, max {1e3*max(full):.1f}; feasible_count median {statistics.median(fc)} max {max(fc)}")
