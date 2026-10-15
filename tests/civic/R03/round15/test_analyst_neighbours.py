"""Функции соседей «для R03» (их ветки раунда 15): табло и кризисы R17, конфликты R12, инициативы R16, встречи R13.

Две части: (1) фикстуры точно в форматах этих функций — тест всегда; (2) настоящие модули соседей — если они есть
в сборке (у R01 после B1), иначе тест пропускается (NOT_RUN: модуля нет в этой ветке).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import r03_r15_fixtures as F
from agent.civic_assistant import api
from agent.civic_assistant.analyst import core


@pytest.fixture(autouse=True)
def clean():
    core.reset()
    yield
    core.reset()


ROOT = Path(__file__).resolve().parents[4]


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


# Проверка с настоящими модулями соседей — в отдельном процессе Python: make_service() соседей регистрирует сервисы в их
# модулях (R17 api_state, R16 _services, R13 _SERVICES); в общем прогоне pytest сборки R01 эти сервисы на временной базе
# достались бы тестам R13 / R16 / R17, которые идут после R03 (R01 BUILD_LOG: «порядок тестов»).
_REAL_CHECK = r"""
import json, sys
from agent.civic_assistant import api
from agent.civic_assistant.analyst import core
agencies = __import__("ui.civic_agencies", fromlist=["_"])
together = __import__("ui.civic_together", fromlist=["_"])
meetings = __import__("ui.civic_meetings", fromlist=["_"])
calendar = __import__("engine.civic_geo.works_calendar", fromlist=["_"])
akim = __import__("ui.civic_akim", fromlist=["_"])
db = sys.argv[1]
agencies.make_service(db)
together.make_service(db)
meetings.make_service(db)
core.configure(provider=None, rate=(1000, 60.0))
staff = {"username": "operator", "role": "editor"}
board = agencies.board_snapshot(30, None)
totals = board.get("totals") or {}
# Итог табло, который аналитик называет «просрочено»: срок исправления R08, без R08 — срок ответа; табло без записей
# (в тесте нет связки R01 с жалобами R09) — аналитик честно считает по срокам «Картины дня» R08.
late = totals.get("overdue_fix") if totals.get("overdue_fix") is not None else totals.get("overdue")
expect = {
    "Какие службы отстают?": ("lagging_services", akim.summary()["overdue"]["count"] if board.get("empty") else late, 1),
    "Где копаем дважды?": ("work_conflicts", calendar.conflicts_summary(None)["conflicts"], 0),
    "Какие инициативы жителей?": ("initiatives", together.initiatives_summary(None)["upcoming"], 0),
    "Что поручили на встречах с жителями?": ("meeting_orders", meetings.board_block(district=None)["counts"]["total"], 0),
}
rows = []
for question, (kind, value, index) in expect.items():
    b = next(x for x in api.ask(question, "ru", staff)["blocks"] if x["kind"] == kind)
    got = b["numbers"][index]["value"] if b["status"] == "ok" and len(b["numbers"]) > index else None
    rows.append({"q": question, "kind": kind, "status": b["status"], "role": b["source"]["role"], "value": value,
                 "got": got, "lines": b["lines"]["ru"][:2]})
crisis = next(x for x in api.ask("Что с бураном?", "ru", staff)["blocks"] if x["kind"] == "crisis")
print(json.dumps({"rows": rows, "board_empty": bool(board.get("empty")), "crisis_role": crisis["source"]["role"]},
                 ensure_ascii=False))
"""


def test_real_neighbours_if_present(tmp_path):
    agencies, together, meetings = _real("ui.civic_agencies"), _real("ui.civic_together"), _real("ui.civic_meetings")
    calendar = _real("engine.civic_geo.works_calendar")
    if not all(hasattr(m, n) for m, n in ((agencies, "board_snapshot"), (agencies, "active_incidents"),
                                          (together, "initiatives_summary"), (meetings, "board_block"),
                                          (calendar, "conflicts_summary"))):
        pytest.skip("NOT_RUN: функции соседей «для R03» ещё не в сборке")
    env = dict(os.environ, CIVIC_DEMO="1")
    env.pop("CIVIC_DEMO_WORLD", None)
    env.pop("CIVIC_DB_PATH", None)
    proc = subprocess.run([sys.executable, "-B", "-c", _REAL_CHECK, str(tmp_path / "civic.sqlite3")], cwd=ROOT,
                          env=env, capture_output=True, text=True, timeout=240)
    assert proc.returncode == 0, proc.stderr[-3000:]
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    for row in data["rows"]:
        assert row["status"] in ("ok", "empty"), row
        if row["kind"] == "lagging_services":
            assert row["role"] == ("R08" if data["board_empty"] else "R17"), row
        if row["status"] == "ok":
            assert row["got"] == row["value"], row
    assert data["crisis_role"] == "R17"
