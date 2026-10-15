"""R09 · раунд 15 · жалоба v2.1 (CONTRACT §5.1): обращение для нескольких служб и передачи между службами.

Правила (ui/civic_feedback/v2/joint.py): статус всей жалобы — по ведущей службе; «исправлено» — когда все части done;
передача не обнуляет срок ответа жителю (рабочие дни и праздники РК); жителю — кто что делает, без причин передач.
"""

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, Conflict, NotFound, RecordError
from ui.civic_feedback.v2 import joint, lifecycle, workdays
from ui.civic_feedback.v2 import record as rec

DEV_A, DEV_B, DEV_C = "dev-aaaaaaaaaaaaaaaa", "dev-bbbbbbbbbbbbbbbb", "dev-cccccccccccccccc"
SEGMENT = {"kind": "segment", "id": "osm-w123-4", "label_ru": "Участок ул. Сарайшык"}
POINT = [71.4135, 51.0915]
PIT = "Яма после раскопок водоканала, траншею не закопали"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 22, 10, 0, tzinfo=rec.ASTANA_TZ)   # четверг перед Днём Республики

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    s = ComplaintStore(tmp_path / "j.sqlite3", clock=clock)
    yield s
    s.close()


def pit(store, device=DEV_A, **over):
    body = {"text": PIT, "category": "roads", "subtopic": "pothole", "point": POINT, "target": SEGMENT}
    body.update(over)
    return store.create(body, device)[0]


class Staff:
    is_staff = True
    username = "operator1"
    role = "editor"

    def check_csrf(self, value):
        return value == "tok"


STAFF_CTX = {"headers": {"X-CSRF-Token": "tok"}, "host_allowed": True, "is_same_origin": True}
P = "/api/civic/v2/complaints"


def call(service, method, path, body=None, principal=None, ctx=None):
    reply = service.handle(method, path, None, json.dumps(body) if body is not None else None, principal,
                           ctx if ctx is not None else {"host_allowed": True, "is_same_origin": True})
    return reply["status"], reply["body"]


# ---------------------------------------------------------------- запись v2.1 и миграция
def test_new_complaint_is_v21_with_table_service_and_empty_parts(store):
    record = pit(store)
    assert record["schema"] == "civic-complaint-v2.1"
    assert (record["service"], record["service_source"]) == ("road", "table")
    assert record["services"] == [] and record["handoffs"] == [] and record["route_hint"] is None
    parts = joint.parts(record)
    assert [(p["service"], p["role"], p["status"]) for p in parts] == [("road", "lead", "todo")]
    # Ведущая «по таблице» следует за таблицей R08, как паспорт FINAL-4 (правка акимата видна сразу).
    r08 = lambda c, s: {"id": "water", "ru": "Водоканал", "kk": "Сумен жабдықтау қызметі"}
    assert joint.lead_service(record, r08) == "water"
    assert lifecycle.passport_view(record, store._now(), r08)["assignee_source"] == "r08"


def test_old_v2_records_upgrade_once_without_losing_fields(tmp_path, clock):
    path = tmp_path / "old.sqlite3"
    first = ComplaintStore(path, clock=clock)
    record = pit(first)
    first.update_passport(record["id"], {"service": "power", "next_step": "Выезд бригады"})
    first.close()
    # Как в базе FINAL-4: записи без полей v2.1 и без отметки миграции.
    db = sqlite3.connect(path)
    raw = json.loads(db.execute("SELECT record_json FROM complaints_v2").fetchone()[0])
    for key in ("service", "service_source", "services", "handoffs", "route_hint"):
        raw.pop(key, None)
    raw["schema"] = "civic-complaint-v2"
    db.execute("UPDATE complaints_v2 SET record_json = ?", (json.dumps(raw, ensure_ascii=False),))
    db.execute("DELETE FROM complaint_meta_v2 WHERE key = 'migrated_v21'")
    db.commit()
    db.close()
    again = ComplaintStore(path, clock=clock)
    try:
        upgraded = again.get(record["id"])
        assert upgraded["schema"] == "civic-complaint-v2.1"
        assert (upgraded["service"], upgraded["service_source"]) == ("power", "staff")   # выбор сотрудника сохранён
        assert upgraded["passport"]["next_step"] == "Выезд бригады" and upgraded["text"] == PIT
        assert {k: v for k, v in upgraded.items() if k in raw and k != "schema"} == \
               {k: v for k, v in raw.items() if k != "schema"}                          # ничего не потеряно
        assert again.migrate_v21() == {"upgraded": 0, "total": None, "at": rec.iso(clock.now)}   # повтор — ничего
    finally:
        again.close()


