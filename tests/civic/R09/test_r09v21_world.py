"""R09 · раунд 15 · демо-мир (CONTRACT §11): seed_world(db_path, records, now) — идемпотентно, время от засева,
части служб и передачи, «Я тоже», статусы; жалобы «Хан Шатыр» шага 2 демо остаются. Лента R06 (§5.8)."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, joint, lifecycle
from ui.civic_feedback.v2 import record as rec
from ui.civic_feedback.v2.demo_seed import seed_demo
from ui.civic_feedback.v2.integration import handoffs, seed_world, service_parts, updates, yard_complaints
from ui.civic_feedback.v2.world_seed import scene_complaint, world_id

WORLD = Path(__file__).parent / "fixtures" / "world_sample_r09.json"
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=rec.ASTANA_TZ)


@pytest.fixture
def world():
    return json.loads(WORLD.read_text(encoding="utf-8"))


def test_seed_world_inserts_valid_and_reports_invalid(tmp_path, world):
    db = tmp_path / "world.sqlite3"
    report = seed_world(db, world, now=NOW)
    assert (report["inserted"], report["skipped"], report["total"]) == (5, 0, 7)
    assert len(report["invalid"]) == 2 and any("spaceships" in r for r in report["invalid"])
    kept = seed_world(db, world, now=NOW + timedelta(hours=5), reset=False)
    assert (kept["inserted"], kept["skipped"], kept["reset"]) == (0, 5, 0)        # только добавить — ничего не дублирует
    again = seed_world(db, world, now=NOW + timedelta(hours=5))
    assert (again["inserted"], again["skipped"], again["reset"]) == (0, 0, 5)     # по умолчанию — к виду мира от нового now
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        items = store.list(include_duplicates=True)
        assert len(items) == 5 and all(r["demo"] is True for r in items)
        assert all(r["schema"] == rec.SCHEMA and r["service_source"] == "world" for r in items)
        assert len({r["code"] for r in items}) == 5
    finally:
        store.close()


def test_times_are_relative_to_seeding_and_deadline_is_computed(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    seed_world(db, world, now=NOW)
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        pit = store.get(world_id("w-c-pit"))
        assert pit["created_at"] == rec.iso(NOW - timedelta(hours=51))
        assert pit["due_at"] == rec.due_at(pit["created_at"], "roads")          # срок — кодом, рабочие дни РК
        assert pit["metoo"] == 6 and rec.reporters(pit) == 7
        times = store.metoo_times([pit["id"]])[pit["id"]]
        assert len(times) == 6 and all(pit["created_at"] <= t <= rec.iso(NOW) for t in times)
        assert pit["route_hint"]["services"] == ["water", "road"] and pit["route_hint"]["joint"] is True
        assert joint.lead_service(pit) == "road" and pit["services"] == []
        assert pit["world"] == {"id": "w-c-pit", "scene": "scene8", "event": None} and pit["scene"] == "scene8"
        assert scene_complaint(store, "scene8")["id"] == pit["id"]
        # «Я тоже» мира — устройства по формуле R02 (SCHEMA §2.3), времена — из metoo_times.
        assert [t for t in times] == [rec.iso(NOW - timedelta(hours=h)) for h in (50, 40, 30, 20, 10, 2)]
    finally:
        store.close()


def test_joint_parts_handoffs_and_resolutions_from_world(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    seed_world(db, world, now=NOW)
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        jr = store.get(world_id("w-c-joint-done"))
        assert [(p["service"], p["role"], p["status"]) for p in jr["services"]] == \
               [("water", "lead", "done"), ("road", "partner", "in_progress")]
        assert jr["status"] == "in_progress" and jr["services"][0]["note"] == "Трубу заменили"
        assert jr["handoffs"][0]["from"] == "road" and jr["handoffs"][0]["at"] == rec.iso(NOW - timedelta(days=7))
        assert [h["status"] for h in jr["status_history"]] == ["new", "accepted", "in_progress"]
        assert jr["passport"]["assignee_id"] == "water" and jr["passport"]["fix_eta"] == (NOW.date() + timedelta(days=6)).isoformat()
        assert jr["passport"]["delay"]["needs_decision"] is True and len(jr["passport"]["delay"]["options"]) == 2
        assert jr["passport"]["delay"]["reason"] == "Асфальтовый завод закрыт до весны"
        assert jr["updates"] == [{"at": rec.iso(NOW - timedelta(days=3)), "kind": "note", "text": "Водоканал заменил трубу"}]
        verified = store.get(world_id("w-c-verified"))
        assert verified["status"] == "fixed" and verified["resolution"]["state"] == "verified"
        assert lifecycle.heat_state(verified, NOW) is None                      # проверено 9 дней назад — остыло
        reopened = store.get(world_id("w-c-reopened"))
        assert reopened["status"] == "in_progress" and reopened["resolution"]["state"] == "reopened"
        assert lifecycle.heat_state(reopened, NOW) == "reopened"
        # «Я тоже» мира не могут проверить чужие: проверка — только для участников до «служба сообщила».
        assert store.can_verify(verified["id"], "dev-presenter-000001") is False
        # Числа для R17 и R16 — из тех же записей.
        rows = {r["complaint_id"]: r for r in service_parts(store, days=60)}
        assert rows[jr["id"]]["joint"] is True and rows[jr["id"]]["lead"] == "water"
        assert [h["to"] for h in handoffs(store, days=60)] == ["water"]
        yard = yard_complaints(store, "yard-42")
        assert yard["counts"] == {"open": 1, "fixed": 1, "verified": 1, "total": 2, "people": 8}
    finally:
        store.close()


def test_reset_returns_world_to_initial_state_after_rehearsal(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    seed_world(db, world, now=NOW)
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        cid = world_id("w-c-pit")
        store.set_services(cid, [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}])
        store.metoo(cid, "dev-presenter-000001")
        assert store.get(cid)["metoo"] == 7
    finally:
        store.close()
    later = NOW + timedelta(days=1)
    report = seed_world(db, world, now=later)
    assert (report["inserted"], report["reset"]) == (0, 5)
    store = ComplaintStore(db, clock=lambda: later)
    try:
        fresh = store.get(cid)
        assert fresh["services"] == [] and fresh["handoffs"] == [] and fresh["metoo"] == 6
        assert fresh["created_at"] == rec.iso(later - timedelta(hours=51))          # снова «свежая» к показу
        assert store.metoo_times([cid])[cid] and len(store.metoo_times([cid])[cid]) == 6
    finally:
        store.close()


def test_real_complaints_are_never_touched_by_reset(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        real = store.create({"text": "Настоящая жалоба жителя", "category": "roads", "point": [71.41, 51.09]},
                            "dev-real-000000000001")[0]
    finally:
        store.close()
    seed_world(db, world, now=NOW, reset=True)
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        assert store.get(real["id"])["text"] == "Настоящая жалоба жителя" and store.get(real["id"])["demo"] is False
    finally:
        store.close()


def test_khan_shatyr_demo_stays_with_world(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        seed_demo(store)
        seed_world(store, world, now=NOW)
        khan = [r for r in store.list() if r["target"]["id"] == "osm-node-4109037549"]
        assert len(khan) == 2 and {r["category"] for r in khan} == {"lighting", "transport"}
        seed_demo(store)                                                          # шлюз зовёт при каждом запуске
        assert len(store.list()) == 7
    finally:
        store.close()



def test_example_goes_after_world_complaints_in_its_inbox_group(tmp_path, world):
    """Цель «Хан Шатыр»: пример шага 2 (demo без мира — только просмотр) и жалоба мира в одной группе «Обращений»:
    первой идёт жалоба мира — карточка и части служб строки открываются на ней (как быстрые действия строки)."""
    import copy
    from ui.civic_feedback.v2.demo_seed import KHAN_SHATYR, KHAN_SHATYR_POINT
    stop = copy.deepcopy(next(c for c in world["complaints"] if c["id"] == "w-c-esil"))
    stop.update({"id": "w-c-khan-bus", "text": "Автобус не приходит по 40 минут", "category": "transport",
                 "subtopic": None, "target": dict(KHAN_SHATYR), "point": list(KHAN_SHATYR_POINT), "district": "nura",
                 "metoo": 0, "metoo_times": [], "service": "transport"})
    sample = {**world, "complaints": [stop]}
    db = tmp_path / "w.sqlite3"
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        seed_world(store, sample, now=NOW)
        seed_demo(store)                       # шлюз сеет примеры при запуске — порядок любой
        service = ComplaintsV2Service(store)

        class Staff:
            is_staff, username, role = True, "operator1", "editor"

            def check_csrf(self, value):
                return True

        reply = service.handle("GET", "/api/civic/v2/complaints/inbox", None, None, Staff(),
                               {"headers": {"X-CSRF-Token": "t"}, "host_allowed": True, "is_same_origin": True})
        group = next(g for g in reply["body"]["data"]["items"] if g["key"] == "osm-node-4109037549|transport")
        assert [(c["demo"], c["world"]) for c in group["complaints"]] == [(True, True), (True, False)]
        assert group["world"] is True and group["services"][0]["service"] == "transport"
    finally:
        store.close()

def test_seed_world_notifies_listeners_once(tmp_path, world):
    store = ComplaintStore(tmp_path / "w.sqlite3", clock=lambda: NOW)
    seen = []
    store.subscribe(seen.append)
    try:
        seed_world(store, world, now=NOW)
        assert [e["type"] for e in seen] == ["world_seeded"]                     # карта R07 сбрасывает кэш один раз
        assert store.events_since(0) == []                                        # в «пульс» засев не попадает
    finally:
        store.close()


def test_updates_feed_for_r06(tmp_path):
    clock = {"now": NOW}
    store = ComplaintStore(tmp_path / "f.sqlite3", clock=lambda: clock["now"])
    try:
        record = store.create({"text": "Яма после раскопок, не закопали", "category": "roads",
                               "point": [71.4135, 51.0915]}, "dev-feed-0000000001")[0]
        since = rec.iso(clock["now"])
        clock["now"] += timedelta(hours=1)
        store.set_services(record["id"], [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}])
        clock["now"] += timedelta(hours=1)
        store.set_part(record["id"], "water", "done", "Трубу заменили")
        events = updates("dev-feed-0000000001", since, store)
        kinds = [e["event"] for e in events]
        assert kinds == ["part", "status", "services"]                     # новые сверху; часть — раньше статуса
        assert all(e["module"] == "R09" and e["kind"] == "complaint.update" for e in events)
        assert all(e["link"].startswith("#mine/event=") for e in events)
        part = next(e for e in events if e["event"] == "part")
        assert part["title_ru"] == "Водоканал — сделано" and part["title_kk"] == "Сумен жабдықтау қызметі — орындалды"
        joint_e = next(e for e in events if e["event"] == "services")
        assert joint_e["title_ru"] == "Работают 2 службы" and joint_e["title_kk"] == "2 қызмет жұмыс істейді"
        flat = json.dumps(events, ensure_ascii=False)
        assert "Совместное исполнение" not in flat and "operator" not in flat
        assert updates("dev-nobody-00000000001", since, store) == []
        assert updates("bad device", since, store) == []
    finally:
        store.close()


def test_world_complaints_appear_in_staff_inbox_and_counts_match(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    seed_world(db, world, now=NOW)
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        service = ComplaintsV2Service(store)

        class Staff:
            is_staff = True
            username, role = "operator1", "editor"

            def check_csrf(self, value):
                return True
        reply = service.handle("GET", "/api/civic/v2/complaints/inbox", None, None, Staff(),
                               {"host_allowed": True, "is_same_origin": True})
        data = reply["body"]["data"]
        open_ids = {c["id"] for g in data["items"] for c in g["complaints"]}
        expected = {r["id"] for r in store.list() if lifecycle.inbox_tab(r, NOW)}
        assert open_ids == expected and len(open_ids) == 4                        # исправленное и проверенное — нет
        joint_rows = [g for g in data["items"] if g["joint"]]
        assert len(joint_rows) == 1 and [s["service"] for s in joint_rows[0]["services"]] == ["water", "road"]
    finally:
        store.close()


def test_inbox_district_filter(tmp_path, world):
    db = tmp_path / "w.sqlite3"
    seed_world(db, world, now=NOW)
    store = ComplaintStore(db, clock=lambda: NOW)
    try:
        service = ComplaintsV2Service(store)

        class Staff:
            is_staff = True
            username, role = "operator1", "editor"

            def check_csrf(self, value):
                return True
        ctx = {"host_allowed": True, "is_same_origin": True}
        nura = service.handle("GET", "/api/civic/v2/complaints/inbox?district=nura", None, None, Staff(), ctx)["body"]["data"]
        esil = service.handle("GET", "/api/civic/v2/complaints/inbox?district=esil", None, None, Staff(), ctx)["body"]["data"]
        assert nura["district"] == "nura" and sum(nura["counts"].values()) == 3 and sum(esil["counts"].values()) == 1
        bad = service.handle("GET", "/api/civic/v2/complaints/inbox?district=Nura!", None, None, Staff(), ctx)
        assert bad["status"] == 422
    finally:
        store.close()


# Мир R02 в сборке (data/civic/astana/demo-world/, или CIVIC_DEMO_WORLD_PATH): числа «Обращений» = EXPECTED.json R02.
# В ветке R09 файлов мира нет (это пути R02) — тогда проверка пропускается; в сборке R01 она идёт.
def _r02_world():
    import os
    root = Path(__file__).resolve().parents[3] / "data" / "civic" / "astana" / "demo-world"
    world = Path(os.environ.get("CIVIC_DEMO_WORLD_PATH") or root / "world_v1.json")
    expected = world.with_name("EXPECTED.json")
    if not world.exists() or not expected.exists():
        pytest.skip("мира R02 нет в этом дереве (data/civic/astana/demo-world/ — пути R02)")
    return json.loads(world.read_text(encoding="utf-8")), json.loads(expected.read_text(encoding="utf-8"))


def test_r02_world_counts_match_expected(tmp_path):
    world, expected = _r02_world()
    # R09 r15: «Ждут проверки» — только ремонты последних 14 дней (предложение R02). EXPECTED, посчитанный по прежнему
    # правилу (без поля inbox.waiting_check_days), честно пропускаем с причиной — R02 пересчитывает его кодом R09.
    if expected.get("inbox", {}).get("waiting_check_days") != lifecycle.WAITING_CHECK_DAYS:
        pytest.skip("EXPECTED.json R02 посчитан со старым правилом «Ждут проверки» (нет inbox.waiting_check_days=14)")
    now = rec.parse_iso(expected["now"])
    report = seed_world(tmp_path / "r02.sqlite3", world, now=now)
    assert report["invalid"] == [] and report["inserted"] == len(world["complaints"])
    store = ComplaintStore(tmp_path / "r02.sqlite3", clock=lambda: now)
    try:
        records = store.list(status=list(rec.OPEN_STATUSES) + ["fixed"])
        assert lifecycle.inbox(records, now)["counts"] == expected["inbox"]["city"]
        nura = lifecycle.inbox([r for r in records if r.get("district") == "nura"], now)
        assert nura["counts"] == expected["inbox"]["nura"] and len(nura["items"]) == expected["inbox"]["nura_groups"]
        scene8 = expected.get("scenes", {}).get("scene8") or world.get("scenes", {}).get("scene8") or {}
        if scene8.get("complaint"):
            pit = store.get(scene8["complaint"])
            assert pit is not None and pit["route_hint"] and len(pit["route_hint"]["services"]) == 2
    finally:
        store.close()


def test_r17_reader_and_r06_call_convention(tmp_path, world):
    """Стыки соседей: R17 ui/civic_agencies/sources.py ищет ui.civic_feedback.v2.agencies.records_for_agencies;
    R06 ui/civic_store/notify.py зовёт integration.updates(device, since, db=<путь>) — по сигнатуре."""
    import inspect
    from ui.civic_feedback.v2 import agencies, integration
    db = tmp_path / "w.sqlite3"
    seed_world(db, world, now=NOW)
    rows = agencies.records_for_agencies(str(db))
    assert len(rows) == 5 and agencies.agency_records is agencies.records_for_agencies
    joint_row = next(r for r in rows if r["joint"])
    assert joint_row["service"] == "water" and [s["service"] for s in joint_row["services"]] == ["water", "road"]
    assert joint_row["handoffs"][0]["to"] == "water" and joint_row["passport"] == {"assignee_id": "water"}
    flat = json.dumps(rows, ensure_ascii=False)
    for private in ("Прорыв трубы", "point", "device", "photos", "Водоканал заменил трубу"):
        assert private not in flat, private
    assert "db" in inspect.signature(integration.updates).parameters        # R06 передаёт db=<путь> по имени
    assert integration.updates("dev-nobody-00000000001", None, db=str(db)) == []
