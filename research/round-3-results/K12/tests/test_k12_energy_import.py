"""Tests for k12_energy_import.py (stdlib unittest). Run: python -m unittest discover -s tests -v"""
import calendar
import csv
import datetime as dt
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "energy_import"))
import k12_energy_import as m  # noqa: E402

WINDOW = (dt.date(2025, 1, 1), dt.date(2025, 12, 31))
BASE = {"building_id": "B1", "city_id": "kz.shymkent", "country": "KZ", "object_type": "school",
        "electricity_kwh": "5000", "unit": "kWh", "value_status": "reported", "reading_type": "actual",
        "coverage_share": "1", "floor_area_m2": "2000", "area_source": "techpassport", "kind": "synthetic",
        "source_id": "test", "source_locator": "test", "measurement_terms": "synthetic", "note": ""}


def month(mth, **over):
    last = calendar.monthrange(2025, mth)[1]
    return dict(BASE, period_start=f"2025-{mth:02d}-01", period_end=f"2025-{mth:02d}-{last:02d}", **over)


def year(**over):
    return [month(i, **over) for i in range(1, 13)]


def run_rows(rows, **kw):
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "in.csv"
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=m.FIELDS)
            w.writeheader()
            w.writerows(rows)
        return m.run(p, WINDOW, n_sim=200, **kw)


def building(buildings, bid):
    return next(b for b in buildings if b["building_id"] == bid)


