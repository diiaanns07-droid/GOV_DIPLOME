"""R01 раунд 14: каркас API v2 (/api/civic/v2/*, CONTRACT §7) в ui/web_server.py.

Что проверяем:
- пока модуль роли не сдан, каждый маршрут отвечает 503 {"error": "module_not_ready", "module", "role"},
  а приложение и API v1 работают дальше;
- сданная функция получает уже проверенные параметры, её ответ уходит без обёртки;
- неверный ввод (координаты вне Астаны, неизвестная категория, голос 2) -> 400 до вызова модуля;
- ошибки модуля превращаются в понятные ответы, сервер не падает;
- маршруты сотрудника требуют сессию R02 (как staff-маршруты v1);
- настоящий HTTP: Host/Origin, PUT только в v2, 404/405, размер тела;
- B1: обработчики ролей R07/R08 (handle_get) и сервис жалоб R09 (конверт ok/data) подключены как есть;
  связка R09 -> тепловая карта R07 -> «Картина дня» R08 на настоящих модулях.
"""

from __future__ import annotations

import http.client
import json
import threading
import types

import pytest

from ui import web_server
from ui.web_server import CivicGateway, CivicV2Gateway, V2BadRequest, V2_HANDLERS, V2_ROUTES

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
    ("GET", "/categories", "", None),
    ("GET", "/complaints", "", None),
    ("POST", "/complaints", "", {"text": "яма"}),
    ("GET", "/complaints/mine", "", None),
    ("GET", "/complaints/events", "", None),
    ("GET", "/complaints/summary", "", None),
    ("GET", "/complaints/place", "lon=71.41&lat=51.11", None),
    ("GET", "/complaints/c-1", "", None),
    ("POST", "/complaints/c-1/metoo", "", {"device_id": "device-123"}),
    ("POST", "/complaints/c-1/status", "", {"status": "fixed"}),
    ("POST", "/complaints/c-1/duplicate", "", {"of": "c-2"}),
    ("GET", "/heat", "", None),
    ("GET", "/heat/meta", "", None),
    ("GET", "/heat/target", "kind=object&id=osm-node-1", None),
    ("GET", "/akim/summary", "", None),
    ("GET", "/street-segment", "from=71.41,51.11&to=71.42,51.11", None),
    ("GET", "/street-snap", "lon=71.41&lat=51.11", None),
    ("GET", "/objects-near", "lon=71.41&lat=51.11", None),
    ("GET", "/yard", "lon=71.41&lat=51.11", None),
    ("GET", "/geo/status", "", None),
    ("GET", "/proposals/summary", "", None),
    ("GET", "/proposals/p-1", "", None),
    ("POST", "/proposals/p-1/approve", "", {}),
    ("POST", "/proposals/p-1/reject", "", {}),
    ("POST", "/proposals/p-1/withdraw", "", {}),
    ("GET", "/objects/lagging", "", None),
    ("GET", "/objects/o-1", "", None),
    ("GET", "/staff/objects/o-1/stage", "", None),
    ("GET", "/proposals", "", None),
    ("POST", "/proposals", "", {"kind": "park"}),
    ("POST", "/proposals/p-1/vote", "", {"value": 1, "device_id": "device-123"}),
    ("GET", "/objects", "", None),
    ("PUT", "/objects/o-1/stage", "", {"stage": "design"}),
    ("GET", "/forecast", "month=2026-11&k=5", None),
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
    assert data["module"] and data["role"] in {"R04", "R06", "R07", "R08", "R09", "R12", "R13"}
    assert "Traceback" not in json.dumps(data, ensure_ascii=False)


def test_real_import_of_absent_packages_is_not_ready():
    # Настоящий importlib: пакетов ролей раунда 14 в сборке I0 ещё нет (или они уже есть — тогда ready).
    gateway = CivicV2Gateway()
    for key, state in gateway.modules().items():
        assert state["status"] in {"ready", "module_not_ready"}, (key, state)


def test_modules_route_lists_each_route_with_role():
    status, data = call(gw({"ui.civic_heat.api": fake_module(handle_get=lambda path, query: (200, {"items": []}))}),
                        "GET", "/modules")
    assert status == 200
    assert data["modules"]["heat"] == {"role": "R07", "module": "ui.civic_heat.api", "function": "handle_get",
                                       "status": "ready"}
    assert data["modules"]["classify"]["status"] == "module_not_ready"


def test_module_without_the_function_is_not_ready():
    status, data = call(gw({"ui.civic_ml_api": fake_module(other=lambda: None)}), "POST", "/classify", "",
                        {"text": "яма"})
    assert status == 503 and data["module"] == "ui.civic_ml_api"


def test_broken_module_is_reported_and_app_keeps_working(monkeypatch):
    def broken_import(name):
        if name.startswith("ui.civic_heat"):
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


