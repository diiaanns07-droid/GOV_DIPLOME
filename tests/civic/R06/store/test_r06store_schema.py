"""R02: схема SQLite, миграции и политика расположения файла базы."""

import sqlite3

import pytest

from ui.civic_store import db as civic_db
from ui.civic_store.db import Database, SCHEMA_VERSION, StorageError


EXPECTED_TABLES = {
    "civic_schema_migrations", "civic_users", "civic_sessions", "civic_login_failures",
    "civic_objects", "civic_public_objects", "civic_history", "civic_imports",
    "civic_import_candidates", "civic_create_requests",
    # R06 раунд 14, миграция 6: этапы, предложения, голоса.
    "civic_object_stages", "civic_stage_history", "civic_proposals", "civic_proposal_history",
    "civic_votes", "civic_v2_settings",
}


def tables(path):
    with sqlite3.connect(path) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                if not row[0].startswith("sqlite_")}


def test_empty_database_in_tmp_dir_reads_as_empty(tmp_path):
    database = Database(tmp_path / "civic.sqlite3")
    assert database.migrate() == list(range(1, SCHEMA_VERSION + 1))
    assert tables(database.path) == EXPECTED_TABLES
    with database.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM civic_public_objects").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM civic_history").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM civic_users").fetchone()[0] == 0
        # Отсутствующая запись — отсутствие, а не пустой объект.
        assert conn.execute("SELECT * FROM civic_objects WHERE id = ?", ("missing",)).fetchone() is None
    database.require_current_schema()
    assert database.open_connections == 0


def test_migrate_is_idempotent_and_survives_restart(tmp_path):
    path = tmp_path / "civic.sqlite3"
    assert Database(path).migrate() == list(range(1, SCHEMA_VERSION + 1))
    again = Database(path)
    assert again.migrate() == []
    assert set(again.applied_migrations()) == set(range(1, SCHEMA_VERSION + 1))
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        # Общий на файл user_version не используется: его может трогать другой модуль.
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0


def test_uninitialised_database_is_reported(tmp_path):
    with pytest.raises(StorageError, match="init"):
        Database(tmp_path / "nothing.sqlite3").require_current_schema()


def test_newer_or_modified_schema_is_refused(tmp_path):
    path = tmp_path / "civic.sqlite3"
    Database(path).migrate()
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO civic_schema_migrations VALUES (99, 'future', 'x', 'now')")
    with pytest.raises(StorageError, match="более новой"):
        Database(path).migrate()

    other = tmp_path / "other.sqlite3"
    Database(other).migrate()
    with sqlite3.connect(other) as conn:
        conn.execute("UPDATE civic_schema_migrations SET checksum = 'tampered'")
    with pytest.raises(StorageError, match="отличается"):
        Database(other).migrate()


def test_history_is_append_only_and_objects_are_not_deleted(tmp_path):
    database = Database(tmp_path / "civic.sqlite3")
    database.migrate()
    with database.write() as conn:
        conn.execute("""INSERT INTO civic_objects(id, city, kind, status, publication, data_json,
                        revision, created_at, updated_at)
                        VALUES ('o1', 'astana', 'event', 'unknown', 'draft', '{}', 1, 't', 't')""")
        conn.execute("""INSERT INTO civic_history(object_id, revision, at, action, publication,
                        changed_fields_json, diff_json, actor_kind, actor_label, public_actor_label,
                        snapshot_json) VALUES ('o1', 1, 't', 'create', 'draft', '[]', '{}', 'system',
                        'test', 'test', '{}')""")
    for statement in ("UPDATE civic_history SET reason = 'x'", "DELETE FROM civic_history",
                      "DELETE FROM civic_objects"):
        with pytest.raises(sqlite3.IntegrityError):
            with database.write() as conn:
                conn.execute(statement)
    with database.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_history").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 1


def test_check_constraints_reject_out_of_contract_values(tmp_path):
    database = Database(tmp_path / "civic.sqlite3")
    database.migrate()
    with pytest.raises(sqlite3.IntegrityError):
        with database.write() as conn:
            conn.execute("""INSERT INTO civic_objects(id, city, kind, status, publication, data_json,
                            revision, created_at, updated_at)
                            VALUES ('o2', 'shymkent', 'event', 'unknown', 'draft', '{}', 1, 't', 't')""")
    with pytest.raises(sqlite3.IntegrityError):
        with database.write() as conn:
            conn.execute("""INSERT INTO civic_objects(id, city, kind, status, publication, data_json,
                            revision, created_at, updated_at)
                            VALUES ('', 'astana', 'event', 'unknown', 'draft', '{}', 1, 't', 't')""")


def test_failed_write_rolls_back_everything(tmp_path):
    database = Database(tmp_path / "civic.sqlite3")
    database.migrate()
    with pytest.raises(RuntimeError):
        with database.write() as conn:
            conn.execute("""INSERT INTO civic_objects(id, city, kind, status, publication, data_json,
                            revision, created_at, updated_at)
                            VALUES ('o3', 'astana', 'event', 'unknown', 'draft', '{}', 1, 't', 't')""")
            raise RuntimeError("boom")
    with database.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 0
    assert database.open_connections == 0


@pytest.mark.parametrize("bad", [None, "", ":memory:", "file:x?mode=memory"])
def test_non_file_databases_are_refused(bad):
    with pytest.raises(StorageError):
        Database(bad)


def test_database_inside_repository_or_web_is_refused():
    root = civic_db.REPO_ROOT
    for path in (root / "web" / "civic.sqlite3", root / "data" / "civic.sqlite3",
                 root / "civic.sqlite3", root / "ui" / "civic_store" / "x.sqlite3",
                 root / ".runtime" / ".." / "web" / "civic.sqlite3"):
        with pytest.raises(StorageError):
            Database(path)
    with pytest.raises(StorageError):
        Database(root / ".runtime")


def test_runtime_dir_is_git_ignored_by_itself(tmp_path, monkeypatch):
    # Изолированная копия политики: «репозиторий» во временной папке.
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    monkeypatch.setattr(civic_db, "REPO_ROOT", fake_root)
    monkeypatch.setattr(civic_db, "RUNTIME_DIR", fake_root / ".runtime")
    database = Database(fake_root / ".runtime" / "civic.sqlite3")
    database.migrate()
    marker = fake_root / ".runtime" / ".gitignore"
    assert marker.read_text(encoding="utf-8").splitlines()[-1] == "*"
    assert database.path.is_file()


@pytest.mark.skipif(__import__("os").name != "posix", reason="права POSIX")
def test_database_file_is_private(tmp_path):
    import stat
    from ui.civic_store import cli
    database = Database(tmp_path / "private.sqlite3")
    database.migrate()
    assert stat.S_IMODE(database.path.stat().st_mode) == 0o600
    copy = tmp_path / "backup with space.sqlite3"
    cli._backup(database.path, copy)
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600


def test_nested_write_in_same_thread_is_refused_and_queue_timeout_is_busy(tmp_path):
    import threading
    database = Database(tmp_path / "queue.sqlite3")
    database.migrate()
    with database.write():
        with pytest.raises(RuntimeError, match="Вложенная"):
            with database.write():
                pass
    database.write_queue_timeout = 0.2
    held = threading.Event()
    release = threading.Event()

    def holder():
        with database.write():
            held.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(5)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        with database.write():
            pass
    release.set()
    thread.join(5)
    with database.write() as conn:  # после освобождения очередь снова свободна
        conn.execute("SELECT 1")
    assert database.open_connections == 0
