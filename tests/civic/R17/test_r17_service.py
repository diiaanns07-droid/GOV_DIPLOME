"""R17 · сервис штаба (make_service(db).handle): права, кризис от создания до закрытия, публичная часть, лента жителя."""

from datetime import datetime, timedelta, timezone

import pytest

import ui.civic_agencies as agencies
from ui.civic_agencies import api_state, demo, service as svc_mod
from ui.civic_agencies.store import AgencyStore

P = "/api/civic/v2"
OK_CTX = {"headers": {"X-CSRF-Token": "tok"}, "host_allowed": True, "is_same_origin": True}


class Staff:
    role, is_staff, username = "editor", True, "operator-login"

    def check_csrf(self, value):
        return value == "tok"


class Resident:
    role, is_staff = "viewer", False

    def check_csrf(self, value):
        return True


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def service(tmp_path, clock, monkeypatch):
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    return agencies.make_service(str(tmp_path / "civic.sqlite3"), clock=clock, demo=True)


def call(service, method, path, body=None, principal=None, ctx=OK_CTX, query=""):
    return service.handle(method, P + path, query, body, principal, ctx)


# ---------------------------------------------------------------- права
@pytest.mark.parametrize("path", ["/agencies/board", "/agencies/joint", "/agencies/handoffs"])
def test_staff_reads_need_session(service, path):
    assert call(service, "GET", path)["status"] == 401
    assert call(service, "GET", path, principal=Resident())["status"] == 403
    assert call(service, "GET", path, principal=Staff(), ctx={"headers": {}, "host_allowed": True})["status"] == 200


@pytest.mark.parametrize("path,body", [
    ("/incidents", {"kind": "blizzard", "zone": {"kind": "district", "district": "esil"}}),
    ("/incidents/inc-demo-blizzard-nura/task", {"service": "gas", "text_ru": "Проверить газ"}),
    ("/incidents/inc-demo-blizzard-nura/update", {"text_ru": "Работаем", "text_kk": "Жұмыс істеп жатырмыз"}),
    ("/incidents/inc-demo-blizzard-nura/close", {"result_ru": "Готово", "result_kk": "Дайын"}),
])
def test_writes_need_staff_csrf_and_same_origin(service, path, body):
    assert call(service, "POST", path, body)["status"] == 401
    assert call(service, "POST", path, body, Resident())["status"] == 403
    no_csrf = call(service, "POST", path, body, Staff(), ctx={"headers": {}, "host_allowed": True})
    assert no_csrf["status"] == 403 and no_csrf["body"]["error"] == "csrf_failed"
    cross = call(service, "POST", path, body, Staff(), ctx={**OK_CTX, "is_same_origin": False})
    assert cross["status"] == 403 and cross["body"]["error"] == "cross_origin"
    foreign_host = call(service, "POST", path, body, Staff(), ctx={**OK_CTX, "host_allowed": False})
    assert foreign_host["status"] == 403


def test_public_incident_hides_internal_parts(service):
    listed = call(service, "GET", "/incidents")["body"]["items"]
    detail = call(service, "GET", "/incidents/inc-demo-blizzard-nura")["body"]["incident"]
    for view in listed + [detail]:
        for secret in ("tasks", "progress", "journal", "revision"):
            assert secret not in view
        for update in view["updates"]:
            assert set(update) == {"id", "at", "kind", "text_ru", "text_kk"}
    # Заметка штаба (public: false) жителю не видна, публичные — видны.
    texts = [u["text_ru"] for u in detail["updates"]]
    assert not any("бригады переведены" in t for t in texts) and len(texts) == 2
    staff = call(service, "GET", "/incidents/inc-demo-blizzard-nura", principal=Staff())["body"]["incident"]
    assert len(staff["tasks"]) == 4 and len(staff["updates"]) == 3
    assert all(set(entry) == {"at", "action", "by_role", "detail"} for entry in staff["journal"])
    assert "operator-login" not in repr(staff)          # в журнале роль, а не логин


