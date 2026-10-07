"""R01 self-review fixes in the gateway (round 11, second review run).

C13  resident feedback is checked against the PUBLIC object, not an unpublished staff edit;
C14  an existing parent folder of --civic-db keeps its permissions;
C15  only a missing role package is "not delivered", other import errors are init failures;
C16  the DB path is expanded/resolved;
C1   a 414 on a civic path is a JSON envelope, not an HTML page.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_r01_gateway import raw_request  # noqa: E402
from test_r01_p0_api import DRAFT, PASSWORD, USER, Running, create_and_publish  # noqa: E402
from ui.web_server import CivicGateway, Handler, ModuleNotDelivered, create_server, resolve_db_path  # noqa: E402

POINT_A = [71.4304, 51.1282]
POINT_B = [71.5304, 51.1282]  # ~7 km east of A, well beyond R06's 1.5 km location check


@pytest.fixture()
def integrated(tmp_path):
    pytest.importorskip("ui.civic_store.service")
    pytest.importorskip("ui.civic_feedback.service")
    quiet = patch.object(Handler, "log_message", return_value=None)
    quiet.start()
    gateway = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    gateway.service("store").accounts.create_user(USER, PASSWORD, display_name="Редактор", public_label="Редакция")
    running = Running(gateway)
    yield running
    running.stop()
    quiet.stop()


def feedback(point, object_id):
    return {"object_id": object_id, "geometry": {"type": "Point", "coordinates": point}, "category": "roads",
            "text": "Проверка места сообщения относительно опубликованной точки", "consent_public": False}


def test_feedback_location_uses_published_geometry_not_staff_edit(integrated):
    integrated.login()
    item = create_and_publish(integrated)
    assert item["geometry"]["coordinates"] == POINT_A == DRAFT["geometry"]["coordinates"]
    status, data, _ = integrated.call("POST", f"/staff/objects/{item['id']}/update",
                                      {"expected_revision": item["revision"], "reason": "Уточнение места (тест)",
                                       "changes": {"geometry": {"type": "Point", "coordinates": POINT_B}}})
    assert status == 200, data
    status, data, _ = integrated.call("GET", f"/objects/{item['id']}", cookie=False)
    assert data["data"]["item"]["geometry"]["coordinates"] == POINT_A, "residents still see A"

    status, data, _ = integrated.call("POST", "/feedback", feedback(POINT_B, item["id"]), cookie=False, csrf=False)
    assert status == 422 and data["error"]["code"] == "location_conflict", data
    status, data, _ = integrated.call("POST", "/feedback", feedback(POINT_A, item["id"]), cookie=False, csrf=False)
    assert status in (200, 201), data


def test_feedback_on_draft_is_rejected_like_missing(integrated):
    integrated.login()
    status, data, _ = integrated.call("POST", "/staff/objects", DRAFT)
    draft_id = data["data"]["item"]["id"]
    status, data, _ = integrated.call("POST", "/feedback", feedback(POINT_A, draft_id), cookie=False, csrf=False)
    assert status == 422 and data["error"]["code"] == "object_not_found"


def test_existing_parent_folder_keeps_its_mode(tmp_path):
    pytest.importorskip("ui.civic_store.service")
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    os.chmod(shared, 0o755)
    gateway = CivicGateway.for_project(tmp_path, shared / "civic.sqlite3")
    assert gateway.service("store") is not None
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert stat.S_IMODE((shared / "civic.sqlite3").stat().st_mode) == 0o600
    created = tmp_path / "new" / "civic.sqlite3"
    assert CivicGateway.for_project(tmp_path, created).service("store") is not None
    assert stat.S_IMODE(created.parent.stat().st_mode) == 0o700


def test_db_path_is_expanded_and_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_db_path("~/x/civic.sqlite3") == (tmp_path / "x" / "civic.sqlite3").resolve()
    assert resolve_db_path("rel.sqlite3").is_absolute()
    assert resolve_db_path(None) is None and resolve_db_path("") is None


def _raise(exc):
    def factory():
        raise exc
    return factory


def test_only_missing_role_package_is_not_delivered():
    gateway = CivicGateway({
        "store": _raise(ModuleNotFoundError("No module named 'ui.civic_store'", name="ui.civic_store")),
        "feedback": _raise(ModuleNotDelivered("feedback needs the object store")),
        "scenarios": _raise(ModuleNotFoundError("No module named 'numpy'", name="numpy")),
        "assistant": _raise(ImportError("cannot import name 'x' from 'agent.civic_assistant.api'")),
    })
    with patch("ui.web_server.LOGGER"):
        status = {name: info["status"] for name, info in gateway.modules().items()}
    assert status == {"store": "unavailable", "feedback": "unavailable",
                      "scenarios": "init_failed", "assistant": "init_failed"}


def test_uri_too_long_on_civic_path_is_json(tmp_path):
    server = create_server(port=0, civic=CivicGateway({}))
    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    with patch.object(Handler, "log_message", return_value=None):
        thread.start()
        try:
            port = server.server_address[1]
            head, body = raw_request(port, b"GET /api/civic/v1/objects?q=" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n")
            assert " 414 " in head.splitlines()[0], head
            assert "application/json" in head
            assert json.loads(body.decode("utf-8"))["ok"] is False
            head, body = raw_request(port, b"GET /?q=" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n")
            assert " 414 " in head.splitlines()[0]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
