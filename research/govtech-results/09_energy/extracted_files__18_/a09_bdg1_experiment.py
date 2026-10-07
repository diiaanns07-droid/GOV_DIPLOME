"""A09 isolated experiment on Building Data Genome Project 1 (BDG1, MIT License).

Purpose: test critical assumptions of a Shymkent municipal-building energy MVP
on REAL open hourly meter data of school buildings (NOT Shymkent data):
  E1  simple baselines + chronological hold-out (train / validation / test)
  E2  detection of SYNTHETIC injected faults (night load) on real residuals,
      model-based detector vs. model-free rule
  E3  sensitivity of EUI (kWh/m2) audit ranking to floor-area error
  E4  error of annual kWh when monthly values are missing (naive annualisation)
Data: github.com/buds-lab/the-building-data-genome-project (codeload zip, master).
"""
import json, sys, platform
import numpy as np, pandas as pd

ROOT = "/home/claude/bdg1/the-building-data-genome-project-master/data"
RNG = np.random.default_rng(20261004)
OUT = {}

meta = pd.read_csv(f"{ROOT}/raw/meta_open.csv")
schools = meta[meta.primaryspaceusage == "Primary/Secondary Classroom"].copy()
raw = pd.read_csv(f"{ROOT}/raw/temp_open_utc.csv", usecols=["timestamp"] + schools.uid.tolist())
raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
raw = raw.set_index("timestamp")

_wcache = {}
def weather(fname):
    if fname in _wcache:
        return _wcache[fname]
    w = pd.read_csv(f"{ROOT}/external/weather/{fname}")
    t = pd.to_datetime(w["DateUTC<br />"].str.replace("<br />", "", regex=False), utc=True, errors="coerce")
    temp = pd.to_numeric(w["TemperatureC"], errors="coerce")
    temp[(temp < -60) | (temp > 60)] = np.nan
    s = pd.Series(temp.values, index=t).dropna()
    s = s[~s.index.duplicated()].sort_index().resample("1h").mean().interpolate(limit=6)
    _wcache[fname] = s
    return s

def design(local_idx, temp):
    how = (local_idx.dayofweek * 24 + local_idx.hour).values
    X_how = np.zeros((len(how), 168)); X_how[np.arange(len(how)), how] = 1.0
    T = np.nan_to_num(temp, nan=np.nanmean(temp))
    hinges = np.column_stack([np.maximum(T - k, 0) for k in (0, 10, 18, 24)] + [T])
    return X_how, hinges

def fit_predict(Xtr, ytr, Xte, ridge=1e-3):
    A = Xtr.T @ Xtr + ridge * np.eye(Xtr.shape[1])
    beta = np.linalg.solve(A, Xtr.T @ ytr)
    return Xte @ beta

def metrics(y, p):
    rmse = np.sqrt(np.mean((y - p) ** 2)); ybar = np.mean(y)
    return {"cvrmse_pct": 100 * rmse / ybar, "nmbe_pct": 100 * np.sum(y - p) / (len(y) * ybar)}

