"""Round 12: статус обработки на платформе, заметки, дубли, категория сотрудника, поиск, миграция.

Статусы описывают работу сотрудников платформы, а не eOtinish/iKOMEK. Публичность по-прежнему
определяется только решением модерации + согласием автора.
"""

import json
import sqlite3

import pytest

from r06_helpers import moderate, public_list, staff, submit
from ui.civic_feedback import FeedbackService, HANDLING_LABELS
from ui.civic_feedback.fixtures import FIXTURE_EDITOR, FIXTURE_RESIDENT, fixture_context, fixture_object_lookup


def card(service, staff_id):
    response = staff(service, "GET", f"/staff/feedback/{staff_id}")
    assert response["status"] == 200, response
    return response["body"]["data"]


def act(service, staff_id, action, revision=None, **body):
    payload = {"action": action, **body}
    if revision is not None:
        payload["expected_revision"] = revision
    return staff(service, "POST", f"/staff/feedback/{staff_id}/moderate", payload)


def queue(service, **query):
    response = staff(service, "GET", "/staff/feedback", query=query)
    assert response["status"] == 200, response
    return response["body"]["data"]


def receipt(service, receipt_id):
    return service.handle("POST", "/api/civic/v1/feedback/receipt", {}, {"receipt_id": receipt_id}, None,
                          fixture_context())["body"]["data"]


def new_message(service, **overrides):
    response = submit(service, **overrides)
    assert response["status"] == 201, response
    item = queue(service, status="all", order="newest")["items"][0]
    return item["id"], response["body"]["data"]["receipt_id"]


# ------------------------------------------------------------------ workflow
def test_new_message_is_new_and_status_filter_works(service):
    staff_id, receipt_id = new_message(service)
    data = queue(service, status="new")
    assert [i["id"] for i in data["items"]] == [staff_id]
    item = data["items"][0]
    assert item["handling_status"] == "new" and item["handling_next"] == ["answered", "closed", "duplicate", "in_review"]
    assert data["handling_counts"]["new"] == 1 and data["filters"]["moderation"] == "all"
    assert receipt(service, receipt_id)["handling_label"] == HANDLING_LABELS["new"]
    # legacy default (без moderation/status) — очередь pending, как в civic-v1
    assert [i["id"] for i in queue(service)["items"]] == [staff_id]


def test_status_answer_flow_and_reply_rules(service):
    staff_id, receipt_id = new_message(service, consent_public=False)
    r = act(service, staff_id, "status", 1, status="in_review", reason="Взято в работу")
    assert r["status"] == 200 and r["body"]["data"]["item"]["handling_status"] == "in_review"
    assert r["body"]["data"]["item"]["moderation"] == "pending"          # публикация не тронута
    no_reply = act(service, staff_id, "status", 2, status="answered", reason="Ответили")
    assert no_reply["status"] == 422 and no_reply["body"]["error"]["code"] == "reply_required"
    ok = act(service, staff_id, "status", 2, status="answered", reason="Ответили",
             public_reply="Спасибо. Сообщение учтено редакцией платформы; сроки работ это не означает.")
    item = ok["body"]["data"]["item"]
    assert ok["status"] == 200 and item["handling_status"] == "answered" and item["handled_by"] == "fixture-editor"
    status = receipt(service, receipt_id)
    assert status["handling_status"] == "answered" and status["public_reply"].startswith("Спасибо")
    assert status["is_public"] is False                                   # нет согласия — не публично
    same = act(service, staff_id, "status", 3, status="answered", reason="Повтор")
    assert same["status"] == 422 and same["body"]["error"]["code"] == "no_change"


