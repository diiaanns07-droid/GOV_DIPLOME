"""Помощники тестов R04 (раунд 14): данные и автофикстура чистого состояния ML-API.

conftest.py в этой папке НАРОЧНО нет: в общей сборке все conftest.py без пакета импортируются под одним
именем «conftest», и `from conftest import …` в тестах другой роли (R03) получал бы чужой модуль.
Каждый тестовый модуль R04 импортирует clean_api отсюда — pytest регистрирует её как autouse-фикстуру.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ml.civic_dedup.search import ASTANA_TZ

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=ASTANA_TZ)
STOP = (71.4180, 51.0905)   # условная точка в Нуре


def record(rid, text, *, point=STOP, days_ago=1.0, status="new", target=None, metoo=0, duplicate_of=None,
           category="transport"):
    created = (NOW - timedelta(days=days_ago)).replace(microsecond=0).isoformat()
    return {"id": rid, "created_at": created, "text": text, "lang": "ru", "category": category,
            "point": list(point) if point is not None else None,
            "target": target or {"kind": "object", "id": "osm-node-1001", "label_ru": "Остановка «Нура»"},
            "status": status, "metoo": metoo, "duplicate_of": duplicate_of, "demo": True}


@pytest.fixture(autouse=True)
def clean_api():
    """Забыть модели, оценщик дублей и источник жалоб до и после каждого теста."""
    import ui.civic_ml_api as api
    api.reset()
    yield
    api.reset()
