"""Демо-сервер R07 — ТОЛЬКО для разработки, скриншотов и показа, пока R01 не подключил маршруты в ui/web_server.py.

    python -m ui.civic_heat.devserver            # http://127.0.0.1:8617/civic/heat/demo.html
    python -m ui.civic_heat.devserver --port 8620

Отдаёт папку web/ и маршруты:
    GET  /api/civic/v2/heat, /heat/meta, /heat/target       — настоящий модуль ui/civic_heat (api.handle_get)
    POST /api/civic/v2/complaints/{id}/status {status}      — ПОДСТАВНОЙ двойник R09 (меняет демо-записи в памяти)
    POST /api/civic/v2/complaints/{id}/metoo {device_id}    — ПОДСТАВНОЙ двойник R09 (одно «Я тоже» с устройства)
    POST /api/civic/v2/heat/demo/complaint {target_id}      — добавить демо-жалобу (для показа пульса)
Все данные синтетические (demo: true) и живут только в памяти процесса.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import api, demo_seed
from .engine import iso
from .service import HeatService

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
STATUSES = ("new", "accepted", "in_progress", "fixed", "rejected")


class DemoStore:
    """Демо-записи в памяти + подставные операции R09 (status, metoo)."""

    def __init__(self, now=None):
        self.lock = threading.Lock()
        self.records = demo_seed.demo_records(now=now)
        self.metoo_devices: dict[str, set] = {}
        # стенд сам отвечает на статус и «Я тоже» примеров — действия с ними работают
        self.service = HeatService(source=lambda since: self.snapshot(), examples_actionable=True)

    def snapshot(self):
        with self.lock:
            return [dict(r) for r in self.records]

    def _find(self, cid):
        return next((r for r in self.records if r["id"] == cid), None)

    def set_status(self, cid, status):
        if status not in STATUSES:
            return 400, {"error": "bad_request", "field": "status"}
        with self.lock:
            r = self._find(cid)
            if not r:
                return 404, {"error": "not_found"}
            r["status"] = status
            r["status_history"] = list(r.get("status_history") or []) + [{"at": iso(datetime.now(timezone.utc)), "status": status}]
        self.service.invalidate()
        return 200, r

    def metoo(self, cid, device):
        with self.lock:
            r = self._find(cid)
            if not r:
                return 404, {"error": "not_found"}
            seen = self.metoo_devices.setdefault(r["target"]["id"], set())
            if device and device in seen:
                return 200, dict(r, already=True)
            seen.add(device or "anon")
            r["metoo"] = int(r.get("metoo") or 0) + 1
        self.service.invalidate()
        return 200, r

    def add(self, target_id):
        targets = demo_seed.load_targets()
        if target_id not in targets:
            return 404, {"error": "not_found", "message": "нет такой цели"}
        with self.lock:
            rec = demo_seed.add_demo_complaint(self.records, target_id, targets=targets)
        self.service.invalidate()
        return 201, rec


def make_handler(store: DemoStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BirgeHeatDev/1"

        def log_message(self, fmt, *args):  # тише в консоли
            pass

        def _json(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path.startswith(api.PREFIX + "/heat"):
                status, body = api.handle_get(u.path, parse_qs(u.query), service=store.service)
                return self._json(status, body)
            if u.path.startswith("/api/"):
                return self._json(503, {"error": "module_not_ready", "module": u.path})
            rel = u.path.lstrip("/") or "civic/heat/demo.html"
            path = (WEB / rel).resolve()
            if WEB not in path.parents and path != WEB or not path.is_file():
                self.send_error(404)
                return
            data = path.read_bytes()
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if path.suffix == ".geojson":
                ctype = "application/geo+json"
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/javascript")) else ""))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            u = urlparse(self.path)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "bad_request"})
            parts = u.path.split("/")
            if u.path == api.PREFIX + "/heat/demo/complaint":
                return self._json(*store.add(str(body.get("target_id") or "")))
            if len(parts) == 7 and u.path.startswith(api.PREFIX + "/complaints/"):
                cid, action = parts[5], parts[6]
                if action == "status":
                    return self._json(*store.set_status(cid, body.get("status")))
                if action == "metoo":
                    return self._json(*store.metoo(cid, str(body.get("device_id") or "")))
            return self._json(404, {"error": "not_found"})

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description="Демо-сервер тепловой карты R07 (synthetic)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8617)
    args = ap.parse_args(argv)
    store = DemoStore()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"R07 демо: http://{args.host}:{args.port}/civic/heat/demo.html  (Ctrl+C — стоп)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
