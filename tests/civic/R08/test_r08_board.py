"""Раунд 15 · R08: Ситуационный центр (GET akim/board), «Картина недели» (GET akim/week) и чтение соседей.

Соседи R17/R16/R13 подменяются модулями в sys.modules (как их модуль появится в сборке): функция чтения,
сервис make_service по маршруту CONTRACT §7, сбой. Без соседей — блок «пока нет данных», фикстура — только
в демо-сборке без демо-мира. Тепловая карта не нужна (heat=False): KPI и пульс считает «Картина дня».
"""
import json
import sqlite3
import sys
import types
from datetime import datetime, timedelta

import pytest

from r08_helpers import NOW, TZ, rec
from ui.civic_akim import AkimService, api, board, neighbors, week

BOARD = "/api/civic/v2/akim/board"
WEEK = "/api/civic/v2/akim/week"
NEIGHBOR_MODULES = ("ui.civic_agencies", "ui.civic_together", "ui.civic_meetings")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    """Соседей нет (как в FINAL-4), кэш табло пуст, окружение без демо-мира."""
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    monkeypatch.delenv("CIVIC_DB_PATH", raising=False)
    monkeypatch.delenv("CIVIC_DB", raising=False)
    for name in NEIGHBOR_MODULES:
        monkeypatch.setitem(sys.modules, name, None)   # None в sys.modules = «модуля нет» (ModuleNotFoundError)
    board.reset_cache()
    neighbors.reset_cache()
    yield
    board.reset_cache()
    neighbors.reset_cache()


def records():
    out = [rec(i, age_days=i % 10, category="snow_ice" if i % 3 else "roads") for i in range(30)]
    out += [rec(100 + i, age_days=3, history=[(0.5, "accepted"), (1, "fixed")]) for i in range(4)]
    return out


def svc(**kw):
    recs = kw.pop("recs", None) or records()
    kw.setdefault("objects", None)
    kw.setdefault("proposals", None)
    return AkimService(heat=False, records=lambda since: recs, clock=lambda: NOW, **kw)


def get(path, service, query=None, staff=True):
    return api.handle_get(path, query or {}, service=service, staff=staff)


