"""Round 12: подключение R08 через load_r08_classifier — проверка контракта до подключения.

Настоящего ml/civic_classifier в этой сборке нет; здесь — подменные модули в sys.modules
(FIXTURE), чтобы проверить поведение адаптера на всех исходах.
"""

import sys
import time
import types

import pytest

from ui.civic_feedback.classifier_adapter import check_suggestion, load_r08_classifier, r08_status


def fake_module(monkeypatch, name, classify):
    module = types.ModuleType(name)
    if classify is not None:
        module.classify = classify
    monkeypatch.setitem(sys.modules, name, module)
    return name


GOOD = {"label": "lighting", "score": 0.61, "score_kind": "uncalibrated_margin", "needs_review": True,
        "model_version": "r08-test-0", "training_data_status": "synthetic"}


def test_contract_conforming_model_is_connected(monkeypatch):
    name = fake_module(monkeypatch, "r06_fake_good", lambda text, language: dict(GOOD))
    status = r08_status(name)
    assert status["available"] and status["model_version"] == "r08-test-0" and status["score_kind"] == "uncalibrated_margin"
    assert load_r08_classifier(name)("текст", "ru")["label"] == "lighting"


@pytest.mark.parametrize("result,reason", [
    ({"label": "potholes"}, "label_not_in_contract"),
    ({"label": "roads", "score": float("nan")}, "score_not_finite_number"),
    ({"label": "roads", "score": True}, "score_not_finite_number"),
    ("roads", "result_not_object"),
    ({"label": "roads", "needs_review": "yes"}, "needs_review_not_bool"),
])
def test_contract_mismatch_is_not_connected(monkeypatch, result, reason):
    name = fake_module(monkeypatch, "r06_fake_bad", lambda text, language: result)
    status = r08_status(name)
    assert status["available"] is False and status["reason"] == "contract_mismatch:" + reason
    assert load_r08_classifier(name) is None


def test_missing_raising_or_hanging_model_is_not_connected(monkeypatch):
    assert load_r08_classifier("ml.r06_definitely_missing_module") is None
    assert r08_status(fake_module(monkeypatch, "r06_fake_none", None))["reason"] == "no_classify_function"

    def boom(text, language):
        raise MemoryError("model too big")
    assert r08_status(fake_module(monkeypatch, "r06_fake_boom", boom))["reason"] == "probe_error:MemoryError"

    def hang(text, language):
        time.sleep(2)
        return dict(GOOD)
    started = time.monotonic()
    assert r08_status(fake_module(monkeypatch, "r06_fake_hang", hang), timeout_s=0.2)["reason"] == "probe_timeout"
    assert time.monotonic() - started < 1.5


def test_check_suggestion_accepts_null_score():
    assert check_suggestion({"label": "other", "score": None, "needs_review": True}) is None
