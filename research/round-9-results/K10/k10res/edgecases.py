"""K10 round 9 stage 3: SYNTHETIC edge-case packs for city-resilience-v1 and a pack of envelopes that must be refused.

Synthetic geometry lies on the equator near 0°E (positions in metres east, 1 m = 1/M degrees); it is not city data.
Every synthetic pack carries a hand-derived expectation (design.hand_expectation); generation stops if the oracle
disagrees. Invalid-envelope cases carry the intended code, written before the oracle is asked.
"""
import copy
import hashlib
import json

from . import oracle_res as R
from k10plan import oracle as O  # noqa: E402
from k10plan import packs as P8  # noqa: E402

M_PER_DEG = P8.M_PER_DEG
CITY = "synthetic-equator"


def _x(m):
    return m / M_PER_DEG  # not rounded: whole-metre positions then give whole-millimetre distances, so hand values are exact


def synth_context(records):
    recs = [{"id": i, "lon": _x(xm), "lat": 0.0, "group": g, "name": i, "qa_flags": []} for i, xm, g in records]
    snap = "synthetic:" + hashlib.sha256(json.dumps(sorted([r["id"], r["lon"], r["group"]] for r in recs)).encode()).hexdigest()
    return {"city_id": CITY, "bbox": [-0.01, -0.01, 0.2, 0.01], "source_snapshot": snap, "records": recs, "synthetic": True}


def plan(ctx, cps, cands, budget, max_sel, radius, selected=(), required=(), excluded=(), cat="school"):
    return {"schema_version": O.SCHEMA, "city_id": CITY, "source_snapshot": ctx["source_snapshot"], "category": cat,
            "control_points": [{"id": i, "lon": _x(x), "lat": 0.0, "weight": w} for i, x, w in cps],
            "candidates": [{"id": i, "lon": _x(x), "lat": 0.0, "category": cat, "kind": "hypothetical", "cost": c} for i, x, c in cands],
            "budget": budget, "max_selected": max_sel, "coverage_radius_m": radius,
            "required_ids": list(required), "excluded_ids": list(excluded), "selected_ids": list(selected)}


def env(p, cases):
    return {"schema_version": R.SCHEMA, "plan": p, "cases": [{"id": i, "label": lab, "disabled_source_ids": list(ids)} for i, lab, ids in cases]}


def hand_problems(pack):
    h, o = pack["design"]["hand_expectation"], pack["expected"]["optimize"]
    bad = []
    for k in ("status", "plans_identical", "price_of_robustness_m", "infeasible_reasons"):
        if k in h and (o.get(k) != h[k] if not isinstance(h[k], float) else o.get(k) is None or abs(o[k] - h[k]) > 1e-6):
            bad.append(k)
    for who in ("nominal", "robust", "manual"):
        for k in ("selected_ids", "worst_vector", "worst_case_ids"):
            key = f"{who}_{k}"
            if key in h and (o[who] or {}).get(k) != h[key]:
                bad.append(key)
    if "manual_feasible" in h and o["manual"]["feasibility"]["feasible"] != h["manual_feasible"]:
        bad.append("manual_feasible")
    if "case_unknown" in h:
        for cid, want in h["case_unknown"].items():
            got = next(c["metrics"]["unknown_count"] for c in o["manual"]["per_case"] if c["case_id"] == cid)
            if got != want:
                bad.append(f"case_unknown[{cid}]")
    return bad


def synth_pack(pack_id, purpose, ctx, envelope, design):
    from .envelopes import expected_for, observations, PACK_FORMAT, DISCLAIMER
    exp = expected_for(ctx, envelope)
    pack = {"pack_format": PACK_FORMAT, "pack_id": pack_id, "kind": "synthetic", "stage": 3, "purpose": purpose,
            "city_id": CITY, "category": envelope["plan"]["category"], "disclaimer": DISCLAIMER, "design": design,
            "synthetic_slice": {"bbox": ctx["bbox"], "source_snapshot": ctx["source_snapshot"], "records": ctx["records"],
                                "note": "SYNTHETIC geometry on the equator near 0°E; not Shymkent or Astana data"},
            "envelope": envelope, "expected": exp, "observations": observations(exp)}
    bad = hand_problems(pack)
    if bad:
        raise SystemExit(f"{pack_id}: oracle differs from the hand expectation in {bad}")
    return pack


