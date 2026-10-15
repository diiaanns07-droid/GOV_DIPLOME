"""R01 раунд 15: демо-мир R02 в сборке (research/round-15/CONTRACT.md §11, SCHEMA R02 §4).

- CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1: шлюз зовёт seed_world(db_path, records, now=...) каждого модуля, у которого функция
  есть, с одним now; итог — одна строка «civic-world: R09 743, R06 55 …»; сбой одного модуля не мешает остальным;
- без флага — демо FINAL-4 без изменений (seed_world не зовётся, карта со синтетикой R07);
- с флагом карта не подмешивает синтетику R07 (числа карты = записи R09 мира);
- GET /api/civic/v2/demo/scenes — id сцен 7–9 для палитры (без мира — пусто).
"""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone

import pytest

from ui.web_server import CivicGateway, CivicV2Gateway

CTX = {"headers": {}, "cookies": {}, "client_ip": "127.0.0.1", "host_allowed": True,
       "is_same_origin": True, "is_https": False, "host": "127.0.0.1"}
NOW = datetime(2026, 10, 16, 14, 0, tzinfo=timezone(timedelta(hours=5)))
WORLD = {"schema": "birge-demo-world-v1", "complaints": [{"id": "c-w1500001"}], "works": [], "initiatives": [],
         "scenes": {"scene7": {"yard": "yard-1", "initiative": "i-w15-01"}, "scene8": {"complaint": "c-w1500010"},
                    "scene9": {"incident": "inc-w15-buran"}}}


def seeder(calls, role, result):
    def seed_world(db_path, records, now=None):
        calls.append((role, db_path, records, now))
        if isinstance(result, Exception):
            raise result
        return result
    return seed_world


def test_without_the_flag_nothing_is_seeded(tmp_path):
    calls = []
    modules = {"ui.civic_together": types.SimpleNamespace(seed_world=seeder(calls, "R16", {"inserted": 1}))}
    gateway = CivicV2Gateway(modules=modules, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=False)
    assert gateway.seed_world(now=NOW, world=WORLD) is None and calls == []
    assert CivicV2Gateway.world_line(None) is None
    assert gateway.handle("GET", "/demo/scenes", "", None, CTX)["body"] == {"world": False, "scenes": {}}


def test_flag_follows_the_environment(monkeypatch):
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.setenv("CIVIC_DEMO_WORLD", "1")
    assert CivicV2Gateway(modules={}).demo_world is True
    monkeypatch.setenv("CIVIC_DEMO", "0")    # мир — только в демо-сборке
    assert CivicV2Gateway(modules={}).demo_world is False
    monkeypatch.setenv("CIVIC_DEMO", "1")
    monkeypatch.delenv("CIVIC_DEMO_WORLD")
    assert CivicV2Gateway(modules={}).demo_world is False


def test_every_module_gets_the_same_now_and_whole_world(tmp_path):
    calls = []
    shared = seeder(calls, "R06", {"inserted": 40, "skipped": 15})
    modules = {
        "ui.civic_feedback.v2.integration": types.SimpleNamespace(seed_world=seeder(calls, "R09", {"inserted": 743, "skipped": 0})),
        "ui.civic_store.v2": types.SimpleNamespace(seed_world=shared),
        "ui.civic_store": types.SimpleNamespace(seed_world=shared),   # та же функция в пакете — один вызов
        "ui.civic_together": types.SimpleNamespace(seed_world=seeder(calls, "R16", {"inserted": 42, "skipped": 0})),
        "ui.civic_agencies": types.SimpleNamespace(other=lambda: None),  # без seed_world — пропуск
    }
    gateway = CivicV2Gateway(modules=modules, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=True)
    report = gateway.seed_world(now=NOW, world=WORLD)
    assert [c[0] for c in calls] == ["R09", "R06", "R16"]                     # жалобы R09 — первыми
    assert {c[1] for c in calls} == {str(tmp_path / "c.sqlite3")}
    assert all(c[2] is WORLD and c[3] == NOW for c in calls)
    assert report["roles"] == {"R09": {"inserted": 743, "skipped": 0}, "R06": {"inserted": 40, "skipped": 15},
                               "R16": {"inserted": 42, "skipped": 0}}
    assert CivicV2Gateway.world_line(report) == "civic-world: R09 743, R06 55 (новых 40), R16 42"


def test_a_failing_module_does_not_stop_the_others(tmp_path):
    calls = []
    modules = {"ui.civic_feedback.v2.integration": types.SimpleNamespace(seed_world=seeder(calls, "R09", RuntimeError("x"))),
               "ui.civic_together": types.SimpleNamespace(seed_world=seeder(calls, "R16", {"inserted": 3, "skipped": 0}))}
    gateway = CivicV2Gateway(modules=modules, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=True)
    report = gateway.seed_world(now=NOW, world=WORLD)
    assert report["roles"]["R09"] == {"error": "RuntimeError"} and report["roles"]["R16"]["inserted"] == 3
    assert CivicV2Gateway.world_line(report) == "civic-world: R09 ошибка (RuntimeError), R16 3"


def test_broken_world_file_is_reported_not_fatal(tmp_path, monkeypatch):
    bad = tmp_path / "world.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CIVIC_DEMO_WORLD_PATH", str(bad))
    gateway = CivicV2Gateway(modules={}, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=True)
    report = gateway.seed_world(now=NOW)
    assert report["error"] and report["roles"] == {}
    assert CivicV2Gateway.world_line(report).startswith("civic-world: демо-мир не загружен")
    assert gateway.handle("GET", "/demo/scenes", "", None, CTX)["body"] == {"world": False, "scenes": {}}


