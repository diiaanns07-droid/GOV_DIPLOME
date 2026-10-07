#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A03 — изолированный эксперимент: CVRPTW для вывоза ТКО с контейнерных площадок.

ВСЕ ДАННЫЕ СИНТЕТИЧЕСКИЕ (kind = synthetic). Координаты площадок, депо, полигона,
«барьер» с двумя переездами, объёмы, окна и скорости придуманы для проверки метода.
Это НЕ реальные площадки, НЕ реальная дорожная сеть и НЕ маршруты акимата/оператора.
Рамка координат примерно соответствует Шымкенту только для правдоподобной карты.

Что проверяется (критические предположения A03):
  H1. На 20–50 точках открытый солвер (OR-Tools / VROOM) решает задачу за секунды
      на обычном CPU, т.е. пригоден для локального HTTP API в стиле STUPITS.
  H2. Выигрыш против ОБЪЯВЛЕННОГО простого baseline измерим одним оценщиком
      на одной матрице; сильный baseline (ближайший сосед с окнами) нужно
      показывать рядом со слабым, чтобы не завышать пользу.
  H3. План, построенный по «прямым линиям» (без барьера и коэффициента извилистости),
      при оценке на «сетевой» матрице даёт нарушения — т.е. расстояние без сети
      и пробок нельзя выдавать за реальное время.
  H4. Детерминизм: при лимите по времени результат GLS может зависеть от машины;
      при фиксированном лимите решений — воспроизводим (важно для принципа STUPITS
      «числа формирует код и они воспроизводимы»).

Запуск: python3 A03_vrp_experiment.py  (пишет файлы в ./out)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
import time
from importlib.metadata import version as pkg_version

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

SEED = 20261004
SHIFT_END = 7 * 3600          # 06:00 + 7 ч = 13:00 — последний момент окончания разгрузки на полигоне (допущение)
UNLOAD_S = 15 * 60            # разгрузка на полигоне (допущение)
SETUP_S = 120                 # подъезд/маневр на площадке (допущение)
PER_CONTAINER_S = 90          # опорожнение одного контейнера 1,1 м³ (допущение)
CAPACITY = 280                # вместимость машины, единицы = 0,1 «контейнера 1,1 м³» (допущение)
N_VEHICLES = 4
DROP_PENALTY = 10_000_000     # штраф за необслуженную площадку (сек-эквивалент)

# Рамка, депо, полигон, барьер — синтетические.
BBOX = dict(lat=(42.26, 42.38), lon=(69.52, 69.70))
DEPOT = (42.300, 69.560)                       # synthetic
LANDFILL = (42.250, 69.665)                    # synthetic
BARRIER = ((42.365, 69.515), (42.265, 69.705))  # synthetic «железная дорога»
CROSSINGS = [(0.30, None), (0.78, None)]       # доли длины барьера, где есть переезды


def haversine_km(a, b):
    r = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def crossing_points():
    (a_lat, a_lon), (b_lat, b_lon) = BARRIER
    return [(a_lat + t * (b_lat - a_lat), a_lon + t * (b_lon - a_lon)) for t, _ in CROSSINGS]


def side(p):
    (a_lat, a_lon), (b_lat, b_lon) = BARRIER
    return np.sign((b_lon - a_lon) * (p[0] - a_lat) - (b_lat - a_lat) * (p[1] - a_lon))


