"""R13 «Встречи с акимом» через настоящий шлюз v2 R01 (CivicV2Gateway, ui/web_server.py).

Если в шлюзе сборки ещё нет маршрутов meetings.* (CONTRACT §7), тест копирует ui/web_server.py во временную папку,
накладывает research/round-15-results/R13/patches/r01_meetings_routes.patch и проверяет его. Когда R01 добавит
маршруты сам — тест идёт по его файлу как есть (и проверяет, что шлюз отвечает так же).
"""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest

import ui.civic_meetings as meetings_module
import ui.civic_qa as qa_module

REPO = Path(__file__).resolve().parents[4]
PATCH = REPO / "research" / "round-15-results" / "R13" / "patches" / "r01_meetings_routes.patch"


def load_web_server(tmp_root: Path):
    module = importlib.import_module("ui.web_server")
    if any(key == "meetings.list" for _m, _p, key in module.V2_ROUTES):
        return module
    (tmp_root / "ui").mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(module.__file__), tmp_root / "ui" / "web_server.py")
    subprocess.run(["git", "apply", str(PATCH)], cwd=tmp_root, check=True)
    spec = importlib.util.spec_from_file_location("r01_web_server_for_r13_meetings", tmp_root / "ui" / "web_server.py")
    patched = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patched)
    return patched


class Principal:
    username, role, is_staff = "editor.one", "editor", True

    def check_csrf(self, value):
        return value == "tok-1"


class FakeStore:
    """Сессия сотрудника R02 для шлюза: cookie «sid=ok» — вошёл; CSRF — заголовок x-csrf-token."""

    def resolve_principal(self, context):
        return Principal() if "sid=ok" in ((context or {}).get("headers") or {}).get("cookie", "") else None

    def require_staff(self, context, unsafe):
        principal = self.resolve_principal(context)
        if principal is None:
            return None, {"status": 401, "body": {"error": {"code": "unauthenticated", "message": "Войдите."}}}
        if unsafe and not principal.check_csrf(((context or {}).get("headers") or {}).get("x-csrf-token")):
            return None, {"status": 403, "body": {"error": {"code": "csrf_failed", "message": "CSRF."}}}
        return principal, None


class FakeStoreGateway:
    def __init__(self):
        self.store = FakeStore()

    def service(self, name):
        return self.store if name == "store" else None


@pytest.fixture
def gateway(tmp_path):
    web = load_web_server(tmp_path / "r01")
    gw = web.CivicV2Gateway(FakeStoreGateway(), modules={"ui.civic_meetings": meetings_module, "ui.civic_qa": qa_module},
                            db_path=str(tmp_path / "civic.sqlite3"), demo=False)
    return gw


def ctx(device=None, staff=False, ip="10.0.0.1"):
    headers = {}
    if device:
        headers["x-birge-device"] = device
    if staff:
        headers.update({"cookie": "sid=ok", "x-csrf-token": "tok-1"})
    return {"headers": headers, "host_allowed": True, "is_same_origin": True, "client_ip": ip}


MEETING = {"district": "nura", "title_ru": "Встреча акима района с жителями", "at": "2030-01-10T18:30:00+05:00",
           "place": {"kind": "area", "id": "yard-1424189376", "label_ru": "Двор: Eco Park"}}


def test_routes_are_ready_in_modules_list(gateway):
    modules = gateway.handle("GET", "/modules", "", None, ctx())["body"]["modules"]
    for key in ("meetings.list", "meetings.get", "meetings.updates", "meetings.create", "meetings.order",
                "meetings.result", "meetings.register", "meetings.question"):
        assert modules[key]["status"] == "ready" and modules[key]["role"] == "R13", key


def test_resident_and_staff_flow_through_gateway(gateway):
    # Проверяем транспорт шлюза (адреса, сессия, CSRF, лимиты); правила встреч — в test_r13_meetings.py.
    assert gateway.handle("GET", "/meetings", "", None, ctx())["status"] == 200
    denied = gateway.handle("POST", "/meetings", "", dict(MEETING), ctx())
    assert denied["status"] == 401                                     # шлюз: нет сессии
    no_csrf = ctx(staff=True)
    no_csrf["headers"].pop("x-csrf-token")
    assert gateway.handle("POST", "/meetings", "", dict(MEETING), no_csrf)["status"] == 403
    created = gateway.handle("POST", "/meetings", "", dict(MEETING, at="2026-12-10T18:30:00+05:00"), ctx(staff=True))
    assert created["status"] == 201, created
    mid = created["body"]["meeting"]["id"]
    reg = gateway.handle("POST", f"/meetings/{mid}/register", "", {}, ctx(device="dev-aaaaaaaa-0001"))
    assert reg["status"] == 200 and reg["body"]["registered"] == 1
    q = gateway.handle("POST", f"/meetings/{mid}/question", "", {"text": "Когда починят свет во дворе?"},
                       ctx(device="dev-aaaaaaaa-0001"))
    assert q["status"] == 201 and q["body"]["question"]["status"] == "pending"
    card = gateway.handle("GET", f"/meetings/{mid}", "", None, ctx(device="dev-aaaaaaaa-0001"))
    assert card["status"] == 200 and card["body"]["meeting"]["my_registration"] is True
    feed = gateway.handle("GET", "/meetings/updates", "since=2026-01-01T00:00:00Z", None, ctx(device="dev-aaaaaaaa-0001"))
    assert feed["status"] == 200 and isinstance(feed["body"]["items"], list)
    order = gateway.handle("POST", f"/meetings/{mid}/order", "", {"text_ru": "Поставить фонари", "service": "lighting",
                                                                  "due": "2026-12-30"}, ctx(staff=True))
    assert order["status"] == 201
    assert gateway.handle("POST", f"/meetings/{mid}/order", "", {}, ctx())["status"] == 401
    assert gateway.handle("GET", "/meetings/bad id", "", None, ctx())["status"] == 404


def test_register_rate_limit_per_meeting_and_address(gateway):
    created = gateway.handle("POST", "/meetings", "", dict(MEETING, at="2026-12-10T18:30:00+05:00"), ctx(staff=True))
    mid = created["body"]["meeting"]["id"]
    statuses = [gateway.handle("POST", f"/meetings/{mid}/register", "", {"going": True},
                               ctx(device=f"dev-{i:08d}-xyz", ip="10.9.9.9"))["status"] for i in range(21)]
    assert statuses[:20] == [200] * 20 and statuses[20] == 429