def test_upgrade_only_adds_fields():
    old = {"id": "c-old0001", "category": "lighting", "subtopic": None, "status": "new", "schema": "civic-complaint-v2"}
    assert joint.upgrade(old) is True
    assert old["service"] == "lighting" and old["service_source"] == "table" and old["services"] == []
    assert joint.upgrade(old) is False                      # второй раз — без изменений
    world = {"category": "roads", "service": "water", "service_source": "world", "services": [], "handoffs": [],
             "route_hint": None, "schema": rec.SCHEMA}
    assert joint.upgrade(world) is False and joint.lead_service(world) == "water"


# ---------------------------------------------------------------- передача: срок не начинается заново
def test_handoff_keeps_deadline_through_holidays_and_status(store, clock):
    record = pit(store)
    due = record["due_at"]
    # 10 рабочих дней от чт 22.10: 24–25 — выходные, 26.10 — перенос Дня Республики → 06.11, а не 05.11.
    assert due == "2026-11-06T10:00:00+05:00"
    assert due == rec.iso(workdays.add_working_days(rec.parse_iso(record["created_at"]), 10))
    store.set_status(record["id"], "in_progress", actor="operator1")
    clock.now = datetime(2026, 10, 27, 9, 30, tzinfo=rec.ASTANA_TZ)                   # после праздников
    moved, notified = store.handoff(record["id"], "water", reason_code="first_other_work", role="editor")
    assert notified == 1
    assert moved["due_at"] == due                                                      # срок тот же
    assert moved["status"] == "in_progress"                                            # шага назад нет
    assert (moved["service"], moved["service_source"]) == ("water", "handoff")
    assert moved["passport"]["assignee_id"] == "water"
    assert moved["handoffs"] == [{"at": "2026-10-27T09:30:00+05:00", "from": "road", "to": "water",
                                  "reason": "Сначала работы другой службы", "reason_code": "first_other_work",
                                  "by_role": "operator"}]
    assert [(p["service"], p["role"], p["status"]) for p in moved["services"]] == [("water", "lead", "todo")]
    # Ещё одна передача через неделю — срок всё тот же, «осталось» считается от того же срока.
    clock.now = datetime(2026, 11, 3, 12, 0, tzinfo=rec.ASTANA_TZ)
    back = store.handoff(record["id"], "road", "Водоканал закончил, нужен асфальт", keep=True, role="admin")[0]
    assert back["due_at"] == due and len(back["handoffs"]) == 2 and back["handoffs"][-1]["by_role"] == "admin"
    assert [(p["service"], p["role"]) for p in back["services"]] == [("road", "lead"), ("water", "partner")]
    info = lifecycle.deadline(back, clock.now)
    assert info["state"] == "answered"                                                 # ответ дан при «в работе»


def test_handoff_of_new_complaint_counts_down_same_deadline(store, clock):
    record = pit(store, category="lighting", subtopic=None, text="Не горит фонарь у остановки")
    due = record["due_at"]
    assert due == "2026-10-28T10:00:00+05:00"                       # 3 рабочих дня: 23, 27, 28 (26.10 — праздник)
    clock.now = datetime(2026, 10, 23, 15, 0, tzinfo=rec.ASTANA_TZ)
    moved = store.handoff(record["id"], "power", reason_code="other_service")[0]
    assert moved["due_at"] == due and moved["status"] == "new"
    assert lifecycle.deadline(moved, clock.now)["working_days_left"] == 2               # 27 и 28 — как без передачи
    clock.now = datetime(2026, 10, 28, 11, 0, tzinfo=rec.ASTANA_TZ)
    assert lifecycle.deadline(store.get(record["id"]), clock.now)["state"] == "overdue"  # передача срок не спасает


