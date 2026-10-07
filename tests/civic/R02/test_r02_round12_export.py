"""R02 раунд 12: публичная выгрузка/восстановление без секретов и миграция существующей схемы.

Все базы — временные (tmp_path); пользовательская runtime-база не открывается.
"""

import copy
import json
import sqlite3
import subprocess
import sys

import pytest

from ui.civic_store import cli
from ui.civic_store.db import MIGRATIONS, REPO_ROOT, Database
from ui.civic_store.importer import import_package
from ui.civic_store.public_export import (PublicRestoreRejected, _digest, export_public,
                                          restore_public)
from ui.civic_store.service import CivicService
from r02_helpers import PASSWORD, ManualClock, call
from test_r02_import_cli import package, real_item
from test_r02_round12_public import SECRET_MARKERS, build_world


def all_rows(path):
    conn = sqlite3.connect(path)
    try:
        return {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
                for t in ("civic_objects", "civic_history", "civic_public_objects", "civic_imports")}
    finally:
        conn.close()


def public_view(service):
    items = call(service, "GET", "/objects", query={"limit": ["100"]})["body"]["data"]["items"]
    return {item["id"]: call(service, "GET", f"/objects/{item['id']}")["body"]["data"] for item in items}


def test_export_contains_only_public_data(service, editor):
    pub = build_world(service, editor)
    # Перенос срока с причиной — должен пережить выгрузку.
    current = editor.get(f"/staff/objects/{pub['id']}")["body"]["data"]["item"]
    current = editor.update(current, {"schedule": {"current_planned_end": "2026-11-05"}},
                            reason="Перенос по письму подрядчика")["body"]["data"]["item"]
    editor.publish(current, reason="Срок перенесён на 5 ноября")
    export = export_public(service.objects)
    text = json.dumps(export, ensure_ascii=False)
    # Вторая публикация законно выпустила и ожидавшую правку описания (MARK-UNPUBLISHED).
    private = [m for m in SECRET_MARKERS if m != "MARK-UNPUBLISHED"]
    for marker in private + ["password", "session", "csrf", "internal_notes", "snapshot"]:
        assert marker not in text, marker
    # Ручная запись — синтетический образец, импорт — тестовая observed: тип не теряется.
    assert export["counts"] == {"objects": 2, "synthetic": 1}
    ids = [o["item"]["id"] for o in export["objects"]]
    assert ids == sorted(public_view(service))
    moved = next(o for o in export["objects"] if o["item"]["id"] == pub["id"])
    assert moved["item"]["schedule"]["original_planned_end"] == "2026-10-20"
    assert moved["item"]["schedule"]["current_planned_end"] == "2026-11-05"
    assert moved["history"][-1]["reason"] == "Срок перенесён на 5 ноября"


def test_restore_round_trip_into_new_database(service, editor, tmp_path):
    build_world(service, editor)
    export = export_public(service.objects)
    target = CivicService(tmp_path / "restored.sqlite3", clock=ManualClock())
    dry = restore_public(target.objects, copy.deepcopy(export), dry_run=True)
    assert dry["status"] == "dry_run" and dry["objects"] == 2
    assert all(rows == [] for rows in all_rows(target.db.path).values())
    report = restore_public(target.objects, copy.deepcopy(export))
    assert report["status"] == "applied"
    # Публичный API восстановленной базы отдаёт то же самое.
    assert public_view(target) == public_view(service)
    again = export_public(target.objects)
    assert again["objects"] == export["objects"] and again["objects_digest"] == export["objects_digest"]
    # Ни пользователей, ни сессий, ни черновиков в новой базе.
    conn = sqlite3.connect(target.db.path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM civic_users").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM civic_sessions").fetchone()[0] == 0
        assert {r[0] for r in conn.execute("SELECT publication FROM civic_objects")} == {"published"}
    finally:
        conn.close()
    # Повтор в непустую базу отклоняется целиком, база не меняется.
    before = all_rows(target.db.path)
    with pytest.raises(PublicRestoreRejected, match="пуст"):
        restore_public(target.objects, copy.deepcopy(export))
    assert all_rows(target.db.path) == before


def test_restored_object_continues_with_locked_original_and_history(service, editor, tmp_path):
    import_package(service.objects, package([real_item("ast-r12-e")]))
    item = editor.get("/staff/objects/ast-r12-e")["body"]["data"]["item"]
    editor.publish(item, reason="Первая публикация")
    target = CivicService(tmp_path / "restored.sqlite3", clock=ManualClock())
    restore_public(target.objects, export_public(service.objects))
    target.accounts.create_user("editor1", PASSWORD, display_name="Новый редактор")
    from r02_helpers import Editor
    new_editor = Editor(target, "editor1", PASSWORD)
    staff = new_editor.get("/staff/objects/ast-r12-e")["body"]["data"]["item"]
    assert staff["staff"]["original_planned_end_locked"] is True
    assert "Восстановлено из публичной выгрузки" in staff["internal_notes"]
    bad = new_editor.update(staff, {"schedule": {"original_planned_end": "2026-12-31"}}, reason="Попытка")
    assert bad["status"] == 422
    staff = new_editor.update(staff, {"schedule": {"current_planned_end": "2026-12-01"}},
                              reason="Перенос после восстановления")["body"]["data"]["item"]
    new_editor.publish(staff, reason="Срок перенесён")
    history = call(target, "GET", "/objects/ast-r12-e")["body"]["data"]["history"]
    assert [h["reason"] for h in history] == ["Первая публикация", "Срок перенесён"]
    # Новый импорт того же source не создаёт дубль и не трогает опубликованную карточку.
    report = import_package(target.objects, package([real_item("ast-r12-e")]))
    assert report["items"][0]["action"] == "id_conflict"