def test_detail_has_zone_geometry_from_osm_district(service):
    detail = call(service, "GET", "/incidents/inc-demo-blizzard-nura")["body"]["incident"]
    assert detail["zone"]["kind"] == "district" and detail["zone"]["district"] == "nura"
    assert detail["geometry"]["features"][0]["properties"] == {"id": "nura", "kind": "district"}
    west, south, east, north = detail["bbox"]
    assert 70.9 < west < east < 71.9 and 50.9 < south < north < 51.4


# ---------------------------------------------------------------- кризис: создать → вести → закрыть
def test_crisis_lifecycle(service, clock):
    staff = Staff()
    created = call(service, "POST", "/incidents", {
        "kind": "heat_outage", "zone": {"kind": "district", "district": "esil"},
        "update": {"text_ru": "Ищем место аварии", "text_kk": "Апат болған жерді іздеп жатырмыз"}}, staff)
    assert created["status"] == 201
    incident = created["body"]["incident"]
    assert incident["title_ru"] == "Авария теплосети" and incident["status"] == "active"
    assert [t["service"] for t in incident["tasks"]] == ["heating", "housing", "emergency", "akimat"]
    assert incident["demo"] is True                      # демо-сборка: «Пример»
    iid, task = incident["id"], incident["tasks"][0]["id"]

    clock.now += timedelta(minutes=10)
    moved = call(service, "POST", f"/incidents/{iid}/task", {"task_id": task, "status": "done", "expected": "todo"}, staff)
    assert moved["status"] == 200
    assert moved["body"]["incident"]["progress"][0] == {"service": "heating", "done": 1, "doing": 0, "total": 1}
    stale = call(service, "POST", f"/incidents/{iid}/task", {"task_id": task, "status": "doing", "expected": "todo"}, staff)
    assert stale["status"] == 409 and stale["body"]["current"] == "done"

    note = call(service, "POST", f"/incidents/{iid}/update", {"text_ru": "Внутренняя заметка", "public": False}, staff)
    assert note["status"] == 200
    one_lang = call(service, "POST", f"/incidents/{iid}/update", {"text_ru": "Только по-русски"}, staff)
    assert one_lang["status"] == 422 and one_lang["body"]["field"] == "text_kk"

    clock.now += timedelta(hours=3)
    closed = call(service, "POST", f"/incidents/{iid}/close",
                  {"result_ru": "Тепло вернули во все дома", "result_kk": "Барлық үйге жылу берілді"}, staff)
    assert closed["status"] == 200
    body = closed["body"]["incident"]
    assert body["status"] == "closed" and body["result"]["text_kk"] == "Барлық үйге жылу берілді"
    assert body["updates"][0]["kind"] == "closed"        # итог — последнее публичное обновление
    after = call(service, "POST", f"/incidents/{iid}/update", {"text_ru": "Ещё", "text_kk": "Тағы"}, staff)
    assert after["status"] == 409 and after["body"]["error"] == "closed"
    actions = [e["action"] for e in reversed(body["journal"])]
    assert actions == ["incident.create", "update.add", "task.status", "update.add", "incident.close"]


@pytest.mark.parametrize("text,code", [
    ("Звоните +7 701 123 45 67", "personal_data"),
    ("Пишите на test@example.com", "personal_data"),
    ("ИИН 900101300126 проверен", "personal_data"),        # верная контрольная цифра РК (как проверяет R04)
    ("ИИН 900101 300 126 — заявитель", "personal_data"),   # с пробелами (R15 S46 у соседа)
    ("Звоните 8 (7172) 55-12-34", "personal_data"),
    ("Звоните ＋７ ７０１ １２３ ４５ ６７", "personal_data"),   # полноширинные цифры (R15, запасной путь без R04)
    # виды R04 раунда 15 (patch R04 r17_crisis_pii.patch) — и в запасных правилах R17 без R04
    ("Помощь — на карту 4400 4300 1234 5678", "personal_data"),
    ("Сбор на счёт KZ86 125K ZT50 0410 0100", "personal_data"),
    ("Нет тепла: ул. Кенесары 40, кв. 12", "personal_data"),
    ("Вопросы — в t.me/nura_help или @nura_help", "personal_data"),
])
def test_public_update_with_personal_data_is_rejected(service, monkeypatch, text, code):
    import sys
    monkeypatch.setitem(sys.modules, "ui.civic_ml_api", None)          # без R04 — запасные правила R17
    reply = call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
                 {"text_ru": text, "text_kk": "Қызметтер жұмыс істеп жатыр"}, Staff())
    assert reply["status"] == 422 and reply["body"]["error"] == code


