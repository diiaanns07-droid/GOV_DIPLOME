"""ИИ-аналитик акима «Спросить Birge» (раунд 15, роль R03): вопрос словами → ответ с числами из данных Birge.

    from agent.civic_assistant.api import ask        # маршрут POST /api/civic/v2/assistant/ask (CONTRACT §7)
    ask("Где в Нуре больше всего жалоб на снег за неделю?", lang="ru", principal={"username": "op", "role": "editor"})

Числа считает код (функции модулей-соседей), языковая модель — по желанию и только для порядка блоков и вводной
фразы без чисел. Подробно — core.py; разбор вопроса — intents.py; источники — sources.py; блоки — blocks.py.
"""
from .core import SCHEMA, TooManyQuestions, ask, configure, reset, warm_up

__all__ = ["SCHEMA", "TooManyQuestions", "ask", "configure", "reset", "warm_up"]
