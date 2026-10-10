"""Категории v2 из research/round-14/categories_v2.json (CONTRACT §3): список не копируется в код."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = REPO_ROOT / "research" / "round-14" / "categories_v2.json"
OTHER = "other"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))


def ids() -> tuple[str, ...]:
    return tuple(c["id"] for c in _data()["categories"])


def v1_to_v2() -> dict[str, str]:
    return dict(_data().get("v1_to_v2") or {})
