"""FIXTURE HARNESS R06 — локальный стенд для браузерной проверки формы и модерации.

Не продукт и не замена R01/R02. Показывает, как HTTP-адаптер должен вызвать
FeedbackService.handle: реальные headers, client_ip, is_same_origin, серверный
principal из cookie. Учётные записи — fixture (ui/civic_feedback/fixtures.py),
пароль не нужен, сервер слушает только 127.0.0.1. БД — временный файл.

    python tests/civic/R06/harness/serve_r06.py --port 8766 [--db PATH]
"""

from __future__ import annotations

import argparse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.civic_feedback import FeedbackService  # noqa: E402
from ui.civic_feedback.fixtures import (FIXTURE_EDITOR, FIXTURE_NOTICE, FIXTURE_RESIDENT,  # noqa: E402
                                        broken_classifier, fixture_keyword_classifier, fixture_object_lookup)

HERE = Path(__file__).resolve().parent
STATIC = {
    "/harness/": (HERE / "index.html", "text/html; charset=utf-8"),
    "/harness/harness.js": (HERE / "harness.js", "text/javascript; charset=utf-8"),
    "/web/civic/feedback/feedback.js": (ROOT / "web/civic/feedback/feedback.js", "text/javascript; charset=utf-8"),
    "/web/civic/feedback/feedback.css": (ROOT / "web/civic/feedback/feedback.css", "text/css; charset=utf-8"),
}
MAX_BODY = 64 * 1024
FIXTURE_USERS = {"editor": FIXTURE_EDITOR, "resident": FIXTURE_RESIDENT}


CLASSIFIERS = {"none": None, "fixture": fixture_keyword_classifier, "broken": broken_classifier}


class Harness:
    def __init__(self, db_path: str, *, limits: dict | None = None, classifier: str = "none"):
        self.service = FeedbackService(db_path, fixture_object_lookup, classifier=CLASSIFIERS[classifier],
                                       limits=limits)
        self.sessions: dict[str, dict] = {}

    def principal(self, handler) -> dict | None:
        cookie = SimpleCookie(handler.headers.get("Cookie") or "")
        token = cookie.get("r06_fixture_session")
        return self.sessions.get(token.value) if token else None


def same_origin(handler) -> bool:
    host = handler.headers.get("Host")
    origin = handler.headers.get("Origin")
    if origin:
        return host is not None and origin == f"http://{host}"
    referer = handler.headers.get("Referer")
    if referer:
        parts = urlsplit(referer)
        return parts.scheme == "http" and parts.netloc == host
    # Без Origin/Referer только безопасные методы считаем своими.
    return handler.command in ("GET", "HEAD")


class Handler(BaseHTTPRequestHandler):
    harness: Harness = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # тихий стенд
        pass

    def reply(self, status, payload, headers=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return None
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        path = urlsplit(self.path).path
        if method == "GET" and path in STATIC:
            file, mime = STATIC[path]
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/harness/"):
            return self.harness_api(method, path)
        if path.startswith("/api/civic/v1/"):
            body = self.read_body() if method == "POST" else None
            if body is None and method == "POST":
                return self.reply(413, {"ok": False, "error": {"code": "too_large", "message": "Слишком большой запрос."}})
            context = {"headers": dict(self.headers.items()), "client_ip": self.client_address[0],
                       "is_same_origin": same_origin(self)}
            result = self.harness.service.handle(method, self.path, None, body,
                                                 self.harness.principal(self), context)
            if result is None:
                return self.reply(404, {"ok": False, "error": {"code": "not_found", "message": "Адрес не найден."}})
            return self.reply(result["status"], result["body"], result.get("headers"))
        self.reply(404, {"ok": False, "error": {"code": "not_found", "message": "Адрес не найден."}})

    def harness_api(self, method, path):
        principal = self.harness.principal(self)
        if path == "/harness/session" and method == "GET":
            return self.reply(200, {"ok": True, "data": self.session_data(principal)})
        if not same_origin(self):
            return self.reply(403, {"ok": False, "error": {"code": "cross_origin", "message": "cross origin"}})
        if path == "/harness/login" and method == "POST":
            try:
                role = json.loads(self.read_body() or b"{}").get("role")
            except ValueError:
                role = None
            user = FIXTURE_USERS.get(role)
            if user is None:
                return self.reply(422, {"ok": False, "error": {"code": "validation_failed", "message": "role"}})
            token = secrets.token_urlsafe(24)
            self.harness.sessions[token] = dict(user, csrf_token=secrets.token_urlsafe(24))
            return self.reply(200, {"ok": True, "data": self.session_data(self.harness.sessions[token])},
                              {"Set-Cookie": f"r06_fixture_session={token}; HttpOnly; SameSite=Strict; Path=/"})
        if path == "/harness/logout" and method == "POST":
            cookie = SimpleCookie(self.headers.get("Cookie") or "").get("r06_fixture_session")
            if cookie:
                self.harness.sessions.pop(cookie.value, None)
            return self.reply(200, {"ok": True, "data": self.session_data(None)},
                              {"Set-Cookie": "r06_fixture_session=; Max-Age=0; Path=/"})
        if path == "/harness/expire" and method == "POST":
            # Имитация истёкшей сессии: principal остаётся, но с прошедшим сроком.
            cookie = SimpleCookie(self.headers.get("Cookie") or "").get("r06_fixture_session")
            if cookie and cookie.value in self.harness.sessions:
                self.harness.sessions[cookie.value]["expires_at"] = "2000-01-01T00:00:00Z"
            return self.reply(200, {"ok": True, "data": {"expired": True}})
        return self.reply(404, {"ok": False, "error": {"code": "not_found", "message": "Адрес не найден."}})

    @staticmethod
    def session_data(principal):
        if not principal:
            return {"authenticated": False, "user": None, "csrf_token": None, "fixture_notice": FIXTURE_NOTICE}
        return {"authenticated": True, "user": {"name": principal["name"], "role": principal["role"]},
                "csrf_token": principal["csrf_token"], "fixture_notice": FIXTURE_NOTICE}


def create_server(port: int, db_path: str | None = None, *, per_sender_max: int | None = None,
                  classifier: str = "none"):
    if db_path is None:
        db_path = str(Path(tempfile.mkdtemp(prefix="r06-harness-")) / "feedback.sqlite3")
    limits = {"per_sender_max": per_sender_max} if per_sender_max else None
    Handler.harness = Harness(db_path, limits=limits, classifier=classifier)
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--db", default=None)
    parser.add_argument("--per-sender-max", type=int, default=None,
                        help="лимит сообщений с одного адреса за 10 минут (по умолчанию как в сервисе: 5)")
    parser.add_argument("--classifier", choices=sorted(CLASSIFIERS), default="none",
                        help="none — без модели; fixture — FIXTURE-подсказка по ключевым словам (не R08); broken — ошибка модели")
    args = parser.parse_args()
    server = create_server(args.port, args.db, per_sender_max=args.per_sender_max, classifier=args.classifier)
    print(f"R06 FIXTURE harness: http://127.0.0.1:{server.server_address[1]}/harness/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
