"""Стенд R12 для QR-паспорта и листа печати (только для тестов; 127.0.0.1).

    python3 -B tests/civic/R12/qr/qr_stand.py [port]     -> печатает «READY <port>»

- GET  /api/civic/v2/target?id=…        НАСТОЯЩИЙ engine/civic_geo (граф и объекты OSM Астаны)
- GET  /api/civic/v2/heat/target?…      СИНТЕТИКА из heat_fixture.json (как отвечает R07; нет записи — 404)
- POST /api/civic/v2/complaints/<id>/metoo   запоминает вызов и прибавляет 1 к числу людей (СИНТЕТИКА)
- GET  /api/test/calls                   что приходило на «Я тоже» (для проверок)
- статика: /civic/** и /vendor/** из web/, /stand/** из этой папки;
  /vendor/qrcode/qrcode.js — настоящий файл LOCAL-11, если есть; ?fakeqr подменяет его ТЕСТОВОЙ заглушкой.
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from engine.civic_geo import api  # noqa: E402

TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2"}
HEAT = json.loads((HERE / "heat_fixture.json").read_text("utf-8"))["items"]
CALLS = []
STATE = {"fail_target": 0, "fail_heat": 0, "fake_qr": False}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static(self, rel_root: Path, rel: str):
        p = (rel_root / rel).resolve()
        if not str(p).startswith(str(rel_root.resolve())) or not p.is_file():
            return self._send(404, {"error": "not_found"})
        self._send(200, p.read_bytes(), TYPES.get(p.suffix, "application/octet-stream"))

    def do_GET(self):  # noqa: N802
        u = urlsplit(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/test/calls":
            return self._send(200, {"calls": CALLS})
        if u.path == "/api/test/set":
            for k in ("fail_target", "fail_heat"):
                if k in q:
                    STATE[k] = int(q[k][0])
            if "fake_qr" in q:
                STATE["fake_qr"] = q["fake_qr"][0] == "1"
            return self._send(200, STATE)
        if u.path == "/api/civic/v2/target":
            if STATE["fail_target"]:
                STATE["fail_target"] -= 1
                return self._send(500, {"error": {"code": "internal", "message": "test"}})
            status, body = api.handle("/target", q)
            return self._send(status, body)
        if u.path == "/api/civic/v2/heat/target":
            if STATE["fail_heat"]:
                STATE["fail_heat"] -= 1
                return self._send(500, {"error": "internal"})
            item = HEAT.get((q.get("id") or [""])[0])
            return self._send(200, {"item": item}) if item else self._send(404, {"error": "not_found"})
        if u.path == "/vendor/qrcode/qrcode.js":
            if STATE["fake_qr"]:
                return self._static(HERE, "fake_qrcode.js")
            return self._static(ROOT / "web", "vendor/qrcode/qrcode.js")
        if u.path.startswith("/civic/") or u.path.startswith("/vendor/"):
            return self._static(ROOT / "web", u.path.lstrip("/"))
        if u.path.startswith("/stand/"):
            return self._static(HERE, u.path[len("/stand/"):] or "stand.html")
        return self._send(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        u = urlsplit(self.path)
        m = re.match(r"^/api/civic/v2/complaints/([A-Za-z0-9._:-]{1,96})/metoo$", u.path)
        if not m:
            return self._send(404, {"error": "not_found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0) or 0) or b"{}")
        CALLS.append({"complaint_id": m.group(1), "device_id": body.get("device_id")})
        for item in HEAT.values():
            if m.group(1) in item.get("open_ids", []):
                item["count"] += 1
        return self._send(200, {"ok": True})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    api.warm_up()
    srv = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 0), Handler)
    print("READY", srv.server_address[1], flush=True)
    srv.serve_forever()
