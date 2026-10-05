#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AST-A03-E003 — вывоз снега: распределение участков погрузки по снежным полигонам
и снегоплавильным пунктам с учётом их приёмной мощности за смену.

ДАННЫЕ СМЕШАННЫЕ (kind = mixed):
  * РЕАЛЬНЫЕ: полигоны шести районов Астаны из OpenStreetMap (кэш Overpass в репозитории
    STUPITS, osm_base 2026-09-22, © OpenStreetMap contributors, ODbL). Используются только
    как рамка, внутри которой разбрасываются синтетические точки, и для подписи района.
  * СИНТЕТИЧЕСКИЕ: участки погрузки, объёмы снега, полигоны/пункты приёма снега, их мощности,
    депо, парк, скорости, время погрузки и разгрузки, длительность смены.
Это НЕ реальные объёмы снега, НЕ реальные места складирования и НЕ маршруты города.

Проверяемое критическое предположение (H5):
  Оптимизатор распределения (min-cost flow) даёт пользу по сравнению с правилом
  «везти на ближайший полигон» только тогда, когда приёмная мощность полигонов
  ограничивает; при большом запасе мощности «ближайший» уже оптимален, и сложный
  модуль не нужен. Если так — первое, что нужно узнать у города, это мощности и
  места приёма снега, а не «AI».

