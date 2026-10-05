"""K10 round-5 REVIEW: re-runnable QA checks for the city-evidence BUILD (stdlib only).

    python3 run_qa.py --app-root <extracted prototypes/city-evidence> [--json out.json]
    python3 run_qa.py --url http://127.0.0.1:8765/ [--json out.json]

Check levels:
  MUST    - failure = defect of the checked version (exit code 1)
  SHOULD  - desired behaviour proposed by this review; failure on baseline 0bf27de is EXPECTED
            and is not a defect claim for another version until that version is run.
Fixture: ../fixtures/ui_coord_group_shymkent.json (the 10-record Shymkent group, ids from K10 data).
"""
import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))
import qa_flags  # noqa: E402

FIXTURE = ROOT / "fixtures" / "ui_coord_group_shymkent.json"
BASELINE_EXPECTED_FAIL = {"SHOULD_data_exposes_coord_group_flag"}


def load_ui(args):
    if args.app_root:
        raw = (Path(args.app_root) / "web" / "data.js").read_bytes()
    else:
        base = args.url if args.url.endswith("/") else args.url + "/"
        with urllib.request.urlopen(base + "data.js", timeout=30) as r:
            raw = r.read()
    return qa_flags.parse_data_js(raw)


def source_fc(app_root, city, layer):
    p = Path(app_root) / "inputs" / "k10" / "data" / city / f"{layer}.geojson"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def run(args):
    ui = load_ui(args)
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    res = []

    def check(name, level, ok, detail):
        res.append({"check": name, "level": level, "status": "PASS" if ok else "FAIL", "detail": detail})

    # fixture group present and complete
    c = ui["cities"].get(fx["city"], {"places": []})
    by_id = {p["id"]: p for p in c["places"]}
    missing = [i for i in fx["ids"] if i not in by_id]
    check("MUST_fixture_ids_present", "MUST", not missing, {"expected": len(fx["ids"]), "missing": missing})
    at_point = sorted(i for i, p in by_id.items() if abs(p["lon"] - fx["lon"]) <= 1e-6 and abs(p["lat"] - fx["lat"]) <= 1e-6)
    check("MUST_fixture_group_coordinate_unchanged", "MUST", at_point == sorted(fx["ids"]),
          {"ids_at_fixture_point": len(at_point), "note": "a fix may flag or annotate the group, not move/delete it"})
    bb = c.get("bbox")
    check("MUST_fixture_group_inside_bbox", "MUST",
          bool(bb) and bb[0] <= fx["lon"] <= bb[2] and bb[1] <= fx["lat"] <= bb[3], {"bbox": bb})

    # id preservation vs source (app-root only)
    if args.app_root:
        for city, cd in sorted(ui["cities"].items()):
            for layer, ui_list, keep in (("places_social", cd["places"], lambda f: True),
                                         ("segments", cd["segments"], lambda f: f["properties"].get("subtype") == "road")):
                fc = source_fc(args.app_root, city, layer)
                if fc is None:
                    check(f"MUST_{city}_{layer}_ids_preserved", "MUST", False, {"error": "source file missing"})
                    continue
                s = sorted(f["id"] for f in fc["features"] if keep(f))
                u = [x["id"] for x in ui_list]
                check(f"MUST_{city}_{layer}_ids_preserved", "MUST", sorted(u) == s and len(set(u)) == len(u),
                      {"source": len(s), "ui": len(u), "missing_in_ui": len(set(s) - set(u)), "extra_in_ui": len(set(u) - set(s)),
                       "duplicates_in_ui": len(u) - len(set(u))})
    else:
        check("INFO_id_preservation_vs_source", "INFO", True, {"skipped": "--url mode has no source files"})

    # qa_flags deterministic and only refers to known ids
    ns = argparse.Namespace(app_root=args.app_root, url=args.url)
    a = json.dumps(qa_flags.build(ns), sort_keys=True, ensure_ascii=False)
    b = json.dumps(qa_flags.build(ns), sort_keys=True, ensure_ascii=False)
    flags = json.loads(a)
    known = {p["id"] for cd in ui["cities"].values() for p in cd["places"]}
    check("MUST_qa_flags_deterministic", "MUST", a == b, {"sha256": qa_flags.sha256(a.encode())})
    check("MUST_qa_flags_ids_known", "MUST", {f["id"] for f in flags["flags"]} <= known, {"flags": len(flags["flags"])})
    check("MUST_qa_flags_no_email_value", "MUST", "@" not in a, {})
    errs = [f for f in flags["flags"] if f["severity"] == "error"]
    check("MUST_no_error_flags", "MUST", not errs, {"error_flags": [(f["city"], f["rule"], f["id"]) for f in errs][:20]})

    # SHOULD: data delivered to the UI marks coordinate groups (proposal of this review)
    grp_ids = set(fx["ids"])
    marked = [i for i in grp_ids if i in by_id and any(k in by_id[i] for k in ("qa_flags", "coord_group", "qa"))]
    check("SHOULD_data_exposes_coord_group_flag", "SHOULD", len(marked) == len(grp_ids),
          {"marked": len(marked), "of": len(grp_ids), "looked_for_keys": ["qa_flags", "coord_group", "qa"]})

    for r in res:
        r["expected_fail_at_baseline_0bf27de"] = r["check"] in BASELINE_EXPECTED_FAIL
    must_fail = [r["check"] for r in res if r["level"] == "MUST" and r["status"] == "FAIL"]
    return {"target": {"app_root_given": bool(args.app_root), "url": args.url,
                       "data_js_sha256": flags["input"]["data_js_sha256"]},
            "results": res, "must_failures": must_fail,
            "should_failures": [r["check"] for r in res if r["level"] == "SHOULD" and r["status"] == "FAIL"]}


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