def make_instance(n_sites=40, seed=SEED, n_clusters=6):
    rng = np.random.default_rng(seed)
    lat0, lat1 = BBOX["lat"]
    lon0, lon1 = BBOX["lon"]
    centers = np.column_stack([rng.uniform(lat0 + 0.01, lat1 - 0.01, n_clusters),
                               rng.uniform(lon0 + 0.01, lon1 - 0.01, n_clusters)])
    sites = []
    for i in range(n_sites):
        c = centers[i % n_clusters]
        lat = float(np.clip(c[0] + rng.normal(0, 0.007), lat0, lat1))
        lon = float(np.clip(c[1] + rng.normal(0, 0.009), lon0, lon1))
        k = int(rng.choice([1, 2, 3, 4, 5], p=[0.15, 0.30, 0.25, 0.20, 0.10]))
        fill = float(rng.uniform(0.5, 1.0))
        sites.append(dict(id=f"SYN-{i + 1:03d}", lat=round(lat, 6), lon=round(lon, 6),
                          containers=k, fill=round(fill, 2), demand=int(round(k * fill * 10)),
                          service_s=SETUP_S + PER_CONTAINER_S * k, tw=[0, SHIFT_END], tw_reason=None))
    idx = rng.permutation(n_sites)
    n_morning = max(1, round(n_sites * 0.15))
    n_late = max(1, round(n_sites * 0.10))
    for j in idx[:n_morning]:
        sites[j]["tw"] = [0, 2 * 3600]
        sites[j]["tw_reason"] = "synthetic: до 08:00 (например, рядом детское учреждение)"
    for j in idx[n_morning:n_morning + n_late]:
        sites[j]["tw"] = [4 * 3600, SHIFT_END - 30 * 60]
        sites[j]["tw_reason"] = "synthetic: 10:00–12:30 (например, двор рынка после разгрузки)"
    return sites


def build_matrix(coords, detour=1.35, speed_kmh=25.0, barrier=True):
    n = len(coords)
    cps = crossing_points()
    sides = [side(p) for p in coords]
    km = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if barrier and sides[i] != sides[j]:
                d = min(haversine_km(coords[i], c) + haversine_km(c, coords[j]) for c in cps)
            else:
                d = haversine_km(coords[i], coords[j])
            km[i, j] = d * detour
    sec = np.rint(km / speed_kmh * 3600).astype(int)
    return km, sec


# ---------------------------------------------------------------- оценщик (один для всех методов)
def evaluate(routes, sites, km, sec):
    """routes: список последовательностей индексов площадок (0..n-1) для каждой машины.
    Узлы матрицы: 0 = депо, 1..n = площадки, n+1 = полигон. Ожидание при раннем
    прибытии разрешено (бригада ждёт открытия окна); опоздание считается нарушением."""
    n = len(sites)
    L = n + 1
    served = set()
    per_vehicle = []
    late_sites, late_min, wait_min, overflow, overrun = 0, 0.0, 0.0, 0, 0
    for r in routes:
        if not r:
            per_vehicle.append(dict(sites=0, km=0.0, duration_min=0.0, load=0, used=False))
            continue
        t, prev, dist, load = 0, 0, 0.0, 0
        for s in r:
            node = s + 1
            t += sec[prev, node]
            dist += km[prev, node]
            a, b = sites[s]["tw"]
            if t < a:
                wait_min += float(a - t) / 60
                t = a
            if t > b:
                late_sites += 1
                late_min += float(t - b) / 60
            t += sites[s]["service_s"]
            load += sites[s]["demand"]
            served.add(s)
            prev = node
        t += sec[prev, L] + UNLOAD_S
        dist += km[prev, L]
        if load > CAPACITY:
            overflow += 1
        if t > SHIFT_END:
            overrun += 1
        per_vehicle.append(dict(sites=len(r), km=round(float(dist), 2), duration_min=round(float(t) / 60, 1),
                                load=int(load), used=True))
    used = [v for v in per_vehicle if v["used"]]
    durs = np.array([v["duration_min"] for v in used]) if used else np.array([0.0])
    return dict(
        total_km=round(float(sum(v["km"] for v in used)), 2),
        total_duration_min=round(float(durs.sum()), 1),
        makespan_min=round(float(durs.max()), 1),
        wait_min=round(wait_min, 1),
        late_sites=late_sites,
        late_min=round(late_min, 1),
        unserved_sites=n - len(served),
        vehicles_used=len(used),
        shift_overrun_vehicles=overrun,
        capacity_overflow_vehicles=overflow,
        balance_max_minus_min_min=round(float(durs.max() - durs.min()), 1),
        balance_cv=round(float(durs.std() / durs.mean()), 3) if durs.mean() > 0 else None,
        per_vehicle=per_vehicle,
    )


