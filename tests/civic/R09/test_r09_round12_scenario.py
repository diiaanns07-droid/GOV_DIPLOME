"""Раунд 12: объяснение сравнения A/B только по фактическому результату движка R07.

Числа (длины путей, разницы), интервалы перекрытий, дата снимка OSM и доля неизвестного доступа
берутся из результата compare(), серверного входа сценария и MANIFEST графа — помощник ничего не
пересчитывает (второй движок не строится). Реальный городской кейс считается настоящим движком
engine.civic_scenarios из этого же дерева (база 56538a3).
"""

import copy
import importlib
import json
import re

import pytest

from agent.civic_assistant import build_answer, build_verified_context
from agent.civic_assistant.api import (ASSISTANT_PATH, AssistantEndpoint, RateLimiter, ScenarioResultCache,
                                       r07_case_loader)
from agent.civic_assistant.audit import statement_violations
from agent.civic_assistant.facts import check_context
from agent.civic_assistant.render import fmt_money
from agent.civic_assistant.scenario import ENTRY_SCHEMA, INPUT_SCHEMA, make_entry, payload_digest

registry = importlib.import_module("engine.civic_scenarios.registry")
engine_compare = importlib.import_module("engine.civic_scenarios.compare")
CITY = "astana-citywide-north-south-v1"
TINY = "synthetic-tiny-v1-demo"
BANNED = ("лучш", "рекоменд", "оптимал", "минут", "время в пути составит", "пробки будут", "выброс составит")


@pytest.fixture(scope="module")
def loader():
    cache = ScenarioResultCache()
    load = r07_case_loader(registry.list_cases, registry.load_graph, engine_compare.compare, result_cache=cache)
    load.cache = cache
    return load


@pytest.fixture(scope="module")
def city(loader):
    return loader(CITY)


def _raw(case_id):
    case = next(c for c in registry.list_cases() if c["case_id"] == case_id)
    payload = copy.deepcopy(case["payload"])
    return {"payload": payload, "result": engine_compare.compare(payload, registry.load_graph(payload["graph_id"]))}


@pytest.fixture(scope="module")
def city_raw():
    return _raw(CITY)


@pytest.fixture(scope="module")
def tiny_raw():
    return _raw(TINY)


def _ctx(entry, sid=CITY):
    return build_verified_context(None, None, entry, scenario_id=sid)


def _audit_clean(answer, ctx):
    facts = check_context(ctx)
    for st in answer["statements"]:
        assert statement_violations(st, facts) == [], st
    assert not [w for w in answer["warnings"] if w.startswith("audit")], answer["warnings"]


def test_citywide_answer_quotes_engine_lengths_and_deltas(city):
    result = city["result"]
    ctx = _ctx(city)
    a = build_answer("Чем план A отличается от B?", ctx)
    assert a["intent"] == "scenario_compare" and a["source"] == "template"
    _audit_clean(a, ctx)
    text = a["text"]
    base = result["baseline"]["routes"][0]["length_m"]
    plan = {p["id"]: p for p in result["plans"]}

    def m(v):  # значение движка без округления, записанное кодом помощника (группы через U+202F)
        return fmt_money(v)

    assert f"Без перекрытий: путь {m(base)} м." in text
    for pid in ("A", "B"):
        length = plan[pid]["routes"][0]["length_m"]
        delta = plan[pid]["vs_baseline"]["pairs"][0]["delta_m"]
        word = "длиннее" if delta > 0 else "короче"
        assert f"План {pid}: путь {m(length)} м — {word} на {m(abs(delta))} м" in text
    ab = result["a_vs_b"]["pairs"][0]["delta_m"]
    assert f"От плана A к плану B путь {'короче' if ab < 0 else 'длиннее'} на {m(abs(ab))} м." in text
    for banned in BANNED:
        assert banned not in text, banned


