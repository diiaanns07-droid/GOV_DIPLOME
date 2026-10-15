"""R16 через настоящий шлюз v2 R01 (ui.web_server.CivicV2Gateway) с маршрутами together/* из поставки R16.

Пока R01 не взял поставку, маршруты добавляются только в память теста (monkeypatch) — тем же списком, что в
tests/civic/R16/stand.py и research/round-15-results/R16/R01_together_routes.patch. Если в сборке маршруты уже есть —
тест проверяет их как есть. Проверяем транспорт: адреса, {id}, лимиты шлюза, заголовок устройства, 404/405, что
маршрут сотрудника без сессии R02 не открыт.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
DEV = "d-gateway-test-0001"


def _stand():
    spec = importlib.util.spec_from_file_location("r16_stand", HERE / "stand.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    ws = pytest.importorskip("ui.web_server")
    stand = _stand()
    if not any(key.startswith("together.") for _m, _p, key in ws.V2_ROUTES):
        monkeypatch.setattr(ws, "V2_ROUTES", ws.V2_ROUTES + tuple((m, p, k) for m, p, k, _s in stand.ROUTES))
        handlers = dict(ws.V2_HANDLERS)
        for _m, _p, key, staff in stand.ROUTES:
            handlers[key] = ws.V2Handler("R16", stand.MODULE, "make_service", kind="service", staff=staff)
        monkeypatch.setattr(ws, "V2_HANDLERS", handlers)
        limits = dict(ws.V2_RATE_LIMITS)
        limits.update(stand.RATE_LIMITS)
        monkeypatch.setattr(ws, "V2_RATE_LIMITS", limits)
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    gw = ws.CivicV2Gateway(None, db_path=tmp_path / "civic.sqlite3", demo=True)
    # Тест транспорта: без связки R09 -> R07 (wire) и без сети.
    monkeypatch.setattr(gw, "wire", lambda: None)
    return gw


def ctx(device=DEV, ip="10.0.0.1"):
    return {"headers": {"x-birge-device": device} if device else {}, "client_ip": ip, "host_allowed": True,
            "is_same_origin": True}


def test_routes_ready_in_modules(gateway):
    modules = gateway.handle("GET", "/modules", "", None, ctx())["body"]["modules"]
    keys = [k for k in modules if k.startswith("together.")]
    assert len(keys) == 15
    assert all(modules[k]["status"] == "ready" and modules[k]["role"] == "R16" for k in keys), modules


def test_resident_flow_through_gateway(gateway):
    listing = gateway.handle("GET", "/together/initiatives", "", None, ctx())
    assert listing["status"] == 200 and len(listing["body"]["items"]) >= 5
    one = gateway.handle("GET", "/together/initiatives/i-demo-scene7", "", None, ctx())
    assert one["status"] == 200 and one["body"]["initiative"]["joined"] == 14
    joined = gateway.handle("POST", "/together/initiatives/i-demo-scene7/join", "", {}, ctx())
    assert joined["status"] == 200 and joined["body"]["joined"] == 15
    yard = gateway.handle("GET", "/together/yards/yard-1454082638", "", None, ctx())
    assert yard["status"] == 200 and yard["body"]["counts"]["members"] == 37
    updates = gateway.handle("GET", "/together/updates", "", None, ctx())
    assert updates["status"] == 200 and isinstance(updates["body"]["items"], list)


def test_ids_methods_and_unknown_paths(gateway):
    assert gateway.handle("GET", "/together/initiatives/..", "", None, ctx())["status"] == 404
    assert gateway.handle("DELETE", "/together/initiatives", "", None, ctx())["status"] == 405
    assert gateway.handle("GET", "/together/initiatives/i-demo-scene7/join", "", None, ctx())["status"] == 405
    assert gateway.handle("GET", "/together/nothing", "", None, ctx())["status"] == 404


def test_staff_routes_closed_without_session(gateway):
    # Без хранилища сессий R02 шлюз не пускает к маршрутам сотрудника (503), модуль — 401 на чтение очереди.
    for path in ("/together/initiatives/i-demo-scene7/support", "/together/initiatives/i-demo-scene7/moderate",
                 "/together/yards/yard-1454082638/moderate"):
        reply = gateway.handle("POST", path, "", {"action": "publish"}, ctx())
        assert reply["status"] in (401, 403, 503), (path, reply)
    queue = gateway.handle("GET", "/together/initiatives", "view=staff", None, ctx())
    assert queue["status"] == 401


def test_gateway_rate_limit_join_per_initiative(gateway):
    # ≤ 20 «Я приду» в сутки за одно дело с одного адреса (R15 S08): 21-й с нового устройства — 429.
    codes = [gateway.handle("POST", "/together/initiatives/i-demo-trees/join", "", {}, ctx(device=f"d-gw-dev-{n:04d}"))
             ["status"] for n in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429