def test_context_and_principal_only_for_functions_that_declare_them():
    seen = {}

    def list_objects(bbox=None, context=None):
        seen["bbox"], seen["context"] = bbox, context
        return 201, {"items": []}

    status, data = call(gw({"ui.civic_store.v2": fake_module(list_objects=list_objects)}), "GET", "/objects", "", None)
    assert status == 201 and data == {"items": []}
    assert seen == {"bbox": None, "context": CTX}


def test_function_with_var_kwargs_also_gets_context_and_principal():
    seen = {}
    status, _ = call(gw({"ui.civic_store.v2": fake_module(list_proposals=lambda **kw: seen.update(kw) or {"items": []})}),
                     "GET", "/proposals", "bbox=71.3,51.0,71.6,51.2")
    assert status == 200 and seen["bbox"] == (71.3, 51.0, 71.6, 51.2)
    assert seen["context"] is CTX and seen["principal"] is None


def test_package_level_function_is_found_when_v2_submodule_is_absent():
    module = fake_module(list_proposals=lambda bbox=None: {"items": [], "bbox": bbox})
    status, data = call(gw({"ui.civic_store": module}), "GET", "/proposals", "bbox=71.3,51.0,71.6,51.2")
    assert status == 200 and tuple(data["bbox"]) == (71.3, 51.0, 71.6, 51.2)


# --- B1: обработчики ролей как есть ------------------------------------------------

def test_raw_role_handler_gets_full_path_and_parsed_query():
    seen = {}

    def handle_get(path, query):
        seen.update(path=path, query=query)
        return 200, {"items": [], "demo": True}

    status, data = call(gw({"ui.civic_heat.api": fake_module(handle_get=handle_get)}), "GET", "/heat/target",
                        "kind=object&id=osm-node-1&days=7")
    assert status == 200 and data == {"items": [], "demo": True}
    assert seen == {"path": "/api/civic/v2/heat/target", "query": {"kind": ["object"], "id": ["osm-node-1"], "days": ["7"]}}


@pytest.mark.parametrize("result,status,code", [((400, {"error": "bad_request", "field": "days"}), 400, "bad_request"),
                                                ((200, [1]), 500, "bad_module_response"),
                                                ("nonsense", 500, "internal")])
def test_raw_role_handler_errors_pass_or_become_500(result, status, code):
    module = fake_module(handle_get=lambda path, query: result)
    got, data = call(gw({"ui.civic_akim.api": module}), "GET", "/akim/summary", "date=2026-10-11")
    assert (got, data["error"]) == (status, code)


class FakeComplaints:
    def __init__(self, db):
        self.db, self.calls = db, []

    def handle(self, method, path, query, body, principal, context):
        self.calls.append((method, path, query, body, principal))
        if path.endswith("/boom"):
            raise RuntimeError("секрет")
        return {"status": 201, "headers": {"Retry-After": "3"}, "body": {"ok": True, "data": {"id": "c-1"}}}


def test_service_role_answers_whole_request_in_its_envelope(tmp_path):
    made = []
    module = fake_module(make_service=lambda db: made.append(FakeComplaints(db)) or made[-1])
    gateway = CivicV2Gateway(modules={"ui.civic_feedback.v2.integration": module}, db_path=tmp_path / "civic.sqlite3")
    status, data = call(gateway, "POST", "/complaints", "", {"text": "Яма", "category": "roads"})
    assert status == 201 and data == {"ok": True, "data": {"id": "c-1"}}
    call(gateway, "GET", "/complaints/mine", "x=1")
    assert len(made) == 1 and made[0].db == str(tmp_path / "civic.sqlite3")  # один сервис на процесс
    assert made[0].calls[0][:2] == ("POST", "/api/civic/v2/complaints") and made[0].calls[1][2] == "x=1"
    assert made[0].calls[0][4] is None  # без шлюза v1 сотрудника нет


def test_service_role_without_database_is_not_ready():
    module = fake_module(make_service=lambda db: FakeComplaints(db))
    status, data = call(CivicV2Gateway(modules={"ui.civic_feedback.v2.integration": module}), "GET", "/complaints")
    assert status == 503 and data["error"] == "module_not_ready" and data["role"] == "R09"


def test_real_b1_chain_complaint_reaches_heat_and_day(tmp_path, monkeypatch):
    """Настоящие R09 + R07 + R08: новая жалоба сразу видна на карте и в «Картине дня»."""
    pytest.importorskip("ui.civic_feedback.v2.integration")
    pytest.importorskip("ui.civic_heat.api")
    pytest.importorskip("ui.civic_akim.api")
    import ui.civic_heat as civic_heat
    monkeypatch.setattr(civic_heat.service, "_default", None)  # не трогаем общий сервис других тестов
    v1 = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    gateway = CivicV2Gateway(v1, demo=False)
    status, before = call(gateway, "GET", "/heat", "days=30&zoom=16")
    assert status == 200 and before["items"] == []  # без демо-набора и без жалоб — пусто, а не выдумано
    ctx = dict(CTX, headers={"x-birge-device": "test-device-0001"})
    status, made = call(gateway, "POST", "/complaints", "", {"text": "На остановке не горит свет", "category": "lighting",
                                                              "point": NURA}, ctx)
    assert status in (200, 201) and made["ok"] is True
    status, after = call(gateway, "GET", "/heat", "days=30&zoom=16")
    assert status == 200 and len(after["items"]) == 1 and after["items"][0]["count"] == 1
    status, day = call(gateway, "GET", "/akim/summary")
    assert status == 200 and day["kpi"]["new_day"]["value"] == 1
    monkeypatch.setattr(civic_heat.service, "_default", None)


