"""Синтетическая история жалоб R13: «территория × месяц × категория», 2024-01 … 2026-10. evidence: synthetic, demo: true.

Реальной истории обращений нет. Чтобы проверить конвейер прогноза и методику (backtest), генератор строит
правдоподобную историю по реальным территориям R12 (targets.py) и погоде (weather.py: LOCAL-9 или фикстура).
Всё, что «знает» генератор, — допущения R13, перечисленные ниже; на реальных данных акимата они проверяются в пилоте.

Как устроено (подробно — ml/civic_forecast/README.md):
  λ(t, m, c) = база(вид, c) × склонность(t) × сезон(c, погода месяца m) × рост платформы(m)
               × горячий эпизод(t, m) × всплеск(t, m, c) × стройка рядом(t, m, c)
  жалобы ~ Пуассон(λ), детерминированно: у каждой территории свой генератор с seed от (SEED, id).
  - сезон: снег и гололёд — снегопад и оттепели (ноябрь–март); отопление — начало сезона (октябрь–ноябрь) и мороз;
    ямы — весна после оттепелей (март–май, сильнее после «качелей» февраля–марта); мусор и запахи — летняя жара;
    освещение — длинные ночи; дворы и площадки — тёплый сезон.
  - склонность места: логнормальная, σ = 0.55 (есть «вечные» проблемные дворы, но их немного);
  - горячие места: эпизод начинается с вероятностью 3 % в месяц, длится в среднем 3 месяца, ×5 на 1–2 категориях.
  - всплески: 1,5 % территорий-месяцев, одна категория ×6 (авария, разовое событие).
  - стройки: 40 синтетических строек (3–9 месяцев) у случайных улиц и дворов; в радиусе 400 м растут
    дороги, тротуары, шум, пыль. План строек известен заранее — это законный признак прогноза.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import random

from .targets import load_targets
from . import weather as wx

REPO = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = REPO / "research" / "round-14" / "categories_v2.json"
SEED = 2026
FIRST_MONTH = "2024-01"
LAST_MONTH = "2026-10"
# Параметры подобраны так, чтобы задача не была тривиальной: в первой версии (склонность σ=0.8, эпизоды 2 %/мес ×4,
# порог 3) даже прогноз «как в прошлом месяце» давал ~90 % на top-30 — такая проверка ничего не различает.
PROPENSITY_SD = 0.55
HOT_START, HOT_MEAN_MONTHS, HOT_FACTOR = 0.03, 3.0, 5.0
BURST_P, BURST_FACTOR = 0.015, 6.0
N_CONSTRUCTIONS, CONSTRUCTION_RADIUS_M = 40, 400.0

# Базовая частота жалоб в месяц на территорию по виду и категории (до сезонных множителей).
BASE = {
    "yard": {"yards": 0.10, "waste": 0.10, "lighting": 0.06, "utilities": 0.10, "parking": 0.08, "snow_ice": 0.08,
             "noise_safety": 0.04, "smell_air": 0.03, "sidewalks": 0.03, "roads": 0.02, "other": 0.03},
    "bus_stop": {"transport": 0.12, "snow_ice": 0.07, "sidewalks": 0.04, "waste": 0.03, "lighting": 0.03,
                 "other": 0.02},
    "segment": {"roads": 0.18, "sidewalks": 0.07, "snow_ice": 0.12, "lighting": 0.05, "parking": 0.04,
                "noise_safety": 0.03, "other": 0.02},
    "playground": {"yards": 0.09, "waste": 0.04, "lighting": 0.03, "noise_safety": 0.02, "snow_ice": 0.02,
                   "other": 0.01},
    "park": {"yards": 0.07, "waste": 0.06, "lighting": 0.05, "noise_safety": 0.03, "smell_air": 0.01,
             "snow_ice": 0.02, "other": 0.01},
    "waste": {"waste": 0.22, "smell_air": 0.09, "other": 0.01},
}
CONSTRUCTION_EFFECT = {"roads": 2.0, "sidewalks": 2.0, "noise_safety": 3.0, "smell_air": 2.5}


def load_categories():
    data = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    return [c["id"] for c in data["categories"]], {c["id"]: c for c in data["categories"]}


def month_range(first: str = FIRST_MONTH, last: str = LAST_MONTH) -> list[str]:
    y, m = int(first[:4]), int(first[5:])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def add_months(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def metres(a, b) -> float:
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)


def weather_for(months, month_table) -> dict[str, dict]:
    """Погода каждого месяца истории. Неполный месяц масштабируется по дням; нет данных — норма."""
    out = {}
    for key in months:
        m = month_table.get(key)
        if m and m["days"] >= 7:
            y, mo = int(key[:4]), int(key[5:])
            full = 31 if mo in (1, 3, 5, 7, 8, 10, 12) else 30 if mo != 2 else (29 if y % 4 == 0 else 28)
            scale = full / m["days"]
            out[key] = {k: (m[k] * scale if k != "tmean" and m[k] is not None else m[k]) for k in wx.MONTHLY_KEYS}
        else:
            norm = wx.normals(month_table, int(key[5:]), "9999-12")
            out[key] = {k: norm.get(k) or 0.0 for k in wx.MONTHLY_KEYS}
    return out


def season(category: str, month: str, w: dict, prev: dict | None) -> float:
    """Сезонный множитель категории в месяце (1.0 — обычный месяц). Погода — фактическая этого месяца."""
    mo = int(month[5:])
    snow, thaw, frost, hot = w["snowfall_cm"] or 0, w["thaw_days"] or 0, w["frost_days"] or 0, w["hot_days"] or 0
    if category == "snow_ice":
        return 0.05 + snow / 8.0 + thaw * 0.12 if mo in (11, 12, 1, 2, 3, 4) else 0.05
    if category == "utilities":
        return {10: 2.6, 11: 2.0, 12: 1.3, 1: 1.3, 2: 1.2, 6: 1.5, 7: 1.2}.get(mo, 0.8) * (1 + frost * 0.05)
    if category == "roads":
        # Ямы: весна после таяния; сильнее, если в прошлом месяце было много оттепелей.
        base = {3: 1.3, 4: 2.6, 5: 1.9, 6: 1.2}.get(mo, 0.8)
        return base * (1 + (prev["thaw_days"] if prev else 0) * 0.04 if mo in (3, 4, 5) else 1)
    if category == "sidewalks":
        return {4: 1.6, 5: 1.5, 12: 1.2, 1: 1.2, 2: 1.2}.get(mo, 1.0) * (1 + thaw * 0.03)
    if category in ("waste", "smell_air"):
        summer = {6: 1.6, 7: 1.9, 8: 1.7, 5: 1.2, 9: 1.1}.get(mo, 0.8)
        return summer * (1 + hot * (0.06 if category == "smell_air" else 0.04))
    if category == "lighting":
        return {10: 1.5, 11: 1.8, 12: 1.9, 1: 1.7, 2: 1.4, 9: 1.1}.get(mo, 0.6)
    if category == "yards":
        return {5: 1.5, 6: 1.7, 7: 1.7, 8: 1.6, 9: 1.3}.get(mo, 0.6)
    if category == "transport":
        return {9: 1.5, 12: 1.3, 1: 1.4, 2: 1.3}.get(mo, 1.0) * (1 + frost * 0.04)
    if category == "parking":
        return {12: 1.3, 1: 1.4, 2: 1.3, 3: 1.2}.get(mo, 1.0) * (1 + snow / 60)
    if category == "noise_safety":
        return {6: 1.4, 7: 1.5, 8: 1.4}.get(mo, 0.9)
    return 1.0


def _rng(*parts) -> random.Random:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _poisson(rng: random.Random, lam: float) -> int:
    """Пуассон без numpy: Кнут для малых λ, нормальное приближение для больших."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


