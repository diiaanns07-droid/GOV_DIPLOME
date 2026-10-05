# -*- coding: utf-8 -*-
"""
A04 — СИНТЕТИЧЕСКИЙ эксперимент (kind=synthetic). Данных Шымкента здесь НЕТ.
Проверяет критические допущения MVP доступности:
  H1. Прямой радиус завышает пешеходную доступность при барьерах (ж/д, канал, промзона).
  H2. Агрегат «район целиком» маскирует провал в отдельном микрорайоне.
  H3. Ранжирование 2–3 участков под новый объект может зависеть от метрики (радиус vs сеть).
Город-игрушка 2x2 км, улицы-решётка 50 м, барьер по y=1000..1050 с 2 переходами,
закрытая промзона без прохода. Всё детерминировано (seed=42).
Запуск: python3 A04_synthetic_experiment.py > A04_synthetic_results.json
"""
import json, math
import numpy as np
import networkx as nx

STEP, SIZE = 50, 2000
SEED = 42
rng = np.random.default_rng(SEED)

coords = [(x, y) for x in range(0, SIZE + 1, STEP) for y in range(0, SIZE + 1, STEP)]
G = nx.Graph()
INDUSTRIAL = lambda x, y: 1300 <= x <= 1700 and 200 <= y <= 600     # закрытая промзона
for (x, y) in coords:
    if INDUSTRIAL(x, y):
        continue
    G.add_node((x, y))
for (x, y) in list(G.nodes):
    for dx, dy in ((STEP, 0), (0, STEP)):
        n2 = (x + dx, y + dy)
        if n2 not in G:
            continue
        # барьер между рядами y=1000 и y=1050; переходы только при x=400 и x=1600
        if dy and y == 1000 and x not in (400, 1600):
            continue
        G.add_edge((x, y), n2, length=STEP)

def quadrant(x, y):
    return ("N" if y > 1000 else "S") + ("W" if x <= 1000 else "E")

# Население: многоэтажка на севере, частный сектор на юге (меньше плотность)
DENS = {"NW": 120, "NE": 90, "SW": 45, "SE": 35}
pop = {n: float(rng.gamma(2.0, DENS[quadrant(*n)] / 2.0)) for n in G.nodes}

FAC = [(500, 1500), (1500, 1500), (600, 700)]
CAND = {"A": (1500, 950), "B": (1200, 150), "C": (1850, 750)}

def eucl_nearest(n, facs):
    return min(math.dist(n, f) for f in facs)

def net_dist(facs):
    return nx.multi_source_dijkstra_path_length(G, list(facs), weight="length")

def coverage(threshold, facs):
    nd = net_dist(facs)
    rows = []
    for n, p in pop.items():
        e = eucl_nearest(n, facs)
        d = nd.get(n, math.inf)
        rows.append((n, p, e, d))
    total = sum(r[1] for r in rows)
    out = {"threshold_m": threshold, "total_pop": round(total)}
    out["covered_share_euclid"] = round(sum(p for _, p, e, _ in rows if e <= threshold) / total, 4)
    out["covered_share_network"] = round(sum(p for _, p, _, d in rows if d <= threshold) / total, 4)
    out["false_covered_share"] = round(sum(p for _, p, e, d in rows if e <= threshold < d) / total, 4)
    by_q = {}
    for q in ("NW", "NE", "SW", "SE"):
        sub = [r for r in rows if quadrant(*r[0]) == q]
        t = sum(r[1] for r in sub)
        by_q[q] = {"pop": round(t),
                   "covered_share_network": round(sum(p for _, p, _, d in sub if d <= threshold) / t, 4),
                   "covered_share_euclid": round(sum(p for _, p, e, _ in sub if e <= threshold) / t, 4)}
    out["by_microdistrict"] = by_q
    ratios = [d / e for _, _, e, d in rows if e > 100 and d < math.inf]
    out["detour_ratio_p50_p90_max"] = [round(float(np.percentile(ratios, q)), 3) for q in (50, 90, 100)]
    return out, rows

def site_comparison(threshold):
    _, base = coverage(threshold, FAC)
    base_net = {n: d for n, _, _, d in base}
    base_eu = {n: e for n, _, e, _ in base}
    res = {}
    for k, c in CAND.items():
        nd_new = nx.single_source_dijkstra_path_length(G, c, weight="length")
        gain_net = sum(p for n, p in pop.items()
                       if base_net[n] > threshold and nd_new.get(n, math.inf) <= threshold)
        gain_eu = sum(p for n, p in pop.items()
                      if base_eu[n] > threshold and math.dist(n, c) <= threshold)
        # средневзвешенное сетевое расстояние до ближайшего объекта после добавления
        after = {n: min(base_net[n], nd_new.get(n, math.inf)) for n in pop}
        mean_after = sum(pop[n] * after[n] for n in pop) / sum(pop.values())
        res[k] = {"site": c, "new_covered_pop_network": round(gain_net),
                  "new_covered_pop_euclid": round(gain_eu),
                  "pop_weighted_mean_net_dist_after_m": round(mean_after)}
    rank_net = sorted(res, key=lambda k: -res[k]["new_covered_pop_network"])
    rank_eu = sorted(res, key=lambda k: -res[k]["new_covered_pop_euclid"])
    return {"threshold_m": threshold, "sites": res,
            "rank_by_network": rank_net, "rank_by_euclid": rank_eu,
            "ranking_differs": rank_net != rank_eu}

if __name__ == "__main__":
    results = {"kind": "synthetic", "seed": SEED,
               "versions": {"networkx": nx.__version__, "numpy": np.__version__},
               "graph": {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
                         "step_m": STEP, "barrier": "y=1000..1050, crossings x=400,1600",
                         "industrial_block": "x1300-1700,y200-600, no passage"},
               "facilities": FAC, "candidates": CAND,
               "coverage": [coverage(t, FAC)[0] for t in (500, 800, 1000)],
               "site_comparison": [site_comparison(t) for t in (500, 800)]}
    print(json.dumps(results, ensure_ascii=False, indent=1))
