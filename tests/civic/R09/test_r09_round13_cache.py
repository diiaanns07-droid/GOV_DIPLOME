"""Раунд 13: контракт пользовательского результата сравнения (scenario_id = "result:" + result_digest).

Всё считается настоящим движком engine.civic_scenarios из этого же дерева (база 56538a3):
- в кэш попадает только проверенный ответ движка на этот вход (digest, вход, согласованность итогов);
- запись компактная (без edge_ids/node_ids маршрутов), а факты из неё те же, что из полного результата;
- лимиты: число записей, TTL, размер одной записи, общий объём; истёкший и неизвестный различаются;
- отсутствующий/истёкший результат -> «выполните сравнение заново», а не подготовленный кейс;
- «ваш расчёт» и «подготовленный пример» не смешиваются ни в контексте, ни в тексте ответа.
"""

import copy
import importlib
import json

import pytest

from agent.civic_assistant import build_answer, build_verified_context
from agent.civic_assistant.api import ASSISTANT_PATH, AssistantEndpoint, RateLimiter, ScenarioResultCache, \
    r07_case_loader
from agent.civic_assistant.audit import statement_violations
from agent.civic_assistant.facts import ContextError, check_context
from agent.civic_assistant.scenario import (INPUT_SCHEMA, make_entry, payload_digest, scenario_facts,
                                            verify_user_result)

registry = importlib.import_module("engine.civic_scenarios.registry")
engine_compare = importlib.import_module("engine.civic_scenarios.compare")
CITY = "astana-citywide-north-south-v1"
K03 = "k03-astana-demo-v1"
TINY = "synthetic-tiny-v1-demo"
CTX = {"client_ip": "127.0.0.1", "headers": {}}
OWN_FACTS = ("scenario.kind", "scenario.result_ref", "scenario.stored_at")


def _raw(case_id, **changes):
    case = next(c for c in registry.list_cases() if c["case_id"] == case_id)
    payload = copy.deepcopy(case["payload"])
    payload.update(changes)
    return payload, engine_compare.compare(payload, registry.load_graph(payload["graph_id"]))


@pytest.fixture(scope="module")
def city():
    return _raw(CITY)


@pytest.fixture(scope="module")
def tiny():
    return _raw(TINY)


def _redigest(result):
    """Подделка «с пересчитанным digest»: digest — контроль целостности, не подпись (см. INTEGRATION)."""
    result["result_digest"] = payload_digest({k: v for k, v in result.items() if k != "result_digest"})
    return result


def _ask(ep, question, scenario_id, object_id=None):
    resp = ep.handle("POST", ASSISTANT_PATH, {}, {"question": question, "object_id": object_id,
                                                  "scenario_id": scenario_id}, CTX)
    assert resp["status"] == 200
    return resp["body"]["data"]


# ---- remember(): только проверенный ответ движка на этот вход ----

def test_tampered_metric_without_new_digest_is_rejected(city):
    payload, result = city
    bad = copy.deepcopy(result)
    bad["baseline"]["routes"][0]["length_m"] += 100
    assert verify_user_result(payload, bad) == "result_digest_mismatch"
    cache = ScenarioResultCache()
    assert cache.remember(payload, bad) is None and cache.last_rejection == "result_digest_mismatch"
    assert cache.stats()["items"] == 0 and cache.stats()["rejections"] == {"result_digest_mismatch": 1}


def test_input_fields_must_match_the_payload(city):
    payload, result = city
    for key, value in (("mode", "driving"), ("analysis_at", "2026-10-07T10:00:00+05:00"),
                       ("graph_id", "other-graph"), ("origin_node_ids", ["0"])):
        bad = copy.deepcopy(result)
        bad["input"][key] = value
        assert verify_user_result(payload, _redigest(bad)) == "input_mismatch:" + key


def test_totals_must_agree_with_input(city, tiny):
    payload, result = city
    bad = copy.deepcopy(result)
    bad["baseline"]["status_summary"]["by_status"]["ok"] += 1
    assert verify_user_result(payload, _redigest(bad)) == "totals_mismatch:baseline"
    bad = copy.deepcopy(result)
    bad["plans"][0]["vs_baseline"]["summary"]["changes"]["longer"] += 1
    assert verify_user_result(payload, _redigest(bad)).startswith("totals_mismatch:plan_")
    bad = copy.deepcopy(result)
    bad["a_vs_b"]["summary"]["comparable_pairs"] += 1
    assert verify_user_result(payload, _redigest(bad)) == "totals_mismatch:a_vs_b"
    bad = copy.deepcopy(result)
    bad["a_vs_b"] = None
    assert verify_user_result(payload, _redigest(bad)) == "totals_mismatch:a_vs_b"
    # Пары = отправления × назначения (у tiny 2 × 6 = 12) — неполный список маршрутов не принимается.
    payload_t, result_t = tiny
    assert verify_user_result(payload_t, result_t) is None
    bad = copy.deepcopy(result_t)
    bad["baseline"]["routes"].pop()
    assert verify_user_result(payload_t, _redigest(bad)) == "totals_mismatch:baseline"


