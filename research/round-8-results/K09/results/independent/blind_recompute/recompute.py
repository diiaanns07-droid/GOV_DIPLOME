#!/usr/bin/env python3
"""Blind recompute of K09 aggregates directly from raw runs.csv / scenarios.csv.

Independent of the project's own aggregation code. Python 3 stdlib only.
"""
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict, OrderedDict
from decimal import Decimal

BASE = "/home/user/GOV_DIPLOME/research/round-8-results/K09/results"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(OUT_DIR, "out.json")
Z = 1.959963984540054
AO_ORDER = [f"{a}/{o}" for a in ("G1", "G2") for o in ("mean", "minimax", "coverage")]
OBJS = ["mean", "minimax", "coverage"]
FACTORS = ["n_candidates", "n_points", "budget_ratio", "weights"]


def ids_of(s):
    s = s.strip()
    return s.split() if s else []


def wilson(h, n):
    if n == 0:
        return None, None
    p = h / n
    z2 = Z * Z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return round(lo, 6), round(hi, 6)


def nearest_rank(vals, q):
    v = sorted(vals)
    if not v:
        return None
    idx = math.ceil(q * len(v)) - 1
    idx = max(0, min(idx, len(v) - 1))
    return v[idx]


def num_key(s):
    try:
        return (0, float(s), s)
    except ValueError:
        return (1, 0.0, s)


def sorted_dict(d):
    return OrderedDict((k, d[k]) for k in sorted(d, key=num_key))


