"""Round 13: квитанция автора (статус, ответ, хронология) и жизненный цикл обработки.

Сценарий житель -> сотрудник -> ответ -> квитанция; переходы new -> in_review -> answered ->
closed, дубль и отмена ошибочного решения; даты и история после перезапуска сервиса.
БД — временный файл pytest; объекты и учётные записи — FIXTURE (ui/civic_feedback/fixtures.py).
"""

import json

from r06_helpers import moderate, public_list, queue_items, staff, submit
from ui.civic_feedback import FeedbackService
from ui.civic_feedback.fixtures import (FIXTURE_EDITOR, FIXTURE_SECOND_EDITOR, fixture_context,
                                        fixture_object_lookup)

NOTE = "Служебно: звонили в КСК, ответа нет"
REASON = "Внутренняя причина: проверено по фото"


def receipt_status(service, receipt_id, context=None):
    return service.handle("POST", "/api/civic/v1/feedback/receipt", {}, {"receipt_id": receipt_id}, None,
                          context or fixture_context("192.0.2.77"))


def new_message(service, **body):
    response = submit(service, **body)
    assert response["status"] == 201, response
    item = max(queue_items(service, moderation="all"), key=lambda entry: int(entry["id"]))
    return item["id"], response["body"]["data"]["receipt_id"]


def status_change(service, staff_id, revision, status, principal=FIXTURE_EDITOR, **extra):
    return staff(service, "POST", f"/staff/feedback/{staff_id}/moderate",
                 dict({"expected_revision": revision, "action": "status", "status": status, "reason": REASON}, **extra),
                 principal=principal)


def test_resident_staff_reply_receipt_scenario(service, clock):
    staff_id, receipt_id = new_message(service, consent_public=False)
    first = receipt_status(service, receipt_id)["body"]["data"]
    assert first["handling_status"] == "new" and first["public_reply"] is None
    assert [entry["event"] for entry in first["timeline"]] == ["submitted"]

    clock.advance(minutes=5)
    assert status_change(service, staff_id, 1, "in_review")["status"] == 200
    staff(service, "POST", f"/staff/feedback/{staff_id}/moderate", {"action": "note", "internal_note": NOTE})
    clock.advance(hours=2)
    answered = status_change(service, staff_id, 2, "answered",
                             public_reply="Сообщение передано модератору района на платформе.")
    assert answered["status"] == 200, answered

    data = receipt_status(service, receipt_id)["body"]["data"]
    assert data["handling_status"] == "answered"
    assert data["public_reply"] == "Сообщение передано модератору района на платформе."
    assert data["is_public"] is False                        # нет согласия: ответ виден только по квитанции
    labels = [entry["label"] for entry in data["timeline"]]
    assert labels[0] == "Сообщение получено платформой"
    assert "Статус: На рассмотрении у сотрудника платформы" in labels
    assert "Статус: Дан ответ платформы" in labels and "Ответ платформы обновлён" in labels
    assert data["timeline"][-1]["at"] == "2026-10-07T11:05:00Z"
    dumped = json.dumps(data, ensure_ascii=False)
    for secret in (NOTE, REASON, "fixture-editor", "client_hash", "moderation_reason", "revision", '"id"'):
        assert secret not in dumped, secret
    # Публично сообщение не видно: нет согласия и нет решения о публикации.
    assert public_list(service)["body"]["data"]["items"] == []


def test_lifecycle_closed_reopen_and_restart_keep_history(tmp_path, clock):
    path = tmp_path / "restart.sqlite3"
    svc = FeedbackService(path, fixture_object_lookup, clock)
    try:
        staff_id, receipt_id = new_message(svc)
        assert status_change(svc, staff_id, 1, "in_review")["status"] == 200
        clock.advance(minutes=10)
        assert status_change(svc, staff_id, 2, "answered", public_reply="Ответ платформы: передано.")["status"] == 200
        clock.advance(minutes=10)
        assert status_change(svc, staff_id, 3, "closed")["status"] == 200
        # Ошибочно закрыто -> вернуть в работу можно только через in_review.
        wrong = status_change(svc, staff_id, 4, "answered", public_reply="Новый ответ")
        assert wrong["status"] == 422 and wrong["body"]["error"]["code"] == "invalid_transition"
        assert wrong["body"]["error"]["allowed"] == ["in_review"]
        clock.advance(minutes=10)
        reopened = status_change(svc, staff_id, 4, "in_review", reason="Закрыто по ошибке, возвращаем")
        assert reopened["status"] == 200 and reopened["body"]["data"]["item"]["handling_status"] == "in_review"
        before = staff(svc, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]
        receipt_before = receipt_status(svc, receipt_id)["body"]["data"]
    finally:
        svc.close()

    restarted = FeedbackService(path, fixture_object_lookup, clock)
    try:
        after = staff(restarted, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]
        assert after["history"] == before["history"]
        assert after["item"]["created_at"] == before["item"]["created_at"] == "2026-10-07T09:00:00Z"
        assert after["item"]["handled_at"] == "2026-10-07T09:30:00Z"
        assert [h["handling_after"] for h in after["history"] if h["action"] == "status_changed"] == \
            ["in_review", "answered", "closed", "in_review"]
        receipt_after = receipt_status(restarted, receipt_id)["body"]["data"]
        assert receipt_after == receipt_before
        assert receipt_after["public_reply"] == "Ответ платформы: передано."   # ответ сохранился после reopen
    finally:
        restarted.close()