def test_handoff_validation(store):
    record = pit(store)
    with pytest.raises(RecordError) as exc:
        store.handoff(record["id"], "made_up", "Причина есть")
    assert "to" in exc.value.fields
    with pytest.raises(RecordError) as exc:
        store.handoff(record["id"], "water", "  ")
    assert "reason" in exc.value.fields
    with pytest.raises(RecordError):
        store.handoff(record["id"], "water", reason_code="secret")
    with pytest.raises(RecordError):
        store.handoff(record["id"], "road", "Уже у нас")                               # та же служба
    with pytest.raises(Conflict):
        store.handoff(record["id"], "water", "Причина есть", expected_lead="lighting")  # кто-то уже передал
    with pytest.raises(NotFound):
        store.handoff("c-nothere00", "water", "Причина есть")
    store.set_status(record["id"], "rejected")
    with pytest.raises(Conflict):
        store.handoff(record["id"], "water", "Причина есть")


def test_handoff_to_partner_makes_it_lead_with_its_status(store):
    record = pit(store)
    store.set_services(record["id"], [{"service": "road", "role": "lead"}, {"service": "water", "role": "partner"}])
    store.set_part(record["id"], "water", "in_progress")
    moved = store.handoff(record["id"], "water", "Сначала замена трубы")[0]
    assert [(p["service"], p["role"], p["status"]) for p in moved["services"]] == [("water", "lead", "in_progress")]
    assert moved["status"] == "in_progress"


# ---------------------------------------------------------------- совместное исполнение и части
def test_joint_execution_fixed_only_when_all_parts_done(store, clock):
    record = pit(store)
    store.metoo(record["id"], DEV_B)
    joint_rec, notified = store.set_services(record["id"], [{"service": "water", "role": "lead"},
                                                            {"service": "road", "role": "partner"}], role="editor")
    assert notified == 2
    assert joint_rec["handoffs"][-1]["reason"] == "Совместное исполнение" and joint_rec["handoffs"][-1]["from"] == "road"
    assert joint_rec["status"] == "new" and joint_rec["service_source"] == "joint"
    clock.now += timedelta(hours=2)
    step = store.set_part(record["id"], "water", "done", "Трубу заменили")[0]
    assert step["status"] == "in_progress"                       # ведущая сделала, Дорожная — ещё нет
    with pytest.raises(Conflict) as exc:
        store.set_status(record["id"], "fixed")                   # «исправлено» раньше всех частей — нельзя
    assert exc.value.fields == {"waiting": ["road"]}
    assert store.get(record["id"])["status"] == "in_progress"
    clock.now += timedelta(hours=3)
    done = store.set_part(record["id"], "road", "done", "Асфальт восстановили")[0]
    assert done["status"] == "fixed"
    assert done["resolution"]["state"] == "reported"
    assert done["resolution"]["what_done"] == "Трубу заменили; Асфальт восстановили"
    assert done["due_at"] == record["due_at"]
    # Жители проверяют ремонт как обычно: «Да» → проверено жителями.
    verified, result = store.verify(record["id"], DEV_B, "yes")
    assert result == "recorded" and verified["resolution"]["state"] == "verified"


def test_lead_status_follows_complaint_status_and_reopen(store):
    record = pit(store)
    store.set_services(record["id"], [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}])
    started = store.set_status(record["id"], "in_progress")
    assert [p["status"] for p in started["services"]] == ["in_progress", "todo"]
    store.set_part(record["id"], "road", "done")
    fixed = store.set_status(record["id"], "fixed", what_done="Всё сделали")
    assert fixed["status"] == "fixed" and [p["status"] for p in fixed["services"]] == ["done", "done"]
    # Жители: «Проблема осталась» → снова в работе у ведущей службы, часть Дорожной службы — как была.
    reopened, _ = store.verify(record["id"], DEV_A, "no")
    assert reopened["status"] == "in_progress"
    assert [(p["service"], p["status"]) for p in reopened["services"]] == [("water", "in_progress"), ("road", "done")]


