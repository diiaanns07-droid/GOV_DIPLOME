"""R13 · «Вопрос акиму» (волна 2 п. 9): сервис ui/civic_qa — правила, модерация, голоса, приватность, демо.

Запуск: python -m pytest -q tests/civic/R13/qa
Через шлюз R01 (если в сборке есть маршруты qa.*) — test_gateway_*; без патча R01 они пропускаются.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from ui.civic_qa import make_service
from ui.civic_qa.service import pii_kinds, week_bounds

P = "/api/civic/v2"
CTX = {"headers": {}, "host_allowed": True, "is_same_origin": True, "client_ip": "127.0.0.1"}
DEV_A, DEV_B = "dev-aaaaaaaa-0001", "dev-bbbbbbbb-0002"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class Staff:
    """Как Principal R02: username, role, is_staff, check_csrf."""

    def __init__(self, staff=True, token="tok-123"):
        self.username, self.role, self.is_staff, self._token = "editor.one", "editor" if staff else "viewer", staff, token

    def check_csrf(self, value):
        return value == self._token


STAFF_CTX = dict(CTX, headers={"x-csrf-token": "tok-123"})


@pytest.fixture
def clock():
    return Clock(datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc))  # понедельник, 11:00 в Астане


@pytest.fixture
def svc(tmp_path, clock):
    return make_service(str(tmp_path / "civic.sqlite3"), clock=clock, demo=False)


@pytest.fixture
def demo(tmp_path, clock):
    return make_service(str(tmp_path / "demo.sqlite3"), clock=clock, demo=True)


def call(svc, method, path, body=None, query="", principal=None, ctx=None):
    reply = svc.handle(method, P + path, query, body, principal, ctx or CTX)
    return reply["status"], reply["body"]


def ask(svc, text="Когда починят фонари на нашей улице?", district="nura", device=DEV_A, **extra):
    return call(svc, "POST", "/questions", dict({"text": text, "district": district, "device_id": device}, **extra))


def publish(svc, qid):
    status, body = call(svc, "POST", f"/questions/{qid}/publish", {}, principal=Staff(), ctx=STAFF_CTX)
    assert status == 200, body
    return body["question"]


# ---------------------------------------------------------------- вопрос жителя
def test_new_question_waits_for_moderation_and_is_not_public(svc):
    status, body = ask(svc)
    assert status == 201 and body["question"]["status"] == "pending"
    for tab in ("top", "new", "answered"):
        _s, page = call(svc, "GET", "/questions", query=f"tab={tab}")
        assert page["items"] == [] and page["counts"]["new"] == 0


@pytest.mark.parametrize("body, field", [
    ({"text": "Коротко", "district": "nura"}, "text"),
    ({"text": "х" * 301, "district": "nura"}, "text"),
    ({"text": "Когда починят фонари на улице?", "district": ""}, "district"),
    ({"text": "Когда починят фонари на улице?", "district": "moscow"}, "district"),
    ({"text": None, "district": "nura"}, "text"),
])
def test_question_validation_names_the_field(svc, body, field):
    status, reply = call(svc, "POST", "/questions", dict(body, device_id=DEV_A))
    assert status == 422 and reply["field"] == field


def test_question_needs_device_id(svc):
    status, reply = call(svc, "POST", "/questions", {"text": "Когда починят фонари на улице?", "district": "nura"})
    assert status == 400 and reply["field"] == "device_id"


def test_text_is_cleaned_but_kept(svc):
    status, body = ask(svc, text="  Когда   уберут\r\n\r\n\r\n\r\nснег\tво дворе?  ")
    q = publish(svc, body["question"]["id"])
    assert q["text"] == "Когда уберут\n\nснег во дворе?"


def test_same_request_id_does_not_duplicate(svc):
    s1, b1 = ask(svc, request_id="req-00000001")
    s2, b2 = ask(svc, request_id="req-00000001")
    assert (s1, s2) == (201, 200) and b1["question"]["id"] == b2["question"]["id"] and b2["created"] is False
    _s, staff = call(svc, "GET", "/questions/staff", query="tab=queue", principal=Staff(), ctx=STAFF_CTX)
    assert staff["counts"]["queue"] == 1


def test_device_cannot_flood_the_queue(svc):
    for i in range(3):
        assert ask(svc, text=f"Вопрос номер {i} про двор и парковку")[0] == 201
    status, body = ask(svc, text="Ещё один вопрос про двор и парковку")
    assert status == 409 and body["error"] == "too_many"
    assert ask(svc, device=DEV_B)[0] == 201  # другое устройство — можно


def test_author_supports_own_question_after_publication(svc):
    _s, body = ask(svc)
    publish(svc, body["question"]["id"])
    _s, page = call(svc, "GET", "/questions", query=f"tab=top&device_id={DEV_A}")
    assert page["items"][0]["votes"] == 1 and page["items"][0]["my_vote"] is True
    _s, other = call(svc, "GET", "/questions", query=f"tab=top&device_id={DEV_B}")
    assert other["items"][0]["my_vote"] is False


# ---------------------------------------------------------------- голоса
def test_one_vote_per_device(svc):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    publish(svc, qid)
    s1, v1 = call(svc, "POST", f"/questions/{qid}/vote", {"device_id": DEV_B})
    s2, v2 = call(svc, "POST", f"/questions/{qid}/vote", {"device_id": DEV_B})
    assert (s1, s2) == (200, 200) and v1["votes"] == v2["votes"] == 2 and v1["created"] and not v2["created"]


def test_device_header_counts_as_the_same_device(svc):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    publish(svc, qid)
    call(svc, "POST", f"/questions/{qid}/vote", {"device_id": DEV_B})
    _s, v = call(svc, "POST", f"/questions/{qid}/vote", {}, ctx=dict(CTX, headers={"x-birge-device": DEV_B}))
    assert v["votes"] == 2 and v["created"] is False


def test_cannot_vote_for_pending_rejected_or_answered(svc):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    assert call(svc, "POST", f"/questions/{qid}/vote", {"device_id": DEV_B})[0] == 404  # ещё на проверке
    publish(svc, qid)
    call(svc, "POST", f"/questions/{qid}/answer", {"answer_ru": "Фонари заменят до конца месяца."},
         principal=Staff(), ctx=STAFF_CTX)
    status, reply = call(svc, "POST", f"/questions/{qid}/vote", {"device_id": DEV_B})
    assert status == 409 and reply["error"] == "answered"
    assert call(svc, "POST", "/questions/q-nonexistent/vote", {"device_id": DEV_B})[0] == 404


def test_vote_from_foreign_site_is_refused(svc):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    publish(svc, qid)
    status, _ = call(svc, "POST", f"/questions/{qid}/vote", {"device_id": DEV_B}, ctx=dict(CTX, is_same_origin=False))
    assert status == 403


def test_device_ids_are_stored_hashed(tmp_path, clock):
    db = tmp_path / "hash.sqlite3"
    svc = make_service(str(db), clock=clock, demo=False)
    _s, body = ask(svc)
    publish(svc, body["question"]["id"])
    call(svc, "POST", f"/questions/{body['question']['id']}/vote", {"device_id": DEV_B})
    for path in tmp_path.iterdir():
        raw = path.read_bytes()
        assert DEV_A.encode() not in raw and DEV_B.encode() not in raw, path.name


# ---------------------------------------------------------------- сотрудник
@pytest.mark.parametrize("principal, ctx, status", [
    (None, STAFF_CTX, 401),
    (Staff(staff=False), STAFF_CTX, 403),
    (Staff(), CTX, 403),                                   # нет X-CSRF-Token
    (Staff(), dict(STAFF_CTX, is_same_origin=False), 403),  # чужой сайт
    (Staff(), dict(STAFF_CTX, host_allowed=False), 403),
])
def test_moderation_needs_staff_session_csrf_and_own_origin(svc, principal, ctx, status):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    assert call(svc, "POST", f"/questions/{qid}/publish", {}, principal=principal, ctx=ctx)[0] == status
    assert call(svc, "POST", f"/questions/{qid}/reject", {"reason": "rude"}, principal=principal, ctx=ctx)[0] == status


def test_staff_list_needs_staff_but_not_csrf(svc):
    assert call(svc, "GET", "/questions/staff", query="tab=queue")[0] == 401
    assert call(svc, "GET", "/questions/staff", query="tab=queue", principal=Staff(), ctx=CTX)[0] == 200


def test_reject_needs_a_reason_and_hides_question(svc):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    publish(svc, qid)
    status, reply = call(svc, "POST", f"/questions/{qid}/reject", {}, principal=Staff(), ctx=STAFF_CTX)
    assert status == 422 and reply["field"] == "reason"
    status, reply = call(svc, "POST", f"/questions/{qid}/reject", {"reason": "duplicate", "note": "Есть такой же"},
                         principal=Staff(), ctx=STAFF_CTX)
    assert status == 200 and reply["question"]["status"] == "rejected"
    _s, page = call(svc, "GET", "/questions", query="tab=new")
    assert page["items"] == []
    assert call(svc, "POST", f"/questions/{qid}/publish", {}, principal=Staff(), ctx=STAFF_CTX)[0] == 409


def test_answer_needs_published_question_and_one_language(svc, clock):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    status, reply = call(svc, "POST", f"/questions/{qid}/answer", {"answer_ru": "Ответим после проверки."},
                         principal=Staff(), ctx=STAFF_CTX)
    assert status == 409 and reply["error"] == "not_published"
    publish(svc, qid)
    status, reply = call(svc, "POST", f"/questions/{qid}/answer", {"answer_ru": " ", "answer_kk": ""},
                         principal=Staff(), ctx=STAFF_CTX)
    assert status == 422
    status, reply = call(svc, "POST", f"/questions/{qid}/answer", {"answer_kk": "Шамдар ай соңына дейін ауыстырылады."},
                         principal=Staff(), ctx=STAFF_CTX)
    assert status == 200 and reply["question"]["answer"]["kk"].startswith("Шамдар")
    first = reply["question"]["answer"]["answered_at"]
    clock.now += timedelta(hours=2)
    _s, reply = call(svc, "POST", f"/questions/{qid}/answer", {"answer_ru": "Фонари заменят до конца месяца.",
                                                               "answer_kk": "Шамдар ай соңына дейін ауыстырылады."},
                     principal=Staff(), ctx=STAFF_CTX)
    assert reply["question"]["answer"]["answered_at"] == first and reply["question"]["answer"]["ru"]
    _s, page = call(svc, "GET", "/questions", query="tab=answered")
    assert [q["id"] for q in page["items"]] == [qid]
    _s, top = call(svc, "GET", "/questions", query="tab=top")
    assert top["items"] == []  # отвеченный — во вкладке «С ответом», не в «Популярных»


def test_answered_question_cannot_be_hidden(svc):
    _s, body = ask(svc)
    qid = body["question"]["id"]
    publish(svc, qid)
    call(svc, "POST", f"/questions/{qid}/answer", {"answer_ru": "Фонари заменят до конца месяца."},
         principal=Staff(), ctx=STAFF_CTX)
    status, reply = call(svc, "POST", f"/questions/{qid}/reject", {"reason": "other"}, principal=Staff(), ctx=STAFF_CTX)
    assert status == 409 and reply["error"] == "answered"


def test_staff_top_is_five_most_supported_without_answer(demo):
    _s, top = call(demo, "GET", "/questions/staff", query="tab=top", principal=Staff(), ctx=STAFF_CTX)
    votes = [q["votes"] for q in top["items"]]
    assert len(votes) == 5 and votes == sorted(votes, reverse=True) and all(q["answer"] is None for q in top["items"])
    assert top["week"]["limit"] == 5 and top["week"]["answered"] == 0  # демо-ответы — на прошлой неделе


def test_week_counts_answers_since_monday_in_astana(demo, clock):
    _s, top = call(demo, "GET", "/questions/staff", query="tab=top", principal=Staff(), ctx=STAFF_CTX)
    qid = top["items"][0]["id"]
    call(demo, "POST", f"/questions/{qid}/answer", {"answer_ru": "Светофор поставят в ноябре."}, principal=Staff(),
         ctx=STAFF_CTX)
    _s, top = call(demo, "GET", "/questions/staff", query="tab=top", principal=Staff(), ctx=STAFF_CTX)
    assert top["week"]["answered"] == 1


def test_week_bounds_start_on_monday_astana_time():
    # Воскресенье 23:30 в Астане (18:30 UTC) — ещё прошлая неделя; понедельник 00:10 — новая.
    start, end = week_bounds(datetime(2026, 10, 11, 18, 30, tzinfo=timezone.utc))
    assert start == datetime(2026, 10, 4, 19, 0, tzinfo=timezone.utc) and end - start == timedelta(days=7)
    start, _ = week_bounds(datetime(2026, 10, 11, 19, 10, tzinfo=timezone.utc))
    assert start == datetime(2026, 10, 11, 19, 0, tzinfo=timezone.utc)


def test_moderator_sees_personal_data_hint(svc):
    _s, body = ask(svc, text="Позвоните мне +7 (701) 123-45-67, ИИН 900101300123, почта a.b@mail.kz")
    _s, staff = call(svc, "GET", "/questions/staff", query="tab=queue", principal=Staff(), ctx=STAFF_CTX)
    assert staff["items"][0]["pii"] == ["phone", "iin", "email"]


@pytest.mark.parametrize("text, kinds", [
    ("Когда отремонтируют дом 12 по улице?", []),
    ("Автобус 21 ходит раз в 40 минут, с 2024 года", []),
    ("Мой номер 8 777 123 45 67", ["phone"]),
    ("+77011234567", ["phone"]),
])
def test_pii_hint_does_not_fire_on_ordinary_numbers(text, kinds):
    assert pii_kinds(text) == kinds


# R04 (INTEGRATION §3, patches/r13_pii_labels.patch): карта — не «ИИН + карта», запасной фильтр закрывает её целиком,
# сотруднику видны все виды R04 (счёт, квартира, контакт), а не только четыре своих.
@pytest.mark.parametrize("text, kinds", [
    ("Списали деньги с карты 4400 4302 1234 5678", ["card"]),
    ("Мой ИИН 900101300123, прошу проверить", ["iin"]),
    ("Карта 4400430212345678", ["card"]),
])
def test_card_number_is_not_taken_for_iin(text, kinds):
    assert pii_kinds(text) == kinds


def test_fallback_filter_masks_the_whole_card_and_staff_sees_r04_kinds(monkeypatch):
    import sys
    from ui.civic_qa.service import QuestionService, moderate_text
    monkeypatch.setitem(sys.modules, "ui.civic_ml_api", None)  # R04 нет — свой запасной фильтр
    public, flags = moderate_text("Деньги ушли с карты 4400 4302 1234 5678, верните", "ru")
    assert "4400" not in public and "5678" not in public and flags == ["card"]
    row = {"id": "q-x", "text": "Пишите в телеграм, квартира 12", "text_public": "Пишите ***, квартира ***", "lang": "ru",
           "district": "nura", "status": "pending", "votes": 0, "base_votes": 0, "created_at": "2026-10-15T10:00:00Z",
           "flags": '["contact", "apartment", "iban"]'}
    view = QuestionService._staff_view(row)
    assert view["pii"] == ["iban", "apartment", "contact"]  # порядок — как в подсказке экрана


# ---------------------------------------------------------------- что видят все
def test_public_view_has_no_device_staff_login_or_reject_reason(demo):
    _s, page = call(demo, "GET", "/questions", query="tab=new&device_id=" + DEV_A)
    for q in page["items"]:
        assert set(q) == {"id", "text", "lang", "district", "votes", "published_at", "answer", "demo", "my_vote"}
        assert q["answer"] is None or set(q["answer"]) == {"ru", "kk", "answered_at", "edited_at"}  # R15-S39
    blob = repr(page)
    assert "device_hash" not in blob and "editor" not in blob and "moderated" not in blob


def test_unknown_tab_and_district_are_rejected(svc):
    assert call(svc, "GET", "/questions", query="tab=all")[0] == 400
    assert call(svc, "GET", "/questions", query="tab=top&district=paris")[0] == 400
    assert call(svc, "GET", "/questions/staff", query="tab=spam", principal=Staff(), ctx=CTX)[0] == 400


def test_district_filter(demo):
    _s, page = call(demo, "GET", "/questions", query="tab=new&district=nura")
    assert page["items"] and {q["district"] for q in page["items"]} == {"nura"}


def test_unknown_routes_and_methods(svc):
    assert call(svc, "PUT", "/questions")[0] == 405
    assert call(svc, "POST", "/questions/q-abcd/like", {})[0] == 404
    assert call(svc, "POST", "/questions/../../etc/vote", {})[0] == 404


# ---------------------------------------------------------------- демо
def test_demo_set_is_marked_and_matches_the_task(demo):
    _s, new = call(demo, "GET", "/questions", query="tab=new")
    _s, answered = call(demo, "GET", "/questions", query="tab=answered")
    _s, queue = call(demo, "GET", "/questions/staff", query="tab=queue", principal=Staff(), ctx=STAFF_CTX)
    assert 8 <= len(new["items"]) <= 10 and len(answered["items"]) == 2  # POLISH_WAVE_2 п. 9: 8–10 вопросов, 2 ответа
    assert all(q["demo"] for q in new["items"] + queue["items"])
    assert all(q["answer"]["ru"] and q["answer"]["kk"] for q in answered["items"])
    assert any(q["pii"] for q in queue["items"])  # подсказка модератору видна на демо
    assert {q["lang"] for q in new["items"]} == {"ru", "kk"}


def test_demo_seed_is_idempotent_and_keeps_moderation(tmp_path, clock):
    db = str(tmp_path / "again.sqlite3")
    first = make_service(db, clock=clock, demo=True)
    call(first, "POST", "/questions/q-demo-12/reject", {"reason": "personal_data"}, principal=Staff(), ctx=STAFF_CTX)
    again = make_service(db, clock=clock, demo=True)
    _s, queue = call(again, "GET", "/questions/staff", query="tab=queue", principal=Staff(), ctx=STAFF_CTX)
    assert "q-demo-12" not in {q["id"] for q in queue["items"]} and queue["counts"]["queue"] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM qa_questions").fetchone()[0] == 12


def test_demo_votes_cannot_be_flipped_by_known_device_ids(demo):
    # R15 S20: у демо нет устройств с известными id — голос «за» можно только добавить, не перевернуть.
    _s, before = call(demo, "GET", "/questions", query="tab=top")
    q = before["items"][0]
    _s, v = call(demo, "POST", f"/questions/{q['id']}/vote", {"device_id": "demo-seed-0-00001-device"})
    assert v["votes"] == q["votes"] + 1


def test_demo_off_by_default_without_env(tmp_path, monkeypatch, clock):
    monkeypatch.delenv("CIVIC_DEMO", raising=False)
    svc = make_service(str(tmp_path / "plain.sqlite3"), clock=clock)
    assert call(svc, "GET", "/questions", query="tab=new")[1]["items"] == []
    monkeypatch.setenv("CIVIC_DEMO", "1")
    svc = make_service(str(tmp_path / "demo-env.sqlite3"), clock=clock)
    assert call(svc, "GET", "/questions", query="tab=new")[1]["counts"]["new"] == 9


# ---------------------------------------------------------------- шлюз R01 (если маршруты подключены)
def _gateway(tmp_path, monkeypatch):
    web_server = pytest.importorskip("ui.web_server")
    if "qa.list" not in getattr(web_server, "V2_HANDLERS", {}):
        pytest.skip("в этой сборке R01 ещё нет маршрутов qa.* (patch R13 INTEGRATION §8)")
    monkeypatch.setenv("CIVIC_DEMO", "1")
    gw = web_server.CivicV2Gateway(store_gateway=None, db_path=str(tmp_path / "gw.sqlite3"), demo=False)
    return gw


def test_gateway_routes_reach_the_service(tmp_path, monkeypatch):
    gw = _gateway(tmp_path, monkeypatch)
    ctx = dict(CTX, headers={})
    reply = gw.handle("GET", "/questions", "tab=top", None, ctx)
    assert reply["status"] == 200 and reply["body"]["counts"]["top"] == 7
    reply = gw.handle("POST", "/questions", "", {"text": "Когда откроют каток во дворе?", "district": "esil",
                                                 "device_id": DEV_A}, ctx)
    assert reply["status"] == 201
    assert gw.handle("GET", "/questions/staff", "tab=queue", None, ctx)["status"] in (401, 503)
    assert gw.modules()["qa.vote"]["status"] == "ready"


def test_gateway_rate_limits_questions_and_votes(tmp_path, monkeypatch):
    gw = _gateway(tmp_path, monkeypatch)
    ctx = dict(CTX, headers={}, client_ip="10.0.0.9")
    codes = [gw.handle("POST", "/questions", "", {"text": f"Вопрос про двор номер {i} и парковку",
                                                  "district": "nura", "device_id": f"dev-flood-{i:04d}"}, ctx)["status"]
             for i in range(5)]
    assert 429 in codes  # больше 3 вопросов в минуту с одного адреса
    votes = [gw.handle("POST", "/questions/q-demo-01/vote", "", {"device_id": f"dev-vote-{i:05d}"}, ctx)["status"]
             for i in range(25)]
    assert votes.count(200) <= 20 and 429 in votes  # R15 S08: ≤ 20 голосов за один вопрос с адреса в сутки
