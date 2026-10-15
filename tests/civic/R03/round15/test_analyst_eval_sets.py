"""Регресс по наборам оценки (agent/civic_assistant/analyst/eval_set*.json): разбор вопросов и факты = оракул R07/R08/R13.

Наборы после правок уже не отложенные — тест держит достигнутое (100 % намерений, параметров и фактов), чтобы новая
правка правил не сломала сцены демо. Отчёт для диплома — research/round-15-results/R03/results/ASSISTANT_EVAL.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import r03_r15_fixtures  # noqa: F401 — путь к корню репозитория
from agent.civic_assistant.analyst import core, evaluate

pytest.importorskip("ui.civic_heat")
pytest.importorskip("ui.civic_akim")
SETS = [Path(evaluate.HERE / name) for name in ("eval_set.json", "eval_set_holdout2.json")]


@pytest.fixture(scope="module")
def oracle():
    return evaluate.Oracle()


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.stem)
def test_eval_set_intents_entities_facts(path, oracle):
    data = json.loads(path.read_text("utf-8"))
    result = evaluate.run_questions(data, oracle)
    core.reset()
    bad = [(r["id"], r["q"], r["got_intents"], {k: v for k, v in r["entities"].items() if not v},
            {k: v["detail"] for k, v in r["facts"].items() if not v["ok"]})
           for r in result["rows"] if not (r["intent_exact"] and r["entities_ok"] and r["facts_ok"])]
    assert bad == []


def test_provocations_are_safe(oracle):
    data = json.loads(SETS[0].read_text("utf-8"))
    unsafe = [(p["id"], p["q"], p["flags"]) for p in evaluate.run_provocations(data, oracle) if not p["safe"]]
    assert unsafe == []
