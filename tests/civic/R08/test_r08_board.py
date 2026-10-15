"""Раунд 15: «Ситуационный центр» (GET akim/board), «Картина недели» (GET akim/week), блоки соседей «Картины дня» 2.0.

Каждый блок соседа необязателен: соседа нет → {"available": False, "reason": "module_not_ready"}, сосед упал →
"module_failed", а «Картина дня» и ситуационный центр работают. Фикстуры R08 — только стенд и тесты; при
CIVIC_DEMO_WORLD=1 — никогда. Числа ситуационного центра — ровно «Картина дня» (а она — карта R07).
"""
import json
import sys
import types
from datetime import datetime, timedelta

import pytest

from r08_helpers import NOW, TZ, rec
from ui.civic_akim import AkimService, api, blocks, neighbors, routing
from ui.civic_akim import situation, weekly

NEIGHBOR_NAMES = tuple(neighbors.FUNCS)
NONE = {name: False for name in NEIGHBOR_NAMES}  # «соседа нет» для всех


def svc(records=None, *, sources=None, fixtures=None, **kw):
    kw.setdefault("objects", None)
    kw.setdefault("proposals", None)
    recs = records if records is not None else []
    return AkimService(heat=False, records=lambda since: recs, clock=lambda: NOW, neighbor_sources=sources,
                       fixtures=fixtures, **kw)


def some_records():
    return [rec(1, age_days=0.1), rec(2, age_days=1, history=[(0.5, "in_progress")]),
            rec(3, age_days=3, history=[(1, "fixed")]), rec(4, age_days=8, category="snow_ice", history=[(1, "accepted")])]


# ---------------------------------------------------------------- без соседей и со сбоем соседа

def test_board_without_neighbours_hides_blocks():
    b = svc(some_records(), sources=dict(NONE)).board(now=NOW)
    for name in ("agencies", "crisis", "together", "meetings", "forecast"):
        assert b[name]["available"] is False
        assert b[name]["reason"] == "module_not_ready"
    assert b["stage"] == []
    assert b["kpi"]["available"] is True
    assert [t["id"] for t in b["kpi"]["items"]] == ["new_day", "in_progress", "overdue", "fixed_week"]


def test_failing_neighbour_does_not_break_board():
    def boom(**_kw):
        raise RuntimeError("сосед упал")
    sources = dict(NONE, agencies_board=boom, incidents=boom, initiatives=boom, meetings=boom)
    b = svc(some_records(), sources=sources).board(now=NOW)
    for name in ("agencies", "crisis", "together", "meetings"):
        assert b[name] == {"available": False, "reason": "module_failed", "source": "failed"} or \
            (name == "together" and b[name]["reason"] == "module_failed")
    assert b["kpi"]["available"] is True


def test_together_without_r16_still_carries_r09_verified():
    t = svc(some_records(), sources=dict(NONE)).summary(now=NOW)["together"]
    assert t["available"] is False and "verified" in t


def test_past_date_has_no_neighbour_blocks():
    s = svc(some_records(), fixtures=True).summary(date="2026-10-10", now=NOW)
    for name in ("agencies", "crisis", "together", "meetings", "forecast"):
        assert s[name] == {"available": False, "reason": "past_date"}


# ---------------------------------------------------------------- фикстуры: только стенд, никогда в демо-мире

def test_fixtures_feed_all_blocks():
    b = svc(some_records(), sources={"forecast_week": False, "forecast_month": False}, fixtures=True).board(now=NOW)
    assert b["stage"] == ["crisis", "agencies", "together", "meetings"]
    for name in ("agencies", "crisis", "together", "meetings"):
        assert b[name]["available"] and b[name]["source"] == "fixture" and b[name]["demo"] is True


def test_demo_world_never_uses_fixtures(monkeypatch):
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
    monkeypatch.setenv("BIRGE_AKIM_FIXTURES", "1")
    nb = neighbors.Neighbors(fixtures=True)
    assert nb.fixtures is False
    data, src = nb.get("agencies_board", now=NOW, days=7)
    assert data is None or src != "fixture"


def test_fixtures_off_by_default(monkeypatch):
    monkeypatch.delenv("BIRGE_AKIM_FIXTURES", raising=False)
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    assert neighbors.Neighbors().fixtures is False


def test_fixture_times_are_relative_to_now():
    inc = neighbors.fixture("incidents", NOW)[0]
    assert datetime.fromisoformat(inc["started_at"]) == NOW - timedelta(hours=30)
    order = neighbors.fixture("meetings", NOW)[0]["orders"][1]
    assert order["due"] == (NOW - timedelta(days=2)).date().isoformat()


