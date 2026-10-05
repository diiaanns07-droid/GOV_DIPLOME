import sys, random, math
from fractions import Fraction
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09")
sys.path.insert(0, ".")
from k09plan import metric, greedy
import fuzz_exact as F   # reuses gen() and mm(); module runs its own loop on import -> guard below

def evalp(points, sources, cmap, ids, rad):
    after = []
    for p in points:
        ds = [F.mm((p["lon"], p["lat"]), (o["lon"], o["lat"])) for o in list(sources) + [cmap[i] for i in ids]]
        after.append(min(ds) if ds else None)
    unk = sum(v is None for v in after)
    ws = sum(p["weight"] * v for p, v in zip(points, after) if v is not None)
    mx = max(after) if unk == 0 else None
    cov = sum(p["weight"] for p, v in zip(points, after) if v is not None and v <= rad * 1000)
    cost = sum(cmap[i]["cost"] for i in ids)
    M = math.inf if mx is None else mx
    s = sorted(ids)
    return dict(ids=s, unk=unk, ws=ws, mx=mx, cov=cov, cost=cost,
                k={"mean": (unk, ws, M, cost, s), "minimax": (unk, M, ws, cost, s), "coverage": (-cov, unk, ws, M, cost, s)})

def g1(points, sources, cands, rad, budget, ms, req, exc, obj):
    cmap = {c["id"]: c for c in cands}
    if len(req) > ms or sum(cmap[i]["cost"] for i in req) > budget: return None
    sel = list(req); cur = evalp(points, sources, cmap, sel, rad)
    while len(sel) < ms:
        opts = [evalp(points, sources, cmap, sel + [c], rad) for c in cmap if c not in sel and c not in exc
                and cur["cost"] + cmap[c]["cost"] <= budget]
        if not opts: break
        b = min(opts, key=lambda m: m["k"][obj])
        if not b["k"][obj] < cur["k"][obj]: break
        sel = b["ids"]; cur = b
    return cur["ids"]

def prim(obj, m):
    if obj == "mean": return -m["ws"]
    if obj == "minimax": return None if m["mx"] is None else -m["mx"]
    return m["cov"]

def g2(points, sources, cands, rad, budget, ms, req, exc, obj):
    cmap = {c["id"]: c for c in cands}
    if len(req) > ms or sum(cmap[i]["cost"] for i in req) > budget: return None
    sel = list(req); cur = evalp(points, sources, cmap, sel, rad)
    while len(sel) < ms:
        bu, br = None, None
        for c in sorted(cmap):
            if c in sel or c in exc or cur["cost"] + cmap[c]["cost"] > budget: continue
            m = evalp(points, sources, cmap, sel + [c], rad)
            du = cur["unk"] - m["unk"]
            if du > 0:
                t = (-du, cmap[c]["cost"], c)
                if bu is None or t < bu[0]: bu = (t, c, m)
                continue
            a, b = prim(obj, cur), prim(obj, m)
            if a is None or b is None or b - a <= 0: continue
            r = Fraction(b - a, cmap[c]["cost"])
            if br is None or r > br[0]: br = (r, c, m)
        pk = bu or br
        if pk is None: break
        sel = sel + [pk[1]]; cur = pk[2]
    base_cost = sum(cmap[i]["cost"] for i in req)
    singles = [evalp(points, sources, cmap, list(req) + [c], rad) for c in sorted(cmap)
               if c not in req and c not in exc and base_cost + cmap[c]["cost"] <= budget] if len(req) < ms else []
    if singles:
        s = min(singles, key=lambda m: m["k"][obj])
        if s["k"][obj] < cur["k"][obj]: return s["ids"]
    return cur["ids"]

rng = random.Random(777)
bad = n = 0
for t in range(2500):
    pts, srcs, cands, rad, budget, ms, req, exc = F.gen(rng)
    pts_sorted = sorted(pts, key=lambda p: p["id"])
    pr = metric.Problem(pts, srcs, cands, rad)
    for obj in ("mean", "minimax", "coverage"):
        for mine, theirs in ((g1, greedy.greedy_key), (g2, greedy.greedy_ratio)):
            a = mine(pts_sorted, srcs, cands, rad, budget, ms, req, exc, obj)
            r = theirs(pr, obj, budget, ms, req, exc)
            b = None if r["status"] == "infeasible" else r["plan"]["selected_ids"]
            n += 1
            if a != b:
                bad += 1
                if bad < 6: print("DIFF", t, obj, theirs.__name__, a, b)
print("greedy comparisons", n, "diffs", bad)
