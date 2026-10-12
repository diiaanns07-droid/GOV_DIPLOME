"""R09 раунд 14 (ночь): демо-жалобы для «Я тоже» на шаге 2 демо (R10 B-030)."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, record as rec
from ui.civic_feedback.v2.demo_seed import KHAN_SHATYR, seed_demo
from ui.civic_feedback.v2.integration import make_service

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=rec.ASTANA_TZ)
KHAN_SHATYR_POINT_NEAR = [71.40660, 51.13112]
ROOT = Path(__file__).resolve().parents[3]


def test_seed_is_synthetic_marked_and_idempotent(tmp_path):
    store = ComplaintStore(tmp_path / "d.sqlite3", clock=lambda: NOW)
    assert seed_demo(store) == {"added": 2, "reset": 0, "kept": 0, "target": KHAN_SHATYR["id"]}
    assert seed_demo(store) == {"added": 0, "reset": 2, "kept": 0, "target": KHAN_SHATYR["id"]}
    assert seed_demo(store, reset=False) == {"added": 0, "reset": 0, "kept": 2, "target": KHAN_SHATYR["id"]}
    items = store.list()
    assert len(items) == 2 and all(i["demo"] is True for i in items)
    assert {i["target"]["id"] for i in items} == {KHAN_SHATYR["id"]}
    light = next(i for i in items if i["category"] == "lighting")
    assert rec.reporters(light) == 3 and light["code"].startswith("B-")
    store.close()


def test_resident_metoo_on_seeded_complaint_counts_once(tmp_path):
    api = make_service(tmp_path / "m.sqlite3", target_lookup=None, demo_seed=True)
    light = next(i for i in api.store.list() if i["category"] == "lighting")
    ctx = {"headers": {"X-Birge-Device": "dev-resident-000000001"}, "host_allowed": True, "is_same_origin": True}
    reply = api.handle("POST", f"/api/civic/v2/complaints/{light['id']}/metoo", None, b"{}", None, ctx)
    body = reply["body"]["data"]
    assert body["result"] == "added" and body["complaint"]["reporters"] == 4
    again = api.handle("POST", f"/api/civic/v2/complaints/{light['id']}/metoo", None, b"{}", None, ctx)
    assert again["body"]["data"]["result"] == "already"
    # Другим жителям — без текста и без точной точки (как у настоящих жалоб).
    public = api.handle("GET", "/api/civic/v2/complaints", "bbox=71.3,51.0,71.5,51.2", None, None, ctx)
    item = public["body"]["data"]["items"][0]
    assert "text" not in item and item["demo"] is True
    api.store.close()


def test_cli_seed_demo(tmp_path):
    db = tmp_path / "c.sqlite3"
    out = subprocess.run([sys.executable, "-m", "ui.civic_feedback.v2", "seed-demo", "--db", str(db)],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["added"] == 2
    out = subprocess.run([sys.executable, "-m", "ui.civic_feedback.v2", "seed-demo", "--db", str(db)],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["reset"] == 2 and json.loads(out.stdout)["added"] == 0


def test_demo_resets_after_rehearsal_and_weeks_later(tmp_path):
    """R10 B-048 (репетиция «съедала» шаг 2) и B-049 (через 14 дней «Я тоже» пропадал): каждый запуск демо-сборки
    возвращает демо-записи в исходное состояние со временем от запуска; настоящие жалобы не трогаются."""
    from datetime import timedelta
    clock = {"now": NOW}
    store = ComplaintStore(tmp_path / "r.sqlite3", clock=lambda: clock["now"])
    seed_demo(store)
    light = next(i for i in store.list() if i["category"] == "lighting")
    code = light["code"]
    # Репетиция: житель «Я тоже», акимат «исправлено» с фото нет, житель проверил; рядом — настоящая жалоба.
    store.metoo(light["id"], "dev-rehearsal-0000000001")
    store.set_status(light["id"], "in_progress")
    store.set_status(light["id"], "fixed", what_done="Заменили лампу")
    store.verify(light["id"], "dev-rehearsal-0000000001", "yes")
    real, _ = store.create({"text": "Настоящая жалоба жителя у остановки", "category": "lighting",
                            "point": KHAN_SHATYR_POINT_NEAR, "target": dict(KHAN_SHATYR)}, "dev-real-resident-000001")
    # Показ через 20 дней после первой настройки.
    clock["now"] = NOW + timedelta(days=20)
    assert seed_demo(store) == {"added": 0, "reset": 2, "kept": 0, "target": KHAN_SHATYR["id"]}
    again = store.get(light["id"])
    assert again["status"] == "new" and again.get("resolution") is None and again["code"] == code
    assert rec.reporters(again) == 3                                     # исходные «Я тоже», без репетиции
    assert clock["now"] - rec.parse_iso(again["created_at"]) == timedelta(hours=30)
    assert store.participant(light["id"], "dev-rehearsal-0000000001") is None
    assert store.get(real["id"])["text"].startswith("Настоящая")          # настоящая жалоба на месте
    recent = store.list(since=clock["now"] - timedelta(days=14), category="lighting")
    assert light["id"] in {r["id"] for r in recent}                      # «Я тоже» на шаге 2 снова находится
    store.close()


def test_demo_reset_never_touches_a_real_record(tmp_path):
    from ui.civic_feedback.v2.demo_seed import demo_records
    store = ComplaintStore(tmp_path / "x.sqlite3", clock=lambda: NOW)
    record, metoo = demo_records(NOW)[0]
    real = dict(record, demo=False, text="настоящая")
    store.import_record(real)
    assert store.reset_demo_record(record, metoo_devices=metoo) == "skipped"
    assert store.get(record["id"])["text"] == "настоящая"
    store.close()