def test_removing_last_pending_partner_closes_complaint(store):
    record = pit(store)
    store.set_services(record["id"], [{"service": "road", "role": "lead"}, {"service": "water", "role": "partner"}])
    store.set_part(record["id"], "road", "done", "Яму засыпали")
    alone = store.set_services(record["id"], [{"service": "road", "role": "lead"}])[0]
    assert alone["status"] == "fixed" and alone["resolution"]["what_done"] == "Яму засыпали"


def test_services_validation(store):
    record = pit(store)
    for bad in ([], "water", [{"service": "water", "role": "lead"}, {"service": "water", "role": "partner"}],
                [{"service": "water", "role": "partner"}],
                [{"service": "water", "role": "lead"}, {"service": "road", "role": "lead"}],
                [{"service": s, "role": "partner"} for s in ("water", "road", "power")] + [{"service": "gas", "role": "lead"}],
                [{"service": "secret", "role": "lead"}], [{"service": "water", "role": "boss"}]):
        with pytest.raises(RecordError):
            store.set_services(record["id"], bad)
    # Ведущая первой, даже если в запросе она не первая.
    ok = store.set_services(record["id"], [{"service": "road", "role": "partner"}, {"service": "water", "role": "lead"}])[0]
    assert [p["service"] for p in ok["services"]] == ["water", "road"]
    # Повтор того же списка — ничего не меняет (и не пишет лишнюю передачу).
    again = store.set_services(record["id"], [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}])[0]
    assert len(again["handoffs"]) == len(ok["handoffs"]) == 1


def test_part_validation(store):
    record = pit(store)
    with pytest.raises(RecordError):
        store.set_part(record["id"], "water", "done")                      # служба не участвует
    with pytest.raises(RecordError):
        store.set_part(record["id"], "road", "почти")
    with pytest.raises(Conflict):
        store.set_part(record["id"], "road", "in_progress", expected="done")
    started = store.set_part(record["id"], "road", "in_progress", "Бригада выехала")[0]
    assert started["status"] == "in_progress" and started["services"][0]["note"] == "Бригада выехала"
    same = store.set_part(record["id"], "road", "in_progress")[0]           # повтор нажатия — без новой строки
    assert len(same["updates"]) == len(started["updates"])
    store.set_status(record["id"], "rejected")
    with pytest.raises(Conflict):
        store.set_part(record["id"], "road", "done")


def test_duplicate_is_not_edited_directly(store):
    original, dup = pit(store), pit(store, DEV_B)
    store.mark_duplicate(dup["id"], original["id"])
    with pytest.raises(Conflict):
        store.handoff(dup["id"], "water", "Причина есть")
    with pytest.raises(Conflict):
        store.set_part(dup["id"], "road", "done")


def test_passport_service_change_is_logged_as_handoff(store):
    record = pit(store)
    chosen = store.update_passport(record["id"], {"service": "water"}, role="editor")[0]
    assert chosen["handoffs"][-1]["reason_code"] == "passport" and chosen["handoffs"][-1]["to"] == "water"
    assert joint.lead_service(chosen) == "water"
    same = store.update_passport(record["id"], {"service": "water", "next_step": "Выезд"})[0]
    assert len(same["handoffs"]) == 1                                      # служба не менялась — передачи нет
    cleared = store.update_passport(record["id"], {"service": ""})[0]
    assert joint.lead_service(cleared) == "road" and cleared["service_source"] == "table"
    assert [h["to"] for h in cleared["handoffs"]] == ["water", "road"]


def test_route_hint_saved_at_creation_and_failure_is_harmless(store):
    calls = []

    def route(**kw):
        calls.append(kw)
        return {"services": [{"service": "water", "score": 0.81, "why_ru": "«после раскопок» — сначала сети"},
                             {"service": "road", "score": 0.77}], "joint": True, "model_version": "r04-route-1"}
    store.route_lookup = route
    record = pit(store)
    assert calls and calls[0]["text"] == PIT and calls[0]["category"] == "roads"
    assert record["route_hint"] == {"services": ["water", "road"], "joint": True, "source": "model",
                                    "model_version": "r04-route-1", "why_ru": "«после раскопок» — сначала сети"}
    accepted = store.set_services(record["id"], [{"service": s, "role": "lead" if i == 0 else "partner"}
                                                 for i, s in enumerate(record["route_hint"]["services"])])[0]
    assert accepted["route_hint"]["accepted_at"] == rec.iso(store._now())
    store.route_lookup = lambda **kw: 1 / 0
    assert pit(store, DEV_C)["route_hint"] is None                         # R04 упал — жалоба принята
    store.route_lookup = lambda **kw: {"services": [{"service": "secret"}]}
    assert pit(store, DEV_B)["route_hint"] is None                         # мусор — подсказки нет



