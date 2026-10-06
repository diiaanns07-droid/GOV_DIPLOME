"""R01: civic-v1 transport gateway in ui/web_server.py (real HTTP, local port).

The services below are TEST DOUBLES that record calls. They are not the R02/R06
backends; these tests only prove what the gateway does before/after a service.
"""

from __future__ import annotations

from http.client import HTTPConnection
import json
import threading
from unittest.mock import patch

import pytest

from ui.web_server import CIVIC_MAX_BODY, CivicGateway, Handler, create_server


class RecordingStore:
    """Test double for the R02 contract surface: handle + resolve_principal."""

    def __init__(self):
        self.calls = []

    def resolve_principal(self, context):
        return {"role": "anonymous"}

    def handle(self, method, path, query, body, context):
        self.calls.append((method, path, query, body, context))
        path = path[len("/api/civic/v1"):]
        if path.startswith("/objects/bad-shape"):
            return {"status": 200, "body": "not an envelope"}
        if path == "/session/login":
            return {"status": 200, "headers": {"Set-Cookie": "civic_session=abc; HttpOnly; SameSite=Strict; Path=/",
                                               "X-Evil": "1", "Location": "http://evil"},
                    "body": {"ok": True, "data": {"authenticated": True}}}
        return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"path": path, "query": query}}}


class RecordingFeedback:
    def __init__(self):
        self.calls = []

    def handle(self, method, path, query, body, principal, context):
        self.calls.append((method, path[len("/api/civic/v1"):], principal))
        return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"items": [], "owner": "feedback"}}}


