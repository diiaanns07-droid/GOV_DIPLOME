"""K05 round 10: SYNTHETIC hand-calculated school-access cases (integer mm matrices written by hand) with expected
values computed BY HAND in this file (not by any implementation). Output: hand_cases.json.
  python3 make_hand_cases.py
"""
import json, os

BB = [69.59, 42.30, 69.62, 42.33]
SRC = [{"id": "src:synthetic", "url": None, "publisher": "K05 test", "title": "synthetic hand fixture", "retrieved_at": None,
        "verification_status": "not_fetched", "license": "unknown"}]


def ent(i, lon, lat, kind="synthetic", **kw):
    e = {"id": i, "label": i, "lon": lon, "lat": lat, "kind": kind, "source_ids": ["src:synthetic"], "field_provenance": {}, "qa": []}
    e.update(kw)
    return e


def school(i, elig="known_public", lon=69.60, lat=42.31):
    return ent(i, lon, lat, category="school", access_eligibility=elig, capacity=None, capacity_source_ids=[])


def cand(i, lon=69.605, lat=42.315, cost=None):
    return ent(i, lon, lat, kind="hypothesis", cost=cost, land_status="unknown")


def case(cid, schools, origins, cands, sel, thr=1.0, k=1, method="geodesic", policy=None):
    return {"schema_version": "school-access-case-v1", "case_id": cid, "city_id": "shymkent", "title": cid, "bbox": BB,
            "snapshot_id": "synthetic-hand-v1", "sources": SRC, "schools": schools, "origins": [ent(o, 69.60 + 0.001 * n, 42.31) for n, o in enumerate(origins)],
            "candidates": cands, "selected_candidate_ids": sel,
            "parameters": {"distance_method": method, "routing_policy_id": policy, "threshold_m": thr, "max_new_objects": k},
            "model_assumptions": ["SYNTHETIC hand fixture: numbers written by hand, not a city"]}


def matrix(case_, table, method="geodesic", policy=None):
    """table: {origin: {target: mm | status-string}}"""
    out = []
    for o, row in table.items():
        for t, v in row.items():
            ok = isinstance(v, int)
            out.append({"origin_id": o, "target_id": t, "distance_mm": v if ok else None, "status": "ok" if ok else v,
                        "method": method, "policy_id": policy, "route_edge_ids": [], "geometry": None, "assumptions": []})
    return {"method": method, "policy_id": policy, "entries": out}


cases = []

# H1: unknown paths, unknown-eligibility school, restricted school ignored. threshold 1 m = 1000 mm.
H1 = case("H1_unknowns_restricted", [school("S1"), school("S2", "unknown"), school("S3", "known_restricted")],
          ["O1", "O2", "O3"], [cand("A"), cand("B")], ["A", "B"])
H1m = matrix(H1, {"O1": {"S1": 1000, "S2": 3000, "S3": 100, "A": 400, "B": 2000},
                  "O2": {"S1": 2500, "S2": "disconnected", "S3": 50, "A": 2600, "B": 500},
                  "O3": {"S1": "outside_coverage", "S2": "unsnappable", "S3": 10, "A": "access_unknown", "B": 900}})
cases.append({"case": H1, "matrix": H1m, "expected": {
    # current: O1 1000(S1) ok; O2 2500(S1) partial (S2 unknown); O3 unknown. sum 3500 mean 1750 max 2500; within<=1000: O1
    "current": {"ids": [], "after": {"O1": 1000, "O2": 2500, "O3": None}, "status": {"O1": "ok", "O2": "partial", "O3": "unknown"},
                "metrics": [3, 2, 1, 3500, 1750.0, 2500, 1, 1 / 3]},
    # A: O1 400(A); O2 2500(S1) partial; O3 unknown. sum 2900 mean 1450 max 2500 within 1
    "candidate:A": {"ids": ["A"], "after": {"O1": 400, "O2": 2500, "O3": None}, "metrics": [3, 2, 1, 2900, 1450.0, 2500, 1, 1 / 3]},
    # B: O1 1000(S1); O2 500(B); O3 900(B) partial (S1,S2 unknown). sum 2400 mean 800 max 1000 within 3
    "candidate:B": {"ids": ["B"], "after": {"O1": 1000, "O2": 500, "O3": 900}, "status": {"O3": "partial"},
                    "delta": {"O1": 0, "O2": -2000, "O3": None}, "metrics": [3, 3, 0, 2400, 800.0, 1000, 3, 1.0]},
    "auto:contract-lex": {"ids": ["B"]}, "auto:minimax": {"ids": ["B"]}}})

# H2: all known; contract rule prefers A (sum), minimax prefers B (worst path). threshold 3 m.
H2 = case("H2_lex_vs_minimax", [school("S1")], ["O1", "O2", "O3"], [cand("A"), cand("B")], ["A", "B"], thr=3.0)
H2m = matrix(H2, {"O1": {"S1": 5000, "A": 100, "B": 3000}, "O2": {"S1": 5000, "A": 4000, "B": 3000}, "O3": {"S1": 5000, "A": 4500, "B": 3000}})
cases.append({"case": H2, "matrix": H2m, "expected": {
    "current": {"ids": [], "metrics": [3, 3, 0, 15000, 5000.0, 5000, 0, 0.0]},
    "candidate:A": {"ids": ["A"], "metrics": [3, 3, 0, 8600, 8600 / 3, 4500, 1, 1 / 3]},
    "candidate:B": {"ids": ["B"], "metrics": [3, 3, 0, 9000, 3000.0, 3000, 3, 1.0]},
    "auto:contract-lex": {"ids": ["A"]}, "auto:minimax": {"ids": ["B"]}}})

