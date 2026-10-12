"""Round 13: изоляция посетителей, права на смену статуса, конфликт ревизий, привязка к объекту.

Объекты и учётные записи — FIXTURE; справочник объектов в тестах привязки — изменяемая копия
FIXTURE_OBJECTS (имитация архивации, удаления и изменения геометрии в R02).
"""

from copy import deepcopy
from datetime import timedelta
import json
import threading

import pytest

from r06_helpers import public_list, queue_items, staff, submit
from ui.civic_feedback import FeedbackService
from ui.civic_feedback.fixtures import (FIXTURE_EDITOR, FIXTURE_LOGGED_OUT, FIXTURE_OBJECTS, FIXTURE_RESIDENT,
                                        FIXTURE_SECOND_EDITOR, fixture_context)

OBJECT_ID = "demo-astana-work-01"


def receipt(service, receipt_id, ip="198.51.100.5"):
    return service.handle("POST", "/api/civic/v1/feedback/receipt", {}, {"receipt_id": receipt_id}, None,
                          fixture_context(ip))


def latest_id(service):
    return max(queue_items(service, moderation="all"), key=lambda item: int(item["id"]))["id"]


def change(service, staff_id, revision, status, principal=FIXTURE_EDITOR, context=None, **extra):
    body = dict({"expected_revision": revision, "action": "status", "status": status,
                 "reason": "Проверка доступа R06"}, **extra)
    return staff(service, "POST", f"/staff/feedback/{staff_id}/moderate", body, principal=principal,
                 context=context)


# ---------------------------------------------------------------- visitors
def test_two_visitors_do_not_see_each_others_service_data(service):
    a = submit(service, ip="203.0.113.10", text="Посетитель А: яма на въезде, машины объезжают по тротуару.",
               client_request_id="aaaa1111-2222-4333-8444-555566667777")["body"]["data"]
    b = submit(service, ip="203.0.113.10", text="Посетитель Б: тёмный проход у остановки, не горит фонарь.",
               consent_public=False, client_request_id="bbbb1111-2222-4333-8444-555566667777")["body"]["data"]
    ids = sorted(queue_items(service, moderation="all"), key=lambda item: int(item["id"]))
    staff(service, "POST", f"/staff/feedback/{ids[0]['id']}/moderate",
          {"action": "note", "internal_note": "Служебно о посетителе А"})
    change(service, ids[1]["id"], 1, "answered", public_reply="Ответ только для посетителя Б.")

    seen_a = receipt(service, a["receipt_id"])["body"]["data"]
    seen_b = receipt(service, b["receipt_id"])["body"]["data"]
    assert seen_a["receipt_id"] == a["receipt_id"] and seen_b["receipt_id"] == b["receipt_id"]
    assert seen_a["public_reply"] is None and seen_b["public_reply"] == "Ответ только для посетителя Б."
    for payload in (a, b, seen_a, seen_b):
        dumped = json.dumps(payload, ensure_ascii=False)
        for forbidden in ("Служебно", "Посетитель", "client_hash", "client_request_id", "fixture-editor",
                          "aaaa1111", "bbbb1111", "public_id"):
            assert forbidden not in dumped, (forbidden, payload)
    assert a["receipt_id"] not in json.dumps(seen_b) and b["receipt_id"] not in json.dumps(seen_a)
    # Публично (до одобрения) — ничего; служебные списки без прав — 401/403.
    assert public_list(service)["body"]["data"]["items"] == []
    assert staff(service, "GET", "/staff/feedback", principal=None)["status"] == 401
    assert staff(service, "GET", f"/staff/feedback/{ids[0]['id']}", principal=FIXTURE_RESIDENT)["status"] == 403
    for number in range(1, 4):   # последовательные номера без прав ничего не открывают
        assert staff(service, "GET", f"/staff/feedback/{number}", principal=FIXTURE_LOGGED_OUT)["status"] == 401


def test_public_projection_has_no_service_fields(service):
    submit(service, text="Нет прохода вдоль ограждения у школы, дети идут по дороге.")
    staff_id = latest_id(service)
    staff(service, "POST", f"/staff/feedback/{staff_id}/moderate",
          {"action": "note", "internal_note": "Служебная заметка, не для публики"})
    change(service, staff_id, 1, "in_review")
    staff(service, "POST", f"/staff/feedback/{staff_id}/moderate",
          {"expected_revision": 2, "action": "approve", "reason": "Причина для сотрудников"})
    item = public_list(service)["body"]["data"]["items"][0]
    assert set(item) == {"id", "object_id", "kind", "kind_label", "category", "category_label", "text",
                         "public_reply", "submitted_on", "published_at", "moderation_label", "handling_status",
                         "handling_label", "official_registration", "history"}
    dumped = json.dumps(item, ensure_ascii=False)
    for forbidden in ("Служебная", "Причина для", "fixture-editor", "receipt", "client", "classifier"):
        assert forbidden not in dumped
    assert not item["id"].isdigit()   # публичный id случайный, не порядковый номер