def test_invalid_transition_lists_allowed(service):
    staff_id, _ = new_message(service)
    assert act(service, staff_id, "status", 1, status="closed", reason="Вне темы платформы")["status"] == 200
    bad = act(service, staff_id, "status", 2, status="answered", reason="x x x",
              public_reply="Ответ платформы без обещаний.")
    assert bad["status"] == 422 and bad["body"]["error"]["code"] == "invalid_transition"
    assert bad["body"]["error"]["allowed"] == ["in_review"]
    assert act(service, staff_id, "status", 2, status="in_review", reason="Открыто снова")["status"] == 200


def test_approve_on_new_moves_to_in_review_or_answered(service):
    a, _ = new_message(service)
    b, _ = new_message(service, text="Нет освещения на пешеходном переходе у школы вечером.", category="lighting")
    assert moderate(service, a, 1)["body"]["data"]["item"]["handling_status"] == "in_review"
    item = moderate(service, b, 1, public_reply="Спасибо, сообщение опубликовано на платформе.")["body"]["data"]["item"]
    assert item["handling_status"] == "answered"
    closed = moderate(service, a, 2, action="reject", status="closed")["body"]["data"]["item"]
    assert closed["handling_status"] == "closed" and closed["moderation"] == "rejected"
    history = card(service, a)["history"]
    assert "handling_status" in history[-1]["changed_fields"]


def test_duplicate_linking_rules(service):
    original, _ = new_message(service)
    dup, dup_receipt = new_message(service, text="Опять нет прохода у ограждения, идём по дороге!",
                                   client_request_id=None)
    third, _ = new_message(service, text="Третье сообщение о том же проходе возле стройки.")
    missing = act(service, dup, "status", 1, status="duplicate", reason="Тот же проход")
    assert missing["status"] == 422 and "duplicate_of" in missing["body"]["error"]["fields"]
    self_link = act(service, dup, "status", 1, status="duplicate", duplicate_of=dup, reason="Тот же проход")
    assert self_link["status"] == 422
    ok = act(service, dup, "status", 1, status="duplicate", duplicate_of=original, reason="Тот же проход")
    assert ok["status"] == 200 and ok["body"]["data"]["item"]["duplicate_of"] == original
    chain = act(service, third, "status", 1, status="duplicate", duplicate_of=dup, reason="Тот же проход")
    assert chain["status"] == 422 and chain["body"]["error"]["code"] == "duplicate_chain"
    parent = act(service, original, "status", 1, status="duplicate", duplicate_of=third, reason="Наоборот")
    assert parent["status"] == 422 and parent["body"]["error"]["code"] == "has_duplicates"
    detail = card(service, original)
    assert [d["id"] for d in detail["duplicates"]] == [dup]
    assert card(service, dup)["duplicate_of"]["id"] == original
    # автор видит статус «объединено», но не номер чужого сообщения
    status = receipt(service, dup_receipt)
    assert status["handling_status"] == "duplicate" and "duplicate_of" not in status
    reopened = act(service, dup, "status", 2, status="in_review", reason="Ошибочно объединено")
    assert reopened["status"] == 200 and reopened["body"]["data"]["item"]["duplicate_of"] is None
    stray = act(service, third, "status", 1, status="in_review", duplicate_of=original, reason="x x x")
    assert stray["status"] == 422 and "duplicate_of" in stray["body"]["error"]["fields"]


def test_internal_note_is_private_and_keeps_revision(service):
    staff_id, receipt_id = new_message(service)
    secret = "Служебно: уточнить у подрядчика СЕКРЕТ-НОТА"
    r = act(service, staff_id, "note", internal_note=secret)
    assert r["status"] == 200 and r["body"]["data"]["item"]["revision"] == 1
    assert any(h["action"] == "note" and h["reason"] == secret for h in r["body"]["data"]["history"])
    moderate(service, staff_id, 1, public_reply="Спасибо, опубликовано на платформе.")
    public = json.dumps(public_list(service)["body"], ensure_ascii=False)
    assert "СЕКРЕТ" not in public and "fixture-editor" not in public
    assert "СЕКРЕТ" not in json.dumps(receipt(service, receipt_id), ensure_ascii=False)
    # без CSRF/прав заметку не добавить
    no_csrf = service.handle("POST", f"/api/civic/v1/staff/feedback/{staff_id}/moderate", {},
                             {"action": "note", "internal_note": "x"}, FIXTURE_EDITOR, fixture_context())
    assert no_csrf["status"] == 403
    resident = staff(service, "POST", f"/staff/feedback/{staff_id}/moderate",
                     {"action": "note", "internal_note": "x"}, principal=FIXTURE_RESIDENT)
    assert resident["status"] == 403
    empty = act(service, staff_id, "note", internal_note="   ")
    assert empty["status"] == 422 and "internal_note" in empty["body"]["error"]["fields"]


