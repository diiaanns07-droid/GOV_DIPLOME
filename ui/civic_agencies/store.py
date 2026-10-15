"""Хранилище кризисного штаба R17: таблицы agency_* в той же SQLite, что у шлюза R01 (рядом с таблицами R09, R13).

Таблицы:
  agency_meta              — версия схемы (устройства жителей R17 не хранит вовсе);
  agency_incidents         — кризис (CONTRACT §5.5): вид, названия ru/kk, зона, статус, итог, demo;
  agency_incident_tasks    — задачи служб (чек-лист): служба, текст ru/kk, todo → doing → done; ВНУТРЕННИЕ (жителям не отдаются);
  agency_incident_updates  — обновления ru/kk: public = жителям зоны, иначе заметка штаба; пометка модерации R04;
  agency_journal           — журнал действий штаба: что сделано и РОЛЬ (operator/editor/admin), без имени сотрудника (§10).
Миграция: CREATE IF NOT EXISTS + добавление новых колонок через ALTER (старые строки не теряются); версия — agency_meta.
Чужие таблицы (жалобы R09 и др.) этот модуль не трогает.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import secrets
import sqlite3
import threading

ASTANA = timezone(timedelta(hours=5))
SCHEMA_VERSION = "r17-agencies-1"
INCIDENT_KINDS = ("blizzard", "heat_outage", "water_outage", "flood", "other")
TASK_STATUSES = ("todo", "doing", "done")
MAX_TASKS = 30
MAX_UPDATES = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS agency_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agency_incidents (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    title_kk TEXT NOT NULL,
    zone_json TEXT NOT NULL,
    district TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'closed')),
    started_at TEXT NOT NULL,
    closed_at TEXT,
    result_ru TEXT,
    result_kk TEXT,
    demo INTEGER NOT NULL DEFAULT 0,
    seed_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS agency_incidents_status ON agency_incidents (status, started_at);
CREATE TABLE IF NOT EXISTS agency_incident_tasks (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    service TEXT NOT NULL,
    text_ru TEXT NOT NULL,
    text_kk TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('todo', 'doing', 'done')),
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS agency_tasks_incident ON agency_incident_tasks (incident_id, position);
CREATE TABLE IF NOT EXISTS agency_incident_updates (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    incident_id TEXT NOT NULL,
    at TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'update',
    text_ru TEXT,
    text_kk TEXT,
    public INTEGER NOT NULL DEFAULT 1,
    moderation_json TEXT,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS agency_updates_incident ON agency_incident_updates (incident_id, seq);
CREATE INDEX IF NOT EXISTS agency_updates_time ON agency_incident_updates (at);
CREATE TABLE IF NOT EXISTS agency_journal (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    incident_id TEXT,
    action TEXT NOT NULL,
    by_role TEXT NOT NULL,
    detail_json TEXT
);
CREATE INDEX IF NOT EXISTS agency_journal_incident ON agency_journal (incident_id, seq);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    """Время по Астане (+05:00), без долей секунды — как записи R09 (CONTRACT §5)."""
    return moment.astimezone(ASTANA).replace(microsecond=0).isoformat()


def parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA)


class NotFound(LookupError):
    pass


class Conflict(Exception):
    """Действие не подходит к состоянию записи (кризис закрыт, задачу уже изменили…) — ответ 409."""

    def __init__(self, code: str, message: str, current=None):
        super().__init__(message)
        self.code, self.message, self.current = code, message, current


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5)}"


class AgencyStore:
    """Доступ к таблицам agency_*. Безопасен для потоков сервера: запись под блокировкой, соединение на вызов."""

    def __init__(self, db_path: str, clock=utc_now):
        self.db_path = str(db_path)
        self.clock = clock
        self._write = threading.Lock()
        with self._tx() as conn:
            conn.executescript(SCHEMA)
            conn.execute("INSERT OR REPLACE INTO agency_meta (key, value) VALUES ('schema', ?)", (SCHEMA_VERSION,))

    # ------------------------------------------------------------------ соединения
    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def _read(self):
        conn = self._open()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _tx(self):
        """Запись одной транзакцией (BEGIN IMMEDIATE): проверка состояния и запись не разрываются другим потоком."""
        with self._write:
            conn = self._open()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def now(self) -> datetime:
        return self.clock()

    # ------------------------------------------------------------------ чтение
    @staticmethod
    def _incident_row(row) -> dict:
        return {
            "id": row["id"], "kind": row["kind"], "title_ru": row["title_ru"], "title_kk": row["title_kk"],
            "zone": json.loads(row["zone_json"]), "district": row["district"], "status": row["status"],
            "started_at": row["started_at"], "closed_at": row["closed_at"],
            "result": ({"text_ru": row["result_ru"], "text_kk": row["result_kk"]}
                       if row["status"] == "closed" else None),
            "demo": bool(row["demo"]), "updated_at": row["updated_at"], "revision": row["revision"],
        }

    def _load(self, conn, incident_id: str) -> dict:
        row = conn.execute("SELECT * FROM agency_incidents WHERE id = ?", (incident_id,)).fetchone()
        if row is None:
            raise NotFound(incident_id)
        incident = self._incident_row(row)
        incident["tasks"] = [dict(r) for r in conn.execute(
            "SELECT id, service, text_ru, text_kk, status, updated_at FROM agency_incident_tasks "
            "WHERE incident_id = ? ORDER BY position, created_at", (incident_id,))]
        incident["updates"] = [self._update_row(r) for r in conn.execute(
            "SELECT * FROM agency_incident_updates WHERE incident_id = ? ORDER BY seq DESC", (incident_id,))]
        return incident

    @staticmethod
    def _update_row(row) -> dict:
        return {"id": row["id"], "seq": row["seq"], "at": row["at"], "kind": row["kind"], "text_ru": row["text_ru"],
                "text_kk": row["text_kk"], "public": bool(row["public"]),
                "moderation": json.loads(row["moderation_json"]) if row["moderation_json"] else None,
                "demo": bool(row["demo"])}

    def get(self, incident_id: str) -> dict:
        with self._read() as conn:
            return self._load(conn, incident_id)

    def list(self, *, status: str | None = None, district: str | None = None, limit: int = 50) -> list[dict]:
        where, args = [], []
        if status in ("active", "closed"):
            where.append("status = ?")
            args.append(status)
        if district:
            # Район зоны или район, где лежат цели зоны (district пишется при создании).
            where.append("district = ?")
            args.append(district)
        sql = "SELECT id FROM agency_incidents"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, started_at DESC LIMIT ?"
        with self._read() as conn:
            ids = [r["id"] for r in conn.execute(sql, args + [max(1, min(int(limit), 200))])]
            return [self._load(conn, i) for i in ids]

    def journal(self, incident_id: str, limit: int = 100) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute("SELECT at, action, by_role, detail_json FROM agency_journal WHERE incident_id = ? "
                                "ORDER BY seq DESC LIMIT ?", (incident_id, max(1, min(int(limit), 500)))).fetchall()
        return [{"at": r["at"], "action": r["action"], "by_role": r["by_role"],
                 "detail": json.loads(r["detail_json"]) if r["detail_json"] else None} for r in rows]

    def public_updates_since(self, since: str | None, *, limit: int = 50) -> list[dict]:
        """Публичные обновления (новые сверху) вместе с их кризисом — для ленты жителя R06 и incidents/updates."""
        args: list = []
        sql = ("SELECT u.*, i.kind AS incident_kind, i.title_ru AS incident_title_ru, i.title_kk AS incident_title_kk, "
               "i.zone_json, i.district AS incident_district, i.status AS incident_status, i.demo AS incident_demo "
               "FROM agency_incident_updates u JOIN agency_incidents i ON i.id = u.incident_id WHERE u.public = 1")
        moment = parse_iso(since)
        rows = []
        with self._read() as conn:
            for row in conn.execute(sql + " ORDER BY u.seq DESC LIMIT ?", args + [2000]):
                at = parse_iso(row["at"])
                if moment is not None and at is not None and at <= moment:
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    break
        out = []
        for row in rows:
            item = self._update_row(row)
            item.update({"incident_id": row["incident_id"], "incident_kind": row["incident_kind"],
                         "incident_title_ru": row["incident_title_ru"], "incident_title_kk": row["incident_title_kk"],
                         "zone": json.loads(row["zone_json"]), "district": row["incident_district"],
                         "incident_status": row["incident_status"], "incident_demo": bool(row["incident_demo"])})
            out.append(item)
        return out

    # ------------------------------------------------------------------ запись
    def _journal(self, conn, at: str, incident_id: str | None, action: str, by_role: str, detail=None) -> None:
        conn.execute("INSERT INTO agency_journal (at, incident_id, action, by_role, detail_json) VALUES (?,?,?,?,?)",
                     (at, incident_id, action, str(by_role or "staff")[:32],
                      json.dumps(detail, ensure_ascii=False) if detail else None))

    def _touch(self, conn, incident_id: str, at: str) -> None:
        conn.execute("UPDATE agency_incidents SET updated_at = ?, revision = revision + 1 WHERE id = ?", (at, incident_id))

    def create(self, *, kind: str, title_ru: str, title_kk: str, zone: dict, district: str | None, tasks: list[dict],
               by_role: str, started_at: str | None = None, demo: bool = False, seed_key: str | None = None,
               incident_id: str | None = None, status: str = "active", closed_at: str | None = None,
               result: dict | None = None, updates: list[dict] | None = None) -> tuple[dict, bool]:
        """Новый кризис с задачами. seed_key — для идемпотентного засева (повтор → (тот же кризис, False))."""
        now = iso(self.now())
        with self._tx() as conn:
            if seed_key:
                row = conn.execute("SELECT id FROM agency_incidents WHERE seed_key = ?", (seed_key,)).fetchone()
                if row is not None:
                    return self._load(conn, row["id"]), False
            iid = incident_id or new_id("inc")
            if conn.execute("SELECT 1 FROM agency_incidents WHERE id = ?", (iid,)).fetchone():
                return self._load(conn, iid), False
            conn.execute(
                "INSERT INTO agency_incidents (id, kind, title_ru, title_kk, zone_json, district, status, started_at, "
                "closed_at, result_ru, result_kk, demo, seed_key, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (iid, kind, title_ru, title_kk, json.dumps(zone, ensure_ascii=False), district, status,
                 started_at or now, closed_at, (result or {}).get("text_ru"), (result or {}).get("text_kk"),
                 1 if demo else 0, seed_key, now, now))
            for position, task in enumerate(tasks[:MAX_TASKS]):
                conn.execute("INSERT INTO agency_incident_tasks (id, incident_id, service, text_ru, text_kk, status, "
                             "position, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                             (task.get("id") or new_id("t"), iid, task["service"], task["text_ru"], task["text_kk"],
                              task.get("status", "todo"), position, now, task.get("updated_at") or now))
            for update in updates or []:
                conn.execute("INSERT INTO agency_incident_updates (id, incident_id, at, kind, text_ru, text_kk, public, "
                             "moderation_json, demo) VALUES (?,?,?,?,?,?,?,?,?)",
                             (update.get("id") or new_id("u"), iid, update.get("at") or now, update.get("kind", "update"),
                              update.get("text_ru"), update.get("text_kk"), 1 if update.get("public", True) else 0,
                              json.dumps(update["moderation"], ensure_ascii=False) if update.get("moderation") else None,
                              1 if demo else 0))
            self._journal(conn, now, iid, "incident.create", by_role, {"kind": kind, "tasks": len(tasks)})
            return self._load(conn, iid), True

    def _active(self, conn, incident_id: str) -> dict:
        row = conn.execute("SELECT status, demo FROM agency_incidents WHERE id = ?", (incident_id,)).fetchone()
        if row is None:
            raise NotFound(incident_id)
        if row["status"] != "active":
            raise Conflict("closed", "Кризис уже закрыт: изменения не принимаются.")
        return dict(row)

    def add_task(self, incident_id: str, *, service: str, text_ru: str, text_kk: str, by_role: str) -> dict:
        now = iso(self.now())
        with self._tx() as conn:
            self._active(conn, incident_id)
            count = conn.execute("SELECT COUNT(*) FROM agency_incident_tasks WHERE incident_id = ?",
                                 (incident_id,)).fetchone()[0]
            if count >= MAX_TASKS:
                raise Conflict("too_many_tasks", f"Не больше {MAX_TASKS} задач в одном кризисе.")
            tid = new_id("t")
            conn.execute("INSERT INTO agency_incident_tasks (id, incident_id, service, text_ru, text_kk, status, position, "
                         "created_at, updated_at) VALUES (?,?,?,?,?,'todo',?,?,?)",
                         (tid, incident_id, service, text_ru, text_kk, count, now, now))
            self._touch(conn, incident_id, now)
            self._journal(conn, now, incident_id, "task.add", by_role, {"task": tid, "service": service})
            return self._load(conn, incident_id)

    def set_task(self, incident_id: str, task_id: str, *, status: str, by_role: str,
                 expected: str | None = None) -> dict:
        now = iso(self.now())
        with self._tx() as conn:
            self._active(conn, incident_id)
            row = conn.execute("SELECT status, service FROM agency_incident_tasks WHERE id = ? AND incident_id = ?",
                               (task_id, incident_id)).fetchone()
            if row is None:
                raise NotFound(task_id)
            if expected is not None and row["status"] != expected:
                raise Conflict("stale", "Задачу уже изменили. Обновите штаб.", row["status"])
            if row["status"] == status:
                return self._load(conn, incident_id)
            conn.execute("UPDATE agency_incident_tasks SET status = ?, updated_at = ? WHERE id = ?", (status, now, task_id))
            self._touch(conn, incident_id, now)
            self._journal(conn, now, incident_id, "task.status", by_role,
                          {"task": task_id, "service": row["service"], "from": row["status"], "to": status})
            return self._load(conn, incident_id)

    def add_update(self, incident_id: str, *, text_ru: str | None, text_kk: str | None, public: bool, by_role: str,
                   moderation: dict | None = None, kind: str = "update") -> dict:
        now = iso(self.now())
        with self._tx() as conn:
            state = self._active(conn, incident_id)
            count = conn.execute("SELECT COUNT(*) FROM agency_incident_updates WHERE incident_id = ?",
                                 (incident_id,)).fetchone()[0]
            if count >= MAX_UPDATES:
                raise Conflict("too_many_updates", f"Не больше {MAX_UPDATES} обновлений в одном кризисе.")
            uid = new_id("u")
            conn.execute("INSERT INTO agency_incident_updates (id, incident_id, at, kind, text_ru, text_kk, public, "
                         "moderation_json, demo) VALUES (?,?,?,?,?,?,?,?,?)",
                         (uid, incident_id, now, kind, text_ru, text_kk, 1 if public else 0,
                          json.dumps(moderation, ensure_ascii=False) if moderation else None, state["demo"]))
            self._touch(conn, incident_id, now)
            self._journal(conn, now, incident_id, "update.add", by_role, {"update": uid, "public": bool(public)})
            return self._load(conn, incident_id)

    def close(self, incident_id: str, *, result_ru: str, result_kk: str, by_role: str,
              moderation: dict | None = None) -> dict:
        now = iso(self.now())
        with self._tx() as conn:
            state = self._active(conn, incident_id)
            conn.execute("UPDATE agency_incidents SET status = 'closed', closed_at = ?, result_ru = ?, result_kk = ?, "
                         "updated_at = ?, revision = revision + 1 WHERE id = ?",
                         (now, result_ru, result_kk, now, incident_id))
            # Итог — последнее публичное обновление: жители зоны видят, что кризис закрыт и что сделано.
            conn.execute("INSERT INTO agency_incident_updates (id, incident_id, at, kind, text_ru, text_kk, public, "
                         "moderation_json, demo) VALUES (?,?,?,'closed',?,?,1,?,?)",
                         (new_id("u"), incident_id, now, result_ru, result_kk,
                          json.dumps(moderation, ensure_ascii=False) if moderation else None, state["demo"]))
            self._journal(conn, now, incident_id, "incident.close", by_role, None)
            return self._load(conn, incident_id)
