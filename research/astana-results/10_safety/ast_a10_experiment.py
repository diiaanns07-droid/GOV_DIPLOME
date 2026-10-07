"""AST-A10 isolated experiment (research only, not product code).

Part 1: consistency checks + derived indicators on observed KPSSU aggregates
        for Astana (AST-A10-D001) and the Shymkent sample (A10-D001 + supplement).
Part 2: shared priority-card engine v0.1 with per-city config; Shymkent
        regression check (v0 cases T01/T02 must keep scores 49.6/53.5) and
        10 Astana test situations. Weights/seasonal rules are UNCALIBRATED hypotheses.
"""
import json, random
from collections import defaultdict

A = json.load(open("AST_A10_sample_kpssu_astana_aggregates.json", encoding="utf-8"))["queries"]
S = json.load(open("A10_sample_kpssu_shymkent_aggregates.json", encoding="utf-8"))["queries"]
S2 = json.load(open("AST_A10_sample_shymkent_supplement.json", encoding="utf-8"))["queries"]

def by_year(rows, yi, ni):
    d = defaultdict(int)
    for r in rows:
        d[r[yi]] += r[ni]
    return dict(sorted(d.items()))

print("== Part 1a: Astana consistency (records per year from 3 groupings)")
d1 = by_year(A["astana_by_district_year"]["rows"], 1, 2)
d2 = by_year(A["astana_by_year_type_dtp"]["rows"], 0, 2)
d3 = by_year(A["astana_by_crash_type_code_year"]["rows"], 1, 2)
ok = all(d1[y] == d2[y] == d3[y] for y in d1) and set(d1) == set(d2) == set(d3)
for y in d1:
    print(f"{y}: district={d1[y]} type_dtp={d2[y]} code={d3[y]}")
print("ALL CONSISTENT:", ok, "| total:", sum(d1.values()), "(area_code 1971 count = 12921)")

ped_a = {r[1]: r[2] for r in A["astana_by_crash_type_code_year"]["rows"] if r[0] == "05"}
ped_s = {r[1]: r[2] for r in S["shymkent_by_crash_type_code_year"]["rows"] if r[0] == "05"}
tot_s = by_year(S["shymkent_by_crash_type_code_year"]["rows"], 1, 2)
da = dict(A["astana_deaths_sum_by_year_all"]["rows"]); da5 = dict(A["astana_deaths_sum_by_year_code05"]["rows"])
print("\n== Part 1b: code '05' share and deaths, Astana vs Shymkent")
for y in (2021, 2022, 2023, 2024, 2025, 2026):
    print(f"{y}: AST 05={ped_a[y]}/{d3[y]}={ped_a[y]/d3[y]:.1%} deaths05={da5[y]}/{da[y]}={da5[y]/da[y]:.1%} | "
          f"SHY 05={ped_s[y]}/{tot_s[y]}={ped_s[y]/tot_s[y]:.1%}")
print(f"Records growth 2024/2023: AST {d3[2024]/d3[2023]:.2f}x (deaths {da[2023]}->{da[2024]}); "
      f"SHY {tot_s[2024]/tot_s[2023]:.2f}x")

def dark_stats(light_rows, lamp_rows, years, ped):
    out = {}
    for y in years:
        day = sum(n for yy, c, n in light_rows if yy == y and c == "день")
        dark = sum(n for yy, c, n in light_rows if yy == y and c in ("сумерки", "ночь"))
        lamp_null = sum(n for yy, c, n in lamp_rows if yy == y and c is None)
        lamp_filled = sum(n for yy, c, n in lamp_rows if yy == y and c is not None)
        off = sum(n for yy, c, n in lamp_rows if yy == y and c in ("не включено", "отсутствует"))
        out[y] = dict(day=day, dark=dark, dark_share=dark/ped[y], lamp_null=lamp_null, lamp_filled=lamp_filled,
                      off=off, off_share=(off/dark if dark else None), null_equals_day=(lamp_null == day))
    return out

print("\n== Part 1c: dark-time and outdoor lighting (code 05)")
ast_dark = dark_stats(A["code05_by_year_light_condition_fd1r07p2"]["rows"], A["code05_by_year_outdoor_lighting_fd1r07p3"]["rows"], (2024, 2025, 2026), ped_a)
shy_dark = dark_stats(S["code05_by_year_light_condition_fd1r07p2"]["rows"], S["code05_by_year_outdoor_lighting_fd1r07p3"]["rows"], (2024, 2025, 2026), ped_s)
for y in (2024, 2025, 2026):
    a, s = ast_dark[y], shy_dark[y]
    print(f"{y}: AST dark={a['dark']} ({a['dark_share']:.1%}) off/absent={a['off']} ({a['off_share']:.1%}) null==day:{a['null_equals_day']} | "
          f"SHY dark={s['dark']} ({s['dark_share']:.1%}) off/absent={s['off']} ({s['off_share']:.1%}) null==day:{s['null_equals_day']}")
