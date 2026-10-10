"""Выгрузка и восстановление ТОЛЬКО публичных данных civic-v1.

Зачем: перенос опубликованных карточек на другой экземпляр, открытая выгрузка, проверка
восстановления без копирования всей базы. В отличие от `backup` (полная копия SQLite с хэшами
паролей, сессиями, черновиками и служебными заметками), сюда попадает лишь то, что и так
отдаёт публичный API: опубликованные карточки (allowlist dto.PUBLIC_FIELDS) и их публичная
история. Учётных записей, сессий, CSRF, черновиков, архива, internal_notes, служебных
diff/снимков, логинов и кандидатов импорта в выгрузке нет по построению.

Восстановление — только в базу без объектов: прежняя история не переписывается и не
сливается. Публичная история переносится как есть (ревизии, даты, причины, подписи);
служебная история недоступна и не выдумывается — карточка помечается служебной заметкой.
"""

from __future__ import annotations

import hashlib
import json

from . import dto
from .objects import ARCHIVE_PUBLIC_REASON, ObjectRepository, _dumps, iso, utc_now
from .validate import (CITY, SCHEMA_VERSION, ValidationError, _Errors, clean_reason, clean_text,
                       is_valid_id, validate_content, validate_for_publication)


FORMAT = "civic-public-export-v1"
MAX_OBJECTS = 20000
MAX_HISTORY = 1000
RESTORE_SOURCE = "public-restore"


class PublicRestoreRejected(ValueError):
    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report


def _digest(objects) -> str:
    text = json.dumps(objects, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def export_public(repo: ObjectRepository) -> dict:
    """Все опубликованные карточки с публичной историей; чтение через публичный путь."""
    with repo.db.read() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM civic_public_objects ORDER BY id")]
    objects = []
    for object_id in ids:
        detail = repo.get_public(object_id)  # тот же allowlist, что у GET /objects/{id}
        objects.append({"item": detail["item"], "history": detail["history"]})
    return {
        "format": FORMAT, "schema_version": SCHEMA_VERSION, "city": CITY,
        "exported_at": iso(utc_now(repo.clock)),
        "note": "Только опубликованные данные публичного API; evidence_type каждой записи сохраняется.",
        "counts": {"objects": len(objects),
                   "synthetic": sum(1 for o in objects if o["item"]["evidence_type"] == "synthetic")},
        "objects_digest": _digest(objects),
        "objects": objects,
    }


def _check_history(entries, object_id, revision, errors, prefix):
    if not isinstance(entries, list) or not entries or len(entries) > MAX_HISTORY:
        errors.add(f"{prefix}.history", f"Непустой список до {MAX_HISTORY} записей.")
        return []
    out, last = [], 0
    for index, entry in enumerate(entries):
        path = f"{prefix}.history[{index}]"
        if not isinstance(entry, dict) or set(entry) != set(dto.PUBLIC_HISTORY_FIELDS):
            errors.add(path, "Ровно поля публичной истории civic-v1.")
            continue
        rev = entry["revision"]
        if isinstance(rev, bool) or not isinstance(rev, int) or not last < rev <= revision:
            errors.add(f"{path}.revision", "Возрастающие ревизии не больше ревизии карточки.")
            continue
        last = rev
        if entry["object_id"] != object_id or entry["id"] != f"{object_id}@{rev}":
            errors.add(f"{path}.id", "id/object_id не соответствуют карточке.")
        at = entry["at"]
        if not isinstance(at, str) or not 19 <= len(at) <= 40 or at[4:5] != "-":
            errors.add(f"{path}.at", "ISO 8601 время.")
        fields = entry["changed_fields"]
        if (not isinstance(fields, list) or len(fields) > 100
                or not all(isinstance(f, str) and 0 < len(f) <= 64 for f in fields)):
            errors.add(f"{path}.changed_fields", "Список путей полей.")
        try:
            reason = clean_reason(entry["reason"], required=False)
        except ValidationError:
            errors.add(f"{path}.reason", "Простой текст без HTML.")
            reason = ""
        label = clean_text(entry["public_actor_label"], f"{path}.public_actor_label", errors,
                           max_len=120, required=True)
        out.append({**entry, "reason": reason, "public_actor_label": label})
    if out and out[-1]["revision"] != revision:
        errors.add(f"{prefix}.history", "Последняя публичная запись должна соответствовать ревизии карточки.")
    return out


def check_export(export, *, today) -> list[dict]:
    """Проверка выгрузки целиком; ValidationError с путями полей по каждой карточке."""
    errors = _Errors()
    if not isinstance(export, dict) or export.get("format") != FORMAT:
        raise PublicRestoreRejected(f"Это не выгрузка {FORMAT}.")
    if export.get("schema_version") != SCHEMA_VERSION or export.get("city") != CITY:
        raise PublicRestoreRejected("Выгрузка не civic-v1 для Астаны.")
    objects = export.get("objects")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        raise PublicRestoreRejected(f"objects — список до {MAX_OBJECTS}.")
    if export.get("objects_digest") != _digest(objects):
        raise PublicRestoreRejected("objects_digest не совпадает: файл изменён или повреждён.")
    prepared, seen = [], set()
    for index, entry in enumerate(objects):
        prefix = f"objects[{index}]"
        item = entry.get("item") if isinstance(entry, dict) else None
        if not isinstance(item, dict) or set(entry) != {"item", "history"}:
            errors.add(prefix, "{item, history}.")
            continue
        object_id = item.get("id")
        if not is_valid_id(object_id) or object_id in seen:
            errors.add(f"{prefix}.item.id", "Допустимый уникальный id.")
            continue
        seen.add(object_id)
        if "geometry_source" not in item:
            # Выгрузка до раунда 14: поля ещё не было — значит «неизвестно».
            item = {**item, "geometry_source": None}
        try:
            if dto.sanitize_public(item) != item or set(item) != set(dto.PUBLIC_FIELDS):
                raise ValidationError({"item": "Только публичные поля civic-v1 (allowlist)."})
            if item["publication"] != "published" or item["city"] != CITY \
                    or item["schema_version"] != SCHEMA_VERSION:
                raise ValidationError({"item.publication": "Только опубликованные карточки Астаны civic-v1."})
            content = dto.content_of(item)
            normalized = validate_content(content, today=today, original_locked=True)
            validate_for_publication(normalized)
            if normalized != content:
                raise ValidationError({"item": "Содержимое не в нормализованном виде civic-v1."})
        except ValidationError as exc:
            for key, message in exc.fields.items():
                errors.add(f"{prefix}.{key}" if key.startswith("item") else f"{prefix}.item.{key}", message)
            continue
        revision = item["revision"]
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            errors.add(f"{prefix}.item.revision", "Целое ≥ 1.")
            continue
        history = _check_history(entry["history"], object_id, revision, errors, prefix)
        prepared.append({"item": item, "content": content, "history": history})
    errors.raise_if_any()
    return prepared


def restore_public(repo: ObjectRepository, export, *, dry_run=False, actor_label="cli") -> dict:
    """Восстанавливает публичные карточки в базу без объектов. Всё или ничего."""
    try:
        prepared = check_export(export, today=repo.today())
    except ValidationError as exc:
        raise PublicRestoreRejected("Выгрузка не прошла проверку; ничего не восстановлено.",
                                    {"status": "rejected", "fields": exc.fields})
    report = {"status": "dry_run" if dry_run else "applied", "dry_run": bool(dry_run),
              "objects": len(prepared), "history_entries": sum(len(p["history"]) for p in prepared),
              "objects_digest": export["objects_digest"], "exported_at": export.get("exported_at")}
    now = iso(utc_now(repo.clock))
    note = (f"Восстановлено из публичной выгрузки {str(export.get('exported_at'))[:40]} "
            f"(sha256 {export['objects_digest'][:12]}). Служебная история, заметки и авторы "
            "правок не переносились.")
    try:
        with repo.db.write() as conn:
            _write_restore(conn, prepared, note, actor_label)
            if dry_run:
                raise _DryRun()  # откат всей транзакции
            conn.execute(
                "INSERT INTO civic_imports(source, package_digest, at, actor_label, report_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (RESTORE_SOURCE, export["objects_digest"], now, f"{RESTORE_SOURCE}:{actor_label}"[:120],
                 _dumps(report)))
    except _DryRun:
        pass
    return report


