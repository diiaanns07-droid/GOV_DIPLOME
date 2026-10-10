"""R05 · стенд для проверки освещения с настоящим движком улиц R12 (engine.civic_geo).

    python3 tests/civic/R05/build3d/geo_stand.py --r12 <рабочая копия ветки R12> --port 8617

Отдаёт статику web/ ЭТОЙ ветки и маршруты R12 /api/civic/v2/street-snap, /street-segment, /targets …
через engine.civic_geo.api.handle(path, query) — так, как их подключит R01 (INTEGRATION R12 §1).
/api/civic/v2/proposals — 404 (сервера предложений здесь нет: модуль честно работает на заглушке).
Ничего не пишет в репозиторий.
"""

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

WEB = Path(__file__).resolve().parents[4] / "web"
MIME = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml", ".html": "text/html; charset=utf-8", ".woff2": "font/woff2"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r12", required=True, help="рабочая копия ветки R12 (engine/civic_geo, data/civic/astana/geo)")
    ap.add_argument("--port", type=int, default=8617)
    args = ap.parse_args()
    sys.path.insert(0, str(Path(args.r12).resolve()))
    from engine.civic_geo import api  # noqa: E402  (код R12, только чтение)
    import threading  # noqa: E402

    # Прогрев графа улиц в фоне (R12 INTEGRATION §1): первый запрос иначе ждёт загрузки графа.
    if hasattr(api, "warm_up"):
        threading.Thread(target=api.warm_up, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parts = urlsplit(self.path)
            if parts.path.startswith("/api/civic/v2/"):
                result = api.handle(parts.path[len("/api/civic/v2"):], parse_qs(parts.query))
                if result is None:
                    return self.send(404, b'{"error":"not_found","message":"no route"}', "application/json; charset=utf-8")
                code, body = result
                return self.send(code, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            target = (WEB / parts.path.lstrip("/")).resolve()
            if not target.is_relative_to(WEB) or not target.is_file():
                return self.send(404, b"not found", "text/plain")
            self.send(200, target.read_bytes(), MIME.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({"url": "http://127.0.0.1:%d/civic/build3d/demo.html" % args.port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
