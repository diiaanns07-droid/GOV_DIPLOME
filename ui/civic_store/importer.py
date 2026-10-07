"""Идемпотентный импорт пакета civic-v1 (формат R05: data/civic/astana/*.json).

Пакет: {"schema_version":"civic-v1","city":"astana","slice":{name,version,demo,...},"items":[...]}
(допускается и голый список объектов с явным --source).

Правила:
- импорт никогда не публикует и не архивирует: новая запись — draft;
- publication/revision/updated_at из пакета игнорируются (назначает сервер);
- повторный импорт того же содержимого ничего не меняет (skip_unchanged);
- изменённая запись обновляется только если это нетронутый импортированный черновик;
  если редактор уже правил или публиковал объект — изменение ложится в
  civic_import_candidates (editor_review), ручные/опубликованные данные не затираются;
- запись, исчезнувшая из пакета, не удаляется и не архивируется (report_missing);
- dry-run выполняет ту же логику в транзакции и откатывает её; при недопустимых записях
  dry-run всё равно показывает, что произошло бы с допустимыми (статус rejected);
- при ошибках проверки по умолчанию не применяется ничего (allow_partial=False);
- отчёт по записи: changed_fields (чем пакет отличается от текущей карточки),
  source_changed_fields / source_refs_change (что изменилось в самом источнике с прошлого
  импорта), ignored_fields (серверные поля из пакета, например publication) и
  possible_duplicates (тот же URL источника или то же название у объекта другого
  происхождения) — предупреждение, объект не сливается автоматически.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .objects import Actor, ObjectRepository, iso, utc_now
from .validate import (CITY, ID_RE, SCHEMA_VERSION, ValidationError, clean_reason, diff, is_valid_id,
                       split_payload, validate_content)


MAX_PACKAGE_BYTES = 20 * 1024 * 1024
MAX_ITEMS = 5000
IMPORT_HINT_FIELDS = frozenset({"suggested_publication"})


class ImportRejected(ValueError):
    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report


class _DryRun(Exception):
    def __init__(self, report):
        super().__init__("dry-run rollback")
        self.report = report


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def digest_of(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def package_digest(items) -> str:
    """Отпечаток пакета как есть (до проверки: NaN и прочий мусор не должны ронять отчёт)."""
    text = json.dumps(items, ensure_ascii=False, sort_keys=True, allow_nan=True, default=repr,
                      separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _reject_constant(value):
    raise ValueError("NaN/Infinity")


def load_package(path) -> dict:
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_PACKAGE_BYTES:
        raise ImportRejected(f"Пакет больше {MAX_PACKAGE_BYTES // (1024 * 1024)} МиБ.")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise ImportRejected(f"Пакет не является корректным JSON: {exc.__class__.__name__}.")


def describe_package(package, source=None) -> dict:
    """Проверка оболочки пакета; возвращает {items, source, slice_version, demo}."""
    slice_info = {}
    if isinstance(package, list):
        items = package
        if not source:
            raise ImportRejected("Для списка без оболочки укажите --source.")
    elif isinstance(package, dict):
        if package.get("schema_version") != SCHEMA_VERSION:
            raise ImportRejected("schema_version пакета должен быть civic-v1.")
        if package.get("city") != CITY:
            raise ImportRejected("Пакет не для Астаны (city должен быть astana).")
        items = package.get("items")
        slice_info = package.get("slice") if isinstance(package.get("slice"), dict) else {}
    else:
        raise ImportRejected("Пакет — JSON-объект с items или список объектов.")
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ImportRejected(f"items — список не длиннее {MAX_ITEMS}.")
    demo = slice_info.get("demo") is True
    if source is None:
        source = slice_info.get("source") or ("r05-astana-demo" if demo else "r05-astana-real")
    if not isinstance(source, str) or not ID_RE.match(source):
        raise ImportRejected("source: латиница/цифры/._- до 64 символов.")
    version = slice_info.get("version")
    return {"items": items, "source": source, "demo": demo,
            "slice_version": version if isinstance(version, str) else None}


def import_package(repo: ObjectRepository, package, *, source=None, dry_run=False,
                   allow_partial=False, actor_label="cli") -> dict:
    meta = describe_package(package, source)
    actor = Actor(kind="import", user_id=None, label=f"import:{meta['source']}:{actor_label}"[:120],
                  public_label="Импорт данных")
    report = {
        "dry_run": bool(dry_run), "source": meta["source"], "slice_version": meta["slice_version"],
        "demo": meta["demo"], "package_digest": package_digest(meta["items"]),
        "status": None, "counts": {}, "items": [], "missing": [],
    }
    reason = f"Импорт {meta['slice_version'] or meta['source']}"
    try:
        # Та же проверка, что у update: иначе первый импорт сохранял бы причину,
        # которую следующий импорт уже отверг бы целиком.
        reason = clean_reason(reason, required=True)
    except ValidationError:
        raise ImportRejected("slice.version пакета должен быть простым текстом (без HTML, ≤ 1000 символов).")
    today = repo.today()

    # Проверка без базы: недопустимые записи не доходят до транзакции.
    prepared, seen = [], set()
    for index, raw in enumerate(meta["items"]):
        external_id = raw.get("id") if isinstance(raw, dict) else None
        entry = {"index": index, "external_id": external_id if isinstance(external_id, str) else None}
        try:
            if not isinstance(raw, dict):
                raise ValidationError({"item": "Объект civic-v1."})
            if not is_valid_id(external_id):
                raise ValidationError({"id": "Стабильный id записи пакета обязателен."})
            if external_id in seen:
                raise ValidationError({"id": "id повторяется в пакете."})
            seen.add(external_id)
            if raw.get("city", CITY) != CITY:
                raise ValidationError({"city": "Только astana."})
            payload = {key: value for key, value in raw.items() if key not in IMPORT_HINT_FIELDS}
            content_raw, _, ignored = split_payload(payload, allow_internal=False)
            content = validate_content(content_raw, today=today)
            # id/city/schema_version — опознавательные поля пакета; остальное серверное
            # (publication, revision...) не применяется, и отчёт это показывает.
            ignored = [key for key in ignored if key not in ("id", "city", "schema_version")]
            if ignored:
                entry["ignored_fields"] = ignored
            if meta["demo"] and content["evidence_type"] != "synthetic":
                raise ValidationError({"evidence_type": "Демо-срез содержит только synthetic."})
            if not meta["demo"] and content["evidence_type"] == "synthetic":
                raise ValidationError({"evidence_type": "Синтетика не импортируется как реальный срез."})
            prepared.append((entry, content, digest_of(content)))
        except ValidationError as exc:
            entry.update({"action": "invalid", "fields": exc.fields})
            report["items"].append(entry)
        except (TypeError, ValueError, UnicodeError, RecursionError):
            # Мусор в записи (нехэшируемые id, суррогаты...) — недопустимая запись, а не падение импорта.
            entry.update({"action": "invalid", "fields": {"item": "Запись не является корректным объектом civic-v1."}})
            report["items"].append(entry)
    invalid = len(report["items"])
    rejected = bool(invalid and not allow_partial)
    if rejected and not dry_run:
        report["status"] = "rejected"
        report["counts"] = {"invalid": invalid, "valid": len(prepared)}
        raise ImportRejected("Пакет содержит недопустимые записи; ничего не импортировано.", report)

    try:
        with repo.db.write() as conn:
            duplicates = _DuplicateIndex(conn, meta["source"]) if prepared else None
            for entry, content, digest in prepared:
                entry.update(_apply_one(repo, conn, actor, meta["source"], entry["external_id"], content,
                                        digest, reason))
                if entry["action"] in ("create", "id_conflict"):
                    found = duplicates.find(content, exclude=entry["object_id"])
                    if found:
                        entry["possible_duplicates"] = found
                if entry["action"] in ("create", "update_import_draft"):
                    duplicates.add(entry["object_id"], meta["source"], content)
                report["items"].append(entry)
            present = {entry["external_id"] for entry, _, _ in prepared}
            for row in conn.execute(
                    "SELECT id, import_external_id, publication FROM civic_objects WHERE import_source = ?",
                    (meta["source"],)):
                if row["import_external_id"] not in present:
                    report["missing"].append({"external_id": row["import_external_id"],
                                              "object_id": row["id"], "publication": row["publication"],
                                              "action": "report_missing"})
            report["items"].sort(key=lambda item: item["index"])
            counts = {}
            for item in report["items"]:
                counts[item["action"]] = counts.get(item["action"], 0) + 1
            counts["report_missing"] = len(report["missing"])
            report["counts"] = counts
            report["status"] = "rejected" if rejected else ("dry_run" if dry_run else "applied")
            if rejected:
                report["counts"]["valid"] = len(prepared)
            candidates = [(entry, entry.pop("_candidate", None)) for entry in report["items"]]
            if dry_run:
                raise _DryRun(report)
            conn.execute(
                "INSERT INTO civic_imports(source, package_digest, at, actor_label, report_json) VALUES (?, ?, ?, ?, ?)",
                (meta["source"], report["package_digest"], iso(utc_now(repo.clock)), actor.label,
                 _canonical(report)))
            import_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for entry, candidate in candidates:
                if candidate:
                    conn.execute(
                        """INSERT OR IGNORE INTO civic_import_candidates(import_id, object_id, source,
                               external_id, digest, data_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (import_id, entry["object_id"], meta["source"], entry["external_id"],
                         candidate["digest"], _canonical(candidate["content"]), iso(utc_now(repo.clock))))
    except _DryRun as dry:
        if rejected:
            raise ImportRejected("Пакет содержит недопустимые записи; ничего не импортировано "
                                 "(dry-run показал и допустимые записи).", dry.report)
        return dry.report
    return report