# ---------------------------------------------------------------- те же числа, что «Картина дня»

def test_board_numbers_equal_day_summary():
    s = svc(some_records(), sources=dict(NONE))
    day, board = s.summary(now=NOW), s.board(now=NOW)
    by = {t["id"]: t for t in board["kpi"]["items"]}
    assert by["new_day"]["value"] == day["kpi"]["new_day"]["value"]
    assert by["in_progress"]["value"] == day["kpi"]["in_progress"]["value"]
    assert by["overdue"]["value"] == day["kpi"]["overdue"]["value"]
    assert by["fixed_week"]["value"] == day["kpi"]["fixed_week"]["value"]
    assert by["new_day"]["series"] == day["kpi"]["new_day"]["series"]
    assert board["decisions"]["count"] == day["decisions"]["count"]


def test_board_on_heat_map_matches_summary_hot_and_districts():
    """С тепловой картой R07 (демо-набор): места и районы ситуационного центра — те же, что в «Картине дня»."""
    pytest.importorskip("ui.civic_heat")
    s = AkimService(neighbor_sources=dict(NONE), objects=None, proposals=None)
    now = datetime.now(TZ)
    day, board = s.summary(now=now), s.board(now=now)
    assert [h["target"]["id"] for h in board["hot"]["items"]] == [h["target"]["id"] for h in day["hot"]["items"][:5]]
    assert {r["district"]: r["value"] for r in board["districts"]["items"]} == \
        {r["district"]: r["value"] for r in day["districts"]["items"]}
    assert board["pulse"]["items"] == day["pulse"]["items"][:3]


# ---------------------------------------------------------------- права: только сотрудник

def test_board_and_week_are_staff_only():
    s = svc(some_records(), sources=dict(NONE))
    for path in ("/api/civic/v2/akim/board", "/api/civic/v2/akim/week"):
        status, body = api.handle_get(path, {}, service=s)
        assert status == 401 and body["error"] == "staff_only"
        status, body = api.handle_get(path, {}, service=s, staff=True)
        assert status == 200
    # «Картина дня» — как раньше, без входа
    assert api.handle_get("/api/civic/v2/akim/summary", {}, service=s)[0] == 200


def test_gateway_passes_staff_flag_to_board_and_week():
    """Сборка R01: akim/board и akim/week — raw-обработчик handle_get со staff_view=True (INTEGRATION §1).

    Шлюз передаёт raw-обработчику staff=True только для staff_view; без него (даже со staff=True — проверка
    сессии и CSRF шлюзом) R08 отвечает 401 staff_only и экран всегда показывает вход. В ветке R08 маршрутов шлюза
    нет — тест пропускается; в сборке он ловит регистрацию без staff_view.
    """
    ws = pytest.importorskip("ui.web_server")
    handlers = getattr(ws, "V2_HANDLERS", {})
    missing = [key for key in ("akim.board", "akim.week") if key not in handlers]
    if missing:
        pytest.skip("шлюз ещё не подключил " + ", ".join(missing))
    for key in ("akim.board", "akim.week"):
        handler = handlers[key]
        assert handler.kind == "raw" and handler.function == "handle_get" and "ui.civic_akim.api" in handler.modules
        assert getattr(handler, "staff_view", False) is True, (
            f"{key}: добавьте staff_view=True (INTEGRATION R08 §1) — иначе сотрудник видит 401 staff_only")


def test_board_bad_district_is_400():
    s = svc(some_records(), sources=dict(NONE))
    status, body = api.handle_get("/api/civic/v2/akim/board", {"district": ["mars"]}, service=s, staff=True)
    assert status == 400 and body["field"] == "district"


# ---------------------------------------------------------------- разбор ответов соседей

