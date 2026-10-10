"""R08 раунд 14: подключение функций R06 (ui/civic_store/v2.py, ветка claude/round-14-r06 @ 3d10f7d).

R06 отдаёт словари, а не списки:
    lagging_objects(district)  -> {today, late:[…], stale:[…], counts, by_district, …}
    list_proposals(district=, status=) -> {items:[…], truncated}
Пока шлюз R01 не вызвал bind(service), функции R06 бросают V2Error(503, "module_not_ready") —
тогда «Картина дня» показывает свои демо-фикстуры (помечены «Пример»), а не пустоту и не ошибку.
Модуль R06 здесь подменяется фейком с тем же форматом ответа, чтобы тест не зависел от их базы.
"""
import sys
import types

import pytest

from r08_helpers import NOW
from ui.civic_akim import AkimService, sources


class FakeV2Error(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def r06_object(i, **kw):
    """Объект в формате StageRepository.lagging() R06 (brief)."""
    base = {"id": f"obj-{i}", "title": f"Объект {i}", "kind": "school", "district": "nura", "stage": "construction",
            "planned_end": "2026-11-01", "forecast_end": "2026-11-20", "delay_days": 19, "stale_days": 3,
            "late": True, "stale": False, "demo": True, "geometry": {"type": "Point", "coordinates": [71.4, 51.1]}}
    base.update(kw)
    return base


@pytest.fixture
def fake_r06(monkeypatch):
    """Подменяет ui.civic_store.v2 фейком; возвращает словарь, через который тест задаёт поведение."""
    import ui.civic_store  # настоящий пакет R02 из сборки — нужен как родитель для v2

    state = {"bound": True, "fail": None, "calls": []}
    late = [r06_object(1, delay_days=30), r06_object(2, delay_days=5, stale=True, stale_days=20)]
    stale = [r06_object(2, delay_days=5, stale=True, stale_days=20),
             r06_object(3, delay_days=0, late=False, stale=True, stale_days=40, title={"ru": "Сквер", "kk": "Саябақ"})]
    props = [{"id": "p1", "kind": "bench", "title_ru": "Скамейки", "title_kk": "Орындықтар", "status": "proposal",
              "district": "nura", "votes_up": 7, "votes_down": 1, "created_at": "2026-10-11T09:00:00+05:00", "demo": True}]

    def guard(name, kwargs):
        state["calls"].append((name, kwargs))
        if state["fail"]:
            raise state["fail"]
        if not state["bound"]:
            raise FakeV2Error(503, "module_not_ready", "R06 не связан с хранилищем")

    def lagging_objects(district=None):
        guard("lagging_objects", {"district": district})
        return {"today": "2026-10-12", "district": district, "late": late, "stale": stale,
                "counts": {"total": 9, "late": 2, "stale": 2}, "by_district": {}, "stale_after_days": 14,
                "truncated": False}

    def list_proposals(bbox=None, district=None, status=None, device_id=None, context=None):
        guard("list_proposals", {"district": district, "status": status})
        return {"items": props, "truncated": False}

    mod = types.ModuleType("ui.civic_store.v2")
    mod.lagging_objects, mod.list_proposals = lagging_objects, list_proposals
    monkeypatch.setitem(sys.modules, "ui.civic_store.v2", mod)
    monkeypatch.setattr(ui.civic_store, "v2", mod, raising=False)
    return state


def service():
    return AkimService(heat=False, records=lambda since: [], clock=lambda: NOW)


def test_r06_functions_are_found_and_dicts_unwrapped(fake_r06):
    svc = service()
    assert svc.source_names["objects"] == "r06" and svc.source_names["proposals"] == "r06"
    s = svc.summary(now=NOW)
    o, p = s["objects"], s["proposals"]
    # obj-2 есть и в late, и в stale у R06 — в «Картине дня» он один раз.
    assert [x["id"] for x in o["late"]] == ["obj-1", "obj-2"] and o["late_count"] == 2
    assert [x["id"] for x in o["stale"]] == ["obj-3", "obj-2"] and o["total"] == 3
    # stale_days R06 → «не обновлялось N дней»; title {ru, kk} → title_ru/title_kk.
    sq = o["stale"][0]
    assert (sq["days_since_update"], sq["title_ru"], sq["title_kk"]) == (40, "Сквер", "Саябақ")
    assert o["late"][0]["has_place"] is True
    assert p["available"] and p["open_count"] == 1 and p["top"][0]["title_kk"] == "Орындықтар"
    # Предложения просим только открытые для голосования.
    assert ("list_proposals", {"district": None, "status": "proposal"}) in fake_r06["calls"]


def test_district_is_passed_to_r06(fake_r06):
    service().summary(now=NOW, district="nura")
    assert ("lagging_objects", {"district": "nura"}) in fake_r06["calls"]
    assert ("list_proposals", {"district": "nura", "status": "proposal"}) in fake_r06["calls"]


def test_unbound_r06_falls_back_to_demo_fixtures(fake_r06):
    """Шлюз R01 ещё не связал R06 с базой → фикстуры R08 с меткой «Пример», а не пустой блок."""
    fake_r06["bound"] = False
    s = service().summary(now=NOW)
    assert s["objects"]["available"] and s["objects"]["demo"] is True
    assert {o["id"] for o in s["objects"]["late"]} <= {o["id"] for o in sources.fixture_objects(NOW.date())}
    assert s["proposals"]["available"] and s["proposals"]["demo"] is True


def test_r06_error_is_unavailable_not_fake(fake_r06):
    """Настоящая ошибка R06 (база упала) — блок «не отвечает», а не подставленные примеры."""
    fake_r06["fail"] = FakeV2Error(500, "internal_error", "boom")
    s = service().summary(now=NOW)
    assert s["objects"]["available"] is False and s["objects"]["reason"] == "objects_failed"
    assert s["proposals"]["available"] is False and s["proposals"]["reason"] == "proposals_failed"


@pytest.mark.parametrize("answer, ids", [
    ([{"id": "a"}], ["a"]),
    ({"items": [{"id": "b"}]}, ["b"]),
    ({"late": [{"id": "c"}], "stale": [{"id": "c"}, {"id": "d"}]}, ["c", "d"]),
    (None, []),
])
def test_object_list_shapes(answer, ids):
    assert [o["id"] for o in sources.r06_object_list(answer)] == ids


def test_without_r06_module_fixture_is_used(monkeypatch):
    monkeypatch.setattr(sources, "_r06", lambda names: None)
    svc = service()
    assert svc.source_names["objects"] == "fixture" and svc.source_names["proposals"] == "fixture"


@pytest.mark.parametrize("title, demo, shown", [
    ("Демо: ремонт тротуара (синтетика)", True, "Ремонт тротуара"),
    ("Демо: городское мероприятие без точного места (синтетика)", True, "Городское мероприятие без точного места"),
    ("Школа на 1200 мест", True, "Школа на 1200 мест"),
    ("Демо: ремонт тротуара (синтетика)", False, "Демо: ремонт тротуара (синтетика)"),  # не demo — не трогаем
])
def test_demo_titles_lose_service_words(title, demo, shown):
    """Демо-объекты R06 (seed-r14-demo) называются «Демо: … (синтетика)»; «Пример» страница ставит сама."""
    o = sources.normalize_object({"id": "x", "title": title, "demo": demo}, NOW)
    assert o["title_ru"] == shown and o["title_kk"] == shown
