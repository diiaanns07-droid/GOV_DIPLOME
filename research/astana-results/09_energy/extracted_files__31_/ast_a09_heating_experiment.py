"""AST-A09 heating-normalisation experiment.

SYNTHETIC school building driven by a REAL cold-climate daily temperature series
(BDG1 weather3.csv, US site, tz America/Chicago, 2014-05-01..2015-05-01, MIT licence).
NOT Astana weather, NOT an Astana building.  Question tested:
  can monthly heat bills + outdoor temperature alone separate envelope-retrofit
  savings from weather, schedule (shift) changes, control changes, unregulated
  district-heat supply (no building substation) and norm-based billing?
All building parameters below are ASSUMPTIONS for the illustration.
"""
import json, numpy as np, pandas as pd

W = "/home/claude/bdg1/the-building-data-genome-project-master/data/external/weather/weather3.csv"
w = pd.read_csv(W)
t = pd.to_datetime(w["DateUTC<br />"].str.replace("<br />", "", regex=False), utc=True, errors="coerce")
tc = pd.to_numeric(w["TemperatureC"], errors="coerce"); tc[(tc < -60) | (tc > 60)] = np.nan
s = pd.Series(tc.values, index=t).dropna(); s = s[~s.index.duplicated()].sort_index()
T1 = s.tz_convert("America/Chicago").resample("1D").mean().interpolate(limit=3)
T1 = T1["2014-05-01":"2015-04-30"].copy()
days = pd.date_range("2025-05-01", periods=len(T1), freq="1D")   # relabel to a generic school year
T1.index = days
T2 = T1 + 1.5                                                    # SYNTHETIC warmer reporting year

A = 5000.0                     # m2 heated area (assumption)
H0, H1 = 10000.0, 8000.0       # W/K before / after envelope retrofit (-20%, assumption)
G_OCC, G_UNOCC = 15.0, 2.0     # W/m2 internal gains (assumption)
T_OCC, T_SETBACK = 20.0, 16.0  # degC
KWH_PER_GCAL = 1163.0

def heating_on(T):             # assumption: heating season while 5-day mean < +8 degC
    return (T.rolling(5, min_periods=1).mean() < 8.0).values

def school_day(idx):           # synthetic KZ-like calendar (assumption)
    d = pd.Series(idx)
    term = ~d.dt.month.isin([6, 7, 8])
    wk = d.dt.dayofweek < 5
    hol = ((d >= "2025-11-03") & (d <= "2025-11-09")) | ((d >= "2025-12-30") & (d <= "2026-01-08")) | \
          ((d >= "2026-03-20") & (d <= "2026-03-29"))
    return (term & wk & ~hol).values

def demand(T, H, occ_hours, setback=True):
    """Daily heat demand kWh_th of a building with its own control (substation)."""
    on = heating_on(T); sd = school_day(T.index); out = np.zeros(len(T))
    for i, (tout, o, dsch) in enumerate(zip(T.values, on, sd)):
        if not o: continue
        q = 0.0
        for h in range(24):
            occ = dsch and (8 <= h < 8 + occ_hours)
            tset = T_OCC if (occ or not setback) else T_SETBACK
            gain = (G_OCC if occ else G_UNOCC) * A
            q += max(0.0, H * (tset - tout) - gain)
        out[i] = q / 1000.0
    return pd.Series(out, index=T.index)

def network_supply(T, H_design):
    """Unregulated district heat: delivered heat follows outdoor temperature only."""
    on = heating_on(T)
    return pd.Series(np.where(on, H_design * np.maximum(0, 20.0 - T.values) * 24 / 1000.0, 0.0), index=T.index)

def norm_bill(T, gcal_per_m2_month=0.02):
    """Norm-based billing: flat charge in heating months (norm value is an assumption)."""
    on = pd.Series(heating_on(T), index=T.index).resample("MS").mean() > 0.5
    return pd.Series(np.where(on, gcal_per_m2_month * A * KWH_PER_GCAL, 0.0), index=on.index)

def monthly(x): return x.resample("MS").sum() if len(x) > 40 else x

def hdd(T, base): return np.maximum(0, base - T).resample("MS").sum()

def fit_predict(y1, X1, X2):
    b = np.linalg.lstsq(X1, y1, rcond=None)[0]; return X2 @ b, b

def estimators(y1, y2, T1, T2, sched1, sched2):
    """Return savings estimates (kWh) = predicted-baseline-in-reporting-period - actual."""
    m1, m2 = monthly(y1), monthly(y2)
    act1 = m1.values; act2 = m2.values; hm1 = act1 > 0; hm2 = act2 > 0
    res = {"naive_year_on_year": float(act1.sum() - act2.sum())}
    # fixed-base HDD18 regression on heating months
    for name, base in (("hdd18_fixed", 18.0),):
        X1 = np.column_stack([np.ones(hm1.sum()), hdd(T1, base).values[hm1]])
        X2 = np.column_stack([np.ones(hm2.sum()), hdd(T2, base).values[hm2]])
        p, b = fit_predict(act1[hm1], X1, X2); res[name] = float(p.sum() - act2[hm2].sum())
        r = act1[hm1] - X1 @ b; den = ((act1[hm1] - act1[hm1].mean()) ** 2).sum()
        res["r2_hdd18_baseline"] = float(1 - (r ** 2).sum() / den) if (hm1.sum() > 2 and den > 1e-9) else None  # None: zero variance (flat bills)
    # variable-base (PRISM-like) degree days, base chosen on baseline year
    best = None
    for base in np.arange(8, 21, 0.5):
        X1 = np.column_stack([np.ones(hm1.sum()), hdd(T1, base).values[hm1]])
        p1, b = fit_predict(act1[hm1], X1, X1); sse = ((act1[hm1] - p1) ** 2).sum()
        if best is None or sse < best[0]: best = (sse, base, b)
    X2 = np.column_stack([np.ones(hm2.sum()), hdd(T2, best[1]).values[hm2]])
    res["vbdd_prism_like"] = float((X2 @ best[2]).sum() - act2[hm2].sum()); res["vbdd_base_c"] = float(best[1])
    # schedule-aware: regressor = demand of a unit-H building with the ACTUAL schedule of each year
    u1 = monthly(demand(T1, 1.0 * H0, *sched1)) / H0; u2 = monthly(demand(T2, 1.0 * H0, *sched2)) / H0
    X1 = u1.values[hm1].reshape(-1, 1); X2 = u2.values[hm2].reshape(-1, 1)
    p, _ = fit_predict(act1[hm1], X1, X2); res["schedule_aware_physical"] = float(p.sum() - act2[hm2].sum())
    return res

