#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A05 — изолированный эксперимент. ВСЕ ДАННЫЕ SYNTHETIC. Это НЕ Шымкент.
Проверяемые предположения (методические, не о городе):
  H1. Прямое (евклидово) расстояние и расстояние по пешеходной сети с барьером
      дают разную оценку покрытия территорий.
  H2. Назначение "к ближайшей школе" без учёта вместимости скрывает дефицит мест,
      который видит назначение с ограничением вместимости (транспортная задача, LP).
  H3. Выбор места новой школы по одному лишь географическому покрытию может
      отличаться от выбора по снижению дефицита мест.
  H4. Рекомендация устойчива/неустойчива к неопределённости спроса.
  H5. Простое правило связывания названий (номер + тип + расстояние) даёт
      приемлемую точность и честно отправляет неоднозначности на ручную проверку.
Запуск: python3 A05_experiment.py  -> A05_synthetic_results.json
"""
import json, math, platform, re, sys, time
import numpy as np
import networkx as nx
import scipy
from scipy.optimize import linprog

SEED = 20261004
rng = np.random.default_rng(SEED)

# ---------------- синтетическая пешеходная сеть ----------------
N, STEP = 30, 100                       # 30x30 узлов, шаг 100 м (~2.9 x 2.9 км)
G = nx.grid_2d_graph(N, N)
nx.set_edge_attributes(G, STEP, "w")
BARRIER_COL, CROSSINGS = 14, {5, 24}    # «железная дорога» между x=14 и x=15, 2 перехода
for y in range(N):
    if y not in CROSSINGS:
        G.remove_edge((BARRIER_COL, y), (BARRIER_COL + 1, y))

# ---------------- синтетический спрос по кварталам 3x3 ----------------
blocks = []
for bx in range(10):
    for by in range(10):
        node = (3 * bx + 1, 3 * by + 1)
        base = rng.lognormal(math.log(45), 0.35)
        if bx >= 6 and by >= 6:              # «новый жилой массив»
            base *= 3.0
        terr = ("А" if node[0] <= BARRIER_COL else "Б") if node[1] < 15 else \
               ("В" if node[0] <= BARRIER_COL else "Г")
        blocks.append({"node": node, "demand": round(base, 1), "territory": terr})
D = np.array([b["demand"] for b in blocks])
TERR = np.array([b["territory"] for b in blocks])

schools = [  # (id, узел, проектная вместимость) — synthetic
    ("S1", (4, 4), 900), ("S2", (11, 11), 1200), ("S3", (22, 6), 900),
    ("S4", (5, 22), 1000), ("S5", (12, 26), 700), ("S6", (17, 17), 800)]
candidates = [("C1", (20, 20)), ("C2", (24, 24)), ("C3", (27, 27)), ("C4", (16, 26)),
              ("C5", (26, 18)), ("C6", (8, 16)), ("C7", (13, 4)), ("C8", (28, 4))]
NEW_CAP = 1000
DMAX = 1500   # допустимая дальность по сети, ПАРАМЕТР эксперимента, не норматив

def net_dist(src):
    d = nx.single_source_dijkstra_path_length(G, src, weight="w")
    return np.array([d.get(b["node"], np.inf) for b in blocks])

def euc_dist(src):
    return np.array([STEP * math.hypot(b["node"][0] - src[0], b["node"][1] - src[1]) for b in blocks])

DN = {sid: net_dist(n) for sid, n, _ in schools}
DN.update({cid: net_dist(n) for cid, n in candidates})
DE = {sid: euc_dist(n) for sid, n, _ in schools}
DE.update({cid: euc_dist(n) for cid, n in candidates})

def nearest(ids, dist):
    M = np.vstack([dist[i] for i in ids])
    return M.argmin(0), M.min(0)

def coverage(dmin, demand, T):
    return float(demand[dmin <= T].sum() / demand.sum())

def lp_assign(ids, caps, demand, dist, penalty=10_000.0, dmax=None):
    """min sum d_ij x_ij + penalty*u_i ; sum_j x_ij + u_i = D_i ; sum_i x_ij <= cap_j ;
    x_ij = 0, если d_ij > dmax (недопустимая дальность). dmax=None -> без ограничения."""
    I, J = len(demand), len(ids)
    Dm = np.vstack([dist[i] for i in ids]).T          # I x J
    c = np.concatenate([Dm.ravel(), np.full(I, penalty)])
    A_eq = np.zeros((I, I * J + I)); A_ub = np.zeros((J, I * J + I))
    for i in range(I):
        A_eq[i, i * J:(i + 1) * J] = 1; A_eq[i, I * J + i] = 1
    for j in range(J):
        A_ub[j, j:I * J:J] = 1
    ub = np.full(I * J + I, None, dtype=object)
    if dmax is not None:
        ub[:I * J] = np.where(Dm.ravel() > dmax, 0.0, None)
    bounds = [(0, b) for b in ub]
    r = linprog(c, A_ub=A_ub, b_ub=caps, A_eq=A_eq, b_eq=demand, bounds=bounds, method="highs")
    assert r.status == 0, r.message
    x = r.x[:I * J].reshape(I, J); u = r.x[I * J:]
    served = x.sum()
    return {"unmet": float(u.sum()), "mean_dist_served": float((x * Dm).sum() / served),
            "max_dist_served": float(Dm[x > 1e-6].max()), "x": x, "util": x.sum(0) / np.array(caps),
            "unmet_by_territory": {t: float(u[TERR == t].sum()) for t in "АБВГ"}}

def two_sfca(ids, caps, demand, dist, d0):
    A = np.zeros(len(demand))
    for j, sid in enumerate(ids):
        inside = dist[sid] <= d0
        pop = demand[inside].sum()
        if pop > 0:
            A[inside] += caps[j] / pop
    return A

def wgini(v, w):
    o = np.argsort(v); v, w = v[o], w[o]
    cw = np.cumsum(w); cvw = np.cumsum(v * w)
    B = (cvw / cvw[-1]); Wn = cw / cw[-1]
    return float(1 - np.sum((Wn - np.concatenate([[0], Wn[:-1]])) * (B + np.concatenate([[0], B[:-1]]))))

def terr_mean(vals, demand):
    return {t: float((vals[TERR == t] * demand[TERR == t]).sum() / demand[TERR == t].sum()) for t in "АБВГ"}

def evaluate(ids, caps, demand, T=1000, d0=1500):
    _, dmin_n = nearest(ids, DN); lp = lp_assign(ids, caps, demand, DN, dmax=DMAX)
    A = two_sfca(ids, caps, demand, DN, d0); tm = terr_mean(A, demand)
    return {"unmet_lp": lp["unmet"], "mean_dist_lp": lp["mean_dist_served"], "unmet_by_territory": lp["unmet_by_territory"],
            "cov_net_T": coverage(dmin_n, demand, T),
            "terr_min_over_max_2sfca": min(tm.values()) / max(tm.values()),
            "gini_2sfca": wgini(A, demand), "terr_2sfca": tm, "_lp": lp}

out = {"meta": {"kind": "synthetic", "seed": SEED, "python": sys.version.split()[0],
                "numpy": np.__version__, "scipy": scipy.__version__, "networkx": nx.__version__,
                "platform": platform.platform(), "note": "Все входы синтетические; выводы — только о методе."}}
t0 = time.time()
ids0 = [s[0] for s in schools]; caps0 = [s[2] for s in schools]
out["inputs"] = {"total_demand": float(D.sum()), "total_capacity": float(sum(caps0)),
                 "demand_by_territory": {t: float(D[TERR == t].sum()) for t in "АБВГ"},
                 "grid": f"{N}x{N} nodes, {STEP} m", "barrier": "между x=14 и x=15, переходы y=5 и y=24",
                 "schools": [{"id": s, "node": n, "cap": c} for s, n, c in schools],
                 "candidates": [{"id": c, "node": n} for c, n in candidates], "new_cap": NEW_CAP}

# ---- H1: евклид против сети ----
_, dmin_n = nearest(ids0, DN); _, dmin_e = nearest(ids0, DE)
h1 = {}
for T in (500, 1000, 1500):
    mis = (dmin_e <= T) & (dmin_n > T)
    h1[str(T)] = {"cov_euclid": coverage(dmin_e, D, T), "cov_network": coverage(dmin_n, D, T),
                  "demand_wrongly_covered_by_euclid": float(D[mis].sum()),
                  "by_territory_network": {t: coverage(dmin_n[TERR == t], D[TERR == t], T) for t in "АБВГ"},
                  "by_territory_euclid": {t: coverage(dmin_e[TERR == t], D[TERR == t], T) for t in "АБВГ"}}
out["H1_euclid_vs_network"] = h1

# ---- H2: ближайшая школа без вместимости против LP ----
arg_n, _ = nearest(ids0, DN)
load = np.array([D[arg_n == j].sum() for j in range(len(ids0))])
over = np.maximum(0, load - np.array(caps0))
lp0 = lp_assign(ids0, caps0, D, DN)
lp0d = lp_assign(ids0, caps0, D, DN, dmax=DMAX)
prim_lp = lp0["x"].argmax(1)
changed = prim_lp != arg_n
out["H2_capacity"] = {
    "nearest_rule_load_vs_cap": {ids0[j]: {"load": float(load[j]), "cap": caps0[j],
                                            "overflow": float(over[j])} for j in range(len(ids0))},
    "nearest_rule_total_overflow": float(over.sum()),
    "lp_unmet_seats": lp0["unmet"], "lp_mean_dist_served_m": lp0["mean_dist_served"],
    "lp_max_dist_served_m": lp0["max_dist_served"],
    "lp_utilization": {ids0[j]: float(lp0["util"][j]) for j in range(len(ids0))},
    "lp_dmax_unmet_seats": lp0d["unmet"], "lp_dmax_unmet_by_territory": lp0d["unmet_by_territory"],
    "lp_dmax_mean_dist_served_m": lp0d["mean_dist_served"], "dmax_m": DMAX,
    "global_deficit_demand_minus_capacity": float(D.sum() - sum(caps0)),
    "rezoning_blocks_changed": int(changed.sum()), "rezoning_demand_changed": float(D[changed].sum()),
    "note": "LP распределяет спрос с учётом мест; блоки с изменённой основной школой = сценарий изменения зон."}

# ---- H3: размещение одной новой школы ----
base = evaluate(ids0, caps0, D)
rows = []
for cid, _ in candidates:
    e = evaluate(ids0 + [cid], caps0 + [NEW_CAP], D)
    rows.append({"candidate": cid, "unmet_lp": e["unmet_lp"], "unmet_by_territory": e["unmet_by_territory"], "mean_dist_lp": e["mean_dist_lp"],
                 "cov_net_1000": e["cov_net_T"], "terr_min_over_max_2sfca": e["terr_min_over_max_2sfca"],
                 "gini_2sfca": e["gini_2sfca"]})
best_opt = min(rows, key=lambda r: (round(r["unmet_lp"], 1), r["mean_dist_lp"]))["candidate"]
best_geo = max(rows, key=lambda r: r["cov_net_1000"])["candidate"]
best_equity = max(rows, key=lambda r: r["terr_min_over_max_2sfca"])["candidate"]
# наивный baseline: территория с наименьшим числом мест на ребёнка, кандидат ближе всего (евклид) к её центроиду спроса
seats_per_child = {}
for t in "АБВГ":
    seats_per_child[t] = sum(c for s, n, c in schools if
                             (("А" if n[0] <= BARRIER_COL else "Б") if n[1] < 15 else ("В" if n[0] <= BARRIER_COL else "Г")) == t) / D[TERR == t].sum()
worst_t = min(seats_per_child, key=seats_per_child.get)
m = TERR == worst_t
cx = (np.array([b["node"][0] for b in blocks])[m] * D[m]).sum() / D[m].sum()
cy = (np.array([b["node"][1] for b in blocks])[m] * D[m]).sum() / D[m].sum()
best_naive = min(candidates, key=lambda c: math.hypot(c[1][0] - cx, c[1][1] - cy))[0]
from scipy.stats import spearmanr
rho = spearmanr([r["cov_net_1000"] for r in rows], [-r["unmet_lp"] for r in rows]).statistic
out["H3_placement"] = {"spearman_geo_coverage_vs_minus_unmet": float(rho),"baseline_no_build": {k: v for k, v in base.items() if k != "_lp"},
                       "candidates": rows, "pick_min_unmet_then_distance": best_opt,
                       "pick_max_geographic_coverage_1000m": best_geo,
                       "pick_max_territorial_equity_2sfca": best_equity,
                       "pick_naive_worst_territory_centroid": best_naive,
                       "naive_rule": f"территория {worst_t} (мест на ребёнка {seats_per_child[worst_t]:.3f}), центроид спроса ({cx:.1f},{cy:.1f})"}

# ---- H4: чувствительность к спросу ----
S = 200
wins = {c: 0 for c, _ in candidates}
in_best = {c: 0 for c, _ in candidates}
regret_c1 = []
regret_geo, regret_naive, ties = [], [], 0
for s_ in range(S):
    Ds = D * rng.lognormal(0, 0.25, size=len(D)) * rng.uniform(0.9, 1.3)
    full = {cid: lp_assign(ids0 + [cid], caps0 + [NEW_CAP], Ds, DN, dmax=DMAX) for cid, _ in candidates}
    res = {cid: round(v["unmet"], 1) for cid, v in full.items()}
    best_u = min(res.values())
    tied = [c for c in res if res[c] == best_u]
    if len(tied) > 1: ties += 1
    for c in tied: in_best[c] += 1
    regret_c1.append(res["C1"] - best_u)
    b = min(tied, key=lambda c: full[c]["mean_dist_served"]); wins[b] += 1
    regret_geo.append(res[best_geo] - best_u); regret_naive.append(res[best_naive] - best_u)
out["H4_sensitivity"] = {"scenarios": S, "dmax_m": DMAX, "scenarios_with_tie_on_unmet": ties,
                         "tie_break": "при равном числе непокрытых мест — меньшее среднее расстояние", "demand_noise": "lognormal(0,0.25) по кварталам x общий рост U(0.9,1.3)",
                         "best_candidate_frequency": {k: v / S for k, v in wins.items() if v},
                         "in_best_tied_set_frequency": {k: v / S for k, v in in_best.items()},
                         "regret_unmet_seats_if_C1": {"median": float(np.median(regret_c1)), "p90": float(np.percentile(regret_c1, 90))},
                         "regret_unmet_seats_if_geo_pick": {"median": float(np.median(regret_geo)), "p90": float(np.percentile(regret_geo, 90))},
                         "regret_unmet_seats_if_naive_pick": {"median": float(np.median(regret_naive)), "p90": float(np.percentile(regret_naive, 90))}}

# ---- H5: связывание названий (synthetic) ----
NUM_RE = re.compile(r"(?:№|N°|No\.?|#)\s*(\d{1,3})|\b(\d{1,3})\s*(?:-?\s*(?:ші|шы|сы|сі|інші|ыншы))?\s*(?:мектеп|школ|бала|ясли|сад)", re.I)
def norm(s):
    s = s.lower().replace("ё", "е").replace("«", " ").replace("»", " ").replace('"', " ")
    return " ".join(s.split())
def kind(s):
    s = norm(s)
    if re.search(r"сад|балабақша|бөбекжай|ясли|kindergarten", s): return "kg"
    if re.search(r"школ|мектеп|гимназ|лице|school", s): return "school"
    return "unknown"
NUM_RE2 = re.compile(r"(?:школ\w*|лице\w*|гимнази\w*|мектеп\w*|сад\w*|балабақша\w*)\s+(\d{1,3})\b", re.I)
def number(s):
    m = NUM_RE.search(norm(s))
    if m: return int(m.group(1) or m.group(2))
    m = NUM_RE2.search(norm(s))
    return int(m.group(1)) if m else None
def toks(s):
    stop = {"кгу", "гкп", "на", "пхв", "коммунальное", "государственное", "учреждение", "управления",
            "образования", "города", "шымкент", "шымкент", "қаласы", "білім", "басқармасының", "ко", "имени", "атындағы"}
    return {t for t in re.findall(r"[a-zа-яәіңғүұқөһ]+", norm(s)) if t not in stop and len(t) > 2}
def match(reg, osm, auto_m=300, review_m=1000):
    """Возвращает (reg_id, osm_id|REVIEW|None, правило). Авто — только при однозначном совпадении."""
    out_ = []
    for r in reg:
        auto, review = [], []
        kr, nr = kind(r["name"]), number(r["name"])
        for o in osm:
            ko, no = kind(o["name"]), number(o["name"])
            if "unknown" not in (kr, ko) and kr != ko: continue        # школа != детсад
            d = math.hypot(r["x"] - o["x"], r["y"] - o["y"])
            a, b = toks(r["name"]), toks(o["name"])
            jac = len(a & b) / len(a | b) if a and b else 0.0
            if nr is not None and nr == no:
                (auto if d <= auto_m and kr == ko else review).append((o["id"], d)) if d <= review_m else None
            elif nr is not None and no is not None:
                continue                                                 # разные номера
            elif nr is None and no is None and jac >= 0.5 and d <= 150:
                (auto if kr == ko else review).append((o["id"], d))
            elif d <= 100:                                               # номер только у одной стороны
                review.append((o["id"], d))
        if len(auto) == 1 and not review: out_.append((r["id"], auto[0][0], "auto"))
        elif auto or review: out_.append((r["id"], "REVIEW", ";".join(f"{i}@{d:.0f}м" for i, d in auto + review)))
        else: out_.append((r["id"], None, "нет кандидата"))
    return out_
REG = [  # синтетический «реестр»; координаты в метрах
    {"id": "R1", "name": "КГУ «Общеобразовательная школа № 45» управления образования города Шымкент", "x": 1000, "y": 1000},
    {"id": "R2", "name": "Школа-гимназия №12", "x": 2000, "y": 500},
    {"id": "R3", "name": "Ясли-сад № 12", "x": 2050, "y": 520},
    {"id": "R4", "name": "№ 7 жалпы білім беретін мектеп", "x": 300, "y": 2500},
    {"id": "R5", "name": "Средняя школа № 7", "x": 2800, "y": 2800},
    {"id": "R6", "name": "Частная школа «Альфа»", "x": 1500, "y": 1500},
    {"id": "R7", "name": "Школа-лицей № 101", "x": 500, "y": 500},
    {"id": "R8", "name": "Общеобразовательная школа № 64", "x": 2600, "y": 1200},
    {"id": "R9", "name": "Детский сад «Тестовый»", "x": 900, "y": 2100},
    {"id": "R10", "name": "Школа № 33", "x": 1800, "y": 2400}]
OSM = [  # синтетические «точки OSM»: разные написания, смещения, ловушки
    {"id": "O1", "name": "Школа №45", "x": 1080, "y": 960},
    {"id": "O2", "name": "Мектеп-гимназия № 12", "x": 1990, "y": 470},
    {"id": "O3", "name": "Балабақша №12", "x": 2070, "y": 530},
    {"id": "O4", "name": "7 мектеп", "x": 340, "y": 2560},
    {"id": "O5", "name": "Школа № 7", "x": 2780, "y": 2850},
    {"id": "O6", "name": "Альфа", "x": 1520, "y": 1490},
    {"id": "O7", "name": "Лицей 101", "x": 900, "y": 900},          # смещена на ~570 м
    {"id": "O8", "name": "Школа № 64", "x": 2610, "y": 1190},
    {"id": "O8b", "name": "Школа № 64 (корпус 2)", "x": 2700, "y": 1250},
    {"id": "O10", "name": "Школа", "x": 1800, "y": 2410}]          # без номера
TRUTH = {"R1": "O1", "R2": "O2", "R3": "O3", "R4": "O4", "R5": "O5", "R6": "O6", "R7": "O7", "R8": "O8", "R9": None, "R10": "O10"}
res = match(REG, OSM)
auto = [(r, o) for r, o, _ in res if o not in (None, "REVIEW")]
correct = sum(1 for r, o in auto if TRUTH[r] == o)
out["H5_name_matching"] = {"results": [{"reg": r, "osm": o, "rule": why, "truth": TRUTH[r]} for r, o, why in res],
                           "auto_matches": len(auto), "auto_correct": correct,
                           "precision_auto": correct / len(auto) if auto else None,
                           "recall_auto_vs_truth": correct / sum(1 for v in TRUTH.values() if v),
                           "sent_to_review": sum(1 for _, o, _ in res if o == "REVIEW"),
                           "review_contains_truth": sum(1 for r, o, why in res if o == "REVIEW" and TRUTH[r] and TRUTH[r] + "@" in why),
                           "false_auto": sum(1 for r, o in auto if TRUTH[r] != o),
                           "note": "Синтетический тест из 10 записей; показывает поведение правил, не точность на реальных данных."}
out["meta"]["runtime_s"] = round(time.time() - t0, 2)

def clean(o):
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items() if k != "_lp"}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)): return round(float(o), 4)
    if isinstance(o, np.integer): return int(o)
    return o
json.dump(clean(out), open("A05_synthetic_results.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(clean({k: out[k] for k in ("inputs", "H1_euclid_vs_network", "H2_capacity")}), ensure_ascii=False, indent=1)[:4000])
print(json.dumps(clean({k: out[k] for k in ("H3_placement", "H4_sensitivity", "H5_name_matching")}), ensure_ascii=False, indent=1))
print("runtime_s", out["meta"]["runtime_s"])
