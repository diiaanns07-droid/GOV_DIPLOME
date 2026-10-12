"""Round 12, приёмка R06 через настоящий HTTP-шлюз R01 + R02 (временная SQLite, синтетический объект).

создать -> увидеть в очереди -> обработать -> проверить публичность/приватность;
без модели R08 сообщение сохраняется; два быстрых одинаковых клика не дают неожиданного дубля.
Пропускается, если в дереве нет шлюза R01/R02 (как в ветке только с путями R06).
"""

import json
import secrets
import threading
import urllib.error
import urllib.request

import pytest

web_server = pytest.importorskip("ui.web_server")
civic_service_module = pytest.importorskip("ui.civic_store.service")
civic_auth = pytest.importorskip("ui.civic_store.auth")
if not hasattr(web_server, "CivicGateway"):
    pytest.skip("шлюз civic-v1 R01 ещё не в этом дереве", allow_module_level=True)

NOTE = "R12-ACCEPT служебная заметка: не для публикации"
REASON = "R12-ACCEPT внутреннее обоснование"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(civic_auth, "SCRYPT_N", 2 ** 10)  # быстрый KDF только в тесте
    monkeypatch.setattr(civic_auth, "SCRYPT_P", 1)
    db_path = tmp_path / "civic.sqlite3"
    password = "R06-" + secrets.token_urlsafe(16)          # одноразовый, не хранится в Git
    store = civic_service_module.CivicService(db_path)
    store.accounts.create_user("r06editor", password, display_name="Редактор R06")
    srv = web_server.create_server(port=0, civic_db=db_path)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    status, login, headers = http(base, "POST", "/session/login", {"username": "r06editor", "password": password})
    assert status == 200, login
    session = {"cookie": headers["Set-Cookie"].split(";", 1)[0], "csrf": login["data"]["csrf_token"]}
    object_id = publish_object(base, session)
    yield base, session, object_id
    srv.shutdown()
    srv.server_close()


def http(base, method, path, body=None, cookie=None, csrf=None, query=""):
    request = urllib.request.Request(base + "/api/civic/v1" + path + query, method=method,
                                     data=None if body is None else json.dumps(body).encode())
    request.add_header("Content-Type", "application/json")
    request.add_header("Origin", base)
    if cookie:
        request.add_header("Cookie", cookie)
    if csrf:
        request.add_header("X-CSRF-Token", csrf)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read()), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read()), error.headers


def staff(base, session, method, path, body=None, query=""):
    return http(base, method, path, body, session["cookie"], session["csrf"], query)


def publish_object(base, session):
    payload = {"kind": "roadworks", "title": "СИНТЕТИКА R06 r12: ремонт прохода", "description": "Тестовая запись.",
               "status": "planned", "geometry": {"type": "Point", "coordinates": [71.43, 51.17]},
               "geometry_precision": "approximate",
               "schedule": {"planned_start": "2026-10-14", "original_planned_end": None,
                            "current_planned_end": "2026-10-20", "actual_end": None},
               "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
               "responsible": {"organization": None, "public_contact": None},
               "evidence_type": "synthetic", "source_refs": [], "evidence_notes": "R06 r12 acceptance"}
    status, created, _ = staff(base, session, "POST", "/staff/objects", payload)
    assert status == 201, created
    item = created["data"]["item"]
    status, published, _ = staff(base, session, "POST", f"/staff/objects/{item['id']}/publish",
                                 {"expected_revision": item["revision"], "reason": "R06 r12"})
    assert status == 200, published
    return item["id"]


