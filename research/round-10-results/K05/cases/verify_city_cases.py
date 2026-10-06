"""K05 r10: independent verification of out/<city>/compare.json:
  (1) every geodesic matrix cell recomputed with an independent Python haversine (R = 6371008.8, clamp, floor(x*1000+0.5));
  (2) every plan (rows + metrics + auto choices) recomputed by ref/school_compare_ref.py (no plan.js).
  python3 cases/verify_city_cases.py [out]"""
import json, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "ref"))
import school_compare_ref as R


def hav_mm(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return math.floor(2 * 6371008.8 * math.asin(math.sqrt(min(1.0, max(0.0, a)))) * 1000 + 0.5)


out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "out")
bad = 0
for city in ("shymkent", "astana"):
    c = json.load(open(os.path.join(out, city, "case.json"), encoding="utf-8"))
    m = json.load(open(os.path.join(out, city, "matrix.json"), encoding="utf-8"))
    js = json.load(open(os.path.join(out, city, "compare.json"), encoding="utf-8"))
    pos = {e["id"]: e for e in c["schools"] + c["origins"] + c["candidates"]}
    cell = sum(1 for e in m["entries"] if e["distance_mm"] != hav_mm(pos[e["origin_id"]]["lon"], pos[e["origin_id"]]["lat"], pos[e["target_id"]]["lon"], pos[e["target_id"]]["lat"]))
    plans, n = R.compare(c, m)
    mism = []
    for pid, rp in plans.items():
        p = next(x for x in js["plans"] if x["plan_id"] == pid)
        if p["selected_candidate_ids"] != rp["selected_candidate_ids"]:
            mism.append(pid + ":ids")
        for k, v in rp["metrics"].items():
            if (v is None) != (p["metrics"][k] is None) or (v is not None and abs(v - p["metrics"][k]) > 1e-9):
                mism.append(f"{pid}:{k}")
        jr = {r["origin_id"]: r for r in p["rows"]}
        for r in rp["rows"]:
            for f in ("before_mm", "after_mm", "delta_mm", "status", "nearest_target_id"):
                if jr[r["origin_id"]][f] != r[f]:
                    mism.append(f"{pid}:{r['origin_id']}:{f}")
    print(f"{city}: matrix cells {len(m['entries'])}, haversine mismatches {cell}; plans {len(plans)}, ref mismatches {len(mism)} {mism[:5]}")
    bad += cell + len(mism)
sys.exit(1 if bad else 0)
