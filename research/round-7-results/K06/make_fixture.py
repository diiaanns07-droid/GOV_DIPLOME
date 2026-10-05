"""Build fixtures/whatif_fixture.json from a city-evidence BUILD copy (default: base c58a3b2) with expected values
from the oracle AND from the independent chord formula. Usage:
  python3 make_fixture.py --app-root <extracted prototypes/city-evidence> [--out fixtures/whatif_fixture.json]
The fixture is meant for the BUILD to replay with its own implementation (see README, "Как проверить сборку").
"""
import argparse, hashlib, json, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import whatif_oracle as W

TOL_M = 1e-6          # implementation vs oracle, metres (double precision, same formula)
TOL_INDEP_M = 1e-6    # oracle vs independent chord formula at <= 3 km


def js_object(text, var):
    return json.loads(re.search(r"window\." + var + r"\s*=\s*(\{.*\})\s*;\s*$", text, re.S).group(1))


def load(app_root):
    D = js_object(open(os.path.join(app_root, "web", "data.js"), encoding="utf-8").read(), "CITY_EVIDENCE")
    E = js_object(open(os.path.join(app_root, "web", "evidence.js"), encoding="utf-8").read(), "CITY_OBS")
    return D, E


def qa_codes(E, city):
    q = E["cities"][city].get("qa") or {}
    codes = {}
    for g in q.get("colocated") or []:
        for i in g["ids"]:
            codes.setdefault(i, set()).add("COLOCATED")
    for pair in q.get("possible_duplicates") or []:
        for i in ([pair.get("a"), pair.get("b")] if isinstance(pair, dict) else pair):   # {a, b, distance_m, rule}
            codes.setdefault(i, set()).add("POSSIBLE_DUPLICATE")
    for i in (q.get("category_doubt") or {}):
        codes.setdefault(i, set()).add("CATEGORY_DOUBT")
    return {k: sorted(v) for k, v in codes.items()}


def reference_snapshot(city, c, category):
    """K06 reference fingerprint: sha256 of canonical category records + bbox + release + formula parameters.
    The BUILD may define its own; it must be derived from data, never from a file name."""
    recs = sorted([p["id"], p["lon"], p["lat"]] for p in c["places"] if p["group"] == category)
    blob = json.dumps({"city": city, "category": category, "bbox": c["bbox"], "release": c.get("release"),
                       "records": recs, "formula": {"haversine_R_m": W.R_EARTH_M, "clamp": [0, 1]}},
                      sort_keys=True, separators=(",", ":"))
    return "k06ref-sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def rnd_point(rng, bb, pid):
    return {"id": pid, "lon": rng.uniform(bb[0], bb[2]), "lat": rng.uniform(bb[1], bb[3])}


