"""K05 round 10: independent Python reference of the CONTRACT comparison (school-access-case-v1), stdlib only.
Does not use plan.js or school-compare.js. Same documented policies as the adapter:
  * targets = schools with access_eligibility != known_restricted (unknown eligibility included, flagged);
  * before = nearest known (status ok) target among schools; after = among schools + selected candidates;
    ties: distance, then school before candidate, then id;
  * row status: unknown (no known path) | partial (known, but some used target has no known path) | ok;
  * delta = after - before (null if either unknown);
  * metrics per CONTRACT; threshold in integer mm (round(threshold_m * 1000)); share denominator = all points;
  * default choice: min (unknown_count, sum_distance_mm, max_distance_mm, sorted ids; empty first);
    minimax (separate objective): (unknown_count, max_distance_mm, sum_distance_mm, ids).
"""
from itertools import combinations


def plan_rows(case, matrix, ids):
    st = {(e["origin_id"], e["target_id"]): e for e in matrix["entries"]}
    schools = [s for s in case["schools"] if s["access_eligibility"] != "known_restricted"]
    unk_elig = {s["id"] for s in schools if s["access_eligibility"] == "unknown"}
    rows = []
    for o in sorted(case["origins"], key=lambda x: x["id"]):
        def best(targets):
            known = [(st[(o["id"], t)]["distance_mm"], rank, t) for t, rank in targets if st[(o["id"], t)]["status"] == "ok"]
            return min(known) if known else None
        tb = [(s["id"], 0) for s in schools]
        ta = tb + [(c, 1) for c in ids]
        b, a = best(tb), best(ta)
        unknown_targets = sorted(t for t, _ in ta if st[(o["id"], t)]["status"] != "ok")
        rows.append({"origin_id": o["id"], "before_mm": b[0] if b else None, "after_mm": a[0] if a else None,
                     "delta_mm": a[0] - b[0] if a and b else None,
                     "status": "unknown" if a is None else ("partial" if unknown_targets else "ok"),
                     "nearest_target_id": a[2] if a else None,
                     "nearest_access_eligibility_unknown": bool(a and a[2] in unk_elig)})
    return rows


def metrics(rows, thr_mm):
    known = [r["after_mm"] for r in rows if r["after_mm"] is not None]
    within = sum(1 for d in known if d <= thr_mm)
    return {"total_origins": len(rows), "known_count": len(known), "unknown_count": len(rows) - len(known),
            "sum_distance_mm": sum(known), "mean_distance_mm": sum(known) / len(known) if known else None,
            "max_distance_mm": max(known) if known else None, "within_threshold_count": within,
            "within_threshold_share_of_all_points": within / len(rows) if rows else None}


def compare(case, matrix):
    thr = round(case["parameters"]["threshold_m"] * 1000)
    k = case["parameters"]["max_new_objects"]
    cids = sorted(c["id"] for c in case["candidates"])
    sets = [list(s) for n in range(0, k + 1) for s in combinations(cids, n)]
    evald = []
    for s in sets:
        rows = plan_rows(case, matrix, s)
        evald.append((s, rows, metrics(rows, thr)))
    mx = lambda m: -1 if m["max_distance_mm"] is None else m["max_distance_mm"]
    lex = min(evald, key=lambda t: (t[2]["unknown_count"], t[2]["sum_distance_mm"], mx(t[2]), t[0]))
    mm = min(evald, key=lambda t: (t[2]["unknown_count"], mx(t[2]), t[2]["sum_distance_mm"], t[0]))
    out = {"current": evald[0]}
    for c in case["selected_candidate_ids"]:
        out["candidate:" + c] = next(t for t in evald if t[0] == [c]) if k >= 1 else (lambda r: ([c], r, metrics(r, thr)))(plan_rows(case, matrix, [c]))
    out["auto:contract-lex"], out["auto:minimax"] = lex, mm
    return {pid: {"selected_candidate_ids": t[0], "rows": t[1], "metrics": t[2]} for pid, t in out.items()}, len(sets)
