"""Погода Астаны для прогноза R13: дневной архив Open-Meteo (LOCAL-9) → месячные показатели.

Реальный файл кладёт LOCAL-9: data/civic/astana/weather/openmeteo_daily.csv (CC BY 4.0, «Weather data by Open-Meteo.com»).
Пока его нет, берётся ФИКСТУРА ml/civic_forecast/data/weather_fixture.csv — синтетический ряд того же формата
по климатическим нормам Астаны (seed 14). Источник всегда виден в meta["evidence_type"]: real | synthetic.

Загрузчик терпим к формату: принимает и «чистый» CSV (date,temperature_2m_max,…), и CSV, скачанный с сайта
Open-Meteo (строки метаданных сверху, колонка time, единицы в скобках: «temperature_2m_max (°C)»).

Месячные показатели (то, что понятно акимату):
  snowfall_cm  — снег за месяц, см          thaw_days — дни с оттепелью (max > 0 и min < 0) — гололёд и ямы
  frost_days   — дни с морозом ниже −20 °C   hot_days  — дни жарче +28 °C
  precip_mm    — осадки, мм                  tmean     — средняя температура
Прогноз на следующий месяц использует только известное заранее: погоду прошедших месяцев и норму
месяца по прошлым годам (normals) — фактическая погода будущего месяца в признаки не попадает.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
import io
import json
import math
from pathlib import Path
import random

REPO = Path(__file__).resolve().parents[2]
REAL_PATH = REPO / "data" / "civic" / "astana" / "weather" / "openmeteo_daily.csv"
FIXTURE_PATH = Path(__file__).with_name("data") / "weather_fixture.csv"
COLUMNS = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "snowfall_sum", "rain_sum",
           "wind_speed_10m_max")
MONTHLY_KEYS = ("snowfall_cm", "thaw_days", "frost_days", "hot_days", "precip_mm", "tmean")

# Климатические нормы Астаны (средняя температура, осадки мм) — для синтетической фикстуры.
NORMAL_T = (-14.2, -13.4, -6.0, 5.4, 13.8, 19.4, 20.9, 18.6, 12.1, 4.1, -5.4, -11.8)
NORMAL_P = (17, 14, 17, 20, 31, 39, 51, 32, 23, 28, 25, 21)


def _clean_name(name: str) -> str:
    name = name.strip().split(" (")[0].strip()
    return "date" if name == "time" else name


def parse_csv(text: str):
    """Строки {date, …} из CSV любого из двух видов. Пустые значения → None."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        head = line.split(",")[0].strip().lower()
        if head in ("date", "time"):
            start = i
            break
    if start is None:
        raise ValueError("В CSV погоды нет строки заголовка с колонкой date/time.")
    reader = csv.reader(io.StringIO("\n".join(lines[start:])))
    header = [_clean_name(h) for h in next(reader)]
    rows = []
    for raw in reader:
        if not raw or not raw[0].strip():
            continue
        row = {"date": raw[0].strip()[:10]}
        for name, value in zip(header[1:], raw[1:]):
            value = value.strip()
            row[name] = float(value) if value not in ("", "nan", "NaN") else None
        rows.append(row)
    return rows


