"""K06 round 3: isolated headway / waiting-time calculator for the historical Astana bus dataset.

City: Astana only. Data: Mansurova et al., Zenodo 15769359 (read via mirror Mrithula742/Bussure @ 0356bb5),
operator CTS, routes 10/12/46, 2024-07-29..2024-09-21. Trip start times are reconstructed from GPS by the
dataset authors; headways are measured at the trip start, not at every stop. Not a Shymkent dataset.

Keys are always explicit: (route, direction, service_date, window). Days are never mixed silently.

Cleaning rules (all counted in the output):
  R1 exact duplicates      same (route, direction, date, start rounded to 1 s) -> keep one departure.
  R2 near-duplicates       departure < min_headway_s after the previous kept one -> later departure dropped.
                           Zero/negative headways cannot survive sorting + R1/R2.
  R3 service breaks        gap > max_gap_s -> no passenger is assumed to wait inside it (arrival time excluded).
  R4 midnight              GTFS times >= 24:00:00 stay on their service date (seconds may exceed 86400);
                           end_time < start_time in trip durations -> +86400.
  R5 observation bounds    passenger arrivals before the first or after the last observed departure of a
                           service date are not counted (previous/next departure unknown). Headways are never
                           linked across service dates.
  R6 incomplete days       days with fewer kept departures than min_day_share x median for that
                           route+direction are excluded (counted).

Windows: half-open [start, end) in seconds of the service day. A headway is clipped to the window for the
passenger-time methods; the "by start" assignment (headway belongs to the window of its first departure)
is kept only to compare with AST-A06.

Methods per (route, direction, window, day type):
  pooled_formula   AST-A06: pool by-start headways over all days, W = H/2*(1+CV^2). Algebraically equals
                   sum(h^2)/(2*sum(h)), i.e. a time-weighted mean of daily waits; pooled CV, however,
                   includes between-day differences in headway level and overstates within-day irregularity.
  daily_median     median over days of W_d = H_d/2*(1+CV_d^2). A summary of typical days, NOT the expected
                   wait of a passenger.
  day_equal_mean   mean over days of the clipped daily wait (each day weight 1).
  time_weighted    sum over days of integral(wait dt) / sum of covered seconds: expected wait of a passenger
                   arriving uniformly at random over all observed service time in the window (recommended).
Waiting formula assumptions: passengers arrive uniformly at random, independent of the timetable, board the
first bus (no capacity limit), and do not use real-time information. With timetables/apps waits are shorter,
so the value is an upper-side estimate, not a forecast. PTAL baseline H/2 + 2 min is shown for comparison.
Standard library only.
"""
import argparse, csv, datetime, json, math, os, statistics as st, sys
from collections import Counter, defaultdict

DEFAULT_WINDOWS = "06:00-09:00,09:00-16:00,16:00-19:00,19:00-23:00"


def hms(t):
    h, m, s = t.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_windows(spec):
    out = []
    for part in spec.split(","):
        a, b = part.split("-")
        ws, we = hms(a + ":00"), hms(b + ":00")
        if we <= ws:
            raise ValueError(f"window {part}: end must be after start (use 24:00+ for after midnight)")
        out.append((part, ws, we))
    return out


def day_type(date):
    return "weekend" if datetime.date.fromisoformat(date).weekday() >= 5 else "weekday"


def clean_day(starts, min_headway_s):
    """R1 + R2 for one (route, direction, date). Returns kept sorted departures and counters."""
    c = Counter()
    rounded = sorted(round(t) for t in starts)
    uniq = []
    for t in rounded:
        if uniq and t == uniq[-1]:
            c["exact_duplicates"] += 1
        else:
            uniq.append(t)
    kept = []
    for t in uniq:
        if kept and t - kept[-1] < min_headway_s:
            c["near_duplicates"] += 1
        else:
            kept.append(t)
    return kept, c


