"""K10 round 10: tiny reference of CONTRACT compareCase for the geodesic method (smoke for the data package only).

Not the product engine: BUILD's compareCase is authoritative, K06 checks it independently. This only shows that the
Astana package yields a non-degenerate comparison and gives numbers to cross-check. Distances: spherical formula of
k10case.haversine_m (BUILD may use an ellipsoid; differences of a few metres are expected), rounded to integer mm.
Targets: schools with access_eligibility = known_public (other schools are listed as possible incompleteness).

    python research/round-10-results/K10/scripts/reference_compare.py research/round-10-results/K10/package/astana.case.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import k10case as KC  # noqa: E402


def plan(case, sel):
    known = [s for s in case["schools"] if s["access_eligibility"] == "known_public"]
    cand = [c for c in case["candidates"] if c["id"] in sel]
    thr = case["parameters"]["threshold_m"] * 1000
    rows = []
    for o in sorted(case["origins"], key=lambda r: r["id"]):
        def nearest(ts):
            return min(((int(round(KC.haversine_m(o["lon"], o["lat"], t["lon"], t["lat"]) * 1000)), t["id"]) for t in ts), default=(None, None))
        b, _ = nearest(known)
        a, tid = nearest(known + cand)
        rows.append({"origin_id": o["id"], "before_mm": b, "after_mm": a, "delta_mm": None if a is None or b is None else a - b, "nearest_target_id": tid})
    known_rows = [r for r in rows if r["after_mm"] is not None]
    n = len(rows)
    m = {"total_origins": n, "known_count": len(known_rows), "unknown_count": n - len(known_rows),
         "sum_distance_mm": sum(r["after_mm"] for r in known_rows), "mean_distance_mm": (sum(r["after_mm"] for r in known_rows) // len(known_rows)) if known_rows else None,
         "max_distance_mm": max((r["after_mm"] for r in known_rows), default=None), "within_threshold_count": sum(1 for r in known_rows if r["after_mm"] <= thr)}
    m["within_threshold_share_of_all_points"] = None if n == 0 else round(m["within_threshold_count"] / n, 4)
    return {"selected_candidate_ids": sel, "metrics": m, "improved_origins": sum(1 for r in rows if r["delta_mm"] and r["delta_mm"] < 0), "rows": rows}


def main(path):
    case = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {"kind": "K10 reference smoke (geodesic, spherical), not the product engine", "case_digest_k10": KC.case_digest_k10(case),
           "possible_incompleteness": sorted(s["id"] for s in case["schools"] if s["access_eligibility"] == "unknown"),
           "plans": [plan(case, [])] + [plan(case, [c["id"]]) for c in sorted(case["candidates"], key=lambda c: c["id"])]}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
