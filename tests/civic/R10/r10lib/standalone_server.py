"""R10 standalone HTTP harness for pushed R02 (+ optional R06) services. NOT product code.

Purpose: run the same black-box HTTP suite against R02's CivicService (and R06's
FeedbackService) before R01 integrates them. The harness only translates HTTP into the
`context` documented in R02 ui/civic_store/service.py (headers, client_ip, host_allowed,
is_same_origin, is_https); every allow/deny decision is the services' own. It serves no
static files, so S08 results in this mode say nothing about the product.

  python -I -B standalone_server.py serve --root <R02 checkout> [--feedback-root <R06 checkout>] \
      --db <file> --port N
  python -I -B standalone_server.py create-editor --root <R02 checkout> --db <file> --username U
"""

from __future__ import annotations

import argparse
import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
from urllib.parse import urlsplit

PREFIX = "/api/civic/v1"
READ_LIMIT = 256 * 1024  # services enforce their own limits; this only bounds the socket read


def load(root: str, feedback_root: str | None):
    sys.path.insert(0, root)
    from ui.civic_store.service import CivicService  # noqa: WPS433 (pinned checkout)

    fb_cls = None
    if feedback_root:
        # R06 lives in its own checkout: extend the already-imported `ui` package path so
        # ui.civic_feedback resolves from that checkout without mixing other files.
        import importlib
        import os

        ui_pkg = importlib.import_module("ui")
        ui_pkg.__path__.append(os.path.join(feedback_root, "ui"))
        fb_cls = importlib.import_module("ui.civic_feedback").FeedbackService
    return CivicService, fb_cls


class Handler(BaseHTTPRequestHandler):
    server_version = "R10-standalone/1"

    def log_message(self, *args):  # no request logging (bodies may hold passwords)
        pass

    def _context(self):
        host = self.headers.get("Host", "")
        port = self.server.server_address[1]
        parsed_host = urlsplit("http://" + host)
        host_allowed = parsed_host.hostname in {"127.0.0.1", "localhost", "::1"} and parsed_host.port == port
        origin = self.headers.get("Origin")
        same = None if not origin else (origin == f"http://{host}")
        return {"headers": {k: v for k, v in self.headers.items()},
                "client_ip": self.client_address[0], "host_allowed": host_allowed,
                "is_same_origin": same, "is_https": False}

    def _send(self, reply):
        if reply is None:
            reply = {"status": 404, "headers": {},
                     "body": {"ok": False, "error": {"code": "not_found", "message": "R10 harness: no route"}}}
        data = json.dumps(reply["body"], ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(reply["status"])
        sent_ct = False
        for name, value in (reply.get("headers") or {}).items():
            for item in (value if isinstance(value, (list, tuple)) else [value]):
                self.send_header(name, str(item))
                sent_ct |= name.lower() == "content-type"
        if not sent_ct:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _dispatch(self, method):
        parsed = urlsplit(self.path)
        if not (parsed.path == PREFIX or parsed.path.startswith(PREFIX + "/")):
            self._send({"status": 404, "headers": {}, "body": {"ok": False, "error": {
                "code": "not_found", "message": "R10 harness serves only the API"}}})
            return
        body = None
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            body = self.rfile.read(min(max(length, 0), READ_LIMIT)) if length > 0 else b""
        context = self._context()
        store = self.server.store
        reply = None
        if self.server.feedback is not None:
            principal = store.resolve_principal(context)
            reply = self.server.feedback.handle(method, parsed.path, parsed.query, body, principal, context)
        if reply is None:
            reply = store.handle(method, parsed.path, parsed.query, body, context)
        self._send(reply)

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PUT(self):
        self._dispatch("PUT")


def serve(args):
    service_cls, fb_cls = load(args.root, args.feedback_root)
    store = service_cls(args.db)
    feedback = None
    if fb_cls is not None:
        def object_lookup(object_id):
            # Public projection only: what a resident may attach feedback to.
            r = store.handle("GET", f"{PREFIX}/objects/{object_id}", "", None,
                             {"headers": {}, "client_ip": "127.0.0.1", "host_allowed": True,
                              "is_same_origin": None, "is_https": False})
            if r and r["status"] == 200:
                return r["body"]["data"]["item"]
            return None

        feedback = fb_cls(args.db, object_lookup)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.store, server.feedback = store, feedback
    try:
        server.serve_forever()
    finally:
        server.server_close()


def create_editor(args):
    service_cls, _ = load(args.root, None)
    store = service_cls(args.db)
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("passwords differ", file=sys.stderr)
        sys.exit(2)
    store.accounts.create_user(args.username, first)
    print(f"editor {args.username} created")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--root", required=True)
    s.add_argument("--feedback-root")
    s.add_argument("--db", required=True)
    s.add_argument("--port", type=int, required=True)
    c = sub.add_parser("create-editor")
    c.add_argument("--root", required=True)
    c.add_argument("--db", required=True)
    c.add_argument("--username", required=True)
    args = ap.parse_args()
    serve(args) if args.cmd == "serve" else create_editor(args)


if __name__ == "__main__":
    main()
