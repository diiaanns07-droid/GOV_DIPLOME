"""R09 раунд 14: миграция v1 (feedback_messages раундов 11–13) -> v2 без потерь."""

import json
import sqlite3

import pytest

from ui.civic_feedback.service import SCHEMA_SQL
from ui.civic_feedback.v2 import ComplaintStore, migrate_v1
from ui.civic_feedback.v2 import migrate as mig

BASE = {"city": "astana", "kind": "problem", "text_fingerprint": "f", "consent_public": 1,
        "moderation": "pending", "revision": 1, "created_ts": 0.0, "client_hash": "h",
        "classifier_status": "not_run", "handling_status": "new"}


def make_v1(path, rows, events=()):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA_SQL)
    for row in rows:
        data = {**BASE, "updated_at": row["created_at"], **row}
        cols = ",".join(data)
        db.execute(f"INSERT INTO feedback_messages ({cols}) VALUES ({','.join('?' * len(data))})", list(data.values()))
    for event in events:
        cols = ",".join(event)
        db.execute(f"INSERT INTO feedback_events ({cols}) VALUES ({','.join('?' * len(event))})", list(event.values()))
    db.commit()
    db.close()


ROWS = [
    {"id": 1, "public_id": "fbp_aaa", "receipt_id": "fbr_aaaaaaaaaaaaaaaaaa", "object_id": "demo-r02-stop",
     "lon": 71.41, "lat": 51.09, "category": "transport_stops", "text": "Павильон остановки сломан",
     "language": "ru", "created_at": "2026-10-01T05:00:00+00:00", "moderation": "approved",
     "handling_status": "answered", "public_reply": "Передано", "staff_category": None,
     "classifier_json": json.dumps({"label": "transport_stops", "score": 0.8, "model_version": "r08"}),
     "object_snapshot": json.dumps({"title": "Остановка «Нура»", "revision": 3})},
    {"id": 2, "public_id": "fbp_bbb", "receipt_id": "fbr_bbbbbbbbbbbbbbbbbb", "object_id": None,
     "lon": 71.42, "lat": 51.10, "category": "landscaping", "text": "Аулада алаң сынған",
     "language": "kk", "created_at": "2026-10-02T05:00:00+00:00", "handling_status": "closed",
     "staff_category": "lighting"},
    {"id": 3, "public_id": "fbp_ccc", "receipt_id": "fbr_cccccccccccccccccc", "object_id": "demo-r02-stop",
     "lon": 71.41, "lat": 51.09, "category": "transport_stops", "text": "Остановка без крыши",
     "language": "ru", "created_at": "2026-10-03T05:00:00+00:00", "handling_status": "duplicate",
     "duplicate_of": 1},
    {"id": 4, "public_id": "fbp_ddd", "receipt_id": "fbr_dddddddddddddddddd", "object_id": None,
     "lon": None, "lat": None, "category": "other", "text": "Без места", "language": "ru",
     "created_at": "2026-10-04T05:00:00+00:00", "moderation": "rejected"},
    {"id": 5, "public_id": "fbp_eee", "receipt_id": "fbr_eeeeeeeeeeeeeeeeee", "object_id": "demo-r02-park",
     "lon": None, "lat": None, "category": "landscaping", "text": "Нет скамеек", "language": "ru",
     "created_at": "2026-10-05T05:00:00+00:00", "moderation": "rejected",
     "object_snapshot": json.dumps({"title": "Сквер", "geometry": {"type": "Polygon", "coordinates":
                                    [[[71.43, 51.11], [71.44, 51.11], [71.44, 51.12], [71.43, 51.11]]]}})},
]
EVENTS = [
    {"feedback_id": 1, "revision": 1, "at": "2026-10-01T05:00:00+00:00", "action": "submitted",
     "actor_kind": "resident", "changed_fields": "[]", "handling_after": "new", "moderation_after": "pending"},
    {"feedback_id": 1, "revision": 2, "at": "2026-10-01T07:00:00+00:00", "action": "status",
     "actor_kind": "staff", "actor": "7", "changed_fields": "[]", "handling_after": "in_review",
     "moderation_after": "approved"},
    {"feedback_id": 1, "revision": 3, "at": "2026-10-02T07:00:00+00:00", "action": "status",
     "actor_kind": "staff", "actor": "7", "changed_fields": "[]", "handling_after": "answered",
     "moderation_after": "approved"},
]


