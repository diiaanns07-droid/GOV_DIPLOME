"""CP3: факты сценария R07 и безопасный обработчик POST /assistant."""

import copy
import json
from pathlib import Path

import pytest

from agent.civic_assistant import build_answer, build_verified_context
from agent.civic_assistant.api import ASSISTANT_PATH, AssistantEndpoint, RateLimiter, r02_public_loader, r07_case_loader
from agent.civic_assistant.audit import statement_violations
from agent.civic_assistant.facts import check_context
from agent.civic_assistant.providers import MockProvider

R07 = json.loads((Path(__file__).parent / "fixtures" / "r07_synthetic_result.json").read_text(encoding="utf-8"))
RESULT = R07["result"]
SID = R07["_provenance"]["case_id"]


def scenario_ctx(result=RESULT, **kw):
    return build_verified_context(None, None, result, scenario_id=SID, **kw)


def test_scenario_facts_copy_engine_metrics():
    facts = check_context(scenario_ctx())
    assert facts["scenario.baseline.ok"]["value"] == RESULT["baseline"]["status_summary"]["by_status"]["ok"]
    a = next(p for p in RESULT["plans"] if p["id"] == "A")
    assert facts["scenario.A.vs_baseline.mean_delta_m"]["value"] == a["vs_baseline"]["summary"]["mean_delta_m_comparable"]
    assert facts["scenario.AB.lost_within_model"]["value"] == RESULT["a_vs_b"]["summary"]["changes"]["lost_within_model"]
    assert facts["scenario.graph_evidence_type"]["value"] == "synthetic"


def test_ab_explanation_uses_engine_metrics_without_best_claim():
    ans = build_answer("Какой вариант лучше, A или B?", scenario_ctx())
    assert ans["intent"] == "scenario_compare" and ans["source"] == "template"
    text = ans["text"]
    assert "Пар с найденным путём: план A — 5, план B — 3 (всего пар: 12)." in text
    assert "Среднее изменение длины от A к B (сопоставимых пар: 3) — короче на 53,333 м." in text
    assert "Граф сценария синтетический" in text and "не решение городских органов" in text
    for banned in ("лучш", "рекоменд", "оптимал", "время в пути составит", "минут"):
        assert banned not in text.replace("Какой вариант лучше", ""), banned
    assert not [w for w in ans["warnings"] if w.startswith("audit")]


def test_scenario_kazakh_and_audit_clean():
    ctx = scenario_ctx()
    facts = check_context(ctx)
    for q in ("A мен B жоспарын салыстыр", "Өту қалай өзгереді?", "Чем отличаются планы?", "Как изменится проход?"):
        ans = build_answer(q, ctx)
        for st in ans["statements"]:
            assert statement_violations(st, facts) == [], st
    assert build_answer("A мен B жоспарын салыстыр", ctx)["language"] == "kk"


def test_missing_metrics_are_no_data_not_zero():
    broken = copy.deepcopy(RESULT)
    broken["a_vs_b"] = None
    for p in broken["plans"]:
        p["vs_baseline"]["summary"]["mean_delta_m_comparable"] = None
        p["status_summary"]["by_status"].pop("ok")
    ctx = scenario_ctx(broken)
    assert "scenario_metric_missing" in ctx["warnings"]
    ans = build_answer("Сравни A и B", ctx)
    assert "Сравнение A и B движок не вернул — нет данных." in ans["text"]
    assert "нет данных (нет сопоставимых пар)" in ans["text"]
    impact = build_answer("Как изменится проход?", ctx)
    assert "План A: пар с найденным путём — нет данных из 12" in impact["text"]


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r.update(schema_version="civic-scenario-result-v0"), "scenario_schema"),
    (lambda r: r["input"].update(city="shymkent"), "scenario_city"),
])
def test_foreign_or_wrong_scenario_rejected(mutate, code):
    from agent.civic_assistant import ContextError
    bad = copy.deepcopy(RESULT)
    mutate(bad)
    with pytest.raises(ContextError) as exc:
        scenario_ctx(bad)
    assert exc.value.code == code


def test_object_access_question_without_scenario_says_no_data(ctx_of):
    ans = build_answer("Как изменится проезд?", ctx_of("full"))
    assert "Расчёт доступности для этого объекта не подключён — нет данных." in ans["text"]


