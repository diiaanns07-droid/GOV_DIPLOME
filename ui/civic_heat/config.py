"""Настройки тепловой карты из единого источника — research/round-14/categories_v2.json (CONTRACT §3, §6).

Список категорий, уровни, цвета и полураспад в код не копируются: всё читается из JSON.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = ROOT / "research" / "round-14" / "categories_v2.json"
GEOFENCE_PATH = ROOT / "data" / "civic" / "astana" / "geofence.json"
GRAPH_PATH = ROOT / "engine" / "civic_scenarios" / "graphs" / "osm-astana-walking-20260506.graph.json"

# Районы на мелком масштабе: у района жалоб в разы больше, чем у одной цели, поэтому пороги
# уровней для района умножаются на этот коэффициент (иначе весь город сразу «тёмно-красный»).
DISTRICT_LEVEL_SCALE = 5.0

# Периоды фильтра (UX_BRIEF: 7 / 30 / 90 дней). Другие значения API тоже принимает (1…365).
PERIODS = (7, 30, 90)
DEFAULT_DAYS = 30
MAX_DAYS = 365

# Мини-график в карточке цели — всегда за последние 14 дней (по дням).
DAILY_WINDOW_DAYS = 14

# Смысловой зум (CONTRACT §6): меньше 12 — районы, дальше — дворы, участки и объекты.
DISTRICT_ZOOM_MAX = 12.0


@dataclass(frozen=True)
class Level:
    level: int
    min_weight: float
    color: str | None
    ru: str
    kk: str


@dataclass(frozen=True)
class HeatConfig:
    version: str
    categories: tuple[dict, ...]
    category_ids: frozenset[str]
    levels: tuple[Level, ...]
    fixed_color: str
    fixed_ru: str
    fixed_kk: str
    fixed_days: float
    half_life_days: float

    def level_for(self, weight: float, scale: float = 1.0) -> int:
        """Уровень по весу. Любая живая жалоба видна хотя бы уровнем 1.

        В categories_v2.json у уровня 1 порог веса 1.0, а вес одной жалобы уже через час меньше 1
        (0.5 ** (возраст/14)). Без «пола» одиночная жалоба исчезала бы с карты почти сразу,
        поэтому вес > 0 всегда даёт уровень не ниже 1.
        С порогами сравнивается вес, округлённый до целого человека: иначе 10 свежих жалоб
        (вес 9,95) показывались бы цветом «6–9», а на значке стояло бы «10» — путаница для зрителя.
        """
        if weight <= 0:
            return 0
        rounded = math.floor(weight / scale + 0.5) * scale
        result = 1
        for lv in self.levels:
            if lv.level >= 1 and rounded >= lv.min_weight * scale:
                result = max(result, lv.level)
        return result

    def color_for(self, level: int) -> str | None:
        for lv in self.levels:
            if lv.level == level:
                return lv.color
        return None

    def legend(self) -> dict:
        """Легенда для интерфейса: цвета и подписи без копирования в JS."""
        return {
            "levels": [
                {"level": lv.level, "min_weight": lv.min_weight, "color": lv.color, "ru": lv.ru, "kk": lv.kk}
                for lv in self.levels
            ],
            "fixed": {"color": self.fixed_color, "ru": self.fixed_ru, "kk": self.fixed_kk, "days_visible": self.fixed_days},
            "half_life_days": self.half_life_days,
            "district_level_scale": DISTRICT_LEVEL_SCALE,
        }


def parse_config(raw: dict) -> HeatConfig:
    levels = tuple(
        Level(int(x["level"]), float(x["min_weight"]), x.get("color"), str(x.get("ru", "")), str(x.get("kk", "")))
        for x in raw["heat_levels"]
    )
    if not levels or sorted(lv.level for lv in levels) != [lv.level for lv in levels]:
        raise ValueError("heat_levels должны идти по возрастанию уровня")
    fixed = raw["fixed_state"]
    cats = tuple(raw["categories"])
    return HeatConfig(
        version=str(raw.get("version", "")),
        categories=cats,
        category_ids=frozenset(c["id"] for c in cats),
        levels=levels,
        fixed_color=fixed["color"],
        fixed_ru=fixed.get("ru", ""),
        fixed_kk=fixed.get("kk", ""),
        fixed_days=float(fixed.get("days_visible", 7)),
        half_life_days=float(raw.get("weight_half_life_days", 14)),
    )


@lru_cache(maxsize=1)
def load_config(path: str | None = None) -> HeatConfig:
    p = Path(path) if path else CATEGORIES_PATH
    return parse_config(json.loads(p.read_text("utf-8")))
