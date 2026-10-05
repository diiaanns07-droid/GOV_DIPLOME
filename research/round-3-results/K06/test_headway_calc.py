"""Hand-checked tests for headway_calc (synthetic toy inputs, not city data). Run: python3 -m unittest -v
Hand calculation (minutes), route R, direction 1, window 06:00-09:00:
  day A 2024-08-05 (Mon): 06:00, 06:10, 06:10 (exact dup), 06:10:30 (near dup <60 s), 06:20, 06:30
      kept 06:00, 06:10, 06:20, 06:30 -> headways 10,10,10  H=10 CV=0 W=5   covered 30
  day B 2024-08-06 (Tue): 06:00, 06:30, 07:00 -> headways 30,30  H=30 CV=0 W=15  covered 60
  pooled headways 10,10,10,30,30: H=18, var=(3*64+2*144)/5=96, CV^2=96/324
      pooled formula 9*(1+96/324)=11.6667 = sum h^2/(2 sum h) = 2100/180
  time weighted (30*5 + 60*15)/90 = 11.6667; day-equal mean (5+15)/2 = 10; daily median 10
  PTAL 18/2+2 = 11; between-day excess = 11.6667 - 9 = 2.6667; within-day excess = 0
Clipping, window 06:00-06:15 on day A: integral 10^2/2 + int_10^15 (20-t) dt = 50 + 37.5 = 87.5 -> 87.5/15 = 5.8333
"""
import unittest
from headway_calc import compute, parse_windows, hms, clean_day, day_window_stats

M = 60


def dep(date, *times, r="R", d="1"):
    return [(r, d, date, hms(t)) for t in times]


TOY = dep("2024-08-05", "06:00:00", "06:10:00", "06:10:00", "06:10:30", "06:20:00", "06:30:00") + \
      dep("2024-08-06", "06:00:00", "06:30:00", "07:00:00")


class TwoDayExample(unittest.TestCase):
    def setUp(self):
        self.res = compute(TOY, parse_windows("06:00-09:00"), min_day_share=0)
        self.s = [x for x in self.res["summary"] if x["day_type"] == "all"][0]

    def test_cleaning_counters(self):
        self.assertEqual(self.res["counters"]["exact_duplicates"], 1)
        self.assertEqual(self.res["counters"]["near_duplicates"], 1)

    def test_daily(self):
        days = {x["date"]: x for x in self.res["days"]}
        self.assertAlmostEqual(days["2024-08-05"]["H_min"], 10)
        self.assertAlmostEqual(days["2024-08-05"]["cv"], 0)
        self.assertAlmostEqual(days["2024-08-05"]["wait_clipped_min"], 5)
        self.assertAlmostEqual(days["2024-08-06"]["wait_clipped_min"], 15)
        self.assertAlmostEqual(days["2024-08-06"]["covered_min"], 60)

    def test_methods(self):
        s = self.s
        self.assertAlmostEqual(s["pooled_H_min"], 18)
        self.assertAlmostEqual(s["pooled_cv"] ** 2, 96 / 324)
        self.assertAlmostEqual(s["median_daily_cv"], 0)
        self.assertAlmostEqual(s["pooled_formula_wait_min"], 2100 / 180)
        self.assertAlmostEqual(s["time_weighted_wait_min"], 2100 / 180)
        self.assertAlmostEqual(s["day_equal_mean_wait_min"], 10)
        self.assertAlmostEqual(s["daily_median_wait_min"], 10)
        self.assertAlmostEqual(s["ptal_wait_min"], 11)
        self.assertAlmostEqual(s["excess_between_days_min"], 2100 / 180 - 9)
        self.assertAlmostEqual(s["excess_within_day_min"], 0)

    def test_pooled_formula_equals_time_weighted_when_unclipped(self):
        self.assertAlmostEqual(self.s["pooled_formula_wait_min"], self.s["time_weighted_wait_min"])


class Boundaries(unittest.TestCase):
    def test_window_clipping(self):
        kept, _ = clean_day([hms(t) for t in ("06:00:00", "06:10:00", "06:20:00")], 60)
        integral, covered, by_start, _ = day_window_stats(kept, hms("06:00:00"), hms("06:15:00"), 3 * 3600)
        self.assertAlmostEqual(covered / M, 15)
        self.assertAlmostEqual(integral / covered / M, 87.5 / 15)
        self.assertEqual(len(by_start), 2)  # both headways start inside [06:00, 06:15)

    def test_midnight_gtfs_times(self):
        res = compute(dep("2024-08-05", "23:30:00", "23:50:00", "24:05:00"), parse_windows("23:00-25:00"),
                      min_day_share=0)
        day = res["days"][0]
        self.assertAlmostEqual(day["H_min"], 17.5)  # 20 and 15 min, same service date
        self.assertAlmostEqual(day["covered_min"], 35)

    def test_no_link_across_dates(self):
        res = compute(dep("2024-08-05", "21:00:00", "22:00:00") + dep("2024-08-06", "06:00:00", "06:10:00"),
                      parse_windows("00:00-24:00"), min_day_share=0)
        self.assertEqual(sorted(round(x["covered_min"]) for x in res["days"]), [10, 60])

    def test_service_break_excluded(self):
        res = compute(dep("2024-08-05", "06:00:00", "06:10:00", "10:30:00", "10:40:00"),
                      parse_windows("06:00-12:00"), min_day_share=0)
        day = res["days"][0]
        self.assertAlmostEqual(day["covered_min"], 20)  # 4h20 gap > 3 h is not waiting time
        self.assertEqual(res["counters"]["service_breaks"], 1)

    def test_arrivals_outside_observation_not_counted(self):
        res = compute(dep("2024-08-05", "07:00:00", "07:20:00"), parse_windows("06:00-09:00"), min_day_share=0)
        self.assertAlmostEqual(res["days"][0]["covered_min"], 20)
        self.assertAlmostEqual(res["days"][0]["wait_clipped_min"], 10)

    def test_incomplete_day_excluded(self):
        full = dep("2024-08-05", *[f"{h:02d}:00:00" for h in range(6, 16)]) + \
               dep("2024-08-06", *[f"{h:02d}:00:00" for h in range(6, 16)]) + \
               dep("2024-08-07", "06:00:00", "07:00:00")
        res = compute(full, parse_windows("06:00-16:00"), min_day_share=0.5)
        self.assertEqual([x["date"] for x in res["excluded_days"]], ["2024-08-07"])

    def test_bad_window(self):
        with self.assertRaises(ValueError):
            parse_windows("09:00-06:00")


if __name__ == "__main__":
    unittest.main()
