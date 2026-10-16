"""R09 · раунд 15+ (поправка П3, сцена 0) · точка входа «ИИ-разбора пачки обращений» R04 → записи жалоб R09.

ui/civic_feedback/v2/intake.py: commit_tasks(db, batch_id, tasks, texts, demo=…) и integration.intake_commit(…).
Задачи — в форме ответа R04 analyze (П3). Тексты и места — синтетические («Пример»).
"""

import json
from datetime import datetime

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, integration, intake, joint, lifecycle
from ui.civic_feedback.v2 import record as rec

KHAN = {"kind": "object", "id": "osm-node-4109037549", "label_ru": "Остановка «Хан Шатыр»",
        "label_kk": "«Хан Шатыр» аялдамасы", "point": [71.406553, 51.131155]}
BAYAN = {"kind": "segment", "id": "osm-w243047611-4", "label_ru": "Участок: улица Баян Сулу"}
TEXTS = {
    "t1": "На остановке Хан Шатыр вечером не горит свет, страшно ждать автобус",
    "t2": "Хан Шатыр аялдамасында кешке жарық жоқ",
    "t3": "остановка хан шатыр темно уже неделю",
    "t4": "Раскопали дорогу на Баян Сулу и бросили, траншея не закопана",
    "t5": "Баян Сулу көшесінде жол қазылып тасталды",
    "t6": "Где-то во дворе течёт вода из люка",
}


def tasks():
    return [
        {"id": "k1", "title_ru": "Нет света на остановке «Хан Шатыр»", "title_kk": "«Хан Шатыр» аялдамасында жарық жоқ",
         "category": "lighting", "services": [{"id": "lighting", "role": "lead"}], "why_ru": "Освещение остановки",
         "why_kk": "Аялдаманы жарықтандыру", "target": KHAN, "address_text": "остановка Хан Шатыр",
         "text_ids": ["t1", "t2", "t3"], "people": 3, "urgent": False, "urgent_why": None},
        {"id": "k2", "title_ru": "Раскопки на Баян Сулу", "title_kk": "Баян Сулу көшесінде қазба", "category": "roads",
         "subtopic": "pothole", "services": [{"id": "water", "role": "lead"}, {"id": "road", "role": "partner"}],
         "why_ru": "Раскопки без восстановления: Водоканал — сети, Дорожная служба — покрытие",
         "why_kk": "Қазбадан кейін жабылмаған: Сумен жабдықтау — желі, Жол қызметі — жабын",
         "target": BAYAN, "point": [71.4135, 51.0915], "address_text": "Баян Сулу", "text_ids": ["t4", "t5"],
         "people": 2, "urgent": True, "urgent_why": "Открытая траншея у дороги"},
        {"id": "k3", "title_ru": "Течёт вода из люка", "title_kk": "Құдықтан су ағып жатыр", "category": "utilities",
         "services": [{"id": "water", "role": "lead"}], "target": None, "address_text": "", "text_ids": ["t6"],
         "people": 1, "urgent": True, "urgent_why": "Люк"},
    ]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 19, 9, 0, tzinfo=rec.ASTANA_TZ)   # понедельник

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    s = ComplaintStore(tmp_path / "intake.sqlite3", clock=Clock())
    yield s
    s.close()


class Staff:
    is_staff = True
    username = "operator1"
    role = "editor"

    def check_csrf(self, value):
        return value == "tok"


def call(service, method, path, body=None, principal=None):
    reply = service.handle(method, path, None, json.dumps(body) if body is not None else None, principal,
                           {"headers": {"X-CSRF-Token": "tok"}, "host_allowed": True, "is_same_origin": True})
    return reply["status"], reply["body"]


