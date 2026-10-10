"""R15: транспорт ui/web_server.py (владелец R01) — статика, заголовки, Origin/CSRF, доступ сотрудника.

Всё через настоящий HTTP на 127.0.0.1 и временную базу. PASS-тесты фиксируют то, что уже защищено
(регрессия), xfail — открытые находки из SECURITY_REVIEW.md.
"""

from __future__ import annotations

import json

import pytest

from r15_common import error_code, live_server, need_module, request, xfail

EVIL = "http://evil.example"


@pytest.fixture()
def srv(tmp_path):
    with live_server(tmp_path) as server:
        yield server


# --- 5. статика: только белый список, выхода за web/ нет ---------------------------------

TRAVERSAL = [
    "/../ui/web_server.py", "/civic/../../ui/web_server.py", "/%2e%2e/ui/web_server.py",
    "/civic/shell/..%2f..%2f..%2fui%2fweb_server.py", "/.env", "/.git/config", "/web/index.html",
    "/civic/", "/vendor/", "/civic/shell/", "/..%5c..%5cui%5cweb_server.py", "//etc/passwd",
    "/research/round-14/CONTRACT.md", "/.runtime/civic.sqlite3", "/private/form.csv",
]


@pytest.mark.parametrize("path", TRAVERSAL)
def test_static_has_no_path_traversal(srv, path):
    status, _headers, body = request(srv, "GET", path)
    assert status == 404, path
    assert b"import " not in body and b"[core]" not in body


def test_index_is_served_with_basic_security_headers(srv):
    status, headers, _ = request(srv, "GET", "/")
    assert status == 200
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("referrer-policy") == "same-origin"
    assert "frame-ancestors 'none'" in headers.get("content-security-policy", "")


@xfail("S01")
def test_csp_limits_scripts_on_html(srv):
    """Без script-src любая XSS в одном из 14 модулей получает полный доступ к странице сотрудника."""
    _status, headers, _ = request(srv, "GET", "/")
    csp = headers.get("content-security-policy", "")
    directives = {part.strip().split(" ")[0]: part.strip() for part in csp.split(";") if part.strip()}
    script = directives.get("script-src") or directives.get("default-src") or ""
    assert "'self'" in script and "'unsafe-inline'" not in script and "'unsafe-eval'" not in script
    assert "object-src 'none'" in csp
    assert "base-uri" in csp


# --- 2. Origin / CSRF для изменяющих запросов --------------------------------------------

V2_WRITES = [
    ("POST", "/api/civic/v2/complaints", {"text": "Яма у остановки", "point": [71.41, 51.11]}),
    ("POST", "/api/civic/v2/complaints/c-abcdef12/metoo", {"device_id": "device-r15-000001"}),
    ("POST", "/api/civic/v2/proposals/p-1/vote", {"value": 1, "device_id": "device-r15-000001"}),
    ("POST", "/api/civic/v2/complaints/c-abcdef12/status", {"status": "fixed"}),
    ("PUT", "/api/civic/v2/objects/o-1/stage", {"stage": "design"}),
]


@pytest.mark.parametrize("method,path,body", V2_WRITES)
def test_cross_origin_write_is_rejected(srv, method, path, body):
    status, _h, data = request(srv, method, path, body, headers={"Origin": EVIL})
    assert status == 403, data
    assert json.loads(data)["error"] == "cross_origin"