@pytest.mark.parametrize("text", [
    "Автобусы маршрутов 10 12 14 16 18 21 24 ходят по зимнему графику.",
    "Пункт обогрева в школе № 54, площадь 200 кв. м, с 08:00 до 22:00.",
    "Квартал 5 и микрорайон 7 расчищены, техника на улице Кенесары.",
])
def test_ordinary_update_with_numbers_is_published(service, monkeypatch, text):
    """Ложных срабатываний нет: номера маршрутов, школ, площадь и кварталы — не личные данные."""
    import sys
    monkeypatch.setitem(sys.modules, "ui.civic_ml_api", None)
    reply = call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
                 {"text_ru": text, "text_kk": "Қызметтер жұмыс істеп жатыр"}, Staff())
    assert reply["status"] == 200, reply


@pytest.mark.parametrize("flag,status", [
    ({"kind": "card", "group": "pii", "count": 1, "luhn_ok": 0}, 200),     # «маршруты 10 12 14 16 18 21 24» у R04
    ({"kind": "card", "group": "pii", "count": 1, "luhn_ok": 1}, 422),     # настоящая карта
    ({"kind": "card", "group": "pii", "count": 1}, 422),                   # старый R04 без проверки — блок, как раньше
    ({"kind": "iin", "group": "pii", "count": 1, "checksum_ok": 0}, 200),  # 12 цифр, но не ИИН
    ({"kind": "iin", "group": "pii", "count": 1, "checksum_ok": 1}, 422),
])
def test_r04_card_and_iin_need_a_real_checksum(service, monkeypatch, flag, status):
    """Обновление в буран не блокируется списком номеров: R04 сам говорит, прошла ли цепочка Луна / контрольную цифру."""
    import sys
    import types
    fake = types.ModuleType("ui.civic_ml_api")
    fake.moderate = lambda text=None, lang=None, body=None, **_: {
        "text_public": "***", "clean": False, "action": "review", "pii": True, "rude": False, "flags": [flag]}
    monkeypatch.setitem(sys.modules, "ui.civic_ml_api", fake)
    reply = call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
                 {"text_ru": "Автобусы маршрутов 10 12 14 16 18 21 24 ходят", "text_kk": "Автобустар жүріп тұр"}, Staff())
    assert reply["status"] == status, reply


@pytest.mark.parametrize("kind,group", [("card", "finance"), ("iban", "finance"), ("apartment", "address"),
                                        ("contact", "social")])
def test_r04_pii_kinds_block_even_with_another_group(service, monkeypatch, kind, group):
    """R04 INTEGRATION п. 3: card/iban/apartment/contact — личные данные, даже если группа у R04 названа иначе."""
    import sys
    import types
    fake = types.ModuleType("ui.civic_ml_api")
    fake.moderate = lambda text=None, lang=None, body=None, **_: {
        "text_public": "***", "clean": False, "action": "review", "flags": [{"kind": kind, "group": group, "count": 1}]}
    monkeypatch.setitem(sys.modules, "ui.civic_ml_api", fake)
    reply = call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
                 {"text_ru": "Текст с находкой", "text_kk": "Табылған мәтін"}, Staff())
    assert reply["status"] == 422 and reply["body"]["error"] == "personal_data"


