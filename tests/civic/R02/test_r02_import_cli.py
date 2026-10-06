"""R02: идемпотентный импорт пакета R05, CLI, демо-набор, резервная копия и восстановление."""

import copy
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from ui.civic_store import cli
from ui.civic_store.db import REPO_ROOT
from ui.civic_store.importer import ImportRejected, import_package
from ui.civic_store.service import CivicService
from r02_helpers import Editor, PASSWORD, call, sample_object


R05_DEMO = REPO_ROOT / "data" / "civic" / "astana" / "demo_synthetic.json"


def package(items, *, demo=False, version="test-v1"):
    return {"schema_version": "civic-v1", "city": "astana",
            "slice": {"name": "test", "version": version, "demo": demo}, "items": items}


def real_item(external_id="ast-r05-test-1", **overrides):
    item = sample_object(evidence_type="observed", title="Ремонт (тестовая запись)",
                         source_refs=[{"id": "src-1", "url": "https://example.org/n/1", "publisher": "Тест",
                                       "published_on": "2026-10-01", "retrieved_at": "2026-10-05T10:00:00+05:00",
                                       "access_status": "fetched", "license": None,
                                       "fields": ["title", "schedule.planned_start"]}])
    item.update({"id": external_id, "publication": "published", "revision": 7,
                 "updated_at": "2026-10-05T00:00:00Z", "schema_version": "civic-v1", "city": "astana"})
    item.update(overrides)
    return item


def test_reimport_does_not_duplicate_or_publish(service):
    pkg = package([real_item("ast-r05-a"), real_item("ast-r05-b", title="Вторая запись")])
    first = import_package(service.objects, pkg)
    assert first["status"] == "applied" and first["counts"]["create"] == 2
    assert first["source"] == "r05-astana-real"
    second = import_package(service.objects, copy.deepcopy(pkg))
    assert second["counts"] == {"skip_unchanged": 2, "report_missing": 0}
    with service.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 2
        assert {r[0] for r in conn.execute("SELECT publication FROM civic_objects")} == {"draft"}
        assert conn.execute("SELECT COUNT(*) FROM civic_public_objects").fetchone()[0] == 0
    assert call(service, "GET", "/objects")["body"]["data"]["items"] == []
    staff = service.objects.get_staff("ast-r05-a")
    assert staff["item"]["revision"] == 1  # revision/publication из пакета не приняты
    assert staff["history"][0]["action"] == "import_create"


def test_dry_run_reports_without_writing(service):
    report = import_package(service.objects, package([real_item()]), dry_run=True)
    assert report["status"] == "dry_run" and report["counts"]["create"] == 1
    with service.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM civic_imports").fetchone()[0] == 0


def test_changed_record_updates_untouched_draft_only(service, editor):
    import_package(service.objects, package([real_item("ast-r05-a"), real_item("ast-r05-b")]))
    # Редактор правит и публикует запись b; запись a остаётся нетронутой.
    item_b = editor.get("/staff/objects/ast-r05-b")["body"]["data"]["item"]
    item_b = editor.update(item_b, {"title": "Название уточнено редактором"})["body"]["data"]["item"]
    editor.publish(item_b, reason="Проверено редактором")

    changed = package([real_item("ast-r05-a", title="Новое название из источника"),
                       real_item("ast-r05-b", title="Новое название из источника")], version="test-v2")
    report = import_package(service.objects, changed)
    actions = {item["external_id"]: item["action"] for item in report["items"]}
    assert actions == {"ast-r05-a": "update_import_draft", "ast-r05-b": "editor_review"}
    assert service.objects.get_staff("ast-r05-a")["item"]["title"] == "Новое название из источника"
    staff_b = service.objects.get_staff("ast-r05-b")["item"]
    assert staff_b["title"] == "Название уточнено редактором"  # ручная правка не затоптана
    assert staff_b["staff"]["pending_import_candidates"] == 1
    public_b = call(service, "GET", "/objects/ast-r05-b")["body"]["data"]["item"]
    assert public_b["title"] == "Название уточнено редактором"
    # Повтор того же пакета не плодит кандидатов.
    again = import_package(service.objects, changed)
    assert {i["external_id"]: i["action"] for i in again["items"]} == {
        "ast-r05-a": "skip_unchanged", "ast-r05-b": "editor_review"}
    assert service.objects.get_staff("ast-r05-b")["item"]["staff"]["pending_import_candidates"] == 1


def test_missing_records_are_reported_not_deleted(service):
    import_package(service.objects, package([real_item("ast-r05-a"), real_item("ast-r05-b")]))
    report = import_package(service.objects, package([real_item("ast-r05-a")]))
    assert [m["external_id"] for m in report["missing"]] == ["ast-r05-b"]
    assert service.objects.get_staff("ast-r05-b")["item"]["publication"] == "draft"