def _norm_title(text) -> str:
    return " ".join(str(text or "").casefold().replace("ё", "е").split())


class _DuplicateIndex:
    """Подсказка редактору о возможных дублях: тот же URL источника или то же kind+название.

    Сравниваются объекты ДРУГОГО происхождения (ручные, другой source): внутри одного source
    стабильный external_id и так исключает повторное создание.
    """

    def __init__(self, conn, source):
        self.source = source
        self.by_url, self.by_title = {}, {}
        for row in conn.execute("SELECT id, import_source, data_json FROM civic_objects"):
            self.add(row["id"], row["import_source"], json.loads(row["data_json"]))

    def add(self, object_id, source, content):
        for ref in content.get("source_refs") or []:
            if ref.get("url"):
                self.by_url.setdefault(ref["url"], []).append((object_id, source))
        key = (content.get("kind"), _norm_title(content.get("title")))
        self.by_title.setdefault(key, []).append((object_id, source))

    def find(self, content, *, exclude) -> list[dict]:
        hits = {}
        for ref in content.get("source_refs") or []:
            for object_id, source in self.by_url.get(ref.get("url"), []):
                hits.setdefault(object_id, (source, set()))[1].add("source_url")
        for object_id, source in self.by_title.get((content.get("kind"), _norm_title(content.get("title"))), []):
            hits.setdefault(object_id, (source, set()))[1].add("kind_title")
        return [{"object_id": object_id, "import_source": source, "match": sorted(match)}
                for object_id, (source, match) in sorted(hits.items())
                if object_id != exclude and source != self.source][:5]