def test_duplicate_and_undo_hide_target_from_author(service):
    original_id, _ = new_message(service)
    dup_id, dup_receipt = new_message(service, ip="10.1.1.1",
                                      text="Нет прохода у ограждения, пешеходы выходят на проезжую часть.")
    marked = status_change(service, dup_id, 1, "duplicate", duplicate_of=original_id)
    assert marked["status"] == 200 and marked["body"]["data"]["item"]["duplicate_of"] == original_id
    data = receipt_status(service, dup_receipt)["body"]["data"]
    assert data["handling_status"] == "duplicate" and data["handling_label"] == "Объединено с похожим сообщением"
    dumped = json.dumps(data, ensure_ascii=False)
    assert "duplicate_of" not in dumped and f"#{original_id}" not in dumped
    # Ошибочная отметка дубля отменяется через in_review: ссылка на исходное снимается.
    undone = status_change(service, dup_id, 2, "in_review", reason="Это другой участок, не дубль")
    assert undone["status"] == 200 and undone["body"]["data"]["item"]["duplicate_of"] is None
    assert receipt_status(service, dup_receipt)["body"]["data"]["handling_status"] == "in_review"


def test_erroneous_publication_can_be_reverted(service):
    staff_id, receipt_id = new_message(service)
    assert moderate(service, staff_id, 1, action="approve")["status"] == 200
    assert len(public_list(service)["body"]["data"]["items"]) == 1
    reverted = moderate(service, staff_id, 2, action="reject", reason="Опубликовано по ошибке: в тексте адрес")
    assert reverted["status"] == 200
    assert public_list(service)["body"]["data"]["items"] == []
    data = receipt_status(service, receipt_id)["body"]["data"]
    assert data["moderation"] == "rejected" and data["is_public"] is False
    assert [e["label"] for e in data["timeline"] if e["event"] == "moderation"] == [
        "Проверено модератором платформы", "Отклонено модератором платформы"]


def test_reply_and_note_are_separate_fields_and_reply_is_checked(service):
    staff_id, receipt_id = new_message(service)
    note = staff(service, "POST", f"/staff/feedback/{staff_id}/moderate", {"action": "note", "internal_note": NOTE})
    assert note["status"] == 200 and note["body"]["data"]["item"]["public_reply"] is None
    leaked = status_change(service, staff_id, 1, "answered", public_reply="Позвоните +7 701 555 44 33")
    assert leaked["status"] == 422 and leaked["body"]["error"]["code"] == "personal_data_suspected"
    ok = moderate(service, staff_id, 1, public_reply="Спасибо, сообщение рассмотрено на платформе.")
    assert ok["status"] == 200
    public = public_list(service)["body"]["data"]["items"][0]
    assert public["public_reply"] == "Спасибо, сообщение рассмотрено на платформе."
    for payload in (public, receipt_status(service, receipt_id)["body"]["data"]):
        assert NOTE not in json.dumps(payload, ensure_ascii=False)


def test_receipt_errors_do_not_leak(service):
    staff_id, receipt_id = new_message(service)
    missing = receipt_status(service, "fbr_" + "A" * 24)
    assert missing["status"] == 404 and missing["body"]["error"]["code"] == "receipt_not_found"
    for bad in ("1", str(staff_id), "fbr_short", receipt_id + "' OR 1=1 --"):
        assert receipt_status(service, bad)["status"] == 422
    cross = receipt_status(service, receipt_id, fixture_context(same_origin=False))
    assert cross["status"] == 403
    # Квитанция — только тело POST: в URL (логи, Referer) номер не принимается.
    in_url = service.handle("GET", f"/api/civic/v1/feedback/receipt?receipt_id={receipt_id}", None, None, None,
                            fixture_context())
    assert in_url["status"] == 405


def test_second_editor_sees_first_editors_actions_in_history(service):
    staff_id, _ = new_message(service)
    assert status_change(service, staff_id, 1, "in_review")["status"] == 200
    detail = staff(service, "GET", f"/staff/feedback/{staff_id}", principal=FIXTURE_SECOND_EDITOR)["body"]["data"]
    entry = [h for h in detail["history"] if h["action"] == "status_changed"][0]
    assert entry["actor"] == "fixture-editor" and entry["reason"] == REASON


def test_classifier_thread_failure_still_saves_message(tmp_path, clock, monkeypatch):
    import threading

    svc = FeedbackService(tmp_path / "thread.sqlite3", fixture_object_lookup, clock,
                          classifier=lambda text, language: {"label": "roads"})

    def no_threads(self):
        raise RuntimeError("can't start new thread")
    monkeypatch.setattr(threading.Thread, "start", no_threads)
    try:
        response = submit(svc)
        assert response["status"] == 201 and response["body"]["data"]["receipt_id"].startswith("fbr_")
        item = queue_items(svc, moderation="all")[0]
        assert item["classifier"]["status"] == "error" and item["category"] == "sidewalks"
        assert svc._classifier_inflight == 0
    finally:
        monkeypatch.undo()
        svc.close()
