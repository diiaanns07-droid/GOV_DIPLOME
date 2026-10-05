"""K10 round 7: check the city-whatif-v1 fixtures against a BUILD (stdlib; node optional for the JS cross-check).

    python3 check_fixtures.py --app-root <extracted prototypes/city-evidence> [--json out.json]
    python3 check_fixtures.py --url http://127.0.0.1:8765/ [--json out.json]

Per fixture:
  SOURCE   - source_copy (ids, lon, lat, group of the category) and source_snapshot still match the target build;
             a mismatch = STALE fixture (data changed), not a product defect.
  RECOMPUTE- expected values recomputed with tools/whatif_ref.py from the fixture's own source copy are identical
             (fixture not edited by hand); independent of the target build's current data.
  JS       - tools/whatif_ref.cjs gives the same ids and distances within 1e-6 m (IEEE cross-check).
This does not test the BUILD's own implementation (none exists in the base commit); see HANDOFF.md.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import whatif_ref as W  # noqa: E402

TOL_M = 1e-6


def get(args, rel):
    if args.app_root:
        return (Path(args.app_root) / rel).read_bytes()
    base = args.url if args.url.endswith("/") else args.url + "/"
    with urllib.request.urlopen(base + rel.replace("web/", "", 1), timeout=30) as r:
        return r.read()


def parse_js(raw):
    t = raw.decode("utf-8")
    return json.loads(t[t.index("{"):t.rstrip().rindex(";")])


def strip_derived(rows):
    keep = ("control_point_id", "before_m", "nearest_before_id", "distance_to_proposed_m", "after_m", "nearest_after_id", "delta_m", "label")
    return [{k: r[k] for k in keep} for r in rows]


def run(args):
    data = parse_js(get(args, "web/data.js"))
    fixtures = sorted(p for p in (ROOT / "fixtures").glob("*.json") if p.name != "INDEX.json")
    results = []
    js = {}
    if shutil.which("node"):
        js = json.loads(subprocess.check_output(["node", str(ROOT / "tools" / "whatif_ref.cjs"), *map(str, fixtures)]))
    for p in fixtures:
        fx = json.loads(p.read_text(encoding="utf-8"))
        r = {"fixture_id": fx["fixture_id"], "kind": fx["kind"], "checks": {}}
        if fx["kind"].startswith("real_slice"):
            city = fx["city_id"]
            c = data["cities"][city]
            recs = [{"id": q["id"], "lon": q["lon"], "lat": q["lat"], "group": q["group"]} for q in c["places"]]
            src_sha = fx["source"]["places_social_sha256"]
            if args.app_root:
                src_sha_now = hashlib.sha256((Path(args.app_root) / fx["source"]["places_social_file"]).read_bytes()).hexdigest()
            else:
                src_sha_now = src_sha  # --url: source file is not served; snapshot still checks UI coordinates
            snap_now, _ = W.snapshot_id(city, c["release"], c["bbox"], src_sha_now, recs)
            snap_fx = fx["steps"][0]["scenario"]["source_snapshot"]
            ok = snap_now == snap_fx and src_sha_now == src_sha
            if "source_copy" in fx:
                cat = fx["category"]
                now = sorted([q["id"], q["lon"], q["lat"], q["group"]] for q in recs if q["group"] == cat)
                was = sorted([q["id"], q["lon"], q["lat"], q["group"]] for q in fx["source_copy"]["category_records"])
                ok = ok and now == was
            r["checks"]["SOURCE"] = "PASS" if ok else "STALE"
        else:
            recs = fx["synthetic_slice"]["records"]
            r["checks"]["SOURCE"] = "SYNTHETIC"
        # RECOMPUTE uses the fixture's own source copy, so a data change is reported once (SOURCE=STALE)
        own = fx["source_copy"]["category_records"] if "source_copy" in fx else recs
        own_snap = ("k10s1-" + hashlib.sha256(W.canon(fx["source"]["snapshot_components"]).encode()).hexdigest()[:32]
                    if "source" in fx else None)
        bad = 0
        for s in fx["steps"]:
            exp = s["expected"]
            if "rows" in exp:
                bbox = data["cities"][fx["city_id"]]["bbox"] if fx["kind"].startswith("real") else fx["synthetic_slice"]["bbox"]
                W.validate(s["scenario"], bbox, s["scenario"]["source_snapshot"])
                got = W.compute(s["scenario"], own)
                bad += strip_derived(got["rows"]) != strip_derived(exp["rows"]) or got["category_records_in_slice"] != exp["category_records_in_slice"]
            else:
                try:
                    W.validate(s["scenario"], fx["source"]["snapshot_components"]["bbox"], own_snap)
                    got = {"rejected": False}
                except W.ScenarioError as e:
                    got = {"rejected": True, "k10_code": e.code, "field": e.field}
                bad += got != exp
        r["checks"]["RECOMPUTE"] = "PASS" if not bad else f"FAIL({bad})"
        if fx["fixture_id"] in js:
            worst, ids_ok = 0.0, True
            for s, jsstep in zip(fx["steps"], js[fx["fixture_id"]]):
                for a, b in zip(s["expected"]["rows"], jsstep["rows"]):
                    ids_ok &= a["nearest_before_id"] == b["nearest_before_id"]
                    for k in ("before_m", "after_m", "delta_m"):
                        if (a[k] is None) != (b[k] is None):
                            ids_ok = False
                        elif a[k] is not None:
                            worst = max(worst, abs(a[k] - b[k]))
            r["checks"]["JS"] = "PASS" if ids_ok and worst <= TOL_M else "FAIL"
            r["js_max_abs_diff_m"] = worst
        elif fx["steps"] and "rows" in fx["steps"][0]["expected"]:
            r["checks"]["JS"] = "SKIP(node not found)"
        results.append(r)
    fails = [x["fixture_id"] for x in results if any(v.startswith("FAIL") for v in x["checks"].values())]
    stale = [x["fixture_id"] for x in results if x["checks"].get("SOURCE") == "STALE"]
    return {"target": {"mode": "app-root" if args.app_root else "url", "url": args.url,
                       "data_js_sha256": hashlib.sha256(get(args, "web/data.js")).hexdigest()},
            "tolerance_m": TOL_M, "results": results, "failures": fails, "stale": stale}


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
    sys.exit(1 if out["failures"] or out["stale"] else 0)


if __name__ == "__main__":
    main()