def test_agencies_respects_r17_order_and_ignores_unknown_ids():
    board = {"services": [
        {"service": "water", "open": 5, "overdue": 1, "verified_pct": 40, "rank": 2},
        {"service": "road", "open": 9, "overdue": 0, "verified_share": 0.5, "rank": 1},
        {"service": "made_up_service", "open": 50, "overdue": 50},
    ]}
    a = blocks.agencies(None, "none", board, "r17", [{"services": [{"service": "water", "status": "done"}, {"service": "road", "status": "in_progress"}]}],
                        [{"at": (NOW - timedelta(days=1)).isoformat()}, {"at": (NOW - timedelta(days=9)).isoformat()}], as_of=NOW)
    assert [x["service"]["id"] for x in a["lagging"]] == ["road", "water"]  # порядок R17 (rank)
    assert {x["service"]["id"] for x in a["board"]} == {"water", "road"}   # чужой id не показываем
    water = next(x for x in a["board"] if x["service"]["id"] == "water")
    assert water["verified_share"] == 0.4
    assert water["service"]["ru"] == routing.SERVICES["water"]["ru"]       # названия — из таблицы R08 (CONTRACT §3)
    assert a["joint"] == 1 and a["handoffs_week"] == 1


def test_agencies_own_order_when_r17_gives_none():
    board = {"services": [{"service": "water", "open": 10, "overdue": 1}, {"service": "road", "open": 4, "overdue": 3},
                          {"service": "lighting", "open": 3, "overdue": 0}]}
    a = blocks.agencies(None, "none", board, "r17", as_of=NOW)
    assert [x["service"]["id"] for x in a["lagging"]] == ["road", "water"]  # больше просроченных — выше
    assert a["joint"] is None and a["handoffs_week"] is None


def test_crisis_link_only_for_related_alarm():
    crisis = blocks.crisis([{"id": "inc-1", "kind": "blizzard", "status": "active", "title_ru": "Буран",
                             "zone": {"kind": "district", "district": "nura"}, "started_at": (NOW - timedelta(hours=5)).isoformat(),
                             "tasks": [{"service": "street_cleaning", "status": "done"}, {"service": "transport", "status": "todo"}],
                             "updates": [{"at": (NOW - timedelta(hours=1)).isoformat(), "text_ru": "Публично", "public": True},
                                         {"at": NOW.isoformat(), "text_ru": "Служебное", "public": False}]}],
                           "r17", as_of=NOW, district=None, district_names={"nura": {"ru": "Нура", "kk": "Нұра"}})
    a = crisis["active"]
    assert a["tasks_total"] == 2 and a["tasks_done"] == 1 and a["hours"] == 5
    assert a["last_update"]["text_ru"] == "Публично"  # служебные заметки на экран не выводим
    alarms = [{"kind": "spike", "category": "snow_ice", "district": "nura"},
              {"kind": "spike", "category": "roads", "district": "nura"},
              {"kind": "spike_city", "category": "snow_ice", "district": None, "districts": [{"district": "esil"}, {"district": "nura"}]},
              {"kind": "spike", "category": "snow_ice", "district": "esil"}]
    blocks.crisis_links(alarms, crisis)
    assert alarms[0]["crisis"]["id"] == "inc-1"
    assert "crisis" not in alarms[1] and "crisis_new" not in alarms[1]   # «Дороги» в штаб бурана не ведут
    assert alarms[2]["crisis"]["id"] == "inc-1"                           # всплеск по городу задел Нуру
    assert "crisis" not in alarms[3] and alarms[3]["crisis_new"] == {"kind": "blizzard", "district": "esil"}


def test_crisis_in_district_filter():
    inc = [{"id": "a", "status": "active", "zone": {"district": "esil"}, "started_at": NOW.isoformat()}]
    c = blocks.crisis(inc, "r17", as_of=NOW, district="nura", district_names={})
    assert c["active"] is None and c["active_count"] == 0


def test_together_week_windows_and_privacy():
    items = [
        {"id": "i1", "status": "done", "joined": 15, "district": "nura", "report": {"at": (NOW - timedelta(days=2)).isoformat()},
         "target": {"kind": "area", "id": "yard-1", "label_ru": "Двор"}, "author_device": "secret-device", "support": {"by_akimat": True}},
        {"id": "i2", "status": "done", "joined": 30, "district": "nura", "report": {"at": (NOW - timedelta(days=12)).isoformat()}},
        {"id": "i3", "status": "published", "joined": 14, "district": "nura", "starts_at": (NOW + timedelta(days=2)).isoformat()},
        {"id": "i4", "status": "published", "joined": 9, "district": "nura", "starts_at": (NOW + timedelta(days=20)).isoformat()},
        {"id": "i5", "status": "on_review", "joined": 0, "district": "nura"},
        {"id": "i6", "status": "done", "joined": 7, "district": "esil", "report": {"at": (NOW - timedelta(days=1)).isoformat()}},
    ]
    kpi = {"fixed_week": {"value": 10, "verified": 4}, "verification_available": True}
    t = blocks.together(items, "r16", [{"id": "yard-1", "members": 37}], as_of=NOW, district="nura", kpi=kpi)
    assert (t["done_week"], t["people_done"], t["upcoming"], t["people_upcoming"]) == (1, 15, 1, 14)
    assert t["on_review"] == 1 and t["supported"] == 1
    assert t["yard_of_week"]["id"] == "i1" and t["yard_of_week"]["yard_members"] == 37
    assert t["verified"] == {"value": 4, "fixed": 10, "available": True}
    assert "secret-device" not in json.dumps(t)