# ---------------------------------------------------------------- baselines
def nearest_neighbor(sites, sec, use_tw):
    """Объявленный алгоритмический baseline (НЕ «маршрут акимата»).
    Машины заполняются по очереди: из депо к ближайшей допустимой площадке
    (вместимость; успеть на полигон до конца смены; при use_tw — успеть до закрытия окна,
    выбор по времени начала обслуживания с учётом ожидания)."""
    n = len(sites)
    L = n + 1
    left = set(range(n))
    routes = []
    for _ in range(N_VEHICLES):
        t, prev, load, r = 0, 0, 0, []
        while True:
            best, best_key = None, None
            for s in left:
                node = s + 1
                arr = t + sec[prev, node]
                a, b = sites[s]["tw"]
                start = max(arr, a) if use_tw else arr
                if use_tw and start > b:
                    continue
                if load + sites[s]["demand"] > CAPACITY:
                    continue
                finish = start + sites[s]["service_s"] + sec[node, L] + UNLOAD_S
                if use_tw and finish > SHIFT_END:
                    continue
                if not use_tw and arr + sites[s]["service_s"] + sec[node, L] + UNLOAD_S > SHIFT_END:
                    continue
                key = (start - t) if use_tw else sec[prev, node]
                if best_key is None or key < best_key:
                    best, best_key = s, key
            if best is None:
                break
            node = best + 1
            arr = t + sec[prev, node]
            t = (max(arr, sites[best]["tw"][0]) if use_tw else arr) + sites[best]["service_s"]
            load += sites[best]["demand"]
            r.append(best)
            left.discard(best)
            prev = node
        routes.append(r)
    return routes


# ---------------------------------------------------------------- OR-Tools
def solve_ortools(sites, sec, time_limit_s=5, solution_limit=None, span_coef=0, duration_cost=False):
    n = len(sites)
    L = n + 1
    starts, ends = [0] * N_VEHICLES, [L] * N_VEHICLES
    mgr = pywrapcp.RoutingIndexManager(n + 2, N_VEHICLES, starts, ends)
    rt = pywrapcp.RoutingModel(mgr)
    service = [0] + [s["service_s"] for s in sites] + [UNLOAD_S]
    demand = [0] + [s["demand"] for s in sites] + [0]

    def travel_cb(i, j):
        a, b = mgr.IndexToNode(i), mgr.IndexToNode(j)
        return int(sec[a, b])

    def time_cb(i, j):
        a, b = mgr.IndexToNode(i), mgr.IndexToNode(j)
        return int(service[a] + sec[a, b])

    tr = rt.RegisterTransitCallback(travel_cb)
    rt.SetArcCostEvaluatorOfAllVehicles(tr)
    tt = rt.RegisterTransitCallback(time_cb)
    rt.AddDimension(tt, SHIFT_END, SHIFT_END + UNLOAD_S, True, "Time")
    td = rt.GetDimensionOrDie("Time")
    for s in range(n):
        idx = mgr.NodeToIndex(s + 1)
        a, b = sites[s]["tw"]
        td.CumulVar(idx).SetRange(a, b)
        rt.AddDisjunction([idx], DROP_PENALTY)
    for v in range(N_VEHICLES):
        # окончание разгрузки на полигоне не позже конца смены: cumul(end) + UNLOAD_S <= SHIFT_END
        td.CumulVar(rt.End(v)).SetMax(SHIFT_END - UNLOAD_S)
    if span_coef:
        td.SetGlobalSpanCostCoefficient(span_coef)
    if duration_cost:
        # цель = время в пути + длительность смены машины (включая ожидание); выезд фиксирован в 06:00
        for v in range(N_VEHICLES):
            td.CumulVar(rt.Start(v)).SetRange(0, 0)
        td.SetSpanCostCoefficientForAllVehicles(1)
    dc = rt.RegisterUnaryTransitCallback(lambda i: demand[mgr.IndexToNode(i)])
    rt.AddDimensionWithVehicleCapacity(dc, 0, [CAPACITY] * N_VEHICLES, True, "Load")

    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    if solution_limit:
        p.solution_limit = solution_limit
        p.time_limit.seconds = 600
    else:
        p.time_limit.seconds = time_limit_s
    t0 = time.perf_counter()
    sol = rt.SolveWithParameters(p)
    wall = time.perf_counter() - t0
    if sol is None:
        return None, wall, None
    routes = []
    for v in range(N_VEHICLES):
        i = rt.Start(v)
        r = []
        i = sol.Value(rt.NextVar(i))
        while not rt.IsEnd(i):
            r.append(mgr.IndexToNode(i) - 1)
            i = sol.Value(rt.NextVar(i))
        routes.append(r)
    return routes, wall, sol.ObjectiveValue()


