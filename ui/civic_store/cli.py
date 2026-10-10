"""CLI R02: python -m ui.civic_store [--db PATH] <команда>.

  init                          создать/мигрировать базу (по умолчанию .runtime/civic.sqlite3)
  status                        версия схемы и счётчики
  create-editor USER            учётная запись редактора; пароль через getpass (дважды)
  set-password USER             смена пароля (все сессии пользователя отзываются)
  disable-editor USER           отключить вход и отозвать сессии
  list-editors                  список без хэшей паролей
  revoke-sessions [USER]        выход везде
  import FILE [--dry-run]       идемпотентный импорт пакета civic-v1 (только draft)
  seed-demo [--package FILE]    синтетический демо-набор + демо-публикация (только synthetic)
  seed-r14-demo                 R06 раунд 14: seed-demo (если пусто) + демо-этапы и 5 демо-предложений в Нуре
  backup DEST                   согласованная копия через SQLite backup API
  restore SRC --yes             восстановление с предварительной копией текущей базы
  verify-backup SRC             проверить копию только для чтения: целостность, схема, счётчики
  export-audit [--since ISO]    служебная история изменений (JSON Lines) для редактора
  export-public [--out FILE]    только опубликованные карточки + публичная история (без сессий/секретов)
  restore-public FILE [--dry-run]  восстановить публичную выгрузку в базу без объектов

Пароль никогда не принимается аргументом командной строки (он остался бы в истории shell
и в списке процессов). Без терминала используйте --password-stdin (одна строка stdin).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from .auth import PasswordPolicyError, ROLES, check_password_policy, normalize_username
from .db import (DEFAULT_DB_PATH, MIGRATIONS, SCHEMA_VERSION, Database, StorageError, _checksum,
                 create_private_file, resolve_db_path, restrict_permissions)
from .importer import ImportRejected, describe_package, import_package, load_package
from .objects import Actor, BadRequest, Conflict, NotFound
from .public_export import PublicRestoreRejected, export_public, restore_public
from .service import CivicService
from .validate import ValidationError


DEMO_PACKAGE = Path(__file__).with_name("demo_package.json")
DEMO_ACTOR = Actor(kind="system", user_id=None, label="seed-demo",
                   public_label="Демо-данные (синтетика)")


def _db_path(args) -> Path:
    return Path(args.db or os.environ.get("CIVIC_DB_PATH") or DEFAULT_DB_PATH)


def _read_password(args, username: str) -> str:
    if args.password_stdin:
        # Только перевод строки (LF или CRLF Windows); прочие пробелы — часть пароля.
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        if not sys.stdin.isatty():
            raise SystemExit("Нет терминала для скрытого ввода: используйте --password-stdin.")
        password = getpass.getpass("Пароль: ")
        if getpass.getpass("Повторите пароль: ") != password:
            raise SystemExit("Пароли не совпадают.")
    check_password_policy(username, password)
    return password


def _print(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_init(args, service):
    _print({"db": str(service.db.path), "schema_version": SCHEMA_VERSION,
            "migrations": sorted(service.db.applied_migrations())})


def cmd_status(args, service):
    with service.db.read() as conn:
        counts = {row["publication"]: row["n"] for row in conn.execute(
            "SELECT publication, COUNT(*) AS n FROM civic_objects GROUP BY publication")}
        _print({
            "db": str(service.db.path), "schema_version": SCHEMA_VERSION,
            "objects": counts,
            "public_objects": conn.execute("SELECT COUNT(*) FROM civic_public_objects").fetchone()[0],
            "history_entries": conn.execute("SELECT COUNT(*) FROM civic_history").fetchone()[0],
            "editors": conn.execute("SELECT COUNT(*) FROM civic_users WHERE disabled_at IS NULL").fetchone()[0],
            "pending_import_candidates": conn.execute("SELECT COUNT(*) FROM civic_import_candidates").fetchone()[0],
        })


def cmd_create_editor(args, service):
    username = normalize_username(args.username)
    if username is None:
        raise SystemExit("Логин: 3–32 символа a-z, 0-9, точка, дефис, подчёркивание.")
    password = _read_password(args, username)
    service.accounts.create_user(username, password, display_name=args.display_name,
                                 public_label=args.public_label, role=args.role)
    print(f"Создан редактор {username} (роль {args.role}). Пароль не сохранён в открытом виде.")


def cmd_set_password(args, service):
    username = normalize_username(args.username) or ""
    service.accounts.set_password(username, _read_password(args, username))
    print(f"Пароль {username} изменён, сессии отозваны.")


def cmd_disable_editor(args, service):
    service.accounts.disable_user(args.username)
    print(f"Вход {args.username} отключён, сессии отозваны.")


def cmd_list_editors(args, service):
    _print(service.accounts.list_users())


def cmd_revoke_sessions(args, service):
    print(f"Отозвано сессий: {service.accounts.revoke_all(args.username)}")


def cmd_import(args, service):
    report = import_package(service.objects, load_package(args.file), source=args.source,
                            dry_run=args.dry_run, allow_partial=args.allow_partial)
    _print(report)


def seed_demo(service, package, *, publish=True) -> dict:
    """Импорт синтетического пакета и публикация по suggested_publication.

    Работает только для slice.demo=true (импорт уже требует evidence_type=synthetic).
    Для записи с разными original/current_planned_end показывает перенос срока
    двумя публикациями с причиной — чтобы у демо была публичная история.
    """
    meta = describe_package(package)
    if not meta["demo"]:
        raise ImportRejected("seed-demo принимает только синтетический пакет (slice.demo=true).")
    report = import_package(service.objects, package)
    if not publish:
        return report
    intents = {item["id"]: item.get("suggested_publication") or item.get("publication")
               for item in meta["items"] if isinstance(item, dict)}
    done = []
    repo = service.objects
    for entry in report["items"]:
        if entry["action"] != "create":
            continue
        intent = intents.get(entry["external_id"])
        object_id = entry["object_id"]
        item = repo.get_staff(object_id)["item"]
        if intent == "published":
            schedule = item["schedule"]
            delayed = (schedule["original_planned_end"] and schedule["current_planned_end"]
                       and schedule["original_planned_end"] != schedule["current_planned_end"])
            if delayed:
                final_end = schedule["current_planned_end"]
                item, _ = repo.update(DEMO_ACTOR, object_id, expected_revision=item["revision"],
                                      changes={"schedule": {"current_planned_end": schedule["original_planned_end"]}},
                                      reason="Демо: исходный срок")
                item = repo.publish(DEMO_ACTOR, object_id, expected_revision=item["revision"],
                                    reason="Демо: первая публикация (синтетика)")
                item, _ = repo.update(DEMO_ACTOR, object_id, expected_revision=item["revision"],
                                      changes={"schedule": {"current_planned_end": final_end}},
                                      reason="Демо: перенос срока")
            item = repo.publish(DEMO_ACTOR, object_id, expected_revision=item["revision"],
                                reason=("Демо: перенос срока — синтетический пример" if delayed
                                        else "Демо: публикация синтетической записи"))
        elif intent == "archived":
            item = repo.archive(DEMO_ACTOR, object_id, expected_revision=item["revision"],
                                reason="Демо: архивная синтетическая запись")
        done.append({"object_id": object_id, "publication": item["publication"]})
    report["demo_publication"] = done
    return report


def cmd_seed_demo(args, service):
    package = load_package(args.package or DEMO_PACKAGE)
    _print(seed_demo(service, package, publish=not args.no_publish))


def cmd_seed_r14_demo(args, service):
    from .demo_r14 import seed_r14_demo
    with service.db.read() as conn:
        has_demo = conn.execute(
            "SELECT 1 FROM civic_objects WHERE json_extract(data_json, '$.evidence_type') = 'synthetic'").fetchone()
    report = {"seed_demo": None if has_demo else seed_demo(service, load_package(DEMO_PACKAGE))}
    report.update(seed_r14_demo(service))
    _print(report)


def _integrity_ok(path: Path) -> bool:
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def _backup(src: Path, dest: Path, *, exclusive: bool = False) -> None:
    if not create_private_file(dest, exclusive=exclusive):
        raise StorageError(f"Файл уже существует: {dest}")
    source, target = sqlite3.connect(src), sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    restrict_permissions(dest)
    if not _integrity_ok(dest):
        raise StorageError("Копия не прошла integrity_check.")


def _existing_db(args) -> Path:
    path = resolve_db_path(_db_path(args))
    if not path.is_file():
        raise SystemExit(f"База не найдена: {path}. Выполните init или укажите --db / CIVIC_DB_PATH.")
    return path


def cmd_backup(args, service=None):
    # Копия «как есть»: без миграции и без создания пустой базы по опечатке в пути.
    source = service.db.path if service is not None else _existing_db(args)
    dest = resolve_db_path(args.dest)
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        _backup(source, dest, exclusive=True)
    except StorageError as exc:
        if dest.exists() and "уже существует" in str(exc):
            raise SystemExit("Файл назначения уже существует — выберите новое имя.")
        raise
    print(f"Резервная копия: {dest}")


def _check_source_schema(source: Path) -> None:
    """Копия должна быть базой civic_store с миграциями, совпадающими с кодом (до любой записи)."""
    known = {version: _checksum(statements) for version, _, statements in MIGRATIONS}
    conn = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("Исходный файл повреждён (integrity_check).")
        rows = conn.execute("SELECT version, checksum FROM civic_schema_migrations").fetchall()
    except sqlite3.DatabaseError:
        raise SystemExit("Это не база civic_store.")
    finally:
        conn.close()
    if not rows:
        raise SystemExit("В копии нет миграций civic_store.")
    for version, checksum in rows:
        if version not in known:
            raise SystemExit(f"Копия создана более новой версией (миграция {version}); восстановление не выполнено.")
        if checksum != known[version]:
            raise SystemExit(f"Миграция {version} в копии отличается от кода; восстановление не выполнено.")


def cmd_verify_backup(args, _service_unused=None):
    """Копия открывается только для чтения; рабочая база не трогается и не нужна."""
    source = Path(args.src).expanduser().resolve()
    if not source.is_file():
        raise SystemExit("Файл копии не найден.")
    _check_source_schema(source)
    conn = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    try:
        versions = [r[0] for r in conn.execute("SELECT version FROM civic_schema_migrations ORDER BY 1")]
        counts = {row[0]: row[1] for row in conn.execute(
            "SELECT publication, COUNT(*) FROM civic_objects GROUP BY publication")}
        report = {
            "file": str(source), "integrity": "ok", "migrations": versions,
            "needs_migration": [v for v, _, _ in MIGRATIONS if v not in versions],
            "objects": counts,
            "public_objects": conn.execute("SELECT COUNT(*) FROM civic_public_objects").fetchone()[0],
            "history_entries": conn.execute("SELECT COUNT(*) FROM civic_history").fetchone()[0],
            "editors": conn.execute("SELECT COUNT(*) FROM civic_users").fetchone()[0],
            "note": "Полная служебная копия: содержит хэши паролей, сессии и заметки — хранить как секрет.",
        }
    finally:
        conn.close()
    _print(report)


def _unique_sibling(path: Path, label: str) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for attempt in range(1000):
        suffix = f"-{attempt}" if attempt else ""
        candidate = path.with_name(f"{path.stem}.{label}-{stamp}{suffix}.sqlite3")
        if create_private_file(candidate, exclusive=True):
            return candidate
    raise StorageError("Не удалось выбрать имя файла копии.")


def _remove_db_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(str(path) + suffix).unlink()
        except FileNotFoundError:
            pass


def cmd_restore(args, _service_unused=None):
    target = _db_path(args)
    source = Path(args.src).expanduser().resolve()
    if not args.yes:
        raise SystemExit("Восстановление заменит текущую базу. Остановите сервер и повторите с --yes.")
    if not source.is_file():
        raise SystemExit("Файл копии не найден.")
    _check_source_schema(source)
    target_path = resolve_db_path(target)
    target_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    current_users = _security_state(target_path) if target_path.exists() else {}
    # 1) Готовим восстановленную базу во временном файле рядом: миграции и меры безопасности.
    staging = _unique_sibling(target_path, "restore-staging")
    try:
        src, dst = sqlite3.connect(source), sqlite3.connect(staging)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        Database(staging).migrate()
        notes = _carry_security_state(staging, current_users)
        if not _integrity_ok(staging):
            raise StorageError("Подготовленная копия не прошла integrity_check.")
        # 2) Только теперь трогаем рабочую базу: сначала её копия с уникальным именем.
        if target_path.exists():
            safety = _unique_sibling(target_path, "pre-restore")
            _backup(target_path, safety)
            print(f"Текущая база сохранена: {safety}")
        else:
            create_private_file(target_path)
        # 3) Запись через backup API (корректно с WAL рабочей базы), без os.replace поверх -wal.
        src, dst = sqlite3.connect(staging), sqlite3.connect(target_path)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    finally:
        _remove_db_files(staging)
    restrict_permissions(target_path)
    for line in notes:
        print(line)
    print(f"Восстановлено из {source}")


def _security_state(path: Path) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {row["username"]: dict(row) for row in conn.execute(
            "SELECT username, password_hash, password_changed_at, disabled_at FROM civic_users")}
    except sqlite3.DatabaseError:
        return {}
    finally:
        conn.close()


def _carry_security_state(path: Path, current: dict) -> list[str]:
    """После восстановления данные откатываются, а меры безопасности — нет.

    Все сессии отзываются (украденный токен из копии не оживает); отключение редактора и
    более новая смена пароля из текущей базы переносятся в восстановленную.
    """
    notes = []
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        revoked = conn.execute("UPDATE civic_sessions SET revoked_at = ? WHERE revoked_at IS NULL",
                               (time.time(),)).rowcount
        notes.append(f"Отозвано сессий из копии: {revoked}")
        restored = {row["username"]: row for row in conn.execute("SELECT * FROM civic_users")}
        for username, now_state in current.items():
            old = restored.get(username)
            if old is None:
                notes.append(f"Внимание: редактора {username} нет в копии — создайте заново при необходимости.")
                continue
            if now_state["disabled_at"] and not old["disabled_at"]:
                conn.execute("UPDATE civic_users SET disabled_at = ? WHERE username = ?",
                             (now_state["disabled_at"], username))
                notes.append(f"{username}: отключение сохранено.")
            if now_state["password_changed_at"] > old["password_changed_at"]:
                conn.execute("UPDATE civic_users SET password_hash = ?, password_changed_at = ? WHERE username = ?",
                             (now_state["password_hash"], now_state["password_changed_at"], username))
                notes.append(f"{username}: новый пароль сохранён.")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return notes


def cmd_export_audit(args, service):
    if args.out:
        # Служебные данные (diff, internal_notes, логины): файл сразу 0600 и только новый.
        try:
            fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise SystemExit("Файл уже существует — выберите новое имя.")
        out = os.fdopen(fd, "w", encoding="utf-8")
    else:
        out = sys.stdout
    try:
        with service.db.read() as conn:
            rows = conn.execute(
                """SELECT id, object_id, revision, at, action, publication, changed_fields_json,
                          diff_json, reason, actor_kind, actor_label, public_actor_label, is_public
                   FROM civic_history WHERE at >= ? ORDER BY id""", (args.since or "",))
            for row in rows:
                out.write(json.dumps({
                    "id": row["id"], "object_id": row["object_id"], "revision": row["revision"],
                    "at": row["at"], "action": row["action"], "publication": row["publication"],
                    "changed_fields": json.loads(row["changed_fields_json"]),
                    "diff": json.loads(row["diff_json"]), "reason": row["reason"],
                    "actor_kind": row["actor_kind"], "actor_label": row["actor_label"],
                    "public_actor_label": row["public_actor_label"], "is_public": bool(row["is_public"]),
                }, ensure_ascii=False) + "\n")
    finally:
        if args.out:
            out.close()


def cmd_export_public(args, service):
    text = json.dumps(export_public(service.objects), ensure_ascii=False, indent=1) + "\n"
    if not args.out:
        sys.stdout.write(text)
        return
    try:
        # Данные публичные, но существующий файл не перезаписываем молча.
        with open(args.out, "x", encoding="utf-8") as out:
            out.write(text)
    except FileExistsError:
        raise SystemExit("Файл уже существует — выберите новое имя.")
    print(f"Публичная выгрузка: {args.out}", file=sys.stderr)


def cmd_restore_public(args, service):
    try:
        export = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise PublicRestoreRejected(f"Не удалось прочитать выгрузку: {exc.__class__.__name__}.")
    _print(restore_public(service.objects, export, dry_run=args.dry_run))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ui.civic_store",
                                     description="R02 civic_store: база объектов и доступ редактора")
    parser.add_argument("--db", help="файл SQLite (по умолчанию $CIVIC_DB_PATH или .runtime/civic.sqlite3)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("status").set_defaults(func=cmd_status)
    for name, func in (("create-editor", cmd_create_editor), ("set-password", cmd_set_password)):
        cmd = sub.add_parser(name)
        cmd.add_argument("username")
        cmd.add_argument("--password-stdin", action="store_true",
                         help="прочитать пароль одной строкой из stdin (для автоматизации)")
        if name == "create-editor":
            cmd.add_argument("--display-name")
            cmd.add_argument("--public-label", help="подпись в публичной истории (по умолчанию «Редактор платформы»)")
            cmd.add_argument("--role", choices=ROLES, default="editor")
        cmd.set_defaults(func=func)
    cmd = sub.add_parser("disable-editor")
    cmd.add_argument("username")
    cmd.set_defaults(func=cmd_disable_editor)
    sub.add_parser("list-editors").set_defaults(func=cmd_list_editors)
    cmd = sub.add_parser("revoke-sessions")
    cmd.add_argument("username", nargs="?")
    cmd.set_defaults(func=cmd_revoke_sessions)
    cmd = sub.add_parser("import")
    cmd.add_argument("file")
    cmd.add_argument("--source", help="import_source (по умолчанию r05-astana-real|r05-astana-demo по slice.demo)")
    cmd.add_argument("--dry-run", action="store_true")
    cmd.add_argument("--allow-partial", action="store_true", help="пропустить недопустимые записи")
    cmd.set_defaults(func=cmd_import)
    cmd = sub.add_parser("seed-demo")
    cmd.add_argument("--package", help="синтетический пакет (по умолчанию встроенный demo_package.json)")
    cmd.add_argument("--no-publish", action="store_true")
    cmd.set_defaults(func=cmd_seed_demo)
    sub.add_parser("seed-r14-demo").set_defaults(func=cmd_seed_r14_demo)
    cmd = sub.add_parser("backup")
    cmd.add_argument("dest")
    cmd.set_defaults(func=cmd_backup, no_service=True)
    cmd = sub.add_parser("restore")
    cmd.add_argument("src")
    cmd.add_argument("--yes", action="store_true")
    cmd.set_defaults(func=cmd_restore, no_service=True)
    cmd = sub.add_parser("verify-backup")
    cmd.add_argument("src")
    cmd.set_defaults(func=cmd_verify_backup, no_service=True)
    cmd = sub.add_parser("export-audit")
    cmd.add_argument("--since", help="ISO-время, с которого выгружать")
    cmd.add_argument("--out")
    cmd.set_defaults(func=cmd_export_audit)
    cmd = sub.add_parser("export-public")
    cmd.add_argument("--out")
    cmd.set_defaults(func=cmd_export_public)
    cmd = sub.add_parser("restore-public")
    cmd.add_argument("file")
    cmd.add_argument("--dry-run", action="store_true")
    cmd.set_defaults(func=cmd_restore_public)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if getattr(args, "no_service", False):
            args.func(args)
        elif args.command == "init":
            args.func(args, CivicService(_db_path(args)))  # единственная команда, что создаёт/мигрирует
        else:
            # Остальные работают только с существующей базой текущей схемы: опечатка в --db
            # не создаёт новую пустую базу, status/export/dry-run ничего не мигрируют.
            args.func(args, CivicService(_existing_db(args), auto_migrate=False))
    except (StorageError, PasswordPolicyError, ImportRejected, ValidationError, BadRequest,
            NotFound, Conflict, PublicRestoreRejected) as exc:
        report = getattr(exc, "report", None)
        if report:
            _print(report)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    return 0