# H3: ties. A1/A2 identical distances -> A1 by ID; C never improves -> empty preferred over C on equal key;
# candidate equal to the school distance keeps the school as nearest.
H3 = case("H3_ties", [school("S1")], ["O1", "O2"], [cand("A2"), cand("A1"), cand("C")], ["C", "A2"], thr=1.0)
H3m = matrix(H3, {"O1": {"S1": 2000, "A2": 1000, "A1": 1000, "C": 2000}, "O2": {"S1": 1500, "A2": 1500, "A1": 1500, "C": 1500}})
cases.append({"case": H3, "matrix": H3m, "expected": {
    "current": {"ids": [], "metrics": [2, 2, 0, 3500, 1750.0, 2000, 0, 0.0]},
    "candidate:C": {"ids": ["C"], "after": {"O1": 2000, "O2": 1500}, "nearest": {"O1": "S1", "O2": "S1"}, "metrics": [2, 2, 0, 3500, 1750.0, 2000, 0, 0.0]},
    "candidate:A2": {"ids": ["A2"], "nearest": {"O1": "A2", "O2": "S1"}, "metrics": [2, 2, 0, 2500, 1250.0, 1500, 1, 0.5]},
    "auto:contract-lex": {"ids": ["A1"]}, "auto:minimax": {"ids": ["A1"]}}})

# H4: no improvement possible -> the empty set wins (no extra object on a tie).
H4 = case("H4_no_gain_empty_wins", [school("S1")], ["O1"], [cand("B")], ["B"], thr=1.0)
H4m = matrix(H4, {"O1": {"S1": 300, "B": 900}})
cases.append({"case": H4, "matrix": H4m, "expected": {"auto:contract-lex": {"ids": []}, "auto:minimax": {"ids": []},
                                                     "candidate:B": {"ids": ["B"], "metrics": [1, 1, 0, 300, 300.0, 300, 1, 1.0]}}})

# H5: zero origins -> empty comparison; shares/means null; auto = empty.
H5 = case("H5_no_origins", [school("S1")], [], [cand("A")], ["A"])
H5m = matrix(H5, {})
cases.append({"case": H5, "matrix": H5m, "expected": {"current": {"ids": [], "metrics": [0, 0, 0, 0, None, None, 0, None]},
                                                     "auto:contract-lex": {"ids": []}}})

# H6: no known path anywhere for O1; candidate A creates the only known path -> unknown_count decides first.
H6 = case("H6_unknown_first", [school("S1")], ["O1", "O2"], [cand("A"), cand("B")], ["A", "B"], thr=1.0)
H6m = matrix(H6, {"O1": {"S1": "disconnected", "A": 4000, "B": "disconnected"}, "O2": {"S1": 500, "A": 9000, "B": 100}})
cases.append({"case": H6, "matrix": H6m, "expected": {
    "current": {"ids": [], "metrics": [2, 1, 1, 500, 500.0, 500, 1, 0.5]},
    "candidate:A": {"ids": ["A"], "metrics": [2, 2, 0, 4500, 2250.0, 4000, 1, 0.5]},
    "candidate:B": {"ids": ["B"], "metrics": [2, 1, 1, 100, 100.0, 100, 1, 0.5]},
    "auto:contract-lex": {"ids": ["A"]}, "auto:minimax": {"ids": ["A"]}}})

# H7: pedestrian-v1 with policy; all statuses unknown -> everything unknown, auto empty, mean/max null.
H7 = case("H7_all_unknown_pedestrian", [school("S1")], ["O1", "O2"], [cand("A")], ["A"], method="pedestrian-v1", policy="ped-test-v1")
H7m = matrix(H7, {"O1": {"S1": "disconnected", "A": "unsnappable"}, "O2": {"S1": "outside_coverage", "A": "access_unknown"}},
             method="pedestrian-v1", policy="ped-test-v1")
cases.append({"case": H7, "matrix": H7m, "expected": {"current": {"ids": [], "metrics": [2, 0, 2, 0, None, None, 0, 0.0]},
                                                     "candidate:A": {"ids": ["A"], "metrics": [2, 0, 2, 0, None, None, 0, 0.0]},
                                                     "auto:contract-lex": {"ids": []}}})

FIELDS = ["total_origins", "known_count", "unknown_count", "sum_distance_mm", "mean_distance_mm", "max_distance_mm",
          "within_threshold_count", "within_threshold_share_of_all_points"]
doc = {"schema": "k05-school-hand-cases-v1", "kind": "synthetic", "metric_fields_order": FIELDS,
       "note": "expected values written by hand in make_hand_cases.py; not produced by any implementation", "cases": cases}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_cases.json")
json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(cases), "hand cases ->", out)
