"""R01 round 13: gateway junctions with the real R06/R07/R08/R09 modules of the integration candidate.

- R09 x R07: only the server's own successful /scenarios/compare result can be explained as
  scenario_id "result:<digest>"; failed or oversized results are not kept; browser numbers are refused.
- R06 x R08: the classifier is opt-in (off by default), its status is reported without texts, and a
  failing or hanging model never prevents a message from being saved.
"""

from __future__ import annotations

import time

import pytest

from ui import web_server
from ui.web_server import CivicGateway

pytest.importorskip("agent.civic_assistant.api")
pytest.importorskip("engine.civic_scenarios.registry")
pytest.importorskip("ui.civic_feedback.service")

CTX = {"headers": {}, "cookies": {}, "client_ip": "127.0.0.1", "host_allowed": True,
       "is_same_origin": True, "is_https": False, "host": "127.0.0.1"}
MESSAGE = {"object_id": None, "geometry": {"type": "Point", "coordinates": [71.43, 51.13]}, "category": "roads",
           "text": "Не горят фонари во дворе, вечером темно и опасно.", "consent_public": False}


def k03_payload():
    from engine.civic_scenarios import registry
    return next(c for c in registry.list_cases() if c["case_id"] == "k03-astana-demo-v1")["payload"]


def ask(gw, scenario_id, **extra):
    return gw.handle("POST", "/assistant", "", {"question": "Почему план A меняет путь?", "object_id": None,
                                                "scenario_id": scenario_id, **extra}, CTX)


@pytest.fixture()
def gateway(tmp_path):
    return CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")


def test_server_compare_result_is_explained(gateway):
    reply = gateway.handle("POST", "/scenarios/compare", "", k03_payload(), CTX)
    assert reply["status"] == 200
    digest = reply["body"]["data"]["result_digest"]
    answer = ask(gateway, "result:" + digest)
    data = answer["body"]["data"]
    assert answer["status"] == 200 and data["source"] == "template" and data["intent"] == "scenario_compare"
    assert "гипотеза" in data["text"]  # a hypothesis, not an official closure


def test_unknown_or_forged_digest_is_not_explained(gateway):
    answer = ask(gateway, "result:" + "0" * 16)
    assert answer["status"] == 200 and answer["body"]["data"]["source"] == "unavailable"


def test_browser_numbers_are_refused(gateway):
    reply = gateway.handle("POST", "/scenarios/compare", "", k03_payload(), CTX)
    digest = reply["body"]["data"]["result_digest"]
    forged = ask(gateway, "result:" + digest, facts=[{"id": "a_vs_b", "value": "−5000 м"}])
    assert forged["status"] == 400


def test_failed_compare_is_not_cached(gateway):
    bad = dict(k03_payload(), plans=[])
    reply = gateway.handle("POST", "/scenarios/compare", "", bad, CTX)
    assert reply["status"] != 200
    cache = gateway.scenario_results()
    assert cache is not None and not cache._items


def test_oversized_result_is_not_cached(gateway, monkeypatch):
    monkeypatch.setattr(web_server, "SCENARIO_CACHE_MAX_BYTES", 100)
    reply = gateway.handle("POST", "/scenarios/compare", "", k03_payload(), CTX)
    assert reply["status"] == 200  # the comparison itself is unaffected
    assert ask(gateway, "result:" + reply["body"]["data"]["result_digest"])["body"]["data"]["source"] == "unavailable"


def test_cache_is_bounded(gateway):
    cache = gateway.scenario_results()
    assert cache.max_items == web_server.SCENARIO_CACHE_ITEMS <= 16 and cache.ttl_s == web_server.SCENARIO_CACHE_TTL_S


def test_classifier_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CIVIC_R08_CLASSIFIER", raising=False)
    gw = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    status = gw.modules()["feedback"]["classifier"]
    assert status["enabled"] is False
    assert gw.handle("POST", "/feedback", "", MESSAGE, CTX)["status"] == 201


def test_classifier_opt_in_reports_synthetic_status(tmp_path):
    pytest.importorskip("ml.civic_classifier")
    gw = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3", classifier="r08")
    status = gw.modules()["feedback"]["classifier"]
    assert status["enabled"] and status["available"]
    assert "synthetic" in (status["training_data_status"] or "")
    assert gw.handle("POST", "/feedback", "", MESSAGE, CTX)["status"] == 201
    feedback = gw.service("feedback")
    row = feedback._db.execute("SELECT classifier_status, classifier_json FROM feedback_messages").fetchone()
    assert row["classifier_status"] == "ok" and '"needs_review": true' in row["classifier_json"]


def test_env_switch_enables_classifier(tmp_path, monkeypatch):
    pytest.importorskip("ml.civic_classifier")
    monkeypatch.setenv("CIVIC_R08_CLASSIFIER", "1")
    gw = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    assert gw.modules()["feedback"]["classifier"]["enabled"] is True


@pytest.mark.parametrize("behaviour", ["raise", "hang"])
def test_failing_classifier_never_blocks_saving(tmp_path, monkeypatch, behaviour):
    from ui.civic_feedback import classifier_adapter

    def bad_classify(text, language):
        if behaviour == "raise":
            raise RuntimeError("model broke")
        time.sleep(5)
        return {"label": "roads"}

    monkeypatch.setattr(classifier_adapter, "r08_status", lambda **_: {
        "available": True, "reason": None, "classify": bad_classify, "model_version": "test", "training_data_status": "test",
        "score_kind": None})
    gw = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3", classifier="r08")
    started = time.monotonic()
    reply = gw.handle("POST", "/feedback", "", MESSAGE, CTX)
    assert reply["status"] == 201 and time.monotonic() - started < 4.5
    row = gw.service("feedback")._db.execute("SELECT classifier_status FROM feedback_messages").fetchone()
    assert row["classifier_status"] == ("error" if behaviour == "raise" else "timeout")


def test_unavailable_model_is_reported_and_messages_still_saved(tmp_path, monkeypatch):
    from ui.civic_feedback import classifier_adapter
    monkeypatch.setattr(classifier_adapter, "r08_status", lambda **_: {"available": False, "reason": "import_failed:X"})
    gw = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3", classifier="r08")
    assert gw.modules()["feedback"]["classifier"] == {"enabled": True, "available": False, "reason": "import_failed:X",
                                                      "model_version": None, "training_data_status": None, "score_kind": None}
    assert gw.handle("POST", "/feedback", "", MESSAGE, CTX)["status"] == 201