def synthetic_packs():
    out = []
    # 1. robust differs: nominal A relies on source S; without S, B is better in the worst case
    ctx = synth_context([("S", 0, "school"), ("far", 20000, "school")])
    p = plan(ctx, [("P1", 0, 2), ("P2", 2000, 1)], [("A", 2000, 1), ("B", 1000, 1)], 10, 1, 300, ["A"])
    out.append(synth_pack("synthetic-robust-differs", "nominal plan relies on one source; the robust plan does not", ctx,
                          env(p, [("noS", "Условно не учитываем S", ["S"])]),
                          {"hand_expectation": {"status": "optimal", "nominal_selected_ids": ["A"], "robust_selected_ids": ["B"],
                                                "plans_identical": False, "nominal_worst_vector": [0, 4000000, 2000000],
                                                "robust_worst_vector": [0, 3000000, 1000000], "robust_worst_case_ids": ["noS"],
                                                "price_of_robustness_m": 1000 / 3},
                           "why": "base: A gives 0+0, B gives 0+1000 m; without S: A gives 2*2000+0, B 2*1000+1000 m; "
                                  "price = 1000/3 m (B's base mean) - 0"}))
    # 2. plans coincide: the left-out source is far from every point, nothing changes
    p = plan(ctx, [("P1", 0, 2), ("P2", 2000, 1)], [("A", 2000, 1), ("B", 1000, 1)], 10, 1, 300, [])
    out.append(synth_pack("synthetic-plans-coincide", "the left-out record is nobody's nearest: nominal = robust, price 0", ctx,
                          env(p, [("nofar", "Условно не учитываем far", ["far"])]),
                          {"hand_expectation": {"nominal_selected_ids": ["A"], "robust_selected_ids": ["A"], "plans_identical": True,
                                                "price_of_robustness_m": 0.0, "robust_worst_case_ids": ["base", "nofar"],
                                                "manual_selected_ids": [], "manual_worst_vector": [0, 2000000, 2000000]},
                           "why": "without 'far' every distance is the same, so all cases tie and both are worst"}))
    # 3. every source of the category left out; plus an identical duplicate case
    ctx2 = synth_context([("S1", 0, "school"), ("S2", 3000, "school"), ("O1", 1000, "outpatient_clinic")])
    p = plan(ctx2, [("P1", 0, 1), ("P2", 3000, 1)], [("M", 1500, 5), ("L", 0, 3)], 10, 2, 500, [])
    out.append(synth_pack("synthetic-all-sources-left-out", "a case leaves out every school; a second case repeats it", ctx2,
                          env(p, [("none", "Условно не учитываем все школы среза", ["S1", "S2"]),
                                  ("none_again", "То же исключение второй раз", ["S2", "S1"])]),
                          {"hand_expectation": {"manual_selected_ids": [], "manual_worst_vector": [2, 0, None],
                                                "manual_worst_case_ids": ["none", "none_again"],
                                                "case_unknown": {"base": 0, "none": 2, "none_again": 2},
                                                "nominal_selected_ids": [], "robust_selected_ids": ["L", "M"],
                                                "robust_worst_vector": [0, 1500000, 1500000],
                                                "robust_worst_case_ids": ["none", "none_again"], "plans_identical": False,
                                                "price_of_robustness_m": 0.0},
                           "why": "with schools every plan has base loss 0, so the nominal plan is the cheapest (empty). Without "
                                  "schools: empty -> both points unknown; M -> 1500+1500 m; L -> 0+3000 m; L+M (cost 8 <= 10) -> "
                                  "0+1500 m, the smallest worst vector. Price 0 m: same base mean, the robust plan only costs more"}))
    # 4. infeasible: the required candidate costs more than the budget; manual plan misses the required one
    p = plan(ctx, [("P1", 0, 2), ("P2", 2000, 1)], [("A", 2000, 5), ("B", 1000, 7)], 6, 1, 300, ["A"], required=["B"])
    out.append(synth_pack("synthetic-infeasible-budget", "required candidate costs more than the budget: infeasible, nothing "
                          "is dropped silently", ctx, env(p, [("noS", "Условно не учитываем S", ["S"])]),
                          {"hand_expectation": {"status": "infeasible", "infeasible_reasons": ["required_cost_exceeds_budget"],
                                                "price_of_robustness_m": None, "manual_feasible": False,
                                                "manual_selected_ids": ["A"]},
                           "why": "B (cost 7) is required, budget 6; manual {A} misses B"}))
    # 5. the worst case stays unknown for every allowed plan (max_selected 0)
    p = plan(ctx2, [("P1", 0, 1), ("P2", 3000, 1)], [("M", 1500, 5)], 0, 0, 500, [])
    out.append(synth_pack("synthetic-unknown-worst", "no plan may add a site, a case leaves out every school: the worst "
                          "vector stays unknown and is reported as unknown, not as 0", ctx2,
                          env(p, [("none", "Условно не учитываем все школы среза", ["S1", "S2"])]),
                          {"hand_expectation": {"nominal_selected_ids": [], "robust_selected_ids": [], "plans_identical": True,
                                                "robust_worst_vector": [2, 0, None], "robust_worst_case_ids": ["none"],
                                                "price_of_robustness_m": 0.0, "case_unknown": {"base": 0, "none": 2}},
                           "why": "only the empty plan is allowed; without schools both points have no known distance"}))
    return out