def synthetic_edges():
    """SYNTHETIC records (not city data) for spec edge cases; expected values from the oracle, rejections by name."""
    bb = [71.418372, 51.163033, 71.447, 51.181]
    recs = [{"id": "b", "lon": 71.430, "lat": 51.1702, "group": "school"},
            {"id": "a", "lon": 71.430, "lat": 51.1702, "group": "school"}]           # exact tie (identical coords)
    P = lambda i, lon, lat: {"id": i, "lon": lon, "lat": lat}
    H = lambda lon, lat, cat="school": {"id": "proj1", "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical"}
    S = lambda cat, pts, prop=None: {"schema_version": "city-whatif-v1", "city_id": "astana", "source_snapshot": "synthetic",
                                     "category": cat, "control_points": pts, "proposed_object": prop}
    ok = {"tie_by_id": S("school", [P("cp1", 71.430, 51.1700)]),
          "same_point_zero": S("school", [P("cp1", 71.430, 51.1702)]),
          "project_on_point": S("school", [P("cp1", 71.435, 51.172)], H(71.435, 51.172)),
          "no_records_with_project": S("outpatient_clinic", [P("cp1", 71.435, 51.172)], H(71.436, 51.172, "outpatient_clinic")),
          "no_records_no_project": S("outpatient_clinic", [P("cp1", 71.435, 51.172)])}
    bad = {"zero_points": S("school", []), "eleven_points": S("school", [P(f"cp{i}", 71.43, 51.17) for i in range(11)]),
           "duplicate_id": S("school", [P("cp1", 71.43, 51.17), P("cp1", 71.431, 51.171)]),
           "point_outside_bbox": S("school", [P("cp1", 71.50, 51.17)]),
           "project_outside_bbox": S("school", [P("cp1", 71.43, 51.17)], H(71.60, 51.171)),
           "category_mismatch": S("school", [P("cp1", 71.43, 51.17)], H(71.43, 51.171, "outpatient_clinic")),
           "category_not_in_mvp": S("hospital", [P("cp1", 71.43, 51.17)])}
    return {"kind": "synthetic", "bbox": bb, "records": recs,
            "cases": [{"case": k, "scenario": v, "expected": W.compute(v, recs, bb)} for k, v in ok.items()],
            "must_reject": [{"case": k, "scenario": v} for k, v in bad.items()],
            "must_reject_numbers": ["NaN", "Infinity", "-Infinity", "1e999"],
            "clamp_case": {"a": [0, -74.6], "b": [180, 74.6], "expected_m": W.haversine_m(0, -74.6, 180, 74.6),
                           "note": "unclamped intermediate = 1.0000000000000002; without clamp asin(sqrt(a)) fails"}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-root", required=True)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "whatif_fixture.json"))
    a = ap.parse_args()
    D, E = load(a.app_root)
    man = os.path.join(a.app_root, "_extract_manifest.json")
    commit = json.load(open(man))["commit"] if os.path.exists(man) else None
    rng = random.Random(20261005)
    out = {"schema": "k06-whatif-fixture-v1", "spec": "research/round-7/FEATURE_SPEC.txt @ codex/research-import-2026-10-05 7927fa8",
           "source_build_commit": commit, "formula": {"haversine_R_m": W.R_EARTH_M, "clamp": [0, 1], "input": "[lon, lat]"},
           "tolerance_m": TOL_M, "display_note": "values are unrounded metres; round only for display",
           "cases": []}
    for city in D["city_order"]:
        c = D["cities"][city]; bb = c["bbox"]; qa = qa_codes(E, city)
        for cat in W.CATEGORIES:
            recs = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"]} for p in c["places"]]
            pts = [rnd_point(rng, bb, f"cp{i + 1}") for i in range(10)]
            variants = [("no_project", None),
                        ("project_random", dict(rnd_point(rng, bb, "proj1"), category=cat, kind="hypothetical")),
                        ("project_at_cp1", {"id": "proj1", "lon": pts[0]["lon"], "lat": pts[0]["lat"], "category": cat, "kind": "hypothetical"})]
            for name, prop in variants:
                sc = {"schema_version": "city-whatif-v1", "city_id": city, "source_snapshot": reference_snapshot(city, c, cat),
                      "category": cat, "control_points": pts, "proposed_object": prop}
                rows = W.compute(sc, recs, bb)
                for r, p in zip(rows, pts):
                    if r["nearest_record_id"]:
                        rec = next(x for x in recs if x["id"] == r["nearest_record_id"])
                        r["before_m_independent_chord"] = W.chord_distance_m(p["lon"], p["lat"], rec["lon"], rec["lat"])
                        r["nearest_record_qa"] = qa.get(r["nearest_record_id"], [])
                out["cases"].append({"case": f"{city}/{cat}/{name}", "bbox": bb, "records_in_category":
                                     sum(1 for x in recs if x["group"] == cat), "scenario": sc, "expected": rows})
    out["synthetic_edge_cases"] = synthetic_edges()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(len(out["cases"]), "cases ->", a.out)


if __name__ == "__main__":
    main()