def fake_module(monkeypatch, name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


# ---------------------------------------------------------------- доступ

@pytest.mark.parametrize("path", [BOARD, WEEK])
def test_staff_only(path):
    s = svc(examples=True)
    for staff in (False, None, "1", 1):
        status, body = api.handle_get(path, {}, service=s, staff=staff)
        assert status == 403 and body["error"] == "forbidden"
    status, _ = get(path, s)
    assert status == 200


def test_summary_stays_public_and_unchanged_shape():
    """«Картина дня» FINAL-4 не требует входа (шаг 4 сценария) — новые маршруты её не трогают."""
    status, body = api.handle_get("/api/civic/v2/akim/summary", {}, service=svc())
    assert status == 200 and "kpi" in body and "pulse" in body


# ---------------------------------------------------------------- каждый блок без соседа

def test_board_without_neighbors_says_no_data_not_error():
    status, b = get(BOARD, svc(examples=False))
    assert status == 200
    for block in ("services", "crisis", "together", "meetings"):
        assert b[block]["available"] is False and b[block]["reason"] == "module_not_ready", block
        assert b["sources"][block] == "none"
    assert b["kpi"]["new_day"]["value"] == b["kpi"]["new_day"]["series"][-1]
    # Без соседей на экране — только свои блоки (без карты R07 в тесте — «Нужно решение акима» и прогноз R13 FINAL-4).
    assert set(b["slides"]) <= {"decisions", "forecast", "topics", "districts"}
    assert b["rotate_s"] == 15


def test_fixture_only_in_demo_build_and_never_with_demo_world(monkeypatch):
    status, b = get(BOARD, svc(demo_build=True))
    assert status == 200
    for block in ("services", "crisis", "together", "meetings"):
        assert b[block]["available"] is True and b[block]["source"] == "fixture" and b[block]["demo"] is True
    assert b["demo"]["any"] is True
    assert b["slides"][0] == "crisis"   # активный кризис — первым
    board.reset_cache()
    status, b = get(BOARD, svc(demo_build=True, demo_world=True))
    for block in ("services", "crisis", "together", "meetings"):
        assert b[block]["available"] is False, block
    board.reset_cache()
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
    status, b = get(BOARD, svc(demo_build=True))
    assert b["services"]["available"] is False and b["sources"]["demo_world"] is True
    board.reset_cache()
    status, b = get(BOARD, svc(demo_build=False))   # обычная сборка: пример не подмешивается никогда
    assert b["together"]["available"] is False


def test_fixture_lives_in_today():
    """Фикстура сдвигается к «сейчас»: кризис начался сегодня утром, встреча Есиля — в будущем."""
    _, b = get(BOARD, svc(demo_build=True))
    started = datetime.fromisoformat(b["crisis"]["active"][0]["started_at"])
    assert timedelta(0) < NOW - started < timedelta(hours=12)
    assert datetime.fromisoformat(b["meetings"]["next"]["at"]) > NOW


# ---------------------------------------------------------------- R17 функцией

def test_r17_function_board_and_lagging(monkeypatch):
    seen = {}

    def board_for_akim(db_path=None, *, days=7, district=None, now=None):
        seen.update(days=days, district=district, now=now)
        return {"days": 7, "items": [
            {"service": "water", "open_count": 9, "overdue_count": 4, "median_days": 3.25, "verified_pct": 40},
            {"service": "road", "open": 12, "overdue": 4, "median_answer_days": 5.0, "verified_share": 0.5},
            {"service": "lighting", "open": 3, "overdue": 0},
            {"service": "waste", "open": 2, "overdue": 1, "median_answer_days": 1.0},
            {"bad": "row"}, "строка"],
            "joint": {"open": 2, "week": 3}, "handoffs": 5}

    fake_module(monkeypatch, "ui.civic_agencies", board_for_akim=board_for_akim, incidents_for_akim=lambda **kw: [])
    _, b = get(BOARD, svc(), {"district": ["nura"]})
    sv = b["services"]
    assert sv["source"] == "r17" and seen["district"] == "nura" and seen["days"] == 7
    water = next(it for it in sv["items"] if it["service"] == "water")
    assert (water["open"], water["overdue"], water["median_answer_days"], water["verified_share"]) == (9, 4, 3.2, 0.4)
    assert water["ru"] == "Водоканал" and water["kk"]                     # названия — из таблицы R08 (CONTRACT §3)
    # Порядок «отстающих» — как у R17 lagging(): просрочки, затем открытые; без просрочек службы в «отстающих» нет.
    assert sv["lagging"] == ["road", "water", "waste"] and sv["lagging_source"] == "r17_order"
    assert sv["joint"] == {"open": 2, "week": 3} and sv["handoffs"] == {"week": 5}
    assert "services" in b["slides"]


def test_r17_own_lagging_order_wins(monkeypatch):
    fake_module(monkeypatch, "ui.civic_agencies",
                board_for_akim=lambda **kw: {"items": [{"service": "water", "overdue": 1}, {"service": "road", "overdue": 9}],
                                             "lagging": ["water", "road"]})
    _, b = get(BOARD, svc())
    assert b["services"]["lagging"] == ["water", "road"] and b["services"]["lagging_source"] == "r17"


def test_r17_failure_is_empty_block_not_error(monkeypatch):
    def boom(**kw):
        raise RuntimeError("база R17 сломалась")

    fake_module(monkeypatch, "ui.civic_agencies", board_for_akim=boom, incidents_for_akim=boom)
    status, b = get(BOARD, svc(demo_build=True))
    assert status == 200
    assert b["services"] == {**b["services"], "available": False, "reason": "module_failed"}
    assert b["crisis"]["available"] is False and b["crisis"]["reason"] == "module_failed"
    assert b["together"]["source"] == "fixture"   # другие соседи не страдают


def test_crisis_tasks_by_service_and_pulse_link(monkeypatch):
    incident = {
        "id": "inc-7", "kind": "blizzard", "title_ru": "Буран", "title_kk": "Боран", "status": "active",
        "zone": {"kind": "district", "district": "nura", "targets": ["yard-1"], "geometry": None},
        "started_at": (NOW - timedelta(hours=3)).isoformat(),
        "tasks": [{"service": "street_cleaning", "status": "done"}, {"service": "street_cleaning", "status": "doing"},
                  {"service": "transport", "status": "todo"}],
        "updates": [{"at": (NOW - timedelta(hours=2)).isoformat(), "text_ru": "первое", "text_kk": "бірінші", "public": True},
                    {"at": (NOW - timedelta(hours=1)).isoformat(), "text_ru": "внутреннее", "public": False},
                    {"at": (NOW - timedelta(minutes=30)).isoformat(), "text_ru": "свежее", "text_kk": "жаңа"}],
        "demo": False}
    fake_module(monkeypatch, "ui.civic_agencies", incidents_for_akim=lambda **kw: [incident, {"id": "inc-old", "status": "closed"}])
    _, b = get(BOARD, svc())
    c = b["crisis"]["active"][0]
    assert b["crisis"]["closed"] == 1
    assert c["tasks"] == {"total": 3, "done": 1, "doing": 1, "todo": 1}
    assert [(s["service"], s["done"], s["total"]) for s in c["services"]] == [("street_cleaning", 1, 2), ("transport", 0, 1)]
    assert c["last_update"]["text_ru"] == "свежее"            # непубличное обновление не показываем
    assert c["zone"]["district_ru"] == "Нура" and c["zone"]["targets"] == 1
    assert c["link"] == "/#agencies/crisis/inc-7"
    items = [{"kind": "spike", "category": "snow_ice", "district": "nura"},
             {"kind": "spike", "category": "utilities", "district": "esil"},
             {"kind": "new_hot", "category": "roads", "district": "nura"},
             {"kind": "spike", "category": "roads", "district": "nura"},      # в буран растут и «Дороги» — тот же штаб
             {"kind": "spike_city", "category": "waste", "district": None},   # мусор по городу — кнопки штаба нет
             {"kind": "spike", "category": "lighting", "district": "esil"},   # не кризисная тема, кризиса нет
             {"kind": "spike_city", "category": "snow_ice", "district": None}]
    neighbors.pulse_links(items, b["crisis"])
    assert items[0]["crisis"] == {"link": "/#agencies/crisis/inc-7", "incident": "inc-7", "kind": "blizzard"}
    assert items[1]["crisis"] == {"link": "/#agencies/crisis/new/heat_outage/esil", "incident": None,
                                  "kind": "heat_outage"}
    assert "crisis" not in items[2]                          # тревога об одном месте ведёт на карту, не в штаб
    assert items[3]["crisis"]["incident"] == "inc-7"
    assert "crisis" not in items[4] and "crisis" not in items[5]
    assert items[6]["crisis"]["incident"] == "inc-7"         # снег по городу — к идущему бурану


def test_crisis_own_link_from_r17(monkeypatch):
    fake_module(monkeypatch, "ui.civic_agencies",
                incidents_for_akim=lambda **kw: [{"id": "inc-1", "status": "active", "link": "#agencies/crisis/inc-1",
                                                  "zone": {"kind": "district", "district": None}}])
    _, b = get(BOARD, svc())
    assert b["crisis"]["active"][0]["link"] == "/#agencies/crisis/inc-1"   # со страницы центра — в Birge, а не на себя


# ---------------------------------------------------------------- R17 через make_service (запасной путь)

def test_service_fallback_reads_contract_route(monkeypatch, tmp_path):
    db = tmp_path / "civic.sqlite3"
    sqlite3.connect(db).close()
    calls = []

    class Service:
        def __init__(self, path):
            calls.append(("init", path))

        def handle(self, method, path, query, body, principal, context):
            calls.append((method, path, query, principal["role"], getattr(principal, "is_staff", None)))
            assert principal.check_csrf("любой") is False     # служебный сотрудник ничего не пишет
            if path.endswith("/agencies/board"):
                return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"items": [{"service": "road", "overdue": 2}]}}}
            if path.endswith("/incidents"):
                return {"status": 200, "headers": {}, "body": {"items": []}}
            return {"status": 404, "headers": {}, "body": {"error": "not_found"}}

    fake_module(monkeypatch, "ui.civic_agencies", make_service=Service)
    s = svc(db_path=str(db))
    _, b = get(BOARD, s)
    assert b["services"]["source"] == "r17-service" and b["services"]["items"][0]["overdue"] == 2
    assert b["crisis"]["available"] is True and b["crisis"]["active"] == []
    assert ("GET", "/api/civic/v2/agencies/board", "days=7", "staff", True) in calls
    assert sum(1 for c in calls if c[0] == "init") == 1     # один сервис соседа на процесс
    board.reset_cache()
    get(BOARD, s)
    assert sum(1 for c in calls if c[0] == "init") == 1


