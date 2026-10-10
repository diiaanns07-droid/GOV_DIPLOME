"""Необязательное подключение классификатора R08 (ml/civic_classifier).

Контракт civic-v1: classify(text, language) -> {label, score|null, score_kind,
needs_review, model_version, training_data_status}. Если модуля нет, импорт падает,
пробный вызов зависает или ответ не соответствует контракту, возвращается None —
FeedbackService сохраняет сообщения без подсказки.

Подсказка модели никогда не меняет категорию жителя и не принимает решение: сотрудник
может подставить её в форму «Категория» и сохранить сам. Некалиброванный score не
выдаётся за вероятность (интерфейс показывает число и score_kind, без процентов).
"""

from __future__ import annotations

import importlib
import logging
import math
import threading

LOGGER = logging.getLogger(__name__)
CONTRACT_LABELS = ("roads", "sidewalks", "transport_stops", "lighting", "landscaping", "other")
PROBE_TEXT = "Не горят фонари во дворе, вечером темно."
PROBE_LANGUAGE = "ru"


def check_suggestion(value) -> str | None:
    """None, если ответ соответствует контракту civic-v1, иначе краткая причина."""
    if not isinstance(value, dict):
        return "result_not_object"
    if value.get("label") not in CONTRACT_LABELS:
        return "label_not_in_contract"
    score = value.get("score")
    if score is not None and not (isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score)):
        return "score_not_finite_number"
    for key in ("score_kind", "model_version", "training_data_status"):
        if value.get(key) is not None and not isinstance(value.get(key), str):
            return f"{key}_not_string"
    if not isinstance(value.get("needs_review", True), bool):
        return "needs_review_not_bool"
    return None


def _probe(classify, timeout_s: float) -> tuple[str | None, dict | None]:
    outcome: dict = {}

    def run():
        try:
            outcome["value"] = classify(PROBE_TEXT, PROBE_LANGUAGE)
        except Exception as exc:  # чужая модель: любая ошибка = модель недоступна
            outcome["error"] = type(exc).__name__

    worker = threading.Thread(target=run, name="civic-r06-classifier-probe", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        return "probe_timeout", None
    if "error" in outcome:
        return "probe_error:" + outcome["error"], None
    problem = check_suggestion(outcome.get("value"))
    return (("contract_mismatch:" + problem) if problem else None), outcome.get("value")


def r08_status(module_name: str = "ml.civic_classifier", *, probe: bool = True, timeout_s: float = 10.0) -> dict:
    """Диагностика без текстов жителей: доступна ли модель и почему нет.

    {available, reason, module, model_version, training_data_status, score_kind}
    """
    status = {"available": False, "reason": None, "module": module_name, "model_version": None,
              "training_data_status": None, "score_kind": None}
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # отсутствие/поломка модели не блокирует обращения
        status["reason"] = "import_failed:" + type(exc).__name__
        return status
    classify = getattr(module, "classify", None)
    if not callable(classify):
        status["reason"] = "no_classify_function"
        return status
    status["classify"] = classify
    if probe:
        problem, value = _probe(classify, timeout_s)
        if problem:
            status["reason"] = problem
            return status
        for key in ("model_version", "training_data_status", "score_kind"):
            status[key] = value.get(key) if isinstance(value.get(key), str) else None
    status["available"] = True
    return status


def load_r08_classifier(module_name: str = "ml.civic_classifier", *, probe: bool = True, timeout_s: float = 10.0):
    """classify(text, language) R08 либо None. Пробный вызов проверяет контракт до подключения."""
    status = r08_status(module_name, probe=probe, timeout_s=timeout_s)
    if not status["available"]:
        LOGGER.info("R08 classifier not connected: %s", status["reason"])
        return None
    LOGGER.info("R08 classifier connected: %s", status.get("model_version") or "version unknown")
    return status["classify"]