def test_vote_body_is_checked_and_passed():
    seen = {}
    module = fake_module(vote_proposal=lambda proposal_id, value, device_id: seen.update(
        id=proposal_id, value=value, device=device_id) or {"votes_up": 1, "votes_down": 0})
    gateway = gw({"ui.civic_store.v2": module})
    status, _ = call(gateway, "POST", "/proposals/p-7/vote", "", {"value": -1, "device_id": "device-abc-123"})
    assert status == 200 and seen == {"id": "p-7", "value": -1, "device": "device-abc-123"}


# --- неверный ввод: 400 до вызова модуля ----------------------------------------

# Жалобы R09, тепловая карта R07 и «Картина дня» R08 проверяют свои параметры сами (их тесты в tests/civic/R07–R09).
BAD_INPUT = [
    ("POST", "/classify", "", {"text": "   "}, "text"),
    ("POST", "/classify", "", {"text": "я" * 5001}, "text"),
    ("POST", "/similar", "", {"text": "яма", "point": [0, 0]}, "point"),
    ("POST", "/similar", "", {"text": "яма", "days": 0}, "days"),
    ("GET", "/targets", "lon=71.4", None, "lon"),
    ("GET", "/targets", "lon=37.6&lat=55.7", None, "lon"),  # Москва — вне Астаны
    ("GET", "/targets", "lon=nan&lat=51.1", None, "lon"),
    ("GET", "/targets", "lon=71.4&lat=51.1&category=potholes", None, "category"),
    ("GET", "/objects", "bbox=71.6,51.0,71.3,51.2", None, "bbox"),
    ("GET", "/proposals", "bbox=1,2,3", None, "bbox"),
    ("POST", "/proposals/p-1/vote", "", {"value": 2, "device_id": "device-123"}, "value"),
    ("POST", "/proposals/p-1/vote", "", {"value": True, "device_id": "device-123"}, "value"),
    ("POST", "/proposals/p-1/vote", "", {"value": 1, "device_id": "x"}, "device_id"),
]


@pytest.mark.parametrize("method,path,query,body,field", BAD_INPUT)
def test_bad_input_is_400_and_module_is_not_called(method, path, query, body, field):
    called = []
    any_fn = lambda *a, **kw: called.append(1) or {}  # noqa: E731
    names = {h.function: any_fn for h in V2_HANDLERS.values() if h.kind == "function"}
    modules = {name: fake_module(**names) for h in V2_HANDLERS.values() if h.kind == "function" for name in h.modules}
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
    def list_objects(**kw):
        raise exc

    got_status, data = call(gw({"ui.civic_store.v2": fake_module(list_objects=list_objects)}), "GET", "/objects")
    assert (got_status, data["error"]) == (status, code)
    assert "секретная" not in json.dumps(data, ensure_ascii=False)


def test_non_object_result_is_500_not_a_crash():
    status, data = call(gw({"ui.civic_store.v2": fake_module(list_objects=lambda **kw: [1, 2])}), "GET", "/objects")
    assert status == 500 and data["error"] == "bad_module_response"


# --- маршруты сотрудника --------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("POST", "/proposals", {"kind": "park"}),
    ("PUT", "/objects/o-1/stage", {"stage": "design"}),
])
def test_staff_routes_need_r02_session(tmp_path, method, path, body):
    pytest.importorskip("ui.civic_store")
    called = []
    fn = lambda **kw: called.append(kw) or {"ok": 1}  # noqa: E731
    modules = {"ui.civic_store.v2": fake_module(create_proposal=fn, set_object_stage=fn)}
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
    v2 = gw({"ui.civic_heat.api": fake_module(handle_get=lambda path, q: (200, {"generated_at": "t", "items": [],
                                                                               "seen": int(q["days"][0])})),
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


def test_forecast_arguments_are_checked_before_the_module():
    gateway = CivicV2Gateway()
    assert gateway.arguments("forecast", {}, "", None) == {"month": None, "district": None, "k": 10}
    assert gateway.arguments("forecast", {}, "month=2026-11&district=nura&k=3", None) == {
        "month": "2026-11", "district": "nura", "k": 3}
    for query, field in (("month=2026-13", "month"), ("month=11-2026", "month"), ("k=0", "k"), ("k=51", "k"),
                         ("district=Нура", "district")):
        with pytest.raises(V2BadRequest) as error:
            gateway.arguments("forecast", {}, query, None)
        assert error.value.field == field