rows, det_rows, gap_rows = [], [], []
FAULTS = [0.10, 0.25, 0.50, 1.00]
for _, b in schools.iterrows():
    y = raw[b.uid].dropna()
    y = y[y >= 0]
    if len(y) < 24 * 300:
        continue
    start, end = y.index.min(), y.index.max()
    full_idx = pd.date_range(start, end, freq="1h", tz="UTC")
    missing_frac = 1 - len(y) / len(full_idx)
    y = y.reindex(full_idx)
    temp = weather(b.newweatherfilename).reindex(full_idx).interpolate(limit=12).values
    loc = full_idx.tz_convert(b.timezone)
    X_how, Xh = design(loc, temp)
    a0 = loc[48]  # anchor: first full local day (UTC->local shift can put first hours in previous month)
    mon = np.asarray((loc.year - a0.year) * 12 + loc.month - a0.month)  # 0..11 relative calendar month
    tr, va, te = (mon < 6), (mon >= 6) & (mon < 8), (mon >= 8) & (mon < 12)
    ok = ~np.isnan(y.values) & ~np.isnan(temp)
    yv = y.values
    res = {"uid": b.uid, "tz": b.timezone, "sqm": b.sqm, "hours": int(ok.sum()), "missing_frac": round(missing_frac, 4)}
    # descriptive, area-free indicators
    hr, dow = loc.hour, loc.dayofweek
    night = ok & ((hr <= 4) | (hr >= 23)); day = ok & (dow < 5) & (hr >= 9) & (hr <= 14)
    res["night_to_day_ratio"] = float(np.median(yv[night]) / np.median(yv[day]))
    annual_kwh = np.nansum(yv) / max(1e-9, (1 - missing_frac))
    res["annual_kwh"] = float(annual_kwh); res["eui_kwh_m2"] = float(annual_kwh / b.sqm)
    # E1 models
    preds = {}
    for name, X in {"M1_hour_of_week": X_how, "M2_how_plus_temp": np.hstack([X_how, Xh])}.items():
        m_tr = tr & ok
        if m_tr.sum() < 24 * 60 or (te & ok).sum() < 24 * 30:
            continue
        p = fit_predict(X[m_tr], yv[m_tr], X)
        preds[name] = p
        for split, mask in (("val", va & ok), ("test", te & ok)):
            mh = metrics(yv[mask], p[mask]); res[f"{name}_{split}_hourly_cvrmse"] = mh["cvrmse_pct"]; res[f"{name}_{split}_nmbe"] = mh["nmbe_pct"]
            dfd = pd.DataFrame({"y": yv[mask], "p": p[mask]}, index=loc[mask]).resample("1D").sum(min_count=20).dropna()
            res[f"{name}_{split}_daily_cvrmse"] = metrics(dfd.y.values, dfd.p.values)["cvrmse_pct"]
        # per-month test NMBE (to expose schedule / holiday effects)
        dfm = pd.DataFrame({"y": yv, "p": p, "m": mon}, index=loc)[te & ok]
        for mm, g in dfm.groupby("m"):
            res[f"{name}_test_month{int(mm)}_nmbe"] = 100 * (g.y.sum() - g.p.sum()) / g.y.sum()
    rows.append(res)
    # E2 injected faults
    if "M2_how_plus_temp" not in preds:
        continue
    p = preds["M2_how_plus_temp"]
    D = pd.DataFrame({"y": yv, "p": p, "ok": ok, "night": (hr <= 5) | (hr >= 22)}, index=loc)
    base_night = np.nanmedian(yv[tr & ok & D.night.values])
    def daily_stats(ys):
        d = D.assign(y=ys)
        dd = d[d.ok].resample("1D").agg({"y": "sum", "p": "sum"})
        nn = d[d.ok & d.night].resample("1D")["y"].sum()
        return dd, nn
    dd0, nn0 = daily_stats(yv)
    dloc = dd0.index
    dmon = np.asarray((dloc.year - a0.year) * 12 + dloc.month - a0.month)
    r0 = dd0.y - dd0.p
    vmask, tmask = (dmon >= 6) & (dmon < 8), (dmon >= 8) & (dmon < 12)
    mu, sd = r0[vmask].mean(), r0[vmask].std()
    z0 = ((r0 - mu) / sd).rolling(7).mean()
    thr = np.nanpercentile(z0[vmask], 95)
    # rule (model-free): 7-day night energy vs median of the preceding 28 days
    def rule_flag(nn):
        ref = nn.shift(7).rolling(28, min_periods=14).median()
        return (nn.rolling(7).mean() > 1.15 * ref)
    rule0 = rule_flag(nn0)
    test_days = np.where(tmask)[0]
    fa_model = float(np.nanmean((z0 > thr)[tmask])); fa_rule = float(np.nanmean(rule0[tmask]))
    for f in FAULTS:
        for rep in range(5):
            s0 = int(RNG.choice(test_days[:-21])) if len(test_days) > 30 else None
            if s0 is None:
                continue
            fault_start = dloc[s0].normalize(); fault_end = fault_start + pd.Timedelta(days=14)
            inj = yv.copy()
            sel = (loc >= fault_start) & (loc < fault_end) & D.night.values
            inj[sel] = inj[sel] + f * base_night
            dd1, nn1 = daily_stats(inj)
            z1 = ((dd1.y - dd1.p - mu) / sd).rolling(7).mean()
            win = (dd1.index >= fault_start) & (dd1.index < fault_end + pd.Timedelta(days=6))
            det_rows.append({"uid": b.uid, "fault_frac_of_night_median": f,
                             "model_detect": bool((z1[win] > thr).any()),
                             "model_detect_clean_same_window": bool((z0[win] > thr).any()),
                             "rule_detect": bool(rule_flag(nn1)[win].any()),
                             "rule_detect_clean_same_window": bool(rule0[win].any()),
                             "fa_model_test_daily": fa_model, "fa_rule_test_daily": fa_rule})
    # E4 missing months -> naive annualisation error
    mk = pd.DataFrame({"y": yv, "m": mon}, index=loc)[ok].groupby("m").y.sum()
    mk = mk[(mk.index >= 0) & (mk.index < 12)]
    if len(mk) == 12:
        true = mk.sum()
        for k in (1, 2, 3):
            for rep in range(50):
                drop = RNG.choice(mk.index.values, size=k, replace=False)
                est = mk.drop(index=drop).sum() * 12 / (12 - k)
                gap_rows.append({"uid": b.uid, "k_missing_months": k, "err_pct": 100 * (est - true) / true})

