"""Builds the two example inputs for k12_energy_import.py (stdlib only, no network).

1. bdg1_gb_2014_2015/input.csv — REAL international data: 74 UK school buildings from BDG1
   (Building Data Genome 1 @521a6c0f), local calendar months Dec 2014 - Nov 2015, built from
   ../inputs/ (K12 round 2 extract, see ../inputs/MANIFEST.json). Building names are kept as in
   BDG1 (bdg1:PrimClass_*). NOT Shymkent, NOT Astana. city_id = gb.unknown: BDG1 meta has no city.
2. synthetic_cases/input.csv — SYNTHETIC rows invented to exercise every validation rule.
   City ids are Kazakh only to test the operator format; these are NOT buildings of either city.
"""
import calendar
import csv
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
INPUTS = HERE.parent / "inputs"
sys.path.insert(0, str(HERE.parent / "energy_import"))
from k12_energy_import import FIELDS  # noqa: E402

BDG1_TERMS = "unknown: repository LICENSE is MIT (software); terms of the original measurement sources are not listed"


def month_bounds(ym):
    y, m = map(int, ym.split("-"))
    return f"{ym}-01", f"{ym}-{calendar.monthrange(y, m)[1]:02d}"


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def bdg1_rows():
    with open(INPUTS / "K12_bdg1_schools_meta.csv", encoding="utf-8") as f:
        meta = {r["uid"]: r for r in csv.DictReader(f)}
    with open(INPUTS / "K12_bdg1_schools_monthly.csv", encoding="utf-8") as f:
        monthly = list(csv.DictReader(f))
    rows = []
    for r in monthly:
        m = meta[r["uid"]]
        if m["timezone"] != "Europe/London":
            continue
        start, end = month_bounds(r["month_local"])
        hours_obs, hours_exp = int(r["hours_observed"]), int(r["hours_expected"])
        kwh = float(r["kwh_observed_sum"])
        if hours_obs == 0:
            value, status = "", "missing"
        elif kwh == 0:
            value, status = "0", "reported_zero"
        else:
            value, status = r["kwh_observed_sum"], "reported"
        rows.append({
            "building_id": f"bdg1:{r['uid']}", "city_id": "gb.unknown", "country": "GB",
            "object_type": "school" if m["subindustry"] == "Primary/Secondary School" else "other",
            "period_start": start, "period_end": end, "electricity_kwh": value, "unit": "kWh",
            "value_status": status, "reading_type": "actual",
            "coverage_share": f"{hours_obs / hours_exp:.4f}", "floor_area_m2": m["sqm"],
            "area_source": "dataset_metadata", "kind": "derived", "source_id": "BDG1@521a6c0f",
            "source_locator": f"data/raw/temp_open_utc.csv:{r['uid']} + meta_open.csv",
            "measurement_terms": BDG1_TERMS,
            "note": "GB school Dec2014-Nov2015; sum of observed hours, gaps not filled; unit kWh assumed (not stated by source)",
        })
    return rows