# --- HTTP handler -------------------------------------------------------------------------------

@pytest.fixture
def endpoint(data):
    published = {"r09-synth-full": (data["objects"]["full"], data["history"]["full"])}

    def load(object_id):
        if object_id == "leaky-draft":  # неисправный загрузчик вернул черновик — второй рубеж должен отказать
            return data["objects"]["draft"], []
        return published.get(object_id)

    return AssistantEndpoint(load, lambda sid: RESULT if sid == SID else None,
                             rate_limiter=RateLimiter(1000, 60))


def post(ep, body, ip="10.0.0.1"):
    return ep.handle("POST", ASSISTANT_PATH, {}, body, {"client_ip": ip, "headers": {}})


def test_answer_envelope_and_object_binding(endpoint):
    resp = post(endpoint, {"question": "Когда закончат?", "object_id": "r09-synth-full", "scenario_id": None})
    assert resp["status"] == 200 and resp["body"]["ok"] is True
    data = resp["body"]["data"]
    assert data["object_id"] == "r09-synth-full" and data["source"] == "template"
    assert data["context_digest"].startswith("sha256:") and data["facts_version"] == "civic-assistant-facts-v1"
    assert resp["headers"]["Cache-Control"] == "no-store"


@pytest.mark.parametrize("body,status,code", [
    ({"question": "Когда?", "object_id": "r09-synth-full", "facts": [{"id": "x", "value": 1}]}, 400, "unexpected_fields"),
    ({"question": "Когда?", "object_id": "r09-synth-full", "verified_context": {}}, 400, "unexpected_fields"),
    ({"question": "Когда?", "object_id": "r09-synth-full", "role": "editor"}, 400, "unexpected_fields"),
    (["Когда?"], 400, "invalid_body"),
    ("Когда?", 400, "invalid_body"),
    ({"question": "Когда?", "object_id": 5}, 422, "invalid_id"),
    ({"question": "Когда?", "object_id": "../staff/objects"}, 422, "invalid_id"),
    ({"question": "Когда?", "object_id": "<script>"}, 422, "invalid_id"),
    ({"question": "Когда?"}, 422, "missing_target"),
    ({"question": {"text": "Когда?"}, "object_id": "r09-synth-full"}, 422, "question_type"),
    ({"question": 42, "object_id": "r09-synth-full"}, 422, "question_type"),
    ({"question": "", "object_id": "r09-synth-full"}, 422, "question_empty"),
    ({"question": "?" * 501, "object_id": "r09-synth-full"}, 413, "question_too_long"),
    ({"question": "a" * 100000, "object_id": "r09-synth-full"}, 413, "question_too_long"),
])
def test_bad_requests_are_json_errors(endpoint, body, status, code):
    resp = post(endpoint, body)
    assert resp["status"] == status and resp["body"]["ok"] is False and resp["body"]["error"]["code"] == code


def test_methods_and_paths(endpoint):
    assert endpoint.handle("GET", ASSISTANT_PATH, {}, None, {})["status"] == 405
    assert endpoint.handle("POST", "/api/civic/v1/objects", {}, {}, {}) is None
    # шлюз R01 передаёт относительный путь
    rel = endpoint.handle("POST", "/assistant", {}, {"question": "Когда?", "object_id": "r09-synth-full"},
                          {"client_ip": "1.2.3.4", "headers": {}})
    assert rel["status"] == 200 and rel["body"]["data"]["object_id"] == "r09-synth-full"


def test_draft_and_missing_are_indistinguishable(endpoint):
    a = post(endpoint, {"question": "Что здесь?", "object_id": "r09-synth-draft"})["body"]["data"]
    b = post(endpoint, {"question": "Что здесь?", "object_id": "no-such-object"})["body"]["data"]
    assert a["source"] == b["source"] == "unavailable" and a["text"] == b["text"]
    leaked = post(endpoint, {"question": "Сколько стоит?", "object_id": "leaky-draft"})["body"]["data"]
    assert leaked["source"] == "unavailable" and "999" not in leaked["text"] and "Секретный" not in leaked["text"]
    assert leaked["warnings"] == ["object_not_public"]


