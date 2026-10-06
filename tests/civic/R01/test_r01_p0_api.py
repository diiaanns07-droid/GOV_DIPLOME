"""R01 P0 acceptance through real HTTP on the integrated server.

Parametrised over backends:
  double — tests/civic/R01/contract_double.py (TEST DOUBLE, in memory)
  r02    — ui.civic_store (R02) on a temporary SQLite file; skipped until delivered.
The same assertions run against both, so the double cannot drift from what the
integrated product must do. Restart persistence is checked only for r02.
"""

from __future__ import annotations

from http.client import HTTPConnection
import importlib
import json
from pathlib import Path
import secrets
import sys
import threading
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contract_double import make_double_gateway  # noqa: E402
from ui.web_server import CivicGateway, Handler, create_server  # noqa: E402

PASSWORD = "Esil-" + secrets.token_urlsafe(12)
USER = "editor_p0"


def _r02_available():
    try:
        importlib.import_module("ui.civic_store.service")
        return True
    except ImportError:
        return False


class Running:
    def __init__(self, gateway):
        self.server = create_server(port=0, civic=gateway)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = None
        self.csrf = None

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def call(self, method, path, payload=None, *, csrf=True, origin=None, cookie=True):
        headers = {"Origin": origin or f"http://127.0.0.1:{self.port}"}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if cookie and self.cookie:
            headers["Cookie"] = self.cookie
        if csrf and self.csrf and method == "POST":
            headers["X-CSRF-Token"] = self.csrf
        conn = HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            conn.request(method, "/api/civic/v1" + path, body=body, headers=headers)
            response = conn.getresponse()
            data = json.loads(response.read().decode("utf-8"))
            cookies = [v for k, v in response.getheaders() if k.lower() == "set-cookie"]
            return response.status, data, cookies
        finally:
            conn.close()

    def login(self, password=PASSWORD):
        status, data, cookies = self.call("POST", "/session/login", {"username": USER, "password": password})
        if status == 200:
            self.cookie = cookies[0].split(";", 1)[0]
            self.csrf = data["data"]["csrf_token"]
        return status, data, cookies


def make_backend(kind, tmp_path):
    if kind == "double":
        gateway, store = make_double_gateway([])
        store.add_editor(USER, PASSWORD)
        return gateway, lambda: None
    if not _r02_available():
        pytest.skip("R02 ui.civic_store not imported in this build")
    db = tmp_path / "civic.sqlite3"

    def build():
        gateway = CivicGateway.for_project(tmp_path, db)
        return gateway

    gateway = build()
    store = gateway.service("store")
    assert store is not None, "R02 store failed to start"
    store.accounts.create_user(USER, PASSWORD, display_name="Редактор P0", public_label="Редакция платформы")
    return gateway, build


@pytest.fixture(params=["double", "r02"])
def backend(request, tmp_path):
    quiet = patch.object(Handler, "log_message", return_value=None)
    quiet.start()
    gateway, rebuild = make_backend(request.param, tmp_path)
    running = Running(gateway)
    running.kind, running.rebuild = request.param, rebuild
    yield running
    running.stop()
    quiet.stop()


DRAFT = {
    "kind": "roadworks", "title": "Проверочный ремонт тротуара (синтетический)",
    "description": "Создано приёмкой R01. Не сведения о реальных работах.", "status": "planned",
    "geometry": {"type": "Point", "coordinates": [71.4304, 51.1282]}, "geometry_precision": "approximate",
    "schedule": {"planned_start": "2026-10-14", "original_planned_end": None,
                 "current_planned_end": "2026-10-30", "actual_end": None},
    "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
    "responsible": {"organization": None, "public_contact": None},
    "evidence_type": "synthetic", "source_refs": [], "evidence_notes": "Приёмочный тест R01.",
}


def create_and_publish(api):
    status, data, _ = api.call("POST", "/staff/objects", DRAFT)
    assert status in (200, 201), data
    item = data["data"]["item"]
    status, data, _ = api.call("POST", f"/staff/objects/{item['id']}/publish",
                               {"expected_revision": item["revision"], "reason": "Первая публикация"})
    assert status == 200, data
    return data["data"]["item"]


def test_unauthenticated_cannot_create_or_publish(backend):
    status, data, _ = backend.call("POST", "/staff/objects", DRAFT)
    assert status == 401 and data["ok"] is False
    status, data, _ = backend.call("GET", "/staff/objects")
    assert status == 401
    status, data, _ = backend.call("GET", "/objects")
    assert status == 200 and data["data"]["items"] == []


def test_login_wrong_password_and_cookie_flags(backend):
    status, data, _ = backend.login(password="wrong-" + PASSWORD)
    assert status == 401 and data["error"]["code"] in ("invalid_credentials", "unauthenticated")
    status, data, cookies = backend.login()
    assert status == 200 and data["data"]["authenticated"] is True and data["data"]["csrf_token"]
    flags = cookies[0].lower()
    assert "httponly" in flags and "samesite=strict" in flags
    assert PASSWORD not in json.dumps(data)


def test_csrf_and_cross_origin_are_enforced(backend):
    backend.login()
    status, data, _ = backend.call("POST", "/staff/objects", DRAFT, csrf=False)
    assert status == 403
    real = backend.csrf
    backend.csrf = "forged-token"
    status, _, _ = backend.call("POST", "/staff/objects", DRAFT)
    assert status == 403
    backend.csrf = real
    status, _, _ = backend.call("POST", "/staff/objects", DRAFT, origin="http://evil.example")
    assert status == 403
    status, data, _ = backend.call("GET", "/staff/objects")
    assert status == 200 and data["data"]["items"] == []