# ---------------------------------------------------------------- permissions
@pytest.mark.parametrize("principal,context,status,code", [
    (None, None, 401, "unauthenticated"),
    (FIXTURE_LOGGED_OUT, None, 401, "unauthenticated"),
    (FIXTURE_RESIDENT, None, 403, "forbidden"),
    (FIXTURE_EDITOR, fixture_context(), 403, "csrf_failed"),                       # нет CSRF
    (FIXTURE_EDITOR, fixture_context(csrf="wrong-token"), 403, "csrf_failed"),
    (FIXTURE_EDITOR, fixture_context(csrf=FIXTURE_EDITOR["csrf_token"], same_origin=False), 403, "cross_origin"),
    (dict(FIXTURE_EDITOR, expires_at=0), None, 401, "session_expired"),
])
def test_unauthorized_status_change_changes_nothing(service, principal, context, status, code):
    submit(service)
    staff_id = latest_id(service)
    result = change(service, staff_id, 1, "closed", principal=principal, context=context)
    assert result["status"] == status and result["body"]["error"]["code"] == code
    item = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["item"]
    assert item["handling_status"] == "new" and item["revision"] == 1


def test_moderator_session_loss_then_relogin(service, clock):
    submit(service)
    staff_id = latest_id(service)
    expired = dict(FIXTURE_EDITOR, expires_at=(clock() - timedelta(seconds=1)).timestamp())
    lost = change(service, staff_id, 1, "answered", principal=expired, public_reply="Ответ после истечения сессии")
    assert lost["status"] == 401 and lost["body"]["error"]["code"] == "session_expired"
    assert "не выполнено" in lost["body"]["error"]["message"]
    # После повторного входа то же действие с той же ревизией проходит: частичного сохранения не было.
    fresh = dict(FIXTURE_EDITOR, expires_at=(clock() + timedelta(hours=1)).timestamp())
    again = change(service, staff_id, 1, "answered", principal=fresh, public_reply="Ответ после истечения сессии")
    assert again["status"] == 200 and again["body"]["data"]["item"]["revision"] == 2


# ---------------------------------------------------------------- conflicts
def test_concurrent_editors_get_conflict_with_current_state(service):
    submit(service)
    staff_id = latest_id(service)
    first = change(service, staff_id, 1, "in_review")
    assert first["status"] == 200
    second = change(service, staff_id, 1, "answered", principal=FIXTURE_SECOND_EDITOR,
                    context=fixture_context(csrf=FIXTURE_SECOND_EDITOR["csrf_token"]),
                    public_reply="Ответ второго сотрудника")
    assert second["status"] == 409
    error = second["body"]["error"]
    assert error["code"] == "stale_revision" and error["current_revision"] == 2
    current = error["current"]
    assert current["handling_status"] == "in_review" and current["public_reply"] is None
    assert current["last_action"]["action"] == "status_changed" and current["last_action"]["actor"] == "fixture-editor"
    item = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["item"]
    assert item["handling_status"] == "in_review" and item["public_reply"] is None    # ничего не перезаписано
    retry = change(service, staff_id, 2, "answered", principal=FIXTURE_SECOND_EDITOR,
                   context=fixture_context(csrf=FIXTURE_SECOND_EDITOR["csrf_token"]),
                   public_reply="Ответ второго сотрудника")
    assert retry["status"] == 200


def test_parallel_threads_only_one_wins(service):
    submit(service)
    staff_id = latest_id(service)
    results = []
    barrier = threading.Barrier(8)

    def worker(number):
        barrier.wait()
        results.append(change(service, staff_id, 1, "answered", public_reply=f"Ответ потока {number}")["status"])

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200] + [409] * 7
    detail = staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]
    assert detail["item"]["revision"] == 2 and len([h for h in detail["history"] if h["action"] == "status_changed"]) == 1


