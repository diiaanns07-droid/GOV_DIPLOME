"""Функции соседей «для R03» (их ветки раунда 15): табло и кризисы R17, конфликты R12, инициативы R16, встречи R13.

Две части: (1) фикстуры точно в форматах этих функций — тест всегда; (2) настоящие модули соседей — если они есть
в сборке (у R01 после B1), иначе тест пропускается (NOT_RUN: модуля нет в этой ветке).
"""
from __future__ import annotations

import os

import pytest

import r03_r15_fixtures as F
from agent.civic_assistant import api
from agent.civic_assistant.analyst import core


@pytest.fixture(autouse=True)
def clean():
    core.reset()
    yield
    core.reset()


def ask(question, **cfg):
    core.reset()
    core.configure(**F.full_config(**cfg))
    return api.ask(question, "ru", F.STAFF)


def block(answer, kind):
    return next(b for b in answer["blocks"] if b["kind"] == kind)


def test_r17_board_snapshot_totals_are_complaints_not_rows():
    """Отставание — по сроку исправления R08 (overdue_fix): итог R17 4, а не 2 + 3 по строкам (совместное — одно)."""
    a = ask("Какие службы отстают?", agencies_board=F.r17_board_snapshot)
    lag = block(a, "lagging_services")
    assert lag["source"]["role"] == "R17"
    assert [n["value"] for n in lag["numbers"]] == [2, 4]
    assert [i["service"] for i in lag["items"]] == ["water", "utilities"]
    assert lag["items"][1]["verified_pct"] == 50
    assert "Медиана ответа этой службы — 2,5 дн." in lag["lines"]["ru"]
    # Срок ответа жителю — другое число и другое имя (вкладка «Ответ просрочен»), итог R17 8.
    assert "Срок первого ответа жителю прошёл у 8 обращений (вкладка «Ответ просрочен»)." in lag["lines"]["ru"]


def test_r17_active_incidents_progress_and_openers():
    a = ask("Что с бураном?", agencies_incidents=F.r17_active_incidents)
    crisis = block(a, "crisis")
    assert crisis["title"]["ru"] == "Кризисный штаб: Буран в Нуре"
    assert [n["value"] for n in crisis["numbers"]] == [1, 2]    # 1 из 2 задач, 2 службы
    assert "район Нура" in crisis["lines"]["ru"][0]
    opener = next(x for x in crisis["actions"] if x["kind"] == "open")["opener"]
    assert opener == {"global": "BirgeAgencies", "fn": "openCrisis", "arg": {"incident": "inc-demo-blizzard-nura"}}
    focus = next(x for x in crisis["actions"] if x["kind"] == "map.focus")
    assert focus["target"]["id"] == "osm-w100-1"                  # самое горячее место Нуры по снегу (карта R07)


def test_r12_conflicts_summary_and_no_works():
    b = block(ask("Где копаем дважды?", works_conflicts=F.r12_conflicts_summary), "work_conflicts")
    assert [n["value"] for n in b["numbers"]] == [5, 2]
    assert b["lines"]["ru"][0] == "Самый важный: Копаем дважды — ул. Сыганак."
    assert b["actions"][0]["opener"] == {"global": "BirgeWorksCalendar", "fn": "openConflict", "arg": "cf-1"}
    empty = block(ask("Где копаем дважды?", works_conflicts=F.r12_no_works), "work_conflicts")
    assert empty["status"] == "empty" and "пока нет записей о работах" in empty["lines"]["ru"][0]


def test_r16_initiatives_summary():
    b = block(ask("Какие инициативы жителей в Нуре?", together_initiatives=F.r16_initiatives_summary), "initiatives")
    assert [n["value"] for n in b["numbers"]] == [4, 34, 2]
    assert "пришли 26 соседей" in b["lines"]["ru"][0]
    assert b["actions"][0]["target"]["id"] == "yard-7"


def test_r13_board_block_and_missing_service():
    b = block(ask("Что поручили на встречах с жителями?", meetings_list=F.r13_board_block), "meeting_orders")
    assert [n["value"] for n in b["numbers"]] == [9, 4, 1]
    nothing = block(ask("Что поручили на встречах с жителями?", meetings_list=lambda **kw: None), "meeting_orders")
    assert nothing["status"] == "not_ready"                         # board_block() → None: сервиса нет


def test_r16_no_data_and_r17_no_service_are_not_ready():
    b = block(ask("Какие инициативы жителей?", together_initiatives=lambda **kw: {"status": "no_data"}), "initiatives")
    assert b["status"] == "not_ready"
    lag = block(ask("Какие службы отстают?", agencies_board=lambda **kw: {"services": [], "totals": {}, "empty": True,
                                                                           "source": "none"}), "lagging_services")
    assert lag["source"]["role"] == "R08"                           # запасной расчёт по срокам «Картины дня»


# ---------------------------------------------------------------- настоящие модули соседей (в сборке R01)

def _real(module):
    try:
        return __import__(module, fromlist=["_"])
    except ImportError:
        pytest.skip(f"NOT_RUN: модуля {module} нет в этой ветке (появится в сборке R01)")


def _late_total(totals):
    """Итог табло R17, который аналитик называет «просрочено»: срок исправления R08, без R08 — срок ответа."""
    return totals["overdue_fix"] if totals.get("overdue_fix") is not None else totals["overdue"]


def test_real_neighbours_if_present(tmp_path, monkeypatch):
    agencies, together, meetings = _real("ui.civic_agencies"), _real("ui.civic_together"), _real("ui.civic_meetings")
    calendar = _real("engine.civic_geo.works_calendar")
    if not all(hasattr(m, n) for m, n in ((agencies, "board_snapshot"), (agencies, "active_incidents"),
                                          (together, "initiatives_summary"), (meetings, "board_block"),
                                          (calendar, "conflicts_summary"))):
        pytest.skip("NOT_RUN: функции соседей «для R03» ещё не в сборке")
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    db = str(tmp_path / "civic.sqlite3")
    agencies.make_service(db)
    together.make_service(db)
    meetings.make_service(db)
    core.configure(provider=None, rate=(1000, 60.0))
    expect = {
        "Какие службы отстают?": ("lagging_services", _late_total(agencies.board_snapshot(30, None)["totals"]), 1),
        "Где копаем дважды?": ("work_conflicts", calendar.conflicts_summary(None)["conflicts"], 0),
        "Какие инициативы жителей?": ("initiatives", together.initiatives_summary(None)["upcoming"], 0),
        "Что поручили на встречах с жителями?": ("meeting_orders", meetings.board_block(district=None)["counts"]["total"], 0),
    }
    for question, (kind, value, index) in expect.items():
        b = block(api.ask(question, "ru", F.STAFF), kind)
        assert b["status"] in ("ok", "empty"), (question, b["status"], b["lines"]["ru"])
        if b["status"] == "ok":
            assert b["numbers"][index]["value"] == value, (question, b["numbers"])
    crisis = block(api.ask("Что с бураном?", "ru", F.STAFF), "crisis")
    assert crisis["source"]["role"] == "R17" or os.environ.get("CIVIC_DEMO_WORLD") == "1"
