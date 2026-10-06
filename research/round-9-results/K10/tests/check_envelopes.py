"""K10 round 9: check the city-resilience-v1 demo packs (stdlib).

    python3 tests/check_envelopes.py --app-root <BUILD prototypes/city-evidence> [--packs envelopes] [--json out.json]
    (run from research/round-9-results/K10)

Per pack:
  SOURCE     real packs: source_copy and source_snapshot equal the target app root (else STALE); every left-out id is a
             real source record of the category
  VALID      the envelope passes k10res validation against the pack's own copy of the slice
  RECOMPUTE  expected values recomputed by k10res.oracle_res from the pack's own copy are identical
  ORDER      reversed cases / disabled ids / points / candidates give the same results and digests
  CROSS_R8   independent path: for every case the K10 r8 v2 oracle, run on a copy of the slice without the left-out
             records, gives the same per-case metrics for manual/nominal/robust; nominal = r8 'mean' optimum on base;
             robust = brute-force minimum of (W, L_base, cost, ids) over all feasible subsets evaluated by r8
  HAND       synthetic packs: the oracle equals the hand-written expectation
  INDEX      sha256 equals INDEX.json
Whole run: IMMUTABLE - app-root inputs and pack files unchanged by the run.
"""
import argparse
import copy
import hashlib
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from k10res import envelopes as E  # noqa: E402
from k10res import oracle_res as R  # noqa: E402
from k10plan import oracle as O  # noqa: E402
from k10plan import slice as S8  # noqa: E402

try:
    from k10res import edgecases as X
except ImportError:
    X = None


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False)


def pack_context(p):
    if p["kind"] == "real_slice":
        pr = p["provenance"]
        return {"city_id": p["city_id"], "bbox": pr["bbox"], "source_snapshot": pr["source_snapshot"],
                "records": copy.deepcopy(p["source_copy"]["category_records"])}
    s = p["synthetic_slice"]
    return {"city_id": p["city_id"], "bbox": s["bbox"], "source_snapshot": s["source_snapshot"], "synthetic": True,
            "records": copy.deepcopy(s["records"])}


def cross_r8(p):
    """Per case, the r8 v2 oracle on a filtered copy of the slice; brute-force robust optimum."""
    ctx = pack_context(p)
    env = R.validate_resilience(json.loads(json.dumps(p["envelope"])), ctx)
    sc = env["plan"]
    cat = sc["category"]
    problems = []

    def case_ctx(c):
        off = set(c["disabled_source_ids"])
        return dict(ctx, records=[r for r in ctx["records"] if not (r["group"] == cat and r["id"] in off)])

    ctxs = [case_ctx(c) for c in env["cases"]]

    def r8_losses(ids):
        mets = [O.evaluate_plan(cc, sc, ids)["metrics"] for cc in ctxs]
        return mets, [R.loss(m) for m in mets]

    opt = p["expected"]["optimize"]
    plans = [("manual", opt["manual"])]
    if opt["status"] == "optimal":
        plans += [("nominal", opt["nominal"]), ("robust", opt["robust"])]
    for name, s in plans:
        mets, _ = r8_losses(s["selected_ids"])
        for m8, row in zip(mets, s["per_case"]):
            got = {k: row["metrics"][k] for k in ("unknown_count", "weighted_sum_mm", "max_mm", "covered_weight", "cost")}
            want = {k: m8[k] for k in got}
            if got != want or (m8["weighted_mean_mm"] is None) != (row["metrics"]["weighted_mean_mm"] is None):
                problems.append(f"{name}/{row['case_id']}: r8 {want} vs res {got}")
    if opt["status"] == "optimal":
        mean8 = O.optimize_plans(ctxs[0], sc, {"sensitivity": False})["objectives"]["mean"]["selected_ids"]
        if mean8 != opt["nominal"]["selected_ids"]:
            problems.append(f"nominal {opt['nominal']['selected_ids']} vs r8 mean {mean8}")
        ids_all = [c["id"] for c in sc["candidates"] if c["id"] not in sc["excluded_ids"]]
        best = None
        for k in range(sc["max_selected"] + 1):
            for comb in itertools.combinations(sorted(ids_all), k):
                ids = sorted(comb)
                if not set(sc["required_ids"]) <= set(ids):
                    continue
                cost = sum(c["cost"] for c in sc["candidates"] if c["id"] in ids)
                if cost > sc["budget"]:
                    continue
                _, ls = r8_losses(ids)
                key = (max(ls), ls[0], cost, ids)
                best = key if best is None or key < best else best
        if best[3] != opt["robust"]["selected_ids"]:
            problems.append(f"robust {opt['robust']['selected_ids']} vs brute force {best[3]}")
    return problems