def test_r04_round15_flags_kind_and_group(service, monkeypatch):
    """R04 раунда 15: flags — [{kind, group}], наверху pii/rude. Находка «contact» группы pii — тоже 422."""
    import sys
    import types
    fake = types.ModuleType("ui.civic_ml_api")

    def moderate(text=None, lang=None, body=None, **_):
        if "t.me/" in (text or ""):
            return {"text_public": "***", "clean": False, "action": "review", "pii": True, "rude": False,
                    "flags": [{"kind": "contact", "group": "pii", "count": 1}]}
        return {"text_public": text, "clean": True, "action": "publish", "pii": False, "rude": False, "flags": []}
    fake.moderate = moderate
    monkeypatch.setitem(sys.modules, "ui.civic_ml_api", fake)
    bad = call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
               {"text_ru": "Вопросы — в t.me/akimat_nura", "text_kk": "Қызметтер жұмыс істеп жатыр"}, Staff())
    assert bad["status"] == 422 and bad["body"]["error"] == "personal_data"
    good = call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
                {"text_ru": "Дороги расчищены", "text_kk": "Жолдар тазартылды"}, Staff())
    assert good["status"] in (200, 201)


def test_zone_rules(service):
    staff = Staff()
    polygon = call(service, "POST", "/incidents", {"kind": "flood", "zone": {"kind": "polygon",
                                                                             "geometry": {"type": "Polygon"}}}, staff)
    assert polygon["status"] == 422
    unknown = call(service, "POST", "/incidents", {"kind": "flood", "zone": {"kind": "district", "district": "mars"}},
                   staff)
    assert unknown["status"] == 422 and unknown["body"]["field"] == "zone.district"
    ghost = call(service, "POST", "/incidents", {"kind": "flood", "zone": {"kind": "targets", "targets": ["yard-1"]}},
                 staff)
    assert ghost["status"] == 422                       # такой цели нет на карте R12
    from ui.civic_agencies import geo
    yard = sorted(y for y, v in geo.yards().items() if v["district"] == "almaty")[0]
    real = call(service, "POST", "/incidents", {"kind": "flood", "zone": {"kind": "targets", "targets": [yard]}}, staff)
    assert real["status"] == 201
    zone = real["body"]["incident"]["zone"]
    assert zone["district"] == "almaty" and zone["labels"][0]["label_ru"].startswith("Двор")
    duplicate = call(service, "POST", "/incidents", {"kind": "flood", "zone": {"kind": "targets", "targets": [yard]}},
                     staff)
    assert duplicate["status"] == 409 and duplicate["body"]["current"] == real["body"]["incident"]["id"]


def test_unknown_kind_and_bad_ids(service):
    assert call(service, "POST", "/incidents", {"kind": "meteor", "zone": {}}, Staff())["status"] == 422
    assert call(service, "GET", "/incidents/inc-nope0000")["status"] == 404
    assert call(service, "GET", "/incidents/../../etc")["status"] == 404
    assert call(service, "GET", "/agencies/board", principal=Staff(), query="days=0")["status"] == 400
    assert call(service, "GET", "/agencies/board", principal=Staff(), query="district=mars")["status"] == 400
    assert call(service, "DELETE", "/incidents")["status"] == 405


# ---------------------------------------------------------------- жители зоны
def test_resident_updates_by_place(service, clock):
    nura = call(service, "GET", "/incidents/updates", query="district=nura")["body"]
    assert nura["zone_known"] is True and len(nura["items"]) == 2
    assert all(item["text_kk"] and item["text_ru"] for item in nura["items"])   # ҚАЗ и РУС
    assert call(service, "GET", "/incidents/updates", query="district=esil")["body"]["items"] == []
    nowhere = call(service, "GET", "/incidents/updates")["body"]
    assert nowhere == {"items": [], "zone_known": False, "since": None}
    since = nura["items"][0]["at"]
    clock.now += timedelta(minutes=5)
    call(service, "POST", "/incidents/inc-demo-blizzard-nura/update",
         {"text_ru": "Дороги к школам расчищены", "text_kk": "Мектепке баратын жолдар тазартылды"}, Staff())
    fresh = call(service, "GET", "/incidents/updates", query="district=nura&since=" + since)["body"]["items"]
    assert [i["text_ru"] for i in fresh] == ["Дороги к школам расчищены"]


