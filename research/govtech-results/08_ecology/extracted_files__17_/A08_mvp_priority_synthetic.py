"""A08 — изолированный эксперимент MVP «где обследовать / где озеленять». ВСЕ ДАННЫЕ SYNTHETIC.

Цель: проверить МЕТОД (без нейросети), а не Шымкент. Ни одно число отсюда не описывает город.
Проверяется: (1) воспроизводимый индикатор доступности зелени; (2) индекс приоритета на
перцентильных рангах; (3) baseline; (4) чувствительность к весам и пропускам; (5) 3 сценария.

Запуск: python3 A08_mvp_priority_synthetic.py  -> печатает JSON и пишет A08_mvp_results_synthetic.json
Зависимости: numpy, scipy (проверено: numpy 2.4.4, scipy 1.17.1, Python 3.12.3).
"""
import json
import numpy as np
from scipy import ndimage
from scipy.stats import rankdata

SEED = 42
rng = np.random.default_rng(SEED)
N, CELL = 100, 100.0                      # 100x100 ячеек по 100 м = 10x10 км (как сетка GHSL/WorldPop)
yy, xx = np.mgrid[0:N, 0:N]
cx, cy = (xx + 0.5) * CELL, (yy + 0.5) * CELL   # центроиды, м


def smooth(sigma):
    f = ndimage.gaussian_filter(rng.normal(size=(N, N)), sigma)
    return (f - f.min()) / (f.max() - f.min())


# ---------- 1. Синтетические слои «наблюдения» ----------
center = np.exp(-(((xx - 50) ** 2 + (yy - 55) ** 2) / (2 * 28 ** 2)))
built = np.clip(0.55 * center + 0.45 * smooth(6), 0, 1)
industrial = (xx > 72) & (yy < 25)                      # промзона: без жителей
pop = rng.poisson(lam=np.where(industrial, 0, 1 + 60 * built ** 2)).astype(float)

n_parks = 25
pk_x, pk_y = rng.uniform(500, 9500, n_parks), rng.uniform(500, 9500, n_parks)
pk_area_ha = np.round(rng.lognormal(mean=0.3, sigma=1.1, size=n_parks), 2)
pk_public = rng.random(n_parks) < 0.8
veg = np.clip(0.6 * (1 - built) + 0.25 * smooth(3), 0, 1)
for x0, y0, a in zip(pk_x, pk_y, pk_area_ha):
    r = np.sqrt(a * 1e4 / np.pi)
    veg = np.where(np.hypot(cx - x0, cy - y0) <= max(r, 60), np.maximum(veg, 0.75), veg)
lst = 36 + 9 * built - 7 * veg + 1.2 * rng.normal(size=(N, N)) + np.where(industrial, 4, 0)  # «поверхность», °C

rec = np.zeros((N, N))                                  # школы/сады/поликлиники
idx = rng.choice(N * N, size=120, replace=False, p=(pop / pop.sum()).ravel())
np.add.at(rec.ravel(), idx, 1)

populated = pop > 0
P = populated.ravel()


# ---------- 2. Воспроизводимый индикатор: доступ к зелени ----------
def access_distance(px, py, area, public, min_ha=0.5):
    """Расстояние от центроида ячейки до края ближайшего публичного зелёного участка >= min_ha.
    Край аппроксимирован кругом равной площади: d = max(0, d_центр - sqrt(A/pi))."""
    ok = public & (area >= min_ha)
    if not ok.any():
        return np.full((N, N), np.inf)
    d = np.hypot(cx[..., None] - px[ok], cy[..., None] - py[ok]) - np.sqrt(area[ok] * 1e4 / np.pi)
    return np.clip(d, 0, None).min(axis=-1)


def share_within(dist, m):
    return float(pop[dist <= m].sum() / pop.sum())


dist0 = access_distance(pk_x, pk_y, pk_area_ha, pk_public)
access = {"share_pop_within_300m": round(share_within(dist0, 300), 4),
          "share_pop_within_500m": round(share_within(dist0, 500), 4),
          "parks_total": n_parks, "parks_counted_public_ge_0_5ha": int((pk_public & (pk_area_ha >= 0.5)).sum())}


# ---------- 3. Индекс приоритета озеленения ----------
def prank(v, mask=P):
    """Перцентильный ранг 0..1 среди жилых ячеек; NaN остаётся NaN."""
    out = np.full(v.size, np.nan)
    m = mask & ~np.isnan(v)
    out[m] = (rankdata(v[m], method="average") - 1) / max(m.sum() - 1, 1)
    return out