def test_service_fallback_needs_existing_database(monkeypatch, tmp_path):
    fake_module(monkeypatch, "ui.civic_agencies", make_service=lambda path: pytest.fail("сервис не создаётся без базы"))
    _, b = get(BOARD, svc(db_path=str(tmp_path / "нет.sqlite3")))
    assert b["services"]["available"] is False and b["services"]["reason"] == "no_database"


def test_db_path_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CIVIC_DB_PATH", str(tmp_path / "x.sqlite3"))
    assert neighbors.Settings().db_path == str(tmp_path / "x.sqlite3")


# ---------------------------------------------------------------- R16 «Жители вместе»

def initiative(i, status, *, joined=5, starts=None, report_at=None, district="nura", supported=False, yard=None):
    return {"id": f"i-{i}", "kind": "cleanup", "title": f"Дело {i}", "lang": "ru", "status": status, "joined": joined,
            "target": {"kind": "area", "id": yard or f"yard-{i}", "label_ru": f"Двор {i}", "label_kk": f"Аула {i}"},
            "district": district, "starts_at": (starts or NOW + timedelta(days=1)).isoformat(),
            "support": {"by_akimat": supported, "note": "Мешки"} if supported else None,
            "report": {"text": "ok", "at": report_at.isoformat()} if report_at else None,
            "author_device": "dev-секрет", "demo": False}


