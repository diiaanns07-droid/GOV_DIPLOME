"""Модели прогноза R13: «будет ли у территории ≥ N жалоб в следующем месяце».

  gbm             — HistGradientBoostingClassifier (scikit-learn); вероятность.
  fallback        — без зависимостей: сезонная наивная + взвешенная частота по категориям;
                    ожидаемое число жалоб λ = Σ_c (0.7·уровень категории без сезона × сезон прогнозного месяца
                    + 0.3·тот же месяц год назад) × 1.3 при стройке рядом; вероятность P(Пуассон(λ) ≥ N).
                    Уровень без сезона — за 12 месяцев, последние 3 с двойным весом; сезон — по прошлым годам города.
  last_month      — базовый: сколько было в прошлом месяце.
  same_month_ly   — базовый: сколько было в тот же месяц год назад.
У всех один интерфейс: Forecaster(kind).fit(history, last_asof).score(history, asof) → {territory_id: score}.
Ранжирование top-K: по score, при равенстве — по жалобам за 3 месяца, затем по id (детерминированно).
"""

from __future__ import annotations

import math

from .features import FeatureBuilder, MIN_ASOF, THRESHOLD
from .history import History, add_months

MODELS = ("gbm", "fallback", "last_month", "same_month_ly")


def sklearn_available() -> bool:
    try:
        import sklearn.ensemble  # noqa: F401
        return True
    except ImportError:
        return False


def poisson_at_least(lam: float, n: int) -> float:
    if lam <= 0:
        return 0.0
    term, cdf = math.exp(-lam), 0.0
    for k in range(n):
        cdf += term
        term *= lam / (k + 1)
    return max(0.0, 1.0 - cdf)


class Forecaster:
    def __init__(self, kind: str = "gbm", threshold: int = THRESHOLD, weather: bool = True, seed: int = 0):
        if kind not in MODELS:
            raise ValueError(f"Неизвестная модель: {kind}")
        if kind == "gbm" and not sklearn_available():
            raise ImportError("scikit-learn не установлен: используйте kind='fallback'.")
        self.kind, self.threshold, self.weather, self.seed = kind, threshold, weather, seed
        self.model = None
        self.season = None
        self.builder = None
        self.trained_upto = None

    # --- обучение -----------------------------------------------------------------------
    def fit(self, history: History, last_asof: int):
        """Обучение на строках as-of MIN_ASOF … last_asof (их метки — месяцы ≤ last_asof+1, все в прошлом)."""
        self.builder = FeatureBuilder(history, self.threshold, weather=self.weather)
        self.trained_upto = history.months[last_asof + 1]
        if self.kind == "gbm":
            from sklearn.ensemble import HistGradientBoostingClassifier
            X, y = self.builder.training_set(last_asof)
            self.model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_leaf_nodes=31,
                                                        l2_regularization=1.0, min_samples_leaf=40,
                                                        random_state=self.seed)
            self.model.fit(X, y)
        elif self.kind == "fallback":
            self.season = seasonal_ratios(history, upto=last_asof + 1)
        return self

    # --- прогноз --------------------------------------------------------------------------
    def score(self, history: History, asof: int) -> dict[str, float]:
        ids = [t["id"] for t in history.targets]
        if self.kind == "gbm":
            X, _ = self.builder.matrix(asof)
            proba = self.model.predict_proba(X)[:, 1]
            return dict(zip(ids, (float(p) for p in proba)))
        if self.kind == "fallback":
            return {tid: poisson_at_least(lam, self.threshold)
                    for tid, lam in expected_counts(history, asof, self.season).items()}
        if self.kind == "last_month":
            return {tid: float(sum(history.counts[tid][asof])) for tid in ids}
        ly = asof + 1 - 12
        return {tid: float(sum(history.counts[tid][ly])) for tid in ids}


def seasonal_ratios(history: History, upto: int) -> list[list[float]]:
    """ratio[c][calendar_month-1] = средние жалобы категории в этом календарном месяце / в среднем месяце.

    Считается по городу и только по месяцам с индексом ≤ upto (без заглядывания в будущее).
    """
    n_cat = len(history.categories)
    month_sum = [[0.0] * 12 for _ in range(n_cat)]
    month_n = [0] * 12
    for mi in range(upto + 1):
        cm = int(history.months[mi][5:]) - 1
        month_n[cm] += 1
        for t in history.targets:
            row = history.counts[t["id"]][mi]
            for ci in range(n_cat):
                month_sum[ci][cm] += row[ci]
    ratios = []
    for ci in range(n_cat):
        means = [month_sum[ci][m] / month_n[m] for m in range(12) if month_n[m]]
        overall = sum(means) / len(means) if means else 0.0
        ratios.append([(month_sum[ci][m] / month_n[m] / overall) if month_n[m] and overall else 1.0 for m in range(12)])
    return ratios


def expected_counts(history: History, asof: int, season, components: bool = False):
    """λ запасной модели по территориям; components=True — ещё и вклад категорий (для причин)."""
    fmonth = add_months(history.months[asof], 1)
    cm = int(fmonth[5:]) - 1
    ly = asof + 1 - 12
    out, parts = {}, {}
    for t in history.targets:
        rows = history.counts[t["id"]]
        lam, per_cat = 0.0, {}
        for ci, cat in enumerate(history.categories):
            # Уровень «без сезона» за 12 месяцев (последние 3 — с весом 2): Σ w·жалобы / Σ w·сезон.
            # Так одна жалоба на снег в октябре не раздувается делением на почти нулевой октябрьский сезон.
            num = den = 0.0
            for k in range(12):
                w = 2.0 if k < 3 else 1.0
                num += w * rows[asof - k][ci]
                den += w * season[ci][(cm - 1 - k) % 12]
            level = num / den if den else 0.0
            value = 0.7 * level * season[ci][cm] + 0.3 * rows[ly][ci]
            if value:
                per_cat[cat] = value
                lam += value
        if history.construction_active(t["id"], fmonth):
            lam *= 1.3
        out[t["id"]] = lam
        parts[t["id"]] = per_cat
    return (out, parts) if components else out


def top_k(scores: dict[str, float], history: History, asof: int, k: int) -> list[str]:
    tie = {tid: sum(sum(history.counts[tid][m]) for m in range(asof - 2, asof + 1)) for tid in scores}
    return sorted(scores, key=lambda tid: (-scores[tid], -tie[tid], tid))[:k]


__all__ = ["Forecaster", "MODELS", "MIN_ASOF", "expected_counts", "poisson_at_least", "seasonal_ratios",
           "sklearn_available", "top_k"]