def test_recategorize_keeps_resident_category(service):
    staff_id, _ = new_message(service, category="roads")
    r = act(service, staff_id, "recategorize", 1, category="sidewalks", reason="Речь о тротуаре")
    item = r["body"]["data"]["item"]
    assert r["status"] == 200 and item["category"] == "roads" and item["staff_category"] == "sidewalks"
    assert [i["id"] for i in queue(service, status="all", category="sidewalks")["items"]] == [staff_id]
    assert queue(service, status="all", category="roads")["items"] == []
    same = act(service, staff_id, "recategorize", 2, category="sidewalks", reason="Повтор")
    assert same["status"] == 422
    back = act(service, staff_id, "recategorize", 2, category="roads", reason="Житель был прав")
    assert back["body"]["data"]["item"]["staff_category"] is None
    history = card(service, staff_id)["history"]
    assert [h["action"] for h in history].count("recategorized") == 2


@pytest.mark.parametrize("body,field", [
    ({"action": "note", "internal_note": "x", "status": "closed"}, "status"),
    ({"action": "status", "expected_revision": 1, "reason": "ok ok", "status": "closed", "public_text": "x" * 20}, "public_text"),
    ({"action": "status", "expected_revision": 1, "reason": "ok ok"}, "status"),
    ({"action": "status", "expected_revision": 1, "reason": "ok ok", "status": "done"}, "status"),
    ({"action": "recategorize", "expected_revision": 1, "reason": "ok ok", "category": "parks"}, "category"),
    ({"action": "status", "expected_revision": 1, "reason": "ok ok", "status": "duplicate", "duplicate_of": "abc"}, "duplicate_of"),
])
def test_action_field_validation(service, body, field):
    staff_id, _ = new_message(service)
    response = staff(service, "POST", f"/staff/feedback/{staff_id}/moderate", body)
    assert response["status"] == 422 and field in response["body"]["error"]["fields"], response


def test_status_change_is_revision_checked(service):
    staff_id, _ = new_message(service)
    assert act(service, staff_id, "status", 1, status="in_review", reason="Беру")["status"] == 200
    stale = act(service, staff_id, "status", 1, status="closed", reason="Закрываю")
    assert stale["status"] == 409 and stale["body"]["error"]["current_revision"] == 2


# --------------------------------------------------------------------- search
def test_queue_search_is_case_insensitive_cyrillic_and_by_number(service):
    a, _ = new_message(service, text="Сломан СВЕТИЛЬНИК у остановки «Байтерек».", category="lighting")
    b, _ = new_message(service, text="Яма на дороге возле перекрёстка, машины объезжают.", category="roads")
    assert [i["id"] for i in queue(service, status="all", q="светильник")["items"]] == [a]
    assert [i["id"] for i in queue(service, status="all", q="ПЕРЕКРЕСТКА")["items"]] == [b]   # ё = е
    assert [i["id"] for i in queue(service, status="all", q="#" + b)["items"]] == [b]
    assert staff(service, "GET", "/staff/feedback", query={"q": "x" * 101})["status"] == 400
    assert staff(service, "GET", "/staff/feedback", query={"status": "new,bogus"})["status"] == 400
    assert staff(service, "GET", "/staff/feedback", query={"order": "random"})["status"] == 400
    both = queue(service, status="new,in_review", order="newest")["items"]
    assert [i["id"] for i in both] == [b, a]