class RowRules(unittest.TestCase):
    def test_valid_year_is_ranked_as_annual(self):
        result, rows, buildings, _ = run_rows(year())
        b = building(buildings, "B1")
        self.assertEqual(result["rows_rejected"], 0)
        self.assertEqual(b["reasons_not_ranked"], [])
        self.assertAlmostEqual(b["eui_window"], 12 * 5000 / 2000)
        self.assertTrue(b["eui_is_annual"])

    def test_negative_rejected(self):
        _, rows, buildings, _ = run_rows(year()[:-1] + [month(12, electricity_kwh="-5")])
        self.assertIn("VALUE_NEGATIVE", rows[-1]["reasons"])
        self.assertIn("INCOMPLETE_WINDOW", building(buildings, "B1")["reasons_not_ranked"])

    def test_missing_is_not_zero(self):
        cases = {
            ("", "missing"): ([], "accepted"),
            ("", "reported"): (["VALUE_EMPTY_BUT_REPORTED"], "rejected"),
            ("0", "reported"): (["ZERO_NOT_CONFIRMED"], "rejected"),
            ("0", "reported_zero"): ([], "accepted"),
            ("10", "missing"): (["VALUE_STATUS_CONFLICT"], "rejected"),
            ("10", "reported_zero"): (["VALUE_STATUS_CONFLICT"], "rejected"),
        }
        for (value, status), (reasons, expected) in cases.items():
            with self.subTest(value=value, status=status):
                _, rows, _, _ = run_rows([month(1, electricity_kwh=value, value_status=status)])
                self.assertEqual(rows[0]["reasons"], reasons)
                self.assertEqual(rows[0]["status"], expected)

    def test_missing_month_breaks_window_and_is_not_annualised(self):
        rows = year()
        rows[6] = month(7, electricity_kwh="", value_status="missing")
        _, _, buildings, _ = run_rows(rows)
        b = building(buildings, "B1")
        self.assertIn("INCOMPLETE_WINDOW", b["reasons_not_ranked"])
        self.assertIsNone(b["eui_window"])
        self.assertEqual(b["days_with_value"], 365 - 31)

    def test_confirmed_zero_counts_as_covered_but_flags(self):
        rows = year()
        rows[7] = month(8, electricity_kwh="0", value_status="reported_zero")
        _, _, buildings, _ = run_rows(rows)
        b = building(buildings, "B1")
        self.assertEqual(b["reasons_not_ranked"], [])
        self.assertIn("ZERO_REPORTED_IN_WINDOW", b["flags"])

    def test_units(self):
        cases = {"kWh": (5000, []), "кВт·ч": (5000, []), "MWh": (5_000_000, ["UNIT_CONVERTED"]),
                 "тыс. кВт·ч": (5_000_000, ["UNIT_CONVERTED"])}
        for unit, (kwh, flags) in cases.items():
            with self.subTest(unit=unit):
                _, rows, _, _ = run_rows([month(1, unit=unit)])
                self.assertEqual(rows[0]["reasons"], [])
                self.assertEqual(rows[0]["kwh"], kwh)
                self.assertEqual(rows[0]["flags"], flags)
        for unit, reason in {"kW": "UNIT_NOT_ELECTRIC_ENERGY", "Gcal": "UNIT_NOT_ELECTRIC_ENERGY",
                             "m3": "UNIT_NOT_ELECTRIC_ENERGY", "kVAh": "UNIT_UNKNOWN"}.items():
            with self.subTest(unit=unit):
                _, rows, _, _ = run_rows([month(1, unit=unit)])
                self.assertEqual(rows[0]["reasons"], [reason])

    def test_numbers(self):
        _, rows, _, _ = run_rows([month(1, electricity_kwh="5 000,5"), month(2, electricity_kwh="1,234.5"),
                                  month(3, electricity_kwh="abc")])
        self.assertEqual(rows[0]["kwh"], 5000.5)
        self.assertIn("DECIMAL_COMMA", rows[0]["flags"])
        self.assertIn("VALUE_NOT_NUMBER", rows[1]["reasons"])
        self.assertIn("VALUE_NOT_NUMBER", rows[2]["reasons"])

    def test_periods(self):
        _, rows, _, _ = run_rows([dict(month(2), period_start="2025-02-30"),
                                  dict(month(3), period_start="2025-03-31", period_end="2025-03-01"),
                                  dict(month(4), period_start="01.04.2025")])
        self.assertEqual(rows[0]["reasons"], ["PERIOD_INVALID"])
        self.assertEqual(rows[1]["reasons"], ["PERIOD_END_BEFORE_START"])
        self.assertEqual(rows[2]["reasons"], ["PERIOD_INVALID"])

    def test_city_rules(self):
        _, rows, _, _ = run_rows([month(1, city_id="kz.almaty"), month(1, city_id="kz.astana", country="GB", building_id="B2"),
                                  month(1, city_id="gb.unknown", country="GB", building_id="B3")])
        self.assertEqual(rows[0]["reasons"], ["CITY_INVALID"])
        self.assertEqual(rows[1]["reasons"], ["CITY_COUNTRY_MISMATCH"])
        self.assertEqual(rows[2]["reasons"], [])

    def test_kind_hypothesis_and_required(self):
        _, rows, _, _ = run_rows([month(1, kind="hypothesis"), month(2, measurement_terms=""),
                                  month(3, coverage_share="1.2"), month(4, reading_type="by_eye")])
        self.assertEqual(rows[0]["reasons"], ["KIND_INVALID"])
        self.assertEqual(rows[1]["reasons"], ["REQUIRED_EMPTY"])
        self.assertEqual(rows[1]["empty_required"], ["measurement_terms"])
        self.assertEqual(rows[2]["reasons"], ["COVERAGE_INVALID"])
        self.assertEqual(rows[3]["reasons"], ["READING_TYPE_INVALID"])


