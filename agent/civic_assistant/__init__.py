"""Помощник civic-v1 по проверенным фактам (раунд 11, роль R09).

Публичный API модуля:
    build_verified_context(item, history, scenario, audience="public") -> context
    build_answer(question, verified_context, provider=None) -> answer
Числа, даты и формулировки собирает код; провайдер (если подключён) выбирает
только тип ответа и ID фактов из каталога.
"""

from agent.civic_assistant.answer import AssistantInputError, build_answer, unavailable_answer
from agent.civic_assistant.facts import FACTS_VERSION, ContextError, build_verified_context

__all__ = ["AssistantInputError", "ContextError", "FACTS_VERSION", "build_answer", "build_verified_context",
           "unavailable_answer"]