R = pd.DataFrame(rows); DET = pd.DataFrame(det_rows); GAP = pd.DataFrame(gap_rows)
OUT["n_school_buildings_used"] = int(len(R))
OUT["tz_breakdown"] = R.tz.value_counts().to_dict()
OUT["missing_frac_median"] = float(R.missing_frac.median())
OUT["eui_kwh_m2_quantiles"] = R.eui_kwh_m2.quantile([.1, .25, .5, .75, .9]).round(1).to_dict()
OUT["night_to_day_ratio_quantiles"] = R.night_to_day_ratio.quantile([.1, .25, .5, .75, .9]).round(3).to_dict()
OUT["corr_spearman_eui_vs_night_ratio"] = float(R[["eui_kwh_m2", "night_to_day_ratio"]].corr(method="spearman").iloc[0, 1])
e1 = {}
for c in [c for c in R.columns if c.startswith("M") and ("cvrmse" in c or c.endswith("_nmbe")) and "month" not in c]:
    e1[c] = {"median": round(float(R[c].median()), 1), "p25": round(float(R[c].quantile(.25)), 1), "p75": round(float(R[c].quantile(.75)), 1)}
OUT["E1_holdout_metrics"] = e1
OUT["E1_share_daily_cvrmse_test_le_20pct"] = {m: float((R[f"{m}_test_daily_cvrmse"] <= 20).mean()) for m in ("M1_hour_of_week", "M2_how_plus_temp")}
monthcols = sorted([c for c in R.columns if c.startswith("M2_how_plus_temp_test_month")], key=lambda s: int(s.split("month")[1].split("_")[0]))
OUT["E1_M2_test_nmbe_by_relative_month_median"] = {c.split("month")[1].split("_")[0]: round(float(R[c].median()), 1) for c in monthcols}
uk = R[R.tz == "Europe/London"]
OUT["E1_M2_test_nmbe_by_relative_month_median_UK_only(Dec2014start)"] = {c.split("month")[1].split("_")[0]: round(float(uk[c].median()), 1) for c in monthcols}
OUT["E2_detection"] = DET.groupby("fault_frac_of_night_median")[["model_detect", "model_detect_clean_same_window", "rule_detect", "rule_detect_clean_same_window"]].mean().round(3).to_dict(orient="index")
OUT["E2_false_alarm_daily_rate_test_clean"] = {"model_median": float(DET.groupby("uid").fa_model_test_daily.first().median()),
                                               "rule_median": float(DET.groupby("uid").fa_rule_test_daily.first().median())}
# E3 area error -> ranking stability
k = max(1, int(round(0.2 * len(R))))
true_top = set(R.nlargest(k, "eui_kwh_m2").uid)
e3 = {}
for sig in (0.1, 0.2, 0.3, 0.5):
    ov = []
    for _ in range(2000):
        noisy = R.annual_kwh / (R.sqm * np.exp(RNG.normal(0, sig, len(R))))
        ov.append(len(true_top & set(R.uid[noisy.nlargest(k).index])) / k)
    e3[f"sigma_log_{sig}"] = {"mean_overlap_top20pct": round(float(np.mean(ov)), 3), "p10": round(float(np.percentile(ov, 10)), 3)}
OUT["E3_area_error_top20_overlap"] = e3; OUT["E3_k"] = k
OUT["E4_missing_months_abs_err_pct"] = {int(kk): {"median": round(float(g.err_pct.abs().median()), 1), "p90": round(float(g.err_pct.abs().quantile(.9)), 1), "max": round(float(g.err_pct.abs().max()), 1)} for kk, g in GAP.groupby("k_missing_months")}
OUT["versions"] = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
R.to_csv("/home/claude/exp/A09_bdg1_per_building_results.csv", index=False)
json.dump(OUT, open("/home/claude/exp/A09_bdg1_experiment_summary.json", "w"), indent=2, ensure_ascii=False, default=str)
print(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
