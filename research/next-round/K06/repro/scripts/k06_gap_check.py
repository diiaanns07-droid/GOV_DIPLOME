"""K06 C4: gap between end_time of a vehicle's trip and start_time of its next trip (same vehicle, same service day).
If most gaps are ~0 s, trips are segmented back-to-back and 'trip duration' includes terminal layover/dwell, i.e. it is
not pure running time and cannot be read as congestion. REAL data, read-only; writes K06_OUT/k06_gap_check.json."""
import csv, os, json, collections, statistics as st
B = os.environ["BUSSURE_GTFS"]; OUT = os.environ["K06_OUT"]
def sec(t): h, m, s = t.split(":"); return int(h)*3600 + int(m)*60 + float(s)
v = collections.defaultdict(list)
for t in csv.DictReader(open(f"{B}/trips.txt"), delimiter="\t"):
    a, b = sec(t["start_time"]), sec(t["end_time"]); v[(t["vehicle_id"], t["service_id"])].append((a, b + 86400 if b < a else b))
gaps = []
for x in v.values():
    x.sort(); gaps += [n[0] - p[1] for p, n in zip(x, x[1:])]
q = lambda p: sorted(gaps)[int(p*(len(gaps)-1))]
res = {"pairs": len(gaps), "gap_le_10s": sum(g <= 10 for g in gaps), "gap_le_60s": sum(g <= 60 for g in gaps),
       "gap_gt_10min": sum(g > 600 for g in gaps), "p50_s": q(.5), "p90_s": q(.9), "share_le_60s": round(sum(g <= 60 for g in gaps)/len(gaps), 3)}
json.dump(res, open(f"{OUT}/k06_gap_check.json", "w"), indent=1); print(res)