class CrossRowRules(unittest.TestCase):
    def test_exact_duplicate_keeps_first(self):
        rows = year() + [month(6)]
        result, out, buildings, _ = run_rows(rows)
        self.assertEqual(out[-1]["reasons"], ["DUPLICATE_EXACT"])
        self.assertEqual(out[5]["reasons"], [])
        self.assertEqual(building(buildings, "B1")["reasons_not_ranked"], [])

    def test_conflicting_duplicate_rejects_both(self):
        rows = year() + [month(6, electricity_kwh="7000")]
        _, out, buildings, _ = run_rows(rows)
        self.assertEqual(out[5]["reasons"], ["DUPLICATE_CONFLICT"])
        self.assertEqual(out[-1]["reasons"], ["DUPLICATE_CONFLICT"])
        self.assertIn("INCOMPLETE_WINDOW", building(buildings, "B1")["reasons_not_ranked"])

    def test_long_period_overlapping_several_short_ones(self):
        rows = year() + [dict(month(1), period_end="2025-03-31", electricity_kwh="15000")]
        _, out, _, _ = run_rows(rows)
        flagged = [x["line"] for x in out if "PERIOD_OVERLAP" in x["reasons"]]
        self.assertEqual(sorted(flagged), [2, 3, 4, 14])  # Jan, Feb, Mar and the quarter

    def test_billing_periods_not_aligned_with_months(self):
        # 15th..14th periods fully covering a window aligned with them -> complete
        rows = []
        for i in range(12):
            s = dt.date(2025, 1 + i, 15) if i < 12 else None
            e = (dt.date(2025 + (i + 1) // 12, (i + 1) % 12 + 1, 14))
            rows.append(dict(BASE, period_start=s.isoformat(), period_end=e.isoformat()))
        aligned = (dt.date(2025, 1, 15), dt.date(2026, 1, 14))
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "in.csv"
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=m.FIELDS)
                w.writeheader()
                w.writerows(rows)
            _, _, b_aligned, _ = m.run(p, aligned, n_sim=50)
            _, _, b_calendar, excl = m.run(p, WINDOW, n_sim=50)
        self.assertEqual(b_aligned[0]["reasons_not_ranked"], [])
        self.assertIn("INCOMPLETE_WINDOW", b_calendar[0]["reasons_not_ranked"])
        self.assertEqual([e["reason"] for e in excl], ["PERIOD_CROSSES_WINDOW"])

    def test_mixed_month_and_quarter_rows_without_overlap(self):
        rows = [dict(month(1), period_end="2025-03-31", electricity_kwh="15000")] + [month(i) for i in range(4, 13)]
        _, out, buildings, _ = run_rows(rows)
        self.assertEqual([x["reasons"] for x in out], [[]] * 10)
        self.assertAlmostEqual(building(buildings, "B1")["kwh_window"], 60000)


class BuildingRules(unittest.TestCase):
    def test_area_rules(self):
        rows = (year(building_id="ZERO", floor_area_m2="0") + year(building_id="EMPTY", floor_area_m2="") +
                [dict(r, building_id="DIFF", floor_area_m2="2000" if i else "2100") for i, r in enumerate(year())])
        _, _, buildings, _ = run_rows(rows)
        self.assertIn("AREA_NOT_POSITIVE", building(buildings, "ZERO")["reasons_not_ranked"])
        self.assertIn("AREA_UNKNOWN", building(buildings, "EMPTY")["reasons_not_ranked"])
        self.assertIn("AREA_INCONSISTENT", building(buildings, "DIFF")["reasons_not_ranked"])

    def test_norm_and_estimated(self):
        rows = year(building_id="NORM")
        rows[0] = dict(rows[0], reading_type="norm")
        est = year(building_id="EST")
        est[0] = dict(est[0], reading_type="estimated")
        _, _, buildings, _ = run_rows(rows + est)
        self.assertIn("NORM_ACCRUAL_IN_WINDOW", building(buildings, "NORM")["reasons_not_ranked"])
        e = building(buildings, "EST")
        self.assertEqual(e["reasons_not_ranked"], [])
        self.assertEqual(e["confidence"], "low")

    def test_two_cities_for_one_building(self):
        rows = year()
        rows[11] = dict(rows[11], city_id="kz.astana")
        _, _, buildings, _ = run_rows(rows)
        b = building(buildings, "B1")
        self.assertIn("CITY_INCONSISTENT", b["reasons_not_ranked"])
        self.assertEqual(b["city_id"], "kz.astana+kz.shymkent")

    def test_metering_coverage_threshold(self):
        _, _, buildings, _ = run_rows(year(coverage_share="0.85"))
        self.assertIn("METERING_COVERAGE_BELOW_MIN", building(buildings, "B1")["reasons_not_ranked"])

    def test_groups_never_mix_cities_or_synthetic_with_real(self):
        rows = (year(building_id="S1") + year(building_id="A1", city_id="kz.astana") +
                year(building_id="R1", kind="observed"))
        result, _, _, _ = run_rows(rows)
        keys = sorted((g["city_id"], g["data_class"]) for g in result["groups"])
        self.assertEqual(keys, [("kz.astana", "synthetic"), ("kz.shymkent", "real"), ("kz.shymkent", "synthetic")])
        self.assertTrue(all(g["n"] == 1 for g in result["groups"]))

    def test_short_window_is_not_called_annual(self):
        rows = [month(1), month(2), month(3)]
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "in.csv"
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=m.FIELDS)
                w.writeheader()
                w.writerows(rows)
            _, _, buildings, _ = m.run(p, (dt.date(2025, 1, 1), dt.date(2025, 3, 31)), n_sim=50)
        self.assertIsNotNone(buildings[0]["eui_window"])
        self.assertFalse(buildings[0]["eui_is_annual"])


