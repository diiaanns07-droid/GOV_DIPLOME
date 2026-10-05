"""K10 round 7: build city-whatif-v1 fixtures from the real K10 slices inside a BUILD app root. Stdlib only.

Fictional parts: control_points and proposed_object only. Their positions follow rules fixed before computing
(bbox fractions), not tuned to a desired effect; they say nothing about residents or population.
Source records are copied read-only with ids, coordinates as delivered to the UI (web/data.js) and file hashes.

Usage: python3 make_fixtures.py --app-root <extracted prototypes/city-evidence> --commit <build sha> --out <dir>
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import whatif_ref as W  # noqa: E402

CP_FRACTIONS = [("cp1", 0.25, 0.25), ("cp2", 0.50, 0.50), ("cp3", 0.75, 0.75)]
PROPOSED_PLACE = ("proj1", 0.50, 0.50)
PROPOSED_MOVE = (0.05, 0.95)
RULES = {
    "control_points": "bbox fractions (x=lon share, y=lat share): cp1 (0.25,0.25), cp2 (0.50,0.50), cp3 (0.75,0.75); fixed before computing",
    "proposed_object": "placed at bbox fraction (0.50,0.50), then moved to (0.05,0.95), then deleted; fixed before computing",
    "qa_nearest_control_point": "at the coordinate of the largest qa.colocated group holding records of the category; else at the smallest-id QA-flagged record of the category; else not built",
    "tie_break": "equal distances -> smallest id (string order); a proposed object at equal distance does not replace the source record",
    "meaning": "control points are user-chosen places, not homes with known population; delta>0 means a shorter straight-line distance only",
}


def parse_js(raw):
    t = raw.decode("utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def frac(bbox, fx, fy):
    return bbox[0] + fx * (bbox[2] - bbox[0]), bbox[1] + fy * (bbox[3] - bbox[1])


def qa_codes(ev_city):
    out = {}
    for g in ev_city["qa"]["colocated"]:
        for i in g["ids"]:
            out.setdefault(i, set()).add("COLOCATED")
    for d in ev_city["qa"]["possible_duplicates"]:
        for i in (d["a"], d["b"]):
            out.setdefault(i, set()).add("POSSIBLE_DUPLICATE")
    for i in ev_city["qa"]["category_doubt"]:
        out.setdefault(i, set()).add("CATEGORY_DOUBT")
    return {k: sorted(v) for k, v in out.items()}


def scenario(city, snap, cat, cps, prop):
    return {"schema_version": W.SCHEMA, "city_id": city, "source_snapshot": snap, "category": cat,
            "control_points": cps, "proposed_object": prop}


def expected(sc, recs, by_id, qa):
    res = W.compute(sc, recs)
    for r in res["rows"]:
        for key in ("nearest_before_id", "nearest_after_id"):
            rid = r[key]
            if rid in by_id:
                p = by_id[rid]
                r[key.replace("_id", "_source")] = {"kind": "source_record", "name": p.get("name"), "group": p["group"],
                                                     "sources": [{"dataset": s.get("dataset"), "license": s.get("license")} for s in p.get("sources") or []],
                                                     "qa_flags": qa.get(rid, [])}
            elif rid is not None:
                r[key.replace("_id", "_source")] = {"kind": "hypothetical"}
        # all records tied at the minimum (shows the tie-break)
        cp = next(c for c in sc["control_points"] if c["id"] == r["control_point_id"])
        pool = [x for x in recs if x["group"] == sc["category"]]
        if pool and r["before_m"] is not None:
            r["tied_at_before_ids"] = sorted(x["id"] for x in pool if W.haversine_m((cp["lon"], cp["lat"]), (x["lon"], x["lat"])) == r["before_m"])
    return res


def build(app, commit):
    data = parse_js((app / "web" / "data.js").read_bytes())
    ev = parse_js((app / "web" / "evidence.js").read_bytes())
    common_src = {"build_commit": commit, "web_data_js_sha256": hashlib.sha256((app / "web/data.js").read_bytes()).hexdigest(),
                  "web_evidence_js_sha256": hashlib.sha256((app / "web/evidence.js").read_bytes()).hexdigest(),
                  "k10_package": {"branch": "claude/save-work-handoff-j7pc05", "data_commit": "602f0c0b6d5db741d20909082086982b3c812c07"}}
    fixtures, not_built = [], []
    for city in W.CITIES:
        c = data["cities"][city]
        bbox, release = c["bbox"], c["release"]
        src_path = f"inputs/k10/data/{city}/places_social.geojson"
        src_sha = hashlib.sha256((app / src_path).read_bytes()).hexdigest()
        recs = [{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "group": p["group"]} for p in c["places"]]
        by_id = {p["id"]: p for p in c["places"]}
        qa = qa_codes(ev["cities"][city])
        snap, comp = W.snapshot_id(city, release, bbox, src_sha, recs)
        cps = [{"id": i, "lon": frac(bbox, fx, fy)[0], "lat": frac(bbox, fx, fy)[1]} for i, fx, fy in CP_FRACTIONS]
        src = dict(common_src, places_social_file=src_path, places_social_sha256=src_sha, snapshot_components=comp)

        def copy_of(cat):
            return [{"id": r["id"], "lon": r["lon"], "lat": r["lat"], "group": r["group"], "qa_flags": qa.get(r["id"], [])}
                    for r in sorted(recs, key=lambda r: r["id"]) if r["group"] == cat]

        for cat in W.CATEGORIES:
            px, py = frac(bbox, PROPOSED_PLACE[1], PROPOSED_PLACE[2])
            mx, my = frac(bbox, *PROPOSED_MOVE)
            prop = {"id": PROPOSED_PLACE[0], "lon": px, "lat": py, "category": cat, "kind": "hypothetical"}
            moved = dict(prop, lon=mx, lat=my)
            steps = []
            for name, pr in (("baseline", None), ("place_proposed", prop), ("move_proposed", moved), ("delete_proposed", None)):
                sc = scenario(city, snap, cat, cps, pr)
                W.validate(sc, bbox, snap)
                steps.append({"step": name, "scenario": sc, "expected": expected(sc, recs, by_id, qa)})
            fixtures.append({"fixture_id": f"{city}-{cat}-place-move-delete", "kind": "real_slice", "city_id": city, "category": cat,
                             "fictional_fields": ["control_points", "proposed_object"], "rules": RULES, "formula": W.FORMULA,
                             "source": src, "source_copy": {"category_records": copy_of(cat)}, "steps": steps})

        # QA nearest (rule fixed in advance): control point at the coordinate of the largest qa.colocated group that
        # holds records of the category; otherwise at the smallest-id QA-flagged record of the category; otherwise none.
        for cat in W.CATEGORIES:
            groups = sorted([g for g in ev["cities"][city]["qa"]["colocated"] if any(by_id[i]["group"] == cat for i in g["ids"])],
                            key=lambda g: (-len(g["ids"]), g["lon"], g["lat"]))
            flagged = sorted(r["id"] for r in recs if r["group"] == cat and r["id"] in qa)
            if groups:
                where, basis = (groups[0]["lon"], groups[0]["lat"]), {"rule": "largest_colocated_group", "group_size": len(groups[0]["ids"]),
                                                                      "category_records_in_group": sorted(i for i in groups[0]["ids"] if by_id[i]["group"] == cat)}
            elif flagged:
                where, basis = (by_id[flagged[0]]["lon"], by_id[flagged[0]]["lat"]), {"rule": "smallest_id_flagged_record", "id": flagged[0]}
            else:
                not_built.append({"fixture_id": f"{city}-{cat}-qa-nearest", "reason": "no QA-flagged record of this category in the slice (web/evidence.js)"})
                continue
            cpq = [{"id": "cp_qa", "lon": where[0], "lat": where[1]}]
            steps = []
            for name, pr in (("baseline", None),
                             ("place_proposed", {"id": "proj1", "lon": frac(bbox, 0.5, 0.5)[0], "lat": frac(bbox, 0.5, 0.5)[1], "category": cat, "kind": "hypothetical"})):
                sc = scenario(city, snap, cat, cpq, pr)
                W.validate(sc, bbox, snap)
                steps.append({"step": name, "scenario": sc, "expected": expected(sc, recs, by_id, qa)})
            fixtures.append({"fixture_id": f"{city}-{cat}-qa-nearest", "kind": "real_slice", "city_id": city, "category": cat,
                             "fictional_fields": ["control_points", "proposed_object"], "rules": RULES, "formula": W.FORMULA,
                             "qa_control_point_basis": basis,
                             "note": "QA flag is a reason to check the record, not proof of an error; the record is not removed",
                             "source": src, "source_copy": {"category_records": copy_of(cat)}, "steps": steps})

        # invalid inputs (expected rejection before any calculation)
        bad = []
        ox, oy = frac(bbox, 1.10, 0.50)
        bad.append(("control_point_out_of_bbox", scenario(city, snap, "school", [{"id": "cp1", "lon": ox, "lat": oy}], None)))
        bad.append(("proposed_category_mismatch", scenario(city, snap, "school", cps[:1],
                                                           {"id": "proj1", "lon": cps[1]["lon"], "lat": cps[1]["lat"], "category": "outpatient_clinic", "kind": "hypothetical"})))
        bad.append(("foreign_snapshot", scenario(city, "k10s1-" + "0" * 32, "school", cps[:1], None)))
        bad.append(("duplicate_ids", scenario(city, snap, "school", [cps[0], dict(cps[1], id="cp1")], None)))
        steps = []
        for name, sc in bad:
            try:
                W.validate(sc, bbox, snap)
                exp = {"rejected": False}
            except W.ScenarioError as e:
                exp = {"rejected": True, "k10_code": e.code, "field": e.field}
            steps.append({"step": name, "scenario": sc, "expected": exp})
        fixtures.append({"fixture_id": f"{city}-invalid-inputs", "kind": "real_slice_invalid_input", "city_id": city,
                         "note": "codes are K10 names; an implementation may use its own codes but must reject before computing",
                         "source": src, "steps": steps})
    return fixtures, not_built


def synthetic():
    """Empty category: the real slices contain both MVP categories, so this one is SYNTHETIC."""
    bbox = [10.0, 10.0, 10.02, 10.02]
    recs = [{"id": "syn-pharmacy-1", "lon": 10.005, "lat": 10.005, "group": "pharmacy"},
            {"id": "syn-school-a", "lon": 10.01, "lat": 10.01, "group": "school"},
            {"id": "syn-school-b", "lon": 10.01, "lat": 10.01, "group": "school"}]
    snap, comp = W.snapshot_id("shymkent", "SYNTHETIC", bbox, "0" * 64, recs)
    cps = [{"id": "cp1", "lon": 10.01, "lat": 10.01}, {"id": "cp2", "lon": 10.015, "lat": 10.005}]
    steps = []
    for name, cat, pr in (("empty_category_no_proposed", "outpatient_clinic", None),
                          ("empty_category_with_proposed", "outpatient_clinic", {"id": "proj1", "lon": 10.01, "lat": 10.015, "category": "outpatient_clinic", "kind": "hypothetical"}),
                          ("tie_and_honest_zero", "school", None),
                          ("proposed_at_equal_distance_keeps_source", "school", {"id": "proj1", "lon": 10.01, "lat": 10.01, "category": "school", "kind": "hypothetical"})):
        sc = scenario("shymkent", snap, cat, cps, pr)
        W.validate(sc, bbox, snap)
        steps.append({"step": name, "scenario": sc, "expected": W.compute(sc, recs)})
    return {"fixture_id": "synthetic-empty-category-and-ties", "kind": "SYNTHETIC",
            "note": "Not a real city slice. city_id is set only to satisfy the contract; coordinates are at 10E 10N.",
            "rules": RULES, "formula": W.FORMULA, "synthetic_slice": {"bbox": bbox, "records": recs, "snapshot_components": comp},
            "steps": steps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    real, not_built = build(Path(a.app_root), a.commit)
    allfx = real + [synthetic()]
    index = []
    for fx in allfx:
        txt = json.dumps(fx, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False) + "\n"
        (out / f"{fx['fixture_id']}.json").write_text(txt, encoding="utf-8")
        index.append({"fixture_id": fx["fixture_id"], "kind": fx["kind"], "sha256": hashlib.sha256(txt.encode()).hexdigest()})
    (out / "INDEX.json").write_text(json.dumps({"build_commit": a.commit, "fixtures": index, "not_built": not_built}, indent=1) + "\n",
                                    encoding="utf-8")
    print(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
