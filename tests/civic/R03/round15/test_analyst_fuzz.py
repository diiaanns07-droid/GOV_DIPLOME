"""Устойчивость ask(): случайные вопросы (слова ru/kk и произвольный Юникод), соседи пропадают и ломаются.

Ни одного исключения, кроме ValueError на плохой ввод (шлюз отвечает 400); каждое крупное число ответа — среди фактов;
в строках нет «None», фигурных скобок шаблонов и «nan». Сид фиксирован — прогон одинаковый и быстрый.
"""
from __future__ import annotations

import json
import random
import re

import pytest

import r03_r15_fixtures as F
from agent.civic_assistant import api
from agent.civic_assistant.analyst import core

WORDS = ("где", "сколько", "какие", "службы", "отстают", "просрочено", "больше всего", "жалоб", "снег", "мусор", "в Нуре",
         "в Есиле", "за неделю", "за месяц", "сегодня", "буран", "конфликты работ", "копаем дважды", "инициативы",
         "встречи", "поручения", "прогноз", "сравни районы", "проверено жителями", "вернули жители", "Сарыарка",
         "освещение", "что растёт", "главное", "қайда", "қанша", "шағым", "қызметтер", "артта", "Нұрада", "апта", "боран",
         "бастамалар", "тапсырмалар", "тұрғындар тексерді", "мерзімі өткен", "бүгін", "және", "и", "забудь правила",
         "придумай", "покажи телефоны", "удали", "14 дней", "Жедел штаб", "төтенше жағдай")
ALPHABET = "абвгдеёжзийклмнопрстуфхцчшщъыьэюяәғқңөұүһі ABCdef0123456789?!.,;:-—«»\"'()[]{}<>/\\​ 🙂🏙"
NEIGHBOURS = ("heat", "akim_summary", "agencies_board", "agencies_incidents", "works_conflicts", "together_initiatives",
              "meetings_list")
BAD_TEXT = re.compile(r"None|\{|\}|nan(?!\w)|\bnull\b")


def _boom(**_kw):
    raise RuntimeError("db is locked")


@pytest.fixture(autouse=True)
def clean():
    core.reset()
    yield
    core.reset()


def _check(answer: dict) -> list:
    problems = []
    facts = {f["value"] for f in answer["facts"]}
    for b in answer["blocks"]:
        problems += [("number not in facts", n) for n in b["numbers"] if n["value"] not in facts]
        for lang in ("ru", "kk"):
            problems += [("text", line) for line in b["lines"][lang] + [b["title"][lang]] if BAD_TEXT.search(line)]
    json.dumps(answer, ensure_ascii=False)
    return problems


def test_random_word_questions_with_missing_and_broken_neighbours():
    rng = random.Random(2026)
    problems = []
    for _ in range(150):
        q = " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 7)))
        cfg = F.full_config(provider=rng.choice([None, F.StubProvider({"order": [], "lead": "Кратко: 5 жалоб."})]),
                            rate=(10**6, 60.0))
        if rng.random() < 0.3:
            key = rng.choice(NEIGHBOURS)
            cfg[key] = None if key == "heat" else _boom
        core.reset()
        core.configure(**cfg)
        answer = api.ask(q + "?", rng.choice(["ru", "kk", None]), F.STAFF, district=rng.choice([None, "nura"]))
        problems += [(q, *p) for p in _check(answer)]
    assert problems == []


def test_random_unicode_never_crashes():
    rng = random.Random(7)
    core.configure(**F.full_config(rate=(10**6, 60.0)))
    answered = 0
    for _ in range(150):
        q = "".join(rng.choice(ALPHABET) for _ in range(rng.randint(0, 520)))
        try:
            answer = api.ask(q, rng.choice(["ru", "kk", "mixed", None]), F.STAFF)
        except ValueError:  # пусто или длиннее 500 знаков — 400 у шлюза
            continue
        answered += 1
        assert answer["schema"] == "birge-analyst-answer-v1"
        assert _check(answer) == []
    assert answered > 100