def test_hint_asked_by_card_is_saved_on_accept(store):
    """Жалоба подана до подключения R04 (route_hint нет): карточка сама спросила POST /route, сотрудник «Принять» —
    подсказка сохраняется в route_hint с asked_at и accepted_at; подсказку из записи она не заменяет; мусор — без 500."""
    service = ComplaintsV2Service(store)
    record = pit(store)
    assert record["route_hint"] is None
    offered = {"services": ["water", "road"], "joint": True, "source": "rules", "model_version": "r04-route-1",
               "why_ru": "Раскопки сетей: Водоканал — засыпка, Дорожная служба — покрытие.", "accepted_at": "2020-01-01"}
    both = [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}]
    status, reply = call(service, "POST", f"{P}/{record['id']}/services", {"services": both, "route_hint": offered},
                         Staff(), STAFF_CTX)
    assert status == 200
    hint = store.get(record["id"])["route_hint"]
    now = rec.iso(store._now())
    assert hint["services"] == ["water", "road"] and hint["source"] == "rules" and hint["model_version"] == "r04-route-1"
    assert hint["asked_at"] == now and hint["accepted_at"] == now           # «принята» ставит сервер, не экран
    assert reply["data"]["complaint"]["joint"]["route_hint"]["accepted_at"] == now
    # В записи подсказка уже есть — предложенная с экрана её не заменяет.
    store.route_lookup = lambda **kw: {"services": ["water", "road"], "joint": True, "source": "model"}
    other = pit(store, DEV_B)
    status, _ = call(service, "POST", f"{P}/{other['id']}/services",
                     {"services": [{"service": "road", "role": "lead"}, {"service": "lighting", "role": "partner"}],
                      "route_hint": {"services": ["road", "lighting"], "joint": True}}, Staff(), STAFF_CTX)
    assert status == 200
    kept = store.get(other["id"])["route_hint"]
    assert kept["services"] == ["water", "road"] and kept["source"] == "model" and "accepted_at" not in kept
    # Мусор вместо подсказки: службы меняются, route_hint не появляется, ошибки нет.
    store.route_lookup = None
    for i, junk in enumerate((["water", "road"], "water", {"services": [{"service": "secret"}]}, {"services": "water,road"})):
        fresh = pit(store, f"dev-junk{i:012d}")
        assert fresh["services"] == []                                    # новая жалоба, не склейка с прежней
        status, reply = call(service, "POST", f"{P}/{fresh['id']}/services", {"services": both, "route_hint": junk},
                             Staff(), STAFF_CTX)
        assert status == 200, (junk, reply)
        assert store.get(fresh["id"])["route_hint"] is None

# ---------------------------------------------------------------- чтение для R17 и R16 (без персональных данных)
def test_service_parts_and_handoffs_log_for_r17(store, clock):
    first = pit(store)
    store.set_services(first["id"], [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}])
    clock.now += timedelta(days=1)
    second = pit(store, DEV_B, category="lighting", subtopic=None, text="Не горит фонарь")
    store.set_status(second["id"], "accepted")
    store.handoff(second["id"], "power", reason_code="other_service")
    rows = store.service_parts(days=30)
    assert {r["complaint_id"] for r in rows} == {first["id"], second["id"]}
    by_id = {r["complaint_id"]: r for r in rows}
    assert by_id[first["id"]]["joint"] is True and by_id[first["id"]]["lead"] == "water"
    assert [s["service"] for s in by_id[first["id"]]["services"]] == ["water", "road"]
    assert by_id[second["id"]]["answered_at"] == rec.iso(clock.now) and by_id[second["id"]]["handoffs"] == 1
    flat = json.dumps(rows, ensure_ascii=False)
    assert PIT not in flat and "point" not in flat and "device" not in flat     # без текста, точки, устройства
    log = store.handoffs_log(days=30)
    assert [(h["from"], h["to"]) for h in log] == [("lighting", "power"), ("road", "water")]   # новые сверху
    assert log[0]["reason"] == "Нужна другая служба" and log[0]["by_role"] == "operator"
    assert store.handoffs_log(since=rec.iso(clock.now + timedelta(hours=1))) == []
    assert store.service_parts(days=30, district="esil") == []


