"""How much of G2's nobase result comes from the 'cheapest unknown-reducer first' rule?"""
import sys, json
from fractions import Fraction
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09")
from k09plan import data, suite, exact, greedy, gap
from k09plan.metric import Problem, OBJECTIVES
import k09plan.greedy as G

cfg = json.load(open("/home/user/GOV_DIPLOME/research/round-8-results/K09/config/experiment_config.json"))
d, sha = data.load_slice(repo="/home/user/GOV_DIPLOME")

def g2_variant(pr, objective, budget, ms, tiebreak):
    """Copy of greedy_ratio with a different tie-break among unknown-reducing candidates."""
    keyf = OBJECTIVES[objective]
    sel = []; after = pr.after_vector(sel); cost = 0; cur = pr.metrics_from_after(after, sel); steps = []
    free = list(range(len(pr.cand_ids)))
    while len(sel) < ms:
        best_unknown, best_ratio = None, None
        for c in sorted(free, key=lambda i: pr.cand_ids[i]):
            if c in sel or cost + pr.cost[c] > budget: continue
            a2 = G._extend(pr, after, c); m2 = pr.metrics_from_after(a2, sel + [c])
            du = cur["unknown_count"] - m2["unknown_count"]
            if du > 0:
                if tiebreak == "id": cand = (-du, pr.cand_ids[c])
                elif tiebreak == "key": cand = (-du, keyf(m2))
                elif tiebreak == "key_per_cost":   # primary metric after the step, per unit cost (lower better for mean/minimax)
                    p = G._primary(objective, m2)
                    cand = (-du, -Fraction(p, 1) / pr.cost[c] if objective == "coverage" else Fraction(-p, 1) * pr.cost[c], pr.cand_ids[c])
                if best_unknown is None or cand < best_unknown[0]:
                    best_unknown = (cand, c, a2, m2)
                continue
            p0, p1 = G._primary(objective, cur), G._primary(objective, m2)
            if p0 is None or p1 is None: continue
            gain = p1 - p0
            if gain <= 0: continue
            ratio = Fraction(gain, pr.cost[c])
            if best_ratio is None or ratio > best_ratio[0]:
                best_ratio = (ratio, c, a2, m2)
        pick = best_unknown or best_ratio
        if pick is None: break
        _, c, after, cur = pick
        sel.append(c); cost += pr.cost[c]; steps.append(pr.cand_ids[c])
    single = None
    for c in sorted(free, key=lambda i: pr.cand_ids[i]):
        if pr.cost[c] > budget: continue
        m = pr.evaluate([c])
        if single is None or keyf(m) < keyf(single): single = m
    if single is not None and keyf(single) < keyf(cur): return single
    return cur

f = cfg["factors"]
for sl in cfg["baselines"]["slices"]:
    ctx = suite.make_context(d, sha, sl["city"], sl["category"], sl["baseline"])
    if sl["id"] != "astana_clinic_nobase": continue
    tot = {o: {"impl": 0, "id": 0, "key": 0, "n": 0, "first_is_cheapest": 0} for o in OBJECTIVES}
    for nc in f["n_candidates"]:
        for npnt in f["n_points"]:
            for br in f["budget_ratio"]:
                for w in f["weights"]:
                    for seed in cfg["seeds"]:
                        sc = suite.make_scenario(ctx, nc, npnt, br, w, 3, 300, seed, cfg["config_version"])
                        pr = Problem(sc["control_points"], ctx["sources"], sc["candidates"], 300)
                        ex = exact.optimize(pr, sc["budget"], 3, with_pareto=False)
                        cheapest = min(range(nc), key=lambda i: (pr.cost[i], pr.cand_ids[i]))
                        for o in OBJECTIVES:
                            e = ex["objectives"][o]
                            r = greedy.greedy_ratio(pr, o, sc["budget"], 3)
                            t = tot[o]; t["n"] += 1
                            t["impl"] += gap.gap(o, r["plan"], e)["hit"]
                            t["first_is_cheapest"] += (r["steps"][:1] == [pr.cand_ids[cheapest]])
                            for tb in ("id", "key"):
                                t[tb] += gap.gap(o, g2_variant(pr, o, sc["budget"], 3, tb), e)["hit"]
    for o, t in tot.items():
        print(sl["id"], o, {k: (v if k == "n" else f"{v} ({100*v/t['n']:.1f}%)") for k, v in t.items()})