def test_plans_of_another_payload_are_rejected(city):
    payload, result = city
    bad = copy.deepcopy(result)
    bad["plans"] = [p for p in bad["plans"] if p["id"] == "A"]
    bad["a_vs_b"] = None
    assert verify_user_result(payload, _redigest(bad)) == "plans_mismatch"


def test_http_timing_field_outside_digest_is_accepted(city):
    payload, result = city
    with_timing = dict(result, timing_ms=12.5)  # HTTP-адаптер R07 добавляет его после расчёта digest
    assert verify_user_result(payload, with_timing) is None
    assert ScenarioResultCache().remember(payload, with_timing) == "result:" + result["result_digest"]


# ---- компактная запись: размер меньше, факты те же ----

@pytest.mark.parametrize("case_id", [CITY, K03, TINY])
def test_slim_entry_gives_the_same_facts_as_the_full_result(case_id):
    payload, result = _raw(case_id)
    full = {"schema": INPUT_SCHEMA, "result": result, "payload": payload, "graph": None}
    entry = make_entry(result, payload, None, kind="prepared_case")
    f_full, w_full = scenario_facts(full, case_id)
    f_slim, w_slim = scenario_facts(entry, case_id)
    assert [f for f in f_slim if f["id"] not in OWN_FACTS] == f_full and w_slim == w_full
    raw_size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    slim_size = len(json.dumps(entry, ensure_ascii=False).encode("utf-8"))
    assert slim_size < raw_size / 2, (slim_size, raw_size)
    for route in entry["result"]["baseline"]["routes"] + [r for p in entry["result"]["plans"] for r in p["routes"]]:
        assert "edge_ids" not in route and "node_ids" not in route


def test_oversized_entry_is_rejected_not_truncated(city):
    payload, result = city
    cache = ScenarioResultCache(max_entry_bytes=1024)
    assert cache.remember(payload, result) is None and cache.last_rejection == "entry_too_large"
    # Сервер посчитал, но не сохранил: «не сохранён», а не «не найден» (иначе клиент пересчитывал бы по кругу).
    assert cache.status("result:" + result["result_digest"]) == "rejected"
    assert cache.status("result:" + "e" * 64) == "unknown"
    ep = AssistantEndpoint(lambda oid: None, load_scenario_result=r07_case_loader(
        registry.list_cases, registry.load_graph, engine_compare.compare, result_cache=cache),
        rate_limiter=RateLimiter(100, 60))
    data = _ask(ep, "Сравни планы", "result:" + result["result_digest"])
    assert data["source"] == "unavailable" and "scenario_result_not_stored" in data["warnings"]
    assert "не сохранил для объяснения" in data["text"] and "Без перекрытий" not in data["text"]


def test_total_bytes_limit_evicts_oldest_and_marks_it_expired(tiny):
    variants = [_raw(TINY, analysis_at=f"2026-10-07T09:{m:02d}:00+05:00") for m in (1, 2, 3)]
    probe = ScenarioResultCache()
    probe.remember(*variants[0])
    one = probe.stats()["bytes"]
    cache = ScenarioResultCache(max_total_bytes=int(one * 2.5))
    keys = [cache.remember(*v) for v in variants]
    assert None not in keys and len(set(keys)) == 3
    assert cache.status(keys[0]) == "expired" and cache.get(keys[0]) is None
    assert cache.get(keys[1]) is not None and cache.get(keys[2]) is not None
    stats = cache.stats()
    assert stats["items"] == 2 and stats["bytes"] <= int(one * 2.5) and stats["tombstones"] == 1


def test_same_result_twice_is_one_entry(city):
    cache = ScenarioResultCache()
    assert cache.remember(*city) == cache.remember(*city)
    assert cache.stats()["items"] == 1


def test_stored_entry_is_detached_from_the_caller(city):
    payload, result = city
    cache = ScenarioResultCache(wall_clock=lambda: "2026-10-07T09:30:00+05:00")
    key = cache.remember(payload, result)
    entry = cache.get(key)
    assert entry["stored_at"] == "2026-10-07T09:30:00+05:00" and entry["kind"] == "user_result"
    mutated = copy.deepcopy(result)
    key2 = cache.remember(payload, mutated)
    mutated["input"]["mode"] = "driving"
    mutated["graph_coverage"]["known_access_share_by_length"] = 0.99
    assert key2 == key and cache.get(key)["result"]["input"]["mode"] == result["input"]["mode"]
    assert cache.get(key)["result"]["graph_coverage"] == result["graph_coverage"]


# ---- отсутствующий / истёкший результат: пересчёт, а не подготовленный кейс ----

