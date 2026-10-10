"""Метрики: accuracy, macro-F1, P/R/F1 по классам, матрица ошибок, бутстрэп 95% ДИ, парная разница, ECE.

Только numpy (без sklearn) — одинаково считается в облаке, на ноутбуке и в тестах.
Macro-F1 усредняется по классам, которые есть в истинных метках (support > 0) — как в v1
(ml/civic_classifier/metrics.py), чтобы числа v1 и v2 были сравнимы. Класс, которого нет в наборе,
но который модель предсказывает, снижает precision других классов через их FN, но в среднее не входит.

Бутстрэп: по текстам или по группам (шаблонам синтетики — ошибки внутри шаблона связаны).
"""

from __future__ import annotations

import numpy as np

N_BOOT = 2000
BOOT_SEED = 20261011


def _cm(y: np.ndarray, p: np.ndarray, k: int) -> np.ndarray:
    return np.bincount(y * k + p, minlength=k * k).reshape(k, k)


def _f1_from_cm(cm: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    tp = np.diag(cm).astype(float)
    pred_n = cm.sum(axis=0).astype(float)
    true_n = cm.sum(axis=1).astype(float)
    prec = np.divide(tp, pred_n, out=np.zeros_like(tp), where=pred_n > 0)
    rec = np.divide(tp, true_n, out=np.zeros_like(tp), where=true_n > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros_like(tp), where=(prec + rec) > 0)
    return prec, rec, f1, true_n


def macro_f1_cm(cm: np.ndarray) -> float:
    _, _, f1, support = _f1_from_cm(cm)
    mask = support > 0
    return float(f1[mask].mean()) if mask.any() else 0.0


def macro_f1(y_true, y_pred, k: int) -> float:
    """macro-F1 по индексам классов — одно правило для выбора модели (val) и для отчёта."""
    return macro_f1_cm(_cm(np.asarray(y_true, dtype=int), np.asarray(y_pred, dtype=int), k))


def report(y_true: list[int], y_pred: list[int], labels: tuple[str, ...]) -> dict:
    """Полный отчёт для одного набора: accuracy, macro-F1, weighted-F1, по классам, матрица."""
    k = len(labels)
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    n = int(len(y))
    if n == 0:
        return {"n": 0, "accuracy": None, "macro_f1": None, "weighted_f1": None, "per_class": {},
                "confusion": {"labels": list(labels), "rows_true_cols_pred": [[0] * k for _ in range(k)]}}
    cm = _cm(y, p, k)
    prec, rec, f1, support = _f1_from_cm(cm)
    per = {labels[c]: {"precision": round(float(prec[c]), 4), "recall": round(float(rec[c]), 4),
                       "f1": round(float(f1[c]), 4), "support": int(support[c]),
                       "predicted": int(cm[:, c].sum())} for c in range(k)}
    weighted = float((f1 * support).sum() / support.sum()) if support.sum() else 0.0
    return {"n": n, "accuracy": round(float((y == p).mean()), 4), "macro_f1": round(macro_f1_cm(cm), 4),
            "weighted_f1": round(weighted, 4), "classes_in_set": int((support > 0).sum()), "per_class": per,
            "confusion": {"labels": list(labels), "rows_true_cols_pred": cm.tolist()},
            "macro_over": "классы с support > 0"}


def _units(n: int, groups: list | None) -> list[np.ndarray]:
    if not groups:
        return [np.array([i]) for i in range(n)]
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    return [np.array(by[g]) for g in sorted(by, key=str)]


def bootstrap(y_true, y_pred, k: int, groups: list | None = None, n_boot: int = N_BOOT,
              seed: int = BOOT_SEED) -> dict:
    """95% перцентильный интервал macro-F1 и accuracy. groups -> кластерный бутстрэп."""
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    if len(y) == 0:
        return {"macro_f1": {"low": None, "high": None}, "accuracy": {"low": None, "high": None}}
    units = _units(len(y), groups)
    rng = np.random.default_rng(seed)
    f1s, accs = np.empty(n_boot), np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(units), size=len(units))
        idx = np.concatenate([units[j] for j in pick])
        yy, pp = y[idx], p[idx]
        f1s[b] = macro_f1_cm(_cm(yy, pp, k))
        accs[b] = (yy == pp).mean()
    unit = f"groups (n={len(units)})" if groups else f"texts (n={len(units)})"
    return {"macro_f1": {"low": round(float(np.percentile(f1s, 2.5)), 4),
                         "high": round(float(np.percentile(f1s, 97.5)), 4)},
            "accuracy": {"low": round(float(np.percentile(accs, 2.5)), 4),
                         "high": round(float(np.percentile(accs, 97.5)), 4)},
            "n_boot": n_boot, "level": 0.95, "unit": unit, "seed": seed}