class RankingAndFiles(unittest.TestCase):
    def test_ranking_is_deterministic_and_reports_area_sensitivity(self):
        rows = []
        for i, (kwh, area) in enumerate([(9000, 3000), (6000, 3200), (4000, 2500), (3000, 4100), (5200, 1800)]):
            rows += year(building_id=f"S{i}", electricity_kwh=str(kwh), floor_area_m2=str(area))
        r1, _, _, _ = run_rows(rows)
        r2, _, _, _ = run_rows(rows)
        self.assertEqual(r1["groups"], r2["groups"])
        g = r1["groups"][0]
        self.assertEqual(g["top_n"], 1)
        self.assertEqual(g["ranking"][0]["building_id"], "S0")
        self.assertIn("sigma_log_0.2", g["area_error_mc"])

    def test_coverage_adjustment_changes_order(self):
        rows = year(building_id="FULL", electricity_kwh="5000") + year(
            building_id="PARTIAL", electricity_kwh="4600", coverage_share="0.9")
        result, _, _, _ = run_rows(rows, top_share=0.5)
        g = result["groups"][0]
        self.assertEqual(g["ranking"][0]["building_id"], "FULL")  # default: no adjustment
        self.assertEqual(g["coverage_adjusted_entering"], ["PARTIAL"])

    def test_missing_columns_is_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "in.csv"
            p.write_text("building_id,city_id\nB1,kz.shymkent\n", encoding="utf-8")
            res = m.run(p, WINDOW)
        self.assertEqual(res["fatal"], "SCHEMA_MISSING_COLUMNS")

    def test_semicolon_delimiter_and_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "in.csv"
            with open(p, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=m.FIELDS, delimiter=";")
                w.writeheader()
                w.writerows(year())
            result, _, _, _ = m.run(p, WINDOW, n_sim=50)
        self.assertEqual(result["delimiter"], ";")
        self.assertEqual(result["buildings_ranked"], 1)

    def test_template_header_and_request_fields(self):
        header = (ROOT / "template/operator_monthly_electricity_TEMPLATE.csv").read_text(encoding="utf-8").strip()
        self.assertEqual(header.split(","), m.FIELDS)
        request = (ROOT / "REQUEST_FIELDS.txt").read_text(encoding="utf-8")
        for f in m.FIELDS:
            self.assertIn(f, request)

    def test_bdg1_example_keeps_real_country_and_names(self):
        p = ROOT / "examples/bdg1_gb_2014_2015/input.csv"
        with open(p, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({r["country"] for r in rows}, {"GB"})
        self.assertEqual({r["city_id"] for r in rows}, {"gb.unknown"})
        self.assertTrue(all(r["building_id"].startswith("bdg1:PrimClass_") for r in rows))
        self.assertTrue(all(r["measurement_terms"].startswith("unknown") for r in rows))
        self.assertEqual({r["period_start"][:4] for r in rows}, {"2014", "2015"})


if __name__ == "__main__":
    unittest.main()
