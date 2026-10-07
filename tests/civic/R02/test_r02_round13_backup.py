"""R02 раунд 13: полная служебная копия отдельно от публичной выгрузки; справочник /staff/meta.

Все базы временные (tmp_path).
"""

import hashlib
import json
from pathlib import Path
import re

import pytest

from ui.civic_store import cli
from ui.civic_store.importer import import_package
from ui.civic_store.public_export import export_public
from ui.civic_store.service import CivicService, meta
from r02_helpers import ManualClock, call
from test_r02_import_cli import package, real_item


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def world(service, editor):
    import_package(service.objects, package([real_item("ast-r13-b")]))
    item = editor.get("/staff/objects/ast-r13-b")["body"]["data"]["item"]
    item = editor.publish(item, reason="Публикация")["body"]["data"]["item"]
    editor.update(item, {"title": "Черновая правка"}, reason="Служебная причина")
    import_package(service.objects, package([real_item("ast-r13-b", title="Источник v2")], version="v2"))
    editor.create(title="Черновик для копии", internal_notes="служебная заметка")


def test_full_backup_verify_and_restore_keep_staff_trail(service, editor, tmp_path, capsys):
    world(service, editor)
    live = service.db.path
    service.db.checkpoint()
    live_hash = file_hash(live)
    backup = tmp_path / "backups" / "full.sqlite3"
    assert cli.main(["--db", str(live), "backup", str(backup)]) == 0
    capsys.readouterr()
    assert cli.main(["verify-backup", str(backup)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["integrity"] == "ok" and report["needs_migration"] == []
    assert report["objects"] == {"draft": 1, "published": 1} and report["editors"] == 2
    assert file_hash(live) == live_hash  # verify ничего не пишет в рабочую базу
    # Восстановление в НОВОЕ место: служебная история, заметки и кандидаты на месте.
    target = tmp_path / "restored" / "civic.sqlite3"
    assert cli.main(["--db", str(target), "restore", str(backup), "--yes"]) == 0
    restored = CivicService(target, clock=ManualClock(), auto_migrate=False)
    original = service.objects.get_staff("ast-r13-b")
    copy = restored.objects.get_staff("ast-r13-b")
    assert copy["history"] == original["history"]
    assert restored.objects.list_candidates("ast-r13-b")["pending"] == 1
    # Публичная выгрузка того же состояния не содержит ни черновика, ни служебных записей.
    public = json.dumps(export_public(service.objects), ensure_ascii=False)
    for private in ("Черновик для копии", "служебная заметка", "Служебная причина", "Черновая правка",
                    "editor1", "Источник v2"):
        assert private not in public


def test_verify_backup_refuses_foreign_or_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["verify-backup", str(tmp_path / "missing.sqlite3")])
    foreign = tmp_path / "foreign.sqlite3"
    import sqlite3
    conn = sqlite3.connect(foreign)
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    with pytest.raises(SystemExit):
        cli.main(["verify-backup", str(foreign)])


def test_staff_meta_is_editor_only_and_lists_every_error_code(service, editor):
    assert call(service, "GET", "/staff/meta")["status"] == 401
    data = editor.get("/staff/meta")["body"]["data"]
    assert data == json.loads(json.dumps(meta()))
    assert data["meta_version"] == 2
    assert data["locked_after_first_publication"] == ["schedule.original_planned_end"]
    used = {}
    for path in Path(cli.__file__).parent.glob("*.py"):
        for status, code in re.findall(r'error\((\d{3}), "([a-z_]+)"', path.read_text(encoding="utf-8")):
            used[code] = int(status)
    conflict_codes = {"stale_revision": 409, "candidate_superseded": 409, "candidate_resolved": 409}  # Conflict.code
    assert {**used, **conflict_codes} == data["errors"]
