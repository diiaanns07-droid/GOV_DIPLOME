"""AST-A06 R1: REAL DATA (open Astana bus dataset, Zenodo 15769359 via mirror; CC BY 4.0 per mirror README).
Inputs : bussure/datasets/astana/gtfs_data/{trips,routes,stops,calendar_dates}.txt (tab-separated)
         stupits/data/astana_districts.geojson (OSM boundaries, snapshot 2026-09-22, via project repo)
Outputs: ast/r1/*.json, *.csv  (aggregates only; no personal data — vehicle_id is a fleet id, kept out of outputs)
Headways are measured between consecutive trip start_time values of the same route+direction+service day.
start_time = first recorded departure of a trip (reconstructed from GPS per dataset README) -> headway at the terminus,
not at every stop (stop_times.txt unavailable: Git LFS host blocked).
"""
import csv, json, os, statistics as st, collections, math
BASE = "/home/claude/bussure/datasets/astana/gtfs_data"
OUT = "/home/claude/ast/r1"; os.makedirs(OUT, exist_ok=True)
def tsv(name, enc="utf-8"):
    with open(f"{BASE}/{name}", encoding=enc, errors="replace") as f:
        return list(csv.DictReader(f, delimiter="\t"))
routes = {r["route_id"]: r for r in tsv("routes.txt", "cp1251")}
trips = tsv("trips.txt"); stops = tsv("stops.txt")
def sec(t):
    h, m, s = t.split(":"); return int(h)*3600 + int(m)*60 + float(s)
q = collections.Counter()
rows = []
for t in trips:
    try:
        a, b = sec(t["start_time"]), sec(t["end_time"])
    except Exception:
        q["bad_time"] += 1; continue
    if b < a: b += 86400; q["crosses_midnight"] += 1
    rows.append({"route": routes[t["route_id"]]["route_short_name"], "dir": t["direction_id"],
                 "day": t["service_id"].replace("service_", ""), "start": a, "dur": b - a})
q["trips_ok"] = len(rows)
# ---- data quality
durs = [r["dur"] for r in rows]
q["dur_le_0"] = sum(d <= 0 for d in durs); q["dur_gt_4h"] = sum(d > 4*3600 for d in durs)
dup = collections.Counter((r["route"], r["dir"], r["day"], round(r["start"])) for r in rows)
q["duplicate_starts"] = sum(c - 1 for c in dup.values() if c > 1)
# ---- headways
groups = collections.defaultdict(list)
for r in rows: groups[(r["route"], r["dir"], r["day"])].append(r["start"])
BANDS = [("06-09", 6, 9), ("09-16", 9, 16), ("16-19", 16, 19), ("19-23", 19, 23)]
def band(s):
    h = (s // 3600) % 24
    for name, a, b in BANDS:
        if a <= h < b: return name
    return "other"
hw = collections.defaultdict(list)            # (route, dir, band) -> headways (s)
per_day_n = collections.defaultdict(list)     # (route, dir) -> trips per day
for (route, d, day), starts in groups.items():
    starts.sort(); per_day_n[(route, d)].append(len(starts))
    for x, y in zip(starts, starts[1:]):
        h = y - x
        if 0 < h <= 3*3600: hw[(route, d, band(x))].append(h)   # drop overnight gaps
def pct(v, p):
    v = sorted(v); k = (len(v)-1)*p; f = math.floor(k); c = math.ceil(k)
    return v[f] if f == c else v[f] + (v[c]-v[f])*(k-f)
reg = []
for (route, d, b), v in sorted(hw.items()):
    if b == "other" or len(v) < 30: continue
    m = st.mean(v); sd = st.pstdev(v); cv = sd/m
    reg.append({"route": route, "direction_id": d, "band": b, "n_headways": len(v),
                "mean_headway_min": round(m/60, 2), "median_headway_min": round(pct(v, .5)/60, 2),
                "p90_headway_min": round(pct(v, .9)/60, 2), "cv": round(cv, 3),
                "wait_if_regular_min": round(m/2/60, 2),                    # H/2
                "wait_random_arrival_min": round(m/2*(1+cv**2)/60, 2),      # E[H]/2*(1+CV^2) (assumption)
                "share_headway_gt_2x_mean": round(sum(h > 2*m for h in v)/len(v), 3)})
# ---- trip duration variability by band (in-vehicle + layover proxy; includes traffic effect, not separable)
td = collections.defaultdict(list)
for r in rows:
    if 0 < r["dur"] <= 4*3600: td[(r["route"], r["dir"], band(r["start"]))].append(r["dur"])
dur = []
for (route, d, b), v in sorted(td.items()):
    if b == "other" or len(v) < 30: continue
    dur.append({"route": route, "direction_id": d, "band": b, "n": len(v), "p10_min": round(pct(v, .1)/60, 1),
                "p50_min": round(pct(v, .5)/60, 1), "p90_min": round(pct(v, .9)/60, 1),
                "p90_over_p50": round(pct(v, .9)/pct(v, .5), 3)})
# ---- stops by district (ray casting on OSM polygons)
gj = json.load(open("/home/claude/stupits/data/astana_districts.geojson"))
def in_ring(x, y, ring):
    ins = False; j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]; xj, yj = ring[j][:2]
        if (yi > y) != (yj > y) and x < (xj - xi)*(y - yi)/(yj - yi + 1e-15) + xi: ins = not ins
        j = i
    return ins
def in_geom(x, y, g):
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    return any(in_ring(x, y, p[0]) and not any(in_ring(x, y, h) for h in p[1:]) for p in polys)
by_d = collections.Counter()
for s in stops:
    x, y = float(s["stop_lon"]), float(s["stop_lat"])
    hit = [f["properties"]["name"] for f in gj["features"] if in_geom(x, y, f["geometry"])]
    by_d[hit[0] if hit else "вне 6 районов OSM"] += 1
days = sorted({r["day"] for r in rows})
summary = {"quality": dict(q), "service_days": [days[0], days[-1], len(days)],
           "routes": {r["route_short_name"]: r["route_long_name"] for r in routes.values()},
           "trips_per_day_mean": {f"{k[0]}/dir{k[1]}": round(st.mean(v), 1) for k, v in sorted(per_day_n.items())},
           "stops_by_osm_district": dict(by_d)}
json.dump({"summary": summary, "regularity": reg, "trip_duration": dur}, open(f"{OUT}/results.json", "w"), ensure_ascii=False, indent=1)
for name, data in (("regularity.csv", reg), ("trip_duration.csv", dur)):
    with open(f"{OUT}/{name}", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
print(json.dumps(summary, ensure_ascii=False, indent=1))
print("route dir band n meanH cv waitReg waitRand >2x")
for r in reg: print(r["route"], r["direction_id"], r["band"], r["n_headways"], r["mean_headway_min"], r["cv"], r["wait_if_regular_min"], r["wait_random_arrival_min"], r["share_headway_gt_2x_mean"])
print("route dir band n p50 p90 ratio")
for r in dur: print(r["route"], r["direction_id"], r["band"], r["n"], r["p50_min"], r["p90_min"], r["p90_over_p50"])