def test_citywide_answer_states_data_date_licence_access_and_limits(city):
    a = build_answer("Сравни варианты", _ctx(city))
    text = a["text"]
    assert "Снимок OpenStreetMap на 06.05.2026, получен 07.10.2026" in text
    assert "ODbL-1.0" in text and "© OpenStreetMap contributors" in text
    assert "не оперативные данные" in text
    known = city["result"]["graph_coverage"]["known_access_share_by_length"]
    assert fmt_money(round(known * 100, 1)) + " %" in text
    assert "Режим доступа неизвестен для" in text
    assert "прямоугольная выборка" in text            # warning graph_is_slice движка
    assert "не время в пути" in text and "пробки" in text  # оговорка, а не прогноз
    assert "гипотеза для сравнения" in text
    assert "не ранжирует варианты" in text


def test_citywide_closure_intervals_and_activity_come_from_engine(city):
    a = build_answer("Как изменится проход?", _ctx(city))
    lines = [s["text"] for s in a["statements"] if "перекрытие (" in s["text"]]
    assert lines == [
        "План A: перекрытие (1 уч.) с 07.10.2026 00:00 (UTC+05:00) до 08.10.2026 00:00 (UTC+05:00) — по условию сценария в момент анализа действует.",
        "План B: перекрытие (1 уч.) с 07.10.2026 00:00 (UTC+05:00) до 08.10.2026 00:00 (UTC+05:00) — по условию сценария в момент анализа действует.",
    ]


def test_inactive_closure_reported_from_engine_list(loader):
    entry = copy.deepcopy(loader(TINY))
    inactive = [(p["id"], c) for p in entry["result"]["plans"] for c in p["inactive_closures"]]
    a = build_answer("Сравни варианты", _ctx(entry, TINY))
    if inactive:
        assert "в момент анализа не действует" in a["text"]
    states = re.findall(r"в момент анализа (действует|не действует)", a["text"])
    payload = next(c for c in registry.list_cases() if c["case_id"] == TINY)["payload"]
    total = sum(len(p["closures"]) for p in payload["plans"])
    assert len(states) == total


def test_payload_not_matching_result_hides_intervals(city_raw):
    bad = copy.deepcopy(city_raw["payload"])
    bad["plans"][0]["closures"][0]["end_at"] = "2026-12-31T00:00:00+05:00"
    # и старая обёртка v1, и компактная запись v2: интервалы не берутся из входа, не совпавшего с расчётом
    for entry in ({"schema": INPUT_SCHEMA, "result": city_raw["result"], "payload": bad, "graph": None},
                  make_entry(city_raw["result"], bad, None, kind="prepared_case")):
        ctx = _ctx(entry)
        assert "scenario_payload_mismatch" in ctx["warnings"]
        a = build_answer("Сравни варианты", ctx)
        assert "Интервалы перекрытий не показаны" in a["text"]
        assert "31.12.2026" not in a["text"]
        _audit_clean(a, ctx)


def test_graph_info_of_another_graph_is_ignored(city):
    entry = copy.deepcopy(city)
    entry["graph"]["digest"] = "0" * 64
    ctx = _ctx(entry)
    assert "scenario_graph_info_mismatch" in ctx["warnings"]
    assert "Снимок OpenStreetMap" not in build_answer("Сравни варианты", ctx)["text"]


def test_unreachable_and_unknown_routes_are_not_zero(city):
    entry = copy.deepcopy(city)
    plan_a = entry["result"]["plans"][0]
    plan_a["routes"][0].update(status="unreachable", length_m=None)
    plan_a["vs_baseline"]["pairs"][0]["delta_m"] = None
    entry["result"]["a_vs_b"]["pairs"][0]["delta_m"] = None
    ctx = _ctx(entry)
    a = build_answer("Сравни варианты", ctx)
    assert "План A: пути в модели нет." in a["text"]
    assert "От плана A к плану B" not in a["text"]
    assert "0 м" not in a["text"]
    assert "свойство графа, а не доказанная потеря доступа" in a["text"]
    _audit_clean(a, ctx)


def test_many_pairs_fall_back_to_engine_summary(loader):
    entry = loader("k03-astana-demo-v1")
    pairs = entry["result"]["baseline"]["routes_total"]
    assert pairs > 3 and entry["result"]["baseline"]["routes"] == []  # большие маршруты не хранятся
    ctx = _ctx(entry, "k03-astana-demo-v1")
    a = build_answer("Сравни варианты", ctx)
    assert f"Пар маршрутов: {pairs}" in a["text"] and "Без перекрытий: путь" not in a["text"]
    _audit_clean(a, ctx)


