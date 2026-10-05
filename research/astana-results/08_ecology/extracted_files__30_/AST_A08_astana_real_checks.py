"""AST-A08 — проверки на РЕАЛЬНЫХ небольших образцах по Астане (2026-10-05).

Входы (все — сторонние публичные репозитории GitHub; официальные хосты из среды недоступны):
  STUPITS   https://github.com/BAITC-Hacks/hack-d3b2c613-stupits  @834a25f  data/astana_districts.geojson (OSM, ODbL)
  AIRDATA   https://github.com/DinaAssylbekova/AirData_Shymkent    @cacb98c  sensors.xlsx + layer_03_*.csv (лицензии нет)
  CLIMAT    https://github.com/SaniyaAbushakimova/Kazhydromet-Web-Scraping  kazgydromet_data/темп/возд/KZ-AKM/темп_возд_KZ-AKM_Астана.csv (лицензии нет)
  AILARIS   https://github.com/ailaris/astana-air-quality          @921aafa  air_quality_data.csv (происхождение не указано)
Сырые строки не перераспространяются: печатаются только агрегаты.

Запуск: python3 AST_A08_astana_real_checks.py <dir_with_clones>   (ожидаются подпапки как в git clone, см. README в отчёте)
Окружение: Python 3.12.3, pandas 3.0.2, numpy 2.4.4, shapely 2.1.2, pyproj 3.8.0
"""
import json, sys, itertools
import numpy as np
import pandas as pd
from shapely.geometry import shape, Point
from shapely.ops import transform, unary_union
from pyproj import Transformer

R = sys.argv[1] if len(sys.argv) > 1 else "."
P_STU = f"{R}/stupits/data/astana_districts.geojson"
P_AIR = f"{R}/gh/DinaAssylbekova_AirData_Shymkent"
P_CLI = f"{R}/gh/SaniyaAbushakimova_Kazhydromet-Web-Scraping/kazgydromet_data/темп/возд/KZ-AKM/темп_возд_KZ-AKM_Астана.csv"
P_AIL = f"{R}/gh/ailaris_astana-air-quality/air_quality_data.csv"
out = {}

# ---------- A. Районы (OSM через STUPITS) ----------
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32642", always_xy=True).transform   # UTM 42N
gj = json.load(open(P_STU))
dist = {f["properties"]["id"]: (f["properties"]["name"], shape(f["geometry"])) for f in gj["features"]}
out["districts_osm"] = {k: {"name": n, "area_km2": round(transform(to_utm, g).area / 1e6, 1)} for k, (n, g) in dist.items()}
city_utm = transform(to_utm, unary_union([g for _, g in dist.values()]))
out["city_union_area_km2"] = round(city_utm.area / 1e6, 1)

# ---------- B. Посты Казгидромета (список AirData, ~2022) ----------
s = pd.read_excel(f"{P_AIR}/sensors.xlsx")
posts = s[s.city == "Нур-Султан"].copy()
posts["district"] = [next((k for k, (_, g) in dist.items() if g.contains(Point(x, y))), None) for x, y in zip(posts.lng, posts.lat)]
xy = np.array([to_utm(x, y) for x, y in zip(posts.lng, posts.lat)])
dd = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1)); np.fill_diagonal(dd, np.inf)
posts["nn_km"] = (dd.min(1) / 1000).round(2)
out["posts"] = posts[["sId", "pnz", "address", "lat", "lng", "district", "nn_km"]].to_dict("records")
out["posts_per_district"] = {k: int((posts.district == k).sum()) for k in dist}

# Покрытие площади: доля площади города далее 2/5 км от ближайшего поста (сетка 250 м)
minx, miny, maxx, maxy = city_utm.bounds
gx, gy = np.meshgrid(np.arange(minx + 125, maxx, 250), np.arange(miny + 125, maxy, 250))
from shapely import contains_xy
inside = contains_xy(city_utm, gx, gy)
dmin = np.hypot(gx[..., None] - xy[:, 0], gy[..., None] - xy[:, 1]).min(-1)
cov = {}
for k, (_, g) in dist.items():
    m = contains_xy(transform(to_utm, g), gx, gy)
    cov[k] = {f"share_area_gt_{r}km": round(float((dmin[m] > r * 1000).mean()), 3) for r in (2, 5)}
cov["city"] = {f"share_area_gt_{r}km": round(float((dmin[inside] > r * 1000).mean()), 3) for r in (2, 5)}
out["monitoring_gap_area_weighted"] = cov

# ---------- C/D/E. Ряды постов ----------
df = pd.read_csv(f"{P_AIR}/layer_03_data_prepared_25.03.22.csv")
df = df[df.stationId.isin(posts.sId)].copy()
df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
out["series_period_utc"] = [str(df.datetime.min()), str(df.datetime.max())]
y0, y1 = pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2021-12-31 23:00", tz="UTC")
w = df[(df.datetime >= y0) & (df.datetime <= y1)]
comp = (w.groupby(["stationId", "code"]).datetime.nunique() / 8760 * 100).round(1).unstack().reindex(posts.sId)
out["completeness_2021_pct"] = comp[[c for c in ["PM2.5", "PM10", "NO2", "SO2", "CO"] if c in comp]].fillna(0.0).to_dict("index")

