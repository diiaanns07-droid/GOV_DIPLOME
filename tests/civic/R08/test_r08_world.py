"""Раунд 15 · R08: что нашла сверка на демо-мире R02 (CIVIC_DEMO_WORLD=1, сборка R01 + соседи).

1. «Нужно решение акима» и «Просрочено — дольше всех»: давняя просрочка не на карте за 7 дней — адрес берётся из цели
   самой жалобы R09 (label_ru / label_kk), а ссылка «на карту» — только у мест, что есть на карте.
2. «Жители вместе»: initiatives_summary() R16 не несёт поддержки акимата, конца дела и адреса — R08 берёт их из
   открытой карточки дела R16 (GET together/initiatives/{id}); «Двор недели» — со страницы двора R16 (подпись, соседи).
   Числа R16 не пересчитываются; скрытое и «на проверке» не показывается.
"""
import sqlite3
import sys
import types
from datetime import timedelta

import pytest

from r08_helpers import NOW, rec
from ui.civic_akim import AkimService, api, board, neighbors

BOARD = "/api/civic/v2/akim/board"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("CIVIC_DEMO_WORLD", raising=False)
    monkeypatch.delenv("CIVIC_DB_PATH", raising=False)
    monkeypatch.delenv("CIVIC_DB", raising=False)
    for name in ("ui.civic_agencies", "ui.civic_together", "ui.civic_meetings"):
        monkeypatch.setitem(sys.modules, name, None)
    board.reset_cache()
    neighbors.reset_cache()
    yield
    board.reset_cache()
    neighbors.reset_cache()


def svc(recs=None, **kw):
    recs = recs if recs is not None else [rec(i, age_days=i % 5) for i in range(6)]
    kw.setdefault("objects", None)
    kw.setdefault("proposals", None)
    return AkimService(heat=False, records=lambda since: recs, clock=lambda: NOW, **kw)


def fake_module(monkeypatch, name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


def _delay():
    return {"reason_code": "needs_decision", "problem_ru": "Нет хозяина", "problem_kk": "Иесі жоқ",
            "options": [{"ru": "Принять", "kk": "Қабылдау"}, {"ru": "Передать", "kk": "Беру"}]}


# ---------------------------------------------------------------- 1. адрес давней просрочки

def test_place_from_complaint_target_when_not_on_map():
    yard = {"kind": "area", "id": "yard-1", "label_ru": "Двор — улица 206", "label_kk": "Аула — 206 көшесі"}
    approx = {"kind": "cell", "id": "cell-9", "label_ru": "Примерное место", "label_kk": "Шамамен орны",
              "approximate": True}
    a = rec(1, age_days=20, category="roads", status="in_progress", target=yard)
    b = rec(2, age_days=25, category="roads", status="in_progress", target=approx)
    for r in (a, b):
        r["delay"] = _delay()
    s = svc([a, b]).summary(now=NOW)
    d = {i["id"]: i for i in s["decisions"]["items"]}
    assert d["c-r08-1"]["place_ru"] == "Двор — улица 206" and d["c-r08-1"]["place_kk"] == "Аула — 206 көшесі"
    assert d["c-r08-1"]["target"] is None          # места нет на карте (карты нет) — без ссылки «на карту»
    assert d["c-r08-2"]["place_ru"] is None        # «примерное место» адресом не считаем
    o = {i["id"]: i for i in s["overdue"]["items"]}
    assert o["c-r08-1"]["place_ru"] == "Двор — улица 206" and o["c-r08-1"]["on_map"] is False
    assert o["c-r08-2"]["place_ru"] is None
    # то же в Ситуационном центре (коротко)
    _, bd = api.handle_get(BOARD, {}, service=svc([a, b]), staff=True)
    assert bd["decisions"]["items"][0]["place"] in (None, {"ru": "Двор — улица 206", "kk": "Аула — 206 көшесі"})
    assert {"ru": "Двор — улица 206", "kk": "Аула — 206 көшесі"} in [i["place"] for i in bd["decisions"]["items"]]


# ---------------------------------------------------------------- 2. R16: карточка дела и страница двора

def _summary():
    iso = lambda h: (NOW + timedelta(hours=h)).isoformat()  # noqa: E731
    return {"status": "ok", "district": None, "upcoming": 3, "joined_upcoming": 29, "supported": 1, "done": 2,
            "neighbors_done": 31, "on_review": 1, "demo": True,
            "next": [
                {"id": "i-now", "title": "Поможем пожилым", "starts_at": iso(-30), "joined": 6, "district": "nura",
                 "target": {"kind": "area", "id": "yard-2"}, "demo": True},
                {"id": "i-snow", "title": "Расчистим двор", "starts_at": iso(19), "joined": 9, "district": "nura",
                 "target": {"kind": "area", "id": "yard-3"}, "demo": True},
                {"id": "i-sat", "title": "Субботник", "starts_at": iso(40), "joined": 14, "district": "nura",
                 "target": {"kind": "area", "id": "yard-1"}, "demo": True},
            ]}


DETAILS = {
    "i-now": {"id": "i-now", "status": "published", "kind": "help", "lang": "ru", "joined": 6,
              "starts_at": None, "ends_at": (NOW + timedelta(hours=30)).isoformat(), "support": None,
              "target": {"kind": "area", "id": "yard-2", "label_ru": "Двор — улица Тауелсиздик",
                         "label_kk": "Аула — Тәуелсіздік көшесі"}, "author_device": "секрет"},
    "i-snow": {"id": "i-snow", "status": "published", "kind": "snow", "lang": "kk", "joined": 9,
               "ends_at": (NOW + timedelta(hours=22)).isoformat(),
               "support": {"by_akimat": True, "inventory": True, "pickup_service": "street_cleaning", "note": "Лопаты"},
               "target": {"kind": "area", "id": "yard-3", "label_ru": "Двор — улица 206", "label_kk": "Аула — 206 көшесі"}},
    "i-sat": {"id": "i-sat", "status": "published", "kind": "cleanup", "lang": "ru", "joined": 14,
              "ends_at": (NOW + timedelta(hours=43)).isoformat(), "support": None,
              "target": {"kind": "area", "id": "yard-1", "label_ru": "Двор: BI City Tokyo",
                         "label_kk": "Аула: BI City Tokyo"}},
}
YARD = {"yard": {"id": "yard-1", "label_ru": "Двор: BI City Tokyo", "label_kk": "Аула: BI City Tokyo",
                 "district": "nura", "members": 37, "captain": {"display_name": "Айгуль"}},
        "problems": [], "initiatives": [], "feed": []}


def _r16(monkeypatch, db, details=DETAILS, yard=YARD, fail=()):
    calls = []

    class Service:
        def __init__(self, path):
            calls.append(("init", path))

        def handle(self, method, path, query, body, principal, context):
            calls.append((method, path))
            assert method == "GET" and principal.check_csrf("x") is False
            key = path.rsplit("/", 1)[-1]
            if key in fail:
                return {"status": 500, "headers": {}, "body": {"error": "internal"}}
            if "/together/initiatives/" in path and key in details:
                return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"initiative": details[key]}}}
            if "/together/yards/" in path and yard and key == yard["yard"]["id"]:
                return {"status": 200, "headers": {}, "body": {"ok": True, "data": yard}}
            return {"status": 404, "headers": {}, "body": {"error": "not_found"}}

    fake_module(monkeypatch, "ui.civic_together", make_service=Service,
                initiatives_summary=lambda district=None, db_path=None: _summary())
    return calls


