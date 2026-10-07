"""Сквозная проверка через HTTP-шлюз R01 (ui.web_server.CivicGateway) + R02 + R06.

Пропускается, пока в дереве нет шлюза R01 и CivicService R02 (как в ветке R06).
В интегрированной ветке R01 проверяет: маршрут /objects/{id}/feedback, Origin, cookie-сессию
R02, CSRF, публичный lookup объекта и запрет модерации после выхода.
"""

import json
import secrets
import threading
import urllib.error
import urllib.request

import pytest

web_server = pytest.importorskip("ui.web_server")
civic_service_module = pytest.importorskip("ui.civic_store.service")
civic_auth = pytest.importorskip("ui.civic_store.auth")
if not hasattr(web_server, "CivicGateway"):
    pytest.skip("шлюз civic-v1 R01 ещё не в этом дереве", allow_module_level=True)


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(civic_auth, "SCRYPT_N", 2 ** 10)
    monkeypatch.setattr(civic_auth, "SCRYPT_P", 1)
    db_path = tmp_path / "civic.sqlite3"
    password = "R06-" + secrets.token_urlsafe(16)
    store = civic_service_module.CivicService(db_path)
    store.accounts.create_user("r06editor", password, display_name="Редактор R06")
    srv = web_server.create_server(port=0, civic_db=db_path)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", password
    srv.shutdown()
    srv.server_close()


def http(base, method, path, body=None, cookie=None, csrf=None, origin=True):
    request = urllib.request.Request(base + "/api/civic/v1" + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
    request.add_header("Content-Type", "application/json")
    if origin:
        request.add_header("Origin", base)
    if cookie:
        request.add_header("Cookie", cookie)
    if csrf:
        request.add_header("X-CSRF-Token", csrf)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), error.headers


def test_gateway_routes_feedback_end_to_end(server):
    base, password = server
    status, login, headers = http(base, "POST", "/session/login", {"username": "r06editor", "password": password})
    assert status == 200, login
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    csrf = login["data"]["csrf_token"]
    payload = {"kind": "roadworks", "title": "Синтетический объект R06", "description": "Тестовая запись.",
               "status": "planned", "geometry": {"type": "Point", "coordinates": [71.43, 51.17]},
               "geometry_precision": "approximate",
               "schedule": {"planned_start": "2026-10-14", "original_planned_end": None,
                            "current_planned_end": "2026-10-20", "actual_end": None},
               "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
               "responsible": {"organization": None, "public_contact": None},
               "evidence_type": "synthetic", "source_refs": [], "evidence_notes": "R06 smoke"}
    status, created, _ = http(base, "POST", "/staff/objects", payload, cookie, csrf)
    assert status == 201, created
    item = created["data"]["item"]
    status, published, _ = http(base, "POST", f"/staff/objects/{item['id']}/publish",
                                {"expected_revision": item["revision"], "reason": "R06 smoke"}, cookie, csrf)
    assert status == 200, published

    body = {"object_id": item["id"], "category": "roads", "consent_public": True,
            "text": "Сквозная проверка: яма у въезда во двор."}
    assert http(base, "POST", "/feedback", body, origin=False)[0] == 403        # без Origin
    status, receipt, _ = http(base, "POST", "/feedback", body)
    assert status == 201, receipt
    status, listing, _ = http(base, "GET", f"/objects/{item['id']}/feedback")
    assert status == 200 and listing["data"]["items"] == []
    status, detail, _ = http(base, "GET", f"/objects/{item['id']}")
    assert status == 200 and detail["data"]["item"]["id"] == item["id"]

    assert http(base, "GET", "/staff/feedback")[0] == 401
    status, queue, _ = http(base, "GET", "/staff/feedback", cookie=cookie)
    assert status == 200, queue
    entry = queue["data"]["items"][0]
    decision = {"expected_revision": entry["revision"], "action": "approve", "reason": "R06 smoke"}
    path = f"/staff/feedback/{entry['id']}/moderate"
    assert http(base, "POST", path, decision, cookie)[0] == 403                    # без CSRF
    status, moderated, _ = http(base, "POST", path, decision, cookie, csrf)
    assert status == 200, moderated
    status, listing, _ = http(base, "GET", f"/objects/{item['id']}/feedback")
    assert len(listing["data"]["items"]) == 1

    http(base, "POST", "/session/logout", {}, cookie, csrf)
    again = dict(decision, expected_revision=entry["revision"] + 1, action="reject")
    assert http(base, "POST", path, again, cookie, csrf)[0] == 401