# ---------------------------------------------------------------- VROOM (та же матрица)
def solve_vroom(sites, sec, exploration_level=5):
    import vroom
    n = len(sites)
    L = n + 1
    inp = vroom.Input()
    inp.set_durations_matrix(profile="car", matrix_input=sec.astype(int).tolist())
    for v in range(N_VEHICLES):
        # VROOM: окно машины ограничивает прибытие в конечную точку; разгрузку учитываем заранее
        inp.add_vehicle(vroom.Vehicle(id=v + 1, start=0, end=L, capacity=[CAPACITY],
                                      time_window=vroom.TimeWindow(0, SHIFT_END - UNLOAD_S)))
    for s, site in enumerate(sites):
        inp.add_job(vroom.Job(id=s + 1, location=s + 1, default_service=site["service_s"],
                              pickup=[site["demand"]],
                              time_windows=[vroom.TimeWindow(site["tw"][0], site["tw"][1])]))
    t0 = time.perf_counter()
    sol = inp.solve(exploration_level=exploration_level, nb_threads=1)
    wall = time.perf_counter() - t0
    df = sol.routes
    routes = []
    for v in range(N_VEHICLES):
        part = df[(df["vehicle_id"] == v + 1) & (df["type"] == "job")]
        routes.append([int(j) - 1 for j in part["id"].tolist()])
    return routes, wall


def route_hash(routes):
    return hashlib.sha256(json.dumps(routes).encode()).hexdigest()[:12]


def strip(m):
    return {k: v for k, v in m.items() if k != "per_vehicle"}


