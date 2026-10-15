"""R13 раунд 15: «Прогноз на неделю» для «Картины дня» R08 (ui.civic_forecast.week_block) и карточка «Встречи».

Запуск: python -m pytest -q tests/civic/R13/test_r13_forecast_week.py
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from ui.civic_forecast import forecast_response, week_block

REPO = Path(__file__).resolve().parents[3]
RESULTS = json.loads((REPO / "ml" / "civic_forecast" / "results.json").read_text(encoding="utf-8"))


def test_week_block_is_an_honest_prototype():
    block = week_block(today=date(2026, 10, 15))
    assert block["label"] == "prototype" and block["evidence_type"] == "synthetic" and block["demo"] is True
    assert block["period"] == {"from": "2026-10-15", "to": "2026-10-21"} and block["month"] == "2026-10"
    assert 3 <= len(block["items"]) <= 5
    assert "синтетическ" in block["note_ru"] and "Open-Meteo" in block["note_ru"]
    assert "синтетика" in block["note_kk"] and "Open-Meteo" in block["note_kk"]
    ranks = [i["rank"] for i in block["items"]]
    risks = [i["risk"] for i in block["items"]]
    assert ranks == list(range(1, len(ranks) + 1)) and risks == sorted(risks, reverse=True)
    for item in block["items"]:
        assert item["target"]["id"] and item["target"]["label_ru"] and item["district"]
        assert item["reason_ru"] and item["reason_kk"] and "\n" not in item["reason_ru"]  # причина — одной строкой
        assert item["reason_source"] in ("history", "weather")
        assert item["level"] in ("high", "medium", "low")


def test_how_we_count_uses_round14_backtest_numbers():
    method = week_block(today=date(2026, 10, 15))["method"]
    gbm, base = RESULTS["summary"]["mean"]["gbm"], RESULTS["summary"]["mean"]["last_month"]
    assert method["backtest"]["precision_at_10"] == round(gbm["10"], 2)
    assert method["backtest"]["baseline_last_month_at_10"] == round(base["10"], 2)
    assert method["backtest"]["season"] == "осень"
    assert method["data"] == {"complaints": "synthetic", "weather": "real",
                              "weather_source": RESULTS["meta"]["weather"]["source"],
                              "history": RESULTS["meta"]["months"], "territories": RESULTS["meta"]["targets"]}
    assert f"{round(gbm['10'] * 100)} %" in method["text_ru"] and "осенью" in method["text_ru"]
    assert "прототип" in method["text_ru"] and "прототип" in method["text_kk"]
    winter = week_block(today=date(2027, 1, 10))["method"]
    assert winter["backtest"]["season"] == "зима" and "зимой" in winter["text_ru"] and "қыс" in winter["text_kk"]


def test_month_of_the_week_is_the_one_with_more_days():
    # 29 окт — 4 ноя: 3 дня октября и 4 дня ноября -> прогноз ноября
    assert week_block(today=date(2026, 10, 29))["month"] == "2026-11"
    assert week_block(today=date(2026, 10, 27))["month"] == "2026-10"


@pytest.mark.parametrize("k, n", [(1, 3), (3, 3), (5, 5), (50, 5), ("x", 5)])
def test_three_to_five_territories(k, n):
    assert len(week_block(k=k, today=date(2026, 10, 15))["items"]) == n


def test_district_filter_and_forecast_response_carries_week():
    nura = week_block(district="nura", today=date(2026, 10, 15))
    assert nura["district"] == "nura" and all(i["district"] == "nura" for i in nura["items"])
    reply = forecast_response(k=10)
    assert reply["week"]["label"] == "prototype" and len(reply["week"]["items"]) == 5
    assert len(reply["items"]) == 10  # прежний ответ раунда 14 не изменился


def test_meetings_board_card_for_day_picture(tmp_path):
    from ui.civic_meetings import make_service
    svc = make_service(str(tmp_path / "b.sqlite3"), demo=True)
    block = svc.board_block()
    card, counts = block["card"], block["counts"]
    assert card["value"] == counts["todo"] + counts["in_progress"]
    assert card["link"] == "#meetings" and card["title_ru"] and card["title_kk"]
    assert len(card["lines"]) == 2 and all(line["ru"] and line["kk"] for line in card["lines"])
    assert f"Выполнено {counts['done']} из {counts['total']}" in card["lines"][0]["ru"]
    assert "Ближайшая встреча" in card["lines"][1]["ru"] and "«Приду» 54" in card["lines"][1]["ru"]
    empty = make_service(str(tmp_path / "e.sqlite3"), demo=False).board_block()
    assert empty["card"]["value"] == 0 and empty["next"] is None and "пока нет" in empty["card"]["lines"][1]["ru"]
