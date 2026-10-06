"""Модерация: права, CSRF, ревизии, публичная проекция, согласие, история, приватность."""

import json

import pytest

from r06_helpers import moderate, public_list, queue_items, staff, submit
from ui.civic_feedback.fixtures import (FIXTURE_EDITOR, FIXTURE_LOGGED_OUT, FIXTURE_RESIDENT,
                                        FIXTURE_SECOND_EDITOR, fixture_context)

XSS = '<img src=x onerror="alert(1)"><script>alert(2)</script> https://evil.example/?q=<b>'
PUBLIC_KEYS = {"id", "object_id", "kind", "kind_label", "category", "category_label", "text",
               "public_reply", "submitted_on", "published_at", "moderation_label",
               "official_registration", "history"}


def first_pending(service):
    item = queue_items(service)[0]
    return item["id"], item["revision"]


def public_items(service, object_id="demo-astana-work-01"):
    response = public_list(service, object_id)
    assert response["status"] == 200
    return response["body"]["data"]["items"]


def receipt_call(service, route, receipt_id, context=None):
    return service.handle("POST", f"/api/civic/v1/feedback/{route}", {}, {"receipt_id": receipt_id},
                          None, context or fixture_context())


# -------------------------------------------------------------------- access
def test_anonymous_cannot_read_queue_or_moderate(service):
    submit(service)
    assert staff(service, "GET", "/staff/feedback", principal=None)["status"] == 401
    assert staff(service, "GET", "/staff/feedback/1", principal=None)["status"] == 401
    response = moderate(service, "1", 1, principal=None)
    assert response["status"] == 401
    assert public_items(service) == []


def test_resident_role_cannot_moderate(service):
    submit(service)
    assert staff(service, "GET", "/staff/feedback", principal=FIXTURE_RESIDENT)["status"] == 403
    assert moderate(service, "1", 1, principal=FIXTURE_RESIDENT)["status"] == 403


@pytest.mark.parametrize("fake", [{"role": "editor"}, {"actor": "admin"}, {"principal": {"role": "admin"}},
                                  {"moderated_by": "boss"}])
def test_fake_role_in_body_gives_no_rights(service, fake):
    submit(service)
    body = {"expected_revision": 1, "action": "approve", "reason": "ok ok", **fake}
    anonymous = service.handle("POST", "/api/civic/v1/staff/feedback/1/moderate", {}, body, None,
                               fixture_context())
    assert anonymous["status"] == 401
    resident = service.handle("POST", "/api/civic/v1/staff/feedback/1/moderate", {}, body, FIXTURE_RESIDENT,
                              fixture_context(csrf=FIXTURE_RESIDENT["csrf_token"]))
    assert resident["status"] == 403
    # Даже у редактора поле роли/актора в теле отклоняется, а не принимается молча.
    editor = staff(service, "POST", "/staff/feedback/1/moderate", body)
    assert editor["status"] == 400 and editor["body"]["error"]["code"] == "unknown_fields"
    assert queue_items(service)[0]["moderation"] == "pending"


def test_logged_out_or_expired_editor_session_does_not_act(service, clock):
    submit(service)
    assert moderate(service, "1", 1, principal=FIXTURE_LOGGED_OUT)["status"] == 401
    expiring = dict(FIXTURE_EDITOR, expires_at="2026-10-07T09:30:00Z")
    clock.advance(hours=1)
    response = moderate(service, "1", 1, principal=expiring)
    assert response["status"] == 401 and response["body"]["error"]["code"] == "session_expired"
    assert queue_items(service)[0]["moderation"] == "pending"


def test_moderation_requires_csrf_and_same_origin(service):
    submit(service)
    body = {"expected_revision": 1, "action": "approve", "reason": "Проверено"}
    path = "/api/civic/v1/staff/feedback/1/moderate"
    no_token = service.handle("POST", path, {}, body, FIXTURE_EDITOR, fixture_context())
    wrong = service.handle("POST", path, {}, body, FIXTURE_EDITOR, fixture_context(csrf="guess"))
    foreign = service.handle("POST", path, {}, body, FIXTURE_EDITOR,
                             fixture_context(csrf=FIXTURE_EDITOR["csrf_token"], same_origin=False))
    other_editors_token = service.handle("POST", path, {}, body, FIXTURE_EDITOR,
                                         fixture_context(csrf=FIXTURE_SECOND_EDITOR["csrf_token"]))
    assert [r["status"] for r in (no_token, wrong, foreign, other_editors_token)] == [403] * 4
    # Адаптер R01/R02 может сам проверить CSRF и сообщить csrf_verified=True.
    verified = dict(fixture_context(), csrf_verified=True)
    assert service.handle("POST", path, {}, body, FIXTURE_EDITOR, verified)["status"] == 200


