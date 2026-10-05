"""A10 isolated experiment (research only, not product code).

Part 1: consistency checks and derived shares on observed KPSSU aggregates (A10-D001).
Part 2: reference implementation of the crossing priority card + refusal rules,
        run on 10 test situations (synthetic inputs; origin noted per case).
Weights are UNCALIBRATED hypotheses; they exist to make the contract testable.
"""
import json, math, random, sys
from collections import defaultdict

agg = json.load(open("A10_sample_kpssu_shymkent_aggregates.json", encoding="utf-8"))["queries"]

# ---------- Part 1 ----------
def sum_by_year(rows, year_idx, n_idx):
    d = defaultdict(int)
    for r in rows:
        d[r[year_idx]] += r[n_idx]
    return dict(sorted(d.items()))

by_dist = sum_by_year(agg["shymkent_by_district_year"]["rows"], 1, 2)
by_type = sum_by_year(agg["shymkent_by_year_type_dtp"]["rows"], 0, 2)
by_code = sum_by_year(agg["shymkent_by_crash_type_code_year"]["rows"], 1, 2)
ped = {r[1]: r[2] for r in agg["shymkent_by_crash_type_code_year"]["rows"] if r[0] == "05"}
deaths_all = dict(agg["shymkent_deaths_sum_by_year_all"]["rows"])
deaths_05 = dict(agg["shymkent_deaths_sum_by_year_code05"]["rows"])

print("== Part 1: consistency of three independent groupings (records per year)")
ok = True
for y in by_dist:
    same = by_dist[y] == by_type[y] == by_code[y]
    ok &= same
    print(f"{y}: district={by_dist[y]} type_dtp={by_type[y]} code={by_code[y]} consistent={same}")
print("total 2018-2026:", sum(by_dist.values()), "(area_code 1979 count = 7064)")
print("ALL CONSISTENT:", ok)

print("\n== Derived: share of code '05' among all records, deaths in code-05 crashes")
for y in sorted(ped):
    print(f"{y}: code05={ped[y]}/{by_code[y]} = {ped[y]/by_code[y]:.1%}; "
          f"deaths code05={deaths_05[y]}/{deaths_all[y]} = {deaths_05[y]/deaths_all[y]:.1%}")

light = agg["code05_by_year_light_condition_fd1r07p2"]["rows"]
lamp = agg["code05_by_year_outdoor_lighting_fd1r07p3"]["rows"]
for y in (2024, 2025, 2026):
    dark = sum(n for yy, c, n in light if yy == y and c in ("сумерки", "ночь"))
    off = sum(n for yy, c, n in lamp if yy == y and c in ("не включено", "отсутствует"))
    on = sum(n for yy, c, n in lamp if yy == y and c == "включено")
    print(f"{y}: code05 in twilight/night={dark} ({dark/ped[y]:.1%}); lighting on={on}, off/absent={off} "
          f"-> off/absent share of dark-time = {off/dark:.1%}")

defs = dict((k if k else "null", v) for k, v in agg["code05_road_deficiencies_fd1r071p1_all_years"]["rows"])
tot = sum(defs.values())
infra = sum(v for k, v in defs.items() if k not in ("отсутствуют", "иные условия", "null", "скользкое покрытие"))
print(f"\nDeficiency field, code05 all years: total={tot}; 'отсутствуют'={defs['отсутствуют']} "
      f"({defs['отсутствуют']/tot:.1%}); infrastructure deficiencies (lighting, sidewalks, markings, signs, surface defects, ped paths)={infra} ({infra/tot:.1%})")
lamp_off_all = sum(n for yy, c, n in lamp if c in ("не включено", "отсутствует"))
print(f"Contrast: records with outdoor lighting 'не включено'/'отсутствует' (all years) = {lamp_off_all}; "
      f"'недостаточное освещение' in deficiency field = {defs['недостаточное освещение проезжей части']}")
print(f"2022 code05 share {ped[2022]/by_code[2022]:.1%} vs minister's 47% (Oct 2022)")

# ---------- Part 2: priority card ----------
W = {  # hypothesis weights (points)
    "hist_per_eb_crash": 10, "hist_cap": 40, "fatal_bonus": 10,
    "school_300m": 15, "lanes_ge4": 10, "speed_ge60": 10,
    "light_off": 10, "light_unknown": 5, "bus_stop_50m": 5,
}
K_OVERDISP = 0.5  # hypothesis; HSM-style EB weight w = 1/(1+k*mu)
REQUIRED = ["school_300m", "lanes", "speed_limit", "lighting", "bus_stop_50m"]