# ---------------------------------------------------------------- envelopes that must be refused (or accepted)
def _compact(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def case_text(case):
    t = case["raw"]
    return t + " " * (case["pad_to_bytes"] - len(t.encode("utf-8"))) if case.get("pad_to_bytes") else t


def context_of(pack):
    if pack["kind"] == "real_slice":
        pr = pack["provenance"]
        return {"city_id": pack["city_id"], "bbox": pr["bbox"], "source_snapshot": pr["source_snapshot"],
                "records": copy.deepcopy(pack["source_copy"]["category_records"])}
    s = pack["synthetic_slice"]
    return {"city_id": pack["city_id"], "bbox": s["bbox"], "source_snapshot": s["source_snapshot"], "synthetic": True,
            "records": copy.deepcopy(s["records"])}


def run_case(pack, case):
    try:
        R.validate_resilience(O.parse_strict(case_text(case)), context_of(pack))
        return {"rejected": False}
    except (R.ResError, O.PlanError) as e:
        return {"rejected": True, "code": e.code}


def _cases(base_env, other_snapshot, other_cat_id, ctx_ids):
    txt = _compact(base_env)
    first = base_env["cases"][0]
    out = []

    def obj(cid, code, fn, note=""):
        e = copy.deepcopy(base_env)
        fn(e)
        out.append((cid, code, _compact(e), None, note))

    def raw(cid, code, text, note="", pad=None):
        out.append((cid, code, text, pad, note))

    def sub(old, new):
        assert txt.count(old) == 1, old
        return txt.replace(old, new)

    raw("duplicate_key", "duplicate_key", sub('"schema_version":"city-resilience-v1"',
                                              '"schema_version":"city-resilience-v1","schema_version":"city-resilience-v1"'))
    raw("nan_budget", "non_finite", sub('"budget":700', '"budget":NaN'))
    raw("too_large", "too_large", txt, "padded with spaces to 262145 bytes", 262145)
    obj("missing_cases", "missing_field", lambda e: e.pop("cases"))
    obj("extra_top_field", "unexpected_field", lambda e: e.update(probability=0.3), "no probabilities or risk scores")
    obj("v2_schema_in_envelope", "bad_schema_version", lambda e: e.update(schema_version="city-plan-v2"))
    obj("plan_derived_results", "derived_not_allowed", lambda e: e["plan"].update(derived_results={"note": "x"}),
        "r9 envelopes neither export nor accept derived fields")
    obj("plan_foreign_snapshot", "foreign_snapshot", lambda e: e["plan"].update(source_snapshot=other_snapshot))
    obj("13_candidates", "too_many_candidates", lambda e: e["plan"]["candidates"].append(dict(e["plan"]["candidates"][0], id="c13")),
        "v2 allows 16; the resilience analysis allows 12 and must say so before any computation")
    obj("17_candidates", "bad_candidate_count", lambda e: e["plan"]["candidates"].extend(
        dict(e["plan"]["candidates"][0], id=f"x{k}") for k in range(5)))
    obj("plan_point_id_html", "bad_id", lambda e: e["plan"]["control_points"][0].update(id="<img src=x>"),
        "BUILD id rule (NFC letters, digits, _ . -) applies to plan ids too")
    obj("zero_cases", "bad_case_count", lambda e: e.update(cases=[]))
    obj("8_user_cases", "bad_case_count", lambda e: e.update(cases=[dict(first, id=f"k{k}") for k in range(8)]),
        "1..7 user cases + automatic base = at most 8")
    obj("case_id_base", "reserved_case_id", lambda e: e["cases"][0].update(id="base"))
    obj("case_id_duplicate", "duplicate_case_id", lambda e: e["cases"][1].update(id=e["cases"][0]["id"]))
    obj("case_id_space", "bad_id", lambda e: e["cases"][0].update(id="top 1"))
    obj("case_id_not_nfc", "bad_id", lambda e: e["cases"][0].update(id="cafe\u0301"))
    obj("case_id_cyrillic", None, lambda e: e["cases"][0].update(id="случай_1"), "accepted: Unicode NFC ids as in BUILD")
    obj("label_empty", "bad_label", lambda e: e["cases"][0].update(label=""))
    obj("label_spaces", "bad_label", lambda e: e["cases"][0].update(label="   "))
    obj("label_121", "bad_label", lambda e: e["cases"][0].update(label="л" * 121))
    obj("label_120", None, lambda e: e["cases"][0].update(label="л" * 120), "accepted: 120 code points")
    obj("label_control_char", "bad_label", lambda e: e["cases"][0].update(label="a\u0007b"))
    obj("label_html", None, lambda e: e["cases"][0].update(label="<b>Условно</b> <img src=x onerror=alert(1)>"),
        "accepted: shown only as text")
    obj("disabled_empty", "bad_disabled", lambda e: e["cases"][0].update(disabled_source_ids=[]))
    obj("disabled_candidate_id", "candidate_id_not_source", lambda e: e["cases"][0].update(disabled_source_ids=["c01"]),
        "candidate ids are not source ids; namespaces stay separate")
    obj("disabled_unknown", "unknown_source_id", lambda e: e["cases"][0].update(disabled_source_ids=["no-such-record"]))
    obj("disabled_other_category", "unknown_source_id", lambda e: e["cases"][0].update(disabled_source_ids=[other_cat_id]),
        "a real record of another category of the same city")
    obj("disabled_duplicate", "duplicate_id", lambda e: e["cases"][0].update(disabled_source_ids=[ctx_ids[0], ctx_ids[0]]))
    obj("disabled_number", "bad_id", lambda e: e["cases"][0].update(disabled_source_ids=[7]))
    obj("case_extra_field", "bad_shape", lambda e: e["cases"][0].update(probability=0.5))
    obj("duplicate_exclusion_sets", None, lambda e: e["cases"].append(dict(first, id="same_again")),
        "accepted: two cases with the same set are allowed and shown as such")
    obj("all_records_left_out", None, lambda e: e["cases"][0].update(disabled_source_ids=list(ctx_ids)),
        "accepted: every record of the category conditionally left out")
    return out


def invalid_pack(real_pack, other_snapshot, other_cat_id):
    from .envelopes import PACK_FORMAT, DISCLAIMER
    ctx = context_of(real_pack)
    ids = sorted(r["id"] for r in ctx["records"] if r["group"] == real_pack["category"])
    cases = []
    for cid, intended, text, pad, note in _cases(real_pack["envelope"], other_snapshot, other_cat_id, ids):
        c = {"case_id": cid, "raw": text, "note": note}
        if pad:
            c["pad_to_bytes"] = pad
        got = run_case(real_pack, c)
        want = {"rejected": False} if intended is None else {"rejected": True, "code": intended}
        if got != want:
            raise SystemExit(f"invalid case {cid}: intended {want}, oracle gave {got}")
        c["expected"] = got
        cases.append(c)
    return {"pack_format": PACK_FORMAT, "pack_id": real_pack["pack_id"].replace("-relied", "-invalid-envelopes"),
            "kind": "real_slice", "stage": 3, "city_id": real_pack["city_id"], "category": real_pack["category"],
            "purpose": "envelopes that must be refused before any computation (state unchanged), and some that must be accepted",
            "disclaimer": DISCLAIMER, "provenance": real_pack["provenance"], "source_copy": real_pack["source_copy"],
            "envelope": real_pack["envelope"], "invalid_cases": cases,
            "codes_note": "codes are K10 names; an implementation may use its own, it must refuse before computing",
            "observations": {"status": "validation_cases", "cases": len(cases),
                             "rejected": sum(c["expected"]["rejected"] for c in cases),
                             "accepted": sum(not c["expected"]["rejected"] for c in cases)}}


def unknown_base_pack():
    """A slice without any school: v2 would accept the plan (empty baseline), but no resilience case can name a school."""
    from .envelopes import PACK_FORMAT, DISCLAIMER
    ctx = synth_context([("O1", 1000, "outpatient_clinic")])
    p = plan(ctx, [("P1", 0, 1)], [("A", 500, 1)], 5, 1, 500, [])
    pack = {"pack_format": PACK_FORMAT, "pack_id": "synthetic-unknown-base-refused", "kind": "synthetic", "stage": 3,
            "city_id": CITY, "category": "school", "disclaimer": DISCLAIMER,
            "purpose": "unknown base: the category has no source record, so the base is unknown and no case can be formed",
            "synthetic_slice": {"bbox": ctx["bbox"], "source_snapshot": ctx["source_snapshot"], "records": ctx["records"],
                                "note": "SYNTHETIC; empty baseline does not mean the service is absent"},
            "invalid_cases": []}
    for cid, ids, code, note in (("clinic_as_school", ["O1"], "unknown_source_id", "O1 is a clinic, not a school"),
                                 ("no_ids", [], "bad_disabled", "a case must name at least one record")):
        c = {"case_id": cid, "raw": _compact(env(p, [("c1", "Условно", ids)])), "note": note}
        got = run_case(pack, c)
        if got != {"rejected": True, "code": code}:
            raise SystemExit(f"unknown-base {cid}: intended {code}, oracle gave {got}")
        c["expected"] = got
        pack["invalid_cases"].append(c)
    pack["observations"] = {"status": "validation_cases", "cases": 2, "rejected": 2, "accepted": 0,
                            "note": "in a valid envelope the base case always contains >= 1 record, so its distances are "
                                    "known and the price of robustness is null only when no plan is feasible"}
    return pack
