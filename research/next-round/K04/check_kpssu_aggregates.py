"""K04: offline consistency check of the KPSSU crash aggregates saved by A10 / AST-A10.

Recomputes the percentages quoted in A10_report.md and AST_A10_report.md from the
aggregate JSON files the agents saved. It does NOT contact gis.kgp.kz (blocked
from this environment) and therefore cannot confirm that the saved aggregates
match the live service; it only checks that the reports agree with their own
saved data and that totals add up across different group-bys.

Output: kpssu_consistency.json next to this file.
"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.abspath(os.path.join(HERE, "..", ".."))
SHY = os.path.join(R, "govtech-results/10_safety/A10_sample_kpssu_shymkent_aggregates.json")
AST = os.path.join(R, "astana-results/10_safety/AST_A10_sample_kpssu_astana_aggregates.json")


def by_year(rows, value_idx=-1, year_idx=0):
    out = collections.Counter()
    for r in rows:
        out[r[year_idx]] += r[value_idx] or 0
    return out


def check(name, claimed, computed, tol=0.15):
    ok = computed is not None and abs(claimed - computed) <= tol
    return {"check": name, "claimed": claimed, "computed": computed, "match": ok}


def shymkent():
    q = json.load(open(SHY, encoding="utf-8"))["queries"]
    res = []
    total = q["by_area_code_shymkent"]["result"]["1979"]
    res.append(check("sum district×year == area total 7064", total,
                     sum(r[2] for r in q["shymkent_by_district_year"]["rows"]), tol=0))
    res.append(check("sum year×type_dtp == 7064", total,
                     sum(r[2] for r in q["shymkent_by_year_type_dtp"]["rows"]), tol=0))
    res.append(check("sum crash_code×year == 7064", total,
                     sum(r[2] for r in q["shymkent_by_crash_type_code_year"]["rows"]), tol=0))
    allyr = by_year(q["shymkent_by_year_type_dtp"]["rows"])
    c05 = collections.Counter({r[1]: r[2] for r in q["shymkent_by_crash_type_code_year"]["rows"] if r[0] == "05"})
    claimed = {2021: 44.1, 2022: 46.3, 2023: 43.6, 2024: 48.8, 2025: 46.4, 2026: 46.1}
    for y, v in claimed.items():
        res.append(check(f"share code05 {y} %", v, round(100 * c05[y] / allyr[y], 1)))
    d_all = dict((r[0], r[1]) for r in q["shymkent_deaths_sum_by_year_all"]["rows"])
    d_05 = dict((r[0], r[1]) for r in q["shymkent_deaths_sum_by_year_code05"]["rows"])
    res.append(check("deaths code05 2025 share % (35/68)", 51.5, round(100 * d_05[2025] / d_all[2025], 1)))
    res.append(check("records 2024/2023 ratio ('в 2,4 раза')", 2.4, round(allyr[2024] / allyr[2023], 2), tol=0.05))
    light = q["code05_by_year_light_condition_fd1r07p2"]["rows"]
    dark25 = sum(r[2] for r in light if r[0] == 2025 and r[1] in ("сумерки", "ночь"))
    res.append(check("dark (сумерки+ночь) code05 2025 == 302", 302, dark25, tol=0))
    res.append(check("code05 by light condition 2025 sums to code05 2025", c05[2025],
                     sum(r[2] for r in light if r[0] == 2025), tol=0))
    res.append({"check": "104 of 302 dark code05 with lighting off/absent (2025)",
                "claimed": 104, "computed": None, "match": None,
                "note": "needs a light×outdoor-lighting cross-tab that is not in the saved file; unverifiable offline"})
    return res


def astana():
    q = json.load(open(AST, encoding="utf-8"))["queries"]
    res = []
    total = q["area_1971_total"]["count"]
    res.append(check("sum district×year == 12921", total,
                     sum(r[2] for r in q["astana_by_district_year"]["rows"]), tol=0))
    res.append(check("sum year×type_dtp == 12921", total,
                     sum(r[2] for r in q["astana_by_year_type_dtp"]["rows"]), tol=0))
    res.append(check("sum crash_code×year == 12921", total,
                     sum(r[2] for r in q["astana_by_crash_type_code_year"]["rows"]), tol=0))
    allyr = by_year(q["astana_by_year_type_dtp"]["rows"])
    c05 = collections.Counter({r[1]: r[2] for r in q["astana_by_crash_type_code_year"]["rows"] if r[0] == "05"})
    shares = {y: round(100 * c05[y] / allyr[y], 1) for y in range(2021, 2027)}
    res.append({"check": "share code05 2021-2026 within claimed 38-47 %", "claimed": [38, 47],
                "computed": shares, "match": all(37.5 <= v <= 47.5 for v in shares.values())})
    m = {(r[0], r[1]): r[2] for r in q["code05_by_year_month_2024_2026"]["rows"]}
    tot25 = sum(v for (y, _), v in m.items() if y == 2025)
    res.append(check("monthly code05 2025 sums to code05 2025", c05[2025], tot25, tol=0))
    res.append(check("Sep-Dec share of 2025 code05 % (41)", 41, round(100 * sum(m[(2025, k)] for k in (9, 10, 11, 12)) / tot25, 1), tol=0.6))
    surf = q["code05_road_surface_fd1r07p1_all_years"]["rows"]
    surf_total = sum(r[1] for r in surf)
    snowy = sum(r[1] for r in surf if r[0] and any(w in r[0] for w in ("обледен", "заснеж", "снежным накатом")))
    treated = sum(r[1] for r in surf if r[0] and "противогололед" in r[0])
    res.append({"check": "code05 on snow/ice % (17.4), all years — agent definition incl. de-iced surface",
                "claimed": 17.4, "computed": round(100 * (snowy + treated) / surf_total, 1),
                "match": abs(17.4 - 100 * (snowy + treated) / surf_total) <= 0.15,
                "note": "matches only if 'обработанная противогололедным материалом' is counted (report §2 says so; summary line says 'на снегу или льду')"})
    res.append({"check": "code05 on snow/ice % — strict (icy/snowy/packed snow only)", "claimed": None,
                "computed": round(100 * snowy / surf_total, 1), "match": None,
                "note": "K04 alternative definition; use this figure if 'snow or ice' is meant literally"})
    res.append(check("surface rows total == all-years code05", sum(c05.values()), surf_total, tol=0))
    return res


def main():
    out = {"note": "offline arithmetic consistency only; live service not reachable from this environment (403 proxy CONNECT, 2026-10-05)",
           "shymkent": shymkent(), "astana": astana()}
    with open(os.path.join(HERE, "kpssu_consistency.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    for city in ("shymkent", "astana"):
        for r in out[city]:
            print(f"{city:8} {str(r['match']):5} {r['check']}: claimed={r['claimed']} computed={r['computed']}")


if __name__ == "__main__":
    main()
