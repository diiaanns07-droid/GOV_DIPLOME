"""R01 раунд 14: каркас API v2 (/api/civic/v2/*, CONTRACT §7) в ui/web_server.py.

Что проверяем:
- пока модуль роли не сдан, каждый маршрут отвечает 503 {"error": "module_not_ready", "module", "role"},
  а приложение и API v1 работают дальше;
- сданная функция получает уже проверенные параметры, её ответ уходит без обёртки;
- неверный ввод (координаты вне Астаны, неизвестная категория, голос 2) -> 400 до вызова модуля;
- ошибки модуля превращаются в понятные ответы, сервер не падает;
- маршруты сотрудника требуют сессию R02 (как staff-маршруты v1);
- настоящий HTTP: Host/Origin, PUT только в v2, 404/405, размер тела.
"""

from __future__ import annotations

import http.client
import json
import threading
import types

import pytest

from ui import web_server
from ui.web_server import CivicGateway, CivicV2Gateway, V2_HANDLERS, V2_ROUTES

CTX = {"headers": {}, "cookies": {}, "client_ip": "127.0.0.1", "host_allowed": True,
       "is_same_origin": True, "is_https": False, "host": "127.0.0.1"}
NURA = [71.4148, 51.1131]  # точка в районе Нура


def fake_module(**functions):
    return types.SimpleNamespace(**functions)


def gw(modules=None, store_gateway=None):
    return CivicV2Gateway(store_gateway=store_gateway, modules=modules or {})


def call(gateway, method, path, query="", body=None, context=CTX):
    reply = gateway.handle(method, path, query, body, context)
    return reply["status"], reply["body"]


# --- модули ещё не сданы -------------------------------------------------------

ROUTE_SAMPLES = [
    ("POST", "/classify", "", {"text": "яма"}),
    ("POST", "/similar", "", {"text": "яма"}),
    ("GET", "/targets", "lon=71.41&lat=51.11", None),
    ("POST", "/complaints", "", {"text": "яма"}),
    ("GET", "/complaints", "", None),
    ("POST", "/complaints/c-1/metoo", "", {"device_id": "device-123"}),
    ("POST", "/complaints/c-1/status", "", {"status": "fixed"}),
    ("GET", "/heat", "", None),
    ("GET", "/akim/summary", "", None),
    ("GET", "/proposals", "", None),
    ("POST", "/proposals", "", {"kind": "park"}),
    ("POST", "/proposals/p-1/vote", "", {"value": 1, "device_id": "device-123"}),
    ("GET", "/objects", "", None),
    ("PUT", "/objects/o-1/stage", "", {"stage": "design"}),
]


def test_every_contract_route_is_in_the_table():
    keys = {key for _m, _p, key in V2_ROUTES} - {"modules"}
    assert keys == set(V2_HANDLERS)
    assert len(ROUTE_SAMPLES) == len(keys)


@pytest.mark.parametrize("method,path,query,body", ROUTE_SAMPLES)
def test_missing_module_answers_503_with_module_name(method, path, query, body):
    status, data = call(gw(), method, path, query, body)
    assert status == 503
    assert data["error"] == "module_not_ready"
    assert data["module"] and data["role"] in {"R04", "R06", "R07", "R08", "R09", "R12"}
    assert "Traceback" not in json.dumps(data, ensure_ascii=False)


def test_real_import_of_absent_packages_is_not_ready():
    # Настоящий importlib: пакетов ролей раунда 14 в сборке I0 ещё нет (или они уже есть — тогда ready).
    gateway = CivicV2Gateway()
    for key, state in gateway.modules().items():
        assert state["status"] in {"ready", "module_not_ready"}, (key, state)


def test_modules_route_lists_each_route_with_role():
    status, data = call(gw({"ui.civic_heat": fake_module(heat=lambda **kw: {"items": []})}), "GET", "/modules")
    assert status == 200
    assert data["modules"]["heat"] == {"role": "R07", "module": "ui.civic_heat", "function": "heat",
                                       "status": "ready"}
    assert data["modules"]["classify"]["status"] == "module_not_ready"


def test_module_without_the_function_is_not_ready():
    status, data = call(gw({"ui.civic_ml_api": fake_module(other=lambda: None)}), "POST", "/classify", "",
                        {"text": "яма"})
    assert status == 503 and data["module"] == "ui.civic_ml_api"