def main():
    global N_VEHICLES
    env = dict(python=sys.version.split()[0], platform=platform.platform(),
               ortools=pkg_version("ortools"), pyvroom=pkg_version("pyvroom"),
               numpy=np.__version__, seed=SEED)
    sites = make_instance(40)
    coords = [DEPOT] + [(s["lat"], s["lon"]) for s in sites] + [LANDFILL]
    km, sec = build_matrix(coords)                     # «сетевая» матрица (барьер + извилистость)
    res = dict(meta=dict(kind="synthetic", experiment="A03-E001", env=env,
                         assumptions=dict(shift_s=SHIFT_END, unload_s=UNLOAD_S, setup_s=SETUP_S,
                                          per_container_s=PER_CONTAINER_S, capacity_units=CAPACITY,
                                          capacity_unit="0.1 container-1.1m3-equivalent",
                                          vehicles=N_VEHICLES, detour=1.35, speed_kmh=25.0,
                                          barrier="synthetic line with 2 crossings")),
               runs={})

    def record(name, routes, wall=None, extra=None):
        m = evaluate(routes, sites, km, sec)
        res["runs"][name] = dict(metrics=m, wall_s=None if wall is None else round(wall, 3),
                                 route_hash=route_hash(routes), routes=routes, **(extra or {}))

    t0 = time.perf_counter(); r = nearest_neighbor(sites, sec, use_tw=False)
    record("B1_nearest_neighbor_no_tw", r, time.perf_counter() - t0)
    t0 = time.perf_counter(); r = nearest_neighbor(sites, sec, use_tw=True)
    record("B2_nearest_neighbor_tw", r, time.perf_counter() - t0)

    r, w, obj = solve_ortools(sites, sec, time_limit_s=5)
    record("OR_gls_5s", r, w, dict(objective=obj))
    r, w, obj = solve_ortools(sites, sec, time_limit_s=5, span_coef=20)
    record("OR_gls_5s_balance_span20", r, w, dict(objective=obj))
    r, w, obj = solve_ortools(sites, sec, time_limit_s=5, duration_cost=True)
    record("OR_gls_5s_cost_travel_plus_duration", r, w, dict(objective=obj))
    r, w = solve_vroom(sites, sec)
    record("VROOM_x5", r, w)

    # H3: план по прямым линиям (без барьера, извилистость 1.0) → оценка на «сетевой» матрице
    km_naive, sec_naive = build_matrix(coords, detour=1.0, barrier=False)
    r, w, obj = solve_ortools(sites, sec_naive, time_limit_s=5)
    pred = strip(evaluate(r, sites, km_naive, sec_naive))
    record("OR_planned_on_crowfly_eval_on_network", r, w,
           dict(predicted_by_crowfly_model=dict(total_km=pred["total_km"], total_duration_min=pred["total_duration_min"],
                                                 makespan_min=pred["makespan_min"], late_sites=pred["late_sites"])))

    # H4: детерминизм
    det = {}
    for label, kw in [("time_1s_a", dict(time_limit_s=1)), ("time_1s_b", dict(time_limit_s=1)),
                      ("time_10s", dict(time_limit_s=10)),
                      ("sol_limit_3000_a", dict(solution_limit=3000)),
                      ("sol_limit_3000_b", dict(solution_limit=3000))]:
        rr, ww, oo = solve_ortools(sites, sec, **kw)
        det[label] = dict(objective=oo, route_hash=route_hash(rr), wall_s=round(ww, 3),
                          total_km=evaluate(rr, sites, km, sec)["total_km"])
    res["determinism"] = det

    # Чувствительность: ранжирование B2 vs OR при разных скорости/извилистости
    sens = []
    for speed in (18.0, 25.0, 32.0):
        for detour in (1.2, 1.35, 1.5):
            k2, s2 = build_matrix(coords, detour=detour, speed_kmh=speed)
            b2 = evaluate(nearest_neighbor(sites, s2, True), sites, k2, s2)
            orr, _, _ = solve_ortools(sites, s2, time_limit_s=3)
            o = evaluate(orr, sites, k2, s2)
            ord_, _, _ = solve_ortools(sites, s2, time_limit_s=3, duration_cost=True)
            od = evaluate(ord_, sites, k2, s2)
            sens.append(dict(speed_kmh=speed, detour=detour,
                             B2=dict(km=b2["total_km"], dur=b2["total_duration_min"], unserved=b2["unserved_sites"], late=b2["late_sites"]),
                             OR=dict(km=o["total_km"], dur=o["total_duration_min"], unserved=o["unserved_sites"], late=o["late_sites"]),
                             OR_dur=dict(km=od["total_km"], dur=od["total_duration_min"], unserved=od["unserved_sites"], late=od["late_sites"])))
    res["sensitivity"] = sens

    # Масштаб: 200 точек, 16 машин (только время/допустимость, не качество)
    scale = {}
    for n_sites, n_veh in ((200, 16),):
        N_VEHICLES = n_veh
        big = make_instance(n_sites, seed=SEED + 1, n_clusters=12)
        cbig = [DEPOT] + [(s["lat"], s["lon"]) for s in big] + [LANDFILL]
        kb, sb = build_matrix(cbig)
        b2 = evaluate(nearest_neighbor(big, sb, True), big, kb, sb)
        rr, ww, _ = solve_ortools(big, sb, time_limit_s=20)
        o = evaluate(rr, big, kb, sb) if rr else None
        rv, wv = solve_vroom(big, sb)
        v = evaluate(rv, big, kb, sb)
        scale[f"{n_sites}_sites_{n_veh}_veh"] = dict(B2=strip(b2), OR_20s=dict(wall_s=round(ww, 2), **(strip(o) if o else {})),
                                                     VROOM_x5=dict(wall_s=round(wv, 2), **strip(v)))
    N_VEHICLES = 4
    res["scale"] = scale

    with open(os.path.join(OUT, "A03_experiment_results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    # GeoJSON для карты (прямые отрезки между точками — НЕ геометрия дорог)
    feats = []
    for i, s in enumerate(sites):
        feats.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[s["lon"], s["lat"]]),
                          properties=dict(kind="synthetic", role="container_site", **{k: v for k, v in s.items() if k not in ("lat", "lon")})))
    for name, pt in (("depot", DEPOT), ("landfill", LANDFILL)):
        feats.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[pt[1], pt[0]]),
                          properties=dict(kind="synthetic", role=name, id=f"SYN-{name.upper()}")))
    feats.append(dict(type="Feature", geometry=dict(type="LineString", coordinates=[[p[1], p[0]] for p in BARRIER]),
                      properties=dict(kind="synthetic", role="barrier", crossings=[[c[1], c[0]] for c in crossing_points()])))
    for run in ("B2_nearest_neighbor_tw", "OR_gls_5s"):
        for v, r in enumerate(res["runs"][run]["routes"]):
            if not r:
                continue
            pts = [DEPOT] + [(sites[s]["lat"], sites[s]["lon"]) for s in r] + [LANDFILL]
            feats.append(dict(type="Feature", geometry=dict(type="LineString", coordinates=[[p[1], p[0]] for p in pts]),
                              properties=dict(kind="synthetic", role="route", run=run, vehicle=v + 1,
                                              note="straight segments between stops, not road geometry")))
    with open(os.path.join(OUT, "A03_synthetic_instance.geojson"), "w", encoding="utf-8") as f:
        json.dump(dict(type="FeatureCollection", name="A03 synthetic instance (NOT real data)", features=feats),
                  f, ensure_ascii=False, indent=1)

    # Сводка в stdout
    print(json.dumps(env, ensure_ascii=False))
    hdr = ["run", "km", "dur_min", "makespan", "wait", "late", "late_min", "unserved", "veh", "overrun", "bal_max-min", "cv", "wall_s"]
    print("\t".join(hdr))
    for name, d in res["runs"].items():
        m = d["metrics"]
        print("\t".join(str(x) for x in [name, m["total_km"], m["total_duration_min"], m["makespan_min"], m["wait_min"],
                                          m["late_sites"], m["late_min"], m["unserved_sites"], m["vehicles_used"],
                                          m["shift_overrun_vehicles"], m["balance_max_minus_min_min"], m["balance_cv"], d["wall_s"]]))
    print("determinism:", json.dumps(det, ensure_ascii=False))
    print("sensitivity:")
    for s in sens:
        print(s)
    print("scale:", json.dumps(scale, ensure_ascii=False, indent=1))
    tot_demand = sum(s["demand"] for s in sites)
    print("total_demand_units", tot_demand, "fleet_capacity", CAPACITY * 4,
          "tw_morning", sum(1 for s in sites if s["tw"][1] == 7200), "tw_late", sum(1 for s in sites if s["tw"][0] == 14400),
          "sides", {int(k): int(v) for k, v in zip(*np.unique([side(c) for c in coords], return_counts=True))})


if __name__ == "__main__":
    main()
