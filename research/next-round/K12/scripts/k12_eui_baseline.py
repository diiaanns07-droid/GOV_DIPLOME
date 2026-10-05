"""K12: offline check of the simplest audit-ranking baseline (A09 section 7):
rank school buildings by EUI = annual electricity kWh / floor area m2, take top 20%.

Inputs: ../data/K12_bdg1_*.csv built by k12_build_extract.py from BDG1 (pinned commit).
Data are REAL but INTERNATIONAL. The UK subset (74 buildings, one weather file, one period
Dec 2014 - Nov 2015) stands in for "one city's school network". It is NOT Shymkent or Astana.

Checks:
  C1  input QC that changes the ranking (coverage, peak-hour missingness, EUI outliers)
  C2  annualisation method: uniform scaling (as in A09) vs month scaling vs hour-profile imputation
  C3  floor-area error (log-normal, sigma 0.1..0.5) -> stability of top 20% and P(top) per building
  C4  cross-check of A09 numbers (A09_bdg1_per_building_results.csv, A09 summary E3/EUI quantiles)

Usage:  python k12_eui_baseline.py           (no network; writes ../results/)
"""
import json
import pathlib
import platform

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
DATA, RES = HERE.parent / "data", HERE.parent / "results"
A09_DIR = HERE.parents[2] / "govtech-results/09_energy/extracted_files__18_"
SEED, N_SIM, TOP_SHARE = 12, 2000, 0.2
SIGMAS = (0.1, 0.2, 0.3, 0.5)
UK_TZ = "Europe/London"


def annual_table(monthly, meta, qc):
    g = monthly.groupby("uid")
    t = pd.DataFrame({
        "kwh_obs": g.kwh_observed_sum.sum(),
        "hours_exp": g.hours_expected.sum(),
        "hours_obs": g.hours_observed.sum(),
        "kwh_imputed": g.kwh_with_imputed_hours.sum(),
        "min_month_coverage": (monthly.hours_observed / monthly.hours_expected).groupby(monthly.uid).min(),
        "months": g.size(),
    })
    t["kwh_uniform"] = t.kwh_obs * t.hours_exp / t.hours_obs
    month_scaled = monthly.kwh_observed_sum * monthly.hours_expected / monthly.hours_observed
    t["kwh_month_scaled"] = month_scaled.groupby(monthly.uid).sum()
    t = t.join(meta.set_index("uid")[["timezone", "sqm", "subindustry", "industry", "heatingtype"]])
    t = t.join(qc.set_index("uid")[["missing_share_in_weekday_09_15", "expected_share_weekday_09_15"]])
    t["coverage"] = t.hours_obs / t.hours_exp
    t["peak_missing_ratio"] = t.missing_share_in_weekday_09_15 / t.expected_share_weekday_09_15
    for k in ("uniform", "month_scaled", "imputed"):
        t[f"eui_{k}"] = t[f"kwh_{k}"] / t.sqm
    return t


def top_set(series, k):
    return set(series.nlargest(k).index)


def area_mc(t, eui_col, kwh_col, k, rng):
    """Multiplicative log-normal error on floor area; returns overlap stats and P(top-k)."""
    true_top = top_set(t[eui_col], k)
    out, p_top = {}, None
    for sig in SIGMAS:
        hits = pd.Series(0, index=t.index)
        ov = np.empty(N_SIM)
        for i in range(N_SIM):
            noisy = t[kwh_col] / (t.sqm * np.exp(rng.normal(0.0, sig, len(t))))
            s = top_set(noisy, k)
            ov[i] = len(true_top & s) / k
            hits[list(s)] += 1
        out[f"sigma_log_{sig}"] = {"mean_overlap": round(float(ov.mean()), 3),
                                   "p10_overlap": round(float(np.percentile(ov, 10)), 3)}
        if sig == 0.2:
            p_top = hits / N_SIM
    return out, p_top


