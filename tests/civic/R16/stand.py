"""Стенд R16: настоящее приложение Birge (ui/web_server.py) + маршруты и файлы «Бірге: жители вместе» — только в памяти.

Пока R01 не поставил маршруты together/* и файлы web/civic/together/ в сборку, этот запуск добавляет их в шлюз
так же, как предлагает INTEGRATION.txt (тот же список ROUTES ниже), и вставляет теги script/link в отдаваемую
index.html. Файлы R01 на диске не меняются.

    mkdir -p /tmp/birge && python3 -B -m ui.civic_store --db /tmp/birge/demo.sqlite3 init   # и засев по COMMON.txt
    CIVIC_DB_PATH=/tmp/birge/demo.sqlite3 CIVIC_DEMO=1 python3 -B tests/civic/R16/stand.py --port 8655

Если часть маршрутов уже есть (R01 взял поставку частично) — стенд добавляет только недостающие.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui import web_server as ws  # noqa: E402

MODULE = ("ui.civic_together",)
# (метод, путь после /api/civic/v2, ключ, сотрудник на уровне шлюза). Точные пути — раньше шаблонов с {id}.
ROUTES = (
    ("GET", ("together", "initiatives"), "together.initiatives.list", False),
    ("POST", ("together", "initiatives"), "together.initiatives.create", False),
    ("GET", ("together", "initiatives", "{id}"), "together.initiatives.get", False),
    ("POST", ("together", "initiatives", "{id}", "join"), "together.initiatives.join", False),
    ("POST", ("together", "initiatives", "{id}", "leave"), "together.initiatives.leave", False),
    ("POST", ("together", "initiatives", "{id}", "support"), "together.initiatives.support", True),
    ("POST", ("together", "initiatives", "{id}", "moderate"), "together.initiatives.moderate", True),
    # Отчёт — автор (житель) или сотрудник: шлюз сотрудника не требует, модуль проверяет сам.
    ("POST", ("together", "initiatives", "{id}", "report"), "together.initiatives.report", False),
    ("GET", ("together", "yards"), "together.yards.list", False),
    ("GET", ("together", "yards", "{id}"), "together.yards.get", False),
    ("POST", ("together", "yards", "{id}", "join"), "together.yards.join", False),
    ("POST", ("together", "yards", "{id}", "leave"), "together.yards.leave", False),
    ("POST", ("together", "yards", "{id}", "captain"), "together.yards.captain", False),
    ("POST", ("together", "yards", "{id}", "moderate"), "together.yards.moderate", True),
    ("GET", ("together", "updates"), "together.updates", False),
)
# Лимиты шлюза по адресу клиента (как R13/R06, R15 S08); модуль держит свои лимиты на устройство.
RATE_LIMITS = {
    "together.initiatives.create": ((60, 3, False), (3600, 10, False), (86400, 20, False)),
    "together.initiatives.join": ((60, 30, False), (86400, 20, True)),
    "together.initiatives.leave": ((60, 30, False),),
    "together.initiatives.report": ((60, 10, False), (3600, 30, False)),
    "together.yards.join": ((60, 10, False), (86400, 50, False)),
    "together.yards.leave": ((60, 10, False),),
    "together.yards.captain": ((3600, 10, False),),
}
ASSETS = ("together/together.js", "together/together-text.js", "together/together.css")
TAGS_HEAD = b'    <link rel="stylesheet" href="/civic/together/together.css" />\n'
TAGS_BODY = (b'    <script defer src="/civic/together/together-text.js"></script>\n'
             b'    <script defer src="/civic/together/together.js"></script>\n')


def install() -> bool:
    """Добавить недостающие маршруты, лимиты, файлы и теги. True — что-то добавили.

    По одному: в сборке R01 раунда 15 уже 12 маршрутов together/* (без списка дворов и «старшего по двору»),
    но ещё нет файлов web/civic/together/ — стенд добавляет только то, чего нет, и не трогает то, что есть."""
    added = False
    have = {key for _m, _p, key in ws.V2_ROUTES}
    new_routes = tuple((method, pattern, key) for method, pattern, key, _staff in ROUTES if key not in have)
    if new_routes:
        ws.V2_ROUTES = ws.V2_ROUTES + new_routes
        added = True
    for _method, _pattern, key, staff in ROUTES:
        if key not in ws.V2_HANDLERS:
            ws.V2_HANDLERS[key] = ws.V2Handler("R16", MODULE, "make_service", kind="service", staff=staff)
            added = True
    for key, limits in RATE_LIMITS.items():
        ws.V2_RATE_LIMITS.setdefault(key, limits)
    for asset in ASSETS:
        if "/civic/" + asset not in ws.ASSETS:
            ws.ASSETS["/civic/" + asset] = ("civic/" + asset, ws.CIVIC_MIME.get(Path(asset).suffix, "text/plain; charset=utf-8"))
            added = True
    original = ws.Handler.send_bytes

    def send_bytes(self, status, data, content_type):
        if content_type.startswith("text/html") and b"/civic/shell/birge.js" in data and b"together.js" not in data:
            data = data.replace(b"  </head>", TAGS_HEAD + b"  </head>", 1).replace(b"  </body>", TAGS_BODY + b"  </body>", 1)
        return original(self, status, data, content_type)

    ws.Handler.send_bytes = send_bytes
    return added


if __name__ == "__main__":
    print("R16 stand: " + ("недостающие маршруты/файлы together добавлены в памяти" if install() else "всё уже в сборке"), flush=True)
    ws.main()