def test_together_privacy_and_counts(monkeypatch):
    items = [initiative(1, "published", joined=14, supported=True, yard="yard-77"),
             initiative(2, "done", joined=22, starts=NOW - timedelta(days=3), report_at=NOW - timedelta(days=3)),
             initiative(3, "on_review", joined=0), initiative(4, "hidden", joined=50),
             initiative(5, "done", joined=40, starts=NOW - timedelta(days=30), report_at=NOW - timedelta(days=30)),
             initiative(6, "published", joined=3, district="esil")]
    fake_module(monkeypatch, "ui.civic_together",
                together_for_akim=lambda **kw: {"initiatives": items,
                                                "yards": [{"id": "yard-2", "label_ru": "Двор 2", "members": 31}]})
    _, b = get(BOARD, svc(), {"district": "nura"})
    t = b["together"]
    ids = [r["id"] for r in t["top"]]
    assert "i-3" not in ids and "i-4" not in ids and "i-6" not in ids     # на проверке, скрытые, чужой район
    assert ids == ["i-1", "i-2"]                                          # сначала ближайшее, потом сделанное
    assert t["counts"] == {"upcoming": 1, "joined_upcoming": 14, "done": 1, "neighbors_done": 22, "supported": 1}
    assert "dev-секрет" not in json.dumps(b, ensure_ascii=False)          # устройство автора не уходит наружу
    assert t["yard_of_week"]["id"] == "yard-2" and t["yard_of_week"]["members"] == 31
    assert t["yard_of_week"]["initiative"]["id"] == "i-2"


def test_together_verified_week_from_kpi(monkeypatch):
    fake_module(monkeypatch, "ui.civic_together", together_for_akim=lambda **kw: {"initiatives": []})
    _, b = get(BOARD, svc())
    # «Проверено жителями» — то же число, что в KPI; нет проверки в данных — None (экран молчит, а не пишет 0).
    assert b["together"]["verified_week"] == (b["kpi"]["fixed_week"]["verified"]
                                              if b["kpi"]["verification_available"] else None)
    assert "together" not in b["slides"]                                  # нечего показать — слайда нет


