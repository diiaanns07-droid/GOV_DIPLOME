"""Репозиторий объектов civic-v1: черновик → публикация → архив с историей.

Каждая операция записи — одна транзакция BEGIN IMMEDIATE: строка объекта,
публичная проекция и запись истории сохраняются вместе или не сохраняются вовсе.
Конкурентные правки отсекаются expected_revision (HTTP 409).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import secrets

from . import dto
from .db import Database
from .validate import (CONTENT_FIELDS, KINDS, PUBLICATIONS, STATUSES, ValidationError,
                       clean_internal_notes, clean_reason, diff, is_valid_id, merge_content,
                       parse_date, split_payload, validate_content, validate_for_publication)


ASTANA_TZ = timezone(timedelta(hours=5), "Asia/Almaty")
DEFAULT_PAGE = 50
MAX_PAGE = 100
MAX_FILTER_VALUES = 10


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    def __init__(self, message: str, current_revision: int | None = None):
        super().__init__(message)
        self.current_revision = current_revision


class BadRequest(ValueError):
    def __init__(self, message: str, fields: dict | None = None):
        super().__init__(message)
        self.fields = fields or {}


@dataclass(frozen=True)
class Actor:
    """Кто меняет данные. Берётся только из серверной сессии или CLI, не из body."""
    kind: str               # editor | import | system
    user_id: int | None
    label: str              # служебная подпись (логин), видна только редакторам
    public_label: str       # подпись в публичной истории


def utc_now(clock) -> datetime:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":"))


def _loads(text):
    return json.loads(text) if text is not None else None


def encode_cursor(updated_at: str, object_id: str) -> str:
    raw = _dumps([updated_at, object_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str):
    try:
        if not isinstance(cursor, str) or len(cursor) > 200:
            raise ValueError
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if (not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], str)
                or len(value[0]) > 40 or not is_valid_id(value[1])):
            raise ValueError
        return value[0], value[1]
    except (ValueError, UnicodeError, TypeError):
        raise BadRequest("Недопустимый cursor.", {"cursor": "Используйте next_cursor из ответа."})


def parse_filters(query: dict, *, staff: bool) -> dict:
    """kind/status/(publication)/from/to/cursor/limit из query (значения — списки строк)."""
    def values(name, allowed):
        raw = [part.strip() for item in query.get(name, []) for part in item.split(",") if part.strip()]
        if len(raw) > MAX_FILTER_VALUES or any(value not in allowed for value in raw):
            raise BadRequest("Недопустимый фильтр.", {name: "Допустимо: " + ", ".join(allowed)})
        return sorted(set(raw))

    def single(name):
        items = query.get(name, [])
        if len(items) > 1:
            raise BadRequest("Параметр указан несколько раз.", {name: "Один раз."})
        return items[0] if items else None

    filters = {"kind": values("kind", KINDS), "status": values("status", STATUSES),
               "publication": values("publication", PUBLICATIONS) if staff else []}
    for name in ("from", "to"):
        value = single(name)
        if value is not None and parse_date(value) is None:
            raise BadRequest("Недопустимая дата фильтра.", {name: "YYYY-MM-DD"})
        filters[name] = value
    if filters["from"] and filters["to"] and filters["from"] > filters["to"]:
        raise BadRequest("from позже to.", {"from": "from ≤ to"})
    cursor = single("cursor")
    filters["cursor"] = decode_cursor(cursor) if cursor else None
    limit = single("limit")
    if limit is None:
        filters["limit"] = DEFAULT_PAGE
    else:
        if not limit.isdigit() or not 1 <= int(limit) <= MAX_PAGE:
            raise BadRequest("Недопустимый limit.", {"limit": f"Целое 1–{MAX_PAGE}."})
        filters["limit"] = int(limit)
    return filters


def _filter_sql(filters: dict, *, staff: bool):
    where, params = [], []
    for name in ("kind", "status") + (("publication",) if staff else ()):
        if filters[name]:
            where.append(f"{name} IN ({','.join('?' * len(filters[name]))})")
            params.extend(filters[name])
    if filters["from"] or filters["to"]:
        # Сопоставляем известные planned_start/current_planned_end; статус из дат не выводим.
        where.append("NOT (planned_start IS NULL AND current_planned_end IS NULL)")
        if filters["to"]:
            where.append("(planned_start IS NULL OR planned_start <= ?)")
            params.append(filters["to"])
        if filters["from"]:
            where.append("(current_planned_end IS NULL OR current_planned_end >= ?)")
            params.append(filters["from"])
    if filters["cursor"]:
        where.append("(updated_at, id) < (?, ?)")
        params.extend(filters["cursor"])
    return (" WHERE " + " AND ".join(where)) if where else "", params


class ObjectRepository:
    def __init__(self, database: Database, clock):
        self.db = database
        self.clock = clock

    # --- служебное -------------------------------------------------------------

    def today(self):
        return utc_now(self.clock).astimezone(ASTANA_TZ).date()

    @staticmethod
    def _content(row) -> dict:
        return _loads(row["data_json"])

    @staticmethod
    def _last_public_dto(conn, object_id):
        row = conn.execute(
            """SELECT public_dto_json FROM civic_history
               WHERE object_id = ? AND action = 'publish' ORDER BY revision DESC LIMIT 1""",
            (object_id,)).fetchone()
        return _loads(row["public_dto_json"]) if row else None

    def _locked_row(self, conn, object_id, expected_revision):
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        if (isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
                or expected_revision < 1):
            raise ValidationError({"expected_revision": "Целое число ≥ 1 из последней карточки."})
        row = conn.execute("SELECT * FROM civic_objects WHERE id = ?", (object_id,)).fetchone()
        if row is None:
            raise NotFound(object_id)
        if row["revision"] != expected_revision:
            raise Conflict("Объект уже изменён другим редактором: обновите карточку.",
                           row["revision"])
        return row

    def _write_object(self, conn, object_id, content, *, publication, revision, now, actor,
                      internal_notes, insert=False, extra=None):
        values = {
            "kind": content["kind"], "status": content["status"], "publication": publication,
            "planned_start": content["schedule"]["planned_start"],
            "current_planned_end": content["schedule"]["current_planned_end"],
            "data_json": _dumps({key: content[key] for key in CONTENT_FIELDS}),
            "internal_notes": internal_notes, "revision": revision, "updated_at": now,
            "updated_by": actor.user_id, **(extra or {}),
        }
        if insert:
            values.update({"id": object_id, "city": "astana", "created_at": now,
                           "created_by": actor.user_id})
            columns = ", ".join(values)
            conn.execute(f"INSERT INTO civic_objects({columns}) VALUES ({', '.join('?' * len(values))})",
                         tuple(values.values()))
        else:
            assignments = ", ".join(f"{key} = ?" for key in values)
            cursor = conn.execute(
                f"UPDATE civic_objects SET {assignments} WHERE id = ? AND revision = ?",
                (*values.values(), object_id, revision - 1))
            if cursor.rowcount != 1:  # не должно случиться под BEGIN IMMEDIATE
                raise Conflict("Объект изменён параллельно.", None)

    @staticmethod
    def _history(conn, object_id, *, revision, now, action, publication, changes, reason, actor,
                 snapshot, is_public=False, public_fields=None, public_item=None):
        conn.execute(
            """INSERT INTO civic_history(object_id, revision, at, action, publication,
                   changed_fields_json, diff_json, reason, actor_kind, actor_user_id, actor_label,
                   public_actor_label, is_public, public_changed_fields_json, public_dto_json,
                   snapshot_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (object_id, revision, now, action, publication, _dumps(sorted(changes)), _dumps(changes),
             reason, actor.kind, actor.user_id, actor.label, actor.public_label, int(is_public),
             _dumps(public_fields) if public_fields is not None else None,
             _dumps(public_item) if public_item is not None else None, _dumps(snapshot)))

    # --- запись -----------------------------------------------------------------

    def create(self, actor: Actor, payload, *, request_key: str | None = None,
               import_meta: dict | None = None, conn=None) -> tuple[dict, list[str], bool]:
        """Создаёт черновик. Возвращает (staff item, ignored fields, created?)."""
        content_raw, internal, ignored = split_payload(payload)
        content = validate_content(content_raw, today=self.today())
        notes = clean_internal_notes(internal) if internal is not ... else ""
        if conn is None:
            with self.db.write() as conn:
                return self._create(conn, actor, content, notes, ignored, request_key, import_meta)
        return self._create(conn, actor, content, notes, ignored, request_key, import_meta)

    def _create(self, conn, actor, content, notes, ignored, request_key, import_meta):
        if request_key and actor.user_id is not None:
            existing = conn.execute(
                "SELECT object_id FROM civic_create_requests WHERE user_id = ? AND request_key = ?",
                (actor.user_id, request_key)).fetchone()
            if existing:
                return self._staff_item(conn, existing["object_id"]), ignored, False
        now = iso(utc_now(self.clock))
        if import_meta:
            object_id = import_meta["object_id"]
        else:
            object_id = None
            for _ in range(8):
                candidate = "ast-" + secrets.token_hex(5)
                if not conn.execute("SELECT 1 FROM civic_objects WHERE id = ?", (candidate,)).fetchone():
                    object_id = candidate
                    break
            if object_id is None:
                raise RuntimeError("Не удалось выделить ID")
        extra = {}
        if import_meta:
            extra = {"import_source": import_meta["source"],
                     "import_external_id": import_meta["external_id"],
                     "import_digest": import_meta["digest"], "import_revision": 1}
        self._write_object(conn, object_id, content, publication="draft", revision=1, now=now,
                           actor=actor, internal_notes=notes, insert=True, extra=extra)
        changes = diff(None, content)
        if notes:
            changes["internal_notes"] = {"before": None, "after": notes}
        self._history(conn, object_id, revision=1, now=now,
                      action="import_create" if import_meta else "create", publication="draft",
                      changes=changes, reason=import_meta.get("reason", "") if import_meta else "",
                      actor=actor, snapshot={"content": content, "internal_notes": notes})
        if request_key and actor.user_id is not None:
            conn.execute("INSERT INTO civic_create_requests(user_id, request_key, object_id, created_at) "
                         "VALUES (?, ?, ?, ?)", (actor.user_id, request_key, object_id, now))
        return self._staff_item(conn, object_id), ignored, True

    def update(self, actor: Actor, object_id, *, expected_revision, changes, reason,
               conn=None, import_meta=None) -> tuple[dict, list[str]]:
        if not isinstance(changes, dict) or not changes:
            raise ValidationError({"changes": "Передайте объект changes хотя бы с одним полем."})
        content_changes, internal, ignored = split_payload(changes)
        if conn is None:
            with self.db.write() as conn:
                return self._update(conn, actor, object_id, expected_revision, content_changes,
                                    internal, ignored, reason, import_meta)
        return self._update(conn, actor, object_id, expected_revision, content_changes, internal,
                            ignored, reason, import_meta)

    def _update(self, conn, actor, object_id, expected_revision, content_changes, internal,
                ignored, reason, import_meta):
        row = self._locked_row(conn, object_id, expected_revision)
        current = self._content(row)
        content = validate_content(merge_content(current, content_changes), today=self.today())
        notes = row["internal_notes"] if internal is ... else clean_internal_notes(internal)
        was_published = row["first_published_at"] is not None
        reason_text = clean_reason(reason, required=was_published)
        changes = diff(current, content)
        if was_published and "schedule.original_planned_end" in changes:
            raise ValidationError({"schedule.original_planned_end":
                                   "Первоначальный срок зафиксирован после первой публикации; "
                                   "меняйте current_planned_end с причиной."})
        if notes != row["internal_notes"]:
            changes["internal_notes"] = {"before": row["internal_notes"], "after": notes}
        if not changes:
            return self._staff_item(conn, object_id), ignored
        revision = row["revision"] + 1
        now = iso(utc_now(self.clock))
        extra = {}
        if import_meta:
            extra = {"import_digest": import_meta["digest"], "import_revision": revision}
        self._write_object(conn, object_id, content, publication=row["publication"],
                           revision=revision, now=now, actor=actor, internal_notes=notes, extra=extra)
        self._history(conn, object_id, revision=revision, now=now,
                      action="import_update" if import_meta else "update",
                      publication=row["publication"], changes=changes, reason=reason_text,
                      actor=actor, snapshot={"content": content, "internal_notes": notes})
        return self._staff_item(conn, object_id), ignored

    def publish(self, actor: Actor, object_id, *, expected_revision, reason) -> dict:
        with self.db.write() as conn:
            row = self._locked_row(conn, object_id, expected_revision)
            reason_text = clean_reason(reason, required=True)
            content = self._content(row)
            validate_for_publication(content)
            previous = self._last_public_dto(conn, object_id)
            first = row["first_published_at"] is None
            changes = {}
            schedule = content["schedule"]
            if schedule["original_planned_end"] is None and schedule["current_planned_end"] is not None \
                    and (first or (previous and previous["schedule"]["original_planned_end"] is None)):
                # Первый публичный срок становится исходным; дальше он не меняется.
                changes["schedule.original_planned_end"] = {"before": None,
                                                            "after": schedule["current_planned_end"]}
                schedule["original_planned_end"] = schedule["current_planned_end"]
            public_changes = diff(dto.content_of(previous), content) if previous else {}
            if row["publication"] == "published" and not public_changes and not changes:
                return self._staff_item(conn, object_id)  # публиковать нечего
            public_fields = sorted(set(public_changes) | set(changes))
            if row["publication"] != "published":
                public_fields = sorted(set(public_fields) | {"publication"})
            changes.update(public_changes)
            changes["publication"] = {"before": row["publication"], "after": "published"}
            revision = row["revision"] + 1
            now = iso(utc_now(self.clock))
            item = dto.public_dto(object_id, content, publication="published", revision=revision,
                                  updated_at=now)
            self._write_object(conn, object_id, content, publication="published", revision=revision,
                               now=now, actor=actor, internal_notes=row["internal_notes"],
                               extra={"first_published_at": row["first_published_at"] or now,
                                      "published_revision": revision})
            conn.execute(
                """INSERT INTO civic_public_objects(id, kind, status, planned_start,
                       current_planned_end, revision, updated_at, dto_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, status = excluded.status,
                       planned_start = excluded.planned_start,
                       current_planned_end = excluded.current_planned_end,
                       revision = excluded.revision, updated_at = excluded.updated_at,
                       dto_json = excluded.dto_json""",
                (object_id, content["kind"], content["status"], schedule["planned_start"],
                 schedule["current_planned_end"], revision, now, _dumps(item)))
            self._history(conn, object_id, revision=revision, now=now, action="publish",
                          publication="published", changes=changes, reason=reason_text, actor=actor,
                          snapshot={"content": content, "internal_notes": row["internal_notes"]},
                          is_public=True, public_fields=public_fields, public_item=item)
            return self._staff_item(conn, object_id)

    def archive(self, actor: Actor, object_id, *, expected_revision, reason) -> dict:
        with self.db.write() as conn:
            row = self._locked_row(conn, object_id, expected_revision)
            reason_text = clean_reason(reason, required=True)
            if row["publication"] == "archived":
                return self._staff_item(conn, object_id)
            was_public = row["publication"] == "published"
            content = self._content(row)
            revision = row["revision"] + 1
            now = iso(utc_now(self.clock))
            self._write_object(conn, object_id, content, publication="archived", revision=revision,
                               now=now, actor=actor, internal_notes=row["internal_notes"])
            # Проекция — не история: строка убирается, все ревизии остаются в civic_history.
            conn.execute("DELETE FROM civic_public_objects WHERE id = ?", (object_id,))
            self._history(conn, object_id, revision=revision, now=now, action="archive",
                          publication="archived",
                          changes={"publication": {"before": row["publication"], "after": "archived"}},
                          reason=reason_text, actor=actor,
                          snapshot={"content": content, "internal_notes": row["internal_notes"]},
                          is_public=was_public, public_fields=["publication"] if was_public else None)
            return self._staff_item(conn, object_id)

    # --- чтение -----------------------------------------------------------------

    def _staff_item(self, conn, object_id) -> dict:
        row = conn.execute(
            """SELECT o.*, cu.username AS created_by_name, uu.username AS updated_by_name
               FROM civic_objects o
               LEFT JOIN civic_users cu ON cu.id = o.created_by
               LEFT JOIN civic_users uu ON uu.id = o.updated_by
               WHERE o.id = ?""", (object_id,)).fetchone()
        if row is None:
            raise NotFound(object_id)
        content = self._content(row)
        item = dto.public_dto(row["id"], content, publication=row["publication"],
                              revision=row["revision"], updated_at=row["updated_at"])
        published = conn.execute("SELECT dto_json FROM civic_public_objects WHERE id = ?",
                                 (object_id,)).fetchone()
        published_item = _loads(published["dto_json"]) if published else None
        pending = conn.execute("SELECT COUNT(*) FROM civic_import_candidates WHERE object_id = ?",
                               (object_id,)).fetchone()[0]
        item["internal_notes"] = row["internal_notes"]
        item["staff"] = {
            "created_at": row["created_at"],
            "created_by": row["created_by_name"],
            "updated_by": row["updated_by_name"],
            "first_published_at": row["first_published_at"],
            "published_revision": row["published_revision"] if published_item else None,
            "has_unpublished_changes": bool(
                published_item is None or dto.content_of(published_item) != content),
            "public_item": published_item,
            "original_planned_end_locked": row["first_published_at"] is not None,
            "import": ({"source": row["import_source"], "external_id": row["import_external_id"]}
                       if row["import_source"] else None),
            "pending_import_candidates": pending,
        }
        return item

    def get_staff(self, object_id) -> dict:
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        with self.db.read() as conn:
            item = self._staff_item(conn, object_id)
            rows = conn.execute(
                "SELECT * FROM civic_history WHERE object_id = ? ORDER BY revision", (object_id,)).fetchall()
            history = [{
                "id": r["id"], "object_id": r["object_id"], "revision": r["revision"], "at": r["at"],
                "action": r["action"], "publication": r["publication"],
                "changed_fields": _loads(r["changed_fields_json"]), "diff": _loads(r["diff_json"]),
                "reason": r["reason"], "actor_kind": r["actor_kind"], "actor_label": r["actor_label"],
                "public_actor_label": r["public_actor_label"], "is_public": bool(r["is_public"]),
            } for r in rows]
            return {"item": item, "history": history}

    def get_public(self, object_id) -> dict:
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        with self.db.read() as conn:
            row = conn.execute("SELECT dto_json FROM civic_public_objects WHERE id = ?",
                               (object_id,)).fetchone()
            if row is None:
                raise NotFound(object_id)  # черновик/архив неотличимы от отсутствия
            rows = conn.execute(
                """SELECT id, object_id, revision, at, reason, public_actor_label,
                          public_changed_fields_json
                   FROM civic_history WHERE object_id = ? AND is_public = 1 ORDER BY revision""",
                (object_id,)).fetchall()
            history = [dto.public_history_entry({
                "id": r["id"], "object_id": r["object_id"], "revision": r["revision"], "at": r["at"],
                "changed_fields": _loads(r["public_changed_fields_json"]) or [],
                "reason": r["reason"], "public_actor_label": r["public_actor_label"]}) for r in rows]
            return {"item": dto.sanitize_public(_loads(row["dto_json"])), "history": history}

    def list_public(self, filters: dict) -> dict:
        where, params = _filter_sql(filters, staff=False)
        with self.db.read() as conn:
            rows = conn.execute(
                f"""SELECT id, updated_at, planned_start, current_planned_end, dto_json
                    FROM civic_public_objects{where} ORDER BY updated_at DESC, id DESC LIMIT ?""",
                (*params, filters["limit"] + 1)).fetchall()
        return self._page(rows, filters, lambda r: dto.sanitize_public(_loads(r["dto_json"])))

    def list_staff(self, filters: dict) -> dict:
        where, params = _filter_sql(filters, staff=True)
        with self.db.read() as conn:
            rows = conn.execute(
                f"""SELECT id, updated_at, planned_start, current_planned_end
                    FROM civic_objects{where} ORDER BY updated_at DESC, id DESC LIMIT ?""",
                (*params, filters["limit"] + 1)).fetchall()
            page = self._page(rows, filters, lambda r: self._staff_item(conn, r["id"]))
        return page

    @staticmethod
    def _page(rows, filters, render) -> dict:
        has_more = len(rows) > filters["limit"]
        rows = rows[:filters["limit"]]
        data = {"items": [render(row) for row in rows],
                "next_cursor": encode_cursor(rows[-1]["updated_at"], rows[-1]["id"]) if has_more else None}
        if filters["from"] or filters["to"]:
            data["date_filter"] = {
                "from": filters["from"], "to": filters["to"],
                "basis": "planned_start/current_planned_end; статус по датам не вычисляется",
                "incomplete_interval_ids": [row["id"] for row in rows if row["planned_start"] is None
                                            or row["current_planned_end"] is None],
            }
        return data