def test_yard_complaints_for_r16(store):
    yard = {"kind": "area", "id": "yard-42", "label_ru": "Двор у ул. Коксенгир"}
    in_yard = store.create({"text": "Во дворе сломана лавочка", "category": "yards", "point": POINT,
                            "target": yard}, DEV_A)[0]
    store.metoo(in_yard["id"], DEV_B)
    playground = store.create({"text": "Сломаны качели", "category": "yards", "point": POINT,
                               "target": {"kind": "object", "id": "osm-way-777"}}, DEV_C)[0]
    pit(store)                                                               # чужая цель
    view = store.yard_complaints("yard-42", targets=["osm-way-777"])
    assert {i["id"] for i in view["items"]} == {in_yard["id"], playground["id"]}
    assert view["counts"] == {"open": 2, "fixed": 0, "verified": 0, "total": 2, "people": 3}
    assert "сломана лавочка" not in json.dumps(view, ensure_ascii=False)        # тексты жителей не отдаются
    assert all("text" not in item and "point" not in item for item in view["items"])
    square = [[[71.41, 51.09], [71.42, 51.09], [71.42, 51.095], [71.41, 51.095], [71.41, 51.09]]]
    by_shape = store.yard_complaints("yard-99", polygon={"type": "Polygon", "coordinates": square})
    assert len(by_shape["items"]) == 3                                       # все три точки внутри квадрата


# ---------------------------------------------------------------- HTTP: только сотрудник, житель видит службы
def test_routes_need_staff_and_csrf(store):
    service = ComplaintsV2Service(store)
    record = pit(store)
    for action, body in (("handoff", {"to": "water", "reason": "Нужна другая служба"}),
                         ("services", {"services": [{"service": "water", "role": "lead"}]}),
                         ("part", {"service": "road", "status": "done"})):
        status, reply = call(service, "POST", f"{P}/{record['id']}/{action}", body)
        assert status == 403 and reply["error"]["code"] == "forbidden"
        status, reply = call(service, "POST", f"{P}/{record['id']}/{action}", body, Staff(),
                             {"headers": {"X-CSRF-Token": "bad"}, "host_allowed": True, "is_same_origin": True})
        assert status == 403 and reply["error"]["code"] == "csrf_failed"
        status, reply = call(service, "GET", f"{P}/{record['id']}/{action}", None, Staff(), STAFF_CTX)
        assert status == 405
    assert store.get(record["id"])["handoffs"] == []


