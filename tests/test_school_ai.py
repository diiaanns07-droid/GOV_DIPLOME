"""AI seam of the school case: the model only picks fact IDs/intents/tools; everything else is refused → labelled fallback."""
import json
from types import SimpleNamespace

import pytest

from agent import school_ai

DIGEST = "sha256:" + "a" * 64


def request(**over):
    body = {"schema_version": "school-ai-request-v1", "request_id": "r-1", "case_digest": DIGEST,
            "question": "Какой вариант лучше, A или B?", "views": ["current", "A", "B"], "origin_ids": ["p1a", "p2b"],
            "facts": [{"id": f"{p}/{m}", "metric": m, "value": 1, "unit": "mm", "plan_id": p, "origin_id": None}
                      for p in ("current", "A", "B") for m in ("mean_distance_mm", "within_threshold_count", "max_distance_mm", "unknown_count")]}
    body.update(over)
    return body


class FakeClient:
    def __init__(self, content):
        self.content, self.calls = content, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])

    def close(self):
        pass


def run(monkeypatch, content, settings=None):
    monkeypatch.setattr(school_ai, "_settings", lambda: settings or {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"})
    fake = FakeClient(content)
    return school_ai.answer(request(), client_factory=lambda s: fake), fake


def test_valid_model_choice_is_bound_to_request_and_digest(monkeypatch):
    out, fake = run(monkeypatch, json.dumps({"intent": "compare_variants", "fact_ids": ["A/mean_distance_mm", "B/mean_distance_mm"],
                                             "tool_calls": [{"name": "show_view", "args": {"view": "B"}}], "needs_clarification": None}))
    assert out["source"] == "model" and out["request_id"] == "r-1" and out["case_digest"] == DIGEST
    assert out["fact_ids"] == ["A/mean_distance_mm", "B/mean_distance_mm"]
    sent = json.loads(fake.calls[0]["messages"][1]["content"])
    assert all("value" not in f for f in sent["facts"])  # the model gets IDs/metrics, not values to restate
    assert "test-key" not in json.dumps(out)


@pytest.mark.parametrize("content,code", [
    ("not json", "model_not_json"),
    (json.dumps({"intent": "compare_variants", "fact_ids": ["A/invented"], "tool_calls": [], "needs_clarification": None}), "model_unknown_fact"),
    (json.dumps({"intent": "compare_variants", "fact_ids": [], "tool_calls": [], "needs_clarification": None, "text": "B лучше на 300 м"}), "model_schema"),
    (json.dumps({"intent": "build_school", "fact_ids": [], "tool_calls": [], "needs_clarification": None}), "model_schema"),
    (json.dumps({"intent": "compare_variants", "fact_ids": [], "tool_calls": [{"name": "apply_plan", "args": {}}], "needs_clarification": None}), "model_tool"),
    (json.dumps({"intent": "point_detail", "fact_ids": [], "tool_calls": [{"name": "select_origin", "args": {"origin_id": "zzz"}}], "needs_clarification": None}), "model_tool"),
    (json.dumps({"intent": "compare_variants", "fact_ids": [], "tool_calls": [], "needs_clarification": "Сравнить 300 м?"}), "model_schema"),
])
def test_invalid_model_output_falls_back(monkeypatch, content, code):
    out, _ = run(monkeypatch, content)
    assert out["source"] == "fallback" and out["reason_code"] == code
    assert set(out["fact_ids"]) <= {f["id"] for f in request()["facts"]}


def test_missing_provider_is_labelled_fallback(monkeypatch):
    monkeypatch.setattr(school_ai, "_settings", lambda: {"OPENAI_API_KEY": "", "OPENAI_MODEL": ""})
    out = school_ai.answer(request())
    assert out["source"] == "fallback" and out["reason_code"] == "missing_key" and out["model"] is None


def test_provider_error_text_is_not_leaked(monkeypatch):
    monkeypatch.setattr(school_ai, "_settings", lambda: {"OPENAI_API_KEY": "secret-123", "OPENAI_MODEL": "m"})

    def boom(settings):
        raise RuntimeError("401 for key secret-123 at https://internal")
    out = school_ai.answer(request(), client_factory=boom)
    assert out["source"] == "fallback" and out["reason_code"] == "api_error"
    assert "secret-123" not in json.dumps(out) and "internal" not in json.dumps(out)


@pytest.mark.parametrize("over", [{"case_digest": "sha256:xyz"}, {"request_id": ""}, {"facts": []}, {"question": "x" * 700},
                                  {"schema_version": "v0"}, {"views": ["C"]}])
def test_bad_requests_are_refused(over):
    with pytest.raises(school_ai.SchoolAIError):
        school_ai.validate_request(request(**over))


def test_fallback_keywords():
    req = school_ai.validate_request(request(question="Сколько стоит построить школу?"))
    assert school_ai.fallback_choice(req)["intent"] == "data_limits"
    req = school_ai.validate_request(request(question="Это по прямой или по улицам?"))
    assert school_ai.fallback_choice(req)["intent"] == "method"
