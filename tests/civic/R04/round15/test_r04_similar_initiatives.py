"""R04 раунд 15: similar_initiatives() — похожая инициатива рядом для R16 («Присоединиться к существующей»)."""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from ui.civic_ml_api import set_initiative_source, similar_initiatives

TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=TZ)
P = [71.41, 51.10]


def rec(i, kind, title, dlon=0.001, days=3, status="published", joined=5, text="секретный текст автора"):
    return {"id": f"i-{i}", "kind": kind, "title": title, "text": text, "point": [P[0] + dlon, P[1]],
            "starts_at": (NOW + timedelta(days=days)).isoformat(), "status": status, "joined": joined,
            "author_device": "dev-secret-123456"}


RECORDS = [
    rec(1, "cleanup", "Субботник во дворе у дома 15"),
    rec(2, "greening", "Посадим деревья на аллее", 0.002),
    rec(3, "cleanup", "Уборка двора после зимы", 0.02),            # 1.4 км — далеко
    rec(4, "snow", "Расчистим снег у подъезда"),
    rec(5, "cleanup", "Сенбілік: ауланы тазалаймыз", 0.003),
    rec(6, "cleanup", "Субботник", status="done"),                  # уже сделано
    rec(7, "cleanup", "Субботник через два месяца", days=60),      # за окном days
    rec(8, "cleanup", "Субботник вчера", days=-1),                  # уже прошёл
]


@pytest.fixture(autouse=True)
def no_source():
    set_initiative_source(None)
    yield
    set_initiative_source(None)


def ids(result):
    return [item["id"] for item in result["items"]]


def test_same_deed_ru_and_kk_nearby_only_live():
    res = similar_initiatives("Субботник в нашем дворе", P, 30, records=RECORDS, now=NOW)
    assert ids(res) == ["i-1", "i-5"]
    assert res["items"][0]["why_ru"].startswith("Тоже уборка") and res["items"][0]["distance_m"] == 70
    res = similar_initiatives("Ауланы тазалау сенбілігі", P, 30, records=RECORDS, now=NOW)
    assert ids(res)[0] == "i-5" and "i-1" in ids(res)


def test_other_deeds_and_privacy():
    assert ids(similar_initiatives("Почистим снег", P, 30, records=RECORDS, now=NOW)) == ["i-4"]
    assert ids(similar_initiatives("Посадка саженцев", P, 30, records=RECORDS, now=NOW)) == ["i-2"]
    dumped = json.dumps(similar_initiatives("Субботник", P, 30, records=RECORDS, now=NOW), ensure_ascii=False)
    assert "секретный" not in dumped and "dev-secret" not in dumped


def test_sources_chain(monkeypatch):
    assert similar_initiatives("Субботник", P, 30, now=NOW)["source"] in ("not_connected", "r16")
    set_initiative_source(lambda point, radius_m, days: RECORDS)
    res = similar_initiatives("Субботник во дворе", P, 30, now=NOW)
    assert res["source"] == "registered" and ids(res)[0] == "i-1"
    set_initiative_source(None)

    class Store:
        def list(self, **kwargs):
            assert kwargs["statuses"] == ("published",) and kwargs["upcoming_only"] is True
            return [dict(RECORDS[0], lon=P[0] + 0.001, lat=P[1], point=None)]

    fake = types.ModuleType("ui.civic_together")
    fake.default_service = lambda db_path=None: types.SimpleNamespace(store=Store())
    monkeypatch.setitem(sys.modules, "ui.civic_together", fake)
    res = similar_initiatives("Субботник во дворе", P, 30, now=NOW)
    assert res["source"] == "r16" and ids(res) == ["i-1"]


def test_positional_call_like_r16_and_validation():
    assert similar_initiatives("Субботник", None, 30)["source"] == "no_point"
    with pytest.raises(ValueError):
        similar_initiatives("", P, 30)
    with pytest.raises(ValueError):
        similar_initiatives("Субботник", [1, 2], 30)
    with pytest.raises(ValueError):
        similar_initiatives("Субботник", P, "много")