# ---------------------------------------------------------------- R13 поручения и прогноз

def test_meeting_orders(monkeypatch):
    m = {"id": "m-1", "district": "nura", "title_ru": "Встреча", "title_kk": "Кездесу",
         "at": (NOW - timedelta(days=7)).isoformat(), "registered": 40,
         "orders": [{"id": "o-1", "text_ru": "Свет", "service": "lighting", "due": "2026-10-09", "status": "in_progress"},
                    {"id": "o-2", "text_ru": "Переход", "service": "traffic", "due": "2026-10-20", "status": "todo"},
                    {"id": "o-3", "text_ru": "Мусор", "service": "waste", "due": "2026-10-05", "status": "done"},
                    {"id": "o-4", "text_ru": "Без статуса", "due": None, "status": "что-то"}]}
    nxt = {"id": "m-2", "district": "nura", "title_ru": "Следующая", "at": (NOW + timedelta(days=5)).isoformat(),
           "registered": 12, "orders": []}
    fake_module(monkeypatch, "ui.civic_meetings", meetings_for_akim=lambda **kw: [m, nxt])
    _, b = get(BOARD, svc())
    mt = b["meetings"]
    assert mt["counts"] == {"total": 4, "overdue": 1, "todo": 2, "in_progress": 1, "done": 1}
    assert [o["id"] for o in mt["orders"]] == ["o-1", "o-2", "o-4", "o-3"]   # просроченное — первым, сделанное — последним
    assert mt["orders"][0]["overdue"] is True and mt["orders"][1]["days_left"] == 8
    assert mt["orders"][0]["ru"] == "Служба освещения"
    assert mt["next"]["id"] == "m-2" and mt["next"]["registered"] == 12


def test_forecast_week_preferred_month_fallback(monkeypatch):
    # R13 без недельной функции (как в FINAL-4) — подменой, а не тем, что лежит в сборке: в B0 у R13 уже есть
    # week_block, и тест не должен зависеть от того, какая версия R13 рядом (просьба R01, STATUS 15 окт).
    import ui.civic_forecast as real
    fake_module(monkeypatch, "ui.civic_forecast", attention_next_month=real.attention_next_month)
    _, b = get(BOARD, svc())
    assert b["forecast"]["source"] == "r13-month" and b["forecast"]["horizon"] == "month"   # прогноз на месяц
    assert b["forecast"]["prototype"] is True and 1 <= len(b["forecast"]["items"]) <= 5
    assert b["forecast"]["items"][0]["reason_ru"]
    week_fn = lambda district=None, k=5, now=None: {  # noqa: E731
        "horizon": "week", "items": [{"target": {"kind": "area", "id": "yard-1", "label_ru": "Двор"},
                                      "district": "nura", "level": "high", "reason_ru": "Снегопад", "reason_kk": "Қар"}],
        "method_ru": "Как считаем"}
    fake_module(monkeypatch, "ui.civic_forecast", week_forecast=week_fn, attention_next_month=real.attention_next_month)
    board.reset_cache()
    _, b = get(BOARD, svc())
    f = b["forecast"]
    assert f["source"] == "r13-week" and f["horizon"] == "week" and f["items"][0]["reason_kk"] == "Қар"
    assert f["method_ru"] == "Как считаем" and f["demo"] is True


# ---------------------------------------------------------------- «Картина недели»

