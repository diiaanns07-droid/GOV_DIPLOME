"""R06 раунд 14 через шлюз v2 R01 (CivicV2Gateway в ui/web_server.py).

Шлюз R01 ещё не в общей сборке. Тест берёт его так:
  - R06_R01_WEB_SERVER=<путь к web_server.py из ветки R01> (git show origin/claude/sharp-dijkstra-0t87gl:ui/web_server.py);
  - иначе ui.web_server из рабочего дерева, если в нём уже есть CivicV2Gateway;
  - иначе тест пропускается (SKIP с причиной) — это не PASS.
Функции R06 вызываются настоящим маршрутизатором R01: имена, разбор параметров, проверка сессии, коды ошибок.
"""

import importlib
import importlib.util
import json
import os

import pytest

from ui.civic_store import v2 as v2mod
from r06r14_helpers import NURA_POINT, Staff, context, device


def load_r01():
    path = os.environ.get("R06_R01_WEB_SERVER")
    if path:
        spec = importlib.util.spec_from_file_location("r01_web_server_for_r06", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    module = importlib.import_module("ui.web_server")
    return module if hasattr(module, "CivicV2Gateway") else None


R01 = load_r01()
pytestmark = pytest.mark.skipif(R01 is None, reason="шлюз v2 R01 не найден: задайте R06_R01_WEB_SERVER")


class StoreOnly:
    """Минимальный store_gateway: шлюзу R01 нужен только service('store') для require_staff."""

    def __init__(self, service):
        self._service = service

    def service(self, name):
        return self._service if name == "store" else None


@pytest.fixture
def gw(stack):
    svc, _ = stack
    v2mod.bind(svc)
    yield R01.CivicV2Gateway(StoreOnly(svc))
    v2mod._BOUND = None


def body(result):
    json.dumps(result["body"], allow_nan=False)
    return result["body"]


def test_all_r06_routes_are_ready(gw):
    modules = body(gw.handle("GET", "/modules", "", None, context()))["modules"]
    for key in ("proposals.list", "proposals.create", "proposals.vote", "objects.list", "objects.stage"):
        assert modules[key]["status"] == "ready", (key, modules[key])


def test_create_vote_list_through_gateway(gw, stack):
    svc, v2 = stack
    staff = Staff(svc, v2)
    payload = {"kind": "playground", "geometry": {"type": "Point", "coordinates": NURA_POINT}, "title_ru": "Площадка"}
    anon = gw.handle("POST", "/proposals", "", payload, context())
    assert anon["status"] == 401
    created = gw.handle("POST", "/proposals", "", payload, staff.ctx())
    assert created["status"] == 201, created
    pid = body(created)["item"]["id"]
    first = gw.handle("POST", f"/proposals/{pid}/vote", "", {"value": 1, "device_id": device(1)}, context())
    assert first["status"] == 200 and body(first)["item"]["votes_up"] == 1
    again = gw.handle("POST", f"/proposals/{pid}/vote", "", {"value": 1, "device_id": device(1)}, context())
    assert body(again)["changed"] is False and body(again)["item"]["votes_up"] == 1
    bad = gw.handle("POST", f"/proposals/{pid}/vote", "", {"value": 5, "device_id": device(1)}, context())
    assert bad["status"] == 400
    listed = body(gw.handle("GET", "/proposals", "bbox=71.3,51.1,71.4,51.2", None, context()))
    assert [i["id"] for i in listed["items"]] == [pid]
    missing = gw.handle("POST", "/proposals/p-000000000000/vote", "", {"value": 1, "device_id": device(2)}, context())
    assert missing["status"] == 404


def test_stage_through_gateway(gw, stack):
    svc, v2 = stack
    staff = Staff(svc, v2)
    item = staff.create_object()
    put = gw.handle("PUT", f"/objects/{item['id']}/stage", "",
                    {"expected_revision": 0, "stage": "procurement", "planned_end": "2026-10-01",
                     "forecast_end": "2026-10-24"}, staff.ctx())
    assert put["status"] == 200, put
    assert body(put)["item"]["delay_days"] == 23
    stale = gw.handle("PUT", f"/objects/{item['id']}/stage", "", {"expected_revision": 0, "stage": "design"}, staff.ctx())
    assert stale["status"] == 409 and body(stale)["error"] == "stale_revision"
    invalid = gw.handle("PUT", f"/objects/{item['id']}/stage", "", {"expected_revision": 1, "stage": "x"}, staff.ctx())
    assert invalid["status"] == 422
    anon = gw.handle("PUT", f"/objects/{item['id']}/stage", "", {"expected_revision": 1, "stage": "design"}, context())
    assert anon["status"] == 401
    objects = body(gw.handle("GET", "/objects", "", None, context()))["items"]
    assert objects[0]["stage"] == "procurement" and objects[0]["late"] is True


def test_not_bound_gives_503(gw):
    v2mod._BOUND = None
    result = gw.handle("GET", "/proposals", "", None, context())
    assert result["status"] == 503 and body(result)["error"] == "module_not_ready"
