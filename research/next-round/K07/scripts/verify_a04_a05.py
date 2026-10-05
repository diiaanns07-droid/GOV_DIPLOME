#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K07: independent re-run of the A04 and A05 synthetic experiments (kind=synthetic, NOT city data).

What it does (no network access, originals are only read):
  1. Records SHA-256 of the original scripts and result files.
  2. Runs copies of A04_synthetic_experiment.py and A05_experiment.py in a temporary directory
     (A05 writes its JSON into the current directory, so it must never run next to the original).
  3. Compares the fresh outputs with the stored result files.
  4. Checks numbers quoted in A04_report.md / A05_report.md / AST_A05_report.md against the JSON.
  5. K07 addition: splits the "radius minus network" coverage gap into
       (a) the grid-geometry part (straight line vs Manhattan grid without any barrier) and
       (b) the obstacle part (railway/industrial block),
     because on a square grid the radius over-states coverage even when there is no barrier.

Usage:
  python3 verify_a04_a05.py [--repo-root PATH] [--out PATH]
Requires: Python 3.12, numpy 2.4.4, networkx 3.6.1, scipy 1.17.1 (the versions recorded by A04/A05).
"""
import argparse, hashlib, json, math, os, runpy, shutil, subprocess, sys, tempfile
from pathlib import Path

import numpy as np
import networkx as nx

HERE = Path(__file__).resolve()
DEFAULT_ROOT = HERE.parents[4]  # research/next-round/K07/scripts/ -> repo root

A04_DIR = "research/govtech-results/04_infrastructure/extracted_files__13_"
A05_DIR = "research/govtech-results/05_education/extracted_files__14_"
AST_A05_DIR = "research/astana-results/05_education/extracted_files__27_"


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def json_diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append({"path": f"{path}/{k}", "stored": a.get(k, "<missing>"), "rerun": b.get(k, "<missing>")})
            else:
                out += json_diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += json_diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append({"path": path, "stored": a, "rerun": b})
    return out


def pct(x):
    return round(100 * x, 1)


def check(claims, cid, source, text, reported, computed):
    claims.append({"id": cid, "source": source, "claim": text, "reported": reported,
                   "computed": computed, "status": "match" if reported == computed else "MISMATCH"})


def coverage(dist_by_node, weights, T):
    tot = sum(weights.values())
    return sum(w for n, w in weights.items() if dist_by_node.get(n, math.inf) <= T) / tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=str(DEFAULT_ROOT))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()
    out_path = Path(args.out) if args.out else root / "research/next-round/K07/results/verify_a04_a05_results.json"

    a04_py, a04_json = root / A04_DIR / "A04_synthetic_experiment.py", root / A04_DIR / "A04_synthetic_results.json"
    a05_py, a05_json = root / A05_DIR / "A05_experiment.py", root / A05_DIR / "A05_synthetic_results.json"
    stored04, stored05 = json.loads(a04_json.read_text()), json.loads(a05_json.read_text())

    res = {"kind": "verification of synthetic experiments; no city data",
           "environment": {"python": sys.version.split()[0], "numpy": np.__version__, "networkx": nx.__version__},
           "inputs_sha256": {str(p.relative_to(root)): sha256(p) for p in (a04_py, a04_json, a05_py, a05_json)}}
    import scipy
    res["environment"]["scipy"] = scipy.__version__

    tmp = Path(tempfile.mkdtemp(prefix="k07_repro_"))
    try:
        # ---------- 1. A04 re-run ----------
        shutil.copy(a04_py, tmp)
        p = subprocess.run([sys.executable, "A04_synthetic_experiment.py"], cwd=tmp, capture_output=True, text=True)
        rerun04_bytes = p.stdout.encode()
        rerun04 = json.loads(p.stdout)
        res["A04_rerun"] = {"exit_code": p.returncode,
                            "stdout_sha256": hashlib.sha256(rerun04_bytes).hexdigest(),
                            "byte_identical_to_stored": hashlib.sha256(rerun04_bytes).hexdigest() == sha256(a04_json),
                            "json_differences": json_diff(stored04, rerun04)}

        # ---------- 2. A05 re-run (module globals kept for extra checks) ----------
        shutil.copy(a05_py, tmp)
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                g05 = runpy.run_path(str(tmp / "A05_experiment.py"), run_name="a05_rerun")
        finally:
            os.chdir(cwd)
        rerun05 = json.loads((tmp / "A05_synthetic_results.json").read_text())
        diffs05 = json_diff(stored05, rerun05)
        res["A05_rerun"] = {"json_differences": diffs05,
                            "only_environment_fields_differ": all(d["path"] in ("/meta/platform", "/meta/runtime_s") for d in diffs05)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------- 3. claims from reports vs JSON ----------
    claims = []
    c04 = {c["threshold_m"]: c for c in rerun04["coverage"]}
    s04 = {s["threshold_m"]: s for s in rerun04["site_comparison"]}
    src = "A04_report.md §11"
    for T, (eu, net, false, se) in {500: (67.4, 44.9, 22.5, 1.3), 800: (94.3, 83.3, 11.0, 26.2), 1000: (96.7, 93.8, 2.8, 53.2)}.items():
        c = c04[T]
        check(claims, f"A04-T{T}-radius", src, f"{T} м: покрытие по радиусу", eu, pct(c["covered_share_euclid"]))
        check(claims, f"A04-T{T}-network", src, f"{T} м: покрытие по сети", net, pct(c["covered_share_network"]))
        check(claims, f"A04-T{T}-false", src, f"{T} м: «ложно покрыты»", false, pct(c["false_covered_share"]))
        check(claims, f"A04-T{T}-SE", src, f"{T} м: SE по сети", se, pct(c["by_microdistrict"]["SE"]["covered_share_network"]))
    check(claims, "A04-detour", src, "обход сеть/прямая: медиана, p90, максимум", [1.34, 1.41, 1.86],
          [round(x, 2) for x in c04[500]["detour_ratio_p50_p90_max"]])
    check(claims, "A04-rank500", "A04_report.md §11", "500 м: A>C>B", ["A", "C", "B"], s04[500]["rank_by_network"])
    check(claims, "A04-rank800", "A04_report.md §11", "800 м: C>B>A", ["C", "B", "A"], s04[800]["rank_by_network"])
    check(claims, "A04-A800", "A04_report.md §11", "A при 800 м: прирост по радиусу и по сети", [3229, 4937],
          [s04[800]["sites"]["A"]["new_covered_pop_euclid"], s04[800]["sites"]["A"]["new_covered_pop_network"]])
    check(claims, "A04-graph", "A04_report.md §11", "1 600 узлов, 3 061 ребро", [1600, 3061],
          [rerun04["graph"]["nodes"], rerun04["graph"]["edges"]])

    h1, h2, h3, h4 = (rerun05[k] for k in ("H1_euclid_vs_network", "H2_capacity", "H3_placement", "H4_sensitivity"))
    src = "A05_report.md §7"
    check(claims, "A05-H1-1000", src, "1000 м: покрытие прямое против сети", [83.4, 74.9],
          [pct(h1["1000"]["cov_euclid"]), pct(h1["1000"]["cov_network"])])
    check(claims, "A05-H1-1000-G", src, "1000 м, территория Г", [58.7, 45.7],
          [pct(h1["1000"]["by_territory_euclid"]["Г"]), pct(h1["1000"]["by_territory_network"]["Г"])])
    check(claims, "A05-H1-1500-G", src, "1500 м, территория Г", [93.9, 64.2],
          [pct(h1["1500"]["by_territory_euclid"]["Г"]), pct(h1["1500"]["by_territory_network"]["Г"])])
    check(claims, "A05-H1-1500-wrong", src, "1500 м: ошибочно «покрыто» из всего спроса", [748.6, 6269.2],
          [h1["1500"]["demand_wrongly_covered_by_euclid"], rerun05["inputs"]["total_demand"]])
    check(claims, "A05-H2-three", src, "три дефицита: арифметический, в пределах 1500 м, ближайшая школа",
          [769.2, 1092.6, 1717.2],
          [h2["global_deficit_demand_minus_capacity"], h2["lp_dmax_unmet_seats"], h2["nearest_rule_total_overflow"]])
    check(claims, "A05-H2-G", src, "из дефицита в пределах 1500 м — в Г", 1040.5, h2["lp_dmax_unmet_by_territory"]["Г"])
    s2 = h2["nearest_rule_load_vs_cap"]["S2"]
    check(claims, "A05-H2-S2", src, "S2 загружена на 48% по правилу ближайшей школы", 48, round(100 * s2["load"] / s2["cap"]))
    check(claims, "A05-H2-rezone", src, "перезакрепление: кварталов, доля спроса %, максимальный путь м",
          [25, 30.5, 2800.0],
          [h2["rezoning_blocks_changed"], pct(h2["rezoning_demand_changed"] / rerun05["inputs"]["total_demand"]),
           h2["lp_max_dist_served_m"]])
    cand = {r["candidate"]: r for r in h3["candidates"]}
    check(claims, "A05-H3-dmax", src, "С dmax=1500: C2/C3/C5, C1, C6 (непокрытые места)",
          [92.6, 92.6, 92.6, 154.8, 1092.6], [cand[k]["unmet_lp"] for k in ("C2", "C3", "C5", "C1", "C6")])
    check(claims, "A05-H3-rho", src, "Spearman ρ географии и мест", 0.80, round(h3["spearman_geo_coverage_vs_minus_unmet"], 2))
    # rank of C1: competition ranking ("1224"), ties share the best place
    def comp_rank(values, key, reverse):
        vals = sorted((v for v in values.values()), reverse=reverse)
        return 1 + sum(1 for v in vals if (v > values[key] if reverse else v < values[key]))
    cov = {k: r["cov_net_1000"] for k, r in cand.items()}
    unm = {k: r["unmet_lp"] for k, r in cand.items()}
    check(claims, "A05-H3-C1-rank", src, "C1 — третий по покрытию, но шестой по непокрытым местам", [3, 6],
          [comp_rank(cov, "C1", True), comp_rank(unm, "C1", False)])
    check(claims, "A05-H3-2SFCA", src, "2SFCA min/max: база → C3; Gini база → C3", [0.287, 0.530, 0.380, 0.261],
          [round(h3["baseline_no_build"]["terr_min_over_max_2sfca"], 3), round(cand["C3"]["terr_min_over_max_2sfca"], 3),
           round(h3["baseline_no_build"]["gini_2sfca"], 3), round(cand["C3"]["gini_2sfca"], 3)])
    f = h4["in_best_tied_set_frequency"]
    check(claims, "A05-H4", src, "200 сценариев с ничьей; C2,C3,C5 100%, C1 78%, C6 0%; регрет C1 p90 122",
          [200, 100, 100, 100, 78, 0, 122],
          [h4["scenarios_with_tie_on_unmet"], round(100 * f["C2"]), round(100 * f["C3"]), round(100 * f["C5"]),
           round(100 * f["C1"]), round(100 * f["C6"]), round(h4["regret_unmet_seats_if_C1"]["p90"])])
    check(claims, "AST-A05-G-thresholds", "AST_A05_report.md §6", "Г: 500/1000/1500 м по сети", [9.8, 45.7, 64.2],
          [pct(h1[t]["by_territory_network"]["Г"]) for t in ("500", "1000", "1500")])

    # A05 H3 "without dmax all 8 sites give 0 unmet" is not stored in JSON -> recompute with the module's own LP
    ids0, caps0 = g05["ids0"], g05["caps0"]
    no_dmax = {cid: round(g05["lp_assign"](ids0 + [cid], caps0 + [g05["NEW_CAP"]], g05["D"], g05["DN"])["unmet"], 4)
               for cid, _ in g05["candidates"]}
    check(claims, "A05-H3-no-dmax", "A05_report.md §7 (не записано в JSON; пересчитано)",
          "без dmax все 8 участков дают 0 непокрытых", [0.0] * 8, list(no_dmax.values()))
    res["claims"] = claims
    res["claims_summary"] = {"total": len(claims), "match": sum(c["status"] == "match" for c in claims),
                             "mismatch": [c["id"] for c in claims if c["status"] != "match"]}

    # ---------- 4. K07: decomposition of the radius-vs-network gap ----------
    g04 = runpy.run_path(str(a04_py), run_name="a04_module")  # __main__ block is not executed
    G04, pop, FAC, STEP, SIZE = g04["G"], g04["pop"], g04["FAC"], g04["STEP"], g04["SIZE"]
    open_grid = nx.grid_2d_graph(SIZE // STEP + 1, SIZE // STEP + 1)
    open_grid = nx.relabel_nodes(open_grid, {(i, j): (i * STEP, j * STEP) for i, j in open_grid.nodes})
    nx.set_edge_attributes(open_grid, STEP, "length")
    industry_only = G04.copy()  # same as G04 but with all barrier edges restored -> industrial block only
    for x in range(0, SIZE + 1, STEP):
        if (x, 1000) in industry_only and (x, 1050) in industry_only:
            industry_only.add_edge((x, 1000), (x, 1050), length=STEP)
    euc = {n: min(math.dist(n, f) for f in FAC) for n in pop}
    variants04 = {"radius": euc,
                  "grid_without_obstacles": nx.multi_source_dijkstra_path_length(open_grid, FAC, weight="length"),
                  "grid_with_industrial_block_only": nx.multi_source_dijkstra_path_length(industry_only, FAC, weight="length"),
                  "a04_network_barrier_and_block": nx.multi_source_dijkstra_path_length(G04, FAC, weight="length")}
    dec04 = {}
    for T in (500, 800, 1000):
        cv = {k: coverage(v, pop, T) for k, v in variants04.items()}
        by_q = {q: {k: pct(coverage(v, {n: w for n, w in pop.items() if g04["quadrant"](*n) == q}, T))
                    for k, v in variants04.items()} for q in ("NW", "NE", "SW", "SE")}
        dec04[str(T)] = {"coverage_pct": {k: pct(v) for k, v in cv.items()},
                         "by_quadrant_coverage_pct": by_q,
                         "gap_total_pp": round(100 * (cv["radius"] - cv["a04_network_barrier_and_block"]), 1),
                         "gap_grid_geometry_pp": round(100 * (cv["radius"] - cv["grid_without_obstacles"]), 1),
                         "gap_obstacles_pp": round(100 * (cv["grid_without_obstacles"] - cv["a04_network_barrier_and_block"]), 1)}

    G05, blocks, D, schools, N05, STEP05 = g05["G"], g05["blocks"], g05["D"], g05["schools"], g05["N"], g05["STEP"]
    w05 = {b["node"]: float(d) for b, d in zip(blocks, D)}
    terr05 = {b["node"]: b["territory"] for b in blocks}
    src05 = [n for _, n, _ in schools]
    open05 = nx.grid_2d_graph(N05, N05)
    nx.set_edge_attributes(open05, STEP05, "w")
    variants05 = {"radius": {n: min(STEP05 * math.hypot(n[0] - s[0], n[1] - s[1]) for s in src05) for n in w05},
                  "grid_without_barrier": nx.multi_source_dijkstra_path_length(open05, src05, weight="w"),
                  "a05_network_with_barrier": nx.multi_source_dijkstra_path_length(G05, src05, weight="w")}
    dec05 = {}
    for T in (500, 1000, 1500):
        cv = {k: coverage(v, w05, T) for k, v in variants05.items()}
        wG = {n: w for n, w in w05.items() if terr05[n] == "Г"}
        cvG = {k: coverage(v, wG, T) for k, v in variants05.items()}
        dec05[str(T)] = {"coverage_pct": {k: pct(v) for k, v in cv.items()},
                         "gap_total_pp": round(100 * (cv["radius"] - cv["a05_network_with_barrier"]), 1),
                         "gap_grid_geometry_pp": round(100 * (cv["radius"] - cv["grid_without_barrier"]), 1),
                         "gap_barrier_pp": round(100 * (cv["grid_without_barrier"] - cv["a05_network_with_barrier"]), 1),
                         "territory_G_coverage_pct": {k: pct(v) for k, v in cvG.items()}}
    # self-check: the decomposition endpoints must equal the stored results
    assert pct(coverage(variants04["a04_network_barrier_and_block"], pop, 500)) == pct(c04[500]["covered_share_network"])
    assert pct(coverage(variants05["a05_network_with_barrier"], w05, 1000)) == pct(h1["1000"]["cov_network"])
    res["K07_gap_decomposition"] = {
        "kind": "synthetic (same toy inputs as A04/A05)",
        "why": "on a square street grid, network distance >= Manhattan >= straight line, so a radius over-states coverage even without any barrier; the obstacle effect is only the second part of the gap",
        "A04": dec04, "A05": dec05}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"claims_summary": res["claims_summary"],
                      "A04_byte_identical": res["A04_rerun"]["byte_identical_to_stored"],
                      "A05_only_env_fields_differ": res["A05_rerun"]["only_environment_fields_differ"],
                      "decomposition_A04": {T: {k: v for k, v in d.items() if k.startswith("gap")} for T, d in dec04.items()},
                      "decomposition_A05": {T: {k: v for k, v in d.items() if k.startswith("gap")} for T, d in dec05.items()}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
