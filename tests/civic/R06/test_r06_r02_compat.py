"""Совместимость R06 с настоящим CivicService R02 (пропускается, если ui.civic_store нет).

В ветке R06 модуля R02 нет; тест выполняется в интегрированной ветке R01 или
локально поверх файлов R02 (см. research/round-11-results/R06/INTEGRATION.txt).
"""

import copy
from datetime import datetime, timedelta, timezone
import json
import secrets

import pytest

civic_service_module = pytest.importorskip("ui.civic_store.service")
civic_auth = pytest.importorskip("ui.civic_store.auth")

from ui.civic_feedback.fixtures import FIXTURE_OBJECTS  # noqa: E402
from ui.civic_feedback.integration import build_feedback_service, dispatch_civic  # noqa: E402


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setattr(civic_auth, "SCRYPT_N", 2 ** 10)  # быстрый KDF только в тесте
    monkeypatch.setattr(civic_auth, "SCRYPT_P", 1)
    clock = Clock()
    db_path = tmp_path / "civic.sqlite3"
    civic = civic_service_module.CivicService(db_path, clock=clock)
    password = "R06-" + secrets.token_urlsafe(16)  # одноразовый, не хранится в Git
    civic.accounts.create_user("r06editor", password, display_name="Редактор R06",
                               public_label="Редакция платформы")
    feedback = build_feedback_service(db_path, civic, classifier=None)
    yield civic, feedback, password, clock
    feedback.close()


def ctx(cookie=None, csrf=None, same_origin=True):
    headers = {"Host": "127.0.0.1:8501"}
    if cookie:
        headers["Cookie"] = f"{civic_auth.COOKIE_NAME}={cookie}"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": "127.0.0.1", "host_allowed": True,
            "is_same_origin": same_origin, "is_https": False}


def call(civic, feedback, method, path, body=None, context=None):
    raw = json.dumps(body).encode() if body is not None else None
    result = dispatch_civic(feedback, civic, method, "/api/civic/v1" + path, None, raw, context or ctx())
    assert result is not None, path
    return result


def login(civic, feedback, password):
    result = call(civic, feedback, "POST", "/session/login", {"username": "r06editor", "password": password})
    assert result["status"] == 200, result
    cookie = result["headers"]["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
    return cookie, result["body"]["data"]["csrf_token"]


def create_object(civic, feedback, cookie, csrf, publish=True):
    payload = copy.deepcopy(FIXTURE_OBJECTS["demo-astana-work-01"])
    for key in ("schema_version", "id", "city", "publication", "updated_at", "revision"):
        payload.pop(key)
    payload["schedule"]["original_planned_end"] = None
    created = call(civic, feedback, "POST", "/staff/objects", payload, ctx(cookie, csrf))
    assert created["status"] == 201, created
    item = created["body"]["data"]["item"]
    if publish:
        published = call(civic, feedback, "POST", f"/staff/objects/{item['id']}/publish",
                         {"expected_revision": item["revision"], "reason": "Публикация для теста R06"},
                         ctx(cookie, csrf))
        assert published["status"] == 200, published
        item = published["body"]["data"]["item"]
    return item


def test_full_flow_with_real_r02_principal_and_objects(stack):
    civic, feedback, password, clock = stack
    cookie, csrf = login(civic, feedback, password)
    published = create_object(civic, feedback, cookie, csrf)
    draft = create_object(civic, feedback, cookie, csrf, publish=False)

    body = {"object_id": published["id"], "category": "sidewalks", "consent_public": True,
            "text": "Нет прохода вдоль ограждения, люди идут по проезжей части."}
    assert call(civic, feedback, "POST", "/feedback", body)["status"] == 201
    draft_body = dict(body, object_id=draft["id"])
    rejected = call(civic, feedback, "POST", "/feedback", draft_body)
    assert rejected["status"] == 422 and rejected["body"]["error"]["code"] == "object_not_found"

    # GET /objects/{id}/feedback не теряется в GET /objects/{id}.
    detail = call(civic, feedback, "GET", f"/objects/{published['id']}")
    assert detail["status"] == 200 and "item" in detail["body"]["data"]
    listing = call(civic, feedback, "GET", f"/objects/{published['id']}/feedback")
    assert listing["status"] == 200 and listing["body"]["data"]["items"] == []
    assert call(civic, feedback, "GET", f"/objects/{draft['id']}/feedback")["status"] == 404

    # Аноним и запрос без CSRF не модерируют; настоящий Principal R02 — модерирует.
    assert call(civic, feedback, "GET", "/staff/feedback")["status"] == 401
    queue = call(civic, feedback, "GET", "/staff/feedback", context=ctx(cookie))
    assert queue["status"] == 200
    item = queue["body"]["data"]["items"][0]
    decision = {"expected_revision": item["revision"], "action": "approve", "reason": "Проверено R06"}
    path = f"/staff/feedback/{item['id']}/moderate"
    assert call(civic, feedback, "POST", path, decision, ctx(cookie))["status"] == 403
    approved = call(civic, feedback, "POST", path, decision, ctx(cookie, csrf))
    assert approved["status"] == 200, approved
    assert approved["body"]["data"]["item"]["moderated_by"] == "r06editor"
    detail = call(civic, feedback, "GET", f"/staff/feedback/{item['id']}", context=ctx(cookie))
    assert detail["body"]["data"]["object"]["title"] == published["title"]
    assert "internal_notes" not in detail["body"]["data"]["object"]

    public = call(civic, feedback, "GET", f"/objects/{published['id']}/feedback")["body"]["data"]["items"]
    assert len(public) == 1 and "r06editor" not in json.dumps(public, ensure_ascii=False)

    # Logout: тот же cookie больше не даёт прав.
    out = call(civic, feedback, "POST", "/session/logout", {}, ctx(cookie, csrf))
    assert out["status"] == 200
    again = dict(decision, expected_revision=item["revision"] + 1, action="reject")
    assert call(civic, feedback, "POST", path, again, ctx(cookie, csrf))["status"] == 401


def test_expired_r02_session_does_not_moderate(stack):
    civic, feedback, password, clock = stack
    cookie, csrf = login(civic, feedback, password)
    published = create_object(civic, feedback, cookie, csrf)
    call(civic, feedback, "POST", "/feedback", {"object_id": published["id"], "category": "roads",
                                                "consent_public": False,
                                                "text": "Яма на въезде во двор у ограждения."})
    clock.now += timedelta(hours=9)  # дольше абсолютного срока сессии R02
    decision = {"expected_revision": 1, "action": "approve", "reason": "Поздно"}
    result = call(civic, feedback, "POST", "/staff/feedback/1/moderate", decision, ctx(cookie, csrf))
    assert result["status"] == 401