S1 = (7, True)   # one shift 8-15, night/holiday setback
S2 = (11, True)  # two shifts 8-19
S0 = (7, False)  # one shift, NO setback (setpoint 20 always)
y1_base = demand(T1, H0, *S1)
scen = {}
def add(name, y1, y2, s1, s2, true_retrofit_kwh, note):
    e = estimators(y1, y2, T1, T2, s1, s2)
    base_adj = float(demand(T2, H0, *s2).sum()) if "network" not in name and "norm" not in name else float(monthly(y1).sum())
    scen[name] = {"note": note, "true_envelope_savings_kwh": true_retrofit_kwh,
                  "true_envelope_savings_pct_of_weather_adjusted_baseline": round(100 * true_retrofit_kwh / base_adj, 1) if base_adj else None,
                  **{k: (round(100 * v / base_adj, 1) if k not in ("r2_hdd18_baseline", "vbdd_base_c") else (round(v, 3) if v is not None else None)) for k, v in e.items()}}
true_env = float(demand(T2, H0, *S1).sum() - demand(T2, H1, *S1).sum())
true_env_2sh = float(demand(T2, H0, *S2).sum() - demand(T2, H1, *S2).sum())
add("A_no_change_warmer_year", y1_base, demand(T2, H0, *S1), S1, S1, 0.0, "Ничего не менялось, отчётный год теплее на 1.5 °C")
add("B_envelope_retrofit", y1_base, demand(T2, H1, *S1), S1, S1, true_env, "Утепление H -20%")
add("C_second_shift_only", y1_base, demand(T2, H0, *S2), S1, S2, 0.0, "Без модернизации, добавлена вторая смена")
add("D_retrofit_plus_second_shift", y1_base, demand(T2, H1, *S2), S1, S2, true_env_2sh, "Утепление и вторая смена одновременно")
add("E_setback_introduced_only", demand(T1, H0, *S0), demand(T2, H0, *S1), S0, S1, 0.0, "Без модернизации, введено ночное/каникулярное снижение температуры (эксплуатационная мера)")
# unregulated district heat: retrofit does not change delivered heat
yn1, yn2 = network_supply(T1, H0), network_supply(T2, H0)
add("F_retrofit_without_substation_network_driven", yn1, yn2, S1, S1, true_env, "Утепление, но здание без регулирования (подача по графику сети): учтённое тепло не меняется, растёт перегрев")
ynb1, ynb2 = norm_bill(T1), norm_bill(T2)
e = estimators(ynb1, ynb2, T1, T2, S1, S1)
scen["G_norm_based_billing"] = {"note": "Начисление по нормативу (не измерение); утепление выполнено", "true_envelope_savings_kwh": true_env,
                                "estimates_kwh": {k: (round(v, 1) if v is not None else None) for k, v in e.items()}}
# diagnostic: weather signal (R2) per billing type
diag = {"r2_hdd18_metered_with_control": scen["A_no_change_warmer_year"]["r2_hdd18_baseline"],
        "r2_hdd18_network_driven": scen["F_retrofit_without_substation_network_driven"]["r2_hdd18_baseline"],
        "r2_hdd18_norm_billing": e.get("r2_hdd18_baseline")}
# overheating proxy in F: indoor temperature that balances delivered heat after retrofit (occupied hours ignored)
on = heating_on(T2)
tin = np.where(on, T2.values + (H0 * np.maximum(0, 20 - T2.values) + G_UNOCC * A) / H1, np.nan)
diag["F_mean_indoor_temp_heating_season_after_retrofit_c"] = round(float(np.nanmean(tin)), 1)
out = {"inputs": {"weather_file": W, "weather_period": "2014-05-01..2015-04-30 (relabelled)", "reporting_year": "same series +1.5 degC (synthetic)",
                  "A_m2": A, "H0_W_per_K": H0, "H1_W_per_K": H1, "gains_W_m2": [G_OCC, G_UNOCC], "setpoints_C": [T_OCC, T_SETBACK],
                  "heating_on_rule": "5-day mean < +8 degC (assumption)", "shifts": {"one": "8-15", "two": "8-19"}},
       "baseline_year_heat_gcal": round(float(y1_base.sum()) / KWH_PER_GCAL, 1),
       "hdd18_baseline_year": round(float(np.maximum(0, 18 - T1).sum())),
       "scenarios_pct_of_weather_adjusted_baseline": scen, "diagnostics": diag,
       "versions": {"numpy": np.__version__, "pandas": pd.__version__}}
json.dump(out, open("/home/claude/ast/AST_A09_heating_experiment_result.json", "w"), ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=1))