@pytest.fixture
def migrated(tmp_path):
    v1 = tmp_path / "v1.sqlite3"
    make_v1(v1, ROWS, EVENTS)
    store = ComplaintStore(tmp_path / "v2.sqlite3")
    report = migrate_v1(v1, store)
    yield v1, store, report
    store.close()


def test_report_counts(migrated):
    _, _, report = migrated
    assert report["total"] == 5 and report["migrated"] == 4 and report["already"] == 0
    assert report["skipped_no_location"] == ["fbp_ddd"]  # нет ни точки, ни геометрии — не выдумываем
    assert report["duplicates"] == 1


def test_record_fields_and_category_mapping(migrated):
    _, store, _ = migrated
    first = store.get(mig.v2_id("fbp_aaa"))
    assert first["category"] == "transport" and first["category_source"] == "resident"
    assert first["target"] == {"kind": "object", "id": "demo-r02-stop", "label_ru": "Остановка «Нура»",
                               "legacy": True}
    assert first["created_at"] == "2026-10-01T10:00:00+05:00"
    assert first["model"]["label"] == "transport" and first["model"]["score"] is None
    assert [h["status"] for h in first["status_history"]] == ["new", "accepted"]
    assert first["status"] == "accepted" and first["demo"] is True and first["code"].startswith("B-")
    second = store.get(mig.v2_id("fbp_bbb"))
    assert second["category"] == "lighting" and second["category_source"] == "staff"  # решение сотрудника
    assert second["target"]["kind"] == "area" and second["target"]["approximate"] is True
    assert second["lang"] == "kk" and "needs_review" in second["legacy"]


def test_nothing_lost(migrated):
    v1, store, _ = migrated
    db = sqlite3.connect(v1)
    db.row_factory = sqlite3.Row
    for row in db.execute("SELECT * FROM feedback_messages WHERE public_id != 'fbp_ddd'"):
        record = store.get(mig.v2_id(row["public_id"]))
        assert record["legacy"]["v1_columns"] == dict(row)  # каждая колонка v1 сохранена
        assert record["text"] == row["text"]
    assert len(store.get(mig.v2_id("fbp_aaa"))["legacy"]["v1_events"]) == 3
    # v1 не тронута
    assert db.execute("SELECT COUNT(*) FROM feedback_messages").fetchone()[0] == 5


def test_duplicate_and_geometry_fallback(migrated):
    _, store, _ = migrated
    dup = store.get(mig.v2_id("fbp_ccc"))
    assert dup["duplicate_of"] == mig.v2_id("fbp_aaa")
    park = store.get(mig.v2_id("fbp_eee"))
    assert park["point"] == [71.43, 51.11] and park["status"] == "rejected"


def test_idempotent(migrated):
    v1, store, _ = migrated
    again = migrate_v1(v1, store)
    assert again["migrated"] == 0 and again["already"] == 4 and again["duplicates"] == 0
    assert len(store.list(include_duplicates=True)) == 4


def test_round11_schema_without_new_columns(tmp_path):
    """Самая старая БД v1 (без handling_status и снимков) тоже переносится."""
    v1 = tmp_path / "old.sqlite3"
    db = sqlite3.connect(v1)
    db.execute("CREATE TABLE feedback_messages (id INTEGER PRIMARY KEY, public_id TEXT, object_id TEXT, "
               "lon REAL, lat REAL, category TEXT, text TEXT, language TEXT, moderation TEXT, created_at TEXT)")
    db.execute("INSERT INTO feedback_messages VALUES (1,'fbp_old',NULL,71.4,51.1,'roads','Яма','ru','approved',"
               "'2026-09-01T10:00:00+05:00')")
    db.commit()
    db.close()
    store = ComplaintStore(tmp_path / "v2.sqlite3")
    report = migrate_v1(v1, store)
    assert report["migrated"] == 1
    assert store.get(mig.v2_id("fbp_old"))["status"] == "new"


def test_empty_or_missing_db(tmp_path):
    store = ComplaintStore(tmp_path / "v2.sqlite3")
    empty = tmp_path / "empty.sqlite3"
    sqlite3.connect(empty).close()
    assert migrate_v1(empty, store)["total"] == 0
    with pytest.raises(FileNotFoundError):
        migrate_v1(tmp_path / "nope.sqlite3", store)