# ------------------------------------------------------------------ lifecycle
def test_approve_with_consent_publishes_allowlisted_card(service):
    submit(service)
    staff_id, revision = first_pending(service)
    response = moderate(service, staff_id, revision, public_reply="Спасибо, сообщение передано редакции платформы.")
    assert response["status"] == 200
    item = response["body"]["data"]["item"]
    assert item["moderation"] == "approved" and item["revision"] == revision + 1 and item["is_public"]
    cards = public_items(service)
    assert len(cards) == 1
    card = cards[0]
    assert set(card) == PUBLIC_KEYS
    assert card["official_registration"] is False
    assert card["public_reply"].startswith("Спасибо")
    assert [h["event"] for h in card["history"]] == ["published"]
    assert card["history"][0]["public_actor_label"] == "Модератор платформы"
    dumped = json.dumps(card, ensure_ascii=False)
    for private in ("fixture-editor", "Внутренняя причина", "127.0.0.1", "fbr_", "client"):
        assert private not in dumped


def test_reject_is_not_public(service):
    submit(service)
    staff_id, revision = first_pending(service)
    assert moderate(service, staff_id, revision, action="reject", reason="Оскорбительный текст")["status"] == 200
    assert public_items(service) == []


def test_approved_without_consent_never_public_even_with_reply(service):
    submit(service, consent_public=False)
    staff_id, revision = first_pending(service)
    response = moderate(service, staff_id, revision, public_reply="Ответ автору")
    assert response["status"] == 200 and response["body"]["data"]["item"]["is_public"] is False
    assert public_items(service) == []
    attempt = moderate(service, staff_id, revision + 1, public_text="Попытка опубликовать без согласия")
    assert attempt["status"] == 422 and attempt["body"]["error"]["code"] == "no_consent"


def test_withdrawn_consent_removes_public_card(service):
    receipt = submit(service)["body"]["data"]["receipt_id"]
    staff_id, revision = first_pending(service)
    moderate(service, staff_id, revision)
    assert len(public_items(service)) == 1
    withdrawn = receipt_call(service, "withdraw-consent", receipt)
    assert withdrawn["status"] == 200 and withdrawn["body"]["data"]["consent_public"] is False
    assert public_items(service) == []
    # Повторное одобрение не возвращает текст без согласия.
    current = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["item"]
    assert moderate(service, staff_id, current["revision"])["status"] == 200
    assert public_items(service) == []
    history = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["history"]
    assert "consent_withdrawn" in [h["action"] for h in history]


def test_receipt_status_and_bad_receipts(service):
    receipt = submit(service)["body"]["data"]["receipt_id"]
    status = receipt_call(service, "receipt", receipt)
    assert status["status"] == 200 and status["body"]["data"]["moderation"] == "pending"
    assert "text" not in status["body"]["data"]
    assert receipt_call(service, "receipt", "fbr_" + "A" * 24)["status"] == 404
    assert receipt_call(service, "receipt", "1")["status"] == 422
    assert receipt_call(service, "receipt", receipt, fixture_context(same_origin=False))["status"] == 403


def test_stale_revision_conflict(service):
    submit(service)
    staff_id, revision = first_pending(service)
    assert moderate(service, staff_id, revision)["status"] == 200
    stale = moderate(service, staff_id, revision, action="reject", reason="Поздно", principal=FIXTURE_SECOND_EDITOR)
    assert stale["status"] == 409
    assert stale["body"]["error"]["current_revision"] == revision + 1
    assert len(public_items(service)) == 1


@pytest.mark.parametrize("body,field", [
    ({"expected_revision": "1", "action": "approve", "reason": "ok ok"}, "expected_revision"),
    ({"expected_revision": True, "action": "approve", "reason": "ok ok"}, "expected_revision"),
    ({"expected_revision": 1, "action": "delete", "reason": "ok ok"}, "action"),
    ({"expected_revision": 1, "action": "approve", "reason": ""}, "reason"),
    ({"expected_revision": 1, "action": "approve"}, "reason"),
    ({"expected_revision": 1, "action": "approve", "reason": "ok ok", "public_reply": 5}, "public_reply"),
])
def test_moderation_body_validation(service, body, field):
    submit(service)
    response = staff(service, "POST", "/staff/feedback/1/moderate", body)
    assert response["status"] == 422 and field in response["body"]["error"]["fields"]


def test_unknown_message_is_404(service):
    assert staff(service, "GET", "/staff/feedback/999")["status"] == 404
    assert staff(service, "GET", "/staff/feedback/abc")["status"] == 404
    assert moderate(service, "999", 1)["status"] == 404


def test_audit_history_records_actor_reason_and_revisions(service):
    submit(service)
    staff_id, revision = first_pending(service)
    moderate(service, staff_id, revision, reason="Первое решение")
    moderate(service, staff_id, revision + 1, action="reject", reason="Пересмотрено: дубликат",
             principal=FIXTURE_SECOND_EDITOR)
    detail = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]
    actions = [(h["action"], h["actor"], h["revision"]) for h in detail["history"]]
    assert actions[0] == ("submitted", None, 1)
    assert ("approved", "fixture-editor", 2) in actions
    assert ("rejected", "fixture-editor-2", 3) in actions
    assert any(h["reason"] == "Пересмотрено: дубликат" for h in detail["history"])
    assert public_items(service) == []