# null==day check over all Astana years
allyrs = sorted({r[0] for r in A["code05_by_year_light_condition_fd1r07p2"]["rows"]})
mism = [y for y in allyrs
        if sum(n for yy, c, n in A["code05_by_year_outdoor_lighting_fd1r07p3"]["rows"] if yy == y and c is None)
        != sum(n for yy, c, n in A["code05_by_year_light_condition_fd1r07p2"]["rows"] if yy == y and c in ("день", None))]
print("Astana years where lighting-null != (day + light-null):", mism)

print("\n== Part 1d: seasonality (code 05 by month)")
def months(rows, y):
    return [n for yy, m, n in sorted(rows) if yy == y]
for y in (2024, 2025):
    am = months(A["code05_by_year_month_2024_2026"]["rows"], y)
    sm = months(S2["code05_by_year_month_2024_2026"]["rows"], y)
    assert sum(am) == ped_a[y] and sum(sm) == ped_s[y], "month sums mismatch"
    a_sd, s_sd = sum(am[8:12]) / sum(am), sum(sm[8:12]) / sum(sm)
    print(f"{y}: AST Sep-Dec share={a_sd:.1%} max/min month={max(am)}/{min(am)}={max(am)/min(am):.2f} | "
          f"SHY Sep-Dec share={s_sd:.1%} max/min={max(sm)}/{min(sm)}={max(sm)/min(sm):.2f} | uniform=33.3%")
am24 = months(A["code05_by_year_month_2024_2026"]["rows"], 2024)
sm24 = months(S2["code05_by_year_month_2024_2026"]["rows"], 2024)
print(f"2024 regime check: AST mean Jan-Jul={sum(am24[:7])/7:.1f} vs Aug-Dec={sum(am24[7:])/5:.1f} (2023 monthly mean={ped_a[2023]/12:.1f}); "
      f"SHY mean Jan-Jul={sum(sm24[:7])/7:.1f} vs Aug-Dec={sum(sm24[7:])/5:.1f} (2023 monthly mean={ped_s[2023]/12:.1f})")
a26 = months(A["code05_by_year_month_2024_2026"]["rows"], 2026)
s26 = months(S2["code05_by_year_month_2024_2026"]["rows"], 2026)
print(f"2026 Aug/Sep: AST {a26[7]}/{a26[8]} vs 2025 Aug/Sep 66/93; SHY {s26[7]}/{s26[8]} -> load lag check")

print("\n== Part 1e: winter road surface and deficiency field (code 05, all years)")
WINTER = ("обледен", "заснеж", "снежн", "противогололед")
def surf(rows):
    tot = sum(n for _, n in rows)
    w = sum(n for k, n in rows if k and any(t in k for t in WINTER))
    return tot, w
ta, wa = surf(A["code05_road_surface_fd1r07p1_all_years"]["rows"])
ts, ws = surf(S2["code05_road_surface_fd1r07p1_all_years"]["rows"])
print(f"AST winter surface={wa}/{ta}={wa/ta:.1%}; SHY winter surface={ws}/{ts}={ws/ts:.1%}")
assert ta == sum(ped_a.values()), "Astana surface total != code05 total"
defs = A["code05_road_deficiencies_fd1r071p1_all_years"]["rows"]
dt = sum(n for _, n in defs)
NONINFRA = ("отсутствуют", "иные условия", "скользкое покрытие", None)
infra = sum(n for k, n in defs if k not in NONINFRA)
print(f"AST deficiency: total={dt}; 'отсутствуют'={dict((k,n) for k,n in defs)['отсутствуют']/dt:.1%}; "
      f"'иные условия'={dict((k,n) for k,n in defs)['иные условия']/dt:.1%}; 'скользкое покрытие' only={dict((k,n) for k,n in defs)['скользкое покрытие']/dt:.1%}; "
      f"infrastructure={infra} ({infra/dt:.1%})")

# ---------- Part 2: shared card engine v0.1 ----------
BASE_W = {"hist_per_eb_crash": 10, "hist_cap": 40, "fatal_bonus": 10, "school_300m": 15, "lanes_ge4": 10,
          "speed_ge60": 10, "light_off": 10, "light_unknown": 5, "bus_stop_50m": 5}
