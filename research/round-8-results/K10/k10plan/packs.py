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
    "invalid_inputs": "mutations of the base pack, one defect per case; the intended code is written first and generation "
                      "stops if the oracle disagrees, so no case is stored with an expectation it does not test",
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


# ---------------------------------------------------------------- invalid input (rejected before any computation)
def _compact(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def _sub_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def invalid_cases(ctx, other_ctx, cat):
    """(case_id, intended code or None for accepted, raw text, pad_to_bytes, note). Mutations of the base scenario."""
    base = base_scenario(ctx, cat)
    txt = _compact(base)
    bbox = ctx["bbox"]
    cases = []

    def obj(case_id, code, fn, note=""):
        sc = copy.deepcopy(base)
        fn(sc)
        cases.append((case_id, code, _compact(sc), None, note))

    def raw(case_id, code, text, note="", pad=None):
        cases.append((case_id, code, text, pad, note))

    raw("duplicate_key", "duplicate_key", _sub_once(txt, '"budget":700', '"budget":700,"budget":1'))
    raw("nan", "non_finite", _sub_once(txt, '"budget":700', '"budget":NaN'))
    raw("infinity", "non_finite", _sub_once(txt, '"budget":700', '"budget":-Infinity'))
    raw("float_overflow_1e999", "non_finite", _sub_once(txt, f'"id":"cp01","lon":{base["control_points"][0]["lon"]}',
                                                                        '"id":"cp01","lon":1e999'))
    raw("integer_overflow", "non_finite", _sub_once(txt, '"budget":700', '"budget":1' + "0" * 400))
    raw("trailing_garbage", "bad_json", txt + "x")
    raw("too_large", "too_large", txt, "padded with spaces after the object to 262145 bytes", 262145)
    obj("schema_v1", "bad_schema_version", lambda s: s.update(schema_version="city-whatif-v1"),
        "v1 file into the v2 importer is refused, v1 keeps its own path")
    obj("missing_budget", "missing_field", lambda s: s.pop("budget"))
    obj("unexpected_top_field", "unexpected_field", lambda s: s.update(population=100000),
        "population is not part of the contract and must not be invented")
    obj("url_field", "unexpected_field", lambda s: s.update(source_url="https://example.invalid/x.json"),
        "no URL loading from a scenario")
    obj("other_city", "bad_city", lambda s: s.update(city_id=other_ctx["city_id"], source_snapshot=other_ctx["source_snapshot"]))
    obj("foreign_snapshot", "foreign_snapshot", lambda s: s.update(source_snapshot=other_ctx["source_snapshot"]))
    obj("bad_category", "bad_category", lambda s: s.update(category="pharmacy"))
    obj("point_out_of_bbox", "out_of_bbox", lambda s: s["control_points"][0].update(lon=round(bbox[2] + 0.01, 6)))
    obj("candidate_out_of_bbox", "out_of_bbox", lambda s: s["candidates"][0].update(lat=round(bbox[1] - 0.01, 6)))
    obj("lat_as_string", "bad_coordinate", lambda s: s["control_points"][1].update(lat=str(s["control_points"][1]["lat"])))
    obj("point_extra_field", "bad_shape", lambda s: s["control_points"][0].update(residents=500))
    obj("zero_points", "bad_point_count", lambda s: s.update(control_points=[]))
    obj("26_points", "bad_point_count", lambda s: s["control_points"].extend(
        dict(p, id=f"x{p['id']}") for p in copy.deepcopy(s["control_points"][:10])))
    obj("17_candidates", "bad_candidate_count", lambda s: s["candidates"].extend(
        dict(c, id=f"x{c['id']}") for c in copy.deepcopy(s["candidates"][:5])))
    obj("duplicate_point_id", "duplicate_id", lambda s: s["control_points"][1].update(id="cp01"))
    obj("duplicate_candidate_id", "duplicate_id", lambda s: s["candidates"][1].update(id="c01"))
    obj("id_65_chars", "bad_id", lambda s: s["control_points"][0].update(id="p" * 65))
    obj("id_empty", "bad_id", lambda s: s["candidates"][0].update(id=""))
    obj("id_number", "bad_id", lambda s: s["control_points"][0].update(id=7))
    obj("weight_0", "bad_value", lambda s: s["control_points"][0].update(weight=0))
    obj("weight_101", "bad_value", lambda s: s["control_points"][0].update(weight=101))
    obj("weight_fraction", "bad_value", lambda s: s["control_points"][0].update(weight=2.5))
    obj("weight_bool", "bad_value", lambda s: s["control_points"][0].update(weight=True))
    obj("cost_0", "bad_value", lambda s: s["candidates"][0].update(cost=0))
    obj("cost_over_max", "bad_value", lambda s: s["candidates"][0].update(cost=1000001))
    obj("budget_negative", "bad_value", lambda s: s.update(budget=-1))
    obj("budget_over_max", "bad_value", lambda s: s.update(budget=1000001))
    obj("max_selected_6", "bad_value", lambda s: s.update(max_selected=6))
    obj("radius_99", "bad_value", lambda s: s.update(coverage_radius_m=99))
    obj("radius_5001", "bad_value", lambda s: s.update(coverage_radius_m=5001))
    obj("candidate_wrong_category", "candidate_category_mismatch",
        lambda s: s["candidates"][0].update(category=[c for c in O.CATEGORIES if c != cat][0]))
    obj("candidate_kind_source", "candidate_not_hypothetical", lambda s: s["candidates"][0].update(kind="source"))
    obj("required_excluded_overlap", "required_excluded_overlap", lambda s: s.update(required_ids=["c01"], excluded_ids=["c01"]),
        "conflicting conditions in the input itself: refuse, do not drop either list silently")
    obj("required_unknown", "unknown_candidate", lambda s: s.update(required_ids=["c99"]))
    first_src = sorted(r["id"] for r in ctx["records"] if r["group"] == cat)[0]
    obj("selected_source_record_id", "unknown_candidate", lambda s: s.update(selected_ids=[first_src]),
        "a source record id is not a candidate id; source and hypothetical ids are separate namespaces")
    obj("selected_duplicate", "duplicate_id", lambda s: s.update(selected_ids=["c01", "c01"]))
    obj("derived_results_forged", None, lambda s: s.update(derived_results={"objectives": {"mean": {"selected_ids": ["c01"],
                                                                                                    "weighted_sum_mm": 0}}}),
        "accepted: derived_results is the one allowed extra field; results are recomputed, the forged values are ignored")
    obj("html_in_ids", None, lambda s: (s["candidates"][0].update(id='<img src=x onerror="alert(1)">'),
                                         s.update(selected_ids=['<img src=x onerror="alert(1)">'])),
        "accepted: ids are plain text; the UI must render them as text, never as HTML")
    return cases


def case_text(case):
    """Exact text of an invalid-input case (too_large is stored unpadded and padded with spaces here)."""
    t = case["raw"]
    return t + " " * (case["pad_to_bytes"] - len(t.encode("utf-8"))) if case.get("pad_to_bytes") else t


def invalid_pack(ctx, other_ctx, src, cat):
    out = []
    for case_id, intended, text, pad, note in invalid_cases(ctx, other_ctx, cat):
        full = text + " " * (pad - len(text.encode("utf-8"))) if pad else text
        try:
            O.validate_plan_scenario(O.parse_strict(full), ctx)
            got = {"rejected": False}
        except O.PlanError as e:
            got = {"rejected": True, "code": e.code}
        want = {"rejected": False} if intended is None else {"rejected": True, "code": intended}
        if got != want:  # the case did not test what it was written for: stop instead of storing a wrong expectation
            raise SystemExit(f"invalid case {case_id}: intended {want}, oracle gave {got}")
        case = {"case_id": case_id, "raw": text, "expected": got, "note": note}
        if pad:
            case["pad_to_bytes"] = pad
        out.append(case)
    return {"pack_format": PACK_FORMAT, "pack_id": f"{ctx['city_id']}-{cat}-invalid-inputs", "kind": "real_slice", "stage": 2,
            "purpose": "inputs that must be refused before computing (state unchanged), plus two that must be accepted",
            "city_id": ctx["city_id"], "category": cat, "rules": {k: RULES[k] for k in ("fixed_before_computing", "invalid_inputs")},
            "provenance": provenance(ctx, src), "source_copy": source_copy(ctx, cat), "scenario": base_scenario(ctx, cat),
            "invalid_cases": out,
            "codes_note": "error codes are K10 names; an implementation may use its own codes, it must only refuse "
                          "before computing and keep the previous state",
            "observations": {"status": "validation_cases", "cases": len(out),
                             "rejected": sum(c["expected"]["rejected"] for c in out),
                             "accepted": sum(not c["expected"]["rejected"] for c in out)}}


# ---------------------------------------------------------------- synthetic geometry (not a city)
M_PER_DEG = 2 * 3.141592653589793 * O.R_EARTH_M / 360  # metres per degree of longitude on the equator


def _x(m):
    return round(m / M_PER_DEG, 7)


def synth_context(name, records):
    recs = [dict(r, qa_flags=[]) for r in records]
    snap = "synthetic:" + hashlib.sha256(_compact(sorted([r["id"], r["lon"], r["lat"], r["group"]] for r in recs)).encode()).hexdigest()
    return {"city_id": name, "bbox": [-0.01, -0.01, 0.2, 0.01], "source_snapshot": snap, "records": recs, "synthetic": True}


def hand_problems(p):
    """Compares a synthetic pack's oracle output with the expectation written by hand in its design block."""
    h, e = p["design"]["hand_expectation"], p["expected"]
    opt, plans, refs = e["optimize"], e["plans"], e["plan_refs"]
    bad = [n for n in ("mean", "minimax", "coverage") if n in h and opt["objectives"][n]["selected_ids"] != h[n]]
    if "pareto" in h and [[q["cost"], q["selected_ids"]] for q in opt["pareto"]] != h["pareto"]:
        bad.append("pareto")
    if "baseline_unknown_count" in h and plans[refs["baseline"]]["metrics"]["unknown_count"] != h["baseline_unknown_count"]:
        bad.append("baseline_unknown_count")
    if "delta_mm" in h and any(r["delta_mm"] != h["delta_mm"] for v in plans.values() for r in v["rows"]):
        bad.append("delta_mm")
    if h.get("pareto_excludes_empty_plan") and (any(q["selected_ids"] == [] for q in opt["pareto"]) or not opt["pareto_note"]):
        bad.append("pareto_excludes_empty_plan")
    if "P1_nearest_before" in h and plans[refs["baseline"]]["rows"][0]["nearest_before"]["id"] != h["P1_nearest_before"]:
        bad.append("P1_nearest_before")
    if "manual_P1_nearest_after" in h and plans[refs["manual"]]["rows"][0]["nearest_after"] != h["manual_P1_nearest_after"]:
        bad.append("manual_P1_nearest_after")
    return bad


def synth_pack(pack_id, purpose, ctx, sc, design):
    exp = expected_for(ctx, sc)
    pack = {"pack_format": PACK_FORMAT, "pack_id": pack_id, "kind": "synthetic", "stage": 2, "purpose": purpose,
            "city_id": ctx["city_id"], "category": sc["category"], "design": design,
            "synthetic_slice": {"bbox": ctx["bbox"], "source_snapshot": ctx["source_snapshot"], "records": ctx["records"],
                                "note": "SYNTHETIC geometry on the equator near 0°E; not Shymkent or Astana data"},
            "scenario": sc, "expected": exp, "observations": observations(exp)}
    bad = hand_problems(pack)
    if bad:  # the oracle disagrees with the hand-derived expectation: stop, do not store
        raise SystemExit(f"{pack_id}: oracle differs from hand expectation in {bad}")
    return pack


def synth_scenario(ctx, cat, cps, cands, budget, max_sel, radius, selected=()):
    return {"schema_version": O.SCHEMA, "city_id": ctx["city_id"], "source_snapshot": ctx["source_snapshot"], "category": cat,
            "control_points": [{"id": i, "lon": _x(x), "lat": 0.0, "weight": w} for i, x, w in cps],
            "candidates": [{"id": i, "lon": _x(x), "lat": 0.0, "category": cat, "kind": "hypothetical", "cost": c}
                           for i, x, c in cands],
            "budget": budget, "max_selected": max_sel, "coverage_radius_m": radius,
            "required_ids": [], "excluded_ids": [], "selected_ids": list(selected)}


def synthetic_packs():
    packs = []
    # 1. objectives differ by design (positions in metres along the equator; margins >= 250 m, far above mm rounding)
    ctx = synth_context("synthetic-equator", [{"id": "src1", "lon": _x(20000), "lat": 0.0, "group": "school", "name": "S"}])
    sc = synth_scenario(ctx, "school", [("P1", 0, 5), ("P2", 1000, 4), ("P3", 1500, 4), ("P4", 5000, 1)],
                        [("a", 0, 1), ("b", 1250, 2), ("c", 2500, 3), ("e", 1000, 4)], 10, 1, 300, ["a"])
    packs.append(synth_pack("synthetic-objectives-differ", "designed so that mean, minimax and coverage pick different "
                            "single candidates", ctx, sc,
                            {"hand_expectation": {"mean": ["e"], "minimax": ["c"], "coverage": ["b"]},
                             "why": "e: smallest weighted sum (11000 m); c: smallest worst point (2500 m); "
                                    "b: covers P2+P3 (weight 8) within 300 m"}))
    # 2. empty baseline: no source record of the category in the slice -> before/delta null, unknown_count
    ctx = synth_context("synthetic-equator", [{"id": "o1", "lon": _x(100), "lat": 0.0, "group": "outpatient_clinic", "name": "O"}])
    sc = synth_scenario(ctx, "school", [(f"P{k}", 1000 * k, 1 + k % 3) for k in range(10)],
                        [(f"k{k}", 1500 * k + 250, 100 + 25 * k) for k in range(8)], 500, 2, 1000, [])
    packs.append(synth_pack("synthetic-empty-baseline", "no source record of the category: before=null, delta=null; "
                            "empty plan has unknown_count=10 and is not placed on the Pareto front", ctx, sc,
                            {"hand_expectation": {"baseline_unknown_count": 10, "delta_mm": None,
                                                  "pareto_excludes_empty_plan": True},
                             "why": "coverage 0 here does not prove the city lacks the service"}))
    # 3. ties: source and candidates at one point, equal candidates -> source wins ties, smallest ids, Pareto collapse
    ctx = synth_context("synthetic-equator", [{"id": "s1", "lon": _x(0), "lat": 0.0, "group": "school", "name": "S1"},
                                              {"id": "s0", "lon": _x(0), "lat": 0.0, "group": "school", "name": "S0"}])
    sc = synth_scenario(ctx, "school", [("P1", 0, 1), ("P2", 2000, 1), ("P3", 3000, 2)],
                        [("t2", 2000, 50), ("t1", 2000, 50), ("u", 0, 10)], 100, 1, 500, ["u"])
    packs.append(synth_pack("synthetic-ties", "equal distances and equal plans: source beats hypothetical on ties, "
                            "smaller id beats larger, equal (cost, sum) collapse to one Pareto point", ctx, sc,
                            {"hand_expectation": {"P1_nearest_before": "s0", "manual_P1_nearest_after": {"kind": "source", "id": "s0"},
                                                  "mean": ["t1"], "pareto": [[0, []], [50, ["t1"]]]},
                             "why": "u sits on the sources and changes nothing; t1 and t2 are identical, t1 < t2"}))
    return packs


def build_all(app_root, src):
    cache = S.load_app(app_root)
    packs, not_built = [], []
    ctxs = {c: S.load_context(app_root, c, cache) for c in O.CITIES}
    for index, (city, cat) in enumerate(REAL_ORDER):
        ctx = ctxs[city]
        packs += real_packs(ctx, src, cat, index)
        p, nb = qa_pack(ctx, src, cat)
        if p:
            packs.append(p)
        else:
            not_built.append(nb)
    for city in O.CITIES:
        other = ctxs[[c for c in O.CITIES if c != city][0]]
        packs.append(invalid_pack(ctxs[city], other, src, "school"))
    packs += synthetic_packs()
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
        if "invalid_cases" not in p:
            write_json(out / "scenarios" / f"{p['pack_id']}.json", p["scenario"])
        for case in p.get("invalid_cases", []):
            if not case.get("pad_to_bytes"):  # too_large: use `cli.py export-case` to write the padded file
                d = out / "scenarios" / "invalid" / p["pack_id"]
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{case['case_id']}.json").write_text(case["raw"], encoding="utf-8")
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