# ------------------------------------------------------------------- privacy
def test_contact_data_blocks_publication_until_redacted(service):
    text = "Яма у подъезда, звоните +7 701 123 45 67 или пишите ivan@mail.kz, Иванов."
    submit(service, text=text)
    staff_id, revision = first_pending(service)
    detail = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["item"]
    assert {h["type"] for h in detail["personal_data_hints"]} >= {"phone", "email"}
    blocked = moderate(service, staff_id, revision)
    assert blocked["status"] == 422 and blocked["body"]["error"]["code"] == "personal_data_suspected"
    assert public_items(service) == []
    redacted = "Яма у подъезда, звоните [скрыто] или пишите [скрыто]."
    ok = moderate(service, staff_id, revision, public_text=redacted)
    assert ok["status"] == 200
    card = public_items(service)[0]
    assert card["text"] == redacted
    assert "701" not in json.dumps(card) and "ivan@" not in json.dumps(card)


def test_reply_cannot_quote_hidden_fragments(service):
    submit(service, text="Во дворе у дома Сейткали Иванова темно, звоните +7 701 123 45 67.")
    staff_id, revision = first_pending(service)
    public_text = "Во дворе темно, не работает освещение."
    leak = moderate(service, staff_id, revision, public_text=public_text,
                    public_reply="Сообщение от жителя дома Иванова учтено.")
    assert leak["status"] == 422 and leak["body"]["error"]["code"] == "reply_reveals_hidden_text"
    phone = moderate(service, staff_id, revision, public_text=public_text,
                     public_reply="Перезвоним на 87011234567")
    assert phone["status"] == 422
    fine = moderate(service, staff_id, revision, public_text=public_text,
                    public_reply="Спасибо, сообщение проверено модератором платформы.")
    assert fine["status"] == 200
    dumped = json.dumps(public_items(service), ensure_ascii=False)
    assert "Иванов" not in dumped and "701" not in dumped


def test_xss_payload_is_stored_and_returned_as_plain_text(service):
    submit(service, text=XSS)
    staff_id, revision = first_pending(service)
    moderate(service, staff_id, revision, public_reply=XSS)
    card = public_items(service)[0]
    # Сервер не превращает текст в HTML; безопасность показа обеспечивает textContent во фронтенде.
    assert card["text"] == XSS and card["public_reply"] == XSS


def test_public_list_for_draft_or_unknown_object_is_404(service):
    for object_id in ("demo-astana-draft-04", "no-such", "demo-other-city-06", "bad id!"):
        response = public_list(service, object_id)
        assert response["status"] == 404 and response["body"]["ok"] is False


def test_public_list_paginates(service):
    for n in range(3):
        submit(service, text=f"Сообщение {n}: прошу добавить скамейки у входа в сквер.", ip=f"10.1.0.{n}")
    for item in queue_items(service):
        moderate(service, item["id"], item["revision"])
    page = service.handle("GET", "/api/civic/v1/objects/demo-astana-work-01/feedback",
                          {"limit": ["2"]}, None, None, fixture_context())["body"]["data"]
    assert len(page["items"]) == 2 and page["next_cursor"] == "2"
    rest = service.handle("GET", "/api/civic/v1/objects/demo-astana-work-01/feedback",
                          {"limit": "2", "cursor": "2"}, None, None, fixture_context())["body"]["data"]
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None
    bad = service.handle("GET", "/api/civic/v1/objects/demo-astana-work-01/feedback",
                         {"limit": "1000"}, None, None, fixture_context())
    assert bad["status"] == 400


def test_queue_filters_and_counts(service):
    submit(service, category="lighting", text="Темно вечером у прохода, нет фонарей.")
    submit(service, category="roads", kind="suggestion", consent_public=False,
           text="Предлагаю сделать временный пандус для колясок.")
    response = staff(service, "GET", "/staff/feedback", query={"moderation": "all", "category": "lighting"})
    data = response["body"]["data"]
    assert [i["category"] for i in data["items"]] == ["lighting"]
    assert data["counts"] == {"pending": 2, "approved": 0, "rejected": 0}
    private = staff(service, "GET", "/staff/feedback", query={"consent": "false"})["body"]["data"]["items"]
    assert [i["kind"] for i in private] == ["suggestion"]
    assert staff(service, "GET", "/staff/feedback", query={"moderation": "weird"})["status"] == 400
    # Служебные антиспам-данные — только агрегат, без хэша/IP.
    dumped = json.dumps(data, ensure_ascii=False)
    assert "client_hash" not in dumped and "127.0.0.1" not in dumped and "receipt" not in dumped