@pytest.fixture()
def served():
    store, feedback = RecordingStore(), RecordingFeedback()
    gateway = CivicGateway({"store": lambda: store, "feedback": lambda: feedback})
    server = create_server(port=0, civic=gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    quiet = patch.object(Handler, "log_message", return_value=None)
    quiet.start()
    thread.start()
    try:
        yield server.server_address[1], store, feedback
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        quiet.stop()


def call(port, method, path, payload=None, *, raw=None, headers=None, origin=True):
    request_headers = {}
    if origin:
        request_headers["Origin"] = f"http://127.0.0.1:{port}"
    body = raw
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        wire = response.read()
        return response.status, response.getheaders(), json.loads(wire.decode("utf-8")) if wire else None
    finally:
        connection.close()


def test_unknown_civic_path_is_json_404_not_html(served):
    port, store, _ = served
    status, headers, body = call(port, "GET", "/api/civic/v1/nope")
    assert status == 404 and body == {"ok": False, "error": {"code": "not_found", "message": body["error"]["message"]}}
    assert dict(headers)["Content-Type"].startswith("application/json")
    assert store.calls == []


def test_wrong_method_is_405_with_allow(served):
    port, store, _ = served
    status, headers, body = call(port, "GET", "/api/civic/v1/staff/objects/x1/publish")
    assert status == 405 and body["error"]["code"] == "method_not_allowed"
    assert dict(headers)["Allow"] == "POST"
    assert store.calls == []


def test_trailing_slash_and_bad_ids_do_not_reach_service(served):
    port, store, _ = served
    for path in ("/api/civic/v1/objects/", "/api/civic/v1/objects//x", "/api/civic/v1/objects/..%2Fetc",
                 "/api/civic/v1/objects/" + "a" * 200, "/api/civic/v1/objects/<script>"):
        status, _, body = call(port, "GET", path)
        assert status == 404, path
        assert body["ok"] is False
    assert store.calls == []


def test_feedback_route_wins_over_object_detail(served):
    port, store, feedback = served
    status, _, body = call(port, "GET", "/api/civic/v1/objects/obj-1/feedback")
    assert status == 200 and body["data"]["owner"] == "feedback"
    assert store.calls == [] and feedback.calls == [("GET", "/objects/obj-1/feedback", {"role": "anonymous"})]


def test_cross_origin_post_never_reaches_service(served):
    port, store, _ = served
    status, _, body = call(port, "POST", "/api/civic/v1/staff/objects", {"title": "x"},
                           headers={"Origin": "http://evil.example"})
    assert status == 403 and body["error"]["code"] == "cross_origin"
    status, _, body = call(port, "POST", "/api/civic/v1/staff/objects", {"title": "x"},
                           headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403
    assert store.calls == []


def test_foreign_host_is_rejected_for_get_and_post(served):
    port, store, _ = served
    status, _, body = call(port, "GET", "/api/civic/v1/objects", headers={"Host": "attacker.example"}, origin=False)
    assert status == 403 and body["error"]["code"] == "forbidden_host"
    status, _, _ = call(port, "POST", "/api/civic/v1/session/login", {"username": "a"},
                        headers={"Host": "attacker.example"}, origin=False)
    assert status == 403
    assert store.calls == []


def test_body_limits_content_type_and_json(served):
    port, store, _ = served
    status, _, body = call(port, "POST", "/api/civic/v1/staff/objects", raw=b"x" * (CIVIC_MAX_BODY + 10))
    assert status == 413 and body["error"]["code"] == "too_large"
    status, _, body = call(port, "POST", "/api/civic/v1/staff/objects", raw=b"{}",
                           headers={"Content-Type": "text/plain"})
    assert status == 415
    for raw in (b"{bad", b"[1,2]", b'{"a": NaN}', b'{"a": Infinity}'):
        status, _, body = call(port, "POST", "/api/civic/v1/staff/objects", raw=raw)
        assert status == 400 and body["error"]["code"] == "invalid_json", raw
    assert store.calls == []


def test_service_exception_is_500_without_details(served):
    port, store, _ = served
    with patch.object(RecordingStore, "handle", side_effect=RuntimeError("secret detail must not leak")):
        status, _, body = call(port, "GET", "/api/civic/v1/objects")
    assert status == 500 and body["error"]["code"] == "internal"
    assert "secret" not in json.dumps(body)


def test_malformed_service_response_is_contained(served):
    port, _, _ = served
    status, _, body = call(port, "GET", "/api/civic/v1/objects/bad-shape")
    assert status == 500 and body["error"]["code"] == "bad_service_response"


def test_only_allowlisted_service_headers_pass(served):
    port, _, _ = served
    status, headers, body = call(port, "POST", "/api/civic/v1/session/login", {"username": "u", "password": "p"})
    assert status == 200 and body["ok"] is True
    names = {name.lower() for name, _ in headers}
    assert "set-cookie" in names and "x-evil" not in names and "location" not in names
    assert dict(headers)["Cache-Control"] == "no-store"


def test_context_carries_server_side_facts_not_body_claims(served):
    port, store, _ = served
    call(port, "POST", "/api/civic/v1/staff/objects", {"title": "t", "actor": "admin", "role": "editor"},
         headers={"Cookie": "civic_session=s1; other=2", "X-CSRF-Token": "tok"})
    method, path, query, body, context = store.calls[-1]
    assert (method, path) == ("POST", "/api/civic/v1/staff/objects")
    assert context["is_same_origin"] is True and context["host_allowed"] is True
    assert context["cookies"] == {"civic_session": "s1", "other": "2"}
    assert context["headers"]["x-csrf-token"] == "tok"
    assert context["client_ip"] == "127.0.0.1"
    # The gateway forwards the body untouched; R02 must ignore actor/role in it (tested in R02/R10).
    assert body["role"] == "editor"
    call(port, "POST", "/api/civic/v1/staff/objects", {"title": "t"}, origin=False)
    assert store.calls[-1][4]["is_same_origin"] is None  # unknown: R02 then relies on CSRF
    call(port, "POST", "/api/civic/v1/staff/objects", {"title": "t"}, origin=False,
         headers={"Sec-Fetch-Site": "same-origin"})
    assert store.calls[-1][4]["is_same_origin"] is True


def test_query_is_passed_raw_and_bounded(served):
    port, store, _ = served
    status, _, body = call(port, "GET", "/api/civic/v1/objects?kind=roadworks&kind=event&from=2026-10-01")
    assert status == 200 and body["data"]["query"] == "kind=roadworks&kind=event&from=2026-10-01"
    status, _, body = call(port, "GET", "/api/civic/v1/objects?x=" + "a" * 3000)
    assert status == 400 and body["error"]["code"] == "query_too_long"


def test_missing_modules_answer_503_and_status_lists_them():
    gateway = CivicGateway({})
    server = create_server(port=0, civic=gateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    with patch.object(Handler, "log_message", return_value=None):
        thread.start()
        try:
            port = server.server_address[1]
            for method, path, payload in (("GET", "/api/civic/v1/objects", None),
                                          ("POST", "/api/civic/v1/staff/objects", {"title": "x"}),
                                          ("POST", "/api/civic/v1/feedback", {"text": "x"}),
                                          ("POST", "/api/civic/v1/scenarios/compare", {}),
                                          ("POST", "/api/civic/v1/assistant", {"question": "?"})):
                status, _, body = call(port, method, path, payload)
                assert status == 503 and body["error"]["code"] == "module_unavailable", path
            status, _, body = call(port, "GET", "/api/civic/v1/modules")
            assert status == 200
            assert {k: v["status"] for k, v in body["data"]["modules"].items()} == {
                "store": "unavailable", "feedback": "unavailable", "scenarios": "unavailable",
                "assistant": "unavailable"}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def test_legacy_routes_unchanged(served):
    port, _, _ = served
    status, _, body = call(port, "GET", "/api/health")
    assert (status, body) == (200, {"status": "ok"})
    status, _, body = call(port, "POST", "/api/not-a-route", {"a": 1})
    assert status == 404 and body["valid"] is False
