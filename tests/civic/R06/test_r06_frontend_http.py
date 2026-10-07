"""Статические проверки фронтенда R06 и HTTP-проверка через реальный сокет стенда."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[3]
JS = (ROOT / "web/civic/feedback/feedback.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/civic/feedback/feedback.css").read_text(encoding="utf-8")


def code_only(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", source)


def test_no_html_injection_sinks_in_component():
    code = code_only(JS)
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in code, sink


def test_component_exposes_contract_globals_only():
    assert "window.CivicFeedback = {" in JS
    assigned = set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=", code_only(JS)))
    assert assigned == {"CivicFeedback"}
    for name in ("mount: mount", "mountModeration: mountModeration"):
        assert name in JS


def test_component_does_not_touch_body_or_storage_or_staff_from_public_form():
    code = code_only(JS)
    assert "document.body" not in code
    assert "localStorage" not in code and "sessionStorage" not in code
    resident = code.split("function mountModeration")[0]
    assert "/staff/" not in resident  # публичная форма не грузит служебные endpoint


def test_css_is_scoped_to_component_prefix():
    selectors = re.findall(r"(?m)^([^{}@/][^{}]*)\{", re.sub(r"/\*.*?\*/", "", CSS, flags=re.S))
    for group in selectors:
        for selector in group.split(","):
            selector = selector.strip()
            if selector:
                assert selector.startswith(".civic-r06"), selector


def test_no_promises_of_execution_in_ui_text():
    lowered = JS.lower()
    for phrase in ("принято в работу", "принят в работу", "акимат принял", "будет исправлено", "исполнено"):
        assert phrase not in lowered
    assert "официальная регистрация не выполняется" in lowered


@pytest.mark.skipif(shutil.which("node") is None, reason="node не установлен")
def test_javascript_syntax():
    subprocess.run(["node", "--check", str(ROOT / "web/civic/feedback/feedback.js")], check=True)


# --------------------------------------------------------------- real HTTP
@pytest.fixture
def harness(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "tests/civic/R06/harness"))
    try:
        import serve_r06
    finally:
        sys.path.pop(0)
    server = serve_r06.create_server(0, str(tmp_path / "http.sqlite3"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base
    server.shutdown()
    server.server_close()
    serve_r06.Handler.harness.service.close()


def call(base, method, path, body=None, headers=None, cookie=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), error.headers


def test_http_flow_with_cookie_session_csrf_and_origin(harness):
    origin = {"Origin": harness}
    body = {"object_id": "demo-astana-work-01", "category": "roads", "consent_public": True,
            "text": "Проверка через HTTP: яма у въезда во двор."}
    status, payload, _ = call(harness, "POST", "/api/civic/v1/feedback", body, origin)
    assert status == 201 and payload["data"]["moderation"] == "pending"
    status, payload, _ = call(harness, "POST", "/api/civic/v1/feedback", body, {"Origin": "http://evil.example"})
    assert status == 403

    status, payload, _ = call(harness, "GET", "/api/civic/v1/staff/feedback")
    assert status == 401 and payload["ok"] is False

    status, payload, headers = call(harness, "POST", "/harness/login", {"role": "editor"}, origin)
    cookie = headers["Set-Cookie"].split(";")[0]
    csrf = payload["data"]["csrf_token"]
    status, payload, _ = call(harness, "GET", "/api/civic/v1/staff/feedback", cookie=cookie)
    assert status == 200 and len(payload["data"]["items"]) == 1
    staff_id = payload["data"]["items"][0]["id"]
    decision = {"expected_revision": 1, "action": "approve", "reason": "HTTP-проверка"}
    path = f"/api/civic/v1/staff/feedback/{staff_id}/moderate"
    assert call(harness, "POST", path, decision, origin, cookie)[0] == 403          # нет CSRF
    assert call(harness, "POST", path, decision, {"X-CSRF-Token": csrf, "Origin": "http://evil.example"},
                cookie)[0] == 403                                                   # чужой Origin
    status, payload, _ = call(harness, "POST", path, decision, {"X-CSRF-Token": csrf, **origin}, cookie)
    assert status == 200 and payload["data"]["item"]["is_public"] is True

    call(harness, "POST", "/harness/logout", {}, origin, cookie)
    again = {"expected_revision": 2, "action": "reject", "reason": "после выхода"}
    assert call(harness, "POST", path, again, {"X-CSRF-Token": csrf, **origin}, cookie)[0] == 401

    status, payload, _ = call(harness, "GET", "/api/civic/v1/objects/demo-astana-work-01/feedback")
    assert status == 200 and len(payload["data"]["items"]) == 1
    assert "moderated_by" not in payload["data"]["items"][0]
