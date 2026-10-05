"""Общий компонент эко-приоритета для Астаны и Шымкента (без нейросети, numpy/scipy).

Город-специфичны только ВХОДЫ (слои, веса, пороги, сезоны), а не код. Скрипт Шымкента
A08_mvp_priority_synthetic.py оставлен без изменений ради воспроизводимости первого прохода;
этот модуль — выделенная из него и расширенная общая часть (QC рядов, жадное покрытие).
"""
import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.stats import rankdata


def prank(v, mask):
    """Перцентильный ранг 0..1 среди mask; NaN сохраняется (пропуск ≠ 0)."""
    v = np.asarray(v, float).ravel(); mask = np.asarray(mask, bool).ravel()
    out = np.full(v.size, np.nan)
    m = mask & ~np.isnan(v)
    if m.sum():
        out[m] = (rankdata(v[m], method="average") - 1) / max(m.sum() - 1, 1)
    return out


def score(comp, names, w, mask):
    """Взвешенная сумма рангов; вес пропущенного компонента перераспределяется."""
    M = np.vstack([comp[n] for n in names]).T
    W = np.broadcast_to(np.asarray(w, float), M.shape).copy()
    miss = np.isnan(M); W[miss] = 0; M = np.where(miss, 0, M)
    den = W.sum(1)
    s = np.where(den > 0, (M * W).sum(1) / np.where(den > 0, den, 1), np.nan)
    s[~np.asarray(mask, bool).ravel()] = np.nan
    return s


def topk(s, k):
    s2 = np.where(np.isnan(s), -np.inf, s)
    return set(np.argpartition(-s2, k)[:k].tolist())


def jacc(a, b):
    return len(a & b) / len(a | b) if (a or b) else 1.0


def weight_sensitivity(comp, names, w_base, mask, k, rng, alpha_scale=20, n=1000):
    """alpha_scale=None -> Dirichlet(1): «любые веса». Возвращает медиану/P10 Jaccard и долю ядра."""
    base = topk(score(comp, names, w_base, mask), k)
    J, freq = [], np.zeros(len(comp[names[0]]))
    for _ in range(n):
        w = rng.dirichlet(alpha_scale * np.asarray(w_base) if alpha_scale else np.ones(len(names)))
        T = topk(score(comp, names, w, mask), k); J.append(jacc(T, base)); freq[list(T)] += 1
    freq /= n
    return {"median_jaccard": round(float(np.median(J)), 3), "p10_jaccard": round(float(np.percentile(J, 10)), 3),
            "core_share_80pct": round(sum(freq[c] >= 0.8 for c in base) / k, 3)}


def fill_neighbors(a, iters=60):
    a = a.copy()
    for _ in range(iters):
        m = np.isnan(a)
        if not m.any():
            break
        v = np.where(m, 0, a); c = (~m).astype(float)
        sv, sc = ndimage.uniform_filter(v, 3), ndimage.uniform_filter(c, 3)
        a = np.where(m & (sc > 0), sv / np.where(sc > 0, sc, 1), a)
    return a


def access_distance(cx, cy, px, py, area_ha, public, min_ha=0.5):
    """Расстояние до края ближайшего публичного участка >= min_ha (край ≈ круг равной площади)."""
    ok = np.asarray(public, bool) & (np.asarray(area_ha) >= min_ha)
    if not ok.any():
        return np.full(cx.shape, np.inf)
    d = np.hypot(cx[..., None] - px[ok], cy[..., None] - py[ok]) - np.sqrt(np.asarray(area_ha)[ok] * 1e4 / np.pi)
    return np.clip(d, 0, None).min(axis=-1)


def greedy_max_cover(n_pick, n_cand, value_fn):
    """Жадное максимальное покрытие: value_fn(list_of_idx) -> float. Не ML, (1-1/e)-приближение для субмодулярных целей."""
    sel = []
    for _ in range(n_pick):
        best = max((j for j in range(n_cand) if j not in sel), key=lambda j: value_fn(sel + [j]))
        sel.append(best)
    return sel


def qc_daily_series(daily, winter_months=(12, 1, 2), summer_months=(6, 7, 8), low=2.0):
    """Простые проверки правдоподобия суточных рядов сети постов (DataFrame: index=date, columns=posts).
    Флаги: neg_corr_network — Spearman с медианой остальных постов < 0;
           season_inverted — медиана зимы < медианы лета, когда у сети в целом наоборот;
           share_below_low — доля суток со средним < low (порог-параметр, по умолчанию 2).
    Флаг означает «проверить», а не «датчик неисправен»."""
    idx = pd.to_datetime(pd.Index(daily.index)); mo = idx.month
    net_w = np.nanmedian(daily[np.isin(mo, winter_months)].values); net_s = np.nanmedian(daily[np.isin(mo, summer_months)].values)
    res = {}
    for c in daily.columns:
        others = daily.drop(columns=c).median(axis=1)
        pair = pd.concat([daily[c], others], axis=1).dropna()
        rho = pair.corr(method="spearman").iloc[0, 1] if len(pair) >= 30 else np.nan
        w = np.nanmedian(daily.loc[np.isin(mo, winter_months), c]) if np.isin(mo, winter_months).any() else np.nan
        s = np.nanmedian(daily.loc[np.isin(mo, summer_months), c]) if np.isin(mo, summer_months).any() else np.nan
        flags = []
        if not np.isnan(rho) and rho < 0: flags.append("neg_corr_network")
        if not (np.isnan(w) or np.isnan(s)) and (net_w > net_s) and (w < s): flags.append("season_inverted")
        sh = float((daily[c].dropna() < low).mean()) if daily[c].notna().any() else np.nan
        if not np.isnan(sh) and sh > 0.3: flags.append("share_below_low>30%")
        res[c] = {"spearman_vs_network": None if np.isnan(rho) else round(float(rho), 2),
                  "share_below_low": None if np.isnan(sh) else round(sh, 3), "flags": flags}
    return res