def test_meetings_orders_overdue_and_next():
    m = [{"id": "m1", "district": "nura", "title_ru": "Встреча", "at": (NOW - timedelta(days=9)).isoformat(),
          "orders": [{"id": "o1", "text_ru": "Свалка", "service": "waste", "due": (NOW - timedelta(days=2)).date().isoformat(), "status": "in_progress"},
                     {"id": "o2", "text_ru": "Разметка", "service": "traffic", "due": (NOW - timedelta(days=1)).date().isoformat(), "status": "done"},
                     {"id": "o3", "text_ru": "Свет", "service": "lighting", "due": (NOW + timedelta(days=3)).date().isoformat(), "status": "todo"}]},
         {"id": "m2", "district": "nura", "title_ru": "Следующая", "at": (NOW + timedelta(days=6)).isoformat(), "registered": 31,
          "questions": ["q1", "q2"], "orders": []}]
    out = blocks.meetings(m, "r13", as_of=NOW, district=None, district_names={"nura": {"ru": "Нура", "kk": "Нұра"}})
    assert out["orders"] == {"total": 3, "done": 1, "in_progress": 1, "todo": 1, "overdue": 1, "due_week": 1}
    assert [o["id"] for o in out["items"]] == ["m1/o1", "m1/o3"]  # просроченное первым, сделанное не показываем
    assert out["items"][0]["days_left"] == -2
    assert out["next"]["id"] == "m2" and out["next"]["registered"] == 31 and out["next"]["questions"] == 2


def test_forecast_month_fallback_is_prototype():
    f = blocks.forecast({"month": "2026-11", "items": [{"target": {"kind": "area", "id": "yard-1", "label_ru": "Двор"},
                                                       "level": "high", "risk": 0.7, "main_category": "snow_ice",
                                                       "reasons": [{"ru": "причина", "kk": "себеп"}]}]}, "r13", "month")
    assert f["prototype"] is True and f["period"] == "month" and f["items"][0]["reason_kk"] == "себеп"


# ---------------------------------------------------------------- сервис соседа вместо функции (CONTRACT §7)

def test_neighbour_service_route_is_read_as_staff(monkeypatch, tmp_path):
    calls = []

    class FakeService:
        def handle(self, method, path, query, body, principal, context):
            calls.append((method, path, query, principal))
            return {"status": 200, "headers": {}, "body": {"services": [{"service": "road", "open": 2, "overdue": 1}]}}

    module = types.ModuleType("ui.civic_agencies")
    module.make_service = lambda db_path: FakeService()
    monkeypatch.setitem(sys.modules, "ui.civic_agencies", module)
    nb = neighbors.Neighbors(db_path=str(tmp_path / "x.sqlite3"))
    data, src = nb.get("agencies_board", now=NOW, days=7, district="nura")
    assert src == "r17" and data["services"][0]["service"] == "road"
    method, path, query, principal = calls[0]
    assert method == "GET" and path == "/api/civic/v2/agencies/board" and query == "days=7&district=nura"
    assert principal["role"] == "editor" and principal.role == "editor"


def test_neighbour_function_gets_only_accepted_args(monkeypatch):
    seen = {}

    def list_meetings(district=None):
        seen["district"] = district
        return {"meetings": []}

    module = types.ModuleType("ui.civic_meetings")
    module.list_meetings = list_meetings
    monkeypatch.setitem(sys.modules, "ui.civic_meetings", module)
    data, src = neighbors.Neighbors().get("meetings", now=NOW, district="esil", days=7)
    assert src == "r13" and data == {"meetings": []} and seen == {"district": "esil"}


# ---------------------------------------------------------------- «Картина недели»