def test_week_bounds_and_comparison():
    recs = [rec(i, at=datetime(2026, 10, 5, 9, tzinfo=TZ) + timedelta(days=i % 7, hours=i % 5)) for i in range(21)]
    recs += [rec(50 + i, at=datetime(2026, 9, 28, 12, tzinfo=TZ) + timedelta(days=i)) for i in range(7)]
    recs += [rec(90, at=datetime(2026, 10, 6, 9, tzinfo=TZ), history=[(1, "accepted"), (2, "fixed")])]
    status, w = get(WEEK, svc(recs=recs), {"date": "2026-10-08"})
    assert status == 200
    assert (w["week"]["start"], w["week"]["end"], w["week"]["current"]) == ("2026-10-05", "2026-10-11", False)
    assert w["week"]["as_of"].startswith("2026-10-11T23:59:59")
    assert w["kpi"]["new"]["value"] == 22 and w["kpi"]["new"]["prev"] == 7 and sum(w["kpi"]["new"]["series"]) == 22
    # База неделей раньше < 10 — разница в штуках («на 15 больше»), как во всей «Картине дня» (summary.change).
    assert (w["kpi"]["new"]["mode"], w["kpi"]["new"]["abs"]) == ("abs", 15)
    assert w["kpi"]["fixed"]["value"] == 1
    assert w["text"]["ru"][0].startswith("5–11") and "поступило 22 обращения — на 15 больше" in w["text"]["ru"][0]
    assert "өтініш түсті" in w["text"]["kk"][0]


def test_current_week_counts_to_now_and_future_days_are_null():
    status, w = get(WEEK, svc())
    assert status == 200 and w["week"]["current"] is True and w["week"]["start"] == "2026-10-12"   # NOW — понедельник
    assert w["kpi"]["new"]["series"][1:] == [None] * 6
    assert w["week"]["days_counted"] == 1


@pytest.mark.parametrize("query,field", [({"date": "2026-10-13"}, "date"), ({"date": "вчера"}, "date"),
                                         ({"district": "марс"}, "district")])
def test_week_bad_params(query, field):
    status, body = get(WEEK, svc(), query)
    assert status == 400 and body["field"] == field


def test_week_neighbor_sentences_only_for_current_week(monkeypatch):
    fake_module(monkeypatch, "ui.civic_meetings", meetings_for_akim=lambda **kw: [
        {"id": "m-1", "district": "nura", "orders": [{"id": "o", "text_ru": "x", "due": "2026-10-01", "status": "todo"}]}])
    _, cur = get(WEEK, svc())
    assert any("Поручения встреч" in line for line in cur["text"]["ru"])
    _, past = get(WEEK, svc(), {"date": "2026-10-01"})
    assert not any("Поручения встреч" in line for line in past["text"]["ru"])
    assert past["meetings"]["available"] is True                          # блок есть, текст — только про неделю


def test_week_module_direct_call():
    w = week.build(svc(), date="2026-10-12")
    assert w["week"]["label_ru"] == "12–18 окт" and w["week"]["label_kk"] == "12–18 қазан"


# ---------------------------------------------------------------- настоящие форматы соседей (раунд 15)

def test_r17_board_snapshot_format(monkeypatch):
    """R17 board_snapshot(days, district): {"services": [20 строк], "totals": {...}, "demo", "empty"}."""
    seen = {}

    def board_snapshot(days=30, district=None):
        seen.update(days=days, district=district)
        rows = [{"service": sid, "open": 0, "overdue": 0, "median_answer_days": None, "verified_share": None,
                 "returned": 0, "joint": 0, "handoffs_in": 0, "handoffs_out": 0} for sid in ("road", "water", "lighting")]
        rows[0].update(open=12, overdue=5, median_answer_days=2.5, verified_share=0.5)
        rows[1].update(open=20, overdue=5)
        return {"services": rows, "totals": {"open": 32, "overdue": 10, "joint": 3, "handoffs": 7, "loops": 1},
                "demo": False, "empty": False}

    fake_module(monkeypatch, "ui.civic_agencies", board_snapshot=board_snapshot, active_incidents=lambda district=None: [])
    _, b = get(BOARD, svc())
    sv = b["services"]
    assert seen == {"days": 7, "district": None} and sv["source"] == "r17"
    assert sv["lagging"] == ["water", "road"]                 # 5 = 5 просрочек → больше открытых первым (как R17)
    assert sv["joint"] == {"open": None, "week": 3} and sv["handoffs"] == {"week": 7}
    assert sv["totals"]["loops"] == 1