def day_window_stats(kept, ws, we, max_gap_s):
    """Clipped passenger-time integral and by-start headways for one day and one window."""
    integral = covered = 0.0
    by_start = []
    breaks = 0
    for a, d in zip(kept, kept[1:]):
        h = d - a
        if h > max_gap_s:
            if ws <= a < we:
                breaks += 1
            continue
        if ws <= a < we:
            by_start.append(h)
        lo, hi = max(a, ws), min(d, we)
        if hi > lo:  # passenger arrives in [lo, hi), waits d - t
            integral += ((d - lo) ** 2 - (d - hi) ** 2) / 2
            covered += hi - lo
    return integral, covered, by_start, breaks


def mean_cv(v):
    m = st.mean(v)
    return m, (st.pstdev(v) / m if len(v) > 1 else 0.0)


def compute(departures, windows, min_headway_s=60, max_gap_s=3 * 3600, min_day_share=0.5, min_n=2):
    """departures: iterable of (route, direction, date 'YYYY-MM-DD', start seconds). Returns dict."""
    groups = defaultdict(list)
    for r, d, date, t in departures:
        groups[(r, d, date)].append(t)
    counters = Counter()
    kept = {}
    for k, v in groups.items():
        kept[k], c = clean_day(v, min_headway_s)
        counters.update(c)
        counters["departures_in"] += len(v)
    med = defaultdict(list)
    for (r, d, date), v in kept.items():
        med[(r, d)].append(len(v))
    med = {k: st.median(v) for k, v in med.items()}
    excluded_days = []
    days = []
    for (r, d, date), v in sorted(kept.items()):
        if len(v) < min_day_share * med[(r, d)]:
            excluded_days.append({"route": r, "direction": d, "date": date, "departures": len(v),
                                  "median_departures": med[(r, d)]})
            continue
        for wname, ws, we in windows:
            integral, covered, by_start, breaks = day_window_stats(v, ws, we, max_gap_s)
            counters["service_breaks"] += breaks
            if covered <= 0:
                continue
            row = {"route": r, "direction": d, "date": date, "day_type": day_type(date), "window": wname,
                   "covered_min": covered / 60, "wait_integral_min2": integral / 3600,
                   "wait_clipped_min": integral / covered / 60, "n_headways_by_start": len(by_start)}
            if len(by_start) >= min_n:
                m, cv = mean_cv(by_start)
                row.update({"H_min": m / 60, "cv": cv, "wait_formula_min": m / 2 * (1 + cv * cv) / 60,
                            "sum_h_min": sum(by_start) / 60, "sum_h2_min2": sum(h * h for h in by_start) / 3600})
            days.append(row)
    return {"counters": dict(counters), "excluded_days": excluded_days, "days": days,
            "summary": aggregate(days, groups_of(days)),
            "params": {"min_headway_s": min_headway_s, "max_gap_s": max_gap_s, "min_day_share": min_day_share,
                       "windows": [w[0] for w in windows]}}


def groups_of(days):
    g = defaultdict(list)
    for row in days:
        for dt in (row["day_type"], "all"):
            g[(row["route"], row["direction"], row["window"], dt)].append(row)
    return g


def aggregate(days, g):
    out = []
    for (r, d, w, dt), rows in sorted(g.items()):
        f = [x for x in rows if "H_min" in x]
        if not f:
            continue
        sh, sh2 = sum(x["sum_h_min"] for x in f), sum(x["sum_h2_min2"] for x in f)
        n = sum(x["n_headways_by_start"] for x in f)
        H = sh / n
        var = max(sh2 / n - H * H, 0.0)
        cv_p = math.sqrt(var) / H
        cov = sum(x["covered_min"] for x in rows)
        tw = sum(x["wait_integral_min2"] for x in rows) / cov
        # regular-service baseline: each day served at its own mean headway with zero variance,
        # weighted by that day's covered passenger time
        base = sum(x["covered_min"] * x["H_min"] / 2 for x in f) / sum(x["covered_min"] for x in f)
        out.append({
            "route": r, "direction": d, "window": w, "day_type": dt, "days": len(rows),
            "n_headways": n, "pooled_H_min": H, "pooled_cv": cv_p,
            "median_daily_cv": st.median(x["cv"] for x in f),
            "ptal_wait_min": H / 2 + 2,
            "pooled_formula_wait_min": H / 2 * (1 + cv_p ** 2),
            "daily_median_wait_min": st.median(x["wait_formula_min"] for x in f),
            "day_equal_mean_wait_min": st.mean(x["wait_clipped_min"] for x in rows),
            "time_weighted_wait_min": tw,
            "excess_between_days_min": base - H / 2,
            "excess_within_day_min": tw - base,
        })
    return out