def test_broken_module_is_reported_and_app_keeps_working(monkeypatch):
    def broken_import(name):
        if name == "ui.civic_heat":
            raise ImportError("broken dependency inside the module")
        raise ModuleNotFoundError(f"No module named '{name}'", name=name)

    gateway = CivicV2Gateway()
    monkeypatch.setattr(web_server.importlib, "import_module", broken_import)
    status, data = call(gateway, "GET", "/heat")
    assert status == 503 and data["error"] == "module_failed"
    status, data = call(gateway, "POST", "/classify", "", {"text": "яма"})
    assert status == 503 and data["error"] == "module_not_ready"


# --- сданная функция получает проверенные параметры ----------------------------

def test_classify_passes_text_and_returns_plain_json():
    seen = {}

    def classify(text):
        seen["text"] = text
        return {"category": "roads", "score": 0.91, "needs_review": False, "model_version": "test",
                "top3": [{"category": "roads", "score": 0.91}]}

    status, data = call(gw({"ui.civic_ml_api": fake_module(classify=classify)}), "POST", "/classify", "",
                        {"text": "Аялдамада жарық жоқ, остановка темно"})
    assert status == 200 and data["category"] == "roads" and "ok" not in data
    assert seen["text"] == "Аялдамада жарық жоқ, остановка темно"


def test_similar_point_and_days_are_parsed():
    seen = {}
    module = fake_module(similar=lambda text, point=None, days=None: seen.update(text=text, point=point, days=days)
                         or {"matches": []})
    status, _ = call(gw({"ui.civic_ml_api": module}), "POST", "/similar", "", {"text": "яма", "point": NURA, "days": 30})
    assert status == 200 and seen == {"text": "яма", "point": NURA, "days": 30}


def test_targets_query_is_parsed_to_numbers():
    seen = {}
    module = fake_module(targets=lambda lon, lat, category=None: seen.update(lon=lon, lat=lat, category=category)
                         or {"candidates": []})
    status, data = call(gw({"engine.civic_geo": module}), "GET", "/targets", "lon=71.4148&lat=51.1131&category=transport")
    assert status == 200 and data == {"candidates": []}
    assert seen == {"lon": 71.4148, "lat": 51.1131, "category": "transport"}


def test_heat_filters_are_parsed():
    seen = {}

    def heat(bbox=None, days=None, category=None, zoom=None):
        seen.update(bbox=bbox, days=days, category=category, zoom=zoom)
        return {"generated_at": "x", "items": []}

    module = fake_module(heat=heat)
    status, _ = call(gw({"ui.civic_heat": module}), "GET", "/heat",
                     "bbox=71.3,51.0,71.6,51.2&days=30&category=roads&zoom=14.5")
    assert status == 200
    assert seen == {"bbox": (71.3, 51.0, 71.6, 51.2), "days": 30, "category": "roads", "zoom": 14.5}


def test_context_and_principal_only_for_functions_that_declare_them():
    seen = {}

    def create_complaint(body, context=None):
        seen["body"], seen["context"] = body, context
        return 201, {"id": "c-1", "status": "new"}

    status, data = call(gw({"ui.civic_feedback.v2": fake_module(create_complaint=create_complaint)}),
                        "POST", "/complaints", "", {"text": "Яма у остановки", "point": NURA, "category": "roads"})
    assert status == 201 and data["id"] == "c-1"
    assert seen["body"]["text"] == "Яма у остановки" and seen["context"] is CTX


def test_function_with_var_kwargs_also_gets_context_and_principal():
    seen = {}
    status, _ = call(gw({"ui.civic_akim": fake_module(summary=lambda **kw: seen.update(kw) or {"topics": []})}),
                     "GET", "/akim/summary", "date=2026-10-11&district=nura")
    assert status == 200 and seen["date"] == "2026-10-11" and seen["district"] == "nura"
    assert seen["context"] is CTX and seen["principal"] is None


def test_package_level_function_is_found_when_v2_submodule_is_absent():
    module = fake_module(list_complaints=lambda bbox=None, since=None: {"items": [], "bbox": bbox})
    status, data = call(gw({"ui.civic_feedback": module}), "GET", "/complaints", "bbox=71.3,51.0,71.6,51.2")
    assert status == 200 and tuple(data["bbox"]) == (71.3, 51.0, 71.6, 51.2)