def synthetic_rows():
    base = {"country": "KZ", "object_type": "school", "unit": "kWh", "value_status": "reported",
            "reading_type": "actual", "coverage_share": "1", "area_source": "techpassport",
            "kind": "synthetic", "source_id": "K12-synthetic", "source_locator": "make_examples.py",
            "measurement_terms": "synthetic: invented test values", "note": "SYNTHETIC"}

    def year(bid, city, kwh, area, over=None):
        out = []
        for mth in range(1, 13):
            s, e = month_bounds(f"2025-{mth:02d}")
            row = dict(base, building_id=bid, city_id=city, period_start=s, period_end=e,
                       electricity_kwh=str(kwh), floor_area_m2=str(area))
            row.update((over or {}).get(mth, {}))
            out.append(row)
        return out

    rows = []
    # five complete buildings per city, so a top-N exists in each group
    for i, (kwh, area) in enumerate([(9000, 3000), (6000, 3200), (4000, 2500), (3000, 4100), (5200, 1800)], 1):
        rows += year(f"SYN-SHY-{i:02d}", "kz.shymkent", kwh, area)
    for i, (kwh, area) in enumerate([(7000, 2600), (5000, 3000), (3500, 2900), (8000, 3600), (2500, 2000)], 1):
        rows += year(f"SYN-AST-{i:02d}", "kz.astana", kwh, area)
    # problem buildings (Shymkent group), one theme each
    rows += year("SYN-SHY-MISSING-MONTH", "kz.shymkent", 5000, 2000,
                 over={7: {"electricity_kwh": "", "value_status": "missing"}})
    rows += year("SYN-SHY-ZERO-UNCONFIRMED", "kz.shymkent", 5000, 2000,
                 over={8: {"electricity_kwh": "0"}})
    rows += year("SYN-SHY-ZERO-CONFIRMED", "kz.shymkent", 5000, 2000,
                 over={8: {"electricity_kwh": "0", "value_status": "reported_zero"}})
    rows += year("SYN-SHY-NEGATIVE", "kz.shymkent", 5000, 2000, over={3: {"electricity_kwh": "-120"}})
    rows += year("SYN-SHY-AREA-ZERO", "kz.shymkent", 5000, 0)
    rows += year("SYN-SHY-AREA-UNKNOWN", "kz.shymkent", 5000, "", over={m: {"area_source": "unknown"} for m in range(1, 13)})
    rows += year("SYN-SHY-NORM", "kz.shymkent", 5000, 2000, over={m: {"reading_type": "norm"} for m in (1, 2)})
    rows += year("SYN-SHY-MWH", "kz.shymkent", 5.0, 2000, over={m: {"unit": "MWh"} for m in range(1, 13)})
    rows += year("SYN-SHY-KW", "kz.shymkent", 5000, 2000, over={4: {"unit": "kW"}})
    rows += year("SYN-SHY-GCAL", "kz.shymkent", 5000, 2000, over={5: {"unit": "Gcal"}})
    rows += year("SYN-SHY-LOWCOV", "kz.shymkent", 5000, 2000, over={m: {"coverage_share": "0.6"} for m in (1, 2, 3)})
    dup = year("SYN-SHY-DUP-EXACT", "kz.shymkent", 5000, 2000)
    rows += dup + [dict(dup[5])]
    conflict = year("SYN-SHY-DUP-CONFLICT", "kz.shymkent", 5000, 2000)
    rows += conflict + [dict(conflict[5], electricity_kwh="7000")]
    # billing periods not aligned with calendar months: 15th..14th, covering a different window
    for mth in range(1, 13):
        y2, m2 = (2025, mth + 1) if mth < 12 else (2026, 1)
        rows.append(dict(base, building_id="SYN-SHY-BILLING-15TH", city_id="kz.shymkent",
                         period_start=f"2025-{mth:02d}-15", period_end=f"{y2}-{m2:02d}-14",
                         electricity_kwh="5000", floor_area_m2="2000"))
    # one quarterly row overlapping monthly rows of the same building
    ov = year("SYN-SHY-OVERLAP", "kz.shymkent", 5000, 2000)
    rows += ov + [dict(ov[0], period_start="2025-01-01", period_end="2025-03-31", electricity_kwh="15000")]
    rows += year("SYN-SHY-ESTIMATED", "kz.shymkent", 5000, 2000, over={m: {"reading_type": "estimated"} for m in (6, 7)})
    rows += year("SYN-SHY-TWO-CITIES", "kz.shymkent", 5000, 2000, over={12: {"city_id": "kz.astana"}})
    rows += [dict(base, building_id="SYN-ALMATY-01", city_id="kz.almaty", period_start="2025-01-01",
                  period_end="2025-01-31", electricity_kwh="5000", floor_area_m2="2000"),
             dict(base, building_id="SYN-SHY-BADDATE", city_id="kz.shymkent", period_start="2025-02-30",
                  period_end="2025-03-01", electricity_kwh="5000", floor_area_m2="2000"),
             dict(base, building_id="SYN-SHY-BACKWARDS", city_id="kz.shymkent", period_start="2025-03-31",
                  period_end="2025-03-01", electricity_kwh="5000", floor_area_m2="2000"),
             dict(base, building_id="", city_id="kz.shymkent", period_start="2025-01-01",
                  period_end="2025-01-31", electricity_kwh="5000", floor_area_m2="2000"),
             dict(base, building_id="SYN-SHY-HYPOTHESIS", city_id="kz.shymkent", period_start="2025-01-01",
                  period_end="2025-01-31", electricity_kwh="5000", floor_area_m2="2000", kind="hypothesis"),
             dict(base, building_id="SYN-SHY-COMMA", city_id="kz.shymkent", period_start="2025-01-01",
                  period_end="2025-01-31", electricity_kwh="5000,5", floor_area_m2="2000")]
    return rows


if __name__ == "__main__":
    b = bdg1_rows()
    write(HERE / "bdg1_gb_2014_2015" / "input.csv", b)
    s = synthetic_rows()
    write(HERE / "synthetic_cases" / "input.csv", s)
    print({"bdg1_rows": len(b), "bdg1_buildings": len({r["building_id"] for r in b}), "synthetic_rows": len(s)})