def _db(tmp_path):
    db = tmp_path / "civic.sqlite3"
    sqlite3.connect(db).close()
    return str(db)


def test_r16_details_support_end_place_and_yard_of_week(monkeypatch, tmp_path):
    db = _db(tmp_path)
    calls = _r16(monkeypatch, db)
    _, b = api.handle_get(BOARD, {}, service=svc(db_path=db), staff=True)
    t = b["together"]
    # числа R16 — как есть
    assert t["source"] == "r16" and t["counts"] == {"upcoming": 3, "joined_upcoming": 29, "done": 2,
                                                     "neighbors_done": 31, "supported": 1}
    rows = {r["id"]: r for r in t["top"]}
    assert rows["i-snow"]["supported"] is True and rows["i-snow"]["support_note"] == "Лопаты"
    assert rows["i-sat"]["supported"] is False and rows["i-now"]["supported"] is False
    assert rows["i-now"]["ends_at"] == DETAILS["i-now"]["ends_at"]
    assert rows["i-now"]["starts_at"] == _summary()["next"][0]["starts_at"]   # время начала — из сводки R16
    assert rows["i-sat"]["place_ru"] == "Двор: BI City Tokyo" and rows["i-snow"]["lang"] == "kk"
    assert [r["joined"] for r in t["top"]] == [6, 9, 14]
    # «Двор недели»: двор ближайшего дела, где записались больше всего соседей; соседей — со страницы двора R16
    y = t["yard_of_week"]
    assert y["id"] == "yard-1" and y["label_ru"] == "Двор: BI City Tokyo" and y["members"] == 37
    assert y["initiative"]["id"] == "i-sat" and y["district_ru"] == "Нура"
    assert "together" in b["slides"]
    text = repr(b)
    assert "секрет" not in text and "Айгуль" not in text and "author_device" not in text   # §10: только нужные поля
    assert ("GET", "/api/civic/v2/together/yards/yard-1") in calls
    assert sum(1 for c in calls if c[0] == "init") == 1


def test_r16_details_skip_hidden_and_failures(monkeypatch, tmp_path):
    db = _db(tmp_path)
    details = dict(DETAILS, **{"i-sat": dict(DETAILS["i-sat"], status="on_review")})
    _r16(monkeypatch, db, details=details, fail=("i-snow", "yard-1"))
    _, b = api.handle_get(BOARD, {}, service=svc(db_path=db), staff=True)
    rows = {r["id"]: r for r in b["together"]["top"]}
    assert rows["i-sat"]["place_ru"] is None and rows["i-sat"]["supported"] is False   # «на проверке» — не берём
    assert rows["i-snow"]["place_ru"] is None                                            # сбой карточки — как в сводке
    assert rows["i-now"]["place_ru"] == "Двор — улица Тауелсиздик"
    # двор недели — двор дела с адресом (i-now), страница двора недоступна → подпись из карточки дела, без числа соседей
    y = b["together"]["yard_of_week"]
    assert y["id"] == "yard-2" and y["label_ru"] == "Двор — улица Тауелсиздик" and y["members"] is None


def test_r16_details_need_database(monkeypatch, tmp_path):
    fake_module(monkeypatch, "ui.civic_together",
                make_service=lambda path: pytest.fail("сервис R16 не создаётся без базы"),
                initiatives_summary=lambda district=None, db_path=None: _summary())
    _, b = api.handle_get(BOARD, {}, service=svc(db_path=str(tmp_path / "нет.sqlite3")), staff=True)
    t = b["together"]
    assert t["source"] == "r16" and [r["id"] for r in t["top"]] == ["i-now", "i-snow", "i-sat"]
    assert t["yard_of_week"] is None and all(r["place_ru"] is None for r in t["top"])
