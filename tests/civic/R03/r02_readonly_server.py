"""R03 read-only integration harness for R02's CivicService (round 11).

Runs R02's real service (imported from a directory given by --r02-root, e.g. an
`git archive <R02 SHA> ui/civic_store` extraction) on a temporary SQLite file,
seeds R03's synthetic fixtures through R02's own staff API, then serves:
  /api/civic/v1/...                    -> CivicService.handle (public reads by the browser)
  /web/, /research/round-11-results/R03/, /tests/civic/R03/fixtures/  -> static (same allowlist as serve.mjs)
  /__r03/log                           -> JSON list of API requests made AFTER seeding (test probe)
Prints one JSON line {"port":..,"ids":{fixture_id: server_id},"seeded":..} on stdout when ready.

Nothing here edits R02 code or the repository; the DB lives in a temp dir and is deleted on exit.
The staff password is random per run and never written anywhere.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading

REPO = Path(__file__).resolve().parents[3]
ALLOWED = ("web/", "research/round-11-results/R03/", "tests/civic/R03/fixtures/")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".png": "image/png", ".svg": "image/svg+xml"}
CONTENT = ("kind", "title", "description", "status", "geometry", "geometry_precision", "schedule",
           "budget", "responsible", "evidence_type", "source_refs", "evidence_notes")


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 6, 6, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(minutes=3)
        return self.now


def ctx(cookie=None, csrf=None):
    headers = {"Host": "127.0.0.1"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": "127.0.0.1", "host_allowed": True,
            "is_same_origin": True, "is_https": False}


def seed(service, auth_mod, fixtures, history):
    """Create, publish and reschedule fixture objects through R02's staff API."""
    password = secrets.token_urlsafe(18) + "Aa1!"
    service.accounts.create_user("r03seed", password, display_name="R03 seed",
                                 public_label="Редакция (демо R03)")
    login = service.handle("POST", "/api/civic/v1/session/login", None,
                           json.dumps({"username": "r03seed", "password": password}).encode(), ctx())
    assert login and login["status"] == 200, login
    cookie = login["headers"]["Set-Cookie"].split(";", 1)[0]
    csrf = login["body"]["data"]["csrf_token"]

    def post(path, body):
        r = service.handle("POST", "/api/civic/v1" + path, None, json.dumps(body).encode(), ctx(cookie, csrf))
        if r["status"] >= 300:
            raise RuntimeError(f"{path}: {r['status']} {json.dumps(r['body'], ensure_ascii=False)}")
        return r["body"]["data"]["item"]

    ids, notes = {}, []
    for fx in fixtures:
        body = {k: copy.deepcopy(fx[k]) for k in CONTENT if k in fx}
        if body.get("evidence_type") == "synthetic" and (body.get("budget") or {}).get("amount_kzt") is not None:
            body["budget"] = {"amount_kzt": None, "basis": "unknown", "source_id": None}
            notes.append(f"{fx['id']}: amount dropped (R02: synthetic record cannot carry tenge)")
        if len(body["title"]) > 200:
            body["title"] = body["title"][:199] + "…"
            notes.append(f"{fx['id']}: title cut to R02 max 200")
        sched = body["schedule"]
        final_end = sched.get("current_planned_end")
        # R02 locks original_planned_end at first publication; create with the original end
        # as the current one, publish, then move the current end with a public reason.
        first_end = sched.get("original_planned_end") or final_end
        sched["original_planned_end"] = None
        sched["current_planned_end"] = first_end
        item = post("/staff/objects", body)
        ids[fx["id"]] = item["id"]
        if fx.get("_r03_draft"):
            continue
        item = post(f"/staff/objects/{item['id']}/publish", {"expected_revision": item["revision"],
                                                              "reason": "Демо R03: публикация синтетической записи"})
        if final_end and final_end != first_end:
            reason = next((h["reason"] for h in reversed(history.get(fx["id"], []))
                           if any(str(c if isinstance(c, str) else c.get("field")).startswith("schedule")
                                  for c in h["changed_fields"])), "Демо R03: перенос срока")
            # R02 updates take whole top-level content fields; the locked original stays as is.
            schedule = dict(item["schedule"], current_planned_end=final_end)
            item = post(f"/staff/objects/{item['id']}/update", {
                "expected_revision": item["revision"], "reason": reason,
                "changes": {"schedule": schedule}})
            item = post(f"/staff/objects/{item['id']}/publish", {"expected_revision": item["revision"],
                                                                  "reason": reason})
        if fx.get("_r03_archive"):
            post(f"/staff/objects/{item['id']}/archive", {"expected_revision": item["revision"],
                                                          "reason": "Демо R03: снято с публикации"})
    service.handle("POST", "/api/civic/v1/session/logout", None, b"{}", ctx(cookie, csrf))
    return ids, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r02-root", required=True)
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    sys.path.insert(0, str(Path(args.r02_root).resolve()))
    from ui.civic_store import auth as auth_mod  # noqa: E402  (R02 code at the pinned SHA)
    from ui.civic_store.service import CivicService  # noqa: E402

    fixtures = json.loads((REPO / "tests/civic/R03/fixtures/objects.json").read_text("utf-8"))["items"]
    history = json.loads((REPO / "tests/civic/R03/fixtures/history.json").read_text("utf-8"))["history"]
    fixtures = [f for f in fixtures if f["id"] != "demo-astana-work-01"]
    extra = copy.deepcopy(fixtures[1])
    extra.update(id="r03-r02-draft", title="Черновик R03 — не должен быть публичным", _r03_draft=True)
    gone = copy.deepcopy(fixtures[2])
    gone.update(id="r03-r02-archived", title="Снятая с публикации запись R03", _r03_archive=True)

    tmp = tempfile.TemporaryDirectory(prefix="r03-r02-")
    service = CivicService(Path(tmp.name) / "civic.sqlite3", clock=Clock())
    ids, notes = seed(service, auth_mod, fixtures + [extra, gone], history)
    log, lock = [], threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, body, ctype="application/json; charset=utf-8", headers=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                if k.lower() in ("content-type", "cache-control"):
                    continue
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _api(self, method):
            path, _, query = self.path.partition("?")
            with lock:
                log.append({"method": method, "path": path, "query": query})
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            context = {"headers": dict(self.headers.items()), "client_ip": self.client_address[0],
                       "host_allowed": True, "is_same_origin": None, "is_https": False}
            reply = service.handle(method, path, query, body, context)
            if reply is None:
                reply = {"status": 404, "headers": {}, "body": {"ok": False, "error": {"code": "not_found", "message": "Адрес API не найден."}}}
            self._send(reply["status"], reply["body"], headers=reply.get("headers"))

        def do_GET(self):
            if self.path.startswith("/api/civic/v1"):
                return self._api("GET")
            if self.path == "/__r03/log":
                with lock:
                    return self._send(200, list(log))
            rel = self.path.split("?", 1)[0].lstrip("/")
            if rel.endswith("/") or not rel:
                rel += "index.html"
            target = (REPO / rel).resolve()
            if ".." in rel or not str(target).startswith(str(REPO) + "/") or not rel.startswith(ALLOWED) or not target.is_file():
                return self._send(404, b"", "text/plain")
            self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))

        def do_POST(self):
            if self.path.startswith("/api/civic/v1"):
                return self._api("POST")
            self._send(405, b"", "text/plain")

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({"port": httpd.server_address[1], "ids": ids, "notes": notes,
                      "seeded": len(ids)}, ensure_ascii=False), flush=True)
    try:
        httpd.serve_forever()
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    main()