def _ref_summary(refs) -> dict:
    return {ref["id"]: ref for ref in refs or []}


def source_refs_change(before, after) -> dict | None:
    """Какие ссылки на источники добавлены/убраны/изменены (по id ссылки)."""
    old, new = _ref_summary(before), _ref_summary(after)
    out = {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
           "changed": {ref_id: sorted(key for key in set(old[ref_id]) | set(new[ref_id])
                                      if old[ref_id].get(key) != new[ref_id].get(key))
                       for ref_id in sorted(set(old) & set(new)) if old[ref_id] != new[ref_id]}}
    return out if any(out.values()) else None


def last_imported_content(conn, row) -> dict | None:
    """Содержимое последней принятой версии источника (отпечаток import_digest)."""
    target = row["import_digest"]
    if target is None:
        return None
    cand = conn.execute(
        "SELECT data_json FROM civic_import_candidates WHERE object_id = ? AND digest = ? ORDER BY id DESC LIMIT 1",
        (row["id"], target)).fetchone()
    if cand is not None:
        return json.loads(cand["data_json"])
    for hist in conn.execute("SELECT snapshot_json FROM civic_history WHERE object_id = ? ORDER BY revision DESC",
                             (row["id"],)):
        content = json.loads(hist["snapshot_json"]).get("content")
        if content is not None and digest_of(content) == target:
            return content
    return None


