"""R02: таблицы другого модуля (R06 feedback_*) в том же файле не затрагиваются."""

import sqlite3

from ui.civic_store import cli
from ui.civic_store.db import Database
from ui.civic_store.service import CivicService
from r06store_helpers import Editor, PASSWORD


def make_foreign_tables(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE feedback_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT)")
        conn.execute("CREATE TABLE feedback_items (id TEXT PRIMARY KEY, object_id TEXT, text TEXT)")
        conn.execute("INSERT INTO feedback_schema_migrations VALUES (1, 'x')")
        conn.execute("INSERT INTO feedback_items VALUES ('fb-1', 'demo', 'приватный текст жителя')")
        conn.execute("PRAGMA user_version = 0")


def snapshot(path):
    with sqlite3.connect(path) as conn:
        return (conn.execute("SELECT * FROM feedback_items").fetchall(),
                conn.execute("SELECT * FROM feedback_schema_migrations").fetchall(),
                conn.execute("SELECT sql FROM sqlite_master WHERE name LIKE 'feedback_%' ORDER BY name").fetchall())


def test_r06store_never_touches_feedback_tables(tmp_path, clock):
    path = tmp_path / "shared.sqlite3"
    make_foreign_tables(path)
    before = snapshot(path)
    service = CivicService(path, clock=clock)  # init/миграции R02 поверх чужих таблиц
    service.accounts.create_user("editor1", PASSWORD)
    editor = Editor(service, "editor1", PASSWORD)
    item = editor.create()
    editor.publish(item)
    Database(path).migrate()  # повторная миграция
    assert snapshot(path) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        civic = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {name for name in civic if not name.startswith(("civic_", "feedback_", "sqlite_"))} == set()

    backup = tmp_path / "copy.sqlite3"
    args = cli.build_parser().parse_args(["--db", str(path), "backup", str(backup)])
    args.func(args, service)
    assert snapshot(backup) == before  # копия включает таблицы R06 целиком

    # R06 добавляет свою миграцию позже — R02 её не замечает и не мешает.
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE feedback_items ADD COLUMN moderation TEXT DEFAULT 'pending'")
        conn.execute("INSERT INTO feedback_schema_migrations VALUES (2, 'y')")
    again = CivicService(path, clock=clock)
    assert again.objects.get_public(item["id"])["item"]["id"] == item["id"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT moderation FROM feedback_items").fetchone()[0] == "pending"