def test_tasks_become_working_complaints_with_people_service_and_source(store):
    report = intake.commit_tasks(store, "night-0001", tasks(), TEXTS, demo=True, actor="Сотрудник акимата",
                                 method="r04-intake-1")
    assert [c["task_id"] for c in report["created"]] == ["k1", "k2"]
    assert report["skipped"] == [{"task_id": "k3", "reason": "no_place"}]        # без места — «адрес уточнить»
    assert report["existing"] == [] and report["total"] == 3 and report["people"] == 5
    khan = store.get(report["created"][0]["id"])
    assert khan["code"] == "B-0001" and khan["id"] == intake.intake_id("night-0001", "k1")
    assert khan["text"] == TEXTS["t1"]                         # оригинал первого обращения группы, не заголовок
    assert khan["status"] == "new" and khan["demo"] is True and rec.reporters(khan) == 3
    assert (khan["service"], khan["service_source"]) == ("lighting", "intake")
    assert khan["category_source"] == "model" and khan["model"]["label"] == "lighting"
    assert khan["target"]["id"] == KHAN["id"] and khan["point"] == KHAN["point"]
    assert khan["due_at"] == rec.due_at(khan["created_at"], "lighting")
    assert khan["source"] == "intake"
    assert khan["intake"] == {"batch_id": "night-0001", "task_id": "k1", "people": 3, "urgent": False,
                              "urgent_why": None, "urgent_why_kk": None, "method": "r04-intake-1",
                              "at": khan["created_at"], "by": "Сотрудник акимата"}
    # Ведущая служба — явная: таблица R08 её не меняет (выбор подтвердил сотрудник «Создать задачи»).
    r08 = lambda c, s: {"id": "akimat", "ru": "Аппарат акима района"}
    assert joint.lead_service(khan, r08) == "lighting"
    pit = store.get(report["created"][1]["id"])
    assert pit["code"] == "B-0002" and rec.reporters(pit) == 2 and pit["service"] == "water"
    # Две службы — подсказка «Похоже, нужны 2 службы» (принять решает сотрудник), как у жалобы жителя.
    assert pit["route_hint"]["services"] == ["water", "road"] and pit["route_hint"]["joint"] is True
    assert pit["route_hint"]["why_ru"].startswith("Раскопки без восстановления")
    assert pit["services"] == [] and not joint.is_joint(pit)
    assert pit["intake"]["urgent"] is True and pit["intake"]["urgent_why"] == "Открытая траншея у дороги"


def test_repeated_commit_of_the_same_batch_creates_nothing_new(store):
    first = intake.commit_tasks(store, "night-0002", tasks()[:1], TEXTS)
    again = intake.commit_tasks(store, "night-0002", tasks(), TEXTS)        # целиком, после части
    assert [c["task_id"] for c in first["created"]] == ["k1"]
    assert [c["task_id"] for c in again["created"]] == ["k2"]
    assert again["existing"] == [{"task_id": "k1", "id": first["created"][0]["id"], "code": "B-0001"}]
    third = intake.commit_tasks(store, "night-0002", tasks(), TEXTS)
    assert third["created"] == [] and len(third["existing"]) == 2
    assert len(store.list()) == 2
    assert store.get(first["created"][0]["id"])["metoo"] == 2               # «Я тоже» не удвоились
    # Та же задача в другой пачке — другая запись (пачки независимы).
    other = intake.commit_tasks(store, "night-0003", tasks()[:1], TEXTS)
    assert other["created"][0]["id"] != first["created"][0]["id"]


def test_bad_tasks_are_skipped_with_reasons_and_the_batch_goes_on(store):
    bad = [
        {"id": "x1", "category": "weather", "point": KHAN["point"], "text_ids": ["t1"]},       # нет такой категории
        {"id": "x2", "category": "lighting", "point": [76.9, 43.2], "text_ids": ["t1"]},       # Алматы — вне Астаны
        {"id": "x3", "category": "lighting", "point": KHAN["point"], "text_ids": ["nope"], "title_ru": "Ок"},
        {"id": "x 4", "category": "lighting", "point": KHAN["point"], "text_ids": ["t1"]},     # неверный id задачи
        "строка вместо задачи",
        {"id": "x5", "category": "lighting", "point": KHAN["point"], "text_ids": ["missing"],
         "title_ru": "Нет света у остановки"},                                                 # текста нет — заголовок
    ]
    report = intake.commit_tasks(store, "night-0004", bad, TEXTS)
    assert [s["reason"] for s in report["skipped"]] == ["category", "no_place", "text", "invalid", "invalid"]
    assert [c["task_id"] for c in report["created"]] == ["x5"]
    assert store.get(report["created"][0]["id"])["text"] == "Нет света у остановки"
    with pytest.raises(ValueError):
        intake.commit_tasks(store, "x", tasks(), TEXTS)                       # batch_id
    with pytest.raises(ValueError):
        intake.commit_tasks(store, "night-0005", {"id": "k1"}, TEXTS)        # не список
    with pytest.raises(ValueError):
        intake.commit_tasks(store, "night-0006", [tasks()[0]] * (intake.MAX_TASKS + 1), TEXTS)


