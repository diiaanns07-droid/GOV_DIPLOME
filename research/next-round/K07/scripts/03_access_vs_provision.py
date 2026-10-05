#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K07 stage 4: geographic access vs provision by seats — a small, hand-checkable, SYNTHETIC example.

No city data, no invented population or school capacity:
  * geography is a toy street grid (kind=synthetic);
  * geographic access uses only coordinates (share of residential BLOCKS, not people);
  * capacity and demand are NOT given as numbers. Only their unknown shares are swept as scenario
    parameters:  s = C_E / (C_W + C_E)  (share of seats in area E)
                 q = D_E / (D_W + D_E)  (share of children in area E)
    Provision is reported relative to the city average C/D, so absolute values cancel.
  * assumption (stated, not data): inside each area, children are spread evenly over its blocks.

Toy: 2.0 x 1.0 km grid, 100 m step. A railway between x=1000 and x=1100 with ONE crossing at y=1000.
Area W (x<=1000) has school S_W at (900,100) next to the railway; area E (x>=1100) has S_E at (1500,500).
25 residential blocks per area on a 200 m lattice.

Usage: python3 03_access_vs_provision.py [--repo-root PATH]
Writes results/03_access_vs_provision_results.json and results/03_access_vs_provision_tables.md
Requires: Python 3.12, networkx 3.6.1.
"""
import argparse, json, math
from pathlib import Path

import networkx as nx

HERE = Path(__file__).resolve()
DEFAULT_ROOT = HERE.parents[4]

STEP, XMAX, YMAX = 100, 2000, 1000
RAIL_WEST_X, RAIL_EAST_X, CROSSING_Y = 1000, 1100, 1000
SCHOOLS = {"S_W": (900, 100), "S_E": (1500, 500)}
LATTICE = [100, 300, 500, 700, 900]
BLOCKS = [(x, y, "W") for x in LATTICE for y in LATTICE] + [(x + 1000, y, "E") for x in LATTICE for y in LATTICE]
THRESHOLDS = (500, 800, 1000)
T_MAIN = 800
S_GRID = (0.3, 0.5, 0.7)
Q_GRID = (0.3, 0.5, 0.7)


def build_graph():
    G = nx.grid_2d_graph(XMAX // STEP + 1, YMAX // STEP + 1)
    G = nx.relabel_nodes(G, {(i, j): (i * STEP, j * STEP) for i, j in G.nodes})
    for y in range(0, YMAX + 1, STEP):
        if y != CROSSING_Y:
            G.remove_edge((RAIL_WEST_X, y), (RAIL_EAST_X, y))
    nx.set_edge_attributes(G, STEP, "m")
    return G


def distances(G):
    net = {k: nx.single_source_dijkstra_path_length(G, p, weight="m") for k, p in SCHOOLS.items()}
    out = {}
    for x, y, a in BLOCKS:
        out[(x, y)] = {"area": a,
                       "net": {k: net[k][(x, y)] for k in SCHOOLS},
                       "radius": {k: math.dist((x, y), p) for k, p in SCHOOLS.items()}}
    return out


def geographic_access(D, T, metric):
    res = {}
    for a in ("W", "E"):
        blocks = [b for b in D.values() if b["area"] == a]
        res[a] = round(100 * sum(min(b[metric].values()) <= T for b in blocks) / len(blocks), 1)
    return res


def catchments(D, T, metric):
    return {k: sorted(xy for xy, b in D.items() if b[metric][k] <= T) for k in SCHOOLS}


def provision(D, T, metric, s, q):
    """2SFCA with uniform demand inside each area; result relative to the city mean C/D (=1)."""
    cap = {"S_W": 1 - s, "S_E": s}                      # shares of total seats C
    n_area = {a: sum(1 for b in D.values() if b["area"] == a) for a in ("W", "E")}
    dem = {xy: ((1 - q) if b["area"] == "W" else q) / n_area[b["area"]] for xy, b in D.items()}  # shares of total D
    R = {}
    for k in SCHOOLS:
        inside = [xy for xy, b in D.items() if b[metric][k] <= T]
        tot = sum(dem[xy] for xy in inside)
        R[k] = cap[k] / tot if tot > 0 else 0.0
    A = {xy: sum(R[k] for k in SCHOOLS if b[metric][k] <= T) for xy, b in D.items()}
    out = {}
    for a in ("W", "E"):
        xs = [xy for xy, b in D.items() if b["area"] == a]
        w = sum(dem[xy] for xy in xs)
        out[a] = {"mean_rel_provision": round(sum(A[xy] * dem[xy] for xy in xs) / w, 3),
                  "share_of_area_demand_with_no_seats_in_reach_pct": round(100 * sum(dem[xy] for xy in xs if A[xy] == 0) / w, 1)}
    # Seats counted inside reach can exceed or fall short of real seats when catchments overlap;
    # the area mean is NOT a balance sheet, it is the 2SFCA accessibility index.
    return out


def arithmetic(s, q):
    return {"W": round((1 - s) / (1 - q), 3), "E": round(s / q, 3)}


def worse(d):
    if math.isclose(d["W"], d["E"], abs_tol=1e-9):
        return "equal"
    return "W" if d["W"] < d["E"] else "E"


def ascii_map(D, T):
    """● covered by network, ○ covered by radius only, × not covered; S = school; | railway, = crossing."""
    rows = []
    for y in reversed(LATTICE):
        line = ""
        for x in [*LATTICE, *[v + 1000 for v in LATTICE]]:
            if x == 1100:
                line += " = " if y == 900 else " | "
            b = D[(x, y)]
            n, r = min(b["net"].values()) <= T, min(b["radius"].values()) <= T
            line += "●" if n else ("○" if r else "×")
            line += " "
        rows.append(f"y={y:<4} {line}")
    rows.append("        x=100 … 900   |  x=1100 … 1900")
    rows.append("Schools: S_W at (900,100) beside the railway (bottom row, 5th mark is its block);"
                " S_E at (1500,500) (middle of area E). Crossing '=' is at y=1000 (drawn on the top row).")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(DEFAULT_ROOT))
    root = Path(ap.parse_args().repo_root).resolve()
    outdir = root / "research/next-round/K07/results"
    G = build_graph()
    D = distances(G)

    geo = {str(T): {"network": geographic_access(D, T, "net"), "radius_baseline": geographic_access(D, T, "radius")}
           for T in THRESHOLDS}
    catch = {m: {k: len(v) for k, v in catchments(D, T_MAIN, m).items()} for m in ("net", "radius")}
    cross = {m: {k: sum(1 for xy in v if D[xy]["area"] != ("W" if k == "S_W" else "E"))
                 for k, v in catchments(D, T_MAIN, m).items()} for m in ("net", "radius")}

    scen = []
    for s in S_GRID:
        for q in Q_GRID:
            p0 = arithmetic(s, q)
            pn = provision(D, T_MAIN, "net", s, q)
            pr = provision(D, T_MAIN, "radius", s, q)
            g = geo[str(T_MAIN)]["network"]
            row = {"s_seat_share_E": s, "q_child_share_E": q,
                   "geographic_access_network_pct": g,
                   "provision_arithmetic_area_balance": p0,
                   "provision_2sfca_network": {a: v["mean_rel_provision"] for a, v in pn.items()},
                   "no_seats_in_reach_network_pct": {a: v["share_of_area_demand_with_no_seats_in_reach_pct"] for a, v in pn.items()},
                   "provision_2sfca_radius_baseline": {a: v["mean_rel_provision"] for a, v in pr.items()},
                   "no_seats_in_reach_radius_pct": {a: v["share_of_area_demand_with_no_seats_in_reach_pct"] for a, v in pr.items()}}
            row["worse_area"] = {"geographic_access": "W" if g["W"] < g["E"] else ("E" if g["E"] < g["W"] else "equal"),
                                 "provision_arithmetic": worse(p0),
                                 "provision_2sfca_network": worse(row["provision_2sfca_network"]),
                                 "provision_2sfca_radius": worse(row["provision_2sfca_radius_baseline"])}
            gw, pw, rw = (row["worse_area"][k] for k in ("geographic_access", "provision_2sfca_network", "provision_2sfca_radius"))
            row["seats_vs_geography"] = "same" if pw == gw else ("seats_do_not_separate" if pw == "equal" else "opposite")
            row["radius_vs_network_seats"] = "same" if rw == pw else ("radius_breaks_tie" if pw == "equal" else "opposite")
            scen.append(row)

    # self-checks that a reader can redo by hand (see the .md file)
    assert geo["800"]["network"] == {"W": 60.0, "E": 100.0}, geo["800"]
    assert geo["800"]["radius_baseline"] == {"W": 68.0, "E": 100.0}, geo["800"]
    assert catch == {"net": {"S_W": 15, "S_E": 25}, "radius": {"S_W": 29, "S_E": 31}}, catch
    for r in scen:  # with network catchments inside each area, the area mean equals the arithmetic balance
        assert r["provision_2sfca_network"] == r["provision_arithmetic_area_balance"], r

    res = {"kind": "synthetic example; no city data; capacity and demand only as unknown shares",
           "assumptions": ["children spread evenly over blocks inside each area (unknown in reality)",
                           "walking threshold T is a parameter, not a norm",
                           "blocks are not population: geographic access is a share of blocks"],
           "toy": {"grid": "2.0 x 1.0 km, 100 m step", "railway": "between x=1000 and x=1100, one crossing at y=1000",
                   "schools": SCHOOLS, "blocks_per_area": 25, "T_main_m": T_MAIN},
           "geographic_access_pct_by_threshold": geo,
           "catchment_sizes_blocks_T800": catch, "catchment_blocks_from_other_area_T800": cross,
           "scenarios_T800": scen,
           "seats_vs_geography_counts": {k: sum(r["seats_vs_geography"] == k for r in scen) for k in ("same", "seats_do_not_separate", "opposite")},
           "radius_vs_network_seats_counts": {k: sum(r["radius_vs_network_seats"] == k for r in scen) for k in ("same", "radius_breaks_tie", "opposite")},
           "versions": {"networkx": nx.__version__}}
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "03_access_vs_provision_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    md = ["# K07 · Результаты синтетического примера (сгенерировано скриптом 03_access_vs_provision.py)", "",
          "**Синтетика.** Не данные Астаны или Шымкента. Вместимость и численность детей не заданы: перебираются только их неизвестные доли `s` и `q`.", "",
          f"## Карта игрушки, T = {T_MAIN} м", "", "```", ascii_map(D, T_MAIN), "```", "",
          "● — квартал в пределах T по сети; ○ — только по радиусу (ошибка baseline); × — дальше T и по радиусу.", "",
          "## Географическая доступность: доля кварталов в пределах T", "",
          "| T, м | W по сети | W по радиусу | E по сети | E по радиусу |", "|---|---|---|---|---|"]
    for T in THRESHOLDS:
        g = geo[str(T)]
        md.append(f"| {T} | {g['network']['W']} % | {g['radius_baseline']['W']} % | {g['network']['E']} % | {g['radius_baseline']['E']} % |")
    md += ["", f"Зоны обслуживания при T = {T_MAIN} м: по сети S_W — {catch['net']['S_W']} кварталов, S_E — {catch['net']['S_E']}; "
           f"по радиусу S_W — {catch['radius']['S_W']} (из них {cross['radius']['S_W']} за железной дорогой), "
           f"S_E — {catch['radius']['S_E']} (из них {cross['radius']['S_E']} за железной дорогой).", "",
           f"## Обеспеченность местами при T = {T_MAIN} м (1,00 = среднее по игрушечному городу)", "",
           "| s (доля мест в E) | q (доля детей в E) | Хуже по географии | Баланс мест W / E | 2SFCA по сети W / E | Хуже по местам (сеть) | 2SFCA по радиусу W / E | Хуже по местам (радиус) |",
           "|---|---|---|---|---|---|---|---|"]
    for r in scen:
        p0, pn, pr, w = r["provision_arithmetic_area_balance"], r["provision_2sfca_network"], r["provision_2sfca_radius_baseline"], r["worse_area"]
        md.append(f"| {r['s_seat_share_E']} | {r['q_child_share_E']} | {w['geographic_access']} | {p0['W']:.2f} / {p0['E']:.2f} | "
                  f"{pn['W']:.2f} / {pn['E']:.2f} | {w['provision_2sfca_network']} | {pr['W']:.2f} / {pr['E']:.2f} | {w['provision_2sfca_radius']} |")
    sv, rv = res["seats_vs_geography_counts"], res["radius_vs_network_seats_counts"]
    md += ["", f"Из {len(scen)} сценариев места по сети указывают ту же худшую территорию, что и география, в {sv['same']}, "
           f"противоположную — в {sv['opposite']}, а в {sv['seats_do_not_separate']} территории по местам равны.",
           f"Радиус вместо сети меняет вывод по местам на противоположный в {rv['opposite']} сценариях "
           f"и выдумывает различие при равенстве ещё в {rv['radius_breaks_tie']}.",
           "", "При любых s и q по сети у 40 % спроса W нет мест в пределах T (10 из 25 кварталов). Это следует из одной геометрии."]
    (outdir / "03_access_vs_provision_tables.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