def components(lst_map):
    return {"heat": prank((lst_map - np.nanmedian(lst_map[populated])).ravel()),
            "veg_deficit": prank((1 - veg).ravel()),
            "access_deficit": prank(np.minimum(dist0, 3000).ravel()),
            "population": prank(pop.ravel()),
            "receptors": prank(rec.ravel())}


NAMES = ["heat", "veg_deficit", "access_deficit", "population", "receptors"]
W_BASE = np.array([0.35, 0.20, 0.15, 0.20, 0.10])  # политический выбор для обсуждения, НЕ истина


def score(comp, w, renorm_missing=True):
    M = np.vstack([comp[n] for n in NAMES]).T          # cells x 5
    W = np.broadcast_to(w, M.shape).copy()
    miss = np.isnan(M)
    if renorm_missing:
        W[miss] = 0
        M = np.where(miss, 0, M)
        s = (M * W).sum(1) / np.where(W.sum(1) > 0, W.sum(1), np.nan)
    else:
        s = (np.where(miss, 0, M) * W).sum(1)
    s[~P] = np.nan
    return s


K = int(round(0.05 * P.sum()))                         # топ-5% жилых ячеек


def topk(s, k=K):
    s2 = np.where(np.isnan(s), -np.inf, s)
    return set(np.argpartition(-s2, k)[:k].tolist())


def jacc(a, b):
    return len(a & b) / len(a | b)


comp0 = components(lst)
s_base = score(comp0, W_BASE)
T_base = topk(s_base)

baselines = {
    "heat_only_vs_index": round(jacc(topk(comp0["heat"] * np.where(P, 1, np.nan)), T_base), 3),
    "equal_weights_vs_index": round(jacc(topk(score(comp0, np.full(5, 0.2))), T_base), 3),
    "random_expected_jaccard": round(K / (2 * P.sum() - K), 4),
}

# ---------- 4a. Чувствительность к весам ----------
def weight_sensitivity(alpha_scale, n=2000):
    J, freq = [], np.zeros(N * N)
    for _ in range(n):
        w = rng.dirichlet(alpha_scale * W_BASE if alpha_scale else np.ones(5))
        T = topk(score(comp0, w))
        J.append(jacc(T, T_base))
        freq[list(T)] += 1
    freq /= n
    core = [c for c in T_base if freq[c] >= 0.8]
    return {"median_jaccard": round(float(np.median(J)), 3), "p10_jaccard": round(float(np.percentile(J, 10)), 3),
            "core_share_of_base_topk_in_80pct_draws": round(len(core) / K, 3)}


sens_weights = {"moderate_perturbation_alpha=20*w": weight_sensitivity(20),
                "uninformed_any_weights_alpha=1": weight_sensitivity(0)}


# ---------- 4b. Чувствительность к пропускам LST ----------
def make_mask(frac, clustered):
    if not clustered:
        return rng.random((N, N)) < frac
    f = ndimage.gaussian_filter(rng.normal(size=(N, N)), 8)
    return f > np.quantile(f, 1 - frac)               # «облака»/полосы: пропуски пятнами


def fill(lst_m, how):
    if how == "median":
        return np.where(np.isnan(lst_m), np.nanmedian(lst_m), lst_m)
    if how == "neighbors":
        a = lst_m.copy()
        for _ in range(60):                            # итеративное заполнение средним соседей 3x3
            m = np.isnan(a)
            if not m.any():
                break
            v = np.where(m, 0, a); c = (~m).astype(float)
            sv = ndimage.uniform_filter(v, 3); sc = ndimage.uniform_filter(c, 3)
            a = np.where(m & (sc > 0), sv / np.where(sc > 0, sc, 1), a)
        return a
    return lst_m                                       # "renormalize": NaN -> вес перераспределяется


sens_missing = {}
for clustered in (False, True):
    for frac in (0.1, 0.2, 0.3):
        row = {}
        for how in ("median", "neighbors", "renormalize"):
            js = []
            for _ in range(5):
                lm = np.where(make_mask(frac, clustered), np.nan, lst)
                js.append(jacc(topk(score(components(fill(lm, how)), W_BASE)), T_base))
            row[how] = round(float(np.mean(js)), 3)
        sens_missing[f"{'clustered' if clustered else 'random'}_{int(frac*100)}pct"] = row