def main():
    meta = pd.read_csv(DATA / "K12_bdg1_schools_meta.csv")
    monthly = pd.read_csv(DATA / "K12_bdg1_schools_monthly.csv")
    qc = pd.read_csv(DATA / "K12_bdg1_schools_qc.csv")
    rng = np.random.default_rng(SEED)
    t = annual_table(monthly, meta, qc)
    R = {"kind": "derived from real international open data (BDG1); NOT Shymkent/Astana",
         "seed": SEED, "n_sim": N_SIM, "top_share": TOP_SHARE}

    # ---- C1/C2/C3 on the UK subset: one weather file, one period, one country --------------
    uk = t[t.timezone == UK_TZ].copy()
    k = int(round(TOP_SHARE * len(uk)))
    p10, p90 = uk.eui_imputed.quantile([0.1, 0.9])
    uk["flag_low_coverage"] = uk.coverage < 0.95
    uk["flag_month_below_80pct"] = uk.min_month_coverage < 0.8
    uk["flag_peak_missing_ge_1_5x"] = uk.peak_missing_ratio >= 1.5
    uk["flag_eui_below_p10_check_meter_zone_or_area"] = uk.eui_imputed < p10
    uk["flag_eui_above_p90"] = uk.eui_imputed > p90
    R["uk"] = {
        "n_buildings": int(len(uk)), "k_top": k,
        "subindustry": uk.subindustry.value_counts().to_dict(),
        "heatingtype": uk.heatingtype.fillna("unknown").value_counts().to_dict(),
        "coverage_median": round(float(uk.coverage.median()), 4),
        "peak_missing_ratio_median": round(float(uk.peak_missing_ratio.median()), 2),
        "eui_imputed_quantiles": uk.eui_imputed.quantile([.1, .25, .5, .75, .9]).round(1).to_dict(),
        "annual_bias_uniform_vs_imputed_pct": {
            "median": round(float((100 * (uk.kwh_uniform / uk.kwh_imputed - 1)).median()), 2),
            "min": round(float((100 * (uk.kwh_uniform / uk.kwh_imputed - 1)).min()), 2),
            "max": round(float((100 * (uk.kwh_uniform / uk.kwh_imputed - 1)).max()), 2)},
        "qc_flag_counts": {c: int(uk[c].sum()) for c in uk.columns if c.startswith("flag_")},
    }
    base = top_set(uk.eui_imputed, k)
    R["uk"]["C2_top_overlap_vs_imputed"] = {
        m: round(len(base & top_set(uk[f"eui_{m}"], k)) / k, 3) for m in ("uniform", "month_scaled")}
    R["uk"]["C2_changed_members_uniform_vs_imputed"] = sorted(base ^ top_set(uk.eui_uniform, k))
    mc, p_top = area_mc(uk, "eui_imputed", "kwh_imputed", k, rng)
    R["uk"]["C3_area_error_top_overlap"] = mc
    uk["p_top_sigma_0_2"] = p_top.reindex(uk.index)
    R["uk"]["C3_sigma_0_2_p_top_bands"] = {
        "certain_ge_0_9": int((uk.p_top_sigma_0_2 >= 0.9).sum()),
        "uncertain_0_1_to_0_9": int(uk.p_top_sigma_0_2.between(0.1, 0.9, inclusive="neither").sum()),
        "outside_le_0_1": int((uk.p_top_sigma_0_2 <= 0.1).sum())}

    ranking = uk.sort_values("eui_imputed", ascending=False)
    ranking.insert(0, "rank_eui_imputed", range(1, len(ranking) + 1))
    ranking["in_top_k_point_estimate"] = ranking.index.isin(base)
    cols = ["rank_eui_imputed", "sqm", "subindustry", "heatingtype", "coverage", "peak_missing_ratio",
            "kwh_uniform", "kwh_imputed", "eui_uniform", "eui_imputed", "in_top_k_point_estimate",
            "p_top_sigma_0_2"] + [c for c in ranking.columns if c.startswith("flag_")]
    RES.mkdir(parents=True, exist_ok=True)
    ranking[cols].round(4).to_csv(RES / "K12_uk_schools_eui_ranking.csv", index_label="uid")

    # ---- C4: cross-check A09 on all 105 buildings ---------------------------------------
    a09 = pd.read_csv(A09_DIR / "A09_bdg1_per_building_results.csv").set_index("uid")
    a09s = json.loads((A09_DIR / "A09_bdg1_experiment_summary.json").read_text())
    j = t.join(a09[["annual_kwh", "eui_kwh_m2"]], how="inner")
    rel = 100 * (j.kwh_uniform / j.annual_kwh - 1)
    k_all = max(1, int(round(TOP_SHARE * len(t))))
    mc_all, _ = area_mc(t, "eui_uniform", "kwh_uniform", k_all, rng)
    R["a09_crosscheck_all105"] = {
        "n_matched": int(len(j)),
        "annual_kwh_uniform_vs_a09_rel_diff_pct": {"median_abs": round(float(rel.abs().median()), 3),
                                                   "max_abs": round(float(rel.abs().max()), 3)},
        "eui_uniform_quantiles_k12": t.eui_uniform.quantile([.1, .25, .5, .75, .9]).round(1).to_dict(),
        "eui_quantiles_a09_reported": a09s["eui_kwh_m2_quantiles"],
        "E3_k12": {"k": k_all, **mc_all},
        "E3_a09_reported": {"k": a09s["E3_k"], **a09s["E3_area_error_top20_overlap"]},
        "subindustry_all105": t.subindustry.value_counts().to_dict(),
        "industry_all105": t.industry.value_counts().to_dict(),
        "lowest_eui_buildings": t.eui_uniform.nsmallest(5).round(2).to_dict(),
        "peak_missing_ratio_median_non_uk": round(float(t[t.timezone != UK_TZ].peak_missing_ratio.median()), 2),
    }
    R["versions"] = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    (RES / "K12_baseline_results.json").write_text(json.dumps(R, indent=2, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(R, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
