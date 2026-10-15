"""Стенд R03 «Спросить Birge» без оболочки R01: статические файлы web/civic/ и POST /api/civic/v2/assistant/ask.

    python3 -B tests/civic/R03/round15/analyst_devserver.py --port 8670
    → http://127.0.0.1:8670/civic/assistant/analyst-demo.html  (?lang=kk, ?q=вопрос)

Только для проверки экрана и кадров: слушает 127.0.0.1, сотрудник — демо-«operator» без входа (в сборке R01
маршрут закрыт сессией и CSRF, staff=True). Числа — настоящие модули FINAL-4 в процессе (R07 карта, R08 «Картина
дня») на их демо-наборе; модулей раунда 15 (R17, R12, R16, R13) здесь нет — их блоки честно «не подключены».
"""
from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.civic_assistant.api import ask  # noqa: E402
from agent.civic_assistant.analyst import core  # noqa: E402

WEB = ROOT / "web"
STAFF = {"username": "operator", "role": "editor"}
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("font/woff2", ".woff2")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def log_message(self, fmt, *args):  # тихо: стенд для кадров
        pass

    def _json(self, status: int, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", ""):
            self.send_response(302)
            self.send_header("Location", "/civic/assistant/analyst-demo.html")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):  # noqa: N802
        if self.path.split("?")[0] != "/api/civic/v2/assistant/ask":
            self._json(404, {"error": "not_found", "message": "Адрес API не найден."})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 64 * 1024:
            self._json(413, {"error": "too_large", "message": "Слишком большой запрос."})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except ValueError:
            self._json(400, {"error": "bad_request", "message": "Тело — JSON."})
            return
        # Та же развилка ошибок, что у шлюза R01 для kind="function" (ui/web_server.py, V2Gateway.handle).
        try:
            self._json(200, ask(body=body if isinstance(body, dict) else {}, principal=STAFF))
        except PermissionError as exc:
            self._json(403, {"error": "forbidden", "message": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": "bad_request", "message": str(exc), "field": "question"})
        except core.TooManyQuestions as exc:
            self._json(429, {"error": "too_many_requests", "message": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8670)
    args = parser.parse_args()
    core.configure(provider=None, rate=(600, 60.0))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"R03 стенд: http://127.0.0.1:{args.port}/civic/assistant/analyst-demo.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
