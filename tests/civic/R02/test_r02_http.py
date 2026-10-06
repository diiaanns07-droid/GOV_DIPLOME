"""R02: реальные HTTP-запросы к временному серверу, многопоточность, перезапуск и патч для R01."""

from __future__ import annotations

from contextlib import contextmanager
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading
import types

import pytest

from ui.civic_store.db import REPO_ROOT
from ui.civic_store.http_adapter import CivicHttpAdapter, make_reference_handler
from ui.civic_store.service import CivicService
from r02_helpers import PASSWORD, sample_object


PATCH = REPO_ROOT / "research" / "round-11-results" / "R02" / "web_server.patch"


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def reference_server(db_path):
    service = CivicService(db_path)
    adapter = CivicHttpAdapter(service)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_reference_handler(adapter))
    server.daemon_threads = True
    return server, service


class Client:
    def __init__(self, port, origin=True):
        self.port = port
        self.cookie = None
        self.csrf = None
        self.origin = origin

    def request(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        hdrs = {"Host": f"127.0.0.1:{self.port}"}
        if self.origin and method not in ("GET", "HEAD"):
            hdrs["Origin"] = f"http://127.0.0.1:{self.port}"
        if self.cookie:
            hdrs["Cookie"] = f"civic_session={self.cookie}"
        if self.csrf:
            hdrs["X-CSRF-Token"] = self.csrf
        data = raw
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        try:
            conn.request(method, "/api/civic/v1" + path, body=data, headers=hdrs)
            response = conn.getresponse()
            payload = response.read()
            parsed = json.loads(payload) if payload else None
            return response.status, dict(response.getheaders()), parsed
        finally:
            conn.close()

    def login(self, username="editor1", password=PASSWORD):
        status, headers, body = self.request("POST", "/session/login", {"username": username, "password": password})
        assert status == 200, body
        self.cookie = headers["Set-Cookie"].split(";")[0].split("=", 1)[1]
        status, _, body = self.request("GET", "/session")
        self.csrf = body["data"]["csrf_token"]
        return self


@pytest.fixture
def http_service(tmp_path):
    server, service = reference_server(tmp_path / "http.sqlite3")
    service.accounts.create_user("editor1", PASSWORD, display_name="Редактор Один")
    service.accounts.create_user("editor2", PASSWORD + "x", display_name="Редактор Два")
    with running(server) as port:
        yield port, service, tmp_path / "http.sqlite3"


def test_full_editor_flow_over_http(http_service):
    port, service, db_path = http_service
    anonymous = Client(port)
    status, headers, body = anonymous.request("GET", "/session")
    assert status == 200 and body == {"ok": True, "data": {"authenticated": False, "user": None, "csrf_token": None}}
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Cache-Control"] == "no-store" and headers["X-Content-Type-Options"] == "nosniff"

    editor = Client(port).login()
    status, _, body = editor.request("POST", "/staff/objects", sample_object())
    assert status == 201
    item = body["data"]["item"]
    status, _, body = anonymous.request("GET", f"/objects/{item['id']}")
    assert status == 404 and body["ok"] is False
    status, _, body = editor.request("POST", f"/staff/objects/{item['id']}/publish",
                                     {"expected_revision": item["revision"], "reason": "Первая публикация"})
    assert status == 200
    item = body["data"]["item"]
    status, _, body = editor.request("POST", f"/staff/objects/{item['id']}/update", {
        "expected_revision": item["revision"], "reason": "Перенос: погода",
        "changes": {"schedule": {"current_planned_end": "2026-10-30"}}})
    item = body["data"]["item"]
    status, _, body = editor.request("POST", f"/staff/objects/{item['id']}/publish",
                                     {"expected_revision": item["revision"], "reason": "Срок перенесён: погода"})
    assert status == 200
    status, _, body = anonymous.request("GET", f"/objects/{item['id']}")
    assert body["data"]["item"]["schedule"]["current_planned_end"] == "2026-10-30"
    assert body["data"]["history"][-1]["reason"] == "Срок перенесён: погода"
    status, _, listing = anonymous.request("GET", "/objects?kind=roadworks&from=2026-10-01")
    assert [entry["id"] for entry in listing["data"]["items"]] == [item["id"]]

    status, headers, body = editor.request("POST", "/session/logout", {})
    assert status == 200 and "Max-Age=0" in headers["Set-Cookie"]
    status, _, body = editor.request("GET", "/staff/objects")
    assert status == 401

    # Перезапуск: новый сервер на той же базе отдаёт ту же публичную карточку и историю.
    server, _ = reference_server(db_path)
    with running(server) as new_port:
        status, _, again = Client(new_port).request("GET", f"/objects/{item['id']}")
    assert status == 200 and again["data"]["history"][-1]["reason"] == "Срок перенесён: погода"


def test_transport_level_errors_use_civic_envelope(http_service):
    port, service, _ = http_service
    client = Client(port).login()
    status, _, body = client.request("POST", "/staff/objects", raw=b"x" * (70 * 1024),
                                     headers={"Content-Type": "application/json"})
    assert status == 413 and body["error"]["code"] == "payload_too_large"
    status, _, body = client.request("POST", "/staff/objects", raw=b"title=x",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert status == 415
    status, _, body = client.request("POST", "/staff/objects", raw=b'{"title": NaN}',
                                     headers={"Content-Type": "application/json"})
    assert status == 400 and body["error"]["code"] == "bad_request"
    status, _, body = client.request("GET", "/no/such/path")
    assert status == 404 and body == {"ok": False, "error": {"code": "not_found", "message": "Ресурс не найден."}}
    status, headers, body = client.request("DELETE", "/staff/objects/ast-1")
    assert status == 405 and "DELETE" not in headers["Allow"]
    status, headers, body = client.request("HEAD", "/objects")
    assert status == 200 and body is None


def test_origin_and_host_checks_over_http(http_service):
    port, _, _ = http_service
    client = Client(port).login()
    status, _, body = client.request("POST", "/staff/objects", sample_object(),
                                     headers={"Origin": "http://evil.example"})
    assert status == 403 and body["error"]["code"] == "cross_origin"
    status, _, body = client.request("POST", "/staff/objects", sample_object(),
                                     headers={"Origin": "null"})
    assert status == 403
    status, _, body = client.request("GET", "/staff/objects", headers={"Host": "evil.example"})
    assert status == 403 and body["error"]["code"] == "forbidden_host"
    status, _, body = Client(port).request("POST", "/session/login", {"username": "editor1", "password": PASSWORD},
                                           headers={"Origin": "http://evil.example"})
    assert status == 403
    status, _, _ = client.request("POST", "/staff/objects", sample_object(),
                                  headers={"Sec-Fetch-Site": "same-origin"})
    assert status == 201  # Origin совпадает с Host
    no_origin = Client(port, origin=False)
    no_origin.cookie, no_origin.csrf = client.cookie, client.csrf
    status, _, _ = no_origin.request("POST", "/staff/objects", sample_object(),
                                     headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403


def test_parallel_http_writes_and_races(http_service):
    port, service, _ = http_service
    first, second = Client(port).login(), Client(port).login("editor2", PASSWORD + "x")
    statuses, errors = [], []

    def create_many(client, count):
        try:
            for index in range(count):
                status, _, body = client.request("POST", "/staff/objects", sample_object(title=f"Параллельно {index}"))
                statuses.append(status)
        except Exception as exc:  # pragma: no cover - отчёт о сбое потока
            errors.append(repr(exc))

    threads = [threading.Thread(target=create_many, args=(client, 6))
               for client in (first, second, first, second, first, second, first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert errors == [] and statuses == [201] * 48
    status, _, body = first.request("GET", "/staff/objects?limit=100")
    assert len(body["data"]["items"]) == 48

    item = body["data"]["items"][0]
    for attempt in range(3):
        barrier = threading.Barrier(2)
        results = []

        def update(client, label):
            barrier.wait()
            status, _, _ = client.request("POST", f"/staff/objects/{item['id']}/update", {
                "expected_revision": item["revision"], "changes": {"title": f"{label}-{attempt}"}, "reason": "гонка"})
            results.append(status)

        racers = [threading.Thread(target=update, args=(c, n)) for c, n in ((first, "a"), (second, "b"))]
        for racer in racers:
            racer.start()
        for racer in racers:
            racer.join(30)
        assert sorted(results) == [200, 409]
        status, _, fresh = first.request("GET", f"/staff/objects/{item['id']}")
        item = fresh["data"]["item"]
    history = fresh["data"]["history"]
    assert [h["revision"] for h in history] == list(range(1, item["revision"] + 1))
    assert service.db.open_connections == 0


def load_patched_web_server(tmp_path):
    """Применяет web_server.patch к копии общего файла и загружает её (сам файл не меняется)."""
    work = tmp_path / "patched"
    (work / "ui").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "ui" / "web_server.py", work / "ui" / "web_server.py")
    result = subprocess.run(["git", "apply", str(PATCH)], cwd=work, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    source = (work / "ui" / "web_server.py").read_text(encoding="utf-8")
    module = types.ModuleType("web_server_patched_r02")
    module.__file__ = str(REPO_ROOT / "ui" / "web_server.py")  # ROOT остаётся корнем репозитория
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


@pytest.mark.skipif(not (REPO_ROOT / "ui" / "web_server.py").exists(), reason="нет ui/web_server.py")
def test_patch_applies_to_real_web_server_and_serves_both_apis(tmp_path):
    module = load_patched_web_server(tmp_path)
    db = tmp_path / "patched.sqlite3"
    server = module.create_server(port=0, civic_db=db)
    server.civic.civic.accounts.create_user("editor1", PASSWORD)
    with running(server) as port:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.request("GET", "/api/health")
        assert json.loads(conn.getresponse().read()) == {"status": "ok"}  # старое API не тронуто
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        conn.request("POST", "/api/validate", body=json.dumps({"decisions": []}),
                     headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}"})
        legacy = conn.getresponse()
        assert legacy.status == 200 and "valid" in json.loads(legacy.read())
        conn.close()
        client = Client(port).login()
        status, _, body = client.request("POST", "/staff/objects", sample_object())
        assert status == 201
        status, _, body = client.request("POST", f"/staff/objects/{body['data']['item']['id']}/publish",
                                         {"expected_revision": 1, "reason": "Публикация через общий Handler"})
        assert status == 200
        status, _, body = Client(port).request("GET", "/objects")
        assert status == 200 and len(body["data"]["items"]) == 1
        status, _, body = client.request("DELETE", "/objects/x")
        assert status == 405 and body["ok"] is False
        status, _, body = client.request("GET", "/feedback")
        assert status == 404 and body["error"]["code"] == "not_found"
    # Без civic_db сервер работает как раньше (существующие тесты не создают базу).
    plain = module.create_server(port=0)
    assert plain.civic is None
    plain.server_close()


def test_runtime_database_files_are_not_in_web_or_git():
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    assert not [path for path in tracked if path.endswith((".sqlite", ".sqlite3", ".db", "-wal", "-shm",
                                                           ".wal", ".shm"))]
    web = REPO_ROOT / "web"
    if web.exists():
        assert not [p for p in web.rglob("*") if p.suffix in (".sqlite", ".sqlite3", ".db", ".wal", ".shm")
                    or p.name.endswith(("-wal", "-shm"))]
    runtime = REPO_ROOT / ".runtime"
    if runtime.exists():
        ignored = subprocess.run(["git", "check-ignore", "-q", str(runtime / "civic.sqlite3")], cwd=REPO_ROOT)
        assert ignored.returncode == 0
