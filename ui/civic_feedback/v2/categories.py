"""Категории v2 (раунд 14) и сроки ответа.

Источник истины списка — research/round-14/categories_v2.json (CONTRACT §3).
Список категорий здесь НЕ дублируется: файл читается при первом обращении.
Путь можно переопределить переменной окружения BIRGE_CATEGORIES_V2
(например, если R01 перенесёт файл в data/).
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PATH = ROOT / "research" / "round-14" / "categories_v2.json"

# Сроки первого ответа жителю (перевод из «новое» в «принято»/«в работе»), в днях.
# ДЕМО-НОРМАТИВ R09, не утверждён акиматом. Срочное (холод, вода, гололёд) — 1 день,
# опасное и тёмное — 3 дня, остальное — до 10 дней (закон РК об обращениях даёт до 15 рабочих дней).
# Ключи обязаны совпадать со списком категорий в JSON — это проверяет validate_response_days().
RESPONSE_DAYS = {
    "roads": 10,
    "snow_ice": 1,
    "sidewalks": 10,
    "transport": 5,
    "lighting": 3,
    "yards": 10,
    "waste": 3,
    "utilities": 1,
    "smell_air": 3,
    "noise_safety": 3,
    "parking": 7,
    "other": 10,
}


def categories_path() -> Path:
    return Path(os.environ.get("BIRGE_CATEGORIES_V2") or DEFAULT_PATH)


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [item["id"] for item in data.get("categories", [])]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError(f"{path}: список категорий пуст или содержит повторы")
    return data


def load() -> dict:
    """Весь файл categories_v2.json (кэшируется по пути)."""
    return _load(str(categories_path()))


def ids() -> tuple[str, ...]:
    return tuple(item["id"] for item in load()["categories"])


def by_id() -> dict[str, dict]:
    return {item["id"]: item for item in load()["categories"]}


def is_category(value) -> bool:
    return isinstance(value, str) and value in by_id()


def v1_to_v2(label) -> str:
    """Старая метка v1 -> id v2. Неизвестное -> 'other' (а не ошибка: миграция без потерь,
    исходная метка сохраняется в legacy записи)."""
    if is_category(label):
        return label
    return load().get("v1_to_v2", {}).get(label, "other")


def validate_response_days() -> None:
    known = set(ids())
    have = set(RESPONSE_DAYS)
    if known != have:
        raise ValueError(f"RESPONSE_DAYS не совпадает с categories_v2.json: "
                         f"нет {sorted(known - have)}, лишние {sorted(have - known)}")


def response_days(category: str) -> int:
    validate_response_days()
    return RESPONSE_DAYS[category]


def public_payload() -> dict:
    """Ответ GET /api/civic/v2/categories: порядок, подписи ru/kk, иконки, цели, сроки."""
    validate_response_days()
    data = load()
    return {
        "version": data.get("version"),
        "categories": [{"id": c["id"], "ru": c["ru"], "kk": c["kk"], "icon": c.get("icon"),
                        "examples_ru": c.get("examples_ru"), "target_kinds": c.get("target_kinds", []),
                        "response_days": RESPONSE_DAYS[c["id"]]} for c in data["categories"]],
        "heat_levels": data.get("heat_levels", []),
        "fixed_state": data.get("fixed_state"),
        "weight_half_life_days": data.get("weight_half_life_days"),
    }