def test_scenario_only_and_missing_scenario(endpoint):
    d = post(endpoint, {"question": "Сравни A и B", "scenario_id": SID})["body"]["data"]
    assert d["scenario_id"] == SID and d["intent"] == "scenario_compare" and d["object_id"] is None
    d = post(endpoint, {"question": "Сравни A и B", "scenario_id": "unknown-case"})["body"]["data"]
    assert d["source"] == "unavailable"
    d = post(endpoint, {"question": "Когда?", "object_id": "r09-synth-full", "scenario_id": "unknown-case"})["body"]["data"]
    assert d["source"] == "template" and "scenario_not_found" in d["warnings"]


def test_rate_limit_429():
    t = [0.0]
    ep = AssistantEndpoint(lambda oid: None, rate_limiter=RateLimiter(2, 60, clock=lambda: t[0]))
    body = {"question": "Когда?", "object_id": "x1"}
    assert post(ep, body)["status"] == 200 and post(ep, body)["status"] == 200
    assert post(ep, body)["status"] == 429
    assert post(ep, body, ip="10.0.0.2")["status"] == 200
    t[0] = 61.0
    assert post(ep, body)["status"] == 200


def test_store_exception_is_not_leaked():
    def boom(oid):
        raise RuntimeError("sqlite at /secret/.runtime/civic.db locked")
    ep = AssistantEndpoint(boom, rate_limiter=RateLimiter(100, 60))
    d = post(ep, {"question": "Когда?", "object_id": "x1"})["body"]["data"]
    assert d["source"] == "unavailable" and "secret" not in json.dumps(d)


def test_provider_path_through_endpoint(data):
    prov = MockProvider([{"intent": "responsible", "fact_ids": ["responsible.organization"]}])
    ep = AssistantEndpoint(lambda oid: (data["objects"]["full"], data["history"]["full"]), provider=prov,
                           rate_limiter=RateLimiter(100, 60))
    d = post(ep, {"question": "Кто ведёт работы?", "object_id": "r09-synth-full"})["body"]["data"]
    assert d["source"] == "llm" and "Синтетическая организация-заказчик (тест)" in d["text"]


class FakeR02:
    def __init__(self, item, history, prefix="/api/civic/v1"):
        self.calls = []
        self.item, self.history, self.prefix = item, history, prefix

    def handle(self, method, path, query, body, context):
        self.calls.append((method, path, context))
        if not path.startswith(self.prefix + "/"):
            return None
        if path == self.prefix + "/objects/r09-synth-full":
            return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"item": self.item, "history": self.history}}}
        return {"status": 404, "headers": {}, "body": {"ok": False, "error": {"code": "not_found", "message": ""}}}


def test_r02_loader_uses_public_route_without_session(data):
    svc = FakeR02(data["objects"]["full"], data["history"]["full"])
    load = r02_public_loader(svc)
    item, history = load("r09-synth-full")
    assert item["id"] == "r09-synth-full" and load("r09-synth-draft") is None
    for method, path, ctx in svc.calls:
        assert method == "GET" and "/staff/" not in path and not ctx.get("cookies") and "Cookie" not in ctx["headers"]
    rel = FakeR02(data["objects"]["full"], data["history"]["full"], prefix="")
    assert r02_public_loader(rel)("r09-synth-full")[0]["id"] == "r09-synth-full"


def test_r07_case_loader_uses_server_payload():
    calls = []
    cases = [{"case_id": SID, "payload": {"graph_id": "g1", "x": 1}}]
    load = r07_case_loader(lambda: cases, lambda gid: ("graph", gid), lambda p, g: calls.append((p, g)) or RESULT)
    assert load(SID) is RESULT and load(SID) is RESULT and len(calls) == 1
    assert calls[0] == ({"graph_id": "g1", "x": 1}, ("graph", "g1"))
    assert load("other") is None


@pytest.mark.parametrize("bad", [("only-one",), "string", {"item": {}}, (None, None, None)])
def test_malformed_loader_result_is_unavailable(bad):
    ep = AssistantEndpoint(lambda oid: bad, rate_limiter=RateLimiter(100, 60))
    d = post(ep, {"question": "Когда?", "object_id": "x1"})["body"]["data"]
    assert d["source"] == "unavailable"