class _DryRun(Exception):
    pass


def _write_restore(conn, prepared, note, actor_label):
    if conn.execute("SELECT 1 FROM civic_objects LIMIT 1").fetchone():
        raise PublicRestoreRejected("В базе уже есть объекты: восстановление публичной выгрузки "
                                    "выполняется только в пустую базу (история не сливается).")
    for entry in prepared:
        item, content, history = entry["item"], entry["content"], entry["history"]
        first_publish = next((h["at"] for h in history if not _is_archive(h)), item["updated_at"])
        conn.execute(
            """INSERT INTO civic_objects(id, city, kind, status, publication, planned_start,
                   current_planned_end, data_json, internal_notes, revision, created_at, updated_at,
                   first_published_at, published_revision)
               VALUES (?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item["id"], CITY, content["kind"], content["status"], content["schedule"]["planned_start"],
             content["schedule"]["current_planned_end"], _dumps(content), note, item["revision"],
             history[0]["at"], item["updated_at"], first_publish, item["revision"]))
        for h in history:
            archive = _is_archive(h)
            last = h["revision"] == item["revision"]
            conn.execute(
                """INSERT INTO civic_history(object_id, revision, at, action, publication,
                       changed_fields_json, diff_json, reason, actor_kind, actor_user_id, actor_label,
                       public_actor_label, is_public, public_changed_fields_json, public_dto_json,
                       snapshot_json)
                   VALUES (?, ?, ?, ?, ?, ?, '{}', ?, 'system', NULL, ?, ?, 1, ?, ?, ?)""",
                (item["id"], h["revision"], h["at"], "archive" if archive else "publish",
                 "archived" if archive else "published", _dumps(sorted(h["changed_fields"])),
                 h["reason"], f"{RESTORE_SOURCE}:{actor_label}"[:120], h["public_actor_label"],
                 _dumps(h["changed_fields"]), _dumps(item) if last else None,
                 _dumps({"content": content if last else None, "restored_from": RESTORE_SOURCE})))
        conn.execute(
            """INSERT INTO civic_public_objects(id, kind, status, planned_start, current_planned_end,
                   revision, updated_at, dto_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (item["id"], content["kind"], content["status"], content["schedule"]["planned_start"],
             content["schedule"]["current_planned_end"], item["revision"], item["updated_at"],
             _dumps(item)))


def _is_archive(entry) -> bool:
    return entry["changed_fields"] == ["publication"] and entry["reason"] == ARCHIVE_PUBLIC_REASON
