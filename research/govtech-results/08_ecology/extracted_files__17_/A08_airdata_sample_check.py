"""A08 — проверка реального стороннего образца: 2 автоматических поста Казгидромета в Шымкенте.

Источник (A08-S010): https://github.com/DinaAssylbekova/AirData_Shymkent
коммит cacb98c19046bc441c4bfce29d74122ba525cfe2 (2022-04-03). Лицензии в репозитории НЕТ:
сырые строки не перераспространяем, публикуем только агрегаты. Единицы измерения в файле
не указаны; пороги ниже применимы ТОЛЬКО если значения в мкг/м³ (не подтверждено).

Запуск:
  git clone --depth 1 https://github.com/DinaAssylbekova/AirData_Shymkent.git
  python3 A08_airdata_sample_check.py AirData_Shymkent
"""
import json, math, sys
import pandas as pd

root = sys.argv[1] if len(sys.argv) > 1 else "AirData_Shymkent"
sensors = pd.read_excel(f"{root}/sensors.xlsx")
sh = sensors[sensors.city.astype(str).str.contains("Шымкент")].copy()
df = pd.read_csv(f"{root}/layer_03_data_prepared_25.03.22.csv")
df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
df = df[df.stationId.isin(sh.sId)]

# Окно, где у обоих постов есть хоть какие-то ряды: 2021-12-21 .. 2022-03-24 (UTC)
t0, t1 = pd.Timestamp("2021-12-21 00:00", tz="UTC"), pd.Timestamp("2022-03-24 23:00", tz="UTC")
hours = int((t1 - t0) / pd.Timedelta(hours=1)) + 1
w = df[(df.datetime >= t0) & (df.datetime <= t1)]
out = {"window_utc": [str(t0), str(t1)], "expected_hours": hours, "posts": sh[["sId", "pnz", "address", "lat", "lng"]].to_dict("records")}

comp = (w.groupby(["stationId", "code"]).datetime.nunique() / hours * 100).round(1)
out["completeness_pct"] = {f"{s}/{c}": v for (s, c), v in comp.items()}

# Расстояние между постами (гаверсинус)
a, b = sh.iloc[0], sh.iloc[1]
R = 6371.0
p1, p2 = math.radians(a.lat), math.radians(b.lat)
dlat, dlon = p2 - p1, math.radians(b.lng - a.lng)
h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
out["distance_between_posts_km"] = round(2 * R * math.asin(math.sqrt(h)), 2)

# Суточные средние PM2.5 (сутки с >=18 часовыми значениями), по каждому посту за ВЕСЬ период ряда
pm = df[df.code == "PM2.5"].copy()
pm["day"] = pm.datetime.dt.tz_convert("Asia/Almaty").dt.date  # локальные сутки; tzdata учитывает исторический сдвиг (UTC+6 до 01.03.2024)
daily = pm.groupby(["stationId", "day"]).value.agg(["mean", "size"]).reset_index()
daily = daily[daily["size"] >= 18]
res = {}
for s, g in daily.groupby("stationId"):
    res[s] = {"valid_days": int(len(g)),
              "first_day": str(g.day.min()), "last_day": str(g.day.max()),
              "median_daily_mean": round(float(g["mean"].median()), 1),
              "days_gt_15_if_ugm3": int((g["mean"] > 15).sum()),
              "days_gt_35_if_ugm3": int((g["mean"] > 35).sum())}
out["pm25_daily"] = res
piv = daily.pivot(index="day", columns="stationId", values="mean").dropna()
out["pm25_common_valid_days"] = int(len(piv))
if len(piv) >= 5:
    out["pm25_daily_spearman_between_posts"] = round(float(piv.corr(method="spearman").iloc[0, 1]), 2)
    out["pm25_median_abs_diff_between_posts"] = round(float((piv.iloc[:, 0] - piv.iloc[:, 1]).abs().median()), 1)
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