# ---------------------------------------------------------------- anti-spam
@pytest.mark.parametrize("text", ["!!!!!!!!!!!!!!!!", "1234567890 1234567890", "аааааааааааааа",
                                  "см http://a.example http://b.example http://c.example http://d.example ок"])
def test_garbage_or_link_spam_rejected_with_field_error(service, text):
    response = submit(service, text=text)
    assert response["status"] == 422 and "text" in response["body"]["error"]["fields"]


def test_normal_text_with_one_link_accepted(service):
    response = submit(service, text="Фото ямы выложено тут: https://example.org/photo — проверьте, пожалуйста.")
    assert response["status"] == 201


# ---------------------------------------------------------------- migration
V1_TABLE = """
CREATE TABLE feedback_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE feedback_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, public_id TEXT NOT NULL UNIQUE, receipt_id TEXT NOT NULL UNIQUE,
  city TEXT NOT NULL, object_id TEXT, lon REAL, lat REAL, kind TEXT NOT NULL, category TEXT NOT NULL,
  text TEXT NOT NULL, text_fingerprint TEXT NOT NULL, language TEXT NOT NULL,
  consent_public INTEGER NOT NULL CHECK (consent_public IN (0, 1)), consent_withdrawn_at TEXT,
  moderation TEXT NOT NULL CHECK (moderation IN ('pending', 'approved', 'rejected')),
  public_text TEXT, public_reply TEXT, moderation_reason TEXT, moderated_by TEXT, moderated_at TEXT,
  published_at TEXT, revision INTEGER NOT NULL CHECK (revision >= 1), created_at TEXT NOT NULL,
  created_ts REAL NOT NULL, updated_at TEXT NOT NULL, client_hash TEXT NOT NULL, client_request_id TEXT,
  duplicate_confirmed INTEGER NOT NULL DEFAULT 0, classifier_status TEXT NOT NULL DEFAULT 'not_run',
  classifier_json TEXT);
CREATE TABLE feedback_events (id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id INTEGER NOT NULL REFERENCES feedback_messages (id), revision INTEGER NOT NULL, at TEXT NOT NULL,
  action TEXT NOT NULL, actor_kind TEXT NOT NULL, actor TEXT, reason TEXT, changed_fields TEXT NOT NULL,
  is_public INTEGER NOT NULL DEFAULT 0);
INSERT INTO feedback_meta VALUES ('schema_version', 'civic-feedback-v1');
"""


def test_v1_database_is_migrated_without_losing_rows(tmp_path, clock):
    path = tmp_path / "old.sqlite3"
    db = sqlite3.connect(path)
    db.executescript(V1_TABLE)
    rows = [("pending", None), ("approved", "Ответ платформы"), ("rejected", None)]
    for i, (moderation, reply) in enumerate(rows, 1):
        db.execute("INSERT INTO feedback_messages (public_id, receipt_id, city, object_id, kind, category, text, "
                   "text_fingerprint, language, consent_public, moderation, public_reply, revision, created_at, "
                   "created_ts, updated_at, client_hash) VALUES (?, ?, 'astana', 'demo-astana-work-01', 'problem', "
                   "'roads', ?, 'fp', 'ru', 1, ?, ?, 1, '2026-10-01T00:00:00Z', 0, '2026-10-01T00:00:00Z', 'h')",
                   (f"fbp_{i}", f"fbr_old_receipt_{i:012d}", f"Старое сообщение номер {i} о дороге", moderation, reply))
    db.commit()
    db.close()
    svc = FeedbackService(path, fixture_object_lookup, clock)
    try:
        data = svc.handle("GET", "/api/civic/v1/staff/feedback", {"status": "all", "order": "oldest"}, None,
                          FIXTURE_EDITOR, fixture_context())["body"]["data"]
        assert [i["handling_status"] for i in data["items"]] == ["new", "answered", "closed"]
        assert [i["text"] for i in data["items"]][0] == "Старое сообщение номер 1 о дороге"
        assert svc.stats()["schema_version"] == "civic-feedback-v3"   # round 13: v1 -> v3 одним шагом
    finally:
        svc.close()
    # повторное открытие — миграция идемпотентна
    FeedbackService(path, fixture_object_lookup, clock).close()