def test_invalid_record_rejects_whole_package_unless_partial(service):
    bad = real_item("ast-r05-bad", budget={"amount_kzt": float("nan"), "basis": "planned", "source_id": "src-1"})
    with pytest.raises(ImportRejected) as rejected:
        import_package(service.objects, package([real_item("ast-r05-ok"), bad]))
    assert rejected.value.report["status"] == "rejected"
    with service.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 0
    report = import_package(service.objects, package([real_item("ast-r05-ok"), bad]), allow_partial=True)
    assert {i["external_id"]: i["action"] for i in report["items"]} == {"ast-r05-ok": "create",
                                                                       "ast-r05-bad": "invalid"}


@pytest.mark.parametrize("pkg,message", [
    ({"schema_version": "civic-v0", "city": "astana", "items": []}, "civic-v1"),
    ({"schema_version": "civic-v1", "city": "shymkent", "items": []}, "Астан"),
    ({"schema_version": "civic-v1", "city": "astana", "items": {}}, "items"),
    ([], "--source"),
])
def test_bad_package_envelopes(service, pkg, message):
    with pytest.raises(ImportRejected, match=message):
        import_package(service.objects, pkg)


def test_demo_and_real_are_not_mixed(service):
    with pytest.raises(ImportRejected):
        import_package(service.objects, package([real_item()], demo=True))
    synthetic = real_item(evidence_type="synthetic", source_refs=[])
    with pytest.raises(ImportRejected):
        import_package(service.objects, package([synthetic], demo=False))


def test_id_taken_by_manual_object_is_conflict(service, editor):
    manual = editor.create()
    report = import_package(service.objects, package([real_item(manual["id"])]))
    assert report["items"][0]["action"] == "id_conflict"
    assert service.objects.get_staff(manual["id"])["item"]["title"] == manual["title"]


@pytest.mark.skipif(not R05_DEMO.exists(), reason="R05 demo_synthetic.json появится после интеграции R01")
def test_r05_demo_package_imports_as_drafts(service):
    report = import_package(service.objects, json.loads(R05_DEMO.read_text(encoding="utf-8")))
    assert report["status"] == "applied" and report["source"] == "r05-astana-demo"
    assert call(service, "GET", "/objects")["body"]["data"]["items"] == []


def test_seed_demo_publishes_only_synthetic_with_visible_history(service):
    report = cli.seed_demo(service, json.loads(cli.DEMO_PACKAGE.read_text(encoding="utf-8")))
    assert report["source"] == "r02-demo"
    items = call(service, "GET", "/objects")["body"]["data"]["items"]
    assert len(items) == 3
    assert all(item["evidence_type"] == "synthetic" and "синтетика" in item["title"] for item in items)
    assert all(item["budget"]["amount_kzt"] is None for item in items)
    delayed = call(service, "GET", "/objects/demo-r02-sidewalk-delay")["body"]["data"]
    assert delayed["item"]["schedule"]["original_planned_end"] == "2026-10-20"
    assert delayed["item"]["schedule"]["current_planned_end"] == "2026-10-27"
    assert delayed["history"][-1]["changed_fields"] == ["schedule.current_planned_end"]
    assert delayed["history"][-1]["public_actor_label"] == "Демо-данные (синтетика)"
    assert call(service, "GET", "/objects/demo-r02-draft-hidden")["status"] == 404
    with pytest.raises(ImportRejected):
        cli.seed_demo(service, package([real_item()]))


def run_cli(*args, stdin=""):
    return subprocess.run([sys.executable, "-m", "ui.civic_store", *args], input=stdin, text=True,
                          capture_output=True, cwd=REPO_ROOT, timeout=120)


def test_cli_end_to_end(tmp_path):
    db = str(tmp_path / "cli.sqlite3")
    assert run_cli("--db", db, "init").returncode == 0
    secret = "Cli-Strong-Pass-2026"
    created = run_cli("--db", db, "create-editor", "clieditor", "--password-stdin", stdin=secret + "\n")
    assert created.returncode == 0, created.stderr
    assert secret not in created.stdout + created.stderr
    no_tty = run_cli("--db", db, "create-editor", "other")
    assert no_tty.returncode != 0 and "--password-stdin" in (no_tty.stderr + no_tty.stdout)
    weak = run_cli("--db", db, "create-editor", "weak", "--password-stdin", stdin="short\n")
    assert weak.returncode == 2
    listed = json.loads(run_cli("--db", db, "list-editors").stdout)
    assert [user["username"] for user in listed] == ["clieditor"]
    assert "password" not in json.dumps(listed)
    pkg = tmp_path / "pkg.json"
    pkg.write_text(json.dumps(package([real_item()])), encoding="utf-8")
    dry = json.loads(run_cli("--db", db, "import", str(pkg), "--dry-run").stdout)
    assert dry["status"] == "dry_run"
    applied = json.loads(run_cli("--db", db, "import", str(pkg)).stdout)
    assert applied["counts"]["create"] == 1
    again = json.loads(run_cli("--db", db, "import", str(pkg)).stdout)
    assert again["counts"]["skip_unchanged"] == 1
    status = json.loads(run_cli("--db", db, "status").stdout)
    assert status["objects"] == {"draft": 1} and status["public_objects"] == 0
    service = CivicService(db)
    assert Editor(service, "clieditor", secret).get("/staff/objects")["status"] == 200


