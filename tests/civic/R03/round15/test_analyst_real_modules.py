"""Сверка с настоящими модулями FINAL-4: числа аналитика = числа карты R07 и «Картины дня» R08; время < 1 с.

Демо-набор R07 строится от текущего момента, поэтому ожидаемые числа не записаны в тест, а берутся у самих
модулей тем же вызовом, что видит аким на карте и в «Картине дня».
"""
from __future__ import annotations

import time

import pytest

import r03_r15_fixtures as F
from agent.civic_assistant import api
from agent.civic_assistant.analyst import core

heat_mod = pytest.importorskip("ui.civic_heat")
akim_mod = pytest.importorskip("ui.civic_akim")

SCENE = ("Где в Нуре больше всего жалоб на снег за неделю и какие службы отстают?",
         "Какие службы отстают?", "Что с бураном?")


@pytest.fixture(autouse=True)
def real_sources():
    core.reset()
    core.configure(provider=None, rate=(1000, 60.0))
    yield
    core.reset()


def block(answer, kind):
    return next(b for b in answer["blocks"] if b["kind"] == kind)


def test_hot_spots_equal_heat_map():
    a = api.ask(SCENE[0], "ru", F.STAFF)
    hot = block(a, "hot_spots")
    data = heat_mod.default_service().heat(days=7, district="nura", category="snow_ice")
    active = [it for it in data["items"] if it["state"] == "active"]
    assert hot["numbers"][0]["value"] == sum(it["count"] for it in active)
    assert hot["numbers"][1]["value"] == len(active)
    assert hot["items"][0]["target"]["id"] == active[0]["target"]["id"]
    # Подпись района на карте (обзор районов R07) — то же число.
    nura = next(d for d in heat_mod.default_service().districts(days=7, category="snow_ice")
                if d["target"]["id"] == "nura")
    assert nura["count"] == hot["numbers"][0]["value"]


def test_lagging_services_equal_source_totals():
    """Табло R17 есть — его итог по сроку исправления (overdue_fix; без R08 — overdue); нет — «Просрочено» R08."""
    a = api.ask(SCENE[1], "ru", F.STAFF)
    lag = block(a, "lagging_services")
    if lag["source"]["role"] == "R17":
        totals = __import__("ui.civic_agencies", fromlist=["_"]).board_snapshot(30, None)["totals"]
        late = totals["overdue_fix"] if totals.get("overdue_fix") is not None else totals["overdue"]
        assert lag["numbers"][1]["value"] == late
    else:
        assert lag["numbers"][1]["value"] == akim_mod.summary()["overdue"]["count"]


def test_overdue_and_districts_equal_day_picture():
    summary = akim_mod.summary()
    overdue = block(api.ask("Сколько обращений просрочено?", "ru", F.STAFF), "overdue")
    assert overdue["numbers"][0]["value"] == summary["overdue"]["count"]
    compare = block(api.ask("Сравни районы по жалобам", "ru", F.STAFF), "district_compare")
    expected = {d["district"]: d["value"] for d in summary["districts"]["items"]}
    assert {i["district"]: i["value"] for i in compare["items"]} == {k: v for k, v in expected.items()
                                                                       if k in {i["district"] for i in compare["items"]}}


def test_scene_questions_offline_under_one_second():
    for q in SCENE:  # прогрев: в сервере кэши R07/R08 уже тёплые
        api.ask(q, "ru", F.STAFF)
    for q in SCENE:
        with F.no_gc_pause():
            started = time.perf_counter()
            a = api.ask(q, "ru", F.STAFF)
            elapsed = time.perf_counter() - started
        assert elapsed < 1.0, (q, elapsed)
        assert a["mode"] == "offline"
        # Главная кнопка есть всегда: «Показать на карте» или «Открыть …» (табло служб, кризисный штаб).
        assert a["actions"] and a["actions"][0]["kind"] in ("map.focus", "open")
        assert any(b["numbers"] for b in a["blocks"])