def main():
    with open(os.path.join(BASE, "runs.csv"), newline="") as f:
        rd = csv.DictReader(f)
        run_header = rd.fieldnames
        runs = list(rd)
    with open(os.path.join(BASE, "scenarios.csv"), newline="") as f:
        rd = csv.DictReader(f)
        scen_header = rd.fieldnames
        scens = list(rd)

    anomalies = []
    notes = []

    # ---- scenario index
    scen_by_key = {}
    dup_scen = 0
    for s in scens:
        if s["scenario_key"] in scen_by_key:
            dup_scen += 1
        scen_by_key[s["scenario_key"]] = s
    if dup_scen:
        anomalies.append(f"scenarios.csv: {dup_scen} duplicate scenario_key rows")

    main_rows = [r for r in runs if r["analysis"] == "main"]

    # ---- overall
    overall = OrderedDict()
    for ao in AO_ORDER:
        a, o = ao.split("/")
        rr = [r for r in main_rows if r["algorithm"] == a and r["objective"] == o]
        n = len(rr)
        hits = sum(int(r["hit"]) for r in rr)
        pe = sum(1 for r in rr if r["primary_equal"] == "1")
        pdef = sum(1 for r in rr if r["primary_equal"] != "")
        rels = [Decimal(r["rel_gap"]) for r in rr if r["rel_gap"] != ""]
        relpos = sum(1 for x in rels if x > 0)
        p90 = nearest_rank(rels, 0.9)
        rmax = max(rels) if rels else None
        uw = sum(int(r["unknown_worse"]) for r in rr)
        lo, hi = wilson(hits, n)
        overall[ao] = OrderedDict([
            ("n", n),
            ("hits", hits),
            ("primary_equal", pe),
            ("primary_defined", pdef),
            ("rel_positive_n", relpos),
            ("rel_p90", float(p90) if p90 is not None else None),
            ("rel_max", float(rmax) if rmax is not None else None),
            ("unknown_worse", uw),
            ("rel_undefined", n - len(rels)),
            ("wilson_lo", lo),
            ("wilson_hi", hi),
        ])

    # ---- by slice
    by_slice = OrderedDict()
    for ao in AO_ORDER:
        a, o = ao.split("/")
        c = Counter()
        for r in main_rows:
            if r["algorithm"] == a and r["objective"] == o:
                c[r["slice"]] += int(r["hit"])
        # ensure zero-hit slices are present
        for r in main_rows:
            c.setdefault(r["slice"], 0)
        by_slice[ao] = OrderedDict(sorted(c.items()))

    # ---- by factor
    by_factor = OrderedDict()
    for fac in FACTORS:
        levels = sorted({r[fac] for r in main_rows}, key=num_key)
        d = OrderedDict()
        for ao in AO_ORDER:
            a, o = ao.split("/")
            c = OrderedDict((lv, 0) for lv in levels)
            for r in main_rows:
                if r["algorithm"] == a and r["objective"] == o:
                    c[r[fac]] += int(r["hit"])
            d[ao] = c
        by_factor[fac] = d

    # ---- mcnemar
    pair = defaultdict(dict)  # (key, obj) -> {alg: hit}
    for r in main_rows:
        k = (r["scenario_key"], r["objective"])
        if r["algorithm"] in pair[k]:
            anomalies.append(f"duplicate main row for {k} {r['algorithm']}")
        pair[k][r["algorithm"]] = int(r["hit"])
    mcn = OrderedDict()
    for o in OBJS:
        c = OrderedDict([("G1_only", 0), ("G2_only", 0), ("both", 0), ("neither", 0)])
        unpaired = 0
        for (k, oo), d in pair.items():
            if oo != o:
                continue
            if "G1" not in d or "G2" not in d:
                unpaired += 1
                continue
            g1, g2 = d["G1"], d["G2"]
            if g1 and g2:
                c["both"] += 1
            elif g1:
                c["G1_only"] += 1
            elif g2:
                c["G2_only"] += 1
            else:
                c["neither"] += 1
        if unpaired:
            anomalies.append(f"mcnemar {o}: {unpaired} unpaired scenario_keys")
        mcn[o] = c

    # ---- size distribution (main, G1)
    sizedist = OrderedDict()
    for o in OBJS:
        c = Counter(len(ids_of(r["exact_ids"])) for r in main_rows
                    if r["algorithm"] == "G1" and r["objective"] == o)
        sizedist[o] = OrderedDict((str(k), c[k]) for k in sorted(c))

    # ---- nontrivial
    nontriv = OrderedDict()
    for ao in AO_ORDER:
        a, o = ao.split("/")
        rr = [r for r in main_rows if r["algorithm"] == a and r["objective"] == o
              and len(ids_of(r["exact_ids"])) >= 2]
        nontriv[ao] = OrderedDict([("n", len(rr)), ("hits", sum(int(r["hit"]) for r in rr))])

    # ---- secondary
    secondary = OrderedDict()
    for an, col in (("sec_max_selected", "max_selected"), ("sec_radius", "radius_m")):
        rows_an = [r for r in runs if r["analysis"] == an]
        levels = sorted({r[col] for r in rows_an}, key=num_key)
        d = OrderedDict()
        for ao in AO_ORDER:
            a, o = ao.split("/")
            c = OrderedDict((lv, 0) for lv in levels)
            for r in rows_an:
                if r["algorithm"] == a and r["objective"] == o:
                    c[r[col]] += int(r["hit"])
            d[ao] = c
        secondary[an] = d
        # also n per level for context
    sec_n = OrderedDict()
    for an, col in (("sec_max_selected", "max_selected"), ("sec_radius", "radius_m")):
        rows_an = [r for r in runs if r["analysis"] == an]
        sec_n[an] = sorted_dict(Counter(r[col] for r in rows_an
                                        if r["algorithm"] == "G1" and r["objective"] == "mean"))

    # ---- distinct exact plans
    dep = Counter(s["distinct_exact_plans"] for s in scens if s["analysis"] == "main")
    distinct = OrderedDict((k, dep.get(k, 0)) for k in ("1", "2", "3"))
    for k in dep:
        if k not in distinct:
            anomalies.append(f"distinct_exact_plans has unexpected value {k!r} x{dep[k]}")

    # ---- sanity
    a_cnt = b_cnt = c_cnt = d_cnt = e_cnt = f_cnt = 0
    d_missing = 0
    for r in runs:
        g = ids_of(r["greedy_ids"])
        x = ids_of(r["exact_ids"])
        hit = int(r["hit"])
        if hit == 1 and r["greedy_ids"].strip() != r["exact_ids"].strip():
            a_cnt += 1
        if hit == 1 and int(r["greedy_cost"]) != int(r["exact_cost"]):
            b_cnt += 1
        if r["abs_gap"] != "" and int(r["abs_gap"]) < 0:
            c_cnt += 1
        s = scen_by_key.get(r["scenario_key"])
        if s is None:
            d_missing += 1
        elif int(r["greedy_cost"]) > int(s["budget"]):
            d_cnt += 1
        if len(g) > int(r["max_selected"]):
            e_cnt += 1
        if len(x) <= 1 and hit == 0:
            f_cnt += 1
    keys_per_an = defaultdict(set)
    rows_per_key = Counter()
    for r in runs:
        keys_per_an[r["analysis"]].add(r["scenario_key"])
        rows_per_key[r["scenario_key"]] += 1
    h_cnt = sum(1 for k, v in rows_per_key.items() if v != 6)
    sanity = OrderedDict([
        ("a", a_cnt),   # hit==1 but greedy_ids != exact_ids
        ("b", b_cnt),   # hit==1 but greedy_cost != exact_cost
        ("c", c_cnt),   # abs_gap present and < 0
        ("d", d_cnt),   # greedy_cost > scenario budget
        ("e", e_cnt),   # len(greedy_ids) > max_selected
        ("f", f_cnt),   # <=1 id in exact_ids and hit==0
        ("g", OrderedDict(sorted((k, len(v)) for k, v in keys_per_an.items()))),  # distinct keys per analysis
        ("h", h_cnt),   # scenario_keys whose row count != 6
    ])
    sanity_legend = {"a": "hit==1 but greedy_ids != exact_ids", "b": "hit==1 but greedy_cost != exact_cost",
                     "c": "abs_gap present and < 0", "d": "greedy_cost > budget (join scenarios.csv)",
                     "d_missing_scenario_join": d_missing,
                     "e": "len(greedy_ids) > max_selected", "f": "<=1 id in exact_ids and hit==0",
                     "g": "distinct scenario_keys per analysis", "h": "scenario_keys with rows != 6"}

    # ================= extra internal consistency checks =================
    extra = OrderedDict()
    # duplicates of (key, objective, algorithm)
    trip = Counter((r["scenario_key"], r["objective"], r["algorithm"]) for r in runs)
    extra["dup_key_obj_alg"] = sum(1 for v in trip.values() if v > 1)
    # full-row duplicates
    full = Counter(tuple(r[c] for c in run_header) for r in runs)
    extra["dup_full_rows"] = sum(v - 1 for v in full.values() if v > 1)
    # scenario_key in runs but not in scenarios and vice versa
    rk = set(rows_per_key)
    sk = set(scen_by_key)
    extra["run_keys_not_in_scenarios"] = len(rk - sk)
    extra["scenario_keys_not_in_runs"] = len(sk - rk)
    # run fields vs scenario fields
    shared = [c for c in ("analysis", "slice", "n_candidates", "n_points", "budget_ratio", "weights",
                          "max_selected", "radius_m", "seed") if c in scen_header]
    mism = Counter()
    for r in runs:
        s = scen_by_key.get(r["scenario_key"])
        if s is None:
            continue
        for c in shared:
            if r[c] != s[c]:
                mism[c] += 1
    extra["run_vs_scenario_field_mismatch"] = dict(mism)
    # scenario_key encodes fields?
    key_mism = 0
    for r in runs:
        parts = r["scenario_key"].split("|")
        try:
            exp = [r["analysis"], r["slice"], "nc" + r["n_candidates"], "np" + r["n_points"],
                   "br" + r["budget_ratio"], r["weights"], "ms" + r["max_selected"],
                   "r" + r["radius_m"], "s" + r["seed"]]
        except KeyError:
            continue
        if parts != exp:
            key_mism += 1
    extra["scenario_key_vs_columns_mismatch"] = key_mism
    # exact_ids in runs vs scenarios.csv exact_<obj>_ids
    ex_mism = 0
    ex_mism_examples = []
    for r in runs:
        s = scen_by_key.get(r["scenario_key"])
        if s is None:
            continue
        col = f"exact_{r['objective']}_ids"
        if col in s and s[col].strip() != r["exact_ids"].strip():
            ex_mism += 1
            if len(ex_mism_examples) < 5:
                ex_mism_examples.append((r["scenario_key"], r["objective"], r["algorithm"], r["exact_ids"], s[col]))
    extra["exact_ids_runs_vs_scenarios_mismatch"] = ex_mism
    if ex_mism_examples:
        extra["exact_ids_mismatch_examples"] = ex_mism_examples
    # exact_ids / exact_cost same across G1, G2
    grp = defaultdict(set)
    for r in runs:
        grp[(r["scenario_key"], r["objective"])].add((r["exact_ids"], r["exact_cost"]))
    extra["exact_plan_differs_between_G1_G2"] = sum(1 for v in grp.values() if len(v) > 1)
    # distinct_exact_plans consistent with three exact id columns
    dep_mism = 0
    dep_examples = []
    for s in scens:
        n_d = len({s["exact_mean_ids"].strip(), s["exact_minimax_ids"].strip(), s["exact_coverage_ids"].strip()})
        if str(n_d) != s["distinct_exact_plans"]:
            dep_mism += 1
            if len(dep_examples) < 5:
                dep_examples.append((s["scenario_key"], s["distinct_exact_plans"], s["exact_mean_ids"],
                                     s["exact_minimax_ids"], s["exact_coverage_ids"]))
    extra["distinct_exact_plans_vs_id_columns_mismatch"] = dep_mism
    if dep_examples:
        extra["distinct_exact_plans_mismatch_examples"] = dep_examples
    # exact plan feasibility
    ex_over_budget = ex_over_ms = 0
    for r in runs:
        s = scen_by_key.get(r["scenario_key"])
        if s is not None and int(r["exact_cost"]) > int(s["budget"]):
            ex_over_budget += 1
        if len(ids_of(r["exact_ids"])) > int(r["max_selected"]):
            ex_over_ms += 1
    extra["exact_cost_over_budget"] = ex_over_budget
    extra["exact_ids_over_max_selected"] = ex_over_ms
    # ids sorted / unique / within candidate range
    unsorted = dupid = 0
    for r in runs:
        for col in ("greedy_ids", "exact_ids"):
            ids = ids_of(r[col])
            if ids != sorted(ids):
                unsorted += 1
            if len(ids) != len(set(ids)):
                dupid += 1
    extra["id_lists_not_sorted"] = unsorted
    extra["id_lists_with_duplicate_ids"] = dupid
    # id outside candidate range (cNN numbering assumption, 1-based or 0-based)
    out_of_range = 0
    for r in runs:
        nc = int(r["n_candidates"])
        for col in ("greedy_ids", "exact_ids"):
            for i in ids_of(r[col]):
                if i.startswith("c") and i[1:].isdigit():
                    v = int(i[1:])
                    if v > nc or v < 0:
                        out_of_range += 1
    extra["ids_numerically_above_n_candidates"] = out_of_range
    # empty-plan cost != 0
    extra["empty_plan_nonzero_cost"] = sum(
        1 for r in runs for col, cc in (("greedy_ids", "greedy_cost"), ("exact_ids", "exact_cost"))
        if ids_of(r[col]) == [] and int(r[cc]) != 0)
    # same id set -> same cost
    extra["same_ids_diff_cost"] = sum(1 for r in runs if r["greedy_ids"].strip() == r["exact_ids"].strip()
                                      and r["greedy_cost"] != r["exact_cost"])
    # same ids but hit==0
    extra["same_ids_but_hit0"] = sum(1 for r in runs if r["greedy_ids"].strip() == r["exact_ids"].strip()
                                     and r["hit"] == "0")
    # hit=1 but abs_gap != 0, or primary_equal != 1
    extra["hit1_abs_gap_nonzero"] = sum(1 for r in runs if r["hit"] == "1" and r["abs_gap"] not in ("", "0"))
    extra["hit1_primary_equal_ne_1"] = sum(1 for r in runs if r["hit"] == "1" and r["primary_equal"] != "1")
    extra["hit1_rel_gap_nonzero"] = sum(1 for r in runs if r["hit"] == "1" and r["rel_gap"] != ""
                                        and Decimal(r["rel_gap"]) != 0)
    # primary_equal==1 vs abs_gap==0
    extra["primary_equal1_abs_gap_nonzero"] = sum(1 for r in runs if r["primary_equal"] == "1"
                                                  and r["abs_gap"] not in ("", "0"))
    extra["primary_equal0_abs_gap_zero"] = sum(1 for r in runs if r["primary_equal"] == "0"
                                               and r["abs_gap"] == "0")
    extra["primary_equal0_abs_gap_le0"] = sum(1 for r in runs if r["primary_equal"] == "0"
                                              and r["abs_gap"] != "" and int(r["abs_gap"]) <= 0)
    extra["abs_gap_empty"] = sum(1 for r in runs if r["abs_gap"] == "")
    extra["rel_gap_empty"] = sum(1 for r in runs if r["rel_gap"] == "")
    extra["rel_gap_empty_abs_gap_nonzero"] = sum(1 for r in runs if r["rel_gap"] == "" and r["abs_gap"] not in ("", "0"))
    extra["rel_gap_empty_abs_gap_zero"] = sum(1 for r in runs if r["rel_gap"] == "" and r["abs_gap"] == "0")
    extra["rel_gap_negative"] = sum(1 for r in runs if r["rel_gap"] != "" and Decimal(r["rel_gap"]) < 0)
    extra["rel_gap_sign_vs_abs_gap_sign_mismatch"] = sum(
        1 for r in runs if r["rel_gap"] != "" and r["abs_gap"] != ""
        and (Decimal(r["rel_gap"]) > 0) != (int(r["abs_gap"]) > 0))
    # rel_gap empty by objective/algorithm/analysis
    extra["rel_gap_empty_by_analysis_alg_obj"] = dict(Counter(
        f"{r['analysis']}|{r['algorithm']}/{r['objective']}" for r in runs if r["rel_gap"] == ""))
    # hit==0 but primary_equal==1 (tie on objective, differing plan)
    extra["hit0_primary_equal1"] = sum(1 for r in runs if r["hit"] == "0" and r["primary_equal"] == "1")
    extra["hit0_primary_equal1_main"] = sum(1 for r in main_rows if r["hit"] == "0" and r["primary_equal"] == "1")
    # replaced_by_best_single only on G2
    extra["G1_replaced_nonempty"] = sum(1 for r in runs if r["algorithm"] == "G1" and r["replaced_by_best_single"] != "")
    extra["G2_replaced_empty"] = sum(1 for r in runs if r["algorithm"] == "G2" and r["replaced_by_best_single"] == "")
    extra["G2_replaced1_greedy_ids_ne1"] = sum(1 for r in runs if r["algorithm"] == "G2" and
                                              r["replaced_by_best_single"] == "1" and len(ids_of(r["greedy_ids"])) != 1)
    # steps vs greedy plan size
    extra["G1_steps_ne_len_greedy"] = sum(1 for r in runs if r["algorithm"] == "G1"
                                          and int(r["steps"]) != len(ids_of(r["greedy_ids"])))
    extra["G2_steps_ne_len_greedy_not_replaced"] = sum(
        1 for r in runs if r["algorithm"] == "G2" and r["replaced_by_best_single"] == "0"
        and int(r["steps"]) != len(ids_of(r["greedy_ids"])))
    # G1/G2 greedy plan identical when G2 not replaced? (informational)
    g = {}
    for r in runs:
        g[(r["scenario_key"], r["objective"], r["algorithm"])] = r
    g1g2_diff_notrep = 0
    for (k, o, a), r in g.items():
        if a == "G2" and r["replaced_by_best_single"] == "0":
            r1 = g.get((k, o, "G1"))
            if r1 and r1["greedy_ids"] != r["greedy_ids"]:
                g1g2_diff_notrep += 1
    extra["G2_not_replaced_but_greedy_differs_from_G1"] = g1g2_diff_notrep
    # G2 replaced but greedy same as G1 (informational)
    extra["G2_replaced_but_greedy_same_as_G1"] = sum(
        1 for (k, o, a), r in g.items() if a == "G2" and r["replaced_by_best_single"] == "1"
        and g.get((k, o, "G1")) and g[(k, o, "G1")]["greedy_ids"] == r["greedy_ids"])
    # unknown_worse values
    extra["unknown_worse_nonzero"] = sum(1 for r in runs if r["unknown_worse"] != "0")
    # feasible_count / subsets_total sanity in scenarios
    st_bad = 0
    fc_bad = 0
    for s in scens:
        try:
            nc = int(s["n_candidates"])
            if int(s["subsets_total"]) != 2 ** nc:
                st_bad += 1
            if int(s["feasible_count"]) < 1 or int(s["feasible_count"]) > int(s["subsets_total"]):
                fc_bad += 1
        except (KeyError, ValueError):
            pass
    extra["subsets_total_ne_2pow_nc"] = st_bad
    extra["feasible_count_out_of_range"] = fc_bad
    # budget vs budget_ratio: not checkable without candidate costs; record per-analysis rows
    extra["scenarios_rows_per_analysis"] = dict(Counter(s["analysis"] for s in scens))
    # duplicate problem_digest across scenarios
    pd = Counter(s["problem_digest"] for s in scens if "problem_digest" in s)
    extra["problem_digest_duplicates"] = sum(v - 1 for v in pd.values() if v > 1)
    # design balance: main scenarios per factor combination
    combo = Counter((s["slice"], s["n_candidates"], s["n_points"], s["budget_ratio"], s["weights"])
                    for s in scens if s["analysis"] == "main")
    extra["main_design_cells"] = len(combo)
    extra["main_scenarios_per_cell"] = dict(Counter(combo.values()))
    # coupling of factors (are n_candidates/n_points coupled?)
    extra["main_nc_np_pairs"] = sorted({(r["n_candidates"], r["n_points"]) for r in main_rows})
    # seeds per cell
    seeds = Counter(s["seed"] for s in scens if s["analysis"] == "main")
    extra["main_seed_values"] = len(seeds)

    out = OrderedDict([
        ("overall", overall),
        ("by_slice_hits", by_slice),
        ("by_factor_hits", by_factor),
        ("mcnemar", mcn),
        ("size_distribution", sizedist),
        ("nontrivial", nontriv),
        ("secondary", secondary),
        ("distinct_exact_plans", distinct),
        ("sanity", sanity),
    ])
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(OUT_DIR, "extra_checks.json"), "w") as f:
        json.dump(OrderedDict([("sanity_legend", sanity_legend), ("secondary_n_per_level_G1_mean", sec_n), ("checks", extra),
                               ("anomalies", anomalies)]), f, indent=1, ensure_ascii=False, default=str)
        f.write("\n")
    print(json.dumps(out, indent=1))
    print("---- extra")
    print(json.dumps(extra, indent=1, default=str))
    print("---- anomalies", anomalies)


if __name__ == "__main__":
    main()