def test_create_queue_process_public_private(app):
    base, session, object_id = app
    public_body = {"object_id": object_id, "category": "roads", "consent_public": True,
                   "text": "R12 приёмка: нет прохода вдоль ограждения, люди идут по дороге."}
    private_body = {"object_id": object_id, "category": "sidewalks", "consent_public": False,
                    "text": "R12 приёмка: прошу не публиковать — у перехода опасно вечером."}
    status, receipt, _ = http(base, "POST", "/feedback", public_body)
    assert status == 201 and receipt["data"]["official_registration"] is False
    assert receipt["data"]["handling_status"] == "new"
    status, private_receipt, _ = http(base, "POST", "/feedback", private_body)
    assert status == 201

    # очередь через шлюз: новые фильтры query проходят allowlist шлюза
    status, queue, _ = staff(base, session, "GET", "/staff/feedback", query="?status=new&q=" +
                             urllib.request.quote("ограждения"))
    assert status == 200 and len(queue["data"]["items"]) == 1, queue
    entry = queue["data"]["items"][0]
    assert entry["classifier"]["status"] == "unavailable"     # модель R08 не подключена — сообщение сохранено
    path = f"/staff/feedback/{entry['id']}/moderate"

    assert staff(base, session, "POST", path, {"action": "note", "internal_note": NOTE})[0] == 200
    status, step, _ = staff(base, session, "POST", path, {"expected_revision": 1, "action": "status",
                                                           "status": "in_review", "reason": REASON})
    assert status == 200 and step["data"]["item"]["handling_status"] == "in_review"
    status, step, _ = staff(base, session, "POST", path, {
        "expected_revision": 2, "action": "approve", "reason": REASON, "status": "answered",
        "public_reply": "Спасибо. Сообщение опубликовано на платформе; это не означает начала работ."})
    assert status == 200 and step["data"]["item"]["handling_status"] == "answered"

    # публично: текст и ответ платформы, статус обработки; ни заметок, ни обоснований, ни сотрудника
    status, listing, _ = http(base, "GET", f"/objects/{object_id}/feedback")
    dumped = json.dumps(listing, ensure_ascii=False)
    assert status == 200 and len(listing["data"]["items"]) == 1
    assert listing["data"]["items"][0]["handling_label"] == "Дан ответ платформы"
    for secret in (NOTE, REASON, "r06editor", "Редактор R06", "прошу не публиковать", "fbr_", "client"):
        assert secret not in dumped, secret
    # автор видит ответ и статус по квитанции
    status, check, _ = http(base, "POST", "/feedback/receipt", {"receipt_id": receipt["data"]["receipt_id"]})
    assert status == 200 and check["data"]["handling_status"] == "answered" and check["data"]["is_public"]
    assert NOTE not in json.dumps(check, ensure_ascii=False)
    # сообщение без согласия не публикуется даже после одобрения
    status, queue, _ = staff(base, session, "GET", "/staff/feedback", query="?status=new")
    other = queue["data"]["items"][0]
    status, _, _ = staff(base, session, "POST", f"/staff/feedback/{other['id']}/moderate",
                         {"expected_revision": 1, "action": "approve", "reason": REASON})
    assert status == 200
    status, listing, _ = http(base, "GET", f"/objects/{object_id}/feedback")
    assert len(listing["data"]["items"]) == 1
    status, check, _ = http(base, "POST", "/feedback/receipt", {"receipt_id": private_receipt["data"]["receipt_id"]})
    assert check["data"]["is_public"] is False

    # служебные действия без сессии/CSRF не проходят через шлюз
    assert http(base, "POST", path, {"action": "note", "internal_note": "x"})[0] == 401
    assert http(base, "POST", path, {"action": "note", "internal_note": "x"}, session["cookie"])[0] == 403


def test_two_fast_identical_clicks_make_one_message(app):
    base, session, object_id = app
    body = {"object_id": object_id, "category": "roads", "consent_public": True,
            "text": "R12 двойной клик: яма у въезда во двор, машины объезжают по тротуару.",
            "client_request_id": "r12-double-click-000000001"}
    results = []

    def click():
        results.append(http(base, "POST", "/feedback", body))

    threads = [threading.Thread(target=click) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    statuses = sorted(r[0] for r in results)
    assert statuses == [200, 201], [r[1] for r in results]           # вторая — повтор той же отправки
    assert len({r[1]["data"]["receipt_id"] for r in results}) == 1    # одна квитанция
    status, queue, _ = staff(base, session, "GET", "/staff/feedback", query="?status=all&q=" +
                             urllib.request.quote("двойной клик"))
    assert len(queue["data"]["items"]) == 1
    # клиент без client_request_id: повтор того же текста — предупреждение, а не тихая копия
    plain = {k: v for k, v in body.items() if k != "client_request_id"}
    status, warning, _ = http(base, "POST", "/feedback", plain)
    assert status == 409 and warning["error"]["code"] == "duplicate_warning" and warning["error"]["can_confirm"]