def test_week_days_sum_to_total_and_texts():
    recs = [rec(i, age_days=d) for i, d in enumerate([0.2, 1.2, 1.4, 2.5, 6.5, 6.95, 7.2, 8.0, 9.0, 13.5])]
    w = svc(recs, sources=dict(NONE)).week(now=NOW)
    # Сегодня (10:00): окно — 7 суток до 10:00, как «за 7 дней» «Картины дня»: 8 дат, крайние неполные.
    days = w["days"]
    assert len(days) == 8 and days[-1]["date"] == NOW.date().isoformat()
    assert (days[0]["since"], days[-1]["until"]) == ("10:00", "10:00") and days[0]["partial"] and days[-1]["partial"]
    assert not any(d["partial"] for d in days[1:-1])
    assert sum(d["new"] for d in days) == w["totals"]["new"]["value"] == 6   # 0.2 … 6.95 суток; 7.2 — уже вне окна
    assert sum(d["prev"] for d in days) == w["totals"]["new"]["prev"]
    assert days[0]["new"] == 2   # 6.5 и 6.95 суток назад — 5 окт после 10:00
    assert w["period"]["from"] == (NOW - timedelta(days=7)).date().isoformat() and w["period"]["clock"] == "10:00"
    assert w["text"]["ru"][0].startswith("За 7 суток до 10:00") and w["text"]["kk"][0].startswith("10:00 дейінгі 7 тәулікте")
    for lang in ("ru", "kk"):
        text = " ".join(w["text"][lang])
        assert text and "{" not in text and str(w["totals"]["new"]["value"]) in text


@pytest.mark.parametrize("date", [None, "2026-10-09"])
def test_week_totals_equal_day_summary(date):
    """«Картина недели» и «Картина дня» в одну минуту: поступило / исправлено / в работе / просрочено — одни числа."""
    recs = [rec(i, age_days=d, history=[(max(0.0, d - 0.5), "fixed")] if i % 3 == 0 else [(max(0.0, d - 0.3), "in_progress")])
            for i, d in enumerate([0.2, 0.9, 1.2, 2.5, 3.3, 4.1, 5.6, 6.5, 6.95, 7.2, 8.0, 9.0, 10.5, 13.5])]
    s = svc(recs, sources=dict(NONE))
    w, day = s.week(date=date, now=NOW), s.summary(date=date, now=NOW)
    k = day["kpi"]
    assert w["totals"]["new"]["value"] == k["new_week"]["value"] and w["totals"]["new"]["prev"] == k["new_week"]["prev"]
    assert w["totals"]["fixed"]["value"] == k["fixed_week"]["value"] and w["totals"]["fixed"]["prev"] == k["fixed_week"]["prev"]
    assert w["totals"]["fixed"]["verified"] == k["fixed_week"]["verified"]
    assert w["totals"]["in_progress"]["value"] == k["in_progress"]["value"]
    assert w["totals"]["overdue"]["value"] == k["overdue"]["value"]
    if date:  # прошлая дата — ровно 7 календарных дней, без неполных
        assert [d["date"] for d in w["days"]] == [f"2026-10-{n:02d}" for n in range(3, 10)]
        assert not any(d["partial"] for d in w["days"]) and w["period"]["clock"] is None
        assert w["text"]["ru"][0].startswith("За неделю 3–9")


def test_week_past_date_closed_and_without_neighbours():
    w = svc(some_records(), fixtures=True).week(date="2026-10-09", now=NOW)
    assert w["is_today"] is False and w["period"]["to"] == "2026-10-09"
    assert w["agencies"] == {"available": False, "reason": "past_date"}


def test_week_with_fixtures_mentions_neighbours():
    w = svc(some_records(), fixtures=True, sources={"forecast_week": False, "forecast_month": False}).week(now=NOW)
    ru, kk = " ".join(w["text"]["ru"]), " ".join(w["text"]["kk"])
    assert "Жители вместе" in ru and "Тұрғындар бірге" in kk
    assert "Поручения встреч" in ru and "кризисный штаб" in ru


def test_week_future_date_is_400():
    s = svc(some_records(), sources=dict(NONE))
    status, body = api.handle_get("/api/civic/v2/akim/week", {"date": ["2030-01-01"]}, service=s, staff=True)
    assert status == 400 and body["field"] == "date"


def test_board_stage_order_constant():
    assert situation.STAGE == ("crisis", "agencies", "together", "meetings", "forecast")
    assert situation.ROTATE_S == 15


