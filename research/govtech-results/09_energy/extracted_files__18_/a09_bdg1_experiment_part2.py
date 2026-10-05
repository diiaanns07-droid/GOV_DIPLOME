"""A09 part 2: (a) M1 per-month test NMBE, (b) rule-threshold sweep, (c) leave-one-month-out
blocked CV with approximate school calendar (UK schools only, ASSUMED holiday dates)."""
import json, numpy as np, pandas as pd
exec(open('a09_bdg1_experiment.py').read().split("rows, det_rows, gap_rows")[0])  # reuse loaders/helpers
HOL = [("2014-12-22","2015-01-02"),("2015-02-16","2015-02-20"),("2015-03-30","2015-04-10"),
       ("2015-05-25","2015-05-29"),("2015-07-23","2015-09-02"),("2015-10-26","2015-10-30")]
BANK = ["2015-05-04","2015-08-31"]
def holiday_flag(loc):
    d = loc.tz_localize(None).normalize()
    f = np.zeros(len(d), bool)
    for a, b in HOL: f |= (d >= pd.Timestamp(a)) & (d <= pd.Timestamp(b))
    for x in BANK: f |= (d == pd.Timestamp(x))
    return f
out = {"m1_month": [], "rule": [], "lomo": []}
for _, b in schools.iterrows():
    y = raw[b.uid].dropna(); y = y[y >= 0]
    if len(y) < 24*300: continue
    idx = pd.date_range(y.index.min(), y.index.max(), freq="1h", tz="UTC"); y = y.reindex(idx)
    temp = weather(b.newweatherfilename).reindex(idx).interpolate(limit=12).values
    loc = idx.tz_convert(b.timezone); a0 = loc[48]
    mon = np.asarray((loc.year - a0.year)*12 + loc.month - a0.month)
    X_how, Xh = design(loc, temp); yv = y.values; ok = ~np.isnan(yv) & ~np.isnan(temp)
    tr = (mon < 6) & ok
    p1 = fit_predict(X_how[tr], yv[tr], X_how)
    for mm in range(8, 12):
        s = ok & (mon == mm)
        if s.sum() > 24*20: out["m1_month"].append({"uid": b.uid, "tz": b.timezone, "m": mm, "nmbe": 100*(yv[s].sum()-p1[s].sum())/yv[s].sum()})
    # rule threshold sweep with injected night fault (f=0.25, 0.5) on test months 8..11
    hr = loc.hour; night = ((hr <= 5) | (hr >= 22)) & ok
    base_night = np.nanmedian(yv[(mon < 6) & night])
    def nn_of(v): return pd.Series(np.where(night, v, 0.0), index=loc).resample("1D").sum()
    nn0 = nn_of(np.nan_to_num(yv)); dl = nn0.index
    dmon = np.asarray((dl.year - a0.year)*12 + dl.month - a0.month); td = np.where((dmon >= 8) & (dmon < 12))[0]
    if len(td) < 40: continue
    for thr in (1.15, 1.3, 1.5):
        def flag(nn): ref = nn.shift(7).rolling(28, min_periods=14).median(); return nn.rolling(7).mean() > thr*ref
        f0 = flag(nn0); fa = float(f0.iloc[td].mean())
        for f in (0.25, 0.5):
            for rep in range(5):
                s0 = int(RNG.choice(td[:-21])); fs = dl[s0]; fe = fs + pd.Timedelta(days=14)
                inj = np.nan_to_num(yv).copy(); sel = (loc >= fs) & (loc < fe) & night; inj[sel] += f*base_night
                f1 = flag(nn_of(inj)); win = (dl >= fs) & (dl < fe + pd.Timedelta(days=6))
                out["rule"].append({"uid": b.uid, "thr": thr, "f": f, "detect": bool(f1[win].any()), "clean_win": bool(f0[win].any()), "fa_daily": fa})
    # LOMO blocked CV, UK schools (calendar assumption applies to England 2014/15)
    if b.timezone != "Europe/London": continue
    hol = holiday_flag(loc).astype(float)
    Xhol = np.zeros((len(loc), 24)); Xhol[np.arange(len(loc)), loc.hour] = hol
    Xs = {"M1_how": X_how, "M2_how_temp": np.hstack([X_how, Xh]), "M3_how_temp_calendar": np.hstack([X_how, Xh, Xhol])}
    for mm in range(12):
        te = ok & (mon == mm); trn = ok & (mon != mm) & (mon >= 0) & (mon < 12)
        if te.sum() < 24*20: continue
        for name, X in Xs.items():
            p = fit_predict(X[trn], yv[trn], X[te])
            dfd = pd.DataFrame({"y": yv[te], "p": p}, index=loc[te]).resample("1D").sum(min_count=20).dropna()
            out["lomo"].append({"uid": b.uid, "m": mm, "model": name, "month_nmbe": 100*(yv[te].sum()-p.sum())/yv[te].sum(),
                                "daily_cvrmse": metrics(dfd.y.values, dfd.p.values)["cvrmse_pct"],
                                "hourly_cvrmse": metrics(yv[te], p)["cvrmse_pct"]})
M1 = pd.DataFrame(out["m1_month"]); RU = pd.DataFrame(out["rule"]); L = pd.DataFrame(out["lomo"])
S = {}
S["M1_forward_test_nmbe_by_month_median_all"] = M1.groupby("m").nmbe.median().round(1).to_dict()
S["M1_forward_test_nmbe_by_month_median_UK"] = M1[M1.tz=="Europe/London"].groupby("m").nmbe.median().round(1).to_dict()
g = RU.groupby(["thr","f"]).agg(detect=("detect","mean"), clean_window_alarm=("clean_win","mean"))
S["rule_sweep"] = {f"thr={k[0]}|f={k[1]}": {kk: round(float(v),3) for kk, v in r.items()} for k, r in g.iterrows()}
S["rule_daily_false_alarm_median_by_thr"] = RU.groupby(["thr","uid"]).fa_daily.first().groupby("thr").median().round(3).to_dict()
L["abs_month_nmbe"] = L.month_nmbe.abs()
S["LOMO_UK_n_buildings"] = int(L.uid.nunique())
S["LOMO_UK_median"] = L.groupby("model")[["abs_month_nmbe","daily_cvrmse","hourly_cvrmse"]].median().round(1).to_dict(orient="index")
S["LOMO_UK_share_buildings_median_daily_cvrmse_le_20"] = L.groupby(["model","uid"]).daily_cvrmse.median().le(20).groupby("model").mean().round(3).to_dict()
S["LOMO_UK_abs_nmbe_by_month_M1_vs_M3"] = L[L.model.isin(["M1_how","M3_how_temp_calendar"])].groupby(["m","model"]).abs_month_nmbe.median().unstack().round(1).to_dict(orient="index")
json.dump(S, open("A09_bdg1_experiment_part2_summary.json","w"), indent=2, default=str)
print(json.dumps(S, indent=1, default=str))
