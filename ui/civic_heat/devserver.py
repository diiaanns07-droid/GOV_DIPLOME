"""Демо-сервер R07 — ТОЛЬКО для разработки, скриншотов и показа, пока R01 не подключил маршруты в ui/web_server.py.

    python -m ui.civic_heat.devserver            # http://127.0.0.1:8617/civic/heat/demo.html
    python -m ui.civic_heat.devserver --port 8620
    python -m ui.civic_heat.devserver --world    # раунд 15: мини-мир R07 (буран в Нуре) — для «Хроники города»

Отдаёт папку web/ и маршруты:
    GET  /api/civic/v2/heat, /heat/meta, /heat/target       — настоящий модуль ui/civic_heat (api.handle_get)
    GET  /api/civic/v2/heat/replay                           — «Хроника города» (раунд 15), тот же модуль
    POST /api/civic/v2/complaints/{id}/status {status}      — ПОДСТАВНОЙ двойник R09 (меняет демо-записи в памяти)
    POST /api/civic/v2/complaints/{id}/metoo {device_id}    — ПОДСТАВНОЙ двойник R09 (одно «Я тоже» с устройства)
    POST /api/civic/v2/complaints/{id}/verify {answer}      — ПОДСТАВНОЙ двойник R09 «Проблема решена?» (yes | no | cant;
                                                              только у исправленной жалобы) — для показа «проверено жителями»
    POST /api/civic/v2/heat/demo/complaint {target_id}      — добавить демо-жалобу (для показа пульса)
Все данные синтетические (demo: true) и живут только в памяти процесса.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import api, demo_seed, world, world_fixture
from .engine import iso
from .service import HeatService

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
STATUSES = ("new", "accepted", "in_progress", "fixed", "rejected")


class DemoStore:
    """Демо-записи в памяти + подставные операции R09 (status, metoo, verify)."""

    def __init__(self, now=None, world_db=None, world_kind="mini"):
        self.lock = threading.Lock()
        self.metoo_devices: dict[str, set] = {}
        if world_db:
            # Мини-мир R07 (world_fixture): буран в Нуре и отметка шкалы «Буран» — как засеял бы R01 из world_v1.json;
            # city1000 — 1 000 целей для замера плавности хроники
            w = world_fixture.city_world(1300, 5200) if world_kind == "city1000" else world_fixture.build_world()
            moment = now or datetime.now(timezone.utc)
            self.records = world_fixture.to_records(w, moment)
            world.seed_world(world_db, w, moment)
        else:
            self.records = demo_seed.demo_records(now=now)
        # стенд сам отвечает на статус и «Я тоже» примеров — действия с ними работают
        self.service = HeatService(source=lambda since: self.snapshot(), examples_actionable=True, db_path=world_db)

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

    def verify(self, cid, answer):
        # Ответ жителя после ремонта — запись resident_checks, которую читает engine.resident_answers (как у R09).
        if answer not in ("yes", "no", "cant"):
            return 400, {"error": "bad_request", "field": "answer"}
        with self.lock:
            r = self._find(cid)
            if not r:
                return 404, {"error": "not_found"}
            if r.get("status") != "fixed":
                return 409, {"error": "not_fixed"}
            r["resident_checks"] = list(r.get("resident_checks") or []) + [{"answer": answer, "at": iso(datetime.now(timezone.utc))}]
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
            if u.path == api.PREFIX + "/complaints/merged":
                # R09 на стенде нет: «Объединено с этим» (контракт R09) — пустой список, а не 503 в консоли
                return self._json(200, {"items": []})
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
                if action == "verify":
                    return self._json(*store.verify(cid, str(body.get("answer") or "")))
            return self._json(404, {"error": "not_found"})

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description="Демо-сервер тепловой карты R07 (synthetic)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8617)
    ap.add_argument("--world", nargs="?", const="mini", choices=("mini", "city1000"),
                    help="мини-мир R07 с бураном (раунд 15, «Хроника города»); city1000 — 1 000 целей для замера плавности")
    args = ap.parse_args(argv)
    world_db = None
    if args.world:
        world_db = str(Path(tempfile.gettempdir()) / f"birge-r07-world-{args.port}.sqlite3")
        Path(world_db).unlink(missing_ok=True)   # отметки — от этого запуска (время мира — от момента засева)
    store = DemoStore(world_db=world_db, world_kind=args.world or "mini")
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(store))
    print(f"R07 демо: http://{args.host}:{args.port}/civic/heat/demo.html  (Ctrl+C — стоп)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
