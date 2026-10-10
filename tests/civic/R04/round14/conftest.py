"""Общие фикстуры тестов R04 (раунд 14): чистое состояние ML-API и синтетические записи жалоб."""

from __future__ import annotations

from datetime import datetime

import pytest

from ml.civic_dedup.search import ASTANA_TZ

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=ASTANA_TZ)
STOP = (71.4180, 51.0905)   # условная точка в Нуре


@pytest.fixture(autouse=True)
def clean_api():
    import ui.civic_ml_api as api
    api.reset()
    yield
    api.reset()


def record(rid, text, *, point=STOP, days_ago=1.0, status="new", target=None, metoo=0, duplicate_of=None,
           category="transport"):
    from datetime import timedelta
    created = (NOW - timedelta(days=days_ago)).replace(microsecond=0).isoformat()
    return {"id": rid, "created_at": created, "text": text, "lang": "ru", "category": category,
            "point": list(point) if point is not None else None,
            "target": target or {"kind": "object", "id": "osm-node-1001", "label_ru": "Остановка «Нура»"},
            "status": status, "metoo": metoo, "duplicate_of": duplicate_of, "demo": True}
