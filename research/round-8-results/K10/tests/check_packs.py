"""K10 round 8: check the city-plan-v2 scenario packs (stdlib; node optional for the JS cross-check).

    python3 tests/check_packs.py --app-root <BUILD prototypes/city-evidence> [--packs <dir>] [--json out.json]

Per pack:
  SOURCE    real packs: source_copy (ids, lon, lat, group of the category), places file sha256 and source_snapshot
            still match the target app root; mismatch = STALE pack (data changed), not a product defect.
  VALID     the scenario passes oracle validation against the pack's own copy of the slice.
  RECOMPUTE expected results recomputed by k10plan.oracle from the pack's own source copy are identical
            (expected values were not edited by hand).
  INDEX     sha256 of the pack file equals the value recorded in INDEX.json.
  JS        real packs: millimetre distances (before + to every candidate) and source_snapshot computed with the
            BUILD's web/whatif.js equal the oracle values exactly (node required, else SKIP).
Whole run:
  IMMUTABLE sha256 of the app-root input files and of every pack file are the same before and after the run, and
            the oracle did not mutate the context/scenario objects it was given.
"""
import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from k10plan import oracle as O  # noqa: E402
from k10plan import packs as P  # noqa: E402
from k10plan import slice as S  # noqa: E402


def pack_context(p):
    """Oracle context rebuilt only from the pack itself (independent of the target app root)."""
    if p["kind"] == "real_slice":
        prov = p["provenance"]
        return {"city_id": p["city_id"], "bbox": prov["bbox"], "source_snapshot": prov["source_snapshot"],
                "records": copy.deepcopy(p["source_copy"]["category_records"])}
    s = p["synthetic_slice"]
    return {"city_id": p["city_id"], "bbox": s["bbox"], "source_snapshot": s["source_snapshot"], "synthetic": True,
            "records": copy.deepcopy(s["records"])}


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def recompute(p):
    ctx = pack_context(p)
    if "invalid_cases" in p:
        bad = []
        for case in p["invalid_cases"]:
            try:
                O.validate_plan_scenario(O.parse_strict(case["raw"]), ctx)
                got = {"rejected": False}
            except O.PlanError as e:
                got = {"rejected": True, "code": e.code}
            if got != case["expected"]:
                bad.append({"case_id": case["case_id"], "got": got, "expected": case["expected"]})
        return bad
    ctx_before, sc_before = canon(ctx), canon(p["scenario"])
    got = P.expected_for(ctx, p["scenario"])
    mutated = canon(ctx) != ctx_before or canon(p["scenario"]) != sc_before
    bad = []
    if canon(got) != canon(p["expected"]):
        bad.append("expected differs from oracle recomputation")
    if canon(P.observations(got)) != canon(p["observations"]):
        bad.append("observations differ from oracle recomputation")
    if mutated:
        bad.append("oracle mutated its input")
    return bad


def tree_manifest(d):
    return {str(q.relative_to(d)): hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(Path(d).rglob("*.json"))}