def test_demo_world_drops_old_r08_fixtures(monkeypatch):
    """CIVIC_DEMO_WORLD=1: ни объектов, ни предложений, ни «Рядом», ни примера «Нужно решение» из фикстур R08."""
    from ui.civic_akim import nearby, sources
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
    assert sources.fixture_objects(NOW.date()) == [] and sources.fixture_proposals(NOW.date()) == []
    items, names = nearby.load_items("nura", NOW, objects=lambda d, t: [], nearby_fn=False)
    assert names["nearby"] == "none" and not any(i.get("demo") for i in items)
    s = AkimService(heat=False, records=lambda since: [rec(1, age_days=0.1)], clock=lambda: NOW, objects=None,
                    proposals=None, demo_build=True, neighbor_sources=dict(NONE))
    assert s.summary(now=NOW)["decisions"]["demo"] is False


def test_without_demo_world_old_fixtures_stay(monkeypatch):
    from ui.civic_akim import sources
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    assert sources.fixture_objects(NOW.date()) and sources.fixture_proposals(NOW.date())


def test_crisis_from_r17_public_view_with_progress():
    """R17 active_incidents: публичная часть без задач, но с progress, zone_label и ссылкой на штаб."""
    inc = [{"id": "inc-9", "kind": "blizzard", "status": "active", "title_ru": "Буран", "title_kk": "Боран",
            "zone": {"kind": "district", "district": "nura"}, "zone_label": {"ru": "район Нура", "kk": "Нұра ауданы"},
            "started_at": (NOW - timedelta(hours=3)).isoformat(),
            "progress": [{"service": "street_cleaning", "done": 1, "doing": 1, "total": 3}, {"service": "transport", "done": 1, "doing": 0, "total": 1}],
            "updates": [{"at": (NOW - timedelta(hours=1)).isoformat(), "text_ru": "Жителям", "text_kk": "Тұрғындарға"}],
            "link": "#agencies/crisis=inc-9", "demo": True}]
    a = blocks.crisis(inc, "r17", as_of=NOW, district=None, district_names={})["active"]
    assert (a["tasks_done"], a["tasks_total"]) == (2, 4)
    assert a["link"] == "#agencies/crisis=inc-9" and a["zone"]["label_kk"] == "Нұра ауданы"
    assert a["last_update"]["text_kk"] == "Тұрғындарға"


def test_agencies_week_from_r17_takes_its_order_and_counts():
    week = {"lagging": [{"service": "road", "overdue": 5, "open": 15}, {"service": "lighting", "overdue": 3, "open": 7}],
            "joint": 3, "handoffs": 4, "link": "#agencies", "demo": True}
    a = blocks.agencies(week, "r17", None, "none", as_of=NOW)
    assert [x["service"]["id"] for x in a["lagging"]] == ["road", "lighting"]
    assert (a["joint"], a["handoffs_week"], a["link"], a["board"]) == (3, 4, "#agencies", [])
    # «сервиса нет» у R17 — это «нет данных», а не нули
    none = blocks.agencies({"lagging": [], "joint": 0, "handoffs": 0, "empty": True, "source": "none"}, "r17",
                           {"services": [], "empty": True, "source": "none"}, "r17", as_of=NOW)
    assert none["available"] is False


def test_meetings_from_r13_board_block():
    block = {"next": {"id": "m-2", "district": "nura", "title_ru": "Встреча", "at": (NOW + timedelta(days=5)).isoformat(),
                      "registered": 12, "questions_count": {"published": 4, "answered": 1}, "place": {"label_ru": "Школа"}},
             "orders": [{"id": "o-1", "meeting_id": "m-1", "text_ru": "Свалка", "service": "waste",
                         "due": (NOW - timedelta(days=1)).date().isoformat(), "status": "in_progress", "overdue": True},
                        {"id": "o-2", "meeting_id": "m-1", "text_ru": "Свет", "service": "lighting",
                         "due": (NOW + timedelta(days=3)).date().isoformat(), "status": "todo", "overdue": False}],
             "counts": {"total": 5, "todo": 1, "in_progress": 1, "done": 3, "overdue": 1}, "link": "#meetings", "demo": True}
    m = blocks.meetings_from_block(block, "r13", as_of=NOW, district_names={"nura": {"ru": "Нура", "kk": "Нұра"}})
    assert m["orders"] == {"total": 5, "done": 3, "in_progress": 1, "todo": 1, "overdue": 1, "due_week": 1}
    assert [o["id"] for o in m["items"]] == ["m-1/o-1", "m-1/o-2"] and m["items"][0]["overdue"] is True
    assert m["next"]["questions"] == 4 and m["next"]["place_ru"] == "Школа" and m["link"] == "#meetings"