def test_r17_empty_board_has_no_slide(monkeypatch):
    fake_module(monkeypatch, "ui.civic_agencies",
                board_snapshot=lambda days=30, district=None: {"services": [{"service": "road", "open": 0, "overdue": 0}],
                                                             "totals": {}, "empty": True},
                active_incidents=lambda district=None: [])
    _, b = get(BOARD, svc())
    assert b["services"]["available"] is True and b["services"]["items"] == [] and "services" not in b["slides"]


def test_r17_active_incidents_public_view(monkeypatch):
    view = {"id": "inc-9", "kind": "blizzard", "title_ru": "Буран", "title_kk": "Боран", "status": "active",
            "zone": {"kind": "district", "district": "nura"}, "zone_label": {"ru": "район Нура", "kk": "Нұра ауданы"},
            "started_at": (NOW - timedelta(hours=2)).isoformat(),
            "updates": [{"at": (NOW - timedelta(hours=1)).isoformat(), "text_ru": "Расчищаем", "text_kk": "Тазартамыз"}],
            "progress": [{"service": "street_cleaning", "done": 2, "doing": 1, "total": 4},
                         {"service": "transport", "done": 1, "doing": 0, "total": 1}],
            "link": "#agencies/crisis/inc-9", "demo": True}
    fake_module(monkeypatch, "ui.civic_agencies", active_incidents=lambda district=None: [view],
                crisis_link=lambda district=None, kind="blizzard": f"#agencies/crisis/new/{kind}")
    _, b = get(BOARD, svc())
    c = b["crisis"]["active"][0]
    assert c["tasks"] == {"total": 5, "done": 3, "doing": 1, "todo": 1}
    assert [(s["service"], s["done"], s["total"]) for s in c["services"]] == [("street_cleaning", 2, 4), ("transport", 1, 1)]
    assert c["zone"]["label_ru"] == "район Нура" and c["link"] == "/#agencies/crisis/inc-9"
    assert c["last_update"]["text_kk"] == "Тазартамыз"
    items = [{"kind": "spike", "category": "utilities", "district": "esil"}]
    neighbors.pulse_links(items, b["crisis"])
    assert items[0]["crisis"]["link"] == "/#agencies/crisis/new/heat_outage"   # адрес — функцией R17


def test_r16_initiatives_summary_format(monkeypatch):
    summary = {"status": "ok", "district": None, "upcoming": 2, "joined_upcoming": 23, "supported": 1, "done": 4,
               "neighbors_done": 51, "on_review": 1,
               "next": [{"id": "i-1", "title": "Субботник", "starts_at": (NOW + timedelta(days=2)).isoformat(),
                         "joined": 14, "district": "nura", "target": {"kind": "area", "id": "yard-1"}, "demo": True}],
               "demo": True}
    fake_module(monkeypatch, "ui.civic_together", initiatives_summary=lambda district=None, db_path=None: summary)
    _, b = get(BOARD, svc())
    t = b["together"]
    assert t["source"] == "r16" and t["counts"] == {"upcoming": 2, "joined_upcoming": 23, "done": 4,
                                                     "neighbors_done": 51, "supported": 1}
    assert t["top"][0]["title"] == "Субботник" and t["top"][0]["joined"] == 14
    assert "on_review" not in json.dumps(t)                     # на проверке — не на экране
    fake_module(monkeypatch, "ui.civic_together", initiatives_summary=lambda district=None, db_path=None: {"status": "no_data"})
    board.reset_cache()
    _, b = get(BOARD, svc())
    assert b["together"]["available"] is False and "together" not in b["slides"]