pm = df[df.code == "PM2.5"].copy()
pm["day"] = pm.datetime.dt.tz_convert("Asia/Almaty").dt.date     # tzdata: UTC+6 до 01.03.2024
daily = pm.groupby(["stationId", "day"]).value.agg(["mean", "size"]).reset_index()
daily = daily[daily["size"] >= 18]
daily["month"] = pd.to_datetime(daily.day).dt.month
season = {}
for sid, g in daily.groupby("stationId"):
    wi, su = g[g.month.isin([12, 1, 2])], g[g.month.isin([6, 7, 8])]
    season[sid] = {"valid_days_DJF": int(len(wi)), "median_DJF": round(float(wi["mean"].median()), 1) if len(wi) else None,
                   "valid_days_JJA": int(len(su)), "median_JJA": round(float(su["mean"].median()), 1) if len(su) else None,
                   "days_gt_35_if_ugm3_all": int((g["mean"] > 35).sum()), "valid_days_all": int(len(g))}
out["pm25_seasonal_daily"] = season
piv = daily.pivot(index="day", columns="stationId", values="mean")
pairs = []
for a, b in itertools.combinations(piv.columns, 2):
    c = piv[[a, b]].dropna()
    if len(c) >= 30:
        pairs.append({"pair": f"{a}-{b}", "n_days": int(len(c)), "spearman": round(float(c.corr(method="spearman").iloc[0, 1]), 2),
                      "median_abs_diff": round(float((c[a] - c[b]).abs().median()), 1)})
out["pm25_pairwise"] = pairs
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from eco_priority_core import qc_daily_series          # общий компонент двух городов
out["pm25_qc_flags"] = qc_daily_series(piv)

# ---------- F. Проверка единиц стороннего ряда (AQI или мкг/м³?) ----------
def us_aqi(c, bp):
    for (cl, ch, il, ih) in bp:
        if cl <= c <= ch:
            return (ih - il) / (ch - cl) * (c - cl) + il
    return np.nan
BP_OLD = [(0, 12, 0, 50), (12.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 150.4, 151, 200), (150.5, 250.4, 201, 300), (250.5, 500.4, 301, 500)]
ail = pd.read_csv(P_AIL); ail["day"] = pd.to_datetime(ail["date"]).dt.date
citymean = piv.mean(axis=1, skipna=True).rename("kz").reset_index()
m = citymean.merge(ail[["day", "pm25"]], on="day").dropna()
m["kz_r"] = m.kz.round(1)
m["kz_aqi"] = m.kz_r.apply(lambda c: us_aqi(c, BP_OLD))
years = pd.to_datetime(ail["date"]).dt.year.value_counts().sort_index()
if len(m) < 30:   # проверку единиц выполнить нельзя — честно фиксируем
    out["third_party_unit_test"] = {"overlap_days": int(len(m)), "status": "not_testable_no_overlap",
        "ailaris_rows_by_year": {int(k): int(v) for k, v in years.items()}, "ailaris_pm25_non_null": int(ail.pm25.notna().sum()),
        "ailaris_period": [str(ail.day.min()), str(ail.day.max())]}
else:
  out["third_party_unit_test"] = {
    "overlap_days": int(len(m)),
    "spearman_vs_kz_conc": round(float(m[["pm25", "kz"]].corr(method="spearman").iloc[0, 1]), 2),
    "median_abs_log_ratio_vs_conc": round(float(np.median(np.abs(np.log(m.pm25 / m.kz)))), 3),
    "median_abs_log_ratio_vs_usaqi_pre2024": round(float(np.median(np.abs(np.log(m.pm25 / m.kz_aqi)))), 3),
    "median_ratio_series_to_conc": round(float(np.median(m.pm25 / m.kz)), 2),
    "ailaris_rows_total": int(len(ail)), "ailaris_period": [str(ail.day.min()), str(ail.day.max())]}

# ---------- G. Метеостанция «Астана»: экстремумы по 8 срокам ----------
cl = pd.read_csv(P_CLI)
terms = ["18", "21", "00", "03", "06", "09", "12", "15"]
cl[terms] = cl[terms].apply(pd.to_numeric, errors="coerce")
cl["date"] = pd.to_datetime(cl["date"]); cl["year"] = cl.date.dt.year
cl["n"] = cl[terms].notna().sum(axis=1)
ok = cl[cl.n >= 7].copy()
ok["tmax8"], ok["tmin8"] = ok[terms].max(axis=1), ok[terms].min(axis=1)
yr = ok.groupby("year").agg(days=("date", "size"), d_ge30=("tmax8", lambda v: int((v >= 30).sum())), d_ge35=("tmax8", lambda v: int((v >= 35).sum())),
                            d_le_m30=("tmin8", lambda v: int((v <= -30).sum())), d_le_m35=("tmin8", lambda v: int((v <= -35).sum())))
yr = yr[yr.days >= 330]
dec = lambda a, b: yr.loc[a:b].mean().round(1).to_dict()
out["station_astana"] = {"rows": int(len(cl)), "period": [str(cl.date.min().date()), str(cl.date.max().date())],
                         "days_ge7_terms_share": round(float((cl.n >= 7).mean()), 4), "full_years": [int(yr.index.min()), int(yr.index.max())],
                         "mean_2000_2009": dec(2000, 2009), "mean_2010_2019": dec(2010, 2019), "mean_2020_2022": dec(2020, 2022),
                         "max_tmax8": round(float(ok.tmax8.max()), 1), "min_tmin8": round(float(ok.tmin8.min()), 1),
                         "region_code_in_source": str(cl.region.iloc[0])}
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
