"""Сверка выдержек r12.quote_found: границы чисел без ложных отказов (исправление раунда 13)."""

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[4] / "data/civic/astana/round12-verified/tools/r12.py"


@pytest.fixture(scope="module")
def r12():
    spec = importlib.util.spec_from_file_location("r05_r12_quote_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def found(r12, quote, text):
    return r12.quote_found(quote, r12.norm_text(r12.page_text(text)))


def test_sentence_after_a_date_in_previous_block_is_found(r12):
    page = "<p>Опубликовано: 18 июля 2026</p><p>В Астане с 20 июля будет закрыт участок улицы Алматы.</p>"
    assert found(r12, "В Астане с 20 июля будет закрыт участок", page)


@pytest.mark.parametrize("quote,text", [
    ("125 000 000 тенге", "стоимость 1 125 000 000 тенге"),        # число внутри большего числа
    ("250 000", "выделено 250 000 000 тенге"),                       # обрезанный хвост числа
    ("1 ноября", "с 21 ноября 2026 года"),                           # день внутри другого дня
    ("до 2026", "до 2026 1 квартала"),                               # цифра сразу после выдержки
])
def test_numbers_are_still_matched_whole(r12, quote, text):
    assert not found(r12, quote, text)


def test_quote_ending_with_a_word_may_be_followed_by_a_number(r12):
    assert found(r12, "Ремонт продлится до конца года", "Ремонт продлится до конца года 5 бригадами.")


def test_empty_quote_is_never_found(r12):
    assert not found(r12, "   ", "любой текст")