def test_updates_feed_for_r06_uses_device_places(service, monkeypatch):
    monkeypatch.setattr(svc_mod, "device_places", lambda device: ({"nura"}, set()))
    monkeypatch.setattr(agencies, "device_places", lambda device: ({"nura"}, set()))
    events = agencies.updates("device-12345678", None)
    assert events and {e["module"] for e in events} == {"R17"}
    for e in events:
        assert set(e) >= {"id", "at", "module", "kind", "target", "title_ru", "title_kk", "link"}
        assert e["kind"] == "incident.update" and e["link"].startswith("#crisis/inc-")
    monkeypatch.setattr(agencies, "device_places", lambda device: (set(), set()))
    assert agencies.updates("device-12345678", None) == []


def test_neighbor_functions_never_raise_without_service(monkeypatch):
    monkeypatch.setattr(api_state, "_state", {"service": None})
    assert agencies.updates("device-12345678") == []
    assert agencies.active_incidents() == [] and agencies.incident_marks() == []
    assert agencies.board_snapshot()["empty"] is True
    assert agencies.agencies_week()["lagging"] == []
    assert agencies.crisis_link("nura") == "#agencies/crisis/new/blizzard/nura"
    assert len(agencies.service_profiles()) == 20


def test_make_service_once_then_module_functions_and_reset(tmp_path):
    """Контракт для соседей: make_service(db) один раз (как шлюз; R03/R08 зовут без сохранения результата) — дальше
    функции модуля читают эту базу; api_state.reset() — для conftest соседей после тестов со своим шлюзом."""
    import gc

    agencies.make_service(str(tmp_path / "gw.sqlite3"), demo=False)     # результат не сохраняем — как R03
    gc.collect()
    assert api_state.current() is not None
    assert agencies.list_incidents()["items"] == [] and "empty" not in agencies.list_incidents()   # база шлюза, не «нет R17»
    api_state.reset()
    assert api_state.current() is None
    assert agencies.agencies_week()["lagging"] == [] and agencies.list_incidents().get("empty") is True


def test_neighbor_functions_with_service(service, monkeypatch):
    # Табло — по демо-фикстуре R17 (в сборке с R09 v2.1 демо без мира читает пустую базу R09 — тест не об источнике).
    from ui.civic_agencies import sources
    monkeypatch.setattr(sources, "r09_supports_parts", lambda: False)
    week = agencies.agencies_week()
    assert len(week["lagging"]) == 3 and week["source"] == "fixture" and week["demo"] is True
    active = agencies.active_incidents("nura")
    assert [i["id"] for i in active] == ["inc-demo-blizzard-nura"] and "tasks" not in active[0]
    assert agencies.crisis_link("nura") == "#agencies/crisis/inc-demo-blizzard-nura"
    marks = agencies.incident_marks()
    assert {m["id"] for m in marks} == {"inc-demo-blizzard-nura", "inc-demo-heat-saryarka"}


def test_names_neighbors_look_for(service):
    """R03 (agent/civic_assistant/analyst/sources.py) ищет board / list_incidents, R12 — service_profiles.

    ui.civic_agencies.board — функция (подмодуль расчёта называется metrics), иначе сосед нашёл бы модуль.
    """
    import inspect
    assert inspect.isfunction(agencies.board) and inspect.isfunction(agencies.list_incidents)
    body = agencies.board(days=30, district="nura")
    assert len(body["services"]) == 20
    assert {"service", "open", "overdue", "median_answer_days", "verified_share"} <= set(body["services"][0])
    listed = agencies.list_incidents(status="active")
    assert [i["id"] for i in listed["items"]] == ["inc-demo-blizzard-nura"]
    assert "tasks" not in listed["items"][0] and listed["items"][0]["progress"]
    # R07 (ui/civic_heat/marks.py @ cbfea106): list_incidents(db_path=…) — все кризисы, и прошедшие, для шкалы хроники.
    every = agencies.list_incidents(db_path=service.store.db_path)
    assert {i["id"] for i in every["items"]} == {"inc-demo-blizzard-nura", "inc-demo-heat-saryarka"}
    assert all(i["district"] for i in every["items"])
    assert {p["id"] for p in agencies.service_profiles()} == set(agencies._profiles.SERVICE_IDS)


