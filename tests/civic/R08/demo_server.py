"""Демо-сервер R08: страница «Картина дня» + её API без общей сборки R01.

    python tests/civic/R08/demo_server.py            # http://127.0.0.1:8508/civic/akim/
    python tests/civic/R08/demo_server.py --port 8600
    python tests/civic/R08/demo_server.py --kit-dir <папка>   # ui-kit/ и i18n/ из ветки R11, как в сборке:
        git archive origin/claude/r14-R11 web/civic/ui-kit web/civic/i18n | tar -x -C <папка>
        (папка — та, где лежат web/civic/ui-kit и web/civic/i18n, или сразу web/civic)

Отдаёт только файлы из web/civic/ (без листинга папок) и GET /api/civic/v2/akim/summary.
Данные: тепловая карта R07 (ui.civic_heat) с её демо-набором жалоб (все demo: true), объекты и
предложения — фикстуры ui/civic_akim/fixtures (demo). В общей сборке маршрут подключает R01.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ui.civic_akim.api import PREFIX, handle_get  # noqa: E402

WEB_CIVIC = (ROOT / "web" / "civic").resolve()
TYPES = {".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
         ".html": "text/html", ".woff2": "font/woff2", ".png": "image/png"}


class Handler(BaseHTTPRequestHandler):
    server_version = "BirgeAkimDemo/1"

    def log_message(self, fmt, *args):  # тише в консоли
        if self.server.verbose:
            super().log_message(fmt, *args)

    def send(self, status: int, data: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path
        if path in ("/", "/civic/akim"):
            self.send_response(302)
            self.send_header("Location", "/civic/akim/" + (("?" + url.query) if url.query else ""))
            self.end_headers()
            return
        if path.startswith(PREFIX + "/"):
            status, body = handle_get(path, parse_qs(url.query))
            self.send(status, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if path.startswith("/civic/"):
            rel = path[len("/civic/"):]
            if rel.endswith("/") or rel == "":
                rel += "index.html"
            base = WEB_CIVIC
            if self.server.kit_dir and rel.split("/", 1)[0] in ("ui-kit", "i18n"):
                base = self.server.kit_dir
            target = (base / rel).resolve()
            # Только файлы внутри web/civic (или папки ui-kit R11), никаких выходов наверх через «..».
            if base in target.parents and target.is_file():
                ctype = TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"):
                    ctype += "; charset=utf-8"
                self.send(200, target.read_bytes(), ctype)
                return
        self.send(404, "Не найдено".encode("utf-8"), "text/plain; charset=utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Демо-сервер «Картины дня» (R08)")
    ap.add_argument("--port", type=int, default=8508)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--kit-dir", help="папка с ui-kit/ и i18n/ R11 (или с web/civic/ внутри) — как в общей сборке")
    args = ap.parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.verbose = args.verbose
    httpd.kit_dir = None
    if args.kit_dir:
        kit = Path(args.kit_dir).resolve()
        if (kit / "web" / "civic").is_dir():
            kit = kit / "web" / "civic"
        if not (kit / "i18n" / "ru.json").is_file():
            ap.error(f"в {kit} нет i18n/ru.json")
        httpd.kit_dir = kit
        print(f"ui-kit и i18n: {kit}", flush=True)
    print(f"Картина дня: http://{args.host}:{args.port}/civic/akim/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