def test_draft_is_private_until_published(backend):
    backend.login()
    status, data, _ = backend.call("POST", "/staff/objects", {**DRAFT, "publication": "published",
                                                               "revision": 99, "actor": "admin", "id": "forced-id"})
    assert status in (200, 201), data
    item = data["data"]["item"]
    assert item["publication"] == "draft" and item["revision"] == 1 and item["id"] != "forced-id"
    assert backend.call("GET", f"/objects/{item['id']}", cookie=False)[0] == 404
    assert backend.call("GET", f"/objects/{item['id']}")[0] == 404  # even with the editor cookie
    status, data, _ = backend.call("GET", "/objects")
    assert all(i["id"] != item["id"] for i in data["data"]["items"])
    status, data, _ = backend.call("POST", f"/staff/objects/{item['id']}/publish",
                                   {"expected_revision": item["revision"], "reason": "Первая публикация"})
    assert status == 200 and data["data"]["item"]["publication"] == "published"
    status, data, _ = backend.call("GET", f"/objects/{item['id']}", cookie=False)
    assert status == 200 and data["data"]["item"]["title"] == DRAFT["title"]
    assert "internal_notes" not in data["data"]["item"]


def test_deadline_move_keeps_original_and_reason(backend):
    backend.login()
    item = create_and_publish(backend)
    assert item["schedule"]["original_planned_end"] == "2026-10-30"
    move = {"schedule": {"current_planned_end": "2026-11-15"}}
    status, data, _ = backend.call("POST", f"/staff/objects/{item['id']}/update",
                                   {"expected_revision": item["revision"], "changes": move, "reason": ""})
    assert status in (400, 422), "published change without reason must fail"
    status, data, _ = backend.call("POST", f"/staff/objects/{item['id']}/update",
                                   {"expected_revision": item["revision"], "changes": move,
                                    "reason": "Погодные условия (тест)"})
    assert status == 200, data
    moved = data["data"]["item"]
    # The public card changes only after the editor publishes the change (R02 model).
    status, data, _ = backend.call("GET", f"/objects/{item['id']}", cookie=False)
    assert data["data"]["item"]["schedule"]["current_planned_end"] == "2026-10-30"
    status, data, _ = backend.call("POST", f"/staff/objects/{item['id']}/publish",
                                   {"expected_revision": moved["revision"], "reason": "Перенос срока: погодные условия"})
    assert status == 200, data
    moved = data["data"]["item"]
    status, data, _ = backend.call("POST", f"/staff/objects/{item['id']}/update",
                                   {"expected_revision": moved["revision"],
                                    "changes": {"schedule": {"original_planned_end": "2026-12-31"}},
                                    "reason": "Попытка переписать исходный срок"})
    assert status in (400, 422), "original deadline must not be rewritten after publication"
    status, data, _ = backend.call("GET", f"/objects/{item['id']}", cookie=False)
    schedule = data["data"]["item"]["schedule"]
    assert schedule["original_planned_end"] == "2026-10-30" and schedule["current_planned_end"] == "2026-11-15"
    assert schedule["actual_end"] is None
    reasons = [h.get("reason") for h in data["data"]["history"]]
    assert "Перенос срока: погодные условия" in reasons
    assert data["data"]["item"]["budget"]["amount_kzt"] is None


def test_stale_revision_conflict(backend):
    backend.login()
    item = create_and_publish(backend)
    first = backend.call("POST", f"/staff/objects/{item['id']}/update",
                         {"expected_revision": item["revision"], "changes": {"title": "Новое название А"},
                          "reason": "Правка А"})
    second = backend.call("POST", f"/staff/objects/{item['id']}/update",
                          {"expected_revision": item["revision"], "changes": {"title": "Новое название Б"},
                           "reason": "Правка Б"})
    assert first[0] == 200 and second[0] == 409


def test_archive_hides_and_logout_closes_staff(backend):
    backend.login()
    item = create_and_publish(backend)
    status, data, _ = backend.call("POST", f"/staff/objects/{item['id']}/archive",
                                   {"expected_revision": item["revision"], "reason": "Работы отменены (тест)"})
    assert status == 200 and data["data"]["item"]["publication"] == "archived"
    assert backend.call("GET", f"/objects/{item['id']}", cookie=False)[0] == 404
    status, _, _ = backend.call("POST", "/session/logout", {})
    assert status == 200
    status, _, _ = backend.call("POST", "/staff/objects", DRAFT)
    assert status in (401, 403)


def test_data_survives_restart(backend, tmp_path):
    if backend.kind != "r02":
        pytest.skip("restart persistence applies to the SQLite backend only")
    backend.login()
    item = create_and_publish(backend)
    backend.stop()
    restarted = Running(backend.rebuild())
    try:
        status, data, _ = restarted.call("GET", f"/objects/{item['id']}")
        assert status == 200 and data["data"]["item"]["revision"] == item["revision"]
        assert any(h.get("reason") == "Первая публикация" for h in data["data"]["history"])
    finally:
        restarted.stop()
        backend.thread = threading.Thread(target=lambda: None)
        backend.server = restarted.server  # already closed; fixture teardown tolerates it
        backend.stop = lambda: None