# ---------------------------------------------------------------- засев
def test_demo_seed_is_idempotent_and_resets_rehearsal(tmp_path, clock):
    db = str(tmp_path / "w.sqlite3")
    store = AgencyStore(db, clock=clock)
    assert demo.seed_demo_incidents(store) == {"inserted": 2, "skipped": 0, "reset": 0}
    # Репетиция: кризис закрыли — следующий запуск сервера возвращает пример в исходное состояние (SCHEMA R02 §4).
    store.close("inc-demo-blizzard-nura", result_ru="Готово", result_kk="Дайын", by_role="editor")
    assert demo.seed_demo_incidents(store) == {"inserted": 0, "skipped": 0, "reset": 2}
    assert store.get("inc-demo-blizzard-nura")["status"] == "active"


# Формат демо-мира R02 (data/civic/astana/demo-world/SCHEMA.md §1, §2.8): время — объектами, id задач повторяются,
# у закрытого кризиса нет closed_at. Записи — как в world_v1.json @ R02 d8af32a0 (сокращённо).
WORLD = {"incidents": [
    {"id": "inc-w15-buran", "kind": "blizzard", "title_ru": "Буран в Нуре", "title_kk": "Нұрада боран",
     "zone": {"kind": "district", "district": "nura", "targets": [], "geometry": None},
     "started_at": {"ago_hours": 62.0}, "status": "active", "event": "ev-w15-buran",
     "tasks": [{"id": "t-1", "service": "street_cleaning", "text_ru": "Расчистить главные улицы",
                "text_kk": "Басты көшелерді тазалау", "status": "doing"},
               {"id": "t-2", "service": "akimat", "text_ru": "Пункт обогрева", "text_kk": "Жылыну пункті",
                "status": "done"}],
     "updates": [{"at": {"ago_hours": 61.0}, "public": True, "text_ru": "Штаб открыт.", "text_kk": "Штаб ашылды."},
                 {"at": {"ago_hours": 6.0}, "public": True, "text_ru": "Автобусы по зимнему графику.",
                  "text_kk": "Автобустар қысқы кестемен."}],
     "result": None, "demo": True},
    {"id": "inc-w15-water-almaty", "kind": "water_outage", "title_ru": "Прорыв водопровода",
     "title_kk": "Су құбырының жарылуы", "zone": {"kind": "district", "district": "almaty", "targets": [], "geometry": None},
     "started_at": {"ago_days": 33.0}, "status": "closed", "event": None,
     "tasks": [{"id": "t-1", "service": "water", "text_ru": "Заменить трубу", "text_kk": "Құбырды ауыстыру", "status": "done"}],
     "updates": [{"at": {"ago_days": 32.9}, "public": True, "text_ru": "Подвоз воды у школы.", "text_kk": "Су мектеп жанында."}],
     "result": {"text_ru": "Воду дали вечером.", "text_kk": "Су кешке берілді."}, "demo": True},
    {"id": "inc-w15-bad", "kind": "meteor", "zone": {"kind": "district", "district": "nura"}, "demo": True},
]}


