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
ROOT = Path(__file__).resolve().parents[3]


def test_seed_is_synthetic_marked_and_idempotent(tmp_path):
    store = ComplaintStore(tmp_path / "d.sqlite3", clock=lambda: NOW)
    assert seed_demo(store) == {"added": 2, "kept": 0, "target": KHAN_SHATYR["id"]}
    assert seed_demo(store) == {"added": 0, "kept": 2, "target": KHAN_SHATYR["id"]}
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
    assert json.loads(out.stdout)["kept"] == 2
