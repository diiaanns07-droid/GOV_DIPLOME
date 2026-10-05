"""K06: independent checks on the REAL Astana AVL-derived trips (Zenodo 15769359 via Bussure mirror 0356bb5).
Read-only on inputs; stdlib only. Writes K06_OUT/k06_checks.json.
C1 vehicle overlap: same vehicle_id with a trip starting before its previous trip ended (reconstruction artifact signal).
C2 pooled vs within-day CV: AST-A06 pools headways across 55 days; between-day shifts in mean headway inflate pooled CV.
   Here CV is computed per (route, dir, day, band) and the median is reported, same cleaning as R1b 'clean_weekday'.
C3 coverage facts: days, weekday/weekend split, gaps in calendar.
"""
import csv, os, json, collections, statistics as st, datetime
B = os.environ["BUSSURE_GTFS"]; OUT = os.environ["K06_OUT"]
routes = {r["route_id"]: r["route_short_name"] for r in csv.DictReader(open(f"{B}/routes.txt", encoding="cp1251"), delimiter="\t")}
trips = list(csv.DictReader(open(f"{B}/trips.txt"), delimiter="\t"))
def sec(t): h, m, s = t.split(":"); return int(h)*3600 + int(m)*60 + float(s)
# C1
byveh = collections.defaultdict(list)
for t in trips:
    a, b = sec(t["start_time"]), sec(t["end_time"]); b = b + 86400 if b < a else b
    byveh[(t["vehicle_id"], t["service_id"])].append((a, b, routes[t["route_id"]]))
overlap = 0; overlap_gt5 = 0; pairs = 0; route_switch = 0
for v in byveh.values():
    v.sort()
    for (a1, b1, r1), (a2, b2, r2) in zip(v, v[1:]):
        pairs += 1; route_switch += r1 != r2
        if a2 < b1: overlap += 1; overlap_gt5 += (b1 - a2) > 300
c1 = {"vehicle_day_consecutive_pairs": pairs, "next_trip_starts_before_prev_end": overlap,
      "share": round(overlap/pairs, 4), "overlap_gt_5min": overlap_gt5, "vehicles": len({k[0] for k in byveh}),
      "consecutive_pairs_switching_route": route_switch}
# C2
g = collections.defaultdict(list)
for t in trips: g[(routes[t["route_id"]], t["direction_id"], t["service_id"][8:])].append(sec(t["start_time"]))
med = collections.defaultdict(list)
for (rt, d, day), v in g.items(): med[(rt, d)].append(len(v))
med = {k: st.median(v) for k, v in med.items()}
BANDS = {"06-09": (6, 9), "09-16": (9, 16), "16-19": (16, 19)}
pooled = collections.defaultdict(list); daily = collections.defaultdict(list)
for (rt, d, day), v in g.items():
    if datetime.date.fromisoformat(day).weekday() >= 5 or len(v) < 0.5*med[(rt, d)]: continue
    v = sorted(set(round(x) for x in v)); per = collections.defaultdict(list)
    for a, b in zip(v, v[1:]):
        h = b - a
        if not (60 <= h <= 3*3600): continue
        hb = [k for k, (x, y) in BANDS.items() if x <= (a//3600) % 24 < y]
        if hb: per[hb[0]].append(h); pooled[(rt, d, hb[0])].append(h)
    for band, hs in per.items():
        if len(hs) >= 5: daily[(rt, d, band)].append(st.pstdev(hs)/st.mean(hs))
c2 = []
for k in sorted(pooled):
    v = pooled[k]; c2.append({"key": "/".join(k), "pooled_cv": round(st.pstdev(v)/st.mean(v), 2),
        "median_within_day_cv": round(st.median(daily[k]), 2) if daily[k] else None, "days_used": len(daily[k])})
# C3
days = sorted({t["service_id"][8:] for t in trips}); d0, d1 = (datetime.date.fromisoformat(x) for x in (days[0], days[-1]))
c3 = {"first_day": days[0], "last_day": days[-1], "days_present": len(days), "days_in_range": (d1-d0).days + 1,
      "weekend_days": sum(datetime.date.fromisoformat(x).weekday() >= 5 for x in days),
      "trips": len(trips), "routes": sorted(set(routes.values()))}
res = {"C1_vehicle_overlap": c1, "C2_pooled_vs_within_day_cv": c2,
       "C2_summary": {"pooled_median": st.median(x["pooled_cv"] for x in c2),
                      "within_day_median": st.median(x["median_within_day_cv"] for x in c2 if x["median_within_day_cv"] is not None)},
       "C3_coverage": c3}
json.dump(res, open(f"{OUT}/k06_checks.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in res.items() if k != "C2_pooled_vs_within_day_cv"}, ensure_ascii=False, indent=1))
for x in c2: print(x)