@pytest.mark.parametrize("tamper,message", [
    (lambda e: e["objects"][0]["item"].__setitem__("title", "Подмена"), "objects_digest"),
    (lambda e: e.__setitem__("format", "other"), "Это не выгрузка"),
])
def test_tampered_export_is_rejected(service, editor, tmp_path, tamper, message):
    build_world(service, editor)
    export = export_public(service.objects)
    tamper(export)
    target = CivicService(tmp_path / "restored.sqlite3", clock=ManualClock())
    with pytest.raises(PublicRestoreRejected, match=message):
        restore_public(target.objects, export)


def test_export_with_private_fields_is_rejected_with_paths(service, editor, tmp_path):
    build_world(service, editor)
    export = export_public(service.objects)
    export["objects"][0]["item"]["internal_notes"] = "чужая заметка"
    export["objects"][1]["item"]["publication"] = "draft"
    export["objects"][1]["history"][0]["revision"] = 999
    export["objects_digest"] = _digest(export["objects"])  # «аккуратно» пересчитанный отпечаток
    target = CivicService(tmp_path / "restored.sqlite3", clock=ManualClock())
    with pytest.raises(PublicRestoreRejected) as rejected:
        restore_public(target.objects, export)
    fields = rejected.value.report["fields"]
    assert "objects[0].item" in fields and "objects[1].item.publication" in fields
    assert all(rows == [] for rows in all_rows(target.db.path).values())


def test_cli_export_and_restore_public(service, editor, tmp_path):
    build_world(service, editor)
    out = tmp_path / "public.json"
    assert cli.main(["--db", str(service.db.path), "export-public", "--out", str(out)]) == 0
    with pytest.raises(SystemExit):  # существующий файл не перезаписывается
        cli.main(["--db", str(service.db.path), "export-public", "--out", str(out)])
    new_db = tmp_path / "new.sqlite3"
    assert cli.main(["--db", str(new_db), "init"]) == 0
    assert cli.main(["--db", str(new_db), "restore-public", str(out), "--dry-run"]) == 0
    assert cli.main(["--db", str(new_db), "restore-public", str(out)]) == 0
    assert cli.main(["--db", str(new_db), "restore-public", str(out)]) == 2  # не пустая база
    restored = CivicService(new_db, auto_migrate=False)
    assert public_view(restored) == public_view(service)


def test_existing_older_schema_with_data_migrates_without_loss(tmp_path, monkeypatch):
    """База кода с миграциями 1–3 (до решения по кандидатам) с данными обновляется до текущей."""
    import ui.civic_store.db as dbmod
    path = tmp_path / "old.sqlite3"
    monkeypatch.setattr(dbmod, "MIGRATIONS", MIGRATIONS[:3])
    assert Database(path).migrate() == [1, 2, 3]
    monkeypatch.undo()
    conn = sqlite3.connect(path)
    content = json.dumps({"kind": "roadworks"})
    conn.executescript(f"""
        INSERT INTO civic_objects(id, city, kind, status, publication, data_json, revision, created_at,
            updated_at, import_source, import_external_id, import_digest, import_revision)
        VALUES ('ast-old', 'astana', 'roadworks', 'planned', 'draft', '{content}', 1,
            '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00', 'r05-astana-real', 'ast-old', 'd1', 1);
        INSERT INTO civic_history(object_id, revision, at, action, publication, changed_fields_json, diff_json,
            actor_kind, actor_label, public_actor_label, snapshot_json)
        VALUES ('ast-old', 1, '2026-09-01T00:00:00+00:00', 'import_create', 'draft', '[]', '{{}}',
            'import', 'import:test', 'Импорт данных', '{{}}');
        INSERT INTO civic_imports(source, package_digest, at, actor_label, report_json)
        VALUES ('r05-astana-real', 'p1', '2026-09-01T00:00:00+00:00', 'cli', '{{}}');
        INSERT INTO civic_import_candidates(import_id, object_id, source, external_id, digest, data_json, created_at)
        VALUES (1, 'ast-old', 'r05-astana-real', 'ast-old', 'd2', '{content}', '2026-09-02T00:00:00+00:00');
    """)
    conn.commit()
    conn.close()
    before = all_rows(path)
    with pytest.raises(Exception, match="миграц"):
        CivicService(path, auto_migrate=False)  # старая схема не используется молча
    assert Database(path).migrate() == [4]
    after = all_rows(path)
    assert after == before  # данные и история не потеряны и не переписаны
    service = CivicService(path, auto_migrate=False)
    candidates = service.objects.list_candidates("ast-old")["items"]
    assert len(candidates) == 1 and candidates[0]["resolution"] is None
    assert Database(path).migrate() == []
    conn = sqlite3.connect(path)
    try:
        assert [r[0] for r in conn.execute("SELECT version FROM civic_schema_migrations ORDER BY 1")] == [1, 2, 3, 4]
    finally:
        conn.close()


def test_runtime_database_is_not_touched_by_round12_tests():
    runtime = REPO_ROOT / ".runtime"
    before = sorted(p.name for p in runtime.glob("*.sqlite3*")) if runtime.exists() else []
    subprocess.run([sys.executable, "-c", "import ui.civic_store.public_export"], cwd=REPO_ROOT, check=True)
    after = sorted(p.name for p in runtime.glob("*.sqlite3*")) if runtime.exists() else []
    assert before == after
