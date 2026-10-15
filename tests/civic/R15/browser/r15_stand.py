"""R15 · стенд браузерной пробы раунда 15: настоящий ui.web_server + маршруты CONTRACT §7, которых ещё нет в шлюзе.

До сборки R01 (B1) новых маршрутов в шлюзе нет, а экраны ролей уже есть в их ветках. Чтобы проверить экраны в браузере
со строгой CSP шлюза, стенд в ПАМЯТИ своего процесса:
- дописывает в V2_ROUTES / V2_HANDLERS строки CONTRACT §7, которых нет в проверяемой сборке (есть — берёт как есть);
- отдаёт файлы экранов ролей (web/civic/<раздел>/*) и страницу-обвязку R15 (harness/) — тем же обработчиком статики
  и с той же CSP, что и сборка (csp_for_html: script-src 'self' + хэши встроенных скриптов).
Файлы R01 и ролей не меняются. В сборке B1+ стенд дописывает только то, чего там нет.

    python3 -B tests/civic/R15/browser/r15_stand.py --root <дерево сборки> --db <sqlite> --port <порт>
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

HARNESS = Path(__file__).resolve().parent / "harness"
SCREENS = ("together", "agencies", "meetings", "assistant", "works-calendar", "board", "notify")
MIME = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml; charset=utf-8", ".png": "image/png"}
# Тело запроса целиком — функциям R03 ask(body=…) и R04 moderate(body=…) (шлюз R01 добавит свой разбор параметров).
BODY_KEYS = {"r15.assistant.ask", "r15.moderate"}


def contract_routes(ws):
    """(метод, шаблон, ключ, обработчик) CONTRACT §7. Точные пути — раньше шаблонов с {id}."""
    def svc(role, module, staff=False):
        return ws.V2Handler(role, (module,), "make_service", kind="service", staff=staff)

    def raw(role, module, function, **kw):
        return ws.V2Handler(role, (module,), function, kind="raw", **kw)

    tg, ag, mt = "ui.civic_together", "ui.civic_agencies", "ui.civic_meetings"
    rows = [
        ("GET", ("together", "initiatives"), svc("R16", tg)),
        ("POST", ("together", "initiatives"), svc("R16", tg)),
        ("GET", ("together", "yards"), svc("R16", tg)),
        ("GET", ("together", "updates"), svc("R16", tg)),
        ("GET", ("together", "initiatives", "{id}"), svc("R16", tg)),
        ("POST", ("together", "initiatives", "{id}", "join"), svc("R16", tg)),
        ("POST", ("together", "initiatives", "{id}", "leave"), svc("R16", tg)),
        ("POST", ("together", "initiatives", "{id}", "support"), svc("R16", tg, staff=True)),
        ("POST", ("together", "initiatives", "{id}", "moderate"), svc("R16", tg, staff=True)),
        ("POST", ("together", "initiatives", "{id}", "report"), svc("R16", tg)),
        ("GET", ("together", "yards", "{id}"), svc("R16", tg)),
        ("POST", ("together", "yards", "{id}", "join"), svc("R16", tg)),
        ("POST", ("together", "yards", "{id}", "leave"), svc("R16", tg)),
        ("POST", ("together", "yards", "{id}", "captain"), svc("R16", tg)),
        ("POST", ("together", "yards", "{id}", "moderate"), svc("R16", tg, staff=True)),
        ("GET", ("agencies",), svc("R17", ag)),
        ("GET", ("agencies", "board"), svc("R17", ag)),       # чтение сотрудника: сессию проверяет сервис
        ("GET", ("agencies", "joint"), svc("R17", ag)),
        ("GET", ("agencies", "handoffs"), svc("R17", ag)),
        ("GET", ("incidents",), svc("R17", ag)),
        ("POST", ("incidents",), svc("R17", ag, staff=True)),
        ("GET", ("incidents", "updates"), svc("R17", ag)),
        ("GET", ("incidents", "{id}"), svc("R17", ag)),
        ("POST", ("incidents", "{id}", "task"), svc("R17", ag, staff=True)),
        ("POST", ("incidents", "{id}", "update"), svc("R17", ag, staff=True)),
        ("POST", ("incidents", "{id}", "close"), svc("R17", ag, staff=True)),
        ("GET", ("meetings",), svc("R13", mt)),
        ("POST", ("meetings",), svc("R13", mt, staff=True)),
        ("GET", ("meetings", "updates"), svc("R13", mt)),
        ("GET", ("meetings", "{id}"), svc("R13", mt)),
        ("POST", ("meetings", "{id}", "order"), svc("R13", mt, staff=True)),
        ("POST", ("meetings", "{id}", "result"), svc("R13", mt, staff=True)),
        ("POST", ("meetings", "{id}", "register"), svc("R13", mt)),
        ("POST", ("meetings", "{id}", "question"), svc("R13", mt)),
        ("GET", ("works-calendar",), raw("R12", "engine.civic_geo.api", "handle", strip_prefix=True, staff_view=True)),
        ("GET", ("works-conflicts",), raw("R12", "engine.civic_geo.api", "handle", strip_prefix=True, staff_view=True)),
        ("GET", ("akim", "board"), raw("R08", "ui.civic_akim.api", "handle_get", staff_view=True)),
        ("GET", ("akim", "week"), raw("R08", "ui.civic_akim.api", "handle_get", staff_view=True)),
        ("GET", ("heat", "replay"), raw("R07", "ui.civic_heat.api", "handle_get")),
        ("POST", ("assistant", "ask"), ws.V2Handler("R03", ("agent.civic_assistant.api",), "ask", staff=True)),
        ("POST", ("moderate",), ws.V2Handler("R04", ("ui.civic_ml_api",), "moderate")),
    ]
    out = []
    for method, pattern, handler in rows:
        key = "r15." + ".".join(p for p in pattern if p != "{id}") + ("." + method.lower() if method == "POST" else "")
        if pattern in (("assistant", "ask"),):
            key = "r15.assistant.ask"
        if pattern == ("moderate",):
            key = "r15.moderate"
        out.append((method, pattern, key, handler))
    return out


def extend_gateway(ws) -> list:
    have = {(m, tuple(p)) for m, p, _k in ws.V2_ROUTES}
    added = [(m, p, k, h) for m, p, k, h in contract_routes(ws) if (m, p) not in have]
    ws.V2_ROUTES = tuple(ws.V2_ROUTES) + tuple((m, p, k) for m, p, k, _h in added)
    for _m, _p, key, handler in added:
        ws.V2_HANDLERS[key] = handler
    original = ws.CivicV2Gateway.arguments

    def arguments(self, key, params, query, body):
        if key in BODY_KEYS:
            return {"body": body if isinstance(body, dict) else {}}
        return original(self, key, params, query, body)

    ws.CivicV2Gateway.arguments = arguments
    return [f"{m} {'/'.join(p)}" for m, p, _k, _h in added]


def extend_assets(ws, root: Path) -> list:
    added = []
    for section in SCREENS:
        folder = root / "web" / "civic" / section
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix in MIME:
                rel = path.relative_to(root / "web").as_posix()
                if "/" + rel not in ws.ASSETS:
                    ws.ASSETS["/" + rel] = (rel, MIME[path.suffix])
                    added.append(rel)
    for path in sorted(HARNESS.glob("*")):
        if path.suffix in MIME:
            ws.ASSETS["/r15/" + path.name] = (str(path), MIME[path.suffix])   # абсолютный путь: Path(web) / abs = abs
            added.append("r15/" + path.name)
    return added


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root))
    os.chdir(root)
    os.environ["CIVIC_DB_PATH"] = str(Path(args.db).resolve())   # соседи (R08, R03) читают ту же базу
    import ui.web_server as ws
    routes = extend_gateway(ws)
    files = extend_assets(ws, root)
    server = ws.create_server(project=root, port=args.port, civic_db=Path(args.db))
    print(f"R15 stand: +{len(routes)} маршрутов CONTRACT §7, +{len(files)} файлов экранов — http://127.0.0.1:{args.port}/",
          flush=True)
    for line in routes:
        print("  route", line, flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
