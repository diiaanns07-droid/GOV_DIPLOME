"""R13 · «Встречи с акимом» (раунд 15): сервис ui/civic_meetings — права, лимиты, модерация, лента, засев, приватность.

Запуск: python -m pytest -q tests/civic/R13/meetings
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from ui.civic_meetings import make_service, seed_world
from ui.civic_meetings import board_block as module_board_block
from ui.civic_meetings import updates as module_updates
from ui.civic_meetings.demo import r09_demo_complaint

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
NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)  # четверг, 11:00 по Астане


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def svc(tmp_path, clock):
    return make_service(str(tmp_path / "civic.sqlite3"), clock=clock, demo=False)


@pytest.fixture
def demo(tmp_path, clock):
    return make_service(str(tmp_path / "demo.sqlite3"), clock=clock, demo=True)


def call(svc, method, path, body=None, query="", principal=None, ctx=None):
    reply = svc.handle(method, P + path, query, body, principal, ctx or CTX)
    assert set(reply) == {"status", "headers", "body"}
    return reply["status"], reply["body"]


def staff(svc, method, path, body=None, query=""):
    return call(svc, method, path, body, query, principal=Staff(), ctx=STAFF_CTX)


MEETING = {"district": "nura", "title_ru": "Встреча акима района с жителями", "title_kk": "Аудан әкімінің кездесуі",
           "at": "2026-10-20T18:30:00+05:00", "duration_min": 90,
           "place": {"kind": "area", "id": "yard-1424189376", "label_ru": "Двор: Eco Park", "label_kk": "Аула: Eco Park"},
           "point": [71.39142, 51.12761]}


def create(svc, **overrides):
    status, body = staff(svc, "POST", "/meetings", dict(MEETING, **overrides))
    assert status == 201, body
    return body["meeting"]


def ask(svc, mid, text="Когда во дворе поставят освещение у площадки?", device=DEV_A, **extra):
    return call(svc, "POST", f"/meetings/{mid}/question", dict({"text": text, "device_id": device}, **extra))


def publish(svc, qid):
    status, body = svc.qa.handle("POST", f"{P}/questions/{qid}/publish", "", {}, Staff(), STAFF_CTX)["status"], None
    assert status == 200
    return body


# ---------------------------------------------------------------- пусто и демо
def test_empty_list_is_a_clear_empty_state(svc):
    status, body = call(svc, "GET", "/meetings")
    assert status == 200
    assert body["items"] == [] and body["next_id"] is None and body["counts"] == {"upcoming": 0, "past": 0}
    assert body["host"] == {"ru": "Аким района", "kk": "Аудан әкімі"}
    assert body["staff"] is False


def test_demo_has_next_meeting_and_two_past_with_orders(demo):
    _s, body = call(demo, "GET", "/meetings")
    assert body["next_id"] == "m-demo-nura-next" and body["counts"] == {"upcoming": 1, "past": 2}
    phases = {m["id"]: m["phase"] for m in body["items"]}
    assert phases == {"m-demo-nura-next": "upcoming", "m-demo-nura-past": "held", "m-demo-esil-past": "held"}
    assert all(m["demo"] for m in body["items"])
    past = next(m for m in body["items"] if m["id"] == "m-demo-nura-past")
    assert past["orders_count"] == {"total": 5, "todo": 2, "in_progress": 2, "done": 1, "overdue": 1}
    assert past["has_result"] is True
    # Список «только ближайшие» и «только прошедшие»
    _s, up = call(demo, "GET", "/meetings", query="when=upcoming")
    assert [m["id"] for m in up["items"]] == ["m-demo-nura-next"]
    _s, done = call(demo, "GET", "/meetings", query="when=past&district=esil")
    assert [m["id"] for m in done["items"]] == ["m-demo-esil-past"]


def test_demo_card_top_questions_by_votes_and_orders(demo):
    _s, body = call(demo, "GET", "/meetings/m-demo-nura-next", query="device_id=" + DEV_A)
    m = body["meeting"]
    votes = [q["votes"] for q in m["questions"]]
    assert votes == sorted(votes, reverse=True) and len(votes) == 6
    assert m["voting_open"] is True and m["registered"] == 54 and m["my_registration"] is False
    assert "pending_questions" not in m  # непроверенный вопрос жителю не виден
    _s, past = call(demo, "GET", "/meetings/m-demo-nura-past")
    orders = {o["id"]: o for o in past["meeting"]["orders"]}
    assert orders["o-demo-n2"]["overdue"] is True and orders["o-demo-n3"]["overdue"] is False
    assert orders["o-demo-n1"]["link"] == {"kind": "complaint", "id": r09_demo_complaint("khan-shatyr-lighting")}
    assert past["meeting"]["result"]["ru"].startswith("Пришли")
    answered = [q for q in past["meeting"]["questions"] if q["answer"]]
    assert len(answered) == 2


def test_demo_seed_is_idempotent(tmp_path, clock):
    path = str(tmp_path / "x.sqlite3")
    make_service(path, clock=clock, demo=True)
    make_service(path, clock=clock, demo=True)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM mt_meetings").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM mt_orders").fetchone()[0] == 9
        assert conn.execute("SELECT COUNT(*) FROM qa_questions WHERE meeting_id IS NOT NULL").fetchone()[0] == 9


def test_demo_world_flag_skips_own_fixture(tmp_path, clock, monkeypatch):
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
    service = make_service(str(tmp_path / "w.sqlite3"), clock=clock)
    assert call(service, "GET", "/meetings")[1]["items"] == []
    monkeypatch.delenv("CIVIC_DEMO_WORLD")
    service = make_service(str(tmp_path / "w2.sqlite3"), clock=clock)
    assert len(call(service, "GET", "/meetings")[1]["items"]) == 3


# ---------------------------------------------------------------- «Приду»
def test_register_once_per_device_and_cancel(svc):
    m = create(svc)
    status, body = call(svc, "POST", f"/meetings/{m['id']}/register", {"device_id": DEV_A})
    assert status == 200 and body == {"id": m["id"], "registered": 1, "my_registration": True, "changed": True}
    status, body = call(svc, "POST", f"/meetings/{m['id']}/register", {"device_id": DEV_A})
    assert body["registered"] == 1 and body["changed"] is False  # второй раз не считается
    _s, body = call(svc, "POST", f"/meetings/{m['id']}/register", {}, ctx=dict(CTX, headers={"x-birge-device": DEV_B}))
    assert body["registered"] == 2
    _s, card = call(svc, "GET", f"/meetings/{m['id']}", query="device_id=" + DEV_B)
    assert card["meeting"]["my_registration"] is True and card["meeting"]["registered"] == 2
    _s, body = call(svc, "POST", f"/meetings/{m['id']}/register", {"device_id": DEV_A, "going": False})
    assert body["registered"] == 1 and body["my_registration"] is False and body["changed"] is True


def test_register_closed_after_start_and_for_cancelled(svc, clock):
    m = create(svc)
    staff(svc, "POST", "/meetings", {"id": m["id"], "status": "cancelled"})
    status, body = call(svc, "POST", f"/meetings/{m['id']}/register", {"device_id": DEV_A})
    assert status == 409 and body["error"] == "cancelled"
    m2 = create(svc)
    clock.now = NOW + timedelta(days=6)  # 21 окт — встреча уже прошла
    status, body = call(svc, "POST", f"/meetings/{m2['id']}/register", {"device_id": DEV_A})
    assert status == 409 and body["error"] == "started"


@pytest.mark.parametrize("body, ctx, status", [
    ({"device_id": "short"}, CTX, 400),
    ({}, CTX, 400),
    ({"device_id": DEV_A, "going": "yes"}, CTX, 400),
    ({"device_id": DEV_A}, dict(CTX, is_same_origin=False), 403),
    ({"device_id": DEV_A}, dict(CTX, host_allowed=False), 403),
])
def test_register_rejects_bad_input(svc, body, ctx, status):
    m = create(svc)
    assert call(svc, "POST", f"/meetings/{m['id']}/register", body, ctx=ctx)[0] == status


def test_register_daily_limit_per_device(svc):
    ids = [create(svc)["id"] for _ in range(4)]
    store = svc.store
    for mid in ids[:3]:
        store.register(mid, DEV_A, True, max_per_day=3)
    with pytest.raises(Exception) as err:
        store.register(ids[3], DEV_A, True, max_per_day=3)
    assert getattr(err.value, "code", "") == "too_many"


def test_unknown_meeting_is_404(svc):
    assert call(svc, "GET", "/meetings/m-nope")[0] == 404
    assert call(svc, "GET", "/meetings/bad!id")[0] == 404
    assert call(svc, "POST", "/meetings/m-nope/register", {"device_id": DEV_A})[0] == 404


# ---------------------------------------------------------------- вопросы к встрече
def test_question_waits_for_moderation_then_appears_with_votes(svc):
    m = create(svc)
    status, body = ask(svc, m["id"])
    assert status == 201 and body["question"]["status"] == "pending" and body["question"]["meeting_id"] == m["id"]
    qid = body["question"]["id"]
    _s, card = call(svc, "GET", f"/meetings/{m['id']}")
    assert card["meeting"]["questions"] == []
    # Сотрудник видит вопрос и в карточке встречи, и в общей очереди «Вопроса акиму» — с пометкой встречи.
    _s, staff_card = staff(svc, "GET", f"/meetings/{m['id']}")
    assert [q["id"] for q in staff_card["meeting"]["pending_questions"]] == [qid]
    queue = svc.qa.handle("GET", P + "/questions/staff", "tab=queue", None, Staff(), STAFF_CTX)["body"]
    assert [q["meeting_id"] for q in queue["items"]] == [m["id"]]
    publish(svc, qid)
    _s, card = call(svc, "GET", f"/meetings/{m['id']}", query="device_id=" + DEV_A)
    q = card["meeting"]["questions"][0]
    assert q["id"] == qid and q["votes"] == 1 and q["my_vote"] is True  # автор поддержал свой вопрос
    vote = svc.qa.handle("POST", f"{P}/questions/{qid}/vote", "", {"device_id": DEV_B}, None, CTX)
    assert vote["status"] == 200 and vote["body"]["votes"] == 2
    # В общих списках «Вопроса акиму» вопроса встречи нет (на него отвечают на встрече).
    for tab in ("top", "new", "answered"):
        page = svc.qa.handle("GET", P + "/questions", f"tab={tab}", None, None, CTX)["body"]
        assert page["items"] == [] and page["counts"]["new"] == 0


def test_voting_and_questions_close_when_meeting_starts(svc, clock):
    m = create(svc)
    _s, body = ask(svc, m["id"])
    publish(svc, body["question"]["id"])
    clock.now = datetime(2026, 10, 20, 13, 30, tzinfo=timezone.utc)  # 18:30 по Астане — началась
    vote = svc.qa.handle("POST", f"{P}/questions/{body['question']['id']}/vote", "", {"device_id": DEV_B}, None, CTX)
    assert vote["status"] == 409 and vote["body"]["error"] == "closed"
    status, err = ask(svc, m["id"], device=DEV_B)
    assert status == 409 and err["error"] == "closed"
    _s, card = call(svc, "GET", f"/meetings/{m['id']}")
    assert card["meeting"]["phase"] == "live" and card["meeting"]["voting_open"] is False


def test_moving_meeting_moves_voting_close(svc, clock):
    m = create(svc)
    _s, body = ask(svc, m["id"])
    publish(svc, body["question"]["id"])
    staff(svc, "POST", "/meetings", {"id": m["id"], "at": "2026-10-27T18:30:00+05:00"})
    clock.now = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)  # после старого времени, до нового
    vote = svc.qa.handle("POST", f"{P}/questions/{body['question']['id']}/vote", "", {"device_id": DEV_B}, None, CTX)
    assert vote["status"] == 200


def test_question_limits_per_meeting(svc):
    m = create(svc)
    for i in range(3):
        status, body = ask(svc, m["id"], text=f"Вопрос номер {i} про двор и освещение")
        assert status == 201
        publish(svc, body["question"]["id"])
    status, body = ask(svc, m["id"], text="Четвёртый вопрос про двор и освещение")
    assert status == 409 and body["error"] == "too_many_meeting"


@pytest.mark.parametrize("text, status", [("коротко", 422), ("x" * 301, 422), (None, 422), (123, 422)])
def test_question_text_rules(svc, text, status):
    m = create(svc)
    assert call(svc, "POST", f"/meetings/{m['id']}/question", {"text": text, "device_id": DEV_A})[0] == status


def test_personal_data_never_reaches_public_text(svc):
    m = create(svc)
    _s, body = ask(svc, m["id"], text="Позвоните мне +7 701 123 45 67 насчёт освещения во дворе")
    qid = body["question"]["id"]
    _s, staff_card = staff(svc, "GET", f"/meetings/{m['id']}")
    pending = staff_card["meeting"]["pending_questions"][0]
    assert "phone" in pending["pii"] and "+7 701" in pending["text"]  # сотрудник видит исходник и пометку
    publish(svc, qid)
    _s, card = call(svc, "GET", f"/meetings/{m['id']}")
    text = card["meeting"]["questions"][0]["text"]
    assert "701" not in text and "***" in text


def test_r04_moderate_is_used_when_present(svc, monkeypatch):
    import ui.civic_ml_api as ml

    def fake_moderate(text, lang=None):
        return {"text_public": text.replace("плохое", "***"), "flags": ["profanity"]}

    monkeypatch.setattr(ml, "moderate", fake_moderate, raising=False)
    m = create(svc)
    _s, body = ask(svc, m["id"], text="Тут плохое слово и вопрос про двор")
    _s, staff_card = staff(svc, "GET", f"/meetings/{m['id']}")
    assert staff_card["meeting"]["pending_questions"][0]["rude"] is True
    publish(svc, body["question"]["id"])
    _s, card = call(svc, "GET", f"/meetings/{m['id']}")
    assert card["meeting"]["questions"][0]["text"] == "Тут *** слово и вопрос про двор"


# ---------------------------------------------------------------- сотрудник: встреча
@pytest.mark.parametrize("principal, ctx, status", [
    (None, CTX, 401),
    (Staff(staff=False), STAFF_CTX, 403),
    (Staff(), CTX, 403),                                    # нет CSRF
    (Staff(), dict(STAFF_CTX, is_same_origin=False), 403),  # чужой сайт
])
def test_staff_actions_need_session_and_csrf(svc, principal, ctx, status):
    assert call(svc, "POST", "/meetings", dict(MEETING), principal=principal, ctx=ctx)[0] == status
    m = create(svc)
    for path, body in ((f"/meetings/{m['id']}/order", {"text_ru": "Сделать что-то", "service": "road",
                                                       "due": "2026-11-01"}),
                       (f"/meetings/{m['id']}/result", {"result_ru": "Итог встречи такой"})):
        assert call(svc, "POST", path, body, principal=principal, ctx=ctx)[0] == status


@pytest.mark.parametrize("field, value", [
    ("district", "mars"), ("title_ru", "abc"), ("at", "завтра"), ("at", "2030-01-01T10:00:00+05:00"),
    ("place", None), ("place", {"label_ru": "Двор", "kind": "planet", "id": "x"}), ("point", [10.0, 10.0]),
    ("duration_min", 5), ("duration_min", True),
])
def test_meeting_validation(svc, field, value):
    status, body = staff(svc, "POST", "/meetings", dict(MEETING, **{field: value}))
    assert status == 422 and body["field"] == field


def test_meeting_without_map_target_is_allowed(svc):
    m = create(svc, place={"label_ru": "Школа, актовый зал"}, point=None)
    assert m["place"] == {"kind": None, "id": None, "label_ru": "Школа, актовый зал", "label_kk": None}


def test_cannot_move_or_cancel_after_result(svc, clock):
    m = create(svc)
    clock.now = datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc)
    assert staff(svc, "POST", f"/meetings/{m['id']}/result", {"result_ru": "Пришли 40 жителей, дано 3 поручения"})[0] == 200
    status, body = staff(svc, "POST", "/meetings", {"id": m["id"], "at": "2026-10-28T18:00:00+05:00"})
    assert status == 409 and body["error"] == "held"


def test_result_rules(svc, clock):
    m = create(svc)
    status, body = staff(svc, "POST", f"/meetings/{m['id']}/result", {"result_ru": "Пришли 40 жителей"})
    assert status == 409 and body["error"] == "not_started"
    clock.now = datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc)
    assert staff(svc, "POST", f"/meetings/{m['id']}/result", {})[0] == 422
    status, body = staff(svc, "POST", f"/meetings/{m['id']}/result", {"result_kk": "40 тұрғын келді, 3 тапсырма"})
    assert status == 200 and body["meeting"]["result"]["kk"].startswith("40") and body["meeting"]["phase"] == "held"
    first_at = body["meeting"]["result"]["at"]
    clock.now += timedelta(hours=3)
    _s, body = staff(svc, "POST", f"/meetings/{m['id']}/result", {"result_ru": "Пришли 40 жителей, дано 3 поручения"})
    assert body["meeting"]["result"]["at"] == first_at and body["meeting"]["result"]["kk"]  # второй язык не стёрт


# ---------------------------------------------------------------- поручения
def test_orders_create_update_and_overdue(svc, clock):
    m = create(svc)
    status, body = staff(svc, "POST", f"/meetings/{m['id']}/order",
                         {"text_ru": "Нанести разметку у школы", "text_kk": "Мектеп жанында жол таңбасын салу",
                          "service": "traffic", "due": "2026-10-25"})
    assert status == 201
    order = body["order"]
    assert order["status"] == "todo" and order["service_name"]["ru"] and order["overdue"] is False
    clock.now = datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc)
    _s, card = call(svc, "GET", f"/meetings/{m['id']}")
    assert card["meeting"]["orders"][0]["overdue"] is True
    status, body = staff(svc, "POST", f"/meetings/{m['id']}/order", {"order_id": order["id"], "status": "done"})
    assert status == 200 and body["order"]["status"] == "done" and body["order"]["done_at"] and not body["order"]["overdue"]
    status, body = staff(svc, "POST", f"/meetings/{m['id']}/order",
                         {"order_id": order["id"], "link": {"kind": "complaint", "id": "c-demo0123456789abcdef"}})
    assert body["order"]["link"] == {"kind": "complaint", "id": "c-demo0123456789abcdef"}
    status, body = staff(svc, "POST", f"/meetings/{m['id']}/order", {"order_id": order["id"], "link": None})
    assert body["order"]["link"] is None


@pytest.mark.parametrize("body, field", [
    ({"text_ru": "Сделать", "service": "spaceport", "due": "2026-11-01"}, "service"),
    ({"text_ru": "Сделать", "service": "road", "due": "01.11.2026"}, "due"),
    ({"text_ru": "Сделать", "service": "road", "due": "2026-02-30"}, "due"),
    ({"text_ru": "Сделать", "service": "road", "due": "2031-01-01"}, "due"),
    ({"text_ru": "Сд", "service": "road", "due": "2026-11-01"}, "text_ru"),
    ({"text_ru": "Сделать", "service": "road", "due": "2026-11-01", "status": "lost"}, "status"),
    ({"text_ru": "Сделать", "service": "road", "due": "2026-11-01", "link": {"kind": "tweet", "id": "1"}}, "link"),
])
def test_order_validation(svc, body, field):
    m = create(svc)
    status, reply = staff(svc, "POST", f"/meetings/{m['id']}/order", body)
    assert status == 422 and reply["field"] == field


def test_order_update_unknown_or_empty(svc):
    m = create(svc)
    assert staff(svc, "POST", f"/meetings/{m['id']}/order", {"order_id": "o-missing", "status": "done"})[0] == 404
    _s, body = staff(svc, "POST", f"/meetings/{m['id']}/order", {"text_ru": "Сделать разметку", "service": "road",
                                                                 "due": "2026-11-01"})
    assert staff(svc, "POST", f"/meetings/{m['id']}/order", {"order_id": body["order"]["id"]})[0] == 422


# ---------------------------------------------------------------- лента R06
def test_updates_only_for_devices_that_care(svc, clock):
    m = create(svc)
    call(svc, "POST", f"/meetings/{m['id']}/register", {"device_id": DEV_A})
    _s, body = ask(svc, m["id"], device=DEV_B)
    publish(svc, body["question"]["id"])
    since = "2026-10-15T00:00:00Z"
    # Напоминание за сутки — только тому, кто нажал «Приду».
    clock.now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    kinds_a = [e["sub"] for e in svc.updates(DEV_A, since)]
    assert kinds_a == ["reminder"]
    assert [e["sub"] for e in svc.updates(DEV_B, since)] == ["question"]
    assert svc.updates("dev-cccccccc-0003", since) == []
    clock.now = datetime(2026, 10, 20, 16, 0, tzinfo=timezone.utc)
    staff(svc, "POST", f"/meetings/{m['id']}/result", {"result_ru": "Пришли 40 жителей, дано 1 поручение"})
    _s, body = staff(svc, "POST", f"/meetings/{m['id']}/order", {"text_ru": "Поставить фонари у площадки",
                                                                 "service": "lighting", "due": "2026-11-10"})
    clock.now += timedelta(days=2)
    staff(svc, "POST", f"/meetings/{m['id']}/order", {"order_id": body["order"]["id"], "status": "done"})
    events = svc.updates(DEV_A, "2026-10-20T00:00:00Z")
    assert [e["sub"] for e in events] == ["order", "result"]  # свежие первыми
    for e in events:
        assert e["module"] == "R13" and e["kind"] == "meeting.result"
        assert e["link"].startswith(f"#meetings/{m['id']}") and e["title_ru"] and e["title_kk"]
        assert e["target"]["meeting_id"] == m["id"]
    assert events[0]["link"] == f"#meetings/{m['id']}/{body['order']['id']}"
    # since отсекает уже показанное
    assert svc.updates(DEV_A, events[0]["at"]) == []
    # HTTP-маршрут ленты
    status, page = call(svc, "GET", "/meetings/updates", query=f"since=2026-10-20T00:00:00Z&device_id={DEV_A}")
    assert status == 200 and [e["id"] for e in page["items"]] == [e["id"] for e in events]
    assert call(svc, "GET", "/meetings/updates", query="since=вчера&device_id=" + DEV_A)[0] == 400
    assert call(svc, "GET", "/meetings/updates")[0] == 400  # нужен device


def test_module_level_updates_and_board_block(demo, tmp_path):
    path = demo.store.db_path
    assert module_updates("dev-nobody-0000", None, db_path=path) == []
    block = module_board_block(path)
    assert block["next"]["id"] == "m-demo-nura-next" and block["demo"] is True
    assert block["counts"]["total"] == 9 and block["counts"]["overdue"] == 1
    assert block["orders"][0]["overdue"] is True                       # просроченные — первыми
    assert all(o["status"] != "done" for o in block["orders"]) and len(block["orders"]) <= 5
    esil = module_board_block(path, district="esil")
    assert esil["next"] is None and esil["counts"]["done"] == 3


# ---------------------------------------------------------------- демо-мир R02
WORLD = {
    "meetings": [
        {"id": "m-w1", "district": "nura", "title_ru": "Встреча акима района Нура с жителями", "title_kk": "Кездесу",
         "in_days": 2, "time": "18:30", "place": {"kind": "area", "id": "yard-1424189376", "label_ru": "Двор: Eco Park"},
         "point": [71.39142, 51.12761], "registered": 40, "demo": True},
        {"id": "m-w2", "district": "esil", "title_ru": "Встреча акима района Есиль с жителями", "ago_days": 10,
         "place": {"label_ru": "Двор: Argento"}, "registered": 30,
         "result": {"text_ru": "Пришли 30 жителей, дано 2 поручения", "ago_days": 9},
         "orders": [{"id": "o-1", "text_ru": "Отремонтировать тротуар", "service": "road", "due_days_after": 30,
                     "status": "in_progress"},
                    {"id": "o-2", "text_ru": "Поставить скамейки", "service": "landscaping", "due_in_days": -2,
                     "status": "todo"},
                    {"id": "o-3", "text_ru": "Без службы", "due_in_days": 5}]},
        {"id": "bad", "district": "mars", "title_ru": "Плохая запись", "in_days": 1},
    ],
    "questions": [
        {"id": "q-w1", "meeting_id": "m-w1", "text": "Когда поставят свет у детской площадки?", "lang": "ru",
         "votes": 12, "ago_days": 1},
        {"id": "q-w2", "district": "esil", "text": "Будет ли новая остановка у школы?", "votes": 5, "ago_days": 3},
        {"id": "q-w3", "meeting": "m-w2", "text": "Почему не убирают снег во дворе?", "votes": 9, "ago_days": 12,
         "answer_ru": "Уборку дворов включили в график службы."},
        {"id": "nope", "text": "x"},
    ],
}


def test_seed_world_takes_own_part_and_is_idempotent(tmp_path, clock):
    path = str(tmp_path / "world.sqlite3")
    report = seed_world(path, WORLD, now=NOW)
    assert report["inserted"] == 2 + 2 + 3 and report["skipped"] == 1 + 1 + 1
    again = seed_world(path, WORLD, now=NOW)
    assert again["inserted"] == 0
    service = make_service(path, clock=clock, demo=False)
    _s, body = call(service, "GET", "/meetings")
    assert body["next_id"] == "m-w1" and body["counts"] == {"upcoming": 1, "past": 1}
    _s, card = call(service, "GET", "/meetings/m-w1")
    assert card["meeting"]["at"] == "2026-10-17T13:30:00Z"                 # через 2 дня в 18:30 по Астане
    assert [q["id"] for q in card["meeting"]["questions"]] == ["q-w1"] and card["meeting"]["registered"] == 40
    _s, past = call(service, "GET", "/meetings/m-w2")
    orders = past["meeting"]["orders"]
    assert [o["id"] for o in orders] == ["o-w2-1", "o-w2-2"] and orders[1]["overdue"] is True
    assert past["meeting"]["result"]["ru"].startswith("Пришли") and past["meeting"]["questions"][0]["answer"]
    general = service.qa.handle("GET", P + "/questions", "tab=new", None, None, CTX)["body"]
    assert [q["id"] for q in general["items"]] == ["q-w2"]                  # общий вопрос — в «Вопросе акиму»


def test_seed_world_accepts_plain_list_and_empty(tmp_path):
    path = str(tmp_path / "w.sqlite3")
    assert seed_world(path, [], now=NOW) == {"inserted": 0, "skipped": 0}
    assert seed_world(path, {"meetings": WORLD["meetings"][:1]}, now=NOW)["inserted"] == 1


# ---------------------------------------------------------------- приватность
def test_public_answers_have_no_devices_logins_or_staff_only_fields(demo):
    call(demo, "POST", "/meetings/m-demo-nura-next/register", {"device_id": DEV_A})
    blobs = [call(demo, "GET", "/meetings", query="device_id=" + DEV_A)[1],
             call(demo, "GET", "/meetings/m-demo-nura-next", query="device_id=" + DEV_A)[1],
             call(demo, "GET", "/meetings/m-demo-nura-past")[1]]
    text = json.dumps(blobs, ensure_ascii=False)
    for secret in ("device_hash", "created_by", "by_user", "editor", DEV_A, "pending_questions", "telegram"):
        assert secret not in text
    # Ведущий — должность, без имени
    assert blobs[0]["host"] == {"ru": "Аким района", "kk": "Аудан әкімі"}


def test_unknown_routes_and_methods(svc):
    assert call(svc, "DELETE", "/meetings")[0] == 405
    assert call(svc, "POST", "/meetings/updates")[0] == 405
    m = create(svc)
    assert call(svc, "PUT", f"/meetings/{m['id']}")[0] == 405
    assert call(svc, "GET", f"/meetings/{m['id']}/order")[0] == 405
    assert call(svc, "POST", f"/meetings/{m['id']}/dance", {})[0] == 404
    assert call(svc, "GET", "/meetings", query="when=soon")[0] == 400
    assert call(svc, "GET", "/meetings", query="district=mars")[0] == 400
    assert svc.handle("GET", P + "/questions", "", None, None, CTX) is None  # чужой адрес — не наш


# ---------------------------------------------------------------- мир R02 «как в файле» и сброс демо при запуске
RAW_WORLD = {  # формы времени SCHEMA.md R02 §1 (до materialize)
    "meetings": [
        {"id": "m-w15-1", "district": "nura", "title_ru": "Встреча акима района с жителями Нуры", "title_kk": "Кездесу",
         "at": {"ago_days": 12.3}, "time": "18:00", "place": {"kind": "area", "id": "yard-1454082640", "label_ru": "Двор: BI City Tokyo"},
         "registered": 54, "questions": ["q-w15-05"],
         "orders": [{"id": "o-1", "text_ru": "Отремонтировать детскую площадку", "service": "landscaping", "due": {"day": -10},
                     "status": "done", "link": {"kind": "complaint", "id": "c-w1500008"}},
                    {"id": "o-2", "text_ru": "Восстановить освещение улицы", "service": "lighting", "due": {"day": 5},
                     "status": "in_progress"}], "demo": True},
        {"id": "m-w15-2", "district": "nura", "title_ru": "Встреча акима района: зима во дворах",
         "at": {"next_weekday": {"weekday": 3, "hour": 18, "minute": 30}}, "place": {"kind": "area", "id": "yard-1531186326",
         "label_ru": "Двор — улица 206"}, "registered": 31, "questions": ["q-w15-01"], "orders": [], "demo": True},
    ],
    "questions": [
        {"id": "q-w15-01", "district": "nura", "lang": "ru", "text": "Когда во дворах Нуры будут убирать снег быстрее?",
         "status": "published", "created_at": {"ago_days": 1.6}, "published_at": {"ago_days": 1.5}, "base_votes": 46,
         "answer_ru": None, "answer_kk": None, "answered_at": None, "meeting": "m-w15-2", "demo": True},
        {"id": "q-w15-05", "district": "nura", "lang": "ru", "text": "Когда отремонтируют детскую площадку во дворе?",
         "status": "published", "created_at": {"ago_days": 14}, "published_at": {"ago_days": 13.9}, "base_votes": 22,
         "answer_ru": "Ремонт включён в поручения встречи.", "answered_at": {"ago_days": 12.2}, "meeting": "m-w15-1", "demo": True},
    ],
}


def test_seed_world_reads_raw_r02_time_forms(tmp_path, clock):
    path = str(tmp_path / "raw.sqlite3")
    report = seed_world(path, RAW_WORLD, now=NOW)
    assert report == {"inserted": 2 + 2 + 2, "skipped": 0}
    service = make_service(path, clock=clock, demo=False)
    _s, body = call(service, "GET", "/meetings")
    by_id = {m["id"]: m for m in body["items"]}
    # weekday 3 у R02 — четверг; сегодняшний вечер ближе 12 часов -> следующий четверг 18:30
    assert by_id["m-w15-2"]["phase"] == "upcoming" and by_id["m-w15-2"]["at"] == "2026-10-22T13:30:00Z"
    assert by_id["m-w15-1"]["phase"] == "held" and by_id["m-w15-1"]["at"].endswith("T13:00:00Z")      # 18:00 по Астане
    _s, past = call(service, "GET", "/meetings/m-w15-1")
    orders = past["meeting"]["orders"]
    assert [o["due"] for o in orders] == ["2026-10-05", "2026-10-20"]
    assert past["meeting"]["questions"][0]["answer"]["ru"].startswith("Ремонт")
    _s, nxt = call(service, "GET", "/meetings/m-w15-2")
    assert [(q["id"], q["votes"]) for q in nxt["meeting"]["questions"]] == [("q-w15-01", 46)]


def test_demo_reset_on_restart_keeps_real_records(tmp_path):
    path = str(tmp_path / "reset.sqlite3")
    first = Clock(NOW)
    svc = make_service(path, clock=first, demo=True)
    # репетиция: житель нажал «Приду», сотрудник закрыл демо-поручение, добавил своё и снял демо-вопрос
    call(svc, "POST", "/meetings/m-demo-nura-next/register", {"device_id": DEV_A})
    staff(svc, "POST", "/meetings/m-demo-nura-past/order", {"order_id": "o-demo-n2", "status": "done"})
    _s, own = staff(svc, "POST", "/meetings/m-demo-nura-past/order", {"text_ru": "Своё поручение сотрудника",
                                                                      "service": "road", "due": "2026-11-20"})
    assert svc.qa.handle("POST", f"{P}/questions/q-demo-m02/reject", "", {"reason": "personal_data"}, Staff(), STAFF_CTX)["status"] == 200
    # через 5 дней сервер запускают снова
    later = Clock(NOW + timedelta(days=5))
    svc2 = make_service(path, clock=later, demo=True)
    _s, body = call(svc2, "GET", "/meetings", query="device_id=" + DEV_A)
    nxt = next(m for m in body["items"] if m["id"] == "m-demo-nura-next")
    assert nxt["phase"] == "upcoming" and nxt["at"] > (NOW + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert nxt["my_registration"] is True and nxt["registered"] == 55      # отметка устройства сохранилась
    _s, past = call(svc2, "GET", "/meetings/m-demo-nura-past")
    orders = {o["id"]: o for o in past["meeting"]["orders"]}
    assert orders["o-demo-n2"]["status"] == "todo"                          # демо-поручение вернулось к исходному
    assert own["order"]["id"] in orders                                       # поручение сотрудника не тронуто
    _s, card = call(svc2, "GET", "/meetings/m-demo-nura-next")
    assert "q-demo-m02" not in [q["id"] for q in card["meeting"]["questions"]]  # снятый вопрос не вернулся (R15 S20)


def test_complaint_link_shows_place_and_status_from_r09_public_view(tmp_path, clock):
    from ui.civic_feedback.v2.integration import make_service as make_complaints
    path = str(tmp_path / "links.sqlite3")
    make_complaints(path, demo_seed=True)                       # демо-жалоба R09 «Хан Шатыр» (освещение)
    service = make_service(path, clock=clock, demo=True)
    _s, past = call(service, "GET", "/meetings/m-demo-nura-past")
    link = next(o["link"] for o in past["meeting"]["orders"] if o["link"])
    assert link["label_ru"] == "Остановка «Хан Шатыр»" and link["target"] == {"kind": "object", "id": "osm-node-4109037549"}
    assert link["status"] in ("new", "accepted", "in_progress", "fixed") and "text" not in link  # без слов жителя
    # нет такой жалобы — остаётся номер, без ошибки
    staff(service, "POST", "/meetings/m-demo-nura-past/order", {"order_id": "o-demo-n4", "link": {"kind": "complaint", "id": "c-missing-1"}})
    _s, again = call(service, "GET", "/meetings/m-demo-nura-past")
    bare = next(o["link"] for o in again["meeting"]["orders"] if o["id"] == "o-demo-n4")
    assert bare == {"kind": "complaint", "id": "c-missing-1"}
