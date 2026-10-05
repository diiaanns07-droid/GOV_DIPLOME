import sys, itertools, math, random
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09")
from k09plan import metric, exact, greedy, gap

def mm(a, b):
    # independent haversine
    lon1, lat1 = a; lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    h = min(1.0, max(0.0, h))
    return int(math.floor(2*6371008.8*math.asin(math.sqrt(h))*1000 + 0.5))

def brute(points, sources, cands, rad, budget, ms, req, exc):
    cs = sorted(cands, key=lambda c: c["id"])
    plans = []
    for r in range(len(cs)+1):
        for comb in itertools.combinations(cs, r):
            ids = [c["id"] for c in comb]
            if set(exc) & set(ids): continue
            if not set(req) <= set(ids): continue
            if len(ids) > ms: continue
            cost = sum(c["cost"] for c in comb)
            if cost > budget: continue
            after = []
            for p in points:
                ds = [mm((p["lon"], p["lat"]), (o["lon"], o["lat"])) for o in list(sources)+list(comb)]
                after.append(min(ds) if ds else None)
            unk = sum(v is None for v in after)
            ws = sum(p["weight"]*v for p, v in zip(points, after) if v is not None)
            mx = max(after) if unk == 0 else None
            cov = sum(p["weight"] for p, v in zip(points, after) if v is not None and v <= rad*1000)
            M = math.inf if mx is None else mx
            plans.append(dict(ids=sorted(ids), cost=cost, unk=unk, ws=ws, mx=mx, cov=cov,
                              k={"mean": (unk, ws, M, cost, sorted(ids)), "minimax": (unk, M, ws, cost, sorted(ids)),
                                 "coverage": (-cov, unk, ws, M, cost, sorted(ids))}))
    return plans

def pareto(plans):
    known = [p for p in plans if p["unk"] == 0]
    pairs = {(p["cost"], p["ws"]) for p in known}
    nd = sorted(q for q in pairs if not any(o != q and o[0] <= q[0] and o[1] <= q[1] for o in pairs))
    return [{"cost": c, "weighted_sum_mm": w, "selected_ids": min(p["ids"] for p in known if (p["cost"], p["ws"]) == (c, w))} for c, w in nd]

def gen(rng):
    n_c = rng.randint(0, 9); n_p = rng.randint(1, 8); n_s = rng.choice([0, 0, 1, 3])
    grid = rng.choice([True, False])
    def pt():
        if grid:  # coarse grid -> many distance ties
            return round(69.60 + rng.randint(0, 4)*0.001, 6), round(42.31 + rng.randint(0, 4)*0.001, 6)
        return round(rng.uniform(69.59, 69.62), 6), round(rng.uniform(42.30, 42.33), 6)
    pts = [dict(id=f"p{i}", lon=a, lat=b, weight=rng.choice([1, 1, rng.randint(1, 100)])) for i in range(n_p) for a, b in [pt()]]
    srcs = [dict(id=f"s{i}", lon=a, lat=b) for i in range(n_s) for a, b in [pt()]]
    ids = rng.sample(["a", "b", "c", "aa", "ab", "b1", "c10", "c2", "z", "x9", "m"], n_c)
    cands = [dict(id=i, lon=a, lat=b, cost=rng.choice([1, 100, 100, rng.randint(1, 1000)])) for i in ids for a, b in [pt()]]
    tot = sum(c["cost"] for c in cands)
    budget = rng.choice([0, tot, tot // 2, rng.randint(0, max(1, tot))])
    ms = rng.randint(0, 5)
    rad = rng.choice([100, 300, 800])
    req = rng.sample(ids, min(len(ids), rng.choice([0, 0, 1, 2])))
    rest = [i for i in ids if i not in req]
    exc = rng.sample(rest, min(len(rest), rng.choice([0, 0, 1, 2])))
    return pts, srcs, cands, rad, budget, ms, req, exc

def _main():
  pass
if __name__ == '__main__':
    rng = random.Random(12345)
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    bad = 0; nopt = 0; ninf = 0
    posthoc_viol = []
    for t in range(N):
        pts, srcs, cands, rad, budget, ms, req, exc = gen(rng)
        pr = metric.Problem(pts, srcs, cands, rad)
        r = exact.optimize(pr, budget, ms, req, exc)
        plans = brute(sorted(pts, key=lambda p: p["id"]), srcs, cands, rad, budget, ms, req, exc)
        if not plans:
            if r["status"] != "infeasible":
                bad += 1; print("EXPECTED infeasible", t, r["status"])
            ninf += 1
            continue
        nopt += 1
        if r["status"] != "optimal" or r["feasible_count"] != len(plans):
            bad += 1; print("status/count", t, r["status"], r["feasible_count"], len(plans)); continue
        for k in ("mean", "minimax", "coverage"):
            b = min(plans, key=lambda p: p["k"][k])
            g = r["objectives"][k]
            got = (g["selected_ids"], g["cost"], g["unknown_count"], g["weighted_sum_mm"], g["max_mm"], g["covered_weight"])
            exp = (b["ids"], b["cost"], b["unk"], b["ws"], b["mx"], b["cov"])
            if got != exp:
                bad += 1; print("MISMATCH", t, k, got, exp)
            # greedy never better + posthoc claim
            for fn in (greedy.greedy_key, greedy.greedy_ratio):
                gr = fn(pr, k, budget, ms, req, exc)
                if gr["status"] != "heuristic":
                    bad += 1; print("greedy status", t, gr); continue
                p = gr["plan"]
                if p["cost"] > budget or len(p["selected_ids"]) > ms or not set(req) <= set(p["selected_ids"]) or set(exc) & set(p["selected_ids"]):
                    bad += 1; print("greedy infeasible", t, k, fn.__name__, p)
                x = gap.gap(k, p, g)
                if x["greedy_better_than_exact"]:
                    bad += 1; print("greedy better", t)
                if not req and len(g["selected_ids"]) <= 1 and not x["hit"]:
                    posthoc_viol.append((t, k, fn.__name__, g["selected_ids"], p["selected_ids"]))
                if x["abs"] is not None and x["abs"] < 0:
                    bad += 1; print("neg abs", t, k)
        if r["pareto"] != pareto(plans):
            bad += 1; print("PARETO", t, r["pareto"], pareto(plans))
    print(f"N={N} optimal={nopt} infeasible={ninf} bad={bad} posthoc_violations={len(posthoc_viol)}")
    print(posthoc_viol[:5])