@pytest.mark.parametrize("method,path,body", V2_WRITES)
def test_cross_site_fetch_metadata_is_rejected(srv, method, path, body):
    status, _h, _data = request(srv, method, path, body, headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403


def test_simple_form_post_cannot_reach_api(srv):
    # Чужая страница без preflight может послать только text/plain / form — шлюз требует JSON.
    status, _h, _ = request(srv, "POST", "/api/civic/v2/proposals/p-1/vote",
                            raw=b'{"value":1,"device_id":"device-r15-000001"}',
                            headers={"Content-Type": "text/plain"})
    assert status == 415


def test_preflight_gets_no_cors_permission(srv):
    status, headers, _ = request(srv, "OPTIONS", "/api/civic/v2/proposals/p-1/vote",
                                 headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"})
    assert status in (404, 405)
    assert "access-control-allow-origin" not in headers


def test_foreign_host_header_is_rejected(srv):
    # Защита от DNS rebinding: имя чужого сайта в Host -> 403 даже для чтения.
    status, _h, _ = request(srv, "GET", "/api/civic/v2/complaints",
                            headers={"Host": "evil.example:%d" % srv.server_address[1]})
    assert status == 403


# --- 2. действия сотрудника недоступны анониму -------------------------------------------

STAFF_ONLY = [
    ("POST", "/api/civic/v2/complaints/c-abcdef12/status", {"status": "fixed"}),
    ("POST", "/api/civic/v2/proposals", {"kind": "park", "title_ru": "Сквер"}),
    ("PUT", "/api/civic/v2/objects/o-1/stage", {"stage": "design"}),
    ("POST", "/api/civic/v1/staff/objects", {"title": "x"}),
    ("GET", "/api/civic/v1/staff/feedback", None),
    ("GET", "/api/civic/v1/staff/audit", None),
]


@pytest.mark.parametrize("method,path,body", STAFF_ONLY)
def test_staff_actions_need_session(srv, method, path, body):
    status, _h, data = request(srv, method, path, body,
                               headers={"Origin": "http://127.0.0.1:%d" % srv.server_address[1]})
    payload = json.loads(data)
    if status == 503:
        # Модуль ещё не подключён в этой сборке — значит, и действие недоступно.
        assert error_code(payload) in ("module_not_ready", "module_unavailable"), payload
        return
    assert status in (401, 403), (status, payload)


def _staff_login(srv, tmp_path):
    store = srv.civic.service("store")
    if store is None:
        pytest.skip("в этой сборке нет хранилища сотрудников (ui.civic_store)")
    store.accounts.create_user("r15-editor", "R15-Strong-Pass-2026", display_name="R15", role="editor")
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    status, headers, data = request(srv, "POST", "/api/civic/v1/session/login",
                                    {"username": "r15-editor", "password": "R15-Strong-Pass-2026"},
                                    headers={"Origin": origin})
    assert status == 200, data
    return headers.get("set-cookie", ""), json.loads(data)


def test_session_cookie_is_httponly_strict(srv, tmp_path):
    cookie, _ = _staff_login(srv, tmp_path)
    attrs = [part.strip().lower() for part in cookie.split(";")]
    assert "httponly" in attrs
    assert "samesite=strict" in attrs
    assert not any(a.startswith("domain=") for a in attrs)


def test_csrf_token_is_required_for_staff_write(srv, tmp_path):
    cookie, _session = _staff_login(srv, tmp_path)
    token = cookie.split(";")[0]
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    status, _h, data = request(srv, "POST", "/api/civic/v1/staff/objects", {"title": "x"},
                               headers={"Cookie": token, "Origin": origin})
    assert status == 403 and json.loads(data)["error"]["code"] == "csrf_failed"


@xfail("S09")
def test_session_cookie_reaches_api_v2(srv, tmp_path):
    cookie, _ = _staff_login(srv, tmp_path)
    path = next((a.split("=", 1)[1] for a in (p.strip() for p in cookie.split(";")) if a.lower().startswith("path=")), "/")
    assert "/api/civic/v2/complaints/c-1/status".startswith(path.rstrip("/") + "/")


def test_public_akim_summary_has_no_resident_texts(srv):
    """«Картина дня» доступна без входа: в ней только агрегаты, без текстов и точек жителей."""
    need_module("ui.civic_akim")
    status, _h, data = request(srv, "GET", "/api/civic/v2/akim/summary")
    if status == 503:
        pytest.skip("akim.summary не подключён")
    assert status == 200
    text = data.decode("utf-8")
    payload = json.loads(text)

    # .text / .text_parts — это сгенерированная фраза сводки («Сегодня 19 новых обращений…»), не жалоба.
    def keys(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if path == "" and key in ("text", "text_parts"):
                    continue
                yield key
                yield from keys(value, path + "." + key)
        elif isinstance(obj, list):
            for item in obj:
                yield from keys(item, path + "[]")

    found = set(keys(payload)) & {"text", "texts", "quote", "quotes", "point", "device_id", "device_hash",
                                  "phone", "username", "author"}
    assert not found, found
