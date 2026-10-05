"""A06 experiment E3 (SYNTHETIC, local metric CRS, NOT Shymkent).
Checks two critical assumptions of the MVP:
 (a) Euclidean 'stop within 400 m' buffers overstate coverage when a barrier (arterial
     without crossings) exists -> pedestrian links must be verified;
 (b) door-to-door time to a facility can be decomposed into walk / wait / ride / transfer
     and reported as a range, and a local change (one added stop) can be diffed.
Waiting model: random passenger arrivals, E[wait] = E[H]/2 * (1 + CV^2)  (classical result;
source not opened in this session -> treat as assumption to verify).
"""
import heapq, json, math, statistics, os
OUT = os.path.dirname(os.path.abspath(__file__)) + "/e3"; os.makedirs(OUT, exist_ok=True)
STEP, N = 200, 21                       # 4 km x 4 km walk grid, 200 m spacing
ART_Y = 2000; CROSS_X = {1000, 3000}     # arterial at y=2000 crossable only at crosswalks
nodes = [(x*STEP, y*STEP) for x in range(N) for y in range(N)]
def nbrs(p):
    x, y = p
    for dx, dy in ((STEP,0),(-STEP,0),(0,STEP),(0,-STEP)):
        q = (x+dx, y+dy)
        if not (0 <= q[0] <= 4000 and 0 <= q[1] <= 4000): continue
        crosses = (min(y, q[1]) < ART_Y < max(y, q[1])) or (dy != 0 and (y == ART_Y or q[1] == ART_Y) and x not in CROSS_X and False)
        yield q, STEP
# barrier: forbid vertical moves that cross y=1000 except at crosswalks; stops on the arterial sit at y=1000
def walk_edges(p):
    x, y = p
    for q, d in nbrs(p):
        if q[0] == x and ((y < ART_Y <= q[1]) or (q[1] <= ART_Y < y)) and x not in CROSS_X and (y != ART_Y and q[1] != ART_Y):
            continue
        if q[0] == x and ((y == ART_Y and q[1] > ART_Y) or (q[1] == ART_Y and y > ART_Y)) and x not in CROSS_X:
            continue  # stops are on the south kerb: going north of the arterial needs a crosswalk
        yield q, d
def dijkstra(src_set):
    dist = {s: 0.0 for s in src_set}; pq = [(0.0, s) for s in src_set]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]: continue
        for v, w in walk_edges(u):
            nd = d + w
            if nd < dist.get(v, 1e18): dist[v] = nd; heapq.heappush(pq, (nd, v))
    return dist
R1 = [(x, ART_Y) for x in (400, 1200, 2000, 2800, 3600)]   # E-W route along arterial
R2 = [(2000, y) for y in (400, 1200, 2000, 2800, 3600)]    # N-S route, transfer at (1000,1000)
POI = (3600, 3600)                                         # e.g. a polyclinic
H = {"R1": 10*60, "R2": 15*60}; BUS_V = 18/3.6; DWELL = 20
def coverage(stops, radius=400):
    net = dijkstra(stops)
    eu = sum(1 for p in nodes if min(math.dist(p, s) for s in stops) <= radius)
    nw = sum(1 for p in nodes if net.get(p, 1e18) <= radius)
    return eu/len(nodes), nw/len(nodes)
def door_to_poi(stops_r1, cv, walk_v):
    """best of walk-only and R1->R2 / R2-only paths; returns per-node total and parts."""
    wait = lambda h: h/2*(1+cv**2)
    egress = dijkstra([POI])                       # walk distance from any node to POI (symmetric grid)
    poi_stop = min(R2, key=lambda s: egress.get(s, 1e18))
    eg = egress[poi_stop]/walk_v
    res = {}
    d_r1 = {s: dijkstra([s]) for s in stops_r1}; d_r2 = {s: dijkstra([s]) for s in R2}
    for p in nodes:
        opts = [{"walk": egress.get(p, 1e18)/walk_v, "wait": 0, "ride": 0, "transfer": 0}]
        for s in R2:   # direct R2
            ride = abs(s[1]-poi_stop[1])/BUS_V + DWELL*abs(s[1]-poi_stop[1])/800
            opts.append({"walk": d_r2[s].get(p,1e18)/walk_v + eg, "wait": wait(H["R2"]), "ride": ride, "transfer": 0})
        for s in stops_r1:  # R1 to transfer stop (1000,1000), then R2
            r1 = abs(s[0]-2000)/BUS_V + DWELL*abs(s[0]-2000)/800
            r2 = abs(2000-poi_stop[1])/BUS_V + DWELL*abs(2000-poi_stop[1])/800
            opts.append({"walk": d_r1[s].get(p,1e18)/walk_v + eg, "wait": wait(H["R1"]), "ride": r1+r2,
                         "transfer": wait(H["R2"]) + 60})   # 60 s transfer walk, assumed
        best = min(opts, key=lambda o: sum(o.values()))
        res[p] = best
    return res
def summarise(stops_r1, label):
    out = {"label": label}
    eu, nw = coverage(stops_r1 + R2); out["coverage_400m_euclid"] = round(eu, 3); out["coverage_400m_network"] = round(nw, 3)
    for name, cv, v in (("optimistic", 0.2, 1.3), ("pessimistic", 0.8, 0.9)):
        r = door_to_poi(stops_r1, cv, v)
        tot = [sum(o.values())/60 for o in r.values()]
        out[name] = {"cv_headway": cv, "walk_speed_mps": v, "median_min": round(statistics.median(tot), 1),
                     "p90_min": round(sorted(tot)[int(0.9*len(tot))], 1),
                     "share_over_30min": round(sum(t > 30 for t in tot)/len(tot), 3),
                     "share_best_by_transit": round(sum(o["ride"] > 0 for o in r.values())/len(r), 3),
                     "mean_parts_min_transit_users": {k: round(statistics.mean(o[k] for o in r.values() if o["ride"] > 0)/60, 1) for k in ("walk","wait","ride","transfer")}}
    return out
base = summarise(R1, "baseline")
alt1 = summarise(R1 + [(3200, ART_Y)], "A1: add stop on R1 at x=3200")
CROSS_X.add(2000)
alt2 = summarise(R1, "A2: add crosswalk at transfer stop x=2000")
res = {"note": "SYNTHETIC. Parameters are illustrative, not calibrated.", "baseline": base, "A1": alt1, "A2": alt2}
json.dump(res, open(f"{OUT}/results.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False))
