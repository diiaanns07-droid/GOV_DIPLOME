"""K12: small offline extract from BDG1 for the EUI audit-ranking baseline.

Reads ONLY local files of a clone of github.com/buds-lab/the-building-data-genome-project
(pinned commit below). No network, no writes outside ../data/.

Data are REAL but INTERNATIONAL (UK/US/Singapore, 2010-2015). Not Shymkent, not Astana.

Usage:
    python k12_build_extract.py /path/to/the-building-data-genome-project
"""
import hashlib
import json
import pathlib
import platform
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

EXPECTED_COMMIT = "521a6c0f0efe760a96dac656191ed7f4067c4b4d"
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "data"
SCHOOL_USE = "Primary/Secondary Classroom"
PEAK_HOURS = range(9, 16)  # weekday 09:00-15:59 local, used only for the missingness profile


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def impute_missing(y, loc):
    """Fill missing hours with the mean of observed hours of the same building,
    same local month, same day type (Mon-Fri / Sat-Sun) and same local hour.
    Fallbacks: same day type x hour over the whole period, then building mean."""
    df = pd.DataFrame({"y": y.values, "m": loc.strftime("%Y-%m"),
                       "wk": loc.dayofweek < 5, "h": loc.hour}, index=y.index)
    fill = df.groupby(["m", "wk", "h"]).y.transform("mean")
    fallback1 = int((df.y.isna() & fill.isna()).sum())
    fill = fill.fillna(df.groupby(["wk", "h"]).y.transform("mean"))
    fallback2 = int((df.y.isna() & fill.isna()).sum())
    fill = fill.fillna(df.y.mean())
    return df.y.fillna(fill), fallback1, fallback2


def main(root):
    root = pathlib.Path(root)
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if commit != EXPECTED_COMMIT:
        print(f"WARNING: clone is at {commit}, expected {EXPECTED_COMMIT}", file=sys.stderr)

    meta_path = root / "data/raw/meta_open.csv"
    raw_path = root / "data/raw/temp_open_utc.csv"
    meta = pd.read_csv(meta_path)
    sch = meta[meta.primaryspaceusage == SCHOOL_USE].copy()
    raw = pd.read_csv(raw_path, usecols=["timestamp"] + sch.uid.tolist())
    raw.index = pd.to_datetime(raw.pop("timestamp"), utc=True)

    monthly_rows, qc_rows = [], []
    for _, b in sch.iterrows():
        # meta datastart/dataend are local wall-clock times (dd/mm/yy HH:MM)
        start = pd.to_datetime(b.datastart, format="%d/%m/%y %H:%M").tz_localize(b.timezone)
        end = pd.to_datetime(b.dataend, format="%d/%m/%y %H:%M").tz_localize(b.timezone)
        idx = pd.date_range(start.tz_convert("UTC"), end.tz_convert("UTC"), freq="1h")
        series = raw[b.uid]
        outside = int(series[(series.index < idx[0]) | (series.index > idx[-1])].notna().sum())
        y = series.reindex(idx)
        negatives = int((y < 0).sum())
        y = y.where(y >= 0)
        loc = idx.tz_convert(b.timezone)
        y_imp, fb1, fb2 = impute_missing(y, loc)

        miss = y.isna().values
        peak = (loc.dayofweek < 5) & np.isin(loc.hour, list(PEAK_HOURS))
        qc_rows.append({
            "uid": b.uid,
            "hours_expected": len(idx),
            "hours_observed": int((~miss).sum()),
            "negative_values_set_missing": negatives,
            "nonnull_outside_meta_period": outside,
            "missing_share_in_weekday_09_15": round(float(peak[miss].mean()), 4) if miss.any() else None,
            "expected_share_weekday_09_15": round(float(peak.mean()), 4),
            "impute_fallback_daytype_hour": fb1,
            "impute_fallback_building_mean": fb2,
        })
        frame = pd.DataFrame({"obs": y.values, "imp": y_imp.values,
                              "month": loc.strftime("%Y-%m")}, index=idx)
        for month, g in frame.groupby("month"):
            monthly_rows.append({
                "uid": b.uid, "month_local": month,
                "hours_expected": len(g), "hours_observed": int(g.obs.notna().sum()),
                "kwh_observed_sum": round(float(g.obs.sum()), 4),
                "kwh_with_imputed_hours": round(float(g.imp.sum()), 4),
            })

    OUT.mkdir(parents=True, exist_ok=True)
    keep = ["uid", "industry", "subindustry", "primaryspaceusage", "timezone", "newweatherfilename",
            "datastart", "dataend", "sqm", "sqft", "heatingtype", "mainheatingtype",
            "numberoffloors", "occupants", "yearbuilt", "rating"]
    sch[keep].to_csv(OUT / "K12_bdg1_schools_meta.csv", index=False)
    pd.DataFrame(monthly_rows).to_csv(OUT / "K12_bdg1_schools_monthly.csv", index=False)
    pd.DataFrame(qc_rows).to_csv(OUT / "K12_bdg1_schools_qc.csv", index=False)
    shutil.copyfile(root / "LICENSE", OUT / "BDG1_LICENSE.txt")
    prov = {
        "kind": "observed (real international open data, not Kazakhstan)",
        "source": "https://github.com/buds-lab/the-building-data-genome-project",
        "upstream_commit": commit,
        "upstream_files_sha256": {
            "LICENSE": sha256(root / "LICENSE"),
            "data/raw/meta_open.csv": sha256(meta_path),
            "data/raw/temp_open_utc.csv": sha256(raw_path),
        },
        "license": "MIT (Copyright (c) 2016, Clayton Miller); notice copied to BDG1_LICENSE.txt",
        "citation": "Miller C., Meggers F. The Building Data Genome Project. Energy Procedia 122 (2017) 439-444, doi:10.1016/j.egypro.2017.07.400",
        "selection": f"primaryspaceusage == '{SCHOOL_USE}' ({len(sch)} buildings)",
        "period_rule": "meta datastart..dataend, local wall-clock, hourly; negative readings set to missing",
        "units": "kWh per hour as assumed by A09; units are NOT stated in README/meta (not verified)",
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    (OUT / "K12_provenance.json").write_text(json.dumps(prov, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"buildings": len(sch), "monthly_rows": len(monthly_rows), "commit": commit}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