def test_vote_body_is_checked_and_passed():
    seen = {}
    module = fake_module(vote_proposal=lambda proposal_id, value, device_id: seen.update(
        id=proposal_id, value=value, device=device_id) or {"votes_up": 1, "votes_down": 0})
    gateway = gw({"ui.civic_store.v2": module})
    status, _ = call(gateway, "POST", "/proposals/p-7/vote", "", {"value": -1, "device_id": "device-abc-123"})
    assert status == 200 and seen == {"id": "p-7", "value": -1, "device": "device-abc-123"}


# --- неверный ввод: 400 до вызова модуля ----------------------------------------

BAD_INPUT = [
    ("POST", "/classify", "", {"text": "   "}, "text"),
    ("POST", "/classify", "", {"text": "я" * 5001}, "text"),
    ("POST", "/similar", "", {"text": "яма", "point": [0, 0]}, "point"),
    ("POST", "/similar", "", {"text": "яма", "days": 0}, "days"),
    ("GET", "/targets", "lon=71.4", None, "lon"),
    ("GET", "/targets", "lon=37.6&lat=55.7", None, "lon"),  # Москва — вне Астаны
    ("GET", "/targets", "lon=nan&lat=51.1", None, "lon"),
    ("GET", "/targets", "lon=71.4&lat=51.1&category=potholes", None, "category"),
    ("GET", "/heat", "bbox=71.6,51.0,71.3,51.2", None, "bbox"),
    ("GET", "/heat", "bbox=1,2,3", None, "bbox"),
    ("GET", "/heat", "days=abc", None, "days"),
    ("GET", "/akim/summary", "date=11.10.2026", None, "date"),
    ("GET", "/akim/summary", "district=Нура", None, "district"),
    ("POST", "/proposals/p-1/vote", "", {"value": 2, "device_id": "device-123"}, "value"),
    ("POST", "/proposals/p-1/vote", "", {"value": True, "device_id": "device-123"}, "value"),
    ("POST", "/proposals/p-1/vote", "", {"value": 1, "device_id": "x"}, "device_id"),
    ("POST", "/complaints", "", {"text": "яма", "category": "potholes"}, "category"),
]


@pytest.mark.parametrize("method,path,query,body,field", BAD_INPUT)
def test_bad_input_is_400_and_module_is_not_called(method, path, query, body, field):
    called = []
    any_fn = lambda *a, **kw: called.append(1) or {}  # noqa: E731
    names = {h.function: any_fn for h in V2_HANDLERS.values()}
    modules = {name: fake_module(**names) for h in V2_HANDLERS.values() for name in h.modules}
    status, data = call(gw(modules), method, path, query, body)
    assert status == 400 and data["error"] == "bad_request" and data["field"] == field
    assert data["message"] and not called


def test_unknown_path_and_wrong_method():
    status, data = call(gw(), "GET", "/nope")
    assert status == 404 and data["error"] == "not_found"
    reply = gw().handle("DELETE", "/heat", "", None, CTX)
    assert reply["status"] == 405 and reply["headers"]["Allow"] == "GET"
    status, _ = call(gw(), "GET", "/complaints/bad id/metoo")
    assert status == 404


# --- ошибки модуля --------------------------------------------------------------

class ModuleError(Exception):
    status, code = 409, "already_voted"


@pytest.mark.parametrize("exc,status,code", [
    (ValueError("Текст пустой"), 400, "bad_request"),
    (KeyError("c-1"), 404, "not_found"),
    (PermissionError(), 403, "forbidden"),
    (ModuleError("Вы уже голосовали"), 409, "already_voted"),
    (RuntimeError("секретная подробность"), 500, "internal"),
])
def test_module_errors_become_clear_answers(exc, status, code):
    def heat(**kw):
        raise exc

    got_status, data = call(gw({"ui.civic_heat": fake_module(heat=heat)}), "GET", "/heat")
    assert (got_status, data["error"]) == (status, code)
    assert "секретная" not in json.dumps(data, ensure_ascii=False)


def test_non_object_result_is_500_not_a_crash():
    status, data = call(gw({"ui.civic_heat": fake_module(heat=lambda **kw: [1, 2])}), "GET", "/heat")
    assert status == 500 and data["error"] == "bad_module_response"