CITY = {
    "shymkent": {"k": 0.5, "seasonal": False, "history_window": (2024, 2026), "dark_months": None},
    "astana": {"k": 0.5, "seasonal": True, "history_window": (2024, 2026), "dark_months": (9, 10, 11, 12, 1, 2),
               "winter_points": 5, "max_lag_days_ok": 30},
}
REQUIRED = ["school_300m", "lanes", "speed_limit", "lighting", "bus_stop_50m"]

def card(c, city, w=BASE_W):
    cfg = CITY[city]
    out = {"id": c["id"], "status": None, "score": None, "band": None, "components": {}, "flags": [], "next_step": None}
    if c.get("emergency"):
        out.update(status="REFUSE_EMERGENCY", next_step="Не очередь обследования: сообщить в 112/109 по регламенту города; после события — отдельная задача осмотра.")
        return out
    if c.get("question") == "route_safe":
        out.update(status="REFUSE_GUARANTEE", next_step="Сайт не подтверждает безопасность маршрута; показать известные проблемы и пробелы данных.")
        return out
    if c.get("coord") is None or c.get("match_dist_m", 0) > 25:
        out.update(status="REFUSE_LOCATION", next_step="Ручная привязка: координат нет или расхождение источников > 25 м.")
        return out
    quality = sum(1 for f in REQUIRED if c.get(f) is not None) / len(REQUIRED)
    out["components"]["data_quality"] = round(quality, 2)
    hist = None
    if c.get("crash_coverage") is False:
        out["flags"].append("Нет покрытия данных ДТП за окно: история = неизвестно (не ноль).")
    else:
        obs, mu = c.get("ped_crashes_obs", 0), c.get("stratum_mean", 0.6)
        wt = 1 / (1 + cfg["k"] * mu)
        eb = wt * mu + (1 - wt) * obs
        hist = min(w["hist_cap"], w["hist_per_eb_crash"] * eb) + (w["fatal_bonus"] if c.get("fatal_obs", 0) > 0 else 0)
        out["components"]["history"] = {"obs": obs, "stratum_mean": mu, "eb": round(eb, 2), "points": round(hist, 1)}
        if obs == 0:
            out["flags"].append("0 зарегистрированных ДТП не означает безопасность.")
    if c.get("data_lag_days") and cfg.get("max_lag_days_ok") and c["data_lag_days"] > cfg["max_lag_days_ok"]:
        out["flags"].append(f"Свежие месяцы загружены не полностью (лаг {c['data_lag_days']} дн.): не считать их 'спокойными'.")
    sysp = 0
    sysp += w["school_300m"] if c.get("school_300m") else 0
    sysp += w["lanes_ge4"] if (c.get("lanes") or 0) >= 4 else 0
    sysp += w["speed_ge60"] if (c.get("speed_limit") or 0) >= 60 else 0
    if c.get("lighting") in ("off", "absent"):
        sysp += w["light_off"]
    elif c.get("lighting") is None:
        sysp += w["light_unknown"]; out["flags"].append("Освещение неизвестно: нужен ночной осмотр.")
    sysp += w["bus_stop_50m"] if c.get("bus_stop_50m") else 0
    if cfg["seasonal"]:
        if c.get("winter_surface_crashes", 0) > 0:
            sysp += cfg["winter_points"]
            out["flags"].append("ДТП на снегу/льду: проверить зимнее содержание подходов и видимость (снежные валы).")
        if c.get("dark_season_crashes", 0) > 0 and c.get("lighting") != "on":
            out["flags"].append("ДТП в тёмный сезон (сен–фев) без подтверждённого освещения: ночной осмотр в приоритете.")
    out["components"]["systemic_points"] = sysp
    out["flags"] += c.get("extra_flags", [])
    if quality < 0.5:
        out.update(status="INSUFFICIENT_DATA", next_step="Очередь первичного осмотра (не 'низкий приоритет').")
        return out
    score = (hist or 0) + sysp
    out.update(score=round(score, 1), band=("высокий" if score >= 50 else "средний" if score >= 30 else "низкий"),
               status=("RANKED" if hist is not None else "RANKED_SYSTEMIC_ONLY"),
               next_step="Выезд специалиста (день + ночь в тёмный сезон); отметить подтверждено/не подтверждено.")
    return out