def test_scenes_route_gives_scene_ids_after_seeding(tmp_path):
    gateway = CivicV2Gateway(modules={}, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=True)
    gateway.seed_world(now=NOW, world=WORLD)
    reply = gateway.handle("GET", "/demo/scenes", "", None, CTX)
    assert reply["status"] == 200 and reply["body"] == {"world": True, "scenes": WORLD["scenes"]}
    modules = gateway.handle("GET", "/modules", "", None, CTX)["body"]["modules"]
    assert modules["demo.scenes"]["status"] == "ready" and modules["demo.scenes"]["role"] == "R01"


def test_real_world_file_has_the_scenes_r01_needs():
    """Файл мира R02 в сборке: сцены 7–9 с id, которые открывает палитра (если R02 уже сдал мир)."""
    gateway = CivicV2Gateway(modules={}, demo=True, demo_world=True)
    try:
        world = gateway.load_world()
    except (OSError, ValueError) as exc:
        pytest.skip(f"демо-мира R02 в этой сборке ещё нет: {exc}")
    scenes = world.get("scenes") or {}
    assert scenes["scene7"]["yard"].startswith("yard-") and scenes["scene7"]["initiative"]
    assert scenes["scene8"]["complaint"] and scenes["scene9"]["incident"]


def _heat_items(tmp_path, monkeypatch, demo_world):
    """Значки карты /heat и записи, из которых карта их считает (источник, который связал шлюз)."""
    pytest.importorskip("ui.civic_feedback.v2.integration")
    pytest.importorskip("ui.civic_heat.api")
    import ui.civic_heat as civic_heat
    monkeypatch.setattr(civic_heat.service, "_default", None)  # не трогаем общий сервис других тестов
    v1 = CivicGateway.for_project(tmp_path, tmp_path / "civic.sqlite3")
    gateway = CivicV2Gateway(v1, demo=True, demo_world=demo_world)
    reply = gateway.handle("GET", "/heat", "days=30&zoom=12", None, CTX)
    records = civic_heat.service.default_service().records(datetime.now(timezone.utc) - timedelta(days=60))
    monkeypatch.setattr(civic_heat.service, "_default", None)
    assert reply["status"] == 200
    return reply["body"]["items"], records


def test_world_map_takes_complaints_from_r09_only(tmp_path, monkeypatch):
    """FINAL-4: к жалобам R09 карта добавляет синтетику R07 («Нура · 81»). Демо-мир: только жалобы R09 — мир R02,
    засеянный связкой wire() (R02 INTEGRATION §1): числа карты = «Обращения», второго набора нет."""
    from ui.civic_heat import engine
    classic, classic_records = _heat_items(tmp_path / "a", monkeypatch, demo_world=False)
    world, world_records = _heat_items(tmp_path / "b", monkeypatch, demo_world=True)
    assert sum(i.get("count", 0) for i in classic) > 20 and any(engine.is_r07_example(r) for r in classic_records)
    assert world_records and not any(engine.is_r07_example(r) for r in world_records)
    assert any(str(r.get("id", "")).startswith("c-w15") for r in world_records), [r.get("id") for r in world_records[:5]]
    assert sum(i.get("count", 0) for i in world) > 20, json.dumps(world, ensure_ascii=False)[:300]


def test_world_is_materialized_once_with_the_r02_helper(tmp_path):
    """R02 INTEGRATION §1: мир материализуется один раз (абсолютные времена от одного now) и уходит модулям."""
    calls, made = [], []

    def materialize(world, now):
        made.append(now)
        return dict(world, materialized=now.isoformat())

    modules = {"ml.datasets.demo_world_io": types.SimpleNamespace(materialize=materialize),
               "ui.civic_together": types.SimpleNamespace(seed_world=seeder(calls, "R16", {"inserted": 2, "skipped": 0})),
               "ui.civic_agencies": types.SimpleNamespace(seed_world=seeder(calls, "R17", {"inserted": 3, "skipped": 0}))}
    gateway = CivicV2Gateway(modules=modules, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=True)
    report = gateway.seed_world(now=NOW, world=WORLD)
    assert made == [NOW]
    assert [c[2]["materialized"] for c in calls] == [NOW.isoformat()] * 2
    assert report["scenes"] == WORLD["scenes"]


def test_r09_without_seed_world_gets_the_r02_helper_into_its_live_store(tmp_path):
    """Пока у R09 нет seed_world, жалобы мира кладёт помощник R02 seed_r09 в то же хранилище R09, что у карты."""
    seen = []
    live = object()

    class Service:
        def __init__(self):
            self.store = types.SimpleNamespace(store=live)

        def handle(self, *args):
            return {"status": 200, "headers": {}, "body": {"ok": True, "data": {}}}

    def seed_r09(store, records, now):
        seen.append((store, records, now))
        return {"inserted": 743, "skipped": 0, "reset": 2}

    modules = {"ui.civic_feedback.v2.integration": types.SimpleNamespace(make_service=lambda db: Service()),
               "ml.datasets.demo_world_seed": types.SimpleNamespace(seed_r09=seed_r09)}
    gateway = CivicV2Gateway(modules=modules, db_path=tmp_path / "c.sqlite3", demo=True, demo_world=True)
    report = gateway.seed_world(now=NOW, world=WORLD)
    assert seen == [(live, WORLD, NOW)]
    assert report["roles"]["R09"] == {"inserted": 743, "skipped": 0}
    assert CivicV2Gateway.world_line(report) == "civic-world: R09 743"
