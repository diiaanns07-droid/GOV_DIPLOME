"""K10 round 8: city-plan-v2 scenario packs on the real K10 slices (Shymkent, Astana) plus separate synthetic packs.

    python3 -m k10plan.packs --app-root <BUILD prototypes/city-evidence> --commit <BUILD sha> --out <dir>

Every fictional part (control points, weights, candidate places, costs, budget, max_selected, radius) follows the
RULES below, which are fixed in code before any result is computed; nothing is tuned towards a desired outcome.
Expected results are written only from k10plan.oracle output. Real parts: city, bbox, release, source records
(ids/coordinates as in web/data.js), QA flags (web/evidence.js), file hashes, source_snapshot.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from . import oracle as O
from . import slice as S

PACK_FORMAT = "k10-plan-pack-v1"
REAL_ORDER = [("shymkent", "school"), ("shymkent", "outpatient_clinic"), ("astana", "school"), ("astana", "outpatient_clinic")]
CP_GRID = [((i + 0.5) / 4, (j + 0.5) / 4) for j in range(4) for i in range(4)]            # cp01..cp16
CAND_GRID = [(fx, fy) for fy in (1 / 6, 1 / 2, 5 / 6) for fx in (1 / 8, 3 / 8, 5 / 8, 7 / 8)]  # c01..c12
SEED_BASE = 20261005
RULES = {
    "fixed_before_computing": True,
    "coordinates": "bbox fractions (x = share of lon span, y = share of lat span), rounded to 6 decimals",
    "control_points": "cp01..cp16: 4x4 grid, x=(i+0.5)/4, y=(j+0.5)/4, row j outer (south to north), i inner (west to east)",
    "weights": "SYNTHETIC: cp k (1-based) weight = 1 + ((3*k) mod 5); a user priority, not residents",
    "candidates": "c01..c12: x in (1/8,3/8,5/8,7/8) inner, y in (1/6,1/2,5/6) outer; kind=hypothetical",
    "costs": "SYNTHETIC conditional units: candidate k cost = 100 + 50*((5*k) mod 7); not tenge, not an estimate",
    "base": "budget 700, max_selected 3, coverage_radius_m 400 (analysis parameter, not a walking norm), "
            "required [], excluded [], selected_ids [c06, c07] (the two candidates nearest the bbox centre)",
    "tight_budget": "base, budget = smallest candidate cost",
    "required_excluded": "base, required [c12] (fixed corner candidate), excluded = ids of the base 'mean' winner minus c12",
    "conflict_budget": "base, required = the two most expensive candidates (ties: smaller id), budget = their cost sum - 1",
    "conflict_count": "base, required [c01,c02,c03,c04], max_selected 3, budget 1000000 (only the count conflicts)",
    "qa_nearest": "base + one control point at each qa.colocated group of web/evidence.js holding records of the category "
                  "(largest group first, ids cp_qa1..), weight continues the weight rule; not built when no such group",
    "seeded": "LCG x=(1103515245*x+12345) mod 2^31, seed = 20261005 + index in [shymkent/school, shymkent/outpatient_clinic, "
              "astana/school, astana/outpatient_clinic]; 20 control points s01..s20 at x,y = 0.05+0.9*u, weight 1+(x mod 100); "
              "14 candidates r01..r14 at x,y = 0.05+0.9*u, cost 10*(5+(x mod 46)); budget 900, max_selected 4, radius 300; "
              "selected_ids []; draw order per point: x, y, weight; per candidate: x, y, cost",
    "objectives_agree": "computed after the fact from oracle winners; reported as it came out, never searched for",
}


class Lcg:
    def __init__(self, seed):
        self.x = seed % 2 ** 31

    def next(self):
        self.x = (1103515245 * self.x + 12345) % 2 ** 31
        return self.x

    def unit(self):
        return self.next() / 2 ** 31


def frac(bbox, fx, fy):
    return round(bbox[0] + fx * (bbox[2] - bbox[0]), 6), round(bbox[1] + fy * (bbox[3] - bbox[1]), 6)


def weight_rule(k):
    return 1 + ((3 * k) % 5)


def cost_rule(k):
    return 100 + 50 * ((5 * k) % 7)


def base_scenario(ctx, cat):
    bbox = ctx["bbox"]
    cps = []
    for k, (fx, fy) in enumerate(CP_GRID, 1):
        lon, lat = frac(bbox, fx, fy)
        cps.append({"id": f"cp{k:02d}", "lon": lon, "lat": lat, "weight": weight_rule(k)})
    cands = []
    for k, (fx, fy) in enumerate(CAND_GRID, 1):
        lon, lat = frac(bbox, fx, fy)
        cands.append({"id": f"c{k:02d}", "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical", "cost": cost_rule(k)})
    return {"schema_version": O.SCHEMA, "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"], "category": cat,
            "control_points": cps, "candidates": cands, "budget": 700, "max_selected": 3, "coverage_radius_m": 400,
            "required_ids": [], "excluded_ids": [], "selected_ids": ["c06", "c07"]}


def seeded_scenario(ctx, cat, seed):
    g, bbox = Lcg(seed), ctx["bbox"]
    cps, cands = [], []
    for k in range(1, 21):
        lon, lat = frac(bbox, 0.05 + 0.9 * g.unit(), 0.05 + 0.9 * g.unit())
        cps.append({"id": f"s{k:02d}", "lon": lon, "lat": lat, "weight": 1 + g.next() % 100})
    for k in range(1, 15):
        lon, lat = frac(bbox, 0.05 + 0.9 * g.unit(), 0.05 + 0.9 * g.unit())
        cands.append({"id": f"r{k:02d}", "lon": lon, "lat": lat, "category": cat, "kind": "hypothetical",
                      "cost": 10 * (5 + g.next() % 46)})
    return {"schema_version": O.SCHEMA, "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"], "category": cat,
            "control_points": cps, "candidates": cands, "budget": 900, "max_selected": 4, "coverage_radius_m": 300,
            "required_ids": [], "excluded_ids": [], "selected_ids": []}


# ---------------------------------------------------------------- expected results (oracle only)
def _rows_with_ties(ctx, sc, rows):
    """Adds tied_before_ids (all source records at the before distance) and the QA flags of the nearest source."""
    pool = [r for r in ctx["records"] if r["group"] == sc["category"]]
    by_id = {r["id"]: r for r in pool}
    cps = {p["id"]: p for p in sc["control_points"]}
    out = []
    for row in rows:
        row = dict(row)
        if row["before_mm"] is not None:
            p = cps[row["control_point_id"]]
            row["tied_before_ids"] = sorted(r["id"] for r in pool
                                            if O.to_mm(O.haversine_m(p["lon"], p["lat"], r["lon"], r["lat"])) == row["before_mm"])
            row["nearest_before_qa_flags"] = by_id[row["nearest_before"]["id"]].get("qa_flags", [])
        out.append(row)
    return out


def plan_key(ids):
    return "+".join(ids) if ids else "(empty)"


def expected_for(ctx, sc_raw):
    sc = O.validate_plan_scenario(json.loads(json.dumps(sc_raw)), ctx)
    opt = O.optimize_plans(ctx, sc)
    plans = {}

    def add(ids):
        k = plan_key(ids)
        if k not in plans:
            ev = O.evaluate_plan(ctx, sc, ids)
            ev["rows"] = _rows_with_ties(ctx, sc, ev["rows"])
            plans[k] = ev
        return k

    refs = {"manual": add(sc["selected_ids"]), "baseline": add([])}
    if opt["objectives"]:
        for name, met in opt["objectives"].items():
            refs[name] = add(met["selected_ids"])
    return {"generated_by": "k10plan.oracle", "metric_version": O.METRIC_VERSION, "validation": "accepted",
            "problem_digest": O.problem_digest(sc), "scenario_digest": O.scenario_digest(sc),
            "optimize": opt, "plan_refs": refs, "plans": plans}


def observations(exp):
    opt = exp["optimize"]
    obs = {"status": opt["status"], "evaluated": opt["evaluated"], "feasible_count": opt["feasible_count"],
           "pareto_points": len(opt["pareto"])}
    if opt["objectives"]:
        sets = {k: plan_key(v["selected_ids"]) for k, v in opt["objectives"].items()}
        obs["winners"] = sets
        obs["objectives_agree"] = len(set(sets.values())) == 1
        obs["distinct_winner_sets"] = len(set(sets.values()))
        obs["differing_pairs"] = sorted(f"{a}/{b}" for a in sets for b in sets if a < b and sets[a] != sets[b])
    else:
        obs["infeasible_reasons"] = opt["infeasible_reasons"]
    obs["sensitivity"] = [{"budget": s["budget"], "status": s["status"],
                           "mean": plan_key(s["objectives"]["mean"]["selected_ids"]) if s["objectives"] else None}
                          for s in opt["sensitivity"]]
    return obs


# ---------------------------------------------------------------- packs
def provenance(ctx, src):
    return {"build_branch": src["branch"], "build_commit": src["commit"], "app_path": "prototypes/city-evidence",
            "data_js_sha256": src["data_js_sha256"], "evidence_js_sha256": src["evidence_js_sha256"],
            "places_social_file": ctx["places_file"], "places_social_sha256": ctx["places_file_sha256"],
            "release": ctx["release"], "bbox": ctx["bbox"], "source_snapshot": ctx["source_snapshot"],
            "snapshot_components": ctx["snapshot_components"],
            "upstream": "Overture Maps places 2026-09-23.1 via K10 package (round-3 results); not re-downloaded"}


def source_copy(ctx, cat):
    return {"category_records": [{"id": r["id"], "lon": r["lon"], "lat": r["lat"], "group": r["group"], "name": r["name"],
                                  "qa_flags": r["qa_flags"]}
                                 for r in sorted(ctx["records"], key=lambda r: r["id"]) if r["group"] == cat],
            "note": "read-only copy of web/data.js records of this category; the source records are never modified"}


def make_pack(pack_id, stage, purpose, ctx, src, sc, rule_keys, extra=None):
    exp = expected_for(ctx, sc)
    pack = {"pack_format": PACK_FORMAT, "pack_id": pack_id, "kind": "real_slice", "stage": stage, "purpose": purpose,
            "city_id": ctx["city_id"], "category": sc["category"],
            "synthetic_parts": ["control_points (positions by rule, weights)", "candidates (positions by rule, costs)",
                                "budget", "max_selected", "coverage_radius_m", "required_ids", "excluded_ids", "selected_ids"],
            "rules": {k: RULES[k] for k in ["fixed_before_computing", "coordinates"] + rule_keys},
            "provenance": provenance(ctx, src), "source_copy": source_copy(ctx, sc["category"]),
            "scenario": sc, "expected": exp, "observations": observations(exp),
            "does_not_claim": ["costs are not real prices or an estimate", "weights are not population",
                               "the optimum is only among the entered candidates, not the best plan for the city",
                               "straight-line distance in this slice only; no walking time, capacity or social benefit"]}
    if extra:
        pack.update(extra)
    return pack


def real_packs(ctx, src, cat, index):
    base = base_scenario(ctx, cat)
    tag = f"{ctx['city_id']}-{cat}"
    packs = [make_pack(f"{tag}-base", 1, "base v2 pack: 16 control points, 12 candidates, budget 700, max 3", ctx, src,
                       base, ["control_points", "weights", "candidates", "costs", "base"])]
    base_mean = packs[0]["expected"]["optimize"]["objectives"]["mean"]["selected_ids"]

    sc = copy.deepcopy(base)
    sc["budget"] = min(c["cost"] for c in sc["candidates"])
    packs.append(make_pack(f"{tag}-tight-budget", 2, "limited budget: only the cheapest single candidate fits", ctx, src,
                           sc, ["control_points", "weights", "candidates", "costs", "base", "tight_budget"]))

    sc = copy.deepcopy(base)
    sc["required_ids"] = ["c12"]
    sc["excluded_ids"] = sorted(x for x in base_mean if x != "c12")
    packs.append(make_pack(f"{tag}-required-excluded", 2, "required corner candidate, base mean winner excluded", ctx, src,
                           sc, ["control_points", "weights", "candidates", "costs", "base", "required_excluded"]))

    sc = copy.deepcopy(base)
    top2 = sorted(sc["candidates"], key=lambda c: (-c["cost"], c["id"]))[:2]
    sc["required_ids"] = sorted(c["id"] for c in top2)
    sc["budget"] = sum(c["cost"] for c in top2) - 1
    sc["selected_ids"] = sorted(c["id"] for c in top2)
    packs.append(make_pack(f"{tag}-conflict-budget", 2, "conflict: required candidates cost more than the budget", ctx, src,
                           sc, ["control_points", "weights", "candidates", "costs", "base", "conflict_budget"]))

    sc = copy.deepcopy(base)
    sc["required_ids"] = ["c01", "c02", "c03", "c04"]
    sc["max_selected"] = 3
    sc["budget"] = 1000000
    sc["selected_ids"] = ["c01", "c02", "c03", "c04"]
    packs.append(make_pack(f"{tag}-conflict-count", 2, "conflict: 4 required candidates, max_selected 3", ctx, src,
                           sc, ["control_points", "weights", "candidates", "costs", "base", "conflict_count"]))

    sc = seeded_scenario(ctx, cat, SEED_BASE + index)
    packs.append(make_pack(f"{tag}-seeded", 2, "seeded random geometry: 20 points, 14 candidates, budget 900, max 4", ctx, src,
                           sc, ["seeded"], {"seed": SEED_BASE + index}))
    return packs


def qa_pack(ctx, src, cat):
    by_id = {r["id"]: r for r in ctx["records"]}
    groups = sorted((g for g in ctx["qa_colocated"] if any(by_id[i]["group"] == cat for i in g["ids"] if i in by_id)),
                    key=lambda g: (-len(g["ids"]), g["lon"], g["lat"]))
    if not groups:
        return None, {"pack_id": f"{ctx['city_id']}-{cat}-qa-nearest",
                      "reason": "no qa.colocated group with records of this category in web/evidence.js"}
    sc = base_scenario(ctx, cat)
    k0 = len(sc["control_points"])
    for n, g in enumerate(groups, 1):
        sc["control_points"].append({"id": f"cp_qa{n}", "lon": g["lon"], "lat": g["lat"], "weight": weight_rule(k0 + n)})
    pack = make_pack(f"{ctx['city_id']}-{cat}-qa-nearest", 2,
                     "QA nearest: control points on colocated groups; ties and QA flags must stay visible", ctx, src, sc,
                     ["control_points", "weights", "candidates", "costs", "base", "qa_nearest"],
                     {"qa_note": "a QA flag is a reason to check a record, not proof of an error; the record stays in the slice",
                      "qa_groups": [{"lon": g["lon"], "lat": g["lat"], "size": len(g["ids"]),
                                     "of_category": sorted(i for i in g["ids"] if by_id.get(i, {}).get("group") == cat)}
                                    for g in groups]})
    return pack, None


def build_all(app_root, src):
    cache = S.load_app(app_root)
    packs, not_built = [], []
    for index, (city, cat) in enumerate(REAL_ORDER):
        ctx = S.load_context(app_root, city, cache)
        packs += real_packs(ctx, src, cat, index)
        p, nb = qa_pack(ctx, src, cat)
        if p:
            packs.append(p)
        else:
            not_built.append(nb)
    return packs, not_built


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--branch", default="claude/beautiful-clarke-sbzomj")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-stage", type=int, default=2, help="1 = base packs only")
    a = ap.parse_args()
    app = Path(a.app_root)
    src = {"commit": a.commit, "branch": a.branch,
           "data_js_sha256": S.sha256_file(app / "web/data.js"), "evidence_js_sha256": S.sha256_file(app / "web/evidence.js")}
    before = S.input_manifest(app)
    packs, not_built = build_all(app, src)
    packs = [p for p in packs if p["stage"] <= a.max_stage]
    not_built = not_built if a.max_stage >= 2 else []
    after = S.input_manifest(app)
    out = Path(a.out)
    (out / "scenarios").mkdir(parents=True, exist_ok=True)
    index = []
    for p in packs:
        write_json(out / f"{p['pack_id']}.json", p)
        write_json(out / "scenarios" / f"{p['pack_id']}.json", p["scenario"])
        index.append({"pack_id": p["pack_id"], "kind": p["kind"], "stage": p["stage"], "purpose": p["purpose"],
                      **{k: p["observations"].get(k) for k in ("status", "objectives_agree", "distinct_winner_sets",
                                                                "infeasible_reasons", "pareto_points")},
                      "sha256": hashlib.sha256((out / f"{p['pack_id']}.json").read_bytes()).hexdigest()})
    write_json(out / "INDEX.json", {"pack_format": PACK_FORMAT, "generated_by": "k10plan.packs + k10plan.oracle",
                                    "build": src, "rules": RULES, "packs": index, "not_built": not_built,
                                    "inputs_unchanged_during_generation": before == after, "input_manifest": after})
    print(json.dumps({"packs": len(packs), "not_built": not_built, "inputs_unchanged": before == after}, ensure_ascii=False))
    return 0 if before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