def test_texts_as_list_long_text_clipped_people_capped_and_unknown_service_falls_back(store):
    lines = ["x" * 10, "Очень длинное обращение " + "про свет " * 400]
    task = {"id": 7, "category": "lighting", "services": [{"id": "nasa", "role": "lead"}], "point": KHAN["point"],
            "text_ids": [1], "people": 10_000}
    report = intake.commit_tasks(store, "night-0007", [task], lines)
    record = store.get(report["created"][0]["id"])
    assert len(record["text"]) <= rec.TEXT_MAX and record["text"].endswith("…")
    assert record["service"] == lifecycle.default_service("lighting", None)   # чужой id службы — по таблице
    assert rec.reporters(record) == intake.MAX_PEOPLE + 1                       # не больше 400 «Я тоже»
    assert record["intake"]["task_id"] == "7"


def test_created_events_reach_subscribers_after_commit(store):
    seen = []
    store.subscribe(seen.append)
    report = intake.commit_tasks(store, "night-0008", tasks(), TEXTS, demo=True)
    assert [e["type"] for e in seen] == ["created", "created"]
    assert [e["complaint_id"] for e in seen] == [c["id"] for c in report["created"]]
    assert seen[0]["reporters"] == 3 and seen[0]["demo"] is True
    assert [e["complaint_id"] for e in store.events_since(0)] == [c["id"] for c in report["created"]]
    intake.commit_tasks(store, "night-0008", tasks(), TEXTS, demo=True)
    assert len(seen) == 2                                                      # повтор — без событий


def test_inbox_marks_intake_and_keeps_demo_intake_workable(store):
    service = ComplaintsV2Service(store)
    report = integration.intake_commit(service, "night-0009", tasks(), TEXTS, demo=True)
    status, body = call(service, "GET", "/api/civic/v2/complaints/inbox", principal=Staff())
    assert status == 200
    groups = {g["target"]["id"]: g for g in body["data"]["items"]}
    khan = groups[KHAN["id"]]
    assert khan["intake"] is True and khan["complaints"][0]["intake"] is True
    assert khan["people"] == 3 and khan["demo"] is True
    # Пример пачки — рабочий: сотрудник берёт его в работу (не «только просмотр», как demo_seed «Хан Шатыр»).
    cid = report["created"][0]["id"]
    status, body = call(service, "POST", f"/api/civic/v2/complaints/{cid}/status", {"status": "in_progress"},
                        principal=Staff())
    assert status == 200 and store.get(cid)["status"] == "in_progress"
    # Карточка сотрудника видит источник; жители и карта — нет.
    status, body = call(service, "GET", f"/api/civic/v2/complaints/{cid}", principal=Staff())
    assert status == 200 and body["data"]["complaint"]["intake"]["batch_id"] == "night-0009"
    assert "intake" not in rec.public_view(store.get(cid))
    status, body = call(service, "GET", f"/api/civic/v2/complaints/{cid}")
    assert status == 200 and "intake" not in json.dumps(body, ensure_ascii=False)


