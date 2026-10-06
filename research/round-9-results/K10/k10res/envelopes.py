"""K10 round 9: city-resilience-v1 demo envelopes on the real K10 slices (Shymkent, Astana) - stage 2.

    python3 -m k10res.envelopes --app-root <BUILD prototypes/city-evidence> --commit <BUILD sha> --out envelopes
    (run from research/round-9-results/K10)

Fictional parts follow RULES, fixed in code before any result is computed: control points, weights, candidate places,
costs, budget, max_selected, radius (all from the K10 r8 base plan) and which real source records are *conditionally*
left out of a case. A case says "compute as if these records were not in the slice"; it does not claim that any
facility closed or does not exist. Expected results are written only from k10res.oracle_res output.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from . import oracle_res as R
from k10plan import oracle as O  # noqa: E402  (path set by oracle_res)
from k10plan import packs as P8  # noqa: E402
from k10plan import slice as S8  # noqa: E402

PACK_FORMAT = "k10-resilience-pack-v1"
REAL_ORDER = [("shymkent", "school"), ("shymkent", "outpatient_clinic"), ("astana", "school"), ("astana", "outpatient_clinic")]
SEED_BASE = 20261006
RULES = {
    "fixed_before_computing": True,
    "plan": "K10 r8 base plan of the same city and category: control points cp01..cp16 on a 4x4 bbox grid with SYNTHETIC "
            "weights 1+(3k mod 5); 12 hypothetical candidates c01..c12 with SYNTHETIC costs 100+50*(5k mod 7) "
            "(conditional units, not tenge); budget 700, max_selected 3, coverage radius 400 m; manual selection c06+c07",
    "relied": "envelope 'relied': source records of the category ranked by the total weight of control points whose "
              "nearest source (before any candidate) is that record, ties by id; cases top1 = rank 1, top2 = ranks 1-2, "
              "second = rank 2 alone",
    "seeded": "envelope 'seeded': LCG x=(1103515245*x+12345) mod 2^31, seed 20261006 + index in [shymkent/school, "
              "shymkent/outpatient_clinic, astana/school, astana/outpatient_clinic]; case sK (K=1,2,3) starts the LCG at "
              "seed+1000*K and leaves out K distinct records, each drawn as position (x mod remaining) of the still unused "
              "id-sorted records",
    "qa": "envelope 'qa' (built only where records of the category carry QA flags): case qa_all leaves out every record "
          "with a QA flag in web/evidence.js; case colocated leaves out the records of the category in the largest "
          "qa.colocated group. A QA flag is a reason to check a record, not proof of an error",
    "labels": "labels state the rule only ('Условно не учитываем ...'); they never claim a closure",
    "objectives_and_price": "computed after the fact by the oracle; whether the robust plan differs is reported as it came out",
}
DISCLAIMER = "Условно исключаем из расчёта; это не подтверждение закрытия. Пустые исходные данные не означают отсутствие услуги."


def relied_ranking(ctx, plan):
    sc = O.validate_plan_scenario(json.loads(json.dumps(plan)), ctx)
    m = O.Matrix(ctx, sc)
    load = {}
    for b, w in zip(m.base, m.weights):
        if b:
            load[b[2]] = load.get(b[2], 0) + w
    return sorted(load.items(), key=lambda kv: (-kv[1], kv[0]))


def seeded_pick(ids, seed, k):
    x, pool, out = seed % 2 ** 31, sorted(ids), []
    for _ in range(k):
        x = (1103515245 * x + 12345) % 2 ** 31
        out.append(pool.pop(x % len(pool)))
    return sorted(out)


def envelope(plan, cases):
    return {"schema_version": R.SCHEMA, "plan": plan, "cases": cases}


def case(cid, label, ids):
    return {"id": cid, "label": label, "disabled_source_ids": sorted(ids)}


def expected_for(ctx, env_raw):
    env = R.validate_resilience(json.loads(json.dumps(env_raw)), ctx)
    opt = R.optimize_resilience(ctx, env)
    rows = {"manual": R.evaluate_resilience(ctx, env, env["plan"]["selected_ids"])}
    if opt["status"] == "optimal":
        rows["nominal"] = R.evaluate_resilience(ctx, env, opt["nominal"]["selected_ids"])
        rows["robust"] = R.evaluate_resilience(ctx, env, opt["robust"]["selected_ids"])
    return {"generated_by": "k10res.oracle_res", "validation": "accepted", "optimize": opt, "plans_with_rows": rows}


def observations(exp):
    o = exp["optimize"]
    obs = {"status": o["status"], "evaluated": o["evaluated"], "feasible_count": o["feasible_count"],
           "cases": len(o["case_ids"]), "manual_feasible": o["manual"]["feasibility"]["feasible"],
           "manual_worst_case_ids": o["manual"]["worst_case_ids"]}
    if o["status"] == "optimal":
        obs.update(nominal=o["nominal"]["selected_ids"], robust=o["robust"]["selected_ids"], plans_identical=o["plans_identical"],
                   price_of_robustness_m=o["price_of_robustness_m"], price_reason=o["price_reason"],
                   nominal_worst=o["nominal"]["worst_vector"], robust_worst=o["robust"]["worst_vector"],
                   nominal_worst_case_ids=o["nominal"]["worst_case_ids"], robust_worst_case_ids=o["robust"]["worst_case_ids"])
    else:
        obs["infeasible_reasons"] = o["infeasible_reasons"]
    return obs


def make_pack(pack_id, purpose, ctx, src, env_raw, rule_keys, extra=None):
    exp = expected_for(ctx, env_raw)
    by_id = {r["id"]: r for r in ctx["records"]}
    used = sorted({x for c in env_raw["cases"] for x in c["disabled_source_ids"]})
    pack = {"pack_format": PACK_FORMAT, "pack_id": pack_id, "kind": "real_slice", "stage": 2, "purpose": purpose,
            "city_id": ctx["city_id"], "category": env_raw["plan"]["category"], "disclaimer": DISCLAIMER,
            "synthetic_parts": ["control points and weights", "candidate places and costs", "budget, max_selected, radius",
                                "the choice of records conditionally left out of each case"],
            "rules": {k: RULES[k] for k in ["fixed_before_computing", "plan", "labels", "objectives_and_price"] + rule_keys},
            "provenance": P8.provenance(ctx, src), "source_copy": P8.source_copy(ctx, env_raw["plan"]["category"]),
            "left_out_records": [{"id": x, "name": by_id[x]["name"], "qa_flags": by_id[x]["qa_flags"],
                                  "in_cases": [c["id"] for c in env_raw["cases"] if x in c["disabled_source_ids"]]} for x in used],
            "envelope": env_raw, "expected": exp, "observations": observations(exp)}
    if extra:
        pack.update(extra)
    return pack


def real_packs(ctx, src, cat, index):
    plan = P8.base_scenario(ctx, cat)
    tag = f"{ctx['city_id']}-{cat}"
    rank = relied_ranking(ctx, plan)
    r1, r2 = rank[0][0], rank[1][0]
    packs = [make_pack(f"{tag}-relied", "leave out the source records most control points rely on", ctx, src, envelope(plan, [
        case("top1", "Условно не учитываем запись, ближайшую к наибольшему весу точек", [r1]),
        case("top2", "Условно не учитываем две записи, ближайшие к наибольшему весу точек", [r1, r2]),
        case("second", "Условно не учитываем вторую по весу точек запись", [r2])]), ["relied"],
        {"relied_ranking": [{"id": i, "weight": w} for i, w in rank]})]
    ids = [r["id"] for r in ctx["records"] if r["group"] == cat]
    seed = SEED_BASE + index
    packs.append(make_pack(f"{tag}-seeded", "leave out 1, 2 or 3 records chosen by a recorded seed", ctx, src, envelope(
        copy.deepcopy(plan), [case(f"s{k}", f"Условно не учитываем {k} запис{'ь' if k == 1 else 'и'} по правилу seed {seed}",
                                   seeded_pick(ids, seed + 1000 * k, k)) for k in (1, 2, 3)]), ["seeded"], {"seed": seed}))
    flagged = sorted(r["id"] for r in ctx["records"] if r["group"] == cat and r["qa_flags"])
    if flagged:
        groups = sorted((g for g in ctx["qa_colocated"] if any(i in ids for i in g["ids"])), key=lambda g: (-len(g["ids"]), g["lon"]))
        cases = [case("qa_all", "Условно не учитываем все записи с QA-флагами (флаг не доказывает ошибку)", flagged)]
        if groups:
            cases.append(case("colocated", "Условно не учитываем записи из группы с одинаковыми координатами",
                              [i for i in groups[0]["ids"] if i in ids]))
        packs.append(make_pack(f"{tag}-qa", "leave out QA-flagged records (assumption about data quality)", ctx, src,
                               envelope(copy.deepcopy(plan), cases), ["qa"]))
        not_built = None
    else:
        not_built = {"pack_id": f"{tag}-qa", "reason": "no record of this category carries a QA flag in web/evidence.js"}
    return packs, not_built


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def build_real(app_root, src):
    cache = S8.load_app(app_root)
    packs, not_built = [], []
    for index, (city, cat) in enumerate(REAL_ORDER):
        ctx = S8.load_context(app_root, city, cache)
        p, nb = real_packs(ctx, src, cat, index)
        packs += p
        if nb:
            not_built.append(nb)
    return packs, not_built


def write_all(out, packs, not_built, src, app):
    out = Path(out)
    (out / "inputs").mkdir(parents=True, exist_ok=True)
    index = []
    for p in packs:
        write_json(out / f"{p['pack_id']}.json", p)
        if "envelope" in p:
            write_json(out / "inputs" / f"{p['pack_id']}.json", p["envelope"])
        o = p["observations"]
        index.append({"pack_id": p["pack_id"], "kind": p["kind"], "stage": p["stage"], "purpose": p["purpose"],
                      **{k: o.get(k) for k in ("status", "plans_identical", "price_of_robustness_m", "nominal", "robust",
                                                 "infeasible_reasons")},
                      "sha256": hashlib.sha256((out / f"{p['pack_id']}.json").read_bytes()).hexdigest()})
    write_json(out / "INDEX.json", {"pack_format": PACK_FORMAT, "generated_by": "k10res.envelopes + k10res.oracle_res",
                                    "build": src, "rules": RULES, "disclaimer": DISCLAIMER, "packs": index,
                                    "not_built": not_built, "input_manifest": S8.input_manifest(app) if app else None})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--branch", default="claude/beautiful-clarke-sbzomj")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    app = Path(a.app_root)
    src = {"commit": a.commit, "branch": a.branch, "data_js_sha256": S8.sha256_file(app / "web/data.js"),
           "evidence_js_sha256": S8.sha256_file(app / "web/evidence.js")}
    before = S8.input_manifest(app)
    packs, not_built = build_real(app, src)
    try:
        from . import edgecases  # stage 3: synthetic packs (separate module)
        packs += edgecases.synthetic_packs()
    except ImportError:
        pass
    after = S8.input_manifest(app)
    write_all(a.out, packs, not_built, src, app)
    print(json.dumps({"packs": len(packs), "not_built": not_built, "inputs_unchanged": before == after}, ensure_ascii=False))
    return 0 if before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