# --- маршруты сотрудника --------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("POST", "/complaints/c-1/status", {"status": "fixed"}),
    ("POST", "/proposals", {"kind": "park"}),
    ("PUT", "/objects/o-1/stage", {"stage": "design"}),
])
def test_staff_routes_need_r02_session(tmp_path, method, path, body):
    pytest.importorskip("ui.civic_store")
    called = []
    fn = lambda **kw: called.append(kw) or {"ok": 1}  # noqa: E731
    modules = {"ui.civic_feedback.v2": fake_module(set_complaint_status=fn),
               "ui.civic_store.v2": fake_module(create_proposal=fn, set_object_stage=fn)}
    gateway = gw(modules, CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3"))
    status, data = call(gateway, method, path, "", body)
    assert status == 401 and data["error"] == "unauthenticated" and not called


def test_staff_route_without_store_is_503():
    modules = {"ui.civic_store.v2": fake_module(set_object_stage=lambda **kw: {})}
    status, data = call(gw(modules, store_gateway=None), "PUT", "/objects/o-1/stage", "", {"stage": "design"})
    assert status == 503 and data["error"] == "module_not_ready"


def test_signed_in_staff_reaches_the_function(tmp_path):
    pytest.importorskip("ui.civic_store")
    v1 = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    store = v1.service("store")
    principal = types.SimpleNamespace(username="operator", role="editor")
    store.require_staff = lambda context, unsafe: (principal, None)
    seen = {}

    def set_object_stage(object_id, body, principal=None):
        seen.update(object_id=object_id, body=body, principal=principal)
        return {"id": object_id, "stage": body["stage"]}

    gateway = gw({"ui.civic_store.v2": fake_module(set_object_stage=set_object_stage)}, v1)
    status, data = call(gateway, "PUT", "/objects/o-1/stage", "", {"stage": "design"})
    assert status == 200 and data == {"id": "o-1", "stage": "design"}
    assert seen["principal"] == {"username": "operator", "role": "editor"}


# --- настоящий HTTP ---------------------------------------------------------------

@pytest.fixture()
def server(tmp_path):
    v2 = gw({"ui.civic_heat": fake_module(heat=lambda **kw: {"generated_at": "t", "items": [], "seen": kw["days"]}),
             "ui.civic_store.v2": fake_module(set_object_stage=lambda **kw: {"stage": "x"})})
    srv = web_server.create_server(port=0, civic_db=tmp_path / "civic.sqlite3", civic_v2=v2)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Host": f"127.0.0.1:{srv.server_address[1]}"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, (json.loads(raw) if raw else None), resp


def test_http_v2_get_and_503(server):
    status, data, resp = request(server, "GET", "/api/civic/v2/heat?days=7")
    assert status == 200 and data["seen"] == 7
    assert resp.getheader("Content-Type").startswith("application/json")
    assert resp.getheader("Cache-Control") == "no-store"
    status, data, _ = request(server, "POST", "/api/civic/v2/classify", {"text": "яма"})
    assert status == 503 and data == {"error": "module_not_ready", "message": data["message"],
                                      "module": "ui.civic_ml_api", "role": "R04"}


def test_http_v1_still_works_next_to_v2(server):
    status, data, _ = request(server, "GET", "/api/civic/v1/modules")
    assert status == 200 and data["ok"] is True
    status, data, _ = request(server, "GET", "/api/health")
    assert status == 200


def test_http_foreign_host_and_origin_are_refused(server):
    status, data, _ = request(server, "GET", "/api/civic/v2/heat", headers={"Host": "evil.example"})
    assert status == 403 and data["error"] == "forbidden_host"
    status, data, _ = request(server, "POST", "/api/civic/v2/classify", {"text": "яма"},
                           headers={"Origin": "http://evil.example"})
    assert status == 403 and data["error"] == "cross_origin"


def test_http_put_only_in_v2(server):
    status, data, _ = request(server, "PUT", "/api/civic/v2/objects/o-1/stage", {"stage": "design"})
    assert status == 401 or status == 503  # сессия сотрудника обязательна; без R02 — 503
    status, data, _ = request(server, "PUT", "/api/civic/v1/objects", {"a": 1})
    assert status in (404, 405) and data["ok"] is False
    status, data, _ = request(server, "PUT", "/api/validate", {"a": 1})
    assert status == 405


def test_http_body_checks(server):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/api/civic/v2/classify", body=b"not json",
                 headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 400 and json.loads(resp.read())["error"] == "invalid_json"
    conn.close()
    status, data, _ = request(server, "POST", "/api/civic/v2/classify", {"text": "x" * 70000})
    assert status == 413 and data["error"] == "too_large"