def order_problems(p):
    ctx = pack_context(p)
    env = json.loads(json.dumps(p["envelope"]))
    env["cases"] = [dict(c, disabled_source_ids=c["disabled_source_ids"][::-1]) for c in env["cases"][::-1]]
    for k in ("control_points", "candidates", "required_ids", "excluded_ids", "selected_ids"):
        env["plan"][k] = env["plan"][k][::-1]
    ctx["records"] = ctx["records"][::-1]
    got = R.optimize_resilience(ctx, R.validate_resilience(env, ctx))
    want = p["expected"]["optimize"]
    keys = ("status", "resilience_problem_digest", "resilience_scenario_digest", "exclusions_digest", "nominal", "robust",
            "evaluated", "feasible_count", "price_of_robustness_m", "case_ids")
    return [k for k in keys if canon(got.get(k)) != canon(want.get(k))]


def tree(d):
    return {str(q.relative_to(d)): hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(Path(d).rglob("*.json"))}


def run(app_root, packs_dir):
    app = Path(app_root)
    in0, pk0 = S8.input_manifest(app), tree(packs_dir)
    cache = S8.load_app(app)
    index = {e["pack_id"]: e["sha256"] for e in json.loads((packs_dir / "INDEX.json").read_text(encoding="utf-8"))["packs"]}
    results = []
    for f in sorted(q for q in packs_dir.glob("*.json") if q.name != "INDEX.json"):
        p = json.loads(f.read_text(encoding="utf-8"))
        r = {"pack_id": p["pack_id"], "kind": p["kind"], "checks": {}, "problems": []}
        if p["kind"] == "real_slice":
            now = S8.load_context(app, p["city_id"], cache)
            cat = p["category"]
            a = sorted([q["id"], q["lon"], q["lat"], q["group"]] for q in now["records"] if q["group"] == cat)
            b = sorted([q["id"], q["lon"], q["lat"], q["group"]] for q in p["source_copy"]["category_records"])
            ids = {q[0] for q in a}
            left = {x for c in p["envelope"]["cases"] for x in c["disabled_source_ids"]}
            ok = a == b and now["source_snapshot"] == p["provenance"]["source_snapshot"] == p["envelope"]["plan"]["source_snapshot"]
            r["checks"]["SOURCE"] = "PASS" if ok and left <= ids else "STALE"
        else:
            r["checks"]["SOURCE"] = "SYNTHETIC"
        if "invalid_cases" in p:
            bad = [c["case_id"] for c in p["invalid_cases"] if X.run_case(p, c) != c["expected"]]
            r["checks"]["RECOMPUTE"] = "PASS" if not bad else "FAIL"
            r["problems"] += bad
        else:
            try:
                R.validate_resilience(json.loads(json.dumps(p["envelope"])), pack_context(p))
                r["checks"]["VALID"] = "PASS"
            except R.ResError as e:
                r["checks"]["VALID"] = f"FAIL({e.code})"
            ctx = pack_context(p)
            c0 = canon(ctx)
            got = E.expected_for(ctx, p["envelope"])
            ok = canon(got) == canon(p["expected"]) and canon(E.observations(got)) == canon(p["observations"]) and canon(ctx) == c0
            r["checks"]["RECOMPUTE"] = "PASS" if ok else "FAIL"
            ob = order_problems(p)
            r["checks"]["ORDER"] = "PASS" if not ob else f"FAIL({','.join(ob)})"
            cp = cross_r8(p)
            r["checks"]["CROSS_R8"] = "PASS" if not cp else "FAIL"
            r["problems"] += cp
            if p["kind"] == "synthetic" and X is not None:
                hb = X.hand_problems(p)
                r["checks"]["HAND"] = "PASS" if not hb else f"FAIL({','.join(hb)})"
        r["checks"]["INDEX"] = "PASS" if index.get(p["pack_id"]) == hashlib.sha256(f.read_bytes()).hexdigest() else "FAIL"
        results.append(r)
    immutable = S8.input_manifest(app) == in0 and tree(packs_dir) == pk0
    fails = [x["pack_id"] for x in results if any(v.startswith("FAIL") for v in x["checks"].values())]
    stale = [x["pack_id"] for x in results if x["checks"].get("SOURCE") == "STALE"]
    return {"target": {"app_root": str(app), "data_js_sha256": in0.get("web/data.js")}, "packs": len(results),
            "results": results, "failures": fails, "stale": stale, "IMMUTABLE": "PASS" if immutable else "FAIL"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--packs", default=str(ROOT / "envelopes"))
    ap.add_argument("--json")
    a = ap.parse_args()
    out = run(a.app_root, Path(a.packs))
    if a.json:
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    counts = {}
    for x in out["results"]:
        for k, v in x["checks"].items():
            counts[f"{k}={v}"] = counts.get(f"{k}={v}", 0) + 1
    print(json.dumps({"packs": out["packs"], "counts": counts, "failures": out["failures"], "stale": out["stale"],
                      "IMMUTABLE": out["IMMUTABLE"]}, ensure_ascii=False, sort_keys=True))
    sys.exit(1 if out["failures"] or out["stale"] or out["IMMUTABLE"] != "PASS" else 0)


if __name__ == "__main__":
    main()
