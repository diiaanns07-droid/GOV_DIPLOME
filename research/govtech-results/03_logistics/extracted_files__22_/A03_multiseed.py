#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A03-E002: 10 синтетических экземпляров по 40 площадок (seed 20261004..20261013).
Сравнение B2 (ближайший сосед с окнами) с OR-Tools (цель: пробег; цель: пробег+длительность)
и VROOM на одной «сетевой» синтетической матрице и одном оценщике. ВСЕ ДАННЫЕ СИНТЕТИЧЕСКИЕ."""
import json
import os
import statistics as st

import sys

import A03_vrp_experiment as X

# Запуск: python3 A03_multiseed.py run K   — посчитать экземпляр seed=SEED+K и дописать строку в out/A03_multiseed_rows.jsonl
#         python3 A03_multiseed.py summary — собрать сводку из jsonl
ROWS = os.path.join(X.OUT, "A03_multiseed_rows.jsonl")
mode = sys.argv[1] if len(sys.argv) > 1 else "summary"
ks = [int(sys.argv[2])] if mode == "run" else []
rows = []
for k in ks:
    seed = X.SEED + k
    sites = X.make_instance(40, seed=seed)
    coords = [X.DEPOT] + [(s["lat"], s["lon"]) for s in sites] + [X.LANDFILL]
    km, sec = X.build_matrix(coords)
    b2 = X.evaluate(X.nearest_neighbor(sites, sec, True), sites, km, sec)
    o1r, _, _ = X.solve_ortools(sites, sec, solution_limit=500)
    o1 = X.evaluate(o1r, sites, km, sec)
    o2r, _, _ = X.solve_ortools(sites, sec, solution_limit=500, duration_cost=True)
    o2 = X.evaluate(o2r, sites, km, sec)
    vr, vw = X.solve_vroom(sites, sec)
    v = X.evaluate(vr, sites, km, sec)
    row = dict(seed=seed)
    for name, m in (("B2", b2), ("OR_travel", o1), ("OR_travel_plus_duration", o2), ("VROOM", v)):
        row[name] = dict(km=m["total_km"], dur=m["total_duration_min"], late=m["late_sites"],
                         unserved=m["unserved_sites"], veh=m["vehicles_used"])
    with open(ROWS, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(row, flush=True)
if mode == "run":
    sys.exit(0)
rows = [json.loads(l) for l in open(ROWS, encoding="utf-8")]
rows = sorted({r["seed"]: r for r in rows}.values(), key=lambda r: r["seed"])


def rel(a, b):
    return (a - b) / b * 100


summary = {}
for name in ("OR_travel", "OR_travel_plus_duration", "VROOM"):
    dkm = [rel(r[name]["km"], r["B2"]["km"]) for r in rows]
    ddur = [rel(r[name]["dur"], r["B2"]["dur"]) for r in rows]
    summary[name] = dict(
        km_change_vs_B2_pct=dict(median=round(st.median(dkm), 1), min=round(min(dkm), 1), max=round(max(dkm), 1)),
        duration_change_vs_B2_pct=dict(median=round(st.median(ddur), 1), min=round(min(ddur), 1), max=round(max(ddur), 1)),
        instances_better_on_both=sum(1 for a, b in zip(dkm, ddur) if a < 0 and b < 0),
        any_late=sum(r[name]["late"] for r in rows), any_unserved=sum(r[name]["unserved"] for r in rows))
summary["B2"] = dict(any_late=sum(r["B2"]["late"] for r in rows), any_unserved=sum(r["B2"]["unserved"] for r in rows))
out = dict(meta=dict(kind="synthetic", experiment="A03-E002", n_instances=10, sites=40,
                     solver_limit="OR-Tools solution_limit=500; VROOM exploration_level=5, 1 thread"),
           rows=rows, summary=summary)
with open(os.path.join(X.OUT, "A03_multiseed_results.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
