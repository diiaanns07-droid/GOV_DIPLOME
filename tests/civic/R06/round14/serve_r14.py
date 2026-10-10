"""Стенд R06 раунда 14: настоящий HTTP поверх ui.civic_store (v1 + v2) и статика web/.

    python3 tests/civic/R06/round14/serve_r14.py --port 8616 [--kit-dir DIR] [--age-days 16]

- База — временный файл вне репозитория; при запуске: seed-demo + seed-r14-demo (всё synthetic/demo).
- --age-days N: демо-данные засеваются «N дней назад» (часы сдвинуты), чтобы на стенде было видно
  «давно не обновлялось». Сам сервер работает по настоящим часам.
- --package FILE: демо-срез для seed-demo вместо встроенного demo_package.json — например
  data/civic/astana/demo_synthetic.json, как засевает сборка R01 при CIVIC_DEMO=1.
- --kit-dir: папка, в которой лежат web/civic/ui-kit и web/civic/i18n другой ветки (например, свежая
  поставка R11, выгруженная git archive). Без неё берутся файлы из этого рабочего дерева.
- Создаётся сотрудник akimat-demo со случайным паролем; логин и пароль печатаются в stdout одной
  строкой JSON (для браузерной проверки роли «акимат»). В Git не попадает ничего.

Это не замена ui/web_server.py (R01): только стенд для проверки карточек R06 и скриншотов.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import sys
import tempfile
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from ui.civic_store import CivicService, CivicV2  # noqa: E402
from ui.civic_store.cli import DEMO_PACKAGE, seed_demo  # noqa: E402
from ui.civic_store.demo_r14 import seed_r14_demo  # noqa: E402
from ui.civic_store.importer import load_package  # noqa: E402

MIME = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml; charset=utf-8",
        ".html": "text/html; charset=utf-8", ".woff2": "font/woff2", ".png": "image/png"}


def build(db_path: Path, age_days: int, package: Path | None = None):
    shift = timedelta(days=age_days)
    seeding = CivicService(db_path, clock=lambda: datetime.now(timezone.utc) - shift)
    seed_demo(seeding, load_package(package or DEMO_PACKAGE))
    seed_r14_demo(seeding)
    service = CivicService(db_path)
    password = "Demo-" + secrets.token_urlsafe(12)
    service.accounts.create_user("akimat-demo", password, display_name="Сотрудник акимата (демо)",
                                 public_label="Акимат (демо)")
    return service, CivicV2(service), password


def make_handler(service, v2, web_root: Path, kit_root: Path | None, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # тихий стенд
            pass

        def _context(self):
            origin = self.headers.get("Origin")
            same = None if origin is None else origin in {f"http://{h}" for h in allowed_hosts}
            return {"headers": {k: v for k, v in self.headers.items()}, "client_ip": self.client_address[0],
                    "host_allowed": self.headers.get("Host") in allowed_hosts, "is_same_origin": same,
                    "is_https": False}

        def _api(self, method):
            parts = urlsplit(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            result = (v2.handle(method, parts.path, parts.query, body, self._context())
                      or service.handle(method, parts.path, parts.query, body, self._context()))
            if result is None:
                self._send(404, b'{"ok":false,"error":{"code":"not_found","message":"no route"}}',
                           "application/json; charset=utf-8")
                return
            payload = json.dumps(result["body"], ensure_ascii=False).encode("utf-8")
            self.send_response(result["status"])
            for key, value in result["headers"].items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send(self, status, data: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _static(self):
            path = urlsplit(self.path).path
            rel = path.lstrip("/")
            base = web_root
            if kit_root and (rel.startswith("civic/ui-kit/") or rel.startswith("civic/i18n/")):
                base = kit_root
            target = (base / rel).resolve()
            if not target.is_relative_to(base.resolve()) or not target.is_file():
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            ctype = MIME.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self._send(200, target.read_bytes(), ctype)

        def do_GET(self):
            if self.path.startswith("/api/"):
                self._api("GET")
            else:
                self._static()

        def do_POST(self):
            self._api("POST")

        def do_PUT(self):
            self._api("PUT")

        def do_DELETE(self):
            self._api("DELETE")

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8616)
    parser.add_argument("--kit-dir", help="корень с web/civic/ui-kit и web/civic/i18n (другая ветка)")
    parser.add_argument("--age-days", type=int, default=0)
    parser.add_argument("--package", help="демо-срез для seed-demo (по умолчанию встроенный demo_package.json)")
    args = parser.parse_args(argv)
    tmp = Path(tempfile.mkdtemp(prefix="r06-stand-"))
    service, v2, password = build(tmp / "civic.sqlite3", args.age_days, Path(args.package) if args.package else None)
    kit = Path(args.kit_dir).resolve() / "web" if args.kit_dir else None
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(service, v2, REPO / "web", kit, args.port))
    print(json.dumps({"url": f"http://127.0.0.1:{args.port}/civic/proposals/demo.html", "username": "akimat-demo",
                      "password": password, "db": str(tmp / "civic.sqlite3")}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
