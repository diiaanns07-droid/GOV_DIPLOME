"""R13 раунд 15: контракт с соседями — то, что зовут R08 («Картина дня», Ситуационный центр), R06 (лента) и R01 (мир).

Имена и поля — как их ищут соседи в своих ветках (R08 ui/civic_akim/neighbors.py: R13_MEETINGS_FUNCS = ("board_block", …),
R13_WEEK_FUNCS = ("week_forecast", "forecast_week", …), вызов с db_path, district, k, now — лишние параметры отсекаются по
сигнатуре). Если сосед поменяет имя — тест не поймает, но если R13 сломает свою сторону — поймает.
"""

from __future__ import annotations

from datetime import datetime, timezone
import inspect

import ui.civic_forecast as forecast
import ui.civic_meetings as meetings

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)


def _call(fn, **kwargs):
    """Как _call R08: только объявленные параметры."""
    params = inspect.signature(fn).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    return fn(**{k: v for k, v in kwargs.items() if k in params})


def test_r08_week_forecast_names_and_fields():
    for name in ("week_forecast", "forecast_week", "week_block"):
        body = _call(getattr(forecast, name), district=None, k=5, now=NOW)
        assert body["horizon"] == "week" and body["evidence_type"] == "synthetic" and body["demo"] is True
        assert body["method_ru"] and body["method_kk"] and body["note_ru"]
        assert len(body["items"]) == 5
        for item in body["items"]:
            assert {"target", "district", "level", "main_category", "reason_ru", "reason_kk"} <= set(item)
            assert {"kind", "id", "label_ru", "label_kk"} <= set(item["target"])
            # R08 @ eca77d34 (blocks.forecast) берёт причину из reasons[0] — та же строка, что reason_ru / reason_kk
            assert item["reasons"][0]["ru"] == item["reason_ru"] and item["reasons"][0]["kk"] == item["reason_kk"]


def test_r08_board_block_by_db_path(tmp_path):
    path = str(tmp_path / "civic.sqlite3")
    meetings.make_service(path, demo=True)
    body = _call(meetings.board_block, db_path=path, district=None, now=NOW)
    assert {"counts", "orders", "next", "demo", "card"} <= set(body) and "items" not in body
    assert set(body["counts"]) == {"total", "todo", "in_progress", "done", "overdue"}
    for order in body["orders"]:
        assert {"id", "text_ru", "service", "due", "status", "overdue", "meeting_id", "meeting_title_ru", "meeting_at",
                "district"} <= set(order)
    assert {"id", "title_ru", "at", "registered", "district", "demo"} <= set(body["next"])


def test_r06_updates_signature_and_empty_safe(tmp_path):
    path = str(tmp_path / "civic.sqlite3")
    meetings.make_service(path, demo=True)
    assert meetings.updates("dev-unknown-00000001", None, db_path=path) == []
    assert meetings.updates("bad id", None, db_path=path) == []
    assert meetings.updates("dev-unknown-00000001", "2026-01-01T00:00:00Z", db_path=str(tmp_path / "nope" / "x.sqlite3")) == []


def test_r01_seed_world_positional_call(tmp_path):
    # R01 (patch R02): fn(str(db_path), world, now)
    report = meetings.seed_world(str(tmp_path / "w.sqlite3"), {"meetings": [], "questions": []}, NOW)
    assert report == {"inserted": 0, "skipped": 0, "reset": 0}