Запуск: python3 AST_A03_snow_experiment.py   (пишет ./out/*)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
from importlib.metadata import version as pkg_version

import numpy as np
from ortools.graph.python import min_cost_flow

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
DISTRICTS = os.path.join(HERE, "AST_A03_input_astana_districts_osm.geojson")  # реальный OSM (ODbL), копия data/astana_districts.geojson из STUPITS 834a25f

SEED = 20261005
N_SITES = 30
TRUCK_M3 = 20            # кузов самосвала, м³ рыхлого снега (допущение)
LOAD_MIN = 6             # погрузка одного кузова фронтальным погрузчиком, мин (допущение)
SHIFT_MIN = 8 * 60       # ночная смена 23:00–07:00 (допущение)
N_TRUCKS = 60            # парк на смену в основной сетке: с запасом, чтобы смена не ограничивала (допущение)
DETOUR = 1.30            # коэффициент извилистости (допущение)
UNSERVED_COST = 10 ** 7  # штраф за 1 м³ невывезенного снега в потоке (сек-эквивалент)

# Синтетические приёмные пункты (координаты придуманы на окраинах рамки; НЕ реальные места)
DUMPS_TEMPLATE = [
    dict(id="SYN-DUMP-N", lon=71.43, lat=51.27, kind="snow_dump", unload_min=4, share=0.40),
    dict(id="SYN-DUMP-SE", lon=71.62, lat=51.05, kind="snow_dump", unload_min=4, share=0.35),
    dict(id="SYN-MELT-C", lon=71.45, lat=51.15, kind="melting_point", unload_min=8, share=0.25),
]
DEPOT = dict(id="SYN-DEPOT", lon=71.36, lat=51.16)


# ------------------------------------------------------------------ геометрия
def haversine_km(lon1, lat1, lon2, lat2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xin:
                inside = not inside
    return inside


def _in_polygon(x, y, rings):
    return _in_ring(x, y, rings[0]) and not any(_in_ring(x, y, h) for h in rings[1:])


def point_district(x, y, feats):
    for f in feats:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        if any(_in_polygon(x, y, p) for p in polys):
            return f["properties"]["id"]
    return None


# ------------------------------------------------------------------ экземпляр
def make_instance(seed=SEED, cap_ratio=1.15, n_sites=N_SITES):
    gj = json.load(open(DISTRICTS, encoding="utf-8"))
    feats = gj["features"]
    xs, ys = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for k in c:
                walk(k)
    for f in feats:
        walk(f["geometry"]["coordinates"])
    rng = np.random.default_rng(seed)
    sites = []
    while len(sites) < n_sites:
        x, y = rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys))
        d = point_district(x, y, feats)
        if d is None:
            continue
        vol = int(rng.choice([40, 60, 80, 120, 160, 240], p=[0.2, 0.25, 0.2, 0.15, 0.12, 0.08]))
        sites.append(dict(id=f"SYN-S{len(sites) + 1:02d}", lon=round(float(x), 5), lat=round(float(y), 5),
                          district_osm=d, volume_m3=vol))
    total = sum(s["volume_m3"] for s in sites)
    dumps = []
    for t in DUMPS_TEMPLATE:
        dd = dict(t)
        dd["cap_m3"] = int(round(total * cap_ratio * t["share"]))
        dd.pop("share")
        dumps.append(dd)
    return sites, dumps, total


def travel_min(a, b, speed_kmh):
    return haversine_km(a["lon"], a["lat"], b["lon"], b["lat"]) * DETOUR / speed_kmh * 60


def km(a, b):
    return haversine_km(a["lon"], a["lat"], b["lon"], b["lat"]) * DETOUR


# ------------------------------------------------------------------ правила распределения
def assign_nearest(sites, dumps, speed):
    """B-N: каждый участок — на ближайший пункт, мощность игнорируется (диспетчерское правило)."""
    flows = {}
    for i, s in enumerate(sites):
        j = min(range(len(dumps)), key=lambda j: travel_min(s, dumps[j], speed))
        flows[(i, j)] = s["volume_m3"]
    return flows


def assign_greedy_cap(sites, dumps, speed):
    """B-G: участки по убыванию объёма; везём на ближайший пункт с остатком мощности,
    при заполнении — на следующий ближайший (сильный простой baseline)."""
    left = [d["cap_m3"] for d in dumps]
    flows = {}
    for i in sorted(range(len(sites)), key=lambda i: -sites[i]["volume_m3"]):
        need = sites[i]["volume_m3"]
        for j in sorted(range(len(dumps)), key=lambda j: travel_min(sites[i], dumps[j], speed)):
            if need <= 0:
                break
            take = min(need, left[j])
            if take > 0:
                flows[(i, j)] = flows.get((i, j), 0) + take
                left[j] -= take
                need -= take
    return flows


def assign_mcf(sites, dumps, speed):
    """OPT: min Σ x_sd · (время рейса туда-обратно на 1 м³), Σ_d x_sd + u_s = V_s, Σ_s x_sd ≤ cap_d.
    u_s — невывезенный объём со штрафом (всегда допустимо). Решение точное (целые м³)."""
    mcf = min_cost_flow.SimpleMinCostFlow()
    S, D = len(sites), len(dumps)
    src, sink, unserved = S + D, S + D + 1, S + D + 2
    for i, s in enumerate(sites):
        mcf.add_arc_with_capacity_and_unit_cost(src, i, s["volume_m3"], 0)
        for j, d in enumerate(dumps):
            cyc_s = int(round((2 * travel_min(s, d, speed) + LOAD_MIN + d["unload_min"]) * 60 / TRUCK_M3))
            mcf.add_arc_with_capacity_and_unit_cost(i, S + j, s["volume_m3"], cyc_s)
        mcf.add_arc_with_capacity_and_unit_cost(i, unserved, s["volume_m3"], UNSERVED_COST)
    for j, d in enumerate(dumps):
        mcf.add_arc_with_capacity_and_unit_cost(S + j, sink, d["cap_m3"], 0)
    total = sum(s["volume_m3"] for s in sites)
    mcf.add_arc_with_capacity_and_unit_cost(unserved, sink, total, 0)
    mcf.set_node_supply(src, total)
    mcf.set_node_supply(sink, -total)
    status = mcf.solve()
    assert status == mcf.OPTIMAL, status
    flows = {}
    for a in range(mcf.num_arcs()):
        t, h, f = mcf.tail(a), mcf.head(a), mcf.flow(a)
        if f > 0 and t < S and S <= h < S + D:
            flows[(t, h - S)] = f
    return flows


# ------------------------------------------------------------------ единый оценщик
def evaluate(flows, sites, dumps, speed, n_trucks=N_TRUCKS):
    """Пункт принимает не больше cap_m3; излишек невывезен. Рейсы = ceil(объём / кузов).
    Рейсы раскладываются по машинам: короткие циклы первыми, каждому — наименее загруженная машина;
    что не влезает в смену с возвратом в депо — невывезено.
    Холостой пробег депо→первый участок и последний пункт→депо учитывается."""
    accepted_at = [0] * len(dumps)
    trips = []  # (cycle_min, site, dump, m3)
    overflow = 0
    for (i, j), v in sorted(flows.items()):
        room = max(0, dumps[j]["cap_m3"] - accepted_at[j])
        take = min(v, room)
        overflow += v - take
        accepted_at[j] += take
        n = math.ceil(take / TRUCK_M3)
        cyc = 2 * travel_min(sites[i], dumps[j], speed) + LOAD_MIN + dumps[j]["unload_min"]
        for k in range(n):
            m3 = TRUCK_M3 if k < n - 1 else take - TRUCK_M3 * (n - 1)
            trips.append((cyc, i, j, m3))
    load = [0.0] * n_trucks
    tk = [[] for _ in range(n_trucks)]
    unfit_m3 = 0
    # Порядок одинаков для всех методов: сначала короткие циклы (больше рейсов в смену), равные — по участку
    for cyc, i, j, m3 in sorted(trips, key=lambda t: (t[0], t[1], t[2])):
        k = min(range(n_trucks), key=lambda k: load[k])
        first = not tk[k]
        extra = travel_min(DEPOT, sites[i], speed) if first else 0
        back = travel_min(dumps[j], DEPOT, speed)
        # load[k] не включает возврат в депо; проверяем смену с возвратом после этого рейса.
        # Допущение v0: цикл рейса = погрузка + туда-обратно до пункта + разгрузка (возврат на тот же участок).
        if load[k] + extra + cyc + back <= SHIFT_MIN:
            load[k] += extra + cyc
            tk[k].append((cyc, i, j, m3))
        else:
            unfit_m3 += m3
    truck_km, used = 0.0, 0
    durations = []
    for k in range(n_trucks):
        if not tk[k]:
            continue
        used += 1
        first_site = tk[k][0][1]
        last_dump = tk[k][-1][2]
        d_km = km(DEPOT, sites[first_site]) + sum(2 * km(sites[i], dumps[j]) for _, i, j, _ in tk[k]) + km(dumps[last_dump], DEPOT)
        truck_km += d_km
        durations.append(load[k] + travel_min(dumps[last_dump], DEPOT, speed))
    total = sum(s["volume_m3"] for s in sites)
    served = sum(t[3] for k in range(n_trucks) for t in tk[k])
    util = [accepted_at[j] / dumps[j]["cap_m3"] for j in range(len(dumps))]
    flow_to = [sum(v for (i, j), v in flows.items() if j == jj) for jj in range(len(dumps))]
    durs = np.array(durations) if durations else np.array([0.0])
    return dict(
        total_volume_m3=total,
        served_m3=int(served),
        unserved_m3=int(total - served),
        unserved_due_to_dump_overflow_m3=int(overflow),
        unserved_due_to_shift_m3=int(unfit_m3),
        dump_demand_over_capacity=[round(flow_to[j] / dumps[j]["cap_m3"], 3) for j in range(len(dumps))],
        dump_utilization=[round(u, 3) for u in util],
        trips=len(trips),
        truck_km=round(float(truck_km), 1),
        truck_km_per_served_m3=round(float(truck_km) / served, 3) if served else None,
        truck_hours_per_1000_m3=round(float(durs.sum()) / 60 / served * 1000, 1) if served else None,
        truck_hours=round(float(durs.sum()) / 60, 1),
        makespan_h=round(float(durs.max()) / 60, 2),
        trucks_used=used,
        balance_cv=round(float(durs.std() / durs.mean()), 3) if durs.mean() > 0 else None,
    )


METHODS = dict(nearest=assign_nearest, greedy_cap=assign_greedy_cap, min_cost_flow=assign_mcf)


def run_case(seed, cap_ratio, speed, n_trucks=N_TRUCKS):
    sites, dumps, total = make_instance(seed, cap_ratio)
    out = {}
    for name, fn in METHODS.items():
        fl = fn(sites, dumps, speed)
        out[name] = evaluate(fl, sites, dumps, speed, n_trucks)
    return sites, dumps, out


def main():
    env = dict(python=sys.version.split()[0], platform=platform.platform(), ortools=pkg_version("ortools"),
               numpy=np.__version__, seed=SEED,
               districts_sha256=hashlib.sha256(open(DISTRICTS, "rb").read()).hexdigest())
    res = dict(meta=dict(kind="mixed", experiment="AST-A03-E003", env=env,
                         real_inputs="OSM district polygons of Astana (STUPITS cache, osm_base 2026-09-22, ODbL)",
                         synthetic_inputs="sites, volumes, dumps, capacities, depot, fleet, speeds, times",
                         assumptions=dict(truck_m3=TRUCK_M3, load_min=LOAD_MIN, shift_min=SHIFT_MIN,
                                          n_trucks=N_TRUCKS, detour=DETOUR)),
               grid=[], speed_sensitivity=[], fleet_sensitivity=[])

    # Основная сетка: 5 экземпляров × 5 уровней запаса мощности, скорость 20 км/ч, парк 60
    for k in range(5):
        for cap_ratio in (5.0, 2.0, 1.3, 1.1, 1.0):
            _, _, out = run_case(SEED + k, cap_ratio, 20.0)
            res["grid"].append(dict(seed=SEED + k, cap_ratio=cap_ratio, speed_kmh=20.0, results=out))
    # Чувствительность к скорости (зимняя ночь: 15/20/30 км/ч) при cap_ratio 1.1
    for speed in (15.0, 20.0, 30.0):
        _, _, out = run_case(SEED, 1.1, speed)
        res["speed_sensitivity"].append(dict(seed=SEED, cap_ratio=1.1, speed_kmh=speed, results=out))
    # Чувствительность к парку (20/30/40/60 машин) при cap_ratio 1.1, 20 км/ч
    for nt in (20, 30, 40, 60):
        _, _, out = run_case(SEED, 1.1, 20.0, nt)
        res["fleet_sensitivity"].append(dict(seed=SEED, cap_ratio=1.1, speed_kmh=20.0, n_trucks=nt, results=out))

    with open(os.path.join(OUT, "AST_A03_E003_results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    # GeoJSON экземпляра seed=SEED, cap_ratio=1.1 (точки — synthetic; район — из реального OSM)
    sites, dumps, _ = make_instance(SEED, 1.1)
    feats = [dict(type="Feature", geometry=dict(type="Point", coordinates=[s["lon"], s["lat"]]),
                  properties=dict(kind="synthetic", role="snow_loading_site", district_from_real_osm_polygon=s["district_osm"],
                                  **{k: v for k, v in s.items() if k not in ("lon", "lat", "district_osm")})) for s in sites]
    feats += [dict(type="Feature", geometry=dict(type="Point", coordinates=[d["lon"], d["lat"]]),
                   properties=dict(kind="synthetic", role=d["kind"], **{k: v for k, v in d.items() if k not in ("lon", "lat", "kind")})) for d in dumps]
    feats.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[DEPOT["lon"], DEPOT["lat"]]),
                      properties=dict(kind="synthetic", role="depot", id=DEPOT["id"])))
    with open(os.path.join(OUT, "AST_A03_synthetic_snow_instance.geojson"), "w", encoding="utf-8") as f:
        json.dump(dict(type="FeatureCollection", name="AST-A03 synthetic snow instance (NOT real data)",
                       note="Points synthetic; district labels from real OSM polygons (ODbL)", features=feats),
                  f, ensure_ascii=False, indent=1)

    # Сводка
    print(json.dumps(env, ensure_ascii=False))
    print("cap_ratio\tmethod\tunserved_m3\toverflow_m3\tshift_m3\ttruck_h_per_1000m3\tkm_per_m3\tmakespan_h\tmax_dump_demand/cap")
    for cap in (5.0, 2.0, 1.3, 1.1, 1.0):
        rows = [g for g in res["grid"] if g["cap_ratio"] == cap]
        for m in METHODS:
            un = [r["results"][m]["unserved_m3"] for r in rows]
            kmv = [r["results"][m]["truck_km"] for r in rows]
            th = [r["results"][m]["truck_hours"] for r in rows]
            ov = [r["results"][m]["unserved_due_to_dump_overflow_m3"] for r in rows]
            sh = [r["results"][m]["unserved_due_to_shift_m3"] for r in rows]
            th = [r["results"][m]["truck_hours_per_1000_m3"] for r in rows]
            kmv = [r["results"][m]["truck_km_per_served_m3"] for r in rows]
            print(f"{cap}\t{m}\tmed {np.median(un):.0f} [{min(un)}..{max(un)}]\tmed {np.median(ov):.0f}\tmed {np.median(sh):.0f}\t"
                  f"med {np.median(th):.1f} [{min(th)}..{max(th)}]\tmed {np.median(kmv):.3f}\t"
                  f"{np.median([r['results'][m]['makespan_h'] for r in rows]):.2f}\t"
                  f"max {max(max(r['results'][m]['dump_demand_over_capacity']) for r in rows):.2f}")
    print("speed sensitivity (cap 1.1):")
    for s in res["speed_sensitivity"]:
        print(" ", s["speed_kmh"], {m: (v["unserved_m3"], v["truck_km"], v["makespan_h"]) for m, v in s["results"].items()})
    print("fleet sensitivity (cap 1.1, 20 km/h):")
    for s in res["fleet_sensitivity"]:
        print(" ", s["n_trucks"], {m: (v["unserved_m3"], v["unserved_due_to_shift_m3"], v["truck_km"], v["makespan_h"]) for m, v in s["results"].items()})
    s0, d0, t0 = make_instance(SEED, 1.1)
    from collections import Counter
    print("instance seed", SEED, "total m3", t0, "districts", dict(Counter(s["district_osm"] for s in s0)),
          "dump caps", [d["cap_m3"] for d in d0])


if __name__ == "__main__":
    main()