def _change_details(conn, row, content) -> dict:
    current = json.loads(row["data_json"])
    details = {"changed_fields": sorted(diff(current, content))}
    imported = last_imported_content(conn, row)
    if imported is not None:
        details["source_changed_fields"] = sorted(diff(imported, content))
        refs = source_refs_change(imported.get("source_refs"), content.get("source_refs"))
        if refs:
            details["source_refs_change"] = refs
    return details


def _apply_one(repo, conn, actor, source, external_id, content, digest, reason) -> dict:
    row = conn.execute("SELECT * FROM civic_objects WHERE import_source = ? AND import_external_id = ?",
                       (source, external_id)).fetchone()
    if row is None:
        taken = conn.execute("SELECT import_source FROM civic_objects WHERE id = ?", (external_id,)).fetchone()
        if taken is not None:
            # ID занят ручной записью или другим источником: ничего не трогаем.
            return {"action": "id_conflict", "object_id": external_id,
                    "detail": "id уже занят объектом другого происхождения"}
        repo.create(actor, content, conn=conn,
                    import_meta={"object_id": external_id, "source": source, "external_id": external_id,
                                 "digest": digest, "reason": reason})
        return {"action": "create", "object_id": external_id}
    if row["import_digest"] == digest:
        return {"action": "skip_unchanged", "object_id": row["id"]}
    untouched = (row["publication"] == "draft" and row["first_published_at"] is None
                 and row["import_revision"] == row["revision"])
    if untouched:
        details = _change_details(conn, row, content)
        repo.update(actor, row["id"], expected_revision=row["revision"], changes=content,
                    reason=reason, conn=conn, import_meta={"digest": digest})
        return {"action": "update_import_draft", "object_id": row["id"], **details}
    if json.loads(row["data_json"]) == content:
        # Редактор уже привёл объект к этой версии вручную: запоминаем отпечаток, кандидаты закрываем.
        conn.execute("UPDATE civic_objects SET import_digest = ? WHERE id = ?", (digest, row["id"]))
        conn.execute(
            """UPDATE civic_import_candidates SET resolved_at = ?, resolution = 'superseded'
               WHERE object_id = ? AND digest = ? AND resolved_at IS NULL""",
            (iso(utc_now(repo.clock)), row["id"], digest))
        return {"action": "skip_unchanged", "object_id": row["id"], "detail": "совпадает с правкой редактора"}
    previous = conn.execute(
        "SELECT resolution FROM civic_import_candidates WHERE source = ? AND external_id = ? AND digest = ?",
        (source, external_id, digest)).fetchone()
    if previous is None:
        detail, candidate = ("объект изменён редактором или опубликован; новая версия ждёт решения",
                             {"digest": digest, "content": content})
    elif previous["resolution"] is None:
        detail, candidate = "изменение уже ждёт редактора", None
    else:
        detail, candidate = f"эта версия уже рассмотрена редактором ({previous['resolution']})", None
    return {"action": "editor_review", "object_id": row["id"], "detail": detail, "_candidate": candidate,
            **_change_details(conn, row, content)}
