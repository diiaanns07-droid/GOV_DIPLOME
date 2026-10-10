"""Сроки исправления по категориям — по ним «Картина дня» считает «Просрочено».

Просрочено = обращение ещё не исправлено (статус new / accepted / in_progress),
а с момента подачи прошло больше дней, чем указано здесь для его категории.

ВАЖНО: это ДЕМО-НОРМАТИВ R08, акиматом не утверждён. Числа выбраны по смыслу:
  - срочное (нет тепла или воды, гололёд, мусор) — 1–2 дня;
  - опасное и тёмное (фонари, шум, запахи) — 3 дня;
  - ремонт (ямы, остановки, тротуары) — 5–10 дней;
  - благоустройство и парковки — 14 дней.
Закон РК об обращениях даёт до 15 рабочих дней на ответ — ни один срок здесь его не превышает.

Не путать со сроком ПЕРВОГО ОТВЕТА у R09 (ui/civic_feedback/v2/categories.py, RESPONSE_DAYS):
там «новое → принято», здесь «подано → исправлено». Аким смотрит на то, что не решено вовремя.
Ключи обязаны совпадать со списком категорий в categories_v2.json — проверяет validate().
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = ROOT / "research" / "round-14" / "categories_v2.json"

DEADLINE_DAYS = {
    "roads": 7,          # ямы, разбитый асфальт
    "snow_ice": 2,       # снег и гололёд — люди падают уже сегодня
    "sidewalks": 10,
    "transport": 5,      # павильон, расписание
    "lighting": 3,       # тёмный двор — вопрос безопасности
    "yards": 14,         # площадки, деревья — сезонные работы
    "waste": 2,
    "utilities": 1,      # нет тепла или воды
    "smell_air": 3,
    "noise_safety": 3,
    "parking": 14,
    "other": 10,
}


@lru_cache(maxsize=1)
def load_categories(path: str | None = None) -> dict:
    """categories_v2.json — единственный источник списка категорий (CONTRACT §3)."""
    return json.loads(Path(path or CATEGORIES_PATH).read_text("utf-8"))


def category_ids() -> tuple[str, ...]:
    return tuple(c["id"] for c in load_categories()["categories"])


def validate() -> None:
    known, have = set(category_ids()), set(DEADLINE_DAYS)
    if known != have:
        raise ValueError(f"DEADLINE_DAYS не совпадает с categories_v2.json: нет {sorted(known - have)}, "
                         f"лишние {sorted(have - known)}")


def deadline_days(category: str | None) -> int:
    """Срок для категории; неизвестная категория считается «Другое»."""
    return DEADLINE_DAYS.get(category or "other", DEADLINE_DAYS["other"])
