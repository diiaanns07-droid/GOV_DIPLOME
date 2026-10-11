"""R15: ни один публичный маршрут API v2 не отдаёт личные данные — общий сторож для новых маршрутов.

Тест сам берёт таблицу маршрутов шлюза R01 (ui.web_server.V2_ROUTES): каждый GET-маршрут без пометки «сотрудник»
вызывается анонимно с типичными параметрами. До этого в базу кладутся «метки»: жалоба с ФИО, телефоном, почтой и
точной точкой жителя, заметка и логин сотрудника. Ни одна метка не должна появиться ни в одном публичном ответе.
Новые разделы второй волны («Рядом», «Идеи», «Вопрос акиму», пульс, QR) попадают под проверку сами, как только
R01 добавит их маршруты.
"""

from __future__ import annotations

import json

import pytest

from r15_common import live_server, need_module, request

DEVICE = "device-r15-marker-0000001"
POINT = [71.412345, 51.123456]
CELL = "cell-239-232"
STAFF = "r15markerstaff"
MARKERS = {
    "ФИО из текста": "Маркеров",
    "телефон": "5551234",
    "почта": "secret.marker@example.kz",
    "id устройства": DEVICE,
    "точка жителя (широта)": "51.123456",
    "точка жителя (долгота)": "71.412345",
    "заметка сотрудника": "R15-NOTE-MARKER",
    "логин сотрудника": STAFF,
}
QUERY = ("bbox=70.9,50.9,71.9,51.4&lon=71.4123&lat=51.1234&district=nura&days=30&zoom=16"
         f"&target_id={CELL}&kind=area&id={CELL}")


@pytest.fixture()
def srv(tmp_path):
    with live_server(tmp_path) as server:
        if not hasattr(server, "civic_v2"):
            pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
        yield server


def _seed(srv):
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    status, _h, data = request(srv, "POST", "/api/civic/v2/complaints",
                               {"text": "Маркеров Секрет Иванович, тел. +7 701 555 12 34, secret.marker@example.kz — "
                                        "у подъезда не горит фонарь", "category": "lighting", "point": POINT,
                                "target": {"kind": "area", "id": CELL}},
                               headers={"Origin": origin, "X-Birge-Device": DEVICE})
    if status not in (200, 201):
        pytest.skip(f"жалобы R09 в этой сборке не принимаются: {status}")
    complaint = json.loads(data)["data"]["complaint"]
    store = srv.civic.service("store")
    if store is not None and hasattr(store, "accounts"):
        store.accounts.create_user(STAFF, "R15-Strong-Pass-2026", display_name="R15 Маркеров", role="editor")
        status, headers, raw = request(srv, "POST", "/api/civic/v1/session/login",
                                       {"username": STAFF, "password": "R15-Strong-Pass-2026"}, headers={"Origin": origin})
        if status == 200:
            token = json.loads(raw)["data"]["csrf_token"]
            cookie = headers.get("set-cookie", "").split(";")[0]
            request(srv, "POST", "/api/civic/v2/complaints/%s/status" % complaint["id"],
                    {"status": "accepted", "note": "R15-NOTE-MARKER звонил по телефону"},
                    headers={"Origin": origin, "Cookie": cookie, "X-CSRF-Token": token})
    return complaint


def _public_get_routes(web_server):
    for method, pattern, key in web_server.V2_ROUTES:
        handler = web_server.V2_HANDLERS.get(key)
        if method != "GET" or key == "modules" or (handler is not None and handler.staff) or "staff" in pattern:
            continue
        yield key, pattern


def test_public_v2_routes_leak_no_personal_markers(srv):
    web_server = need_module("ui.web_server")
    complaint = _seed(srv)
    ids = {"complaints": complaint["id"]}
    checked, leaks = [], []
    for key, pattern in _public_get_routes(web_server):
        if "{id}" in pattern:
            parts = [ids.get(pattern[0], "r15-unknown-0001") if p == "{id}" else p for p in pattern]
        else:
            parts = list(pattern)
        path = "/api/civic/v2/" + "/".join(parts)
        for query in ("", QUERY):
            status, _h, raw = request(srv, "GET", path + ("?" + query if query else ""),
                                      headers={"X-Birge-Device": "device-r15-stranger-00001"})
            if status == 503:
                break  # модуль не подключён в этой сборке
            body = raw.decode("utf-8", "replace")
            checked.append(f"{key} {status}")
            for what, marker in MARKERS.items():
                if marker in body:
                    leaks.append(f"{key} ({path}{'?' + query if query else ''}): {what}")
    assert checked, "ни один публичный маршрут не ответил"
    assert not leaks, "личные данные в публичных ответах:\n" + "\n".join(sorted(set(leaks)))


def test_author_sees_own_text_but_not_staff_note(srv):
    """Обратная сторона: автор по своему устройству видит свой текст (иначе сторож выше прошёл бы на пустой базе)."""
    complaint = _seed(srv)
    status, _h, raw = request(srv, "GET", "/api/civic/v2/complaints/mine", headers={"X-Birge-Device": DEVICE})
    assert status == 200
    body = raw.decode("utf-8")
    assert "Маркеров" in body and complaint["id"] in body
    assert "R15-NOTE-MARKER" not in body and STAFF not in body
