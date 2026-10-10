"""Тестовый сервер R12: только GET /api/civic/v2/{targets,street-segment,street-snap,objects-near,yard,geo/status}
поверх engine.civic_geo.api.handle. Для браузерных проверок редактора с НАСТОЯЩИМ графом OSM.

    python3 -B tests/civic/R12/geo_api_server.py [port]      (127.0.0.1; печатает «READY <port>»)
Заголовок Access-Control-Allow-Origin: * — только здесь, для стенда на другом порту. В продукте маршруты
подключает R01 в ui/web_server.py (same-origin).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from engine.civic_geo import api  # noqa: E402

PREFIX = "/api/civic/v2"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        u = urlsplit(self.path)
        result = api.handle(u.path[len(PREFIX):], parse_qs(u.query)) if u.path.startswith(PREFIX) else None
        status, body = result if result else (404, {"error": {"code": "not_found", "message": "нет такого маршрута"}})
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    api.warm_up()
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 0), Handler)
    print("READY", srv.server_address[1], flush=True)
    srv.serve_forever()
