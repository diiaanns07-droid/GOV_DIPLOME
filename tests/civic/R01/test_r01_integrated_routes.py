"""R01: integrated gateway with the real role modules (R02, R06, R07, R09) on a temp SQLite file.

Covers R10-D002 (non-string graph_id must not reach R07 and crash it) and staff-only routes of
R06/R09 behind the gateway's session + CSRF rules.
"""

from __future__ import annotations

from http.client import HTTPConnection
import json
import threading
from unittest.mock import patch

import pytest

from ui.web_server import CivicGateway, Handler, create_server

pytest.importorskip("ui.civic_store.service")
pytest.importorskip("engine.civic_scenarios.http")


@pytest.fixture()
def port(tmp_path):
    gateway = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    server = create_server(port=0, civic=gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    with patch.object(Handler, "log_message", return_value=None):
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def call(port, method, path, payload=None, headers=None):
    hdrs = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}
    hdrs.update(headers or {})
    conn = HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request(method, "/api/civic/v1" + path, body=None if payload is None else json.dumps(payload), headers=hdrs)
        response = conn.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()


def test_all_role_modules_ready(port):
    status, body = call(port, "GET", "/modules")
    assert status == 200
    assert {k: v["status"] for k, v in body["data"]["modules"].items()} == {
        "store": "ready", "feedback": "ready", "scenarios": "ready", "assistant": "ready"}


@pytest.mark.parametrize("graph_id", [["a"], {"x": 1}, 5, None, True])
def test_non_string_graph_id_is_422_not_500(port, graph_id):
    status, body = call(port, "POST", "/scenarios/compare", {"graph_id": graph_id})
    assert status == 422 and body["error"]["code"] == "invalid_payload"


def test_scenario_lists_are_public_and_graph_files_not_static(port):
    status, body = call(port, "GET", "/scenarios/graphs")
    assert status == 200 and body["data"]["items"]
    assert all("file" not in item for item in body["data"]["items"])
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/engine/civic_scenarios/graphs/MANIFEST.json")
    assert conn.getresponse().status == 404
    conn.close()


def test_staff_routes_of_r06_and_r09_need_a_session(port):
    assert call(port, "GET", "/staff/feedback")[0] == 401
    status, body = call(port, "POST", "/staff/assistant/extract", {"source_id": "src-1", "text": "Срок до 1 ноября"})
    assert status == 401
    status, body = call(port, "POST", "/staff/feedback/fb-1/moderate", {"expected_revision": 1, "action": "approve", "reason": "x"})
    assert status in (401, 403)


def test_assistant_rejects_client_facts_and_unknown_object(port):
    status, body = call(port, "POST", "/assistant", {"question": "Когда?", "object_id": "nope-1", "scenario_id": None,
                                                     "facts": [{"id": "f", "value": "готово"}]})
    assert status == 400
    status, body = call(port, "POST", "/assistant", {"question": "Когда закончат?", "object_id": "nope-1", "scenario_id": None})
    assert status == 200 and body["data"]["source"] == "unavailable"


def test_feedback_for_unknown_object_rejected(port):
    status, body = call(port, "POST", "/feedback", {"object_id": "nope-1", "geometry": None, "category": "roads",
                                                    "text": "Нет прохода вдоль ограждения", "consent_public": False})
    assert status == 422