def test_missing_result_is_never_replaced_by_a_prepared_case(city):
    payload, result = city
    load = r07_case_loader(registry.list_cases, registry.load_graph, engine_compare.compare,
                           result_cache=ScenarioResultCache())
    prepared = load(CITY)  # тот же вход, что и у «пользователя»: digest совпадает с подготовленным кейсом
    assert prepared["kind"] == "prepared_case" and prepared["result_digest"] == result["result_digest"]
    key = "result:" + result["result_digest"]
    assert load(key) is None and load.status(key) == "unknown"
    ep = AssistantEndpoint(lambda oid: None, load_scenario_result=load, rate_limiter=RateLimiter(100, 60))
    data = _ask(ep, "Сравни планы A и B", key)
    assert data["source"] == "unavailable" and "scenario_result_unknown" in data["warnings"]
    assert "Выполните сравнение заново" in data["text"] and "путь" not in data["text"]


def test_expired_and_unknown_results_get_different_honest_texts(city, data):
    now = [0.0]
    cache = ScenarioResultCache(ttl_s=60, clock=lambda: now[0])
    load = r07_case_loader(registry.list_cases, registry.load_graph, engine_compare.compare, result_cache=cache)
    key = cache.remember(*city)
    full = data["objects"]["full"]
    ep = AssistantEndpoint(lambda oid: (full, data["history"]["full"]) if oid == full["id"] else None,
                           load_scenario_result=load, rate_limiter=RateLimiter(100, 60))
    assert "Это ваш расчёт" in _ask(ep, "Сравни планы", key)["text"]
    now[0] = 61
    expired = _ask(ep, "Сравни планы", key)
    assert expired["source"] == "unavailable" and "scenario_result_expired" in expired["warnings"]
    assert "больше не хранится" in expired["text"] and "Без перекрытий" not in expired["text"]
    unknown = _ask(ep, "Сравни планы", "result:" + "a" * 64)
    assert "не найден" in unknown["text"] and "scenario_result_unknown" in unknown["warnings"]
    # С объектом: ответ по карточке + честная пометка, что расчёта нет; чисел сценария нет.
    with_obj = _ask(ep, "Когда закончат?", key, object_id=full["id"])
    assert with_obj["statements"][0]["text"].startswith("Сохранённый результат вашего расчёта")
    assert with_obj["scenario_id"] is None and "25.10.2026" in with_obj["text"]
    kk = _ask(ep, "Жоспарларды салыстыр", key)
    assert kk["language"] == "kk" and "Без перекрытий" not in kk["text"]


# ---- «ваш расчёт» и «подготовленный пример» не смешиваются ----

def test_user_result_and_prepared_case_are_labelled_and_audit_clean(city):
    payload, result = city
    cache = ScenarioResultCache(wall_clock=lambda: "2026-10-07T09:30:00+05:00")
    key = cache.remember(payload, result)
    user_ctx = build_verified_context(None, None, cache.get(key), scenario_id=key)
    prep_ctx = build_verified_context(None, None, make_entry(result, payload, None, kind="prepared_case"),
                                      scenario_id=CITY)
    for ctx, lang_q in ((user_ctx, "Сравни планы"), (user_ctx, "Жоспарларды салыстыр"), (prep_ctx, "Сравни планы")):
        a = build_answer(lang_q, ctx)
        facts = check_context(ctx)
        assert all(statement_violations(st, facts) == [] for st in a["statements"])
        assert not [w for w in a["warnings"] if w.startswith("audit")]
    user = build_answer("Сравни планы", user_ctx)["text"]
    prep = build_answer("Сравни планы", prep_ctx)["text"]
    assert "Это ваш расчёт" in user and result["result_digest"][:12] in user and "07.10.2026 09:30" in user
    assert "подготовленный пример" not in user
    assert "Это подготовленный пример сценария, а не ваш расчёт." in prep and "ваш расчёт:" not in prep
    assert "Бұл сіздің есебіңіз" in build_answer("Жоспарларды салыстыр", user_ctx)["text"]


def test_ids_and_entry_kinds_cannot_be_swapped(city, tiny):
    payload, result = city
    cache = ScenarioResultCache()
    key = cache.remember(payload, result)
    user_entry = cache.get(key)
    prepared = make_entry(result, payload, None, kind="prepared_case")
    other_key = "result:" + tiny[1]["result_digest"]
    for entry, sid in ((user_entry, CITY), (prepared, key), (user_entry, other_key)):
        with pytest.raises(ContextError) as exc:
            build_verified_context(None, None, entry, scenario_id=sid)
        assert exc.value.code == "scenario_kind_mismatch"
    forged = dict(user_entry, kind="official_plan")
    with pytest.raises(ContextError):
        build_verified_context(None, None, forged, scenario_id=CITY)
    # Через endpoint: загрузчик, вернувший чужую запись, даёт честный отказ, а не чужие числа.
    ep = AssistantEndpoint(lambda oid: None, load_scenario_result=lambda sid: user_entry,
                           rate_limiter=RateLimiter(100, 60))
    swapped = _ask(ep, "Сравни планы", CITY)
    assert swapped["source"] == "unavailable" and "scenario_kind_mismatch" in swapped["warnings"]
