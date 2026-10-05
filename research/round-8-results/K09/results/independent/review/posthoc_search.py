import sys, random
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09"); sys.path.insert(0, ".")
from k09plan import metric, exact, greedy, gap
import fuzz_exact as F
rng = random.Random(4242); checked = viol = 0
for t in range(40000):
    pts, srcs, cands, rad, budget, ms, req, exc = F.gen(rng)
    pr = metric.Problem(pts, srcs, cands, rad)
    r = exact.optimize(pr, budget, ms)
    if r["status"] != "optimal": continue
    for o in ("mean", "minimax", "coverage"):
        e = r["objectives"][o]
        if len(e["selected_ids"]) > 1: continue
        for fn in (greedy.greedy_key, greedy.greedy_ratio):
            checked += 1
            if not gap.gap(o, fn(pr, o, budget, ms)["plan"], e)["hit"]:
                viol += 1; print("VIOLATION", t, o, fn.__name__)
print("checked", checked, "violations", viol)