def card(c, w=W, k=K_OVERDISP):
    out = {"id": c["id"], "status": None, "score": None, "band": None, "components": {}, "flags": [], "next_step": None}
    if c.get("emergency"):
        out.update(status="REFUSE_EMERGENCY", next_step="Не очередь обследования: немедленно сообщить в 112/109 по регламенту города.")
        return out
    if c.get("question") == "route_safe":
        out.update(status="REFUSE_GUARANTEE",
                   next_step="Сайт не подтверждает безопасность маршрута; показать известные проблемы и пробелы данных на маршруте.")
        return out
    if c.get("coord") is None or c.get("match_dist_m", 0) > 25:
        out.update(status="REFUSE_LOCATION",
                   next_step="Ручное сопоставление объекта: координаты отсутствуют или расхождение источников > 25 м.")
        return out
    known = sum(1 for f in REQUIRED if c.get(f) is not None)
    quality = known / len(REQUIRED)
    out["components"]["data_quality"] = round(quality, 2)
    # history (registered crashes only; null if crash data does not cover the period/area)
    if c.get("crash_coverage") is False:
        out["flags"].append("Нет покрытия данных ДТП за период: история = неизвестно (не ноль).")
        hist = None
    else:
        obs, mu = c.get("ped_crashes_obs", 0), c.get("stratum_mean", 0.5)
        wgt = 1 / (1 + k * mu)
        eb = wgt * mu + (1 - wgt) * obs
        hist = min(w["hist_cap"], w["hist_per_eb_crash"] * eb) + (w["fatal_bonus"] if c.get("fatal_obs", 0) > 0 else 0)
        out["components"]["history"] = {"obs": obs, "stratum_mean": mu, "eb": round(eb, 2), "points": round(hist, 1)}
        if obs == 0:
            out["flags"].append("0 зарегистрированных ДТП не означает безопасность (неполная регистрация, низкая экспозиция).")
    sysp = 0
    sysp += w["school_300m"] if c.get("school_300m") else 0
    sysp += w["lanes_ge4"] if (c.get("lanes") or 0) >= 4 else 0
    sysp += w["speed_ge60"] if (c.get("speed_limit") or 0) >= 60 else 0
    if c.get("lighting") in ("off", "absent"):
        sysp += w["light_off"]
    elif c.get("lighting") is None:
        sysp += w["light_unknown"]; out["flags"].append("Освещение неизвестно: требуется ночной осмотр.")
    sysp += w["bus_stop_50m"] if c.get("bus_stop_50m") else 0
    out["components"]["systemic_points"] = sysp
    for f in c.get("extra_flags", []):
        out["flags"].append(f)
    if quality < 0.5:
        out.update(status="INSUFFICIENT_DATA", next_step="Поставить в очередь первичного осмотра (не в 'низкий приоритет').")
        return out
    score = (hist or 0) + sysp
    out["score"] = round(score, 1)
    out["band"] = "высокий" if score >= 50 else "средний" if score >= 30 else "низкий"
    out["status"] = "RANKED" if hist is not None else "RANKED_SYSTEMIC_ONLY"
    out["next_step"] = "Выездная проверка специалистом; результат осмотра вносится в карточку (подтверждено/не подтверждено)."
    return out

cases = [
  dict(id="T01", origin="synthetic", coord=(42.30, 69.60), ped_crashes_obs=0, stratum_mean=0.6, school_300m=True, lanes=4, speed_limit=60, lighting=None, bus_stop_50m=True),
  dict(id="T02", origin="synthetic (поля как в слое КПСиСУ)", coord=(42.31, 69.62), ped_crashes_obs=6, fatal_obs=1, stratum_mean=0.6, school_300m=False, lanes=4, speed_limit=60, lighting="on", bus_stop_50m=True),
  dict(id="T03", origin="observed-derived (код района 197914 есть только с 2023)", coord=(42.35, 69.55), crash_coverage=False, school_300m=True, lanes=2, speed_limit=40, lighting="on", bus_stop_50m=False,
       extra_flags=["Район с изменёнными границами: окно истории только с 2023."]),
  dict(id="T04", origin="observed-derived (fd1r07p3=null у дневных ДТП)", coord=(42.32, 69.59), ped_crashes_obs=3, stratum_mean=0.6, school_300m=False, lanes=2, speed_limit=40, lighting=None, bus_stop_50m=False,
       extra_flags=["null в поле 'Наружное освещение' у дневных ДТП не означает 'освещено'."]),
  dict(id="T05", origin="observed-derived (ночные ДТП с 'не включено')", coord=(42.29, 69.64), ped_crashes_obs=2, stratum_mean=0.6, school_300m=False, lanes=4, speed_limit=50, lighting="off", bus_stop_50m=True,
       extra_flags=["Ночные ДТП при выключенном освещении: проверить работу линии/диспетчеризацию (оператор освещения)."]),
  dict(id="T06", origin="synthetic (контекст: случай ул. Ушкыштар, янв. 2026)", coord=(42.33, 69.61), ped_crashes_obs=1, stratum_mean=0.6, school_300m=True, lanes=2, speed_limit=40, lighting="on", bus_stop_50m=False,
       extra_flags=["Акимат: освещено; жалоба: не горит -> противоречие источников, нужна ночная проверка."]),
  dict(id="T07", origin="observed (школа №13, Забадам, дек. 2025)", coord=(42.36, 69.66), ped_crashes_obs=0, stratum_mean=0.4, school_300m=True, lanes=None, speed_limit=None, lighting=None, bus_stop_50m=None,
       extra_flags=["Временное перекрытие пешеходного пути стройкой: проверить обход и ВОДД."]),
  dict(id="T08", origin="observed (подтопление Елтай, июль 2026)", emergency=True),
  dict(id="T09", origin="synthetic", coord=(42.31, 69.58), match_dist_m=120),
  dict(id="T10", origin="synthetic", question="route_safe"),
]
print("\n== Part 2: priority cards (weights are hypotheses)")
results = [card(c) for c in cases]
for c, r in zip(cases, results):
    print(json.dumps({"origin": c["origin"], **r}, ensure_ascii=False))

# sensitivity: perturb weights +-50% on ranked cases, check band stability
random.seed(42)
ranked = [c for c, r in zip(cases, results) if r["status"] and r["status"].startswith("RANKED")]
base_order = [r["id"] for r in sorted([card(c) for c in ranked], key=lambda r: -r["score"])]
stable = 0
for _ in range(200):
    w2 = {kk: v * random.uniform(0.5, 1.5) for kk, v in W.items()}
    order = [r["id"] for r in sorted([card(c, w2) for c in ranked], key=lambda r: -r["score"])]
    stable += order[0] == base_order[0]
print(f"\nSensitivity: base order {base_order}; top-1 unchanged in {stable}/200 random weight perturbations (+-50%).")
