"""R15: волна 2 в шлюзе R01 (FINAL-2) — новые маршруты через настоящий HTTP на 127.0.0.1.

- «Службы» и выбор акима (R08): запись — только сессия сотрудника + CSRF; чтение — без логина сотрудника (S28).
- Подписки «Рядом» (R08): лимит запросов по адресу (V2_RATE_LIMITS), в файле нет сырого id устройства (S27).
- «Это разные проблемы» и список объединённых (R04 + R09): только сотрудник.
- Фильтр мата в шлюзе (R04): житель видит звёздочки, сотрудник — оригинал; машинные строки (CSRF-токен входа) целы (S26).
Файлы R08 (.runtime/civic_akim/...) — во временной папке. Нет маршрутов волны 2 в сборке — skip.
"""

from __future__ import annotations

import json

import pytest

from r15_common import live_server, need_module, request

STAFF = "r15gwstaff"
PASSWORD = "R15-Strong-Pass-2026"
DEVICE = "device-r15-gateway-000001"


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    web_server = need_module("ui.web_server")
    keys = {key for _m, _p, key in getattr(web_server, "V2_ROUTES", ())}
    if "akim.routing.update" not in keys:
        pytest.skip("в этой сборке нет маршрутов волны 2 R08 (FINAL-2)")
    for module, attr, name in (("ui.civic_akim.routing", "OVERRIDE_PATH", "routing.json"),
                               ("ui.civic_akim.decisions", "STORE_PATH", "decisions.json"),
                               ("ui.civic_akim.nearby", "SUBS_PATH", "subscriptions.json")):
        monkeypatch.setattr(need_module(module), attr, tmp_path / name)
    with live_server(tmp_path) as server:
        yield server


def origin(srv):
    return "http://127.0.0.1:%d" % srv.server_address[1]


def call(srv, method, path, body=None, headers=None):
    status, _h, raw = request(srv, method, "/api/civic/v2" + path, body,
                              headers={"Origin": origin(srv), **(headers or {})})
    return status, raw.decode("utf-8", "replace")


def login(srv):
    """-> (cookie, csrf) сотрудника, как в интерфейсе (сессия R02/R06)."""
    srv.civic.service("store").accounts.create_user(STAFF, PASSWORD, display_name="R15", role="editor")
    status, headers, raw = request(srv, "POST", "/api/civic/v1/session/login", {"username": STAFF, "password": PASSWORD},
                                   headers={"Origin": origin(srv)})
    assert status == 200, raw
    return headers.get("set-cookie", "").split(";")[0], json.loads(raw)["data"]["csrf_token"]


@pytest.mark.parametrize("method,path,body", [
    ("PUT", "/akim/routing", {"rules": {"roads/marking": "road"}}),
    ("POST", "/akim/decisions/c-r15-gw-0001", {"option": 1}),
])
def test_akim_writes_need_session_and_csrf(srv, method, path, body):
    cookie, token = login(srv)
    assert call(srv, method, path, body)[0] in (401, 403)                                   # аноним
    assert call(srv, method, path, body, {"Cookie": cookie})[0] == 403                      # без CSRF
    assert call(srv, method, path, body, {"Cookie": cookie, "X-CSRF-Token": "x" * 43})[0] == 403
    status, text = call(srv, method, path, body, {"Cookie": cookie, "X-CSRF-Token": token})
    # Правка служб проходит; выбора по несуществующему вопросу нет — 404 (до модуля дошли с правами сотрудника).
    assert status == (200 if method == "PUT" else 404), text


def test_routing_read_is_public_without_staff_login(srv):
    cookie, token = login(srv)
    status, _t = call(srv, "PUT", "/akim/routing", {"rules": {"roads/marking": "road"}},
                      {"Cookie": cookie, "X-CSRF-Token": token})
    assert status == 200
    status, text = call(srv, "GET", "/akim/routing")
    assert status == 200 and '"roads/marking"' in text
    assert STAFF not in text


def test_nearby_subscribe_is_rate_limited_and_hashed(srv, tmp_path):
    statuses = []
    for i in range(25):
        status, _t = call(srv, "POST", "/nearby/subscriptions",
                          {"device_id": "device-r15-gw-%010d" % i, "scope": "district", "id": "nura"})
        statuses.append(status)
    assert statuses[0] == 200, statuses
    assert 429 in statuses, statuses                 # V2_RATE_LIMITS nearby.subscribe: 20 в минуту с адреса
    saved = (tmp_path / "subscriptions.json").read_text("utf-8")
    assert "device-r15-gw-" not in saved


@pytest.mark.parametrize("method,path", [("GET", "/complaints/merged?target_id=osm-node-1"),
                                         ("POST", "/complaints/c-000000000001/separate")])
def test_merge_tools_are_staff_only(srv, method, path):
    status, text = call(srv, method, path, {} if method == "POST" else None, {"X-Birge-Device": DEVICE})
    assert status in (401, 403), (status, text[:200])


def test_profanity_masked_for_residents_original_for_staff(srv):
    status, text = call(srv, "POST", "/complaints",
                        {"text": "Сука, опять яма у подъезда, третий год", "category": "roads", "point": [71.43, 51.13]},
                        {"X-Birge-Device": DEVICE})
    if status not in (200, 201):
        pytest.skip(f"жалобы R09 в этой сборке не принимаются: {status}")
    complaint_id = json.loads(text)["data"]["complaint"]["id"]
    status, mine = call(srv, "GET", "/complaints/mine", headers={"X-Birge-Device": DEVICE})
    assert status == 200 and complaint_id in mine and "Сука" not in mine and "яма у подъезда" in mine
    cookie, token = login(srv)                       # CSRF-токен из ответа входа не испорчен фильтром …
    status, staff = call(srv, "GET", "/complaints/" + complaint_id, headers={"Cookie": cookie})
    assert status == 200 and "Сука" in staff         # … и сотрудник видит оригинал
    status, text = call(srv, "POST", "/complaints/%s/status" % complaint_id, {"status": "accepted"},
                        {"Cookie": cookie, "X-CSRF-Token": token})
    assert status == 200, text