def test_seed_world_r02_format(tmp_path, clock):
    db = str(tmp_path / "w.sqlite3")
    assert agencies.seed_world(db, WORLD, now=clock.now) == {"inserted": 2, "skipped": 1, "reset": 0}
    assert agencies.seed_world(db, WORLD, now=clock.now) == {"inserted": 0, "skipped": 1, "reset": 2}
    store = AgencyStore(db, clock=clock)
    buran = store.get("inc-w15-buran")
    started = datetime.fromisoformat(buran["started_at"])
    assert abs((clock.now - started) - timedelta(hours=62)) < timedelta(seconds=2)
    assert buran["status"] == "active" and [t["status"] for t in buran["tasks"]] == ["doing", "done"]
    assert all(t["id"].startswith("t-") and t["id"] != "t-1" for t in buran["tasks"])   # свои id задач
    water = store.get("inc-w15-water-almaty")
    assert water["status"] == "closed" and water["result"]["text_kk"] == "Су кешке берілді."
    closed = datetime.fromisoformat(water["closed_at"])
    assert abs((clock.now - closed) - timedelta(days=32.9)) < timedelta(seconds=2)   # не «сейчас»
    # Список мира целиком (load_world()) и просто список записей — одно и то же.
    assert agencies.seed_world(db, WORLD["incidents"], now=clock.now)["skipped"] == 1


def test_seed_world_never_touches_real_incident(tmp_path, clock):
    db = str(tmp_path / "w.sqlite3")
    store = AgencyStore(db, clock=clock)
    store.create(kind="blizzard", title_ru="Настоящий", title_kk="Нақты", zone={"kind": "district", "district": "nura",
                 "targets": [], "geometry": None}, district="nura", tasks=[], by_role="editor",
                 incident_id="inc-w15-buran", demo=False)
    report = agencies.seed_world(db, WORLD, now=clock.now)
    assert report["skipped"] == 2 and report["reset"] == 0
    assert store.get("inc-w15-buran")["title_ru"] == "Настоящий"


def test_make_service_is_one_per_database(tmp_path, monkeypatch):
    """Шлюз R01 и R08 (neighbors.py) зовут make_service для одной базы — второй вызов не пересевает демо-кризисы."""
    monkeypatch.setattr(api_state, "_state", {"service": None})
    db = str(tmp_path / "one.sqlite3")
    first = agencies.make_service(db, demo=True)
    staff = Staff()
    first.handle("POST", P + "/incidents/inc-demo-blizzard-nura/close", "",
                 {"result_ru": "Готово", "result_kk": "Дайын"}, staff, OK_CTX)
    second = agencies.make_service(db, demo=True)
    assert second is first
    assert second.store.get("inc-demo-blizzard-nura")["status"] == "closed"   # правка оператора цела
    other = agencies.make_service(str(tmp_path / "other.sqlite3"), demo=True)
    assert other is not first


def test_board_shows_r16_pickups_as_service_tasks(service, monkeypatch):
    """IDEA §2A: акимат «Поддержать» с вывозом → задача оператору вывоза (служба waste) на табло R17."""
    from ui.civic_agencies import sources

    rows = [{"initiative_id": "i-w15-01", "service": "waste", "title": "Субботник во дворе", "district": "nura",
             "target": {"kind": "area", "id": "yard-1454082640"}, "starts_at": "2026-10-17T10:00:00+05:00",
             "ends_at": None, "note": "Мешки и вывоз в 14:00", "supported_at": "2026-10-15T12:00:00+05:00",
             "demo": True, "author_device": "не должен попасть наружу"}]
    monkeypatch.setattr(sources, "pickups", lambda db_path, district=None: [
        {k: r.get(k) for k in ("initiative_id", "service", "title", "district", "target", "starts_at", "ends_at",
                               "note", "demo")} for r in rows])
    body = call(service, "GET", "/agencies/board", principal=Staff())["body"]
    assert body["pickups"] == {"waste": 1}
    detail = call(service, "GET", "/agencies/board", principal=Staff(), query="service=waste")["body"]
    assert detail["pickup_items"][0]["note"] == "Мешки и вывоз в 14:00"
    assert "author_device" not in detail["pickup_items"][0]
    other = call(service, "GET", "/agencies/board", principal=Staff(), query="service=road")["body"]
    assert other["pickup_items"] == []