def test_scene8_over_http(store):
    """Сцена 8: «яма после раскопок» → подсказка «2 службы» → совместное исполнение → у жителя паспорт с двумя службами."""
    store.route_lookup = lambda **kw: {"services": ["water", "road"], "joint": True, "source": "rules"}
    service = ComplaintsV2Service(store)
    status, reply = call(service, "POST", P, {"text": PIT, "category": "roads", "point": POINT, "target": SEGMENT},
                         ctx={"headers": {"X-Birge-Device": DEV_A}, "host_allowed": True, "is_same_origin": True})
    assert status == 201
    cid = reply["data"]["complaint"]["id"]
    status, reply = call(service, "GET", f"{P}/{cid}", None, Staff(), STAFF_CTX)
    staff = reply["data"]["complaint"]
    assert staff["joint"]["route_hint"]["services"] == ["water", "road"] and staff["joint"]["joint"] is False
    status, reply = call(service, "POST", f"{P}/{cid}/services",
                         {"services": [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}]},
                         Staff(), STAFF_CTX)
    assert status == 200 and reply["data"]["notified"] == 1
    assert reply["data"]["complaint"]["joint"]["joint"] is True
    status, reply = call(service, "POST", f"{P}/{cid}/part",
                         {"service": "water", "status": "done", "note": "Трубу заменили"}, Staff(), STAFF_CTX)
    assert status == 200 and reply["data"]["complaint"]["status"] == "in_progress"
    status, reply = call(service, "POST", f"{P}/{cid}/part", {"service": "road", "status": "in_progress"},
                         Staff(), STAFF_CTX)
    assert status == 200
    status, reply = call(service, "POST", f"{P}/{cid}/status", {"status": "fixed"}, Staff(), STAFF_CTX)
    assert status == 409 and reply["error"]["fields"] == {"waiting": ["road"]}
    # Житель (автор): «Работают 2 службы: Водоканал — сделано · Дорожная служба — в работе», срок тот же.
    status, reply = call(service, "GET", f"{P}/mine", None, None,
                         {"headers": {"X-Birge-Device": DEV_A}, "host_allowed": True, "is_same_origin": True})
    mine = reply["data"]["items"][0]
    assert mine["joint"]["joint"] is True
    assert [(s["service"], s["status"]) for s in mine["joint"]["services"]] == [("water", "done"), ("road", "in_progress")]
    assert mine["joint"]["services"][0]["note"] == "Трубу заменили"
    assert mine["joint"]["handoffs"] == [{"at": mine["joint"]["handoffs"][0]["at"], "from": "road", "to": "water"}]
    flat = json.dumps(mine, ensure_ascii=False)
    assert "Совместное исполнение" not in flat and "operator" not in flat and "by_role" not in flat
    # Чужой житель: те же службы, но без заметок служб и без текста.
    status, reply = call(service, "GET", f"{P}/{cid}", None, None,
                         {"headers": {"X-Birge-Device": DEV_C}, "host_allowed": True, "is_same_origin": True})
    public = reply["data"]["complaint"]
    assert public["joint"]["joint"] is True and "note" not in json.dumps(public["joint"]) and "text" not in public
    # «Обращения» одной службы — ссылка из «Штаба ведомств» R17.
    status, reply = call(service, "GET", f"{P}/inbox?service=road", None, Staff(), STAFF_CTX)
    assert status == 200 and reply["data"]["items"][0]["joint"] is True
    assert [s["service"] for s in reply["data"]["items"][0]["services"]] == ["water", "road"]
    status, reply = call(service, "GET", f"{P}/inbox?service=gas", None, Staff(), STAFF_CTX)
    assert reply["data"]["items"] == []
    status, reply = call(service, "GET", f"{P}/inbox?service=secret", None, Staff(), STAFF_CTX)
    assert status == 422


def test_r15_s49_wrong_types_give_422_not_500(store):
    """R15-S49: список или словарь вместо id службы / кода причины — понятная 422, а не TypeError и 500."""
    service = ComplaintsV2Service(store)
    record = pit(store)
    for action, body in (("services", {"services": [{"service": ["road"], "role": "lead"}]}),
                         ("services", {"services": [{"service": {"id": "road"}, "role": "lead"}]}),
                         ("handoff", {"to": ["water"], "reason": "Нужна другая служба"}),
                         ("handoff", {"to": "water", "reason_code": ["other_service"]}),
                         ("handoff", {"to": "water", "reason": ["список"]}),
                         ("part", {"service": "road", "status": ["done"]}),
                         ("passport", {"service": ["water"]})):
        status, reply = call(service, "POST", f"{P}/{record['id']}/{action}", body, Staff(), STAFF_CTX)
        assert status == 422 and reply["error"]["code"] == "invalid", (action, body, status, reply)
    status, reply = call(service, "GET", f"{P}/inbox?service=%5B%22road%22%5D", None, Staff(), STAFF_CTX)
    assert status == 422
    assert store.get(record["id"])["handoffs"] == []
    assert joint.parse_route_hint({"services": [["water"], {"service": ["road"]}, "road"]}) == \
        {"services": ["road"], "joint": False, "source": "rules", "model_version": None}
    assert lifecycle.is_service("water") and not lifecycle.is_service(["water"]) and not lifecycle.is_service(None)
