"""Локальный демо-сервер модуля R07 (только loopback; не замена ui/web_server.py, который ведёт R01).

    python3 -m engine.civic_scenarios.devserver [--port 8517]
    открыть http://127.0.0.1:8517/civic/scenarios/demo.html

GET — статика из web/ (без листинга, без выхода за каталог), /api/civic/v1/scenarios/* — engine.civic_scenarios.http.
POST /api/civic/v1/scenarios/compare — JSON до 64 КБ, иначе 413.
"""
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .http import MAX_BODY_BYTES, handle

WEB = Path(__file__).resolve().parents[2] / "web"


class H(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json; charset=utf-8", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            if k.lower() != "content-type":
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method, body=None):
        path = urlsplit(self.path).path
        r = handle(method, path, None, body)
        if r is None:
            return False
        self._send(r["status"], r["body"], headers=r["headers"])
        return True

    def do_GET(self):
        if self._api("GET"):
            return
        path = urlsplit(self.path).path
        target = (WEB / path.lstrip("/")).resolve()
        if WEB not in target.parents or not target.is_file():
            return self._send(404, {"ok": False, "error": {"code": "not_found", "message": "not found"}})
        self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY_BYTES:
            return self._send(413, {"ok": False, "error": {"code": "too_large", "message": "тело больше 64 КБ"}})
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else None
        except (ValueError, UnicodeDecodeError):
            return self._send(400, {"ok": False, "error": {"code": "invalid_json", "message": "тело не JSON"}})
        if not self._api("POST", body):
            self._send(404, {"ok": False, "error": {"code": "not_found", "message": "not found"}})

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8517)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"http://127.0.0.1:{a.port}/civic/scenarios/demo.html")
    srv.serve_forever()


if __name__ == "__main__":
    main()