def run(app_root, packs_dir):
    app = Path(app_root)
    inputs_before, packs_before = S.input_manifest(app), tree_manifest(packs_dir)
    cache = S.load_app(app)
    index = json.loads((packs_dir / "INDEX.json").read_text(encoding="utf-8"))
    index_sha = {e["pack_id"]: e["sha256"] for e in index["packs"]}
    files = sorted(q for q in packs_dir.glob("*.json") if q.name != "INDEX.json")
    js = {}
    if shutil.which("node"):
        js = json.loads(subprocess.check_output(["node", str(ROOT / "tests/xcheck_build.cjs"), str(app), *map(str, files)]))
    results = []
    for f in files:
        p = json.loads(f.read_text(encoding="utf-8"))
        r = {"pack_id": p["pack_id"], "kind": p["kind"], "checks": {}}
        if p["kind"] == "real_slice":
            ctx_now = S.load_context(app, p["city_id"], cache)
            cat = p["category"]
            now = sorted([q["id"], q["lon"], q["lat"], q["group"]] for q in ctx_now["records"] if q["group"] == cat)
            was = sorted([q["id"], q["lon"], q["lat"], q["group"]] for q in p["source_copy"]["category_records"])
            prov = p["provenance"]
            ok = (now == was and ctx_now["source_snapshot"] == prov["source_snapshot"]
                  and ctx_now["places_file_sha256"] == prov["places_social_sha256"]
                  and S.sha256_file(app / prov["places_social_file"]) == prov["places_social_sha256"])
            r["checks"]["SOURCE"] = "PASS" if ok else "STALE"
        else:
            r["checks"]["SOURCE"] = "SYNTHETIC"
        if "invalid_cases" not in p:
            try:
                O.validate_plan_scenario(json.loads(json.dumps(p["scenario"])), pack_context(p))
                r["checks"]["VALID"] = "PASS"
            except O.PlanError as e:
                r["checks"]["VALID"] = f"FAIL({e.code})"
        bad = recompute(p)
        r["checks"]["RECOMPUTE"] = "PASS" if not bad else "FAIL"
        if bad:
            r["recompute_problems"] = bad
        r["checks"]["INDEX"] = "PASS" if index_sha.get(p["pack_id"]) == hashlib.sha256(f.read_bytes()).hexdigest() else "FAIL"
        if p["pack_id"] in js and r["checks"]["SOURCE"] == "STALE":
            r["checks"]["JS"] = "SKIP(source stale)"  # reported once as STALE, not again as a JS failure
        elif p["pack_id"] in js:
            j = js[p["pack_id"]]
            m = O.Matrix(pack_context(p), O.validate_plan_scenario(json.loads(json.dumps(p["scenario"])), pack_context(p)))
            base_py = [[b[0], b[2]] if b else None for b in m.base]
            raw_diff = max((abs(O.haversine_m(cp["lon"], cp["lat"], c["lon"], c["lat"]) - j["raw"][i][k])
                            for i, cp in enumerate(p["scenario"]["control_points"])
                            for k, c in enumerate(p["scenario"]["candidates"])), default=0.0)
            ok = base_py == j["base"] and m.cand == j["cand"] and j["snapshot"] == p["scenario"]["source_snapshot"]
            r["checks"]["JS"] = "PASS" if ok else "FAIL"
            r["js_max_abs_diff_m_unrounded"] = raw_diff
        elif p["kind"] == "real_slice" and "invalid_cases" not in p:
            r["checks"]["JS"] = "SKIP(node not found)"
        results.append(r)
    inputs_after, packs_after = S.input_manifest(app), tree_manifest(packs_dir)
    immutable = inputs_before == inputs_after and packs_before == packs_after
    fails = [x["pack_id"] for x in results if any(v.startswith("FAIL") for v in x["checks"].values())]
    stale = [x["pack_id"] for x in results if x["checks"].get("SOURCE") == "STALE"]
    return {"target": {"app_root": str(app), "data_js_sha256": inputs_after.get("web/data.js")},
            "index_build": index.get("build"), "packs_checked": len(results), "results": results,
            "failures": fails, "stale": stale, "IMMUTABLE": "PASS" if immutable else "FAIL",
            "input_manifest": inputs_after}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--packs", default=str(ROOT / "packs"))
    ap.add_argument("--json")
    a = ap.parse_args()
    out = run(a.app_root, Path(a.packs))
    txt = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.json:
        Path(a.json).write_text(txt, encoding="utf-8")
    counts = {}
    for x in out["results"]:
        for k, v in x["checks"].items():
            counts[f"{k}={v}"] = counts.get(f"{k}={v}", 0) + 1
    print(json.dumps({"packs": out["packs_checked"], "counts": counts, "failures": out["failures"], "stale": out["stale"],
                      "IMMUTABLE": out["IMMUTABLE"]}, ensure_ascii=False, sort_keys=True))
    sys.exit(1 if out["failures"] or out["stale"] or out["IMMUTABLE"] != "PASS" else 0)


if __name__ == "__main__":
    main()
