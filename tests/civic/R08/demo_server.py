"""Демо-сервер R08: страница «Картина дня» + её API без общей сборки R01.

    python tests/civic/R08/demo_server.py            # http://127.0.0.1:8508/civic/akim/
    python tests/civic/R08/demo_server.py --port 8600
    python tests/civic/R08/demo_server.py --kit-dir <папка>   # ui-kit/ и i18n/ из ветки R11, как в сборке:
        git archive origin/claude/r14-R11 web/civic/ui-kit web/civic/i18n | tar -x -C <папка>
        (папка — та, где лежат web/civic/ui-kit и web/civic/i18n, или сразу web/civic)
    python tests/civic/R08/demo_server.py --r06-db <база.sqlite>   # объекты и предложения из R06
        (нужна ветка R06 с ui/civic_store/v2.py; база: python -m ui.civic_store --db <база> init && … seed-r14-demo)

    python tests/civic/R08/demo_server.py --wave2-demo   # + уточнения и проверка жителями в демо-жалобах (синтетика)

Отдаёт только файлы из web/civic/ (без листинга папок) и API R08: GET /akim/summary, GET/PUT /akim/routing,
POST /akim/decisions/<id>, GET /nearby, GET/POST /nearby/subscriptions, GET /nearby/updates. Стенд — локальный: все запросы считаются запросами сотрудника (--resident — наоборот),
GET /api/civic/v1/session отдаёт учебный CSRF-токен. Выбор акима и правки служб пишутся во временную папку
(--state-dir), а не в .runtime проекта.
Данные: тепловая карта R07 (ui.civic_heat) с её демо-набором жалоб (все demo: true), объекты и
предложения — фикстуры ui/civic_akim/fixtures (demo). В общей сборке маршрут подключает R01.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ui.civic_akim import decisions as akim_decisions, nearby as akim_nearby, routing as akim_routing  # noqa: E402
from ui.civic_akim.api import PREFIX, handle_get, handle_post, handle_put  # noqa: E402

STAND_CSRF = "r08-stand-csrf"

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
        if path == "/api/civic/v1/session":
            body = {"authenticated": self.server.staff, "csrf_token": STAND_CSRF if self.server.staff else None}
            self.send(200, json.dumps(body).encode("utf-8"), "application/json; charset=utf-8")
            return
        self.send(404, "Не найдено".encode("utf-8"), "text/plain; charset=utf-8")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > 64 * 1024:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"null")
        except ValueError:
            return None

    def _write(self, fn):
        url = urlsplit(self.path)
        staff = self.server.staff and self.headers.get("X-CSRF-Token") == STAND_CSRF
        status, body = fn(url.path, self._body(), staff=staff, actor="stand")
        self.send(status, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_POST(self):
        self._write(handle_post)

    def do_PUT(self):
        self._write(handle_put)


def stand_warnings(kit_dir) -> list[str]:
    """Чего не хватает стенду в этой ветке (R10 B-005): без R07 нет жалоб, без словаря R11 — ключи на экране."""
    out = []
    try:
        import ui.civic_heat  # noqa: F401
    except ImportError:
        out.append("нет модуля тепловой карты R07 (ui/civic_heat) — страница покажет «Обращения пока не подключены», "
                   "ui_check.cjs даст FAIL. Взять: git fetch origin claude/upbeat-knuth-i0rqaa && "
                   "git archive origin/claude/upbeat-knuth-i0rqaa ui/civic_heat | tar -x")
    ru = (kit_dir or WEB_CIVIC) / "i18n" / "ru.json"
    try:
        has_keys = "akim.updated" in json.loads(ru.read_text("utf-8"))
    except (OSError, ValueError):
        has_keys = False
    if not has_keys:
        out.append(f"в {ru} нет ключей akim.* — нужен словарь R11 (claude/r14-R11): --kit-dir <папка>, см. начало файла")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Демо-сервер «Картины дня» (R08)")
    ap.add_argument("--port", type=int, default=8508)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--r06-db", help="база R06 (ui.civic_store): связать v2 с ней, как это делает шлюз R01")
    ap.add_argument("--kit-dir", help="папка с ui-kit/ и i18n/ R11 (или с web/civic/ внутри) — как в общей сборке")
    ap.add_argument("--wave2-demo", action="store_true",
                    help="дописать в демо-жалобы R07 уточнения и проверку жителями (синтетика, tests/civic/R08/wave2_demo.py)")
    ap.add_argument("--resident", action="store_true", help="запросы — как от жителя (POST/PUT ответят 403)")
    ap.add_argument("--state-dir", help="куда писать выбор акима и правки служб (по умолчанию — временная папка)")
    args = ap.parse_args(argv)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.verbose = args.verbose
    httpd.staff = not args.resident
    httpd.kit_dir = None
    state = Path(args.state_dir or tempfile.mkdtemp(prefix="r08-stand-"))
    akim_decisions.STORE_PATH = state / "decisions.json"
    akim_routing.OVERRIDE_PATH = state / "routing.json"
    akim_nearby.SUBS_PATH = state / "subscriptions.json"
    print(f"Выбор акима и правки служб: {state}", flush=True)
    if args.wave2_demo:
        import importlib
        akim_summary = importlib.import_module("ui.civic_akim.summary")  # имя summary в пакете — функция
        from wave2_demo import wrap
        svc = akim_summary.AkimService()
        if svc._records is not None:
            svc._records = wrap(svc._records)  # источник тот же (R07 demo), поля волны 2 — синтетика стенда
        akim_summary._default = svc
        print("Волна 2: уточнения и проверка жителями дописаны в демо-жалобы (синтетика стенда)", flush=True)
    if args.r06_db:
        from ui.civic_store import CivicService, v2  # ветка R06, раунд 14
        v2.bind(CivicService(args.r06_db))
        print(f"R06: {args.r06_db}", flush=True)
    if args.kit_dir:
        kit = Path(args.kit_dir).resolve()
        if (kit / "web" / "civic").is_dir():
            kit = kit / "web" / "civic"
        if not (kit / "i18n" / "ru.json").is_file():
            ap.error(f"в {kit} нет i18n/ru.json")
        httpd.kit_dir = kit
        print(f"ui-kit и i18n: {kit}", flush=True)
    for warning in stand_warnings(httpd.kit_dir):
        print("ВНИМАНИЕ: " + warning, flush=True)
    print(f"Картина дня: http://{args.host}:{args.port}/civic/akim/", flush=True)
    print(f"Службы: http://{args.host}:{args.port}/civic/akim/services.html · Рядом: http://{args.host}:{args.port}/civic/nearby/",
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