def test_pickups_without_r16_is_empty(tmp_path, monkeypatch):
    """R16 нет в сборке (или его функция упала) — табло без задач вывоза, не ошибка."""
    import sys
    import types
    from ui.civic_agencies import sources

    monkeypatch.setitem(sys.modules, "ui.civic_together", None)      # import → ImportError
    assert sources.pickups(str(tmp_path / "none.sqlite3")) == []
    broken = types.ModuleType("ui.civic_together")
    broken.pickups = lambda district=None, db_path=None: 1 / 0
    monkeypatch.setitem(sys.modules, "ui.civic_together", broken)
    assert sources.pickups(str(tmp_path / "none.sqlite3")) == []
    old_style = types.ModuleType("ui.civic_together")                # только позиционный district
    old_style.pickups = lambda district=None: [{"service": "waste", "title": "Дело", "author_device": "d-1"}, "мусор"]
    monkeypatch.setitem(sys.modules, "ui.civic_together", old_style)
    rows = sources.pickups(str(tmp_path / "none.sqlite3"), "nura")
    assert [r["service"] for r in rows] == ["waste"] and "author_device" not in rows[0]


# ---------------------------------------------------------------- R15-S43: неверный тип JSON → 4xx, не 500
WRONG = [["road"], {"x": 1}, 7, 1.5, True, None, [["nested"]]]
ZONE_OK = {"kind": "district", "district": "esil"}


def _fuzz_cases():
    base = {
        "/incidents": {"kind": "flood", "zone": ZONE_OK, "tasks": [{"service": "road", "text_ru": "Задача"}],
                       "title_ru": "Подтопление", "title_kk": "Су басу",
                       "update": {"text_ru": "Штаб открыт", "text_kk": "Штаб ашылды"}},
        "/incidents/inc-demo-blizzard-nura/task": {"service": "road", "text_ru": "Задача", "text_kk": "Тапсырма"},
        "/incidents/inc-demo-blizzard-nura/update": {"text_ru": "Текст", "text_kk": "Мәтін", "public": True},
        "/incidents/inc-demo-blizzard-nura/close": {"result_ru": "Итог", "result_kk": "Қорытынды"},
    }
    for path, body in base.items():
        for field in body:
            for value in WRONG:
                yield path, dict(body, **{field: value}), field
    # вложенные поля: задача кризиса, зона, обновление, смена статуса задачи
    for value in WRONG:
        yield "/incidents", dict(base["/incidents"], tasks=[{"service": value, "text_ru": "Задача"}]), "tasks[].service"
        yield "/incidents", dict(base["/incidents"], tasks=[{"service": "road", "text_ru": value}]), "tasks[].text_ru"
        yield "/incidents", dict(base["/incidents"], tasks=[value]), "tasks[]"
        yield "/incidents", dict(base["/incidents"], zone={"kind": value}), "zone.kind"
        yield "/incidents", dict(base["/incidents"], zone={"kind": "district", "district": value}), "zone.district"
        yield "/incidents", dict(base["/incidents"], zone={"kind": "targets", "targets": [value]}), "zone.targets[]"
        yield "/incidents", dict(base["/incidents"], zone={"kind": "targets", "targets": value}), "zone.targets"
        yield "/incidents", dict(base["/incidents"], update={"text_ru": value, "text_kk": "Мәтін"}), "update.text_ru"
        yield "/incidents/inc-demo-blizzard-nura/task", {"task_id": value, "status": "done"}, "task_id"
        yield "/incidents/inc-demo-blizzard-nura/task", {"task_id": "t-1", "status": value}, "status"
        yield "/incidents/inc-demo-blizzard-nura/task", {"task_id": "t-1", "status": "done", "expected": value}, "expected"
    for path in base:
        for value in WRONG + ["строка"]:
            yield path, value, "body"


@pytest.mark.parametrize("path,body,field", list(_fuzz_cases()))
def test_wrong_json_types_answer_4xx_not_500(service, path, body, field):
    """R15-S43: список/словарь/число вместо строки (и не-объект вместо тела) — понятная ошибка 4xx, а не TypeError → 500."""
    reply = call(service, "POST", path, body, Staff())
    assert 400 <= reply["status"] < 500 or reply["status"] in (200, 201), (field, body, reply)