def test_accepting_the_two_services_hint_makes_joint_execution(store):
    service = ComplaintsV2Service(store)
    report = intake.commit_tasks(store, "night-0010", tasks(), TEXTS)
    cid = report["created"][1]["id"]
    status, body = call(service, "POST", f"/api/civic/v2/complaints/{cid}/services",
                        {"services": [{"service": "water", "role": "lead"}, {"service": "road", "role": "partner"}],
                         "expected_lead": "water"}, principal=Staff())
    assert status == 200, body
    record = store.get(cid)
    assert joint.is_joint(record) and [p["service"] for p in joint.parts(record)] == ["water", "road"]
    assert record["route_hint"].get("accepted_at")


def test_target_is_checked_by_the_map_when_the_map_is_connected(store):
    far = dict(KHAN, point=[71.50, 51.20])               # точка задачи далеко от остановки
    lookup_calls = []

    def lookup(target):
        lookup_calls.append(target["id"])
        if target["id"] == KHAN["id"]:
            return {"geometry": {"type": "Point", "coordinates": KHAN["point"]}, "label_ru": "Остановка «Хан Шатыр»",
                    "label_kk": "«Хан Шатыр» аялдамасы", "object_kind": "bus_stop"}
        return None

    store.target_lookup = lookup
    near = intake.commit_tasks(store, "night-0011", tasks()[:1], TEXTS)
    record = store.get(near["created"][0]["id"])
    assert record["target"]["label_ru"] == "Остановка «Хан Шатыр»" and record["target"]["object_kind"] == "bus_stop"
    moved = dict(tasks()[0], id="k9", target=far, point=far["point"])
    report = intake.commit_tasks(store, "night-0011", [moved], TEXTS)
    placed = store.get(report["created"][0]["id"])
    assert placed["target"]["kind"] == "area" and placed["target"]["approximate"] is True   # дальше 300 м — примерно
    assert KHAN["id"] in lookup_calls


def test_district_comes_from_the_task_or_the_map_districts(store):
    given = dict(tasks()[0], id="d1", district="nura")
    report = intake.commit_tasks(store, "night-0012", [given], TEXTS)
    assert store.get(report["created"][0]["id"])["district"] == "nura"
    try:
        from ui.civic_heat.geo import district_of
        expected = district_of(KHAN["point"])
    except Exception:  # noqa: BLE001 — R07 нет в дереве: район не обязателен
        expected = None
    report = intake.commit_tasks(store, "night-0012", [dict(tasks()[0], id="d2")], TEXTS)
    assert store.get(report["created"][0]["id"])["district"] == expected


def test_r04_contract_shape_and_alias_create_from_intake(store):
    # Форма задачи из INTEGRATION R04 §9.1: services с name_*, joint, urgent_why_ru / _kk, point задачи, target без точки.
    task = {"id": "r04-1", "title_ru": "Нет света на остановке", "title_kk": "Аялдамада жарық жоқ", "category": "lighting",
            "subtopic": None, "services": [{"id": "lighting", "role": "lead", "name_ru": "Служба освещения",
                                            "name_kk": "Жарықтандыру қызметі"}],
            "joint": False, "why_ru": "Освещение", "why_kk": "Жарық", "target": {k: KHAN[k] for k in ("kind", "id", "label_ru")},
            "point": KHAN["point"], "address_text": "Хан Шатыр", "text_ids": ["t1", "t2"], "people": 2,
            "urgent": True, "urgent_why_ru": "Темно на остановке у дороги", "urgent_why_kk": "Жол жиегіндегі аялдамада қараңғы"}
    report = integration.create_from_intake(store, [task], batch_id="night-0013",
                                            texts=[{"id": "t1", "text": "Свет не горит, номер +7 *** *** ** **"},
                                                   {"id": "t2", "text": "Темно"}], demo=True)
    assert [c["task_id"] for c in report["created"]] == ["r04-1"]
    record = store.get(report["created"][0]["id"])
    assert record["text"] == "Свет не горит, номер +7 *** *** ** **"       # то, что дал R04 после moderate()
    assert record["intake"]["urgent_why"] == "Темно на остановке у дороги"
    assert record["intake"]["urgent_why_kk"] == "Жол жиегіндегі аялдамада қараңғы"
    assert rec.reporters(record) == 2 and record["service"] == "lighting" and record["route_hint"]["joint"] is False