@dataclass
class Construction:
    id: str
    point: list
    near: str
    start: str
    end: str
    affected: list = field(default_factory=list)


@dataclass
class History:
    months: list
    categories: list
    targets: list
    counts: dict            # target_id → [[count по категориям] по месяцам]
    weather: dict           # month → месячные показатели (фактические, для генерации)
    weather_meta: dict
    weather_table: dict     # 'YYYY-MM' → показатели из дневного ряда (для норм месяца в признаках)
    constructions: list
    hot: dict               # target_id → [bool по месяцам] (служебно, для README и тестов)
    seed: int
    evidence_type: str = "synthetic"

    def month_index(self, month: str) -> int:
        return self.months.index(month)

    def total(self, target_id: str, mi: int) -> int:
        return sum(self.counts[target_id][mi]) if 0 <= mi < len(self.months) else 0

    def construction_active(self, target_id: str, month: str) -> list:
        return [c for c in self.constructions if target_id in c.affected and c.start <= month <= c.end]

    def summary(self) -> dict:
        per_month = [sum(sum(self.counts[t["id"]][mi]) for t in self.targets) for mi in range(len(self.months))]
        by_cat = [sum(self.counts[t["id"]][mi][ci] for t in self.targets for mi in range(len(self.months)))
                  for ci in range(len(self.categories))]
        return {"evidence_type": self.evidence_type, "demo": True, "seed": self.seed, "months": [self.months[0], self.months[-1]],
                "targets": len(self.targets), "complaints_total": sum(per_month), "per_month": dict(zip(self.months, per_month)),
                "by_category": dict(zip(self.categories, by_cat)), "constructions": len(self.constructions),
                "weather": self.weather_meta}