# ---------- 5. Сценарии вмешательства ----------
hot_decile = populated & (lst >= np.quantile(lst[populated], 0.9))
treated = np.zeros(N * N, bool); treated[list(T_base)] = True; treated = treated.reshape(N, N)
s1 = {"label": "S1 посадки/затенение в топ-5% ячеек индекса (охват, НЕ эффект)",
      "pop_in_treated_cells_share": round(float(pop[treated].sum() / pop.sum()), 4),
      "hot_decile_pop_covered_share": round(float(pop[treated & hot_decile].sum() / pop[hot_decile].sum()), 4),
      "cooling_effect": "НЕ МОДЕЛИРУЕТСЯ: ΔT воздуха задаётся только как параметр-гипотеза {0; 0.5; 1.0} °C и требует замеров до/после"}
for dT in (0.0, 0.5, 1.0):
    s1[f"person_degree_hypothetical_dT_{dT}"] = round(float(pop[treated].sum() * dT), 1)

n_cand = 60
free = np.argwhere(populated & ~industrial)
pick = free[rng.choice(len(free), n_cand, replace=False)]
cand_x, cand_y = (pick[:, 1] + 0.5) * CELL, (pick[:, 0] + 0.5) * CELL
cand_a = np.round(rng.uniform(0.5, 2.0, n_cand), 2)


def access_with(sel):
    return access_distance(np.r_[pk_x, cand_x[sel]], np.r_[pk_y, cand_y[sel]],
                           np.r_[pk_area_ha, cand_a[sel]], np.r_[pk_public, np.ones(len(sel), bool)])


def greedy_cover(n):                                   # жадное максимальное покрытие: не ML
    sel = []
    for _ in range(n):
        best, bv = None, -1
        for j in range(n_cand):
            if j in sel:
                continue
            v = share_within(access_with(sel + [j]), 300)
            if v > bv:
                best, bv = j, v
        sel.append(best)
    return sel


n_parks_new = 5
g_sel = greedy_cover(n_parks_new)
cand_lst = lst[pick[:, 0], pick[:, 1]]
hot_sel = list(np.argsort(-cand_lst)[:n_parks_new])
rand_vals = [share_within(access_with(list(rng.choice(n_cand, n_parks_new, replace=False))), 300) for _ in range(200)]
s2 = {"label": f"S2 {n_parks_new} микропарков >=0.5 га на свободных участках (геометрия, при условии что парк построен и публичен)",
      "baseline_share_within_300m": access["share_pop_within_300m"],
      "greedy_max_cover": round(share_within(access_with(g_sel), 300), 4),
      "hottest_candidates": round(share_within(access_with(hot_sel), 300), 4),
      "random_mean_of_200": round(float(np.mean(rand_vals)), 4)}

n_sites, m_inspect = 30, 8
sx, sy = rng.uniform(300, 9700, n_sites), rng.uniform(300, 9700, n_sites)
complaints = rng.poisson(3 + 6 * built[(sy // CELL).astype(int), (sx // CELL).astype(int)])
d_site = np.hypot(cx[..., None] - sx, cy[..., None] - sy)
pop500 = np.array([pop[d_site[..., i] <= 500].sum() for i in range(n_sites)])
rec500 = np.array([rec[d_site[..., i] <= 500].sum() for i in range(n_sites)])


def exposed(sel):
    m = (d_site[..., sel] <= 500).any(-1)
    return float(pop[m].sum()), float(rec[m].sum())


expo_rank = np.argsort(-(prank(pop500, np.ones(n_sites, bool)) + prank(rec500, np.ones(n_sites, bool))))[:m_inspect]
compl_rank = np.argsort(-complaints)[:m_inspect]
s3 = {"label": f"S3 обследовать {m_inspect} из {n_sites} подозрительных мест (экспозиция, НЕ подтверждение загрязнения)",
      "by_exposure_pop_rec": exposed(list(expo_rank)),
      "by_complaints_pop_rec": exposed(list(compl_rank)),
      "overlap_sites": len(set(expo_rank) & set(compl_rank))}

result = {"kind": "synthetic", "seed": SEED, "grid": f"{N}x{N} cells, {int(CELL)} m", "populated_cells": int(P.sum()),
          "top_k": K, "weights_base": dict(zip(NAMES, W_BASE.tolist())), "access_indicator": access,
          "baselines": baselines, "sensitivity_weights": sens_weights, "sensitivity_missing_lst": sens_missing,
          "scenarios": {"S1": s1, "S2": s2, "S3": s3}}
print(json.dumps(result, ensure_ascii=False, indent=1))
json.dump(result, open("A08_mvp_results_synthetic.json", "w"), ensure_ascii=False, indent=1)