def test_kazakh_scenario_answer_is_audit_clean(city):
    ctx = _ctx(city)
    a = build_answer("A мен B жоспарын салыстыр", ctx)
    assert a["language"] == "kk" and "OpenStreetMap суреті 06.05.2026" in a["text"]
    _audit_clean(a, ctx)


# ---- результаты пользовательских сравнений (кэш сервера, не данные клиента) ----

def test_result_cache_accepts_only_the_payload_of_that_result(city_raw):
    cache = ScenarioResultCache()
    bad = copy.deepcopy(city_raw["payload"])
    bad["analysis_at"] = "2026-10-07T10:00:00+05:00"
    assert cache.remember(bad, city_raw["result"]) is None and cache.last_rejection == "payload_digest_mismatch"
    assert cache.remember(city_raw["payload"], {"schema_version": "x"}) is None
    key = cache.remember(city_raw["payload"], city_raw["result"])
    assert key == "result:" + city_raw["result"]["result_digest"]
    entry = cache.get(key)
    assert entry["kind"] == "user_result" and entry["result_digest"] == city_raw["result"]["result_digest"]
    assert payload_digest(city_raw["payload"]) == city_raw["result"]["input"]["payload_digest"]


def _tiny_variant(tiny_raw, minute):
    payload = copy.deepcopy(tiny_raw["payload"])
    payload["analysis_at"] = f"2026-10-07T09:{minute:02d}:00+05:00"
    return payload, engine_compare.compare(payload, registry.load_graph(payload["graph_id"]))


def test_result_cache_ttl_and_size_limit(tiny_raw):
    now = [0.0]
    cache = ScenarioResultCache(max_items=2, ttl_s=10, clock=lambda: now[0])
    key = cache.remember(tiny_raw["payload"], tiny_raw["result"])
    now[0] = 11
    assert cache.get(key) is None and cache.status(key) == "expired"
    keys = [cache.remember(*_tiny_variant(tiny_raw, m)) for m in (1, 2, 3)]
    assert None not in keys and len(set(keys)) == 3
    assert cache.get(keys[0]) is None and cache.status(keys[0]) == "expired" and cache.get(keys[2]) is not None


def test_endpoint_explains_a_server_computed_user_comparison(loader, city_raw):
    key = loader.cache.remember(city_raw["payload"], city_raw["result"])
    ep = AssistantEndpoint(lambda oid: None, load_scenario_result=loader, rate_limiter=RateLimiter(100, 60))
    ok = ep.handle("POST", ASSISTANT_PATH, {}, {"question": "Сравни варианты", "object_id": None, "scenario_id": key},
                   {"client_ip": "127.0.0.1", "headers": {}})
    data = ok["body"]["data"]
    assert ok["status"] == 200 and data["source"] == "template" and data["scenario_id"] == key
    assert "Без перекрытий: путь" in data["text"]
    missing = ep.handle("POST", ASSISTANT_PATH, {}, {"question": "Сравни", "object_id": None,
                                                     "scenario_id": "result:" + "f" * 64},
                        {"client_ip": "127.0.0.1", "headers": {}})
    assert missing["body"]["data"]["source"] == "unavailable"
    assert "scenario_result_unknown" in missing["body"]["data"]["warnings"]
    assert "Выполните сравнение заново" in missing["body"]["data"]["text"]


def test_client_cannot_send_metrics_with_the_question(loader):
    ep = AssistantEndpoint(lambda oid: None, load_scenario_result=loader, rate_limiter=RateLimiter(100, 60))
    bad = ep.handle("POST", ASSISTANT_PATH, {}, {"question": "Сравни", "scenario_id": CITY,
                                                 "result": {"a_vs_b": {"delta_m": -999}}},
                    {"client_ip": "127.0.0.1", "headers": {}})
    assert bad["status"] == 400 and bad["body"]["error"]["code"] == "unexpected_fields"


def test_wrapper_schema_is_shared(city):
    assert city["schema"] == ENTRY_SCHEMA and city["kind"] == "prepared_case"
    json.dumps(city["graph"])  # запись MANIFEST сериализуема (уходит только в серверный контекст)