# ------------------------------------------------- resend / reply invariants
def test_request_id_conflict_returns_previous_receipt_to_same_sender(service):
    first = submit(service, client_request_id="r12-request-0000000001")
    assert first["status"] == 201
    edited = submit(service, client_request_id="r12-request-0000000001",
                    text="Нет безопасного прохода вдоль ограждения, люди идут по проезжей части. Уточнение.")
    error = edited["body"]["error"]
    assert edited["status"] == 409 and error["code"] == "request_id_conflict"
    assert error["previous_receipt"]["receipt_id"] == first["body"]["data"]["receipt_id"]
    assert "text" not in error["previous_receipt"]            # квитанция без текста сообщения
    # round 13: тот же client_request_id после смены сети (другой IP) — та же форма, а не новый автор.
    other_network = submit(service, ip="10.0.0.9", client_request_id="r12-request-0000000001",
                           text="Совсем другое сообщение о яме на дороге возле остановки.")
    assert other_network["status"] == 409
    assert other_network["body"]["error"]["previous_receipt"]["receipt_id"] == first["body"]["data"]["receipt_id"]
    # Без client_request_id квитанция не выдаётся никому, даже с того же адреса (общий NAT).
    same_ip_no_id = submit(service, text="Нет безопасного прохода вдоль ограждения, люди идут по проезжей части.")
    assert same_ip_no_id["status"] == 409 and "previous_receipt" not in same_ip_no_id["body"]["error"]


def test_answered_reply_cannot_be_silently_removed(service):
    staff_id, _ = new_message(service)
    moderate(service, staff_id, 1, public_reply="Спасибо, сообщение учтено на платформе.")
    assert card(service, staff_id)["item"]["handling_status"] == "answered"
    removed = moderate(service, staff_id, 2, action="reject", public_reply=None)
    assert removed["status"] == 422 and removed["body"]["error"]["code"] == "reply_required"
    ok = moderate(service, staff_id, 2, action="reject", public_reply=None, status="in_review")
    assert ok["status"] == 200 and ok["body"]["data"]["item"]["public_reply"] is None


def test_fixture_classifier_is_labelled_and_never_decides(tmp_path, clock):
    from ui.civic_feedback.fixtures import broken_classifier, fixture_keyword_classifier
    svc = FeedbackService(tmp_path / "f.sqlite3", fixture_object_lookup, clock, classifier=fixture_keyword_classifier)
    try:
        submit(svc, category="roads", text="Не горят фонари, на дорожке темно вечером.")
        item = svc.handle("GET", "/api/civic/v1/staff/feedback", {"status": "all"}, None, FIXTURE_EDITOR,
                          fixture_context())["body"]["data"]["items"][0]
        suggestion = item["classifier"]["suggestion"]
        assert suggestion["label"] == "lighting" and "не модель R08" in suggestion["model_version"]
        assert suggestion["score_kind"] == "fixture_keyword_share" and suggestion["needs_review"] is True
        assert item["category"] == "roads" and item["staff_category"] is None   # подсказка не меняет категорию
    finally:
        svc.close()
    broken = FeedbackService(tmp_path / "b.sqlite3", fixture_object_lookup, clock, classifier=broken_classifier)
    try:
        assert submit(broken)["status"] == 201
        assert broken.stats()["classifier_status"] == {"error": 1}
    finally:
        broken.close()