def paired_delta(y_true, pred_a, pred_b, k: int, groups: list | None = None, n_boot: int = N_BOOT,
                 seed: int = BOOT_SEED) -> dict:
    """Парный бутстрэп разницы macro-F1 (a − b) на одних и тех же ресэмплах."""
    y = np.asarray(y_true, dtype=int)
    a = np.asarray(pred_a, dtype=int)
    b_ = np.asarray(pred_b, dtype=int)
    if len(y) == 0:
        return {"delta": None, "low": None, "high": None}
    units = _units(len(y), groups)
    rng = np.random.default_rng(seed)
    deltas = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, len(units), size=len(units))
        idx = np.concatenate([units[j] for j in pick])
        deltas[i] = macro_f1_cm(_cm(y[idx], a[idx], k)) - macro_f1_cm(_cm(y[idx], b_[idx], k))
    point = macro_f1_cm(_cm(y, a, k)) - macro_f1_cm(_cm(y, b_, k))
    return {"delta": round(float(point), 4), "low": round(float(np.percentile(deltas, 2.5)), 4),
            "high": round(float(np.percentile(deltas, 97.5)), 4),
            "share_delta_gt_0": round(float((deltas > 0).mean()), 3), "n_boot": n_boot,
            "unit": "groups" if groups else "texts"}


def ece(correct: list[int], scores: list[float], bins: int = 10) -> float | None:
    """Ошибка калибровки max-score (чем меньше, тем ближе score к доле верных)."""
    if not scores:
        return None
    c = np.asarray(correct, dtype=float)
    s = np.asarray(scores, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (s > lo) & (s <= hi) if lo > 0 else (s >= lo) & (s <= hi)
        if mask.any():
            total += mask.mean() * abs(c[mask].mean() - s[mask].mean())
    return round(float(total), 4)


def choose_threshold(scores: list[float], correct: list[bool], is_other: list[bool],
                     target_precision: float = 0.90) -> dict:
    """Порог needs_review по VALIDATION: минимальный t, при котором точность подсказок без проверки
    (score >= t и категория не other) >= target. Недостижимо -> порог с максимальной точностью."""
    grid = [round(0.30 + 0.05 * i, 2) for i in range(14)]  # 0.30 … 0.95
    rows = []
    n = len(scores)
    for t in grid:
        sel = [c for s, c, o in zip(scores, correct, is_other) if s >= t and not o]
        prec = sum(sel) / len(sel) if sel else None
        rows.append({"threshold": t, "auto_share": round(len(sel) / n, 4) if n else None,
                     "precision_auto": None if prec is None else round(prec, 4)})
    ok = [r for r in rows if r["precision_auto"] is not None and r["precision_auto"] >= target_precision]
    if ok:
        chosen = ok[0]["threshold"]
    else:
        scored = [r for r in rows if r["precision_auto"] is not None]
        chosen = max(scored, key=lambda r: (r["precision_auto"], -r["threshold"]))["threshold"] if scored else 1.0
    return {"chosen": chosen, "target_precision": target_precision, "target_met": bool(ok), "grid": rows}