def test_cli_refuses_database_inside_web():
    result = run_cli("--db", str(REPO_ROOT / "web" / "civic.sqlite3"), "init")
    assert result.returncode == 2
    assert not (REPO_ROOT / "web" / "civic.sqlite3").exists()


def test_backup_and_restore_round_trip(tmp_path, service, editor, db_path, clock, capsys):
    item = editor.create()
    editor.publish(item)
    backup = tmp_path / "backups" / "copy.sqlite3"
    args = cli.build_parser().parse_args(["--db", str(db_path), "backup", str(backup)])
    args.func(args, service)
    assert backup.exists()
    # После копии появляется ещё один объект, затем восстанавливаем.
    later = editor.create(title="Создан после копии")
    args = cli.build_parser().parse_args(["--db", str(db_path), "restore", str(backup)])
    with pytest.raises(SystemExit):
        args.func(args)  # без --yes ничего не делает
    assert service.objects.get_staff(later["id"])["item"]["title"] == "Создан после копии"
    args = cli.build_parser().parse_args(["--db", str(db_path), "restore", str(backup), "--yes"])
    args.func(args)
    restored = CivicService(db_path, clock=clock)
    assert call(restored, "GET", f"/objects/{item['id']}")["status"] == 200
    with pytest.raises(Exception):
        restored.objects.get_staff(later["id"])
    safety = list(db_path.parent.glob("civic.pre-restore-*.sqlite3"))
    assert len(safety) == 1  # прежняя база сохранена, а не перезаписана безвозвратно
    with sqlite3.connect(safety[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 2


def test_export_audit_lists_history_without_secrets(service, editor, db_path, tmp_path):
    item = editor.create(internal_notes="служебная заметка")
    editor.publish(item)
    out = tmp_path / "audit.jsonl"
    args = cli.build_parser().parse_args(["--db", str(db_path), "export-audit", "--out", str(out)])
    args.func(args, service)
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [line["action"] for line in lines] == ["create", "publish"]
    text = out.read_text(encoding="utf-8")
    assert PASSWORD not in text and "password" not in text and "scrypt" not in text
    assert editor.cookie not in text and editor.csrf not in text


def test_password_stdin_accepts_windows_line_endings(tmp_path):
    db = str(tmp_path / "crlf.sqlite3")
    secret = "Crlf-Strong-Pass-2026"
    assert run_cli("--db", db, "create-editor", "crlfuser", "--password-stdin", stdin=secret + "\r\n").returncode == 0
    assert Editor(CivicService(db), "crlfuser", secret).get("/staff/objects")["status"] == 200


def test_reimport_with_trailing_newline_id_does_not_duplicate(service):
    import_package(service.objects, package([real_item("road-1")]))
    with pytest.raises(ImportRejected) as rejected:
        import_package(service.objects, package([real_item("road-1\n")]))
    assert rejected.value.report["items"][0]["action"] == "invalid"
    with service.db.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM civic_objects").fetchone()[0] == 1


def test_restore_keeps_security_measures(tmp_path, service, db_path, clock, capsys):
    """Ревью: откат данных не должен оживлять украденную сессию, отключённого редактора и старый пароль."""
    stolen = Editor(service, "editor1", PASSWORD)
    victim2 = Editor(service, "editor2", PASSWORD + "x")
    backup = tmp_path / "pre-incident.sqlite3"
    args = cli.build_parser().parse_args(["--db", str(db_path), "backup", str(backup)])
    args.func(args, service)
    clock.advance(minutes=5)
    service.accounts.disable_user("editor1")
    service.accounts.set_password("editor2", "Rotated-Strong-Pass-77")
    args = cli.build_parser().parse_args(["--db", str(db_path), "restore", str(backup), "--yes"])
    args.func(args)
    output = capsys.readouterr().out
    assert "editor1: отключение сохранено." in output and "editor2: новый пароль сохранён." in output
    restored = CivicService(db_path, clock=clock)
    assert restored.resolve_principal(stolen.ctx()) is None
    assert restored.resolve_principal(victim2.ctx()) is None
    assert call(restored, "POST", "/session/login", {"username": "editor1", "password": PASSWORD})["status"] == 401
    assert call(restored, "POST", "/session/login", {"username": "editor2", "password": PASSWORD + "x"})["status"] == 401
    assert Editor(restored, "editor2", "Rotated-Strong-Pass-77").get("/staff/objects")["status"] == 200


@pytest.mark.skipif(__import__("os").name != "posix", reason="права POSIX")
def test_export_audit_file_is_private_and_not_overwritten(service, editor, db_path, tmp_path):
    import stat
    editor.create()
    out = tmp_path / "audit.jsonl"
    args = cli.build_parser().parse_args(["--db", str(db_path), "export-audit", "--out", str(out)])
    args.func(args, service)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    with pytest.raises(SystemExit):
        args.func(args, service)


def test_dummy_hash_is_ready_before_first_login(tmp_path):
    from ui.civic_store import auth
    auth._DUMMY_HASH = None
    CivicService(tmp_path / "eager.sqlite3")
    assert auth._DUMMY_HASH is not None