def load_astana(gtfs_dir):
    """Adapter for the tab-separated Zenodo 15769359 files. Returns departures, durations, meta."""
    def tsv(name, enc="utf-8"):
        with open(os.path.join(gtfs_dir, name), encoding=enc, newline="") as f:
            return list(csv.DictReader(f, delimiter="\t"))
    routes = {x["route_id"]: x["route_short_name"] for x in tsv("routes.txt", "cp1251")}
    service_date = {x["service_id"]: x["date"] for x in tsv("calendar_dates.txt")}
    dep, dur, bad = [], [], Counter()
    for t in tsv("trips.txt"):
        try:
            a, b = hms(t["start_time"]), hms(t["end_time"])
        except ValueError:
            bad["bad_time"] += 1
            continue
        date = service_date.get(t["service_id"])
        if date is None:
            bad["unknown_service_id"] += 1
            continue
        if b < a:
            b += 86400
            bad["end_before_start_plus_24h"] += 1
        key = (routes[t["route_id"]], t["direction_id"], date)
        dep.append(key + (a,))
        dur.append(key + (a, b - a))
    return dep, dur, dict(bad)


def durations(dur, windows):
    """Trip duration end-start by start window. Includes terminal layover/dwell: NOT congestion."""
    g = defaultdict(list)
    for r, d, date, a, x in dur:
        for wname, ws, we in windows:
            if ws <= a < we and 0 < x <= 4 * 3600:
                g[(r, d, wname, day_type(date))].append(x / 60)
    def q(v, p):
        v = sorted(v); k = (len(v) - 1) * p; f = math.floor(k)
        return v[f] + (v[min(f + 1, len(v) - 1)] - v[f]) * (k - f)
    return [{"route": r, "direction": d, "window": w, "day_type": dt, "n": len(v),
             "p50_min": q(v, .5), "p90_min": q(v, .9)} for (r, d, w, dt), v in sorted(g.items())]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--gtfs", required=True, help="directory with trips.txt, routes.txt, calendar_dates.txt")
    p.add_argument("--out", required=True)
    p.add_argument("--windows", default=DEFAULT_WINDOWS)
    p.add_argument("--min-headway-s", type=float, default=60)
    p.add_argument("--max-gap-s", type=float, default=3 * 3600)
    p.add_argument("--min-day-share", type=float, default=0.5)
    a = p.parse_args(argv)
    windows = parse_windows(a.windows)
    dep, dur, bad = load_astana(a.gtfs)
    res = compute(dep, windows, a.min_headway_s, a.max_gap_s, a.min_day_share)
    res["counters"].update(bad)
    res["durations_include_layover"] = durations(dur, windows)
    dates = sorted({x[2] for x in dep})
    res["meta"] = {"city": "Astana", "routes": sorted({x[0] for x in dep}), "first_date": dates[0],
                   "last_date": dates[-1], "service_dates": len(dates), "trips": len(dep),
                   "source": "Mansurova et al., Zenodo 15769359 (doi:10.5281/zenodo.15769359), via GitHub mirror "
                             "Mrithula742/Bussure @ 0356bb5b37ef; license CC BY 4.0 per mirror README only",
                   "status": "derived from real historical observations (trip starts reconstructed from GPS)"}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "headways.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "summary.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(res["summary"][0]), lineterminator="\n")
        w.writeheader()
        w.writerows({k: round(v, 3) if isinstance(v, float) else v for k, v in x.items()} for x in res["summary"])
    print(json.dumps({"meta": res["meta"], "counters": res["counters"],
                      "excluded_days": len(res["excluded_days"])}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
