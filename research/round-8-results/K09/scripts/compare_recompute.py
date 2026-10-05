#!/usr/bin/env python3
"""Сверка слепого пересчёта агрегатов (results/independent/blind_recompute/out.json) с summary.json и posthoc.json.

  python3 scripts/compare_recompute.py [results_dir]
"""
import json, sys
from pathlib import Path

K = Path(__file__).resolve().parents[1]


def main():
    R = Path(sys.argv[1]) if len(sys.argv) > 1 else K / "results"
    S = json.loads((R / "summary.json").read_text(encoding="utf-8"))
    P = json.loads((R / "posthoc.json").read_text(encoding="utf-8"))
    B = json.loads((R / "independent/blind_recompute/out.json").read_text(encoding="utf-8"))
    mism, n = [], 0

    def eq(path, ours, blind, tol=0.0):
        nonlocal n
        n += 1
        ok = (abs(float(ours) - float(blind)) <= tol) if isinstance(ours, float) or isinstance(blind, float) else ours == blind
        if not ok:
            mism.append({"path": path, "ours": ours, "blind": blind})

    for k, c in S["overall"].items():
        b = B["overall"][k]
        for f in ("n", "hits", "primary_equal", "primary_defined", "rel_positive_n", "unknown_worse", "rel_undefined"):
            eq(f"overall.{k}.{f}", c[f], b[f])
        eq(f"overall.{k}.rel_p90", c["rel_p90"], b["rel_p90"], 1e-9)
        eq(f"overall.{k}.rel_max", c["rel_max"], b["rel_max"], 1e-9)
        eq(f"overall.{k}.wilson_lo", c["wilson95"][0], b["wilson_lo"], 1e-6)
        eq(f"overall.{k}.wilson_hi", c["wilson95"][1], b["wilson_hi"], 1e-6)
    for k, lv in S["by_factor"]["slice"].items():
        for sl, c in lv.items():
            eq(f"slice.{k}.{sl}", c["hits"], B["by_slice_hits"][k][sl])
    for fac in ("n_candidates", "n_points", "budget_ratio", "weights"):
        for k, lv in S["by_factor"][fac].items():
            for l, c in lv.items():
                eq(f"{fac}.{k}.{l}", c["hits"], B["by_factor_hits"][fac][k][l])
    for o, m in S["g1_vs_g2_mcnemar"].items():
        b = B["mcnemar"][o]
        for ours, theirs in (("G1_only_hit", "G1_only"), ("G2_only_hit", "G2_only"), ("both_hit", "both"), ("both_miss", "neither")):
            eq(f"mcnemar.{o}.{ours}", m[ours], b[theirs])
    for o, d in P["size_distribution"].items():
        eq(f"size.{o}", d, B["size_distribution"][o])
    for k, c in P["nontrivial"].items():
        eq(f"nontrivial.{k}.n", c["n"], B["nontrivial"][k]["n"])
        eq(f"nontrivial.{k}.hits", c["hits"], B["nontrivial"][k]["hits"])
    for an in ("sec_max_selected", "sec_radius"):
        for k, lv in S["secondary"][an].items():
            for l, c in lv.items():
                eq(f"{an}.{k}.{l}", c["hits"], B["secondary"][an][k][l])
    eq("distinct_exact_plans", S["exact_plans"]["distinct_plans_across_objectives"], B["distinct_exact_plans"])
    viol = {k: v for k, v in B.get("sanity", {}).items() if isinstance(v, int) and v != 0 and k[0] in "abcdef"}
    rep = {"compared": n, "mismatches": len(mism), "details": mism, "blind_sanity_nonzero": viol}
    (R / "independent/compare_recompute_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "details"}, ensure_ascii=False))
    for m in mism[:20]:
        print(m)
    sys.exit(1 if mism or viol else 0)


if __name__ == "__main__":
    main()