print("\n== Part 2a: Shymkent regression (shared engine must reproduce v0)")
shy_t01 = dict(id="T01", coord=(0, 0), ped_crashes_obs=0, stratum_mean=0.6, school_300m=True, lanes=4, speed_limit=60, lighting=None, bus_stop_50m=True)
shy_t02 = dict(id="T02", coord=(0, 0), ped_crashes_obs=6, fatal_obs=1, stratum_mean=0.6, school_300m=False, lanes=4, speed_limit=60, lighting="on", bus_stop_50m=True)
r1, r2 = card(shy_t01, "shymkent"), card(shy_t02, "shymkent")
print(f"T01 {r1['score']} (v0 49.6), T02 {r2['score']} (v0 53.5) -> regression OK: {r1['score']==49.6 and r2['score']==53.5}")

print("\n== Part 2b: Astana test situations")
cases = [
  dict(id="AT01", origin="observed-derived (AST-A10-F007: осенний пик 05)", coord=(51.13, 71.41), ped_crashes_obs=3, stratum_mean=0.6, dark_season_crashes=3,
       school_300m=False, lanes=4, speed_limit=60, lighting=None, bus_stop_50m=True),
  dict(id="AT02", origin="observed-derived (AST-A10-F009: ДТП на льду/снегу)", coord=(51.16, 71.45), ped_crashes_obs=2, stratum_mean=0.6, winter_surface_crashes=2,
       school_300m=True, lanes=2, speed_limit=40, lighting="on", bus_stop_50m=False),
  dict(id="AT03", origin="observed-derived (AST-A10-F004: код района 197124 с 2025)", coord=(51.09, 71.50), crash_coverage=False,
       school_300m=True, lanes=4, speed_limit=60, lighting="on", bus_stop_50m=True,
       extra_flags=["Новый район (Сарайшык) и уточнение границ 2026: окно истории короткое, районная привязка — по геометрии, не по коду."]),
  dict(id="AT04", origin="observed-derived (AST-A10-F008: лаг загрузки сентября 2026)", coord=(51.12, 71.43), ped_crashes_obs=1, stratum_mean=0.6, data_lag_days=45,
       school_300m=False, lanes=4, speed_limit=60, lighting="on", bus_stop_50m=True),
  dict(id="AT05", origin="observed (AST-A10-F012/F013: Уркер, нет регулируемых переходов; новые школы)", coord=(51.07, 71.38), ped_crashes_obs=0, stratum_mean=0.6,
       school_300m=True, lanes=4, speed_limit=60, lighting=None, bus_stop_50m=None,
       extra_flags=["Высокий прирост населения/школ: история ДТП отстаёт от экспозиции."]),
  dict(id="AT06", origin="observed (AST-A10-F015: Сарыарка — 17 неосвещённых улиц из 330)", coord=(51.18, 71.40), ped_crashes_obs=1, stratum_mean=0.6,
       school_300m=False, lanes=2, speed_limit=40, lighting="off", bus_stop_50m=True,
       extra_flags=["Статус освещения взят на уровне улицы; привязку к переходу проверить."]),
  dict(id="AT07", origin="observed (AST-A10-F017: ливень 23.07.2026)", emergency=True),
  dict(id="AT08", origin="synthetic", coord=(51.10, 71.42), ped_crashes_obs=0, stratum_mean=0.6, school_300m=True, lanes=6, speed_limit=60, lighting="on", bus_stop_50m=True),
  dict(id="AT09", origin="synthetic", coord=(51.15, 71.44), match_dist_m=80),
  dict(id="AT10", origin="synthetic", question="route_safe"),
]
res = [card(c, "astana") for c in cases]
for c, r in zip(cases, res):
    print(json.dumps({"origin": c["origin"], **r}, ensure_ascii=False))

random.seed(42)
ranked = [c for c, r in zip(cases, res) if r["status"] and r["status"].startswith("RANKED")]
base = [r["id"] for r in sorted([card(c, "astana") for c in ranked], key=lambda r: -r["score"])]
stable = stable3 = 0
for _ in range(200):
    w2 = {k: v * random.uniform(0.5, 1.5) for k, v in BASE_W.items()}
    order = [r["id"] for r in sorted([card(c, "astana", w2) for c in ranked], key=lambda r: -r["score"])]
    stable += order[0] == base[0]
    stable3 += set(order[:3]) == set(base[:3])
scores = {r["id"]: r["score"] for r in res if r["score"] is not None}
print(f"\nSensitivity (Astana): base order {base}; scores {scores}")
print(f"top-1 unchanged in {stable}/200; top-3 set unchanged in {stable3}/200 perturbations (+-50%). "
      f"Note: AT05 and AT08 tie at base weights -> top-1 is not meaningful; tie-break rule needed.")
