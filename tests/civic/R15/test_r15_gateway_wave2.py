"""R15: волна 2 в шлюзе R01 (FINAL-2) — новые маршруты через настоящий HTTP на 127.0.0.1.

- «Службы» и выбор акима (R08): запись — только сессия сотрудника + CSRF; чтение — без логина сотрудника (S28).
- Подписки «Рядом» (R08): лимит запросов по адресу (V2_RATE_LIMITS), в файле нет сырого id устройства (S27).
- Инструменты сотрудника по обращениям (R04 merged/separate, R09 inbox/unduplicate/passport/update): не жителю.
- Фото жителя (R09) через шлюз: очищено (S22), видит автор, не посторонний; id фото нет в публичной карточке.
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


# Инструменты сотрудника по обращениям: R04 merged/separate (FINAL-2 шаг 1) и R09 волны 2 (шаг 3 — R04-маршруты
# сняты, у R09 свой /unduplicate). Маршрута нет в этой сборке — пропуск.
STAFF_TOOLS = [("GET", "/complaints/merged?target_id=osm-node-1", "complaints.merged"),
               ("POST", "/complaints/c-000000000001/separate", "complaints.separate"),
               ("GET", "/complaints/inbox", "complaints.inbox"),
               ("POST", "/complaints/c-000000000001/unduplicate", "complaints.unduplicate"),
               ("POST", "/complaints/c-000000000001/passport", "complaints.passport"),
               ("POST", "/complaints/c-000000000001/update", "complaints.update")]


@pytest.mark.parametrize("method,path,key", STAFF_TOOLS, ids=[t[2] for t in STAFF_TOOLS])
def test_staff_complaint_tools_refuse_residents(srv, method, path, key):
    if key not in {k for _m, _p, k in need_module("ui.web_server").V2_ROUTES}:
        pytest.skip(f"маршрута {key} нет в этой сборке")
    status, text = call(srv, method, path, {"text": "R15"} if method == "POST" else None, {"X-Birge-Device": DEVICE})
    assert status in (401, 403), (status, text[:200])


def _create(srv, text="Яма у остановки, вечером опасно", device=DEVICE):
    status, raw = call(srv, "POST", "/complaints", {"text": text, "category": "roads", "point": [71.43, 51.13]},
                       {"X-Birge-Device": device})
    if status not in (200, 201):
        pytest.skip(f"жалобы R09 в этой сборке не принимаются: {status}")
    return json.loads(raw)["data"]["complaint"]["id"]


def test_resident_photo_through_gateway_is_clean_and_private(srv):
    """Фото частями через шлюз: GPS/EXIF и хвост после конца JPEG сняты (S22), фото видит автор, не посторонний."""
    if "complaints.photos.start" not in {k for _m, _p, k in need_module("ui.web_server").V2_ROUTES}:
        pytest.skip("в этой сборке нет фото R09 (волна 1 п. 5)")
    import base64
    from test_r15_photos import JPEG_WITH_TAIL
    complaint_id = _create(srv)
    device = {"X-Birge-Device": DEVICE}
    status, raw = call(srv, "POST", "/complaints/%s/photos" % complaint_id,
                       {"kind": "resident", "size": len(JPEG_WITH_TAIL)}, device)
    assert status == 201, raw
    started = json.loads(raw)["data"]
    step, done = started["chunk_bytes"], None
    for offset in range(0, len(JPEG_WITH_TAIL), step):
        status, raw = call(srv, "POST", "/complaints/%s/photos/%s" % (complaint_id, started["upload_id"]),
                           {"offset": offset, "data": base64.b64encode(JPEG_WITH_TAIL[offset:offset + step]).decode()},
                           device)
        assert status in (200, 201), raw
        done = json.loads(raw)["data"]
    photo_id = done["photo"]["id"]
    path = "/complaints/%s/photos/%s" % (complaint_id, photo_id)
    status, raw = call(srv, "GET", path, headers=device)
    assert status == 200, raw
    data_url = json.loads(raw)["data"]["photo"]["data_url"]
    clean = base64.b64decode(data_url.split(",", 1)[1])
    assert b"SECRETPHONE" not in clean and b"Exif" not in clean and clean.count(b"\xff\xd8\xff") == 1
    for headers in ({"X-Birge-Device": "device-r15-stranger-00001"}, {}):
        assert call(srv, "GET", path, headers=headers)[0] in (401, 403)
    status, public = call(srv, "GET", "/complaints/" + complaint_id, headers={"X-Birge-Device": "device-r15-stranger-00001"})
    assert status == 200 and photo_id not in public


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


def test_photo_upload_starts_are_rate_limited(srv):
    """Начатая загрузка держит до 1,5 МБ в базе час, а у R09 их число не ограничено — предел у шлюза (V2_RATE_LIMITS)."""
    if "complaints.photos.start" not in {k for _m, _p, k in need_module("ui.web_server").V2_ROUTES}:
        pytest.skip("в этой сборке нет фото R09 (волна 1 п. 5)")
    complaint_id = _create(srv)
    statuses = [call(srv, "POST", "/complaints/%s/photos" % complaint_id, {"kind": "resident", "size": 1_400_000},
                     {"X-Birge-Device": DEVICE})[0] for _ in range(25)]
    assert statuses[0] == 201 and 429 in statuses, statuses
