"""K10 round-6 acceptance, data level (stdlib). Adapter for the round-5 checks on the NEW build layout.

Round-5 run_qa.py looked for a group flag inside web/data.js records; the new build delivers QA through
web/evidence.js (window.CITY_OBS.cities[city].qa.{colocated,possible_duplicates,category_doubt} and
place_district). This adapter reads both files; criteria are unchanged.

Usage: python3 k10r6_data.py --app-root <extracted prototypes/city-evidence> [--json out.json]
       python3 k10r6_data.py --url http://127.0.0.1:8765/ [--json out.json]
Exit 1 if any MUST invariant fails. No EXPECTED_FAIL list is applied.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
R5 = HERE.parents[2] / "round-5-results" / "K10"
sys.path.insert(0, str(R5 / "tools"))
import qa_flags  # noqa: E402  (round-5 generator, unchanged)

FIXTURE = json.loads((R5 / "fixtures" / "ui_coord_group_shymkent.json").read_text(encoding="utf-8"))


def fetch(args, rel):
    if args.app_root:
        return (Path(args.app_root) / "web" / rel).read_bytes()
    base = args.url if args.url.endswith("/") else args.url + "/"
    with urllib.request.urlopen(base + rel, timeout=30) as r:
        return r.read()


def run(args):
    data = qa_flags.parse_data_js(fetch(args, "data.js"))
    ev = qa_flags.parse_data_js(fetch(args, "evidence.js"))
    empty = {"colocated": [], "possible_duplicates": [], "category_doubt": {}}
    for cd in ev.get("cities", {}).values():  # a build without QA must fail by verdict, not by exception
        cd.setdefault("qa", empty)
        cd.setdefault("place_district", {})
    ns = argparse.Namespace(app_root=args.app_root, url=args.url)
    mine = qa_flags.build(ns)
    res = []

    def inv(name, ok, detail):
        res.append({"invariant": name, "level": "MUST", "verdict": "PASS" if ok else "FAIL", "detail": detail})

    city = FIXTURE["city"]
    ids = sorted(FIXTURE["ids"])
    places = {p["id"]: p for p in data["cities"][city]["places"]}
    # I1 the 10 records are present, unmoved
    inv("I1_group_records_present_unmoved", all(i in places and abs(places[i]["lon"] - FIXTURE["lon"]) <= 1e-6
                                                 and abs(places[i]["lat"] - FIXTURE["lat"]) <= 1e-6 for i in ids),
        {"present": sum(i in places for i in ids), "of": len(ids)})

    # I2 the group is exposed to the UI (evidence.js qa.colocated) with exactly these ids and this coordinate
    q = ev["cities"][city]["qa"]
    g = [x for x in q["colocated"] if set(x["ids"]) & set(ids)]
    inv("I2_group_exposed_to_ui_exact_members", len(g) == 1 and sorted(g[0]["ids"]) == ids
        and abs(g[0]["lon"] - FIXTURE["lon"]) <= 1e-6 and abs(g[0]["lat"] - FIXTURE["lat"]) <= 1e-6,
        {"groups_touching_fixture": len(g), "members": len(g[0]["ids"]) if g else 0})

    # I5 every QA id refers to a source record of the same city; no foreign ids
    bad = []
    for c, cd in ev["cities"].items():
        known = {p["id"] for p in data["cities"][c]["places"]}
        qa = cd["qa"]
        used = [i for x in qa["colocated"] for i in x["ids"]] + [i for d in qa["possible_duplicates"] for i in (d["a"], d["b"])] \
            + list(qa["category_doubt"])
        bad += [(c, i) for i in used if i not in known]
    inv("I5_qa_ids_are_source_ids_same_city", not bad, {"unknown_or_foreign": bad[:10]})

    # I5b every exact coordinate group of >=3 records (round-5 rule COORD_EXACT_GROUP) is in qa.colocated
    exact3 = [x for x in mine["groups"] if x["kind"] == "exact" and x["size"] >= 3]
    coloc = {(c, tuple(sorted(x["ids"]))) for c, cd in ev["cities"].items() for x in cd["qa"]["colocated"]}
    missing = [x["group_id"] for x in exact3 if (x["city"], tuple(sorted(x["ids"]))) not in coloc]
    extra = [k for k in coloc if k not in {(x["city"], tuple(sorted(x["ids"]))) for x in exact3}]
    inv("I5b_exact_groups_ge3_match_colocated", not missing and not extra,
        {"exact_ge3": len(exact3), "colocated": len(coloc), "missing": missing, "extra": [list(e[1])[:2] for e in extra]})

    # I6 geometry status and coordinate doubt are separate: colocated members keep their K03 status
    pd = ev["cities"][city]["place_district"]
    st = {i: pd.get(i, {}).get("status") for i in ids}
    inv("I6_district_status_kept_separate_from_coordinate_doubt", all(v is not None for v in st.values()),
        {"statuses": sorted(set(st.values()), key=str)})

    # informational: round-5 flags not mirrored by the new QA (threshold/rule differences, not defects)
    pairs = [x for x in mine["groups"] if x["kind"] == "exact" and x["size"] == 2]
    dup = {(c, frozenset((d["a"], d["b"]))) for c, cd in ev["cities"].items() for d in cd["qa"]["possible_duplicates"]}
    info = {"exact_pairs_round5": len(pairs),
            "exact_pairs_also_possible_duplicate": sum((x["city"], frozenset(x["ids"])) in dup for x in pairs),
            "exact_pairs_without_new_flag": [x["group_id"] for x in pairs if (x["city"], frozenset(x["ids"])) not in dup],
            "near_groups_round5": [(x["group_id"], x["size"], x["max_span_m"]) for x in mine["groups"] if x["kind"] == "near"]}
    return {"target": {"mode": "app-root" if args.app_root else "url", "url": args.url,
                       "data_js_sha256": mine["input"]["data_js_sha256"],
                       "evidence_js_sha256": qa_flags.sha256(fetch(args, "evidence.js"))},
            "fixture": {"group_id": FIXTURE["group_id"], "ids": len(ids)},
            "results": res, "info_not_verdicts": info,
            "must_failures": [r["invariant"] for r in res if r["verdict"] == "FAIL"]}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root")
    g.add_argument("--url")
    ap.add_argument("--json")
    a = ap.parse_args()
    out = run(a)
    txt = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")
    print(txt)
    sys.exit(1 if out["must_failures"] else 0)


if __name__ == "__main__":
    main()