def test_r13_board_block_format(monkeypatch):
    block = {"next": {"id": "m-2", "district": "nura", "title_ru": "Встреча", "title_kk": "Кездесу",
                      "at": (NOW + timedelta(days=3)).isoformat(), "registered": 40, "demo": True},
             "orders": [{"id": "o-2", "text_ru": "Переход", "text_kk": "Өткел", "service": "traffic", "due": "2026-10-20",
                         "status": "todo", "overdue": False, "meeting_id": "m-1", "district": "nura",
                         "meeting_title_ru": "Встреча 8 окт", "meeting_title_kk": "8 қазан кездесуі",
                         "meeting_at": "2026-10-08T18:00:00+05:00", "demo": True},
                        {"id": "o-1", "text_ru": "Свет", "service": "lighting", "due": "2026-10-09",
                         "status": "in_progress", "overdue": True, "meeting_id": "m-1", "district": "nura", "demo": True}],
             "counts": {"total": 5, "todo": 1, "in_progress": 1, "done": 3, "overdue": 1}, "link": "#meetings", "demo": True}
    fake_module(monkeypatch, "ui.civic_meetings", board_block=lambda db_path=None, district=None, limit=5: block)
    _, b = get(BOARD, svc())
    m = b["meetings"]
    assert m["source"] == "r13" and m["counts"] == {"total": 5, "overdue": 1, "todo": 1, "in_progress": 1, "done": 3}
    assert [o["id"] for o in m["orders"]] == ["o-1", "o-2"]     # просроченное — первым
    assert m["orders"][1]["meeting"]["title_ru"] == "Встреча 8 окт" and m["next"]["registered"] == 40
    fake_module(monkeypatch, "ui.civic_meetings", board_block=lambda db_path=None, district=None, limit=5: None)
    board.reset_cache()
    _, b = get(BOARD, svc())
    assert b["meetings"]["available"] is False and b["meetings"]["reason"] == "no_data"


# ---------------------------------------------------------------- «Картина дня» 2.0: соседи в публичной сводке

def test_summary_neighbors_fresh_every_answer(monkeypatch):
    """«Я приду» 14 → 15 видно сразу: блоки соседей не ждут 30-секундного кэша расчёта (и не портят его)."""
    joined = {"n": 14}

    def initiatives_summary(district=None, db_path=None):
        return {"status": "ok", "upcoming": 1, "joined_upcoming": joined["n"], "supported": 0, "done": 0,
                "neighbors_done": 0, "next": [], "demo": False}

    fake_module(monkeypatch, "ui.civic_together", initiatives_summary=initiatives_summary)
    s = svc()
    first = s.summary(now=NOW)
    joined["n"] = 15
    second = s.summary(now=NOW)
    assert first["together"]["counts"]["joined_upcoming"] == 14 and second["together"]["counts"]["joined_upcoming"] == 15
    assert first["kpi"] is second["kpi"]                       # сам расчёт — из кэша
    cached = next(iter(s._cache.values()))[1]
    assert "together" not in cached and "crisis" not in cached # кэш без блоков соседей


def test_summary_past_day_has_no_neighbors(monkeypatch):
    fake_module(monkeypatch, "ui.civic_together", initiatives_summary=lambda **kw: pytest.fail("прошлый день не читает соседей"))
    out = svc().summary(date="2026-10-10", now=NOW)
    for block in ("together", "meetings", "forecast", "crisis"):
        assert out[block]["available"] is False and out[block]["reason"] == "past_day"


def test_summary_pulse_links_fresh(monkeypatch):
    incidents = []
    fake_module(monkeypatch, "ui.civic_agencies", active_incidents=lambda district=None: list(incidents))
    recs = [rec(i, age_days=1 + i % 6, category="snow_ice") for i in range(40)]
    s = svc(recs=recs)
    out = s.summary(now=NOW)
    cached = next(iter(s._cache.values()))[1]
    assert all("crisis" not in a for a in cached["pulse"]["items"])   # кэш без ссылок штаба
    incidents.append({"id": "inc-1", "kind": "blizzard", "status": "active", "zone": {"kind": "district", "district": "nura"},
                      "progress": [], "link": "#agencies/crisis/inc-1"})
    again = s.summary(now=NOW)
    assert again["crisis"]["active"][0]["id"] == "inc-1"
    for a in again["pulse"]["items"]:
        if a["kind"] in ("spike", "spike_new", "spike_city") and a.get("district") in (None, "nura"):
            assert a["crisis"]["incident"] == "inc-1"
    assert out["crisis"]["active"] == []
