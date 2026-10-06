"""Локальный демо-сервер R09 (только stdlib, только 127.0.0.1) для проверки UI в браузере.

    python3 tests/civic/R09/demo_server.py [port]   -> печатает "READY <port>"

Отдаёт web/civic/assistant/{demo.html,assistant.js,assistant.css} и два маршрута
AssistantEndpoint на синтетических fixtures. Не заменяет сервер R01: показывает,
как подключить endpoint (тело JSON с лимитом, context с client_ip/is_same_origin).
Редактор в демо — cookie r09demo=editor (заглушка вместо сессии R02).
"""

from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent.civic_assistant.api import AssistantEndpoint, RateLimiter  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
STATIC = {
    "/web/civic/assistant/demo.html": ("text/html; charset=utf-8", ROOT / "web/civic/assistant/demo.html"),
    "/web/civic/assistant/assistant.js": ("text/javascript; charset=utf-8", ROOT / "web/civic/assistant/assistant.js"),
    "/web/civic/assistant/assistant.css": ("text/css; charset=utf-8", ROOT / "web/civic/assistant/assistant.css"),
}
MAX_BODY = 64 * 1024


def _objects():
    data = json.loads((FIX / "objects.json").read_text(encoding="utf-8"))
    o, h = data["objects"], data["history"]
    html = copy.deepcopy(o["full"])
    html.update(id="r09-synth-html", title='<img src=x onerror="window.__xss=1">Синтетика с HTML',
                description="<script>window.__xss=2</script> описание (синтетика)")
    html_hist = [dict(e, object_id="r09-synth-html") for e in h["full"] if e["object_id"] == "r09-synth-full"]
    return {
        "r09-synth-full": (o["full"], h["full"]),
        "r09-synth-missing": (o["missing_deadline"], []),
        "r09-synth-html": (html, html_hist),
        "r09-synth-draft": (o["draft"], []),  # загрузчик «протекает»: второй рубеж отклонит draft
    }


def make_endpoint():
    objects = _objects()
    r07 = json.loads((FIX / "r07_synthetic_result.json").read_text(encoding="utf-8"))
    scenarios = {r07["_provenance"]["case_id"]: r07["result"]}
    return AssistantEndpoint(lambda oid: objects.get(oid), lambda sid: scenarios.get(sid),
                             resolve_principal=lambda ctx: {"name": "demo", "role": "editor"}
                             if "r09demo=editor" in ctx["headers"].get("cookie", "") else None,
                             rate_limiter=RateLimiter(500, 60))


ENDPOINT = make_endpoint()


class Handler(BaseHTTPRequestHandler):
    server_version = "r09-demo"

    def log_message(self, *args):  # тихий режим: без логов запросов (там могут быть тексты вопросов)
        pass

    def _send(self, status, ctype, body: bytes, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                                    "style-src 'self' 'unsafe-inline'; img-src 'self'")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, resp):
        self._send(resp["status"], "application/json; charset=utf-8",
                   json.dumps(resp["body"], ensure_ascii=False).encode("utf-8"),
                   {k: v for k, v in resp["headers"].items() if k.lower() != "content-type"})

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in STATIC:
            ctype, file = STATIC[path]
            return self._send(200, ctype, file.read_bytes())
        if path.startswith("/api/"):
            resp = ENDPOINT.handle("GET", path, {}, None, self._context())
            if resp:
                return self._json(resp)
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def _context(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return {"headers": {k.lower(): v for k, v in self.headers.items()}, "client_ip": self.client_address[0],
                "is_same_origin": origin is None or origin == "http://" + host}

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json({"status": 413, "headers": {}, "body": {"ok": False, "error": {
                "code": "too_large", "message": "тело запроса слишком большое"}}})
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else None
        except (ValueError, UnicodeDecodeError):
            return self._json({"status": 400, "headers": {}, "body": {"ok": False, "error": {
                "code": "invalid_json", "message": "тело не JSON"}}})
        resp = ENDPOINT.handle("POST", path, {}, body, self._context())
        if resp is None:
            return self._json({"status": 404, "headers": {}, "body": {"ok": False, "error": {
                "code": "not_found", "message": "неизвестный путь"}}})
        self._json(resp)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("READY", srv.server_address[1], flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
