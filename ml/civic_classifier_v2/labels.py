"""Категории v2 — читаются из research/round-14/categories_v2.json (источник истины, CONTRACT §3).

Список руками не копируется: порядок, ru/kk-названия и перевод старых меток v1 -> v2 берутся из файла.
Порядок категорий в файле = порядок выходов модели (индекс класса). Если файл поменяют, модель,
обученная на старом порядке, не загрузится (predict.py сверяет список меток).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = REPO_ROOT / "research" / "round-14" / "categories_v2.json"

# Метки инструмента разметки R02 (web/labeling), которые не являются категорией.
NOT_COMPLAINT = "not_complaint"
OTHER = "other"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cats = data.get("categories")
    if not isinstance(cats, list) or not cats:
        raise ValueError(f"{path}: нет списка categories")
    ids = [c["id"] for c in cats]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: повтор id категории")
    if OTHER not in ids:
        raise ValueError(f"{path}: нет категории '{OTHER}'")
    return data


def categories(path: Path = CATEGORIES_PATH) -> list[dict]:
    return list(_load(str(path))["categories"])


def labels(path: Path = CATEGORIES_PATH) -> tuple[str, ...]:
    """Кортеж id категорий в порядке файла: ('roads', 'snow_ice', …, 'other')."""
    return tuple(c["id"] for c in categories(path))


def v1_to_v2(path: Path = CATEGORIES_PATH) -> dict[str, str]:
    return dict(_load(str(path)).get("v1_to_v2") or {})


def names(lang: str = "ru", path: Path = CATEGORIES_PATH) -> dict[str, str]:
    return {c["id"]: c.get(lang) or c["id"] for c in categories(path)}


def normalize_label(raw, *, not_complaint: str = "drop", path: Path = CATEGORIES_PATH) -> str | None:
    """Метка из любого источника -> id категории v2 или None (пропустить запись).

    - id v2 возвращается как есть;
    - старая метка v1 (transport_stops, landscaping) переводится по v1_to_v2;
    - 'not_complaint' («Не жалоба»: спам, реклама, «тест», бессмыслица): по умолчанию 'drop' -> None —
      запись исключается из обучения и оценки 12 классов (ml/datasets/LABELING_GUIDE_v2.md п. 5);
      not_complaint='other' -> 'other' (для отдельного опыта). Благодарности и вопросы без проблемы —
      это уже 'other' по гайду, их разметчик ставит в other, а не в not_complaint;
    - пусто / skip / неизвестная метка -> None.
    """
    if raw is None:
        return None
    lab = str(raw).strip()
    if not lab:
        return None
    labs = labels(path)
    if lab in labs:
        return lab
    if lab == NOT_COMPLAINT:
        return OTHER if not_complaint == "other" else None
    mapped = v1_to_v2(path).get(lab)
    if mapped in labs:
        return mapped
    return None