def generate(targets=None, *, seed: int = SEED, first: str = FIRST_MONTH, last: str = LAST_MONTH,
             weather_rows=None, weather_meta=None, prop_sd: float = PROPENSITY_SD) -> History:
    """Детерминированная история. targets — подмножество (для быстрых тестов) или все из data/targets.json."""
    targets = list(targets if targets is not None else load_targets())
    categories, _ = load_categories()
    months = month_range(first, last)
    if weather_rows is None:
        weather_rows, weather_meta = wx.load_daily()
    table = wx.monthly(weather_rows)
    wmonth = weather_for(months, table)

    # Стройки: у случайных участков улиц и дворов (синтетика), список известен заранее.
    rng_c = _rng(seed, "constructions")
    # Места строек выбираются из ПОЛНОГО списка территорий, а не из переданного подмножества: тогда у любой
    # территории одни и те же жалобы и в полной истории, и в быстрой тестовой выборке.
    try:
        universe = load_targets()
    except OSError:
        universe = targets
    anchors = sorted((t for t in universe if t["kind"] in ("segment", "yard")), key=lambda t: t["id"])
    constructions = []
    for i in range(min(N_CONSTRUCTIONS, len(anchors))):
        anchor = anchors[rng_c.randrange(len(anchors))]
        start = add_months(first, rng_c.randrange(0, len(months) - 2))
        end = add_months(start, rng_c.randint(3, 9) - 1)
        c = Construction(id=f"synthetic-construction-{i + 1:02d}", point=anchor["point"], near=anchor["id"],
                         start=start, end=min(end, add_months(last, 6)))
        c.affected = [t["id"] for t in targets if metres(t["point"], c.point) <= CONSTRUCTION_RADIUS_M]
        constructions.append(c)
    by_target_c = {}
    for c in constructions:
        for tid in c.affected:
            by_target_c.setdefault(tid, []).append(c)

    growth = {mo: 1.0 + 0.015 * i for i, mo in enumerate(months)}  # жителей на платформе становится больше
    counts, hot_flags = {}, {}
    for t in targets:
        rng = _rng(seed, t["id"])
        base = BASE[t["kind"]]
        propensity = math.exp(rng.gauss(0, prop_sd))
        hot_cats = rng.sample(sorted(base), k=min(len(base), rng.randint(1, 2)))
        hot_left = 0
        rows, flags = [], []
        for mi, mo in enumerate(months):
            if hot_left > 0:
                hot_left -= 1
            elif rng.random() < HOT_START:
                hot_left = max(1, int(round(rng.expovariate(1 / HOT_MEAN_MONTHS))))
                hot_cats = rng.sample(sorted(base), k=min(len(base), rng.randint(1, 2)))
            burst_cat = rng.choice(sorted(base)) if rng.random() < BURST_P else None
            prev = wmonth[months[mi - 1]] if mi > 0 else None
            active = [c for c in by_target_c.get(t["id"], []) if c.start <= mo <= c.end]
            row = []
            for cat in categories:
                rate = base.get(cat, 0.0)
                if rate == 0.0:
                    row.append(0)
                    continue
                lam = rate * propensity * season(cat, mo, wmonth[mo], prev) * growth[mo]
                if hot_left > 0 and cat in hot_cats:
                    lam *= HOT_FACTOR
                if cat == burst_cat:
                    lam *= BURST_FACTOR
                if active and cat in CONSTRUCTION_EFFECT:
                    lam *= CONSTRUCTION_EFFECT[cat]
                row.append(_poisson(rng, lam))
            rows.append(row)
            flags.append(hot_left > 0)
        counts[t["id"]] = rows
        hot_flags[t["id"]] = flags
    meta = dict(weather_meta or {})
    return History(months=months, categories=categories, targets=targets, counts=counts, weather=wmonth,
                   weather_meta=meta, weather_table=table, constructions=constructions, hot=hot_flags, seed=seed)


def to_records(history: History, month: str, limit: int | None = None) -> list[dict]:
    """Жалобы месяца в виде записей CONTRACT §5 (demo: true) — для стендов R07/R08. Тексты — служебные."""
    mi = history.month_index(month)
    out = []
    for t in history.targets:
        for ci, n in enumerate(history.counts[t["id"]][mi]):
            for k in range(n):
                day = 1 + (hash((t["id"], ci, k)) % 27)
                out.append({
                    "id": f"c-r13-{month}-{t['id']}-{history.categories[ci]}-{k}",
                    "created_at": f"{month}-{day:02d}T10:00:00+05:00",
                    "text": "Синтетическая запись истории R13 (не обращение жителя)", "lang": "ru",
                    "category": history.categories[ci], "category_source": "model",
                    "point": t["point"], "target": {"kind": t["target_kind"], "id": t["id"]},
                    "district": t["district"], "status": "fixed", "metoo": 0, "duplicate_of": None, "demo": True,
                })
                if limit and len(out) >= limit:
                    return out
    return out
