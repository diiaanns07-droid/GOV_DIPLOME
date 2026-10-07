"""Необязательное подключение классификатора R08 (ml/civic_classifier).

Контракт civic-v1: classify(text, language) -> {label, score|null, score_kind,
needs_review, model_version, training_data_status}. Если модуля нет или импорт
падает, возвращается None — FeedbackService сохраняет сообщения без подсказки.
"""

from __future__ import annotations

import importlib
import logging

LOGGER = logging.getLogger(__name__)


def load_r08_classifier(module_name: str = "ml.civic_classifier"):
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # отсутствие/поломка модели не блокирует обращения
        LOGGER.info("R08 classifier unavailable: %s", type(exc).__name__)
        return None
    classify = getattr(module, "classify", None)
    return classify if callable(classify) else None