def load_daily(path: Path | None = None):
    """(rows, meta). Без явного пути: реальный файл LOCAL-9, если он есть, иначе синтетическая фикстура."""
    if path is None:
        path = REAL_PATH if REAL_PATH.is_file() else FIXTURE_PATH
    path = Path(path)
    rows = parse_csv(path.read_text(encoding="utf-8-sig"))
    synthetic = path.resolve() == FIXTURE_PATH.resolve() or "SYNTHETIC" in path.read_text(encoding="utf-8")[:300]
    meta = {"path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
            "evidence_type": "synthetic" if synthetic else "real",
            "source": "синтетическая фикстура R13 (климатические нормы, seed 14)" if synthetic
            else "Open-Meteo Historical Weather API (LOCAL-9), CC BY 4.0, Weather data by Open-Meteo.com",
            "days": len(rows), "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None}
    return rows, meta


def monthly(rows) -> dict[str, dict]:
    """'YYYY-MM' → месячные показатели. Неполный месяц помечен complete=False."""
    out: dict[str, dict] = {}
    for row in rows:
        key = row["date"][:7]
        m = out.setdefault(key, {"days": 0, "snowfall_cm": 0.0, "thaw_days": 0, "frost_days": 0, "hot_days": 0,
                                 "precip_mm": 0.0, "_t": 0.0, "_tn": 0})
        m["days"] += 1
        tmax, tmin = row.get("temperature_2m_max"), row.get("temperature_2m_min")
        if row.get("snowfall_sum") is not None:
            m["snowfall_cm"] += row["snowfall_sum"]
        if row.get("precipitation_sum") is not None:
            m["precip_mm"] += row["precipitation_sum"]
        if tmax is not None and tmin is not None:
            m["thaw_days"] += int(tmax > 0 and tmin < 0)
            m["frost_days"] += int(tmin < -20)
            m["hot_days"] += int(tmax > 28)
            m["_t"] += (tmax + tmin) / 2
            m["_tn"] += 1
    for key, m in out.items():
        y, mo = int(key[:4]), int(key[5:])
        days_in_month = ((date(y + (mo == 12), mo % 12 + 1, 1)) - date(y, mo, 1)).days
        m["tmean"] = round(m.pop("_t") / m["_tn"], 1) if m["_tn"] else None
        m.pop("_tn")
        m["snowfall_cm"] = round(m["snowfall_cm"], 1)
        m["precip_mm"] = round(m["precip_mm"], 1)
        m["complete"] = m["days"] >= days_in_month
    return out


def normals(month_table: dict, calendar_month: int, before: str) -> dict:
    """Норма календарного месяца по полным месяцам строго раньше before ('YYYY-MM'). Нет данных — None."""
    values = [m for key, m in month_table.items() if int(key[5:]) == calendar_month and key < before and m["complete"]]
    if not values:
        return {k: None for k in MONTHLY_KEYS} | {"years": 0}
    out = {k: round(sum((v[k] or 0) for v in values) / len(values), 1) for k in MONTHLY_KEYS}
    out["years"] = len(values)
    out["first_year"] = min(int(k[:4]) for k, m in month_table.items() if m in values)
    return out


def make_fixture(first: date = date(2023, 1, 1), last: date = date(2026, 10, 9), seed: int = 14) -> str:
    """Синтетический дневной ряд по нормам Астаны: AR(1)-аномалия температуры, осадки, снег при t < 0."""
    rng = random.Random(seed)
    anomaly = 0.0
    out = io.StringIO()
    out.write("# SYNTHETIC weather fixture for R13 (climate normals of Astana, seed 14). NOT Open-Meteo data. "
              "Real archive: LOCAL-9 data/civic/astana/weather/openmeteo_daily.csv\n")
    out.write("date," + ",".join(COLUMNS) + "\n")
    day = first
    while day <= last:
        m = day.month - 1
        # Плавная норма по дням: между серединами соседних месяцев.
        frac = (day.day - 15) / 30
        nxt = (m + 1) % 12 if frac >= 0 else (m - 1) % 12
        t_norm = NORMAL_T[m] + (NORMAL_T[nxt] - NORMAL_T[m]) * abs(frac)
        sd = 4.5 if m in (10, 11, 0, 1, 2) else 2.8
        anomaly = 0.8 * anomaly + rng.gauss(0, sd * math.sqrt(1 - 0.64))
        tmean = t_norm + anomaly
        # Суточный размах в Астане летом ~13 °C, зимой ~9 °C.
        half = 6.5 if m in (4, 5, 6, 7) else 4.5
        tmax = tmean + half + rng.gauss(0, 1.2)
        tmin = tmean - half + rng.gauss(0, 1.2)
        wet_p = 0.3 if m in (4, 5, 6, 7) else 0.25
        precip = rng.expovariate(1 / (NORMAL_P[m] / (30 * wet_p))) if rng.random() < wet_p else 0.0
        snow = round(precip * 0.7, 2) if tmean < 0 else 0.0
        rain = round(precip, 2) if tmean >= 0 else 0.0
        wind = max(2.0, rng.gauss(18 if m in (10, 11, 0, 1, 2, 3) else 15, 5))
        out.write(f"{day.isoformat()},{tmax:.1f},{tmin:.1f},{precip:.2f},{snow:.2f},{rain:.2f},{wind:.1f}\n")
        day += timedelta(days=1)
    return out.getvalue()


def write_fixture(path: Path = FIXTURE_PATH) -> dict:
    text = make_fixture()
    path.write_text(text, encoding="utf-8")
    meta = {"evidence_type": "synthetic", "generator": "ml/civic_forecast/weather.py make_fixture(seed=14)",
            "note": "Синтетика по климатическим нормам Астаны. Заменяется реальным архивом LOCAL-9 автоматически.",
            "columns": ["date", *COLUMNS], "days": text.count("\n") - 2}
    path.with_suffix(".SOURCE.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta
