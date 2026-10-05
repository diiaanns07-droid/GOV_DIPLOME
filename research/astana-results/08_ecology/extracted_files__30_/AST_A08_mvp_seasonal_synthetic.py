"""AST-A08 — синтетический эксперимент MVP для Астаны. ВСЕ СЛОИ SYNTHETIC; описывают метод, не город.

Астана-специфичный вопрос: годится ли ОДИН индекс на весь год, если летом проблема — жара и дефицит
тени, а зимой — эпизоды загрязнения в отопительный сезон? Сравниваем летний индекс озеленения G и
зимний индекс обследования W, их смесь, чувствительность к весам, к пропускам LST и к отказу постов.

Запуск: python3 AST_A08_mvp_seasonal_synthetic.py  (рядом должен лежать eco_priority_core.py)
Проверено: Python 3.12.3, numpy 2.4.4, scipy 1.17.1. Результат: AST_A08_mvp_results_synthetic.json
"""
import json, os, sys
import numpy as np
from scipy import ndimage
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eco_priority_core import prank, score, topk, jacc, weight_sensitivity, fill_neighbors, access_distance, greedy_max_cover

SEED = 7
rng = np.random.default_rng(SEED)
N, CELL = 100, 100.0
yy, xx = np.mgrid[0:N, 0:N]
cx, cy = (xx + 0.5) * CELL, (yy + 0.5) * CELL


def smooth(sig):
    f = ndimage.gaussian_filter(rng.normal(size=(N, N)), sig)
    return (f - f.min()) / (f.max() - f.min())


# --- синтетические слои (Астана-подобная структура: плотный центр + периферийные массивы малоэтажки)
center = np.exp(-(((xx - 45) ** 2 + (yy - 50) ** 2) / (2 * 25 ** 2)))
built = np.clip(0.6 * center + 0.4 * smooth(6), 0, 1)
river = np.abs(yy - (50 + 8 * np.sin(xx / 15))) < 2                        # пойма: без жителей
lowrise = np.zeros((N, N))
for (x0, y0) in [(12, 20), (80, 15), (85, 80), (20, 85)]:                  # массивы частного сектора (гипотетические)
    lowrise += np.exp(-(((xx - x0) ** 2 + (yy - y0) ** 2) / (2 * 7 ** 2)))
lowrise = np.clip(lowrise, 0, 1)
pop = rng.poisson(np.where(river, 0, 1 + 50 * built ** 2 + 15 * lowrise)).astype(float)
P = (pop > 0).ravel()
veg = np.clip(0.55 * (1 - built) + 0.3 * smooth(3) + 0.3 * river, 0, 1)
lst = 34 + 8 * built - 6 * veg + 1.0 * rng.normal(size=(N, N))            # «поверхность», °C
rec = np.zeros((N, N)); np.add.at(rec.ravel(), rng.choice(N * N, 100, replace=False, p=(pop / pop.sum()).ravel()), 1)
n_parks = 20
pk_x, pk_y = rng.uniform(500, 9500, n_parks), rng.uniform(500, 9500, n_parks)
pk_a = np.round(rng.lognormal(0.4, 1.1, n_parks), 2); pk_pub = rng.random(n_parks) < 0.85
dist_green = access_distance(cx, cy, pk_x, pk_y, pk_a, pk_pub)
posts = np.array([[3000, 4000], [5500, 5200], [4500, 7000], [7000, 3000], [2500, 6500], [6000, 8000]])  # 6 постов


def mon_gap(active):
    p = posts[active]
    return np.hypot(cx[..., None] - p[:, 0], cy[..., None] - p[:, 1]).min(-1)


K = int(round(0.05 * P.sum()))
G_NAMES = ["heat", "veg_deficit", "access_deficit", "population", "receptors"]
G_W = [0.35, 0.20, 0.15, 0.20, 0.10]
W_NAMES = ["lowrise", "population", "receptors", "monitoring_gap"]
W_W = [0.40, 0.30, 0.15, 0.15]


def compG(lst_map):
    return {"heat": prank(lst_map - np.nanmedian(lst_map[pop > 0]), P), "veg_deficit": prank(1 - veg, P),
            "access_deficit": prank(np.minimum(dist_green, 3000), P), "population": prank(pop, P), "receptors": prank(rec, P)}


def compW(active=np.ones(6, bool)):
    return {"lowrise": prank(lowrise, P), "population": prank(pop, P), "receptors": prank(rec, P), "monitoring_gap": prank(mon_gap(active), P)}


cG, cW = compG(lst), compW()
sG, sW = score(cG, G_NAMES, G_W, P), score(cW, W_NAMES, W_W, P)
TG, TW = topk(sG, K), topk(sW, K)
blend = 0.5 * sG + 0.5 * sW
TB = topk(blend, K)
season = {"jaccard_summerG_vs_winterW": round(jacc(TG, TW), 3),
          "blend_keeps_share_of_summer_topK": round(len(TB & TG) / K, 3),
          "blend_keeps_share_of_winter_topK": round(len(TB & TW) / K, 3),
          "random_expected_jaccard": round(K / (2 * P.sum() - K), 4)}

sens = {"G_moderate": weight_sensitivity(cG, G_NAMES, G_W, P, K, rng, 20, 1000),
        "G_any_weights": weight_sensitivity(cG, G_NAMES, G_W, P, K, rng, None, 1000),
        "W_moderate": weight_sensitivity(cW, W_NAMES, W_W, P, K, rng, 20, 1000),
        "W_any_weights": weight_sensitivity(cW, W_NAMES, W_W, P, K, rng, None, 1000)}

# Пропуски LST пятнами (облака/полосы) и отказ постов (реальная проблема полноты рядов)
miss = {}
for frac in (0.1, 0.3):
    js_n, js_r = [], []
    for _ in range(5):
        f = ndimage.gaussian_filter(rng.normal(size=(N, N)), 8); m = f > np.quantile(f, 1 - frac)
        lm = np.where(m, np.nan, lst)
        js_n.append(jacc(topk(score(compG(fill_neighbors(lm)), G_NAMES, G_W, P), K), TG))
        js_r.append(jacc(topk(score(compG(lm), G_NAMES, G_W, P), K), TG))
    miss[f"LST_clustered_{int(frac*100)}pct"] = {"neighbors": round(float(np.mean(js_n)), 3), "renormalize": round(float(np.mean(js_r)), 3)}
outage = []
for drop in [(1,), (0, 3), (1, 2, 4)]:
    act = np.ones(6, bool); act[list(drop)] = False
    outage.append({"posts_down": list(drop), "jaccard_W": round(jacc(topk(score(compW(act), W_NAMES, W_W, P), K), TW), 3)})
miss["post_outage"] = outage

# --- Сценарии
hot = (pop > 0) & (lst >= np.quantile(lst[pop > 0], 0.9))
treated = np.zeros(N * N, bool); treated[list(TG)] = True; treated = treated.reshape(N, N)
s1 = {"label": "S1 летние посадки/тень в топ-5% G — ОХВАТ, не эффект",
      "pop_share_in_treated": round(float(pop[treated].sum() / pop.sum()), 4),
      "hot_decile_pop_covered": round(float(pop[treated & hot].sum() / pop[hot].sum()), 4),
      "survival_note": "доля приживаемости — параметр-гипотеза {0.6; 0.8; 0.95}; ожидаемый охват кроной = охват × приживаемость; местных данных нет",
      "expected_canopy_coverage_by_survival": {str(s): round(float(pop[treated].sum() / pop.sum() * s), 4) for s in (0.6, 0.8, 0.95)}}
n_c = 50
free = np.argwhere((pop > 0)); pick = free[rng.choice(len(free), n_c, replace=False)]
cand_x, cand_y, cand_a = (pick[:, 1] + .5) * CELL, (pick[:, 0] + .5) * CELL, np.round(rng.uniform(0.5, 2.0, n_c), 2)


def a300(sel):
    d = access_distance(cx, cy, np.r_[pk_x, cand_x[sel]], np.r_[pk_y, cand_y[sel]], np.r_[pk_a, cand_a[sel]], np.r_[pk_pub, np.ones(len(sel), bool)])
    return float(pop[d <= 300].sum() / pop.sum())


g = greedy_max_cover(5, n_c, a300)
hot_sel = list(np.argsort(-lst[pick[:, 0], pick[:, 1]])[:5])
s2 = {"label": "S2 5 скверов >=0.5 га (геометрия; при условии, что построены, публичны и прижились)",
      "a300_base": round(a300([]), 4), "greedy": round(a300(g), 4), "hottest": round(a300(hot_sel), 4),
      "random_mean_100": round(float(np.mean([a300(list(rng.choice(n_c, 5, replace=False))) for _ in range(100)])), 4)}
# S3: +4 недорогих датчика — размещение по площади против размещения по населению
cg = np.argwhere(np.ones((10, 10), bool)) * 1000 + 500                     # кандидаты: сетка 1 км
cur = mon_gap(np.ones(6, bool))


def cov(sel, wts):
    if not sel:
        d = cur
    else:
        p = cg[sel]; d = np.minimum(cur, np.hypot(cx[..., None] - p[:, 1], cy[..., None] - p[:, 0]).min(-1))
    return float(wts[d <= 2000].sum() / wts.sum())


area_w, pop_w = np.ones((N, N)), pop
sel_area = greedy_max_cover(4, len(cg), lambda s: cov(s, area_w))
sel_pop = greedy_max_cover(4, len(cg), lambda s: cov(s, pop_w))
s3 = {"label": "S3 +4 датчика PM2.5: информационный эффект (покрытие 2 км), не снижение загрязнения",
      "pop_within_2km_now": round(cov([], pop_w), 4),
      "pop_within_2km_area_weighted_siting": round(cov(sel_area, pop_w), 4),
      "pop_within_2km_pop_weighted_siting": round(cov(sel_pop, pop_w), 4)}

res = {"kind": "synthetic", "seed": SEED, "grid": "100x100 x 100 m", "populated_cells": int(P.sum()), "top_k": K,
       "weights": {"G": dict(zip(G_NAMES, G_W)), "W": dict(zip(W_NAMES, W_W))},
       "seasonal_overlap": season, "sensitivity_weights": sens, "sensitivity_missing": miss,
       "scenarios": {"S1": s1, "S2": s2, "S3": s3}}
print(json.dumps(res, ensure_ascii=False, indent=1))
json.dump(res, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "AST_A08_mvp_results_synthetic.json"), "w"), ensure_ascii=False, indent=1)
