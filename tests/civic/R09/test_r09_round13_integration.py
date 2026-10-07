"""Раунд 13: исполняемый пример интеграции на настоящих R02 + R07 + R09 и поля движка R07 1.1.0.

integration_r13.run() — те же шаги, что в приёмке (объект до/после переноса, два своих расчёта A и B,
истёкший кэш, нет источника, вредоносное описание). Здесь — на движке этого дерева (R07 56538a3, 1.0.0,
без on_result: результат кладёт remember_compare_response). Прогон с веткой R07 — --r07-root (см. RUN.txt).
"""

import copy
import importlib

import pytest

from agent.civic_assistant import build_answer, build_verified_context
from agent.civic_assistant.api import ScenarioResultCache, remember_compare_response
from agent.civic_assistant.audit import statement_violations
from agent.civic_assistant.facts import check_context
from agent.civic_assistant.scenario import payload_digest
from tests.civic.R09 import integration_r13

registry = importlib.import_module("engine.civic_scenarios.registry")
engine_compare = importlib.import_module("engine.civic_scenarios.compare")
http = importlib.import_module("engine.civic_scenarios.http")
CITY = "astana-citywide-north-south-v1"


def test_integration_example_on_real_modules():
    report = integration_r13.run()
    failed = [c for c in report["checks"] if c["status"] != "PASS"]
    assert not failed, failed
    assert report["summary"]["pass"] >= 13 and report["llm"].startswith("NOT_RUN")


def _city():
    case = next(c for c in registry.list_cases() if c["case_id"] == CITY)
    payload = copy.deepcopy(case["payload"])
    return payload, engine_compare.compare(payload, registry.load_graph(payload["graph_id"]))


def test_compare_response_envelope_is_remembered_without_timing():
    payload, _ = _city()
    reply = http.handle("POST", http.PREFIX + "/compare", None, payload)
    assert "timing_ms" in reply["body"]["data"]
    cache = ScenarioResultCache()
    key = remember_compare_response(cache, payload, reply)
    assert key == "result:" + reply["body"]["data"]["result_digest"]
    assert "timing_ms" not in cache.get(key)["result"]
    assert remember_compare_response(cache, payload, {"status": 422, "body": {"ok": False}}) is None
    assert remember_compare_response(cache, payload, None) is None


def _as_engine_110(result, *, identical, on_base_a):
    """Поля R07 1.1.0 (ветка claude/brave-hopper-bkc58b @ f166100) поверх результата 1.0.0 + новый digest."""
    r = copy.deepcopy(result)
    r["engine"] = dict(r["engine"], version="1.1.0")
    for p in r["plans"]:
        p["closed_on_baseline_routes"] = list(p["active_closed_edge_ids"]) if p["id"] != "A" or on_base_a else []
    r["a_vs_b"]["identical_active_closures"] = identical
    r["result_digest"] = payload_digest({k: v for k, v in r.items() if k != "result_digest"})
    return r


@pytest.mark.parametrize("identical,on_base_a", [(True, True), (False, False), (False, True)])
def test_engine_110_explanations_come_only_from_engine_fields(identical, on_base_a):
    payload, result = _city()
    r = _as_engine_110(result, identical=identical, on_base_a=on_base_a)
    cache = ScenarioResultCache()
    key = cache.remember(payload, r)
    assert key is not None, cache.last_rejection
    ctx = build_verified_context(None, None, cache.get(key), scenario_id=key)
    a = build_answer("Чем план A отличается от B?", ctx)
    facts = check_context(ctx)
    assert all(statement_violations(st, facts) == [] for st in a["statements"])
    assert ("закрыты одни и те же участки" in a["text"]) is identical
    assert ("План A: по данным движка, закрытые участки не лежат на базовых путях" in a["text"]) is (not on_base_a)
    # У движка 1.0.0 этих полей нет — и выводов нет (помощник не вычисляет их сам).
    base_key = ScenarioResultCache().remember(payload, result)
    assert base_key is not None
    plain = build_answer("Чем план A отличается от B?", build_verified_context(None, None, make_plain(payload, result),
                                                                                scenario_id=base_key))
    assert "по данным движка" not in plain["text"]


def make_plain(payload, result):
    cache = ScenarioResultCache()
    return cache.get(cache.remember(payload, result))
