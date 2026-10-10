"""Признаки «территория × месяц» для прогноза R13. Только то, что известно на конец месяца M (прогноз на M+1).

Строка признаков для территории t «по состоянию на месяц mi» (индекс в history.months):
  жалобы:   за прошлый месяц / 3 / 12 месяцев, тот же месяц год назад (для прогнозного месяца), тренд
            (3 последних − 3 предыдущих), сколько месяцев подряд ≥ N, максимум и число активных месяцев за год;
            по каждой из 12 категорий — за 1 и 3 месяца и тот же месяц год назад;
  погода:   прошлый месяц по факту (снег, оттепели, мороз, жара) и НОРМА прогнозного месяца по прошлым годам —
            фактическая погода будущего месяца в признаки не попадает (её никто не знает заранее);
  место:    вид территории, район, сезон (месяц — синус и косинус), стройка по плану рядом в прогнозном месяце.
Цель (label): жалоб в прогнозном месяце ≥ N (по умолчанию 4).
"""

from __future__ import annotations

import math

from . import weather as wx
from .history import History, add_months

THRESHOLD = 4  # ≥ 4 жалоб в месяц: ~4 % территорий (около 90 из 2334) — «проблемные» месяца
MIN_ASOF = 11  # нужен целый год истории: тот же месяц год назад и сумма за 12 месяцев
KINDS = ("yard", "bus_stop", "segment", "playground", "park", "waste")
DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
WEATHER_LAST = ("snowfall_cm", "thaw_days", "frost_days", "hot_days")
WEATHER_NORM = ("snowfall_cm", "thaw_days", "frost_days", "hot_days")


class FeatureBuilder:
    def __init__(self, history: History, threshold: int = THRESHOLD, weather: bool = True):
        self.h = history
        self.threshold = threshold
        self.use_weather = weather
        self.ids = [t["id"] for t in history.targets]
        self.totals = {tid: [sum(row) for row in history.counts[tid]] for tid in self.ids}
        self._norm_cache = {}
        cats = history.categories
        names = ["tot_1", "tot_3", "tot_12", "tot_ly", "trend_3", "streak", "max_12", "active_12"]
        for c in cats:
            names += [f"{c}_1", f"{c}_3", f"{c}_ly"]
        names += [f"kind_{k}" for k in KINDS] + [f"district_{d}" for d in DISTRICTS]
        names += ["month_sin", "month_cos", "construction_next"]
        if weather:
            names += [f"w_last_{k}" for k in WEATHER_LAST] + [f"w_norm_{k}" for k in WEATHER_NORM]
        self.names = names
        self.index = {n: i for i, n in enumerate(names)}

    def forecast_month(self, mi: int) -> str:
        return add_months(self.h.months[mi], 1)

    def normals(self, month: str) -> dict:
        if month not in self._norm_cache:
            self._norm_cache[month] = wx.normals(self.h.weather_table, int(month[5:]), month)
        return self._norm_cache[month]

    def row(self, tid: str, mi: int) -> list[float]:
        h, tot, n = self.h, self.totals[tid], self.threshold
        counts = h.counts[tid]
        ly = mi + 1 - 12  # тот же календарный месяц год назад, что и прогнозный
        last3, prev3 = sum(tot[mi - 2:mi + 1]), sum(tot[mi - 5:mi - 2])
        streak = 0
        for k in range(mi, -1, -1):
            if tot[k] < n:
                break
            streak += 1
        year = tot[mi - 11:mi + 1]
        out = [tot[mi], last3, sum(year), tot[ly], last3 - prev3, streak, max(year), sum(1 for v in year if v)]
        for ci in range(len(h.categories)):
            out += [counts[mi][ci], counts[mi][ci] + counts[mi - 1][ci] + counts[mi - 2][ci], counts[ly][ci]]
        target = self._target(tid)
        out += [1.0 if target["kind"] == k else 0.0 for k in KINDS]
        out += [1.0 if target["district"] == d else 0.0 for d in DISTRICTS]
        fmonth = self.forecast_month(mi)
        angle = 2 * math.pi * (int(fmonth[5:]) - 1) / 12
        out += [math.sin(angle), math.cos(angle), float(len(h.construction_active(tid, fmonth)))]
        if self.use_weather:
            last = h.weather[h.months[mi]]
            norm = self.normals(fmonth)
            out += [float(last.get(k) or 0.0) for k in WEATHER_LAST]
            out += [float(norm.get(k) or 0.0) for k in WEATHER_NORM]
        return out

    def _target(self, tid):
        if not hasattr(self, "_by_id"):
            self._by_id = {t["id"]: t for t in self.h.targets}
        return self._by_id[tid]

    def matrix(self, mi: int):
        """(X, ids) по состоянию на месяц mi для всех территорий."""
        if mi < MIN_ASOF:
            raise ValueError(f"Нужен год истории: mi ≥ {MIN_ASOF}.")
        return [self.row(tid, mi) for tid in self.ids], list(self.ids)

    def labels(self, mi: int) -> list[int]:
        """1, если в месяце mi+1 у территории ≥ N жалоб (только для прошлого: mi+1 есть в истории)."""
        return [int(self.totals[tid][mi + 1] >= self.threshold) for tid in self.ids]

    def training_set(self, last_asof: int, first_asof: int = MIN_ASOF):
        """Строки для обучения: as-of от first_asof до last_asof включительно (метки известны)."""
        X, y = [], []
        for mi in range(first_asof, last_asof + 1):
            rows, _ = self.matrix(mi)
            X += rows
            y += self.labels(mi)
        return X, y
