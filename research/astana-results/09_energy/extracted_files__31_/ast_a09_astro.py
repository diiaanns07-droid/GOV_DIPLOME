"""AST-A09: astronomical lighting hours and top-of-atmosphere irradiation, Astana vs Shymkent.
Astana point = area-weighted centroid of the 6 OSM district polygons in STUPITS data/astana_districts.geojson.
Shymkent point = same as first pass A09-F020 (42.32N, 69.60E, approximate, from model memory)."""
import json, numpy as np, pandas as pd, pvlib
from shapely.geometry import shape
from shapely.ops import unary_union
g = json.load(open("/home/claude/stupits/hack-d3b2c613-stupits-main/data/astana_districts.geojson", encoding="utf-8"))
u = unary_union([shape(f["geometry"]) for f in g["features"]]); c = u.centroid
pts = {"astana_osm_centroid": (round(c.y, 4), round(c.x, 4), 350), "shymkent_A09": (42.32, 69.60, 500)}
idx = pd.date_range("2027-01-01", "2028-01-01", freq="1min", tz="Asia/Almaty", inclusive="left")
out = {"points": pts, "tz_offset_2027": str(idx[0].utcoffset())}
for name, (lat, lon, alt) in pts.items():
    sp = pvlib.solarposition.get_solarposition(idx, lat, lon, altitude=alt, method="nrel_numpy")
    el = sp["apparent_elevation"]; dark = el < -0.833
    r = {k: round(float((el < thr).sum()) / 60, 1) for k, thr in {"h_dark_sunset_sunrise": -0.833, "h_dark_civil": -6.0, "h_switch_plus3": 3.0}.items()}
    dd = dark.resample("1D").sum() / 60
    r["dark_h_per_day_min_max"] = [round(float(dd.min()), 2), round(float(dd.max()), 2)]
    r["dark_h_by_month"] = {int(m): round(float(v), 0) for m, v in (dark.resample("MS").sum() / 60).items().__iter__() if False} or {int(k.month): round(float(v), 0) for k, v in (dark.resample("MS").sum() / 60).items()}
    for day in ("2027-06-21", "2027-12-21"):
        e = el[day]; up = e[e > -0.833]
        r[f"sunrise_sunset_{day}"] = [up.index.min().strftime("%H:%M"), up.index.max().strftime("%H:%M")]
    ev = (idx.hour >= 17) & (idx.hour < 21)
    r["share_dark_17_21_by_month"] = {int(m): round(float(v), 2) for m, v in pd.Series(dark.values[ev], index=idx[ev]).resample("MS").mean().items() for m in [m.month]}
    # top-of-atmosphere horizontal irradiation (no atmosphere, clouds, snow): upper bound only
    dni_extra = pvlib.irradiance.get_extra_radiation(idx)
    toa = (dni_extra * np.maximum(0, np.cos(np.radians(sp["zenith"])))) / 60 / 1000  # kWh/m2 per minute-step
    mon = toa.resample("MS").sum()
    r["toa_horizontal_kwh_m2_year"] = round(float(toa.sum()), 0)
    r["toa_kwh_m2_by_month"] = {int(k.month): round(float(v), 1) for k, v in mon.items()}
    r["toa_dec_to_jun_ratio"] = round(float(mon.iloc[11] / mon.iloc[5]), 3)
    out[name] = r
out["versions"] = {"pvlib": pvlib.__version__, "pandas": pd.__version__, "numpy": np.__version__}
json.dump(out, open("/home/claude/ast/AST_A09_astro_result.json", "w"), indent=1)
print(json.dumps(out, indent=1))