def test_two_service_instances_on_one_database(tmp_path, clock):
    """Два процесса/воркера на одной SQLite: BEGIN IMMEDIATE + ревизия не дают тихой перезаписи."""
    objects = deepcopy(FIXTURE_OBJECTS)
    path = tmp_path / "shared.sqlite3"
    one = FeedbackService(path, objects.get, clock)
    two = FeedbackService(path, objects.get, clock)
    try:
        submit(one)
        staff_id = latest_id(one)
        assert change(one, staff_id, 1, "in_review")["status"] == 200
        assert change(two, staff_id, 1, "closed")["status"] == 409
        assert staff(two, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["item"]["handling_status"] == "in_review"
    finally:
        one.close()
        two.close()


# ---------------------------------------------------------------- object binding
@pytest.fixture
def mutable(tmp_path, clock):
    objects = deepcopy(FIXTURE_OBJECTS)
    svc = FeedbackService(tmp_path / "binding.sqlite3", lambda object_id: deepcopy(objects.get(object_id)), clock)
    yield svc, objects
    svc.close()


def binding(service, staff_id):
    return staff(service, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]["object_binding"]


def test_binding_unchanged_object(mutable):
    svc, objects = mutable
    receipt_id = submit(svc)["body"]["data"]["receipt_id"]
    result = binding(svc, latest_id(svc))
    assert result["state"] == "published" and result["changed_since_submit"] is False
    assert result["submitted_revision"] == 2 and result["warnings"] == []
    assert "object_note" not in receipt(svc, receipt_id)["body"]["data"]


@pytest.mark.parametrize("publication", ["archived", "draft"])
def test_object_hidden_after_submission(mutable, publication):
    svc, objects = mutable
    receipt_id = submit(svc)["body"]["data"]["receipt_id"]
    staff_id = latest_id(svc)
    objects[OBJECT_ID].update(publication=publication, revision=3)
    result = binding(svc, staff_id)
    assert result["state"] == "not_public" and result["changed_since_submit"] is True
    assert any("не опубликован" in warning for warning in result["warnings"])
    # Сообщение остаётся у сотрудника; публичный список объекта закрыт; автор видит нейтральную пометку.
    assert public_list(svc)["status"] == 404
    note = receipt(svc, receipt_id)["body"]["data"]["object_note"]
    assert "не показывается на карте" in note and publication not in note
    approved = staff(svc, "POST", f"/staff/feedback/{staff_id}/moderate",
                     {"expected_revision": 1, "action": "approve", "reason": "Проверено"})
    assert approved["status"] == 200 and approved["body"]["data"]["warnings"]


def test_object_deleted_after_submission(mutable):
    svc, objects = mutable
    receipt_id = submit(svc)["body"]["data"]["receipt_id"]
    staff_id = latest_id(svc)
    del objects[OBJECT_ID]
    result = binding(svc, staff_id)
    assert result["state"] == "missing" and result["object_id"] == OBJECT_ID
    assert result["submitted_title"] == FIXTURE_OBJECTS[OBJECT_ID]["title"]   # что видел житель
    detail = staff(svc, "GET", f"/staff/feedback/{staff_id}")["body"]["data"]
    assert detail["item"]["object_id"] == OBJECT_ID and detail["object"]["available"] is False
    assert receipt(svc, receipt_id)["body"]["data"]["object_note"]


def test_geometry_changed_after_submission(mutable):
    svc, objects = mutable
    submit(svc, object_id=None, geometry={"type": "Point", "coordinates": [71.4301, 51.1701]})
    submit(svc, ip="10.2.2.2", text="Нет прохода у ограждения возле объекта ремонта, обход по дороге.",
           geometry={"type": "Point", "coordinates": [71.4302, 51.1702]})
    staff_id = latest_id(svc)
    objects[OBJECT_ID].update(geometry={"type": "Point", "coordinates": [71.50, 51.20]}, revision=3,
                              updated_at="2026-10-08T12:00:00+06:00")
    result = binding(svc, staff_id)
    assert result["geometry_changed"] is True and result["current_revision"] == 3
    assert result["point_distance_m"] > 1500
    assert any("Геометрия объекта изменена" in w for w in result["warnings"])
    assert any("км от геометрии" in w for w in result["warnings"])


def test_lookup_failure_and_old_rows_are_reported_as_unknown(mutable):
    svc, objects = mutable
    submit(svc)
    staff_id = latest_id(svc)
    with svc._lock:
        svc._db.execute("UPDATE feedback_messages SET object_snapshot = NULL, object_revision = NULL")
    result = binding(svc, staff_id)
    assert result["changed_since_submit"] is None and result["geometry_changed"] is None   # неизвестно, не «нет»

    def broken(object_id):
        raise RuntimeError("R02 недоступен")
    svc.object_lookup = broken
    result = binding(svc, staff_id)
    assert result["state"] == "lookup_failed" and result["warnings"]
