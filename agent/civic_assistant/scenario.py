"""Факты сценарного сравнения (заполняется на этапе CP3).

Пока результат движка не передан, render_scenario возвращает пустой список,
и ответ честно сообщает «нет данных».
"""

from __future__ import annotations


def scenario_facts(result, scenario_id=None):
    return [], ["scenario_adapter_pending"]


def render_scenario(facts, lang, focus="compare"):
    return []
