"""Хранилище «Встреч с акимом» (R13, раунд 15): таблицы mt_* в той же SQLite, что у шлюза R01.

Что храним (CONTRACT §5.7):
  mt_meetings      — встреча акима района с жителями: район, название ru/kk, начало (UTC), длительность, место
                     (цель §4 + точка), «Приду» демо-основой, итог встречи ru/kk, отмена. Ведущий — «аким района»
                     без имени: имени в базе нет вообще.
  mt_registrations — «Приду»: (встреча, хэш устройства) — одно устройство, один раз. Наружу — только число.
  mt_orders        — поручение после встречи: текст ru/kk, служба (id CONTRACT §3), срок (дата по Астане), статус
                     todo → in_progress → done, связь с обращением / работой / проектом.
  mt_order_log     — журнал поручений: что поменяли и когда; кто — роль («сотрудник»), логин только для акимата.
  mt_meta          — версия схемы и соль для хэша устройства (случайная, создаётся один раз).

Вопросы к встрече хранятся в «Вопросе акиму» (ui/civic_qa, таблица qa_questions, поле meeting_id) — та же
модерация, голоса и ответы. Здесь их нет.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import sqlite3
import threading

SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS mt_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mt_meetings (
    id TEXT PRIMARY KEY,
    district TEXT NOT NULL,
    title_ru TEXT NOT NULL,
    title_kk TEXT,
    at TEXT NOT NULL,
    duration_min INTEGER NOT NULL DEFAULT 90,
    place_kind TEXT,
    place_id TEXT,
    place_label_ru TEXT,
    place_label_kk TEXT,
    lon REAL,
    lat REAL,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'cancelled')),
    base_registered INTEGER NOT NULL DEFAULT 0,
    result_ru TEXT,
    result_kk TEXT,
    result_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS mt_meetings_at ON mt_meetings (at);
CREATE INDEX IF NOT EXISTS mt_meetings_district ON mt_meetings (district, at);
CREATE TABLE IF NOT EXISTS mt_registrations (
    meeting_id TEXT NOT NULL,
    device_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (meeting_id, device_hash)
);
CREATE INDEX IF NOT EXISTS mt_registrations_device ON mt_registrations (device_hash);
CREATE TABLE IF NOT EXISTS mt_orders (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    text_ru TEXT NOT NULL,
    text_kk TEXT,
    service TEXT NOT NULL,
    due TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    link_kind TEXT,
    link_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    done_at TEXT,
    created_by TEXT,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS mt_orders_meeting ON mt_orders (meeting_id, position);
CREATE TABLE IF NOT EXISTS mt_order_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    by_role TEXT NOT NULL,
    by_user TEXT
);
CREATE INDEX IF NOT EXISTS mt_order_log_at ON mt_order_log (at);
CREATE INDEX IF NOT EXISTS mt_order_log_meeting ON mt_order_log (meeting_id, at);
"""

# «Приду» = демо-основа (как будто отметились раньше, без выдуманных устройств — R15 S20) + строки устройств.
_REGISTERED = "(m.base_registered + (SELECT COUNT(*) FROM mt_registrations r WHERE r.meeting_id = m.id))"
_MEETING_COLUMNS = ("m.id, m.district, m.title_ru, m.title_kk, m.at, m.duration_min, m.place_kind, m.place_id, "
                    "m.place_label_ru, m.place_label_kk, m.lon, m.lat, m.status, m.result_ru, m.result_kk, "
                    "m.result_at, m.created_at, m.updated_at, m.demo")
_ORDER_COLUMNS = ("id, meeting_id, position, text_ru, text_kk, service, due, status, link_kind, link_id, created_at, "
                  "updated_at, done_at, demo")
ORDER_STATUSES = ("todo", "in_progress", "done")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    """ISO 8601 с поясом (или «Z») -> datetime в UTC. Без пояса — считаем временем Астаны (UTC+5)."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone(timedelta(hours=5)))
    return moment.astimezone(timezone.utc)


class Conflict(Exception):
    """Действие не подходит к состоянию встречи (уже прошла, отменена…) — ответ 409."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class MeetingStore:
    """Доступ к таблицам mt_*. Безопасен для потоков сервера: запись — под блокировкой, соединение на вызов."""

    def __init__(self, db_path: str, clock=utc_now):
        self.db_path = str(db_path)
        self.clock = clock
        self._write = threading.Lock()
        with self._read() as conn:
            conn.executescript(SCHEMA)
        with self._tx() as conn:
            conn.execute("INSERT OR IGNORE INTO mt_meta (key, value) VALUES ('device_salt', ?)",
                         (secrets.token_hex(16),))
            conn.execute("INSERT OR IGNORE INTO mt_meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))
            self._salt = conn.execute("SELECT value FROM mt_meta WHERE key = 'device_salt'").fetchone()[0]

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
        """Запись одной транзакцией (BEGIN IMMEDIATE): проверка и вставка не разрываются другим потоком."""
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

    def device_hash(self, device_id: str) -> str:
        return hashlib.sha256(f"birge-meetings:{self._salt}:{device_id}".encode()).hexdigest()

    # ------------------------------------------------------------------ встречи
    def create_meeting(self, fields: dict, actor: str | None, *, meeting_id: str | None = None,
                       demo: bool = False, base_registered: int = 0) -> dict:
        now = iso(self.now())
        mid = meeting_id or "m-" + secrets.token_hex(5)
        place = fields.get("place") or {}
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO mt_meetings (id, district, title_ru, title_kk, at, duration_min, place_kind, place_id, "
                "place_label_ru, place_label_kk, lon, lat, base_registered, created_at, updated_at, created_by, demo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (mid, fields["district"], fields["title_ru"], fields.get("title_kk"), fields["at"],
                 int(fields.get("duration_min") or 90), place.get("kind"), place.get("id"), place.get("label_ru"),
                 place.get("label_kk"), *(fields.get("point") or (None, None)), int(base_registered), now, now,
                 actor, int(bool(demo))))
        return self.get_meeting(mid)

    def update_meeting(self, meeting_id: str, fields: dict) -> dict:
        """Правка сотрудника: время, место, название, отмена. Прошедшую встречу (есть итог) не переносим."""
        columns = {"district": "district", "title_ru": "title_ru", "title_kk": "title_kk", "at": "at",
                   "duration_min": "duration_min", "status": "status"}
        sets, args = [], []
        for key, column in columns.items():
            if key in fields:
                sets.append(f"{column} = ?")
                args.append(fields[key])
        if "place" in fields:
            place = fields["place"] or {}
            for column in ("kind", "id", "label_ru", "label_kk"):
                sets.append(f"place_{column} = ?")
                args.append(place.get(column))
        if "point" in fields:
            lon, lat = fields["point"] or (None, None)
            sets += ["lon = ?", "lat = ?"]
            args += [lon, lat]
        with self._tx() as conn:
            row = conn.execute("SELECT result_at FROM mt_meetings WHERE id = ?", (meeting_id,)).fetchone()
            if row is None:
                raise LookupError(meeting_id)
            if row["result_at"] and ("at" in fields or fields.get("status") == "cancelled"):
                raise Conflict("held", "Итог встречи уже опубликован — её нельзя перенести или отменить.")
            if sets:
                sets.append("updated_at = ?")
                args.append(iso(self.now()))
                conn.execute(f"UPDATE mt_meetings SET {', '.join(sets)} WHERE id = ?", (*args, meeting_id))
        return self.get_meeting(meeting_id)

    def set_result(self, meeting_id: str, result_ru: str | None, result_kk: str | None) -> dict:
        """Итог встречи (ru и/или kk). Повтор правит текст; время первого итога сохраняется."""
        with self._tx() as conn:
            row = conn.execute("SELECT at, status, result_ru, result_kk, result_at FROM mt_meetings WHERE id = ?",
                               (meeting_id,)).fetchone()
            if row is None:
                raise LookupError(meeting_id)
            if row["status"] == "cancelled":
                raise Conflict("cancelled", "Встреча отменена.")
            started = parse_iso(row["at"])
            if started is not None and started > self.now():
                raise Conflict("not_started", "Итог можно написать, когда встреча начнётся.")
            new_ru = result_ru if result_ru is not None else row["result_ru"]
            new_kk = result_kk if result_kk is not None else row["result_kk"]
            now = iso(self.now())
            conn.execute("UPDATE mt_meetings SET result_ru = ?, result_kk = ?, result_at = COALESCE(result_at, ?), "
                         "updated_at = ? WHERE id = ?", (new_ru, new_kk, now, now, meeting_id))
        return self.get_meeting(meeting_id)

    def get_meeting(self, meeting_id: str) -> dict:
        with self._read() as conn:
            row = conn.execute(f"SELECT {_MEETING_COLUMNS}, {_REGISTERED} AS registered FROM mt_meetings m "
                               "WHERE m.id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise LookupError(meeting_id)
        return dict(row)

    def list_meetings(self, *, district: str | None = None, when: str = "all", limit: int = 50) -> list[dict]:
        """when: upcoming (ещё не закончились, ближайшие первыми), past (закончились, свежие первыми), all."""
        where, args = [], []
        if district:
            where.append("m.district = ?")
            args.append(district)
        now = iso(self.now())
        # Конец встречи = начало + длительность; считаем в SQL через julianday, чтобы «идёт сейчас» было в upcoming.
        end_sql = "datetime(m.at, '+' || m.duration_min || ' minutes')"
        if when == "upcoming":
            where.append(f"strftime('%Y-%m-%dT%H:%M:%SZ', {end_sql}) > ? AND m.status = 'scheduled'")
            args.append(now)
            order = "m.at ASC, m.id ASC"
        elif when == "past":
            where.append(f"(strftime('%Y-%m-%dT%H:%M:%SZ', {end_sql}) <= ? OR m.status = 'cancelled')")
            args.append(now)
            order = "m.at DESC, m.id DESC"
        else:
            order = "m.at DESC, m.id DESC"
        sql = (f"SELECT {_MEETING_COLUMNS}, {_REGISTERED} AS registered FROM mt_meetings m "
               f"{'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY {order} LIMIT ?")
        with self._read() as conn:
            return [dict(r) for r in conn.execute(sql, (*args, int(limit))).fetchall()]

    # ------------------------------------------------------------------ «Приду»
    def register(self, meeting_id: str, device_id: str, going: bool = True, *, max_per_day: int = 30) -> dict:
        """«Приду» (going=True) или «Не смогу» (False) до начала встречи. Повтор не меняет число.

        max_per_day — сколько изменений «Приду» в сутки с одного устройства (против накрутки нажатиями;
        лимиты по адресу клиента ставит шлюз R01).
        """
        dev = self.device_hash(device_id)
        now = self.now()
        with self._tx() as conn:
            row = conn.execute("SELECT at, status FROM mt_meetings WHERE id = ?", (meeting_id,)).fetchone()
            if row is None:
                raise LookupError(meeting_id)
            if row["status"] == "cancelled":
                raise Conflict("cancelled", "Встреча отменена.")
            started = parse_iso(row["at"])
            if started is not None and started <= now:
                raise Conflict("started", "Встреча уже началась — отметка «Приду» закрыта.")
            exists = conn.execute("SELECT created_at FROM mt_registrations WHERE meeting_id = ? AND device_hash = ?",
                                  (meeting_id, dev)).fetchone()
            changed = False
            if going and exists is None:
                recent = conn.execute("SELECT COUNT(*) FROM mt_registrations WHERE device_hash = ? AND created_at >= ?",
                                      (dev, iso(now - timedelta(days=1)))).fetchone()[0]
                if recent >= max_per_day:
                    raise Conflict("too_many", "Слишком много отметок с этого устройства. Попробуйте завтра.")
                conn.execute("INSERT INTO mt_registrations (meeting_id, device_hash, created_at) VALUES (?, ?, ?)",
                             (meeting_id, dev, iso(now)))
                changed = True
            elif not going and exists is not None:
                conn.execute("DELETE FROM mt_registrations WHERE meeting_id = ? AND device_hash = ?", (meeting_id, dev))
                changed = True
            count = conn.execute(f"SELECT {_REGISTERED} FROM mt_meetings m WHERE m.id = ?", (meeting_id,)).fetchone()[0]
        return {"id": meeting_id, "registered": int(count), "my_registration": bool(going), "changed": changed}

    def registered_by(self, meeting_ids: list[str], device_id: str | None) -> set[str]:
        """На какие встречи из списка это устройство нажало «Приду»."""
        if not device_id or not meeting_ids:
            return set()
        dev = self.device_hash(device_id)
        marks = ",".join("?" * len(meeting_ids))
        with self._read() as conn:
            rows = conn.execute(f"SELECT meeting_id FROM mt_registrations WHERE device_hash = ? AND meeting_id IN "
                                f"({marks})", (dev, *meeting_ids)).fetchall()
        return {r[0] for r in rows}

    def meetings_of_device(self, device_id: str) -> list[str]:
        """Все встречи, где устройство нажало «Приду» (для ленты уведомлений)."""
        dev = self.device_hash(device_id)
        with self._read() as conn:
            return [r[0] for r in conn.execute("SELECT meeting_id FROM mt_registrations WHERE device_hash = ?", (dev,))]

    # ------------------------------------------------------------------ поручения
    def add_order(self, meeting_id: str, fields: dict, actor: str | None, *, order_id: str | None = None,
                  demo: bool = False, status: str = "todo", created_at: str | None = None,
                  done_at: str | None = None) -> dict:
        now = iso(self.now())
        oid = order_id or "o-" + secrets.token_hex(5)
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM mt_meetings WHERE id = ?", (meeting_id,)).fetchone()
            if row is None:
                raise LookupError(meeting_id)
            if row["status"] == "cancelled":
                raise Conflict("cancelled", "Встреча отменена.")
            position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM mt_orders WHERE meeting_id = ?",
                                    (meeting_id,)).fetchone()[0]
            link = fields.get("link") or {}
            stamp = created_at or now
            conn.execute(
                "INSERT INTO mt_orders (id, meeting_id, position, text_ru, text_kk, service, due, status, link_kind, "
                "link_id, created_at, updated_at, done_at, created_by, demo) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, meeting_id, position, fields["text_ru"], fields.get("text_kk"), fields["service"],
                 fields["due"], status, link.get("kind"), link.get("id"), stamp, done_at or stamp,
                 done_at if status == "done" else None, actor, int(bool(demo))))
            conn.execute("INSERT INTO mt_order_log (order_id, meeting_id, at, action, from_status, to_status, by_role, "
                         "by_user) VALUES (?, ?, ?, 'created', NULL, ?, 'staff', ?)",
                         (oid, meeting_id, stamp, status, actor))
            if status != "todo" and done_at:
                conn.execute("INSERT INTO mt_order_log (order_id, meeting_id, at, action, from_status, to_status, "
                             "by_role, by_user) VALUES (?, ?, ?, 'status', 'todo', ?, 'staff', ?)",
                             (oid, meeting_id, done_at, status, actor))
        return self.get_order(oid)

    def update_order(self, meeting_id: str, order_id: str, fields: dict, actor: str | None) -> dict:
        """Статус, срок, связь, текст. Каждая смена статуса — строка журнала (для ленты жителей и истории)."""
        now = iso(self.now())
        with self._tx() as conn:
            row = conn.execute(f"SELECT {_ORDER_COLUMNS} FROM mt_orders WHERE id = ? AND meeting_id = ?",
                               (order_id, meeting_id)).fetchone()
            if row is None:
                raise LookupError(order_id)
            sets, args = [], []
            for key in ("text_ru", "text_kk", "service", "due"):
                if key in fields:
                    sets.append(f"{key} = ?")
                    args.append(fields[key])
            if "link" in fields:
                link = fields["link"] or {}
                sets += ["link_kind = ?", "link_id = ?"]
                args += [link.get("kind"), link.get("id")]
            status = fields.get("status")
            if status is not None and status != row["status"]:
                sets.append("status = ?")
                args.append(status)
                sets.append("done_at = ?")
                args.append(now if status == "done" else None)
                conn.execute("INSERT INTO mt_order_log (order_id, meeting_id, at, action, from_status, to_status, "
                             "by_role, by_user) VALUES (?, ?, ?, 'status', ?, ?, 'staff', ?)",
                             (order_id, meeting_id, now, row["status"], status, actor))
            elif "link" in fields or "due" in fields or "text_ru" in fields or "text_kk" in fields or "service" in fields:
                conn.execute("INSERT INTO mt_order_log (order_id, meeting_id, at, action, from_status, to_status, "
                             "by_role, by_user) VALUES (?, ?, ?, 'edit', ?, ?, 'staff', ?)",
                             (order_id, meeting_id, now, row["status"], row["status"], actor))
            if sets:
                sets.append("updated_at = ?")
                args.append(now)
                conn.execute(f"UPDATE mt_orders SET {', '.join(sets)} WHERE id = ?", (*args, order_id))
        return self.get_order(order_id)

    def get_order(self, order_id: str) -> dict:
        with self._read() as conn:
            row = conn.execute(f"SELECT {_ORDER_COLUMNS} FROM mt_orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise LookupError(order_id)
        return dict(row)

    def orders(self, meeting_ids: list[str]) -> dict[str, list[dict]]:
        """Поручения встреч: {meeting_id: [поручения по порядку]}."""
        out: dict[str, list[dict]] = {mid: [] for mid in meeting_ids}
        if not meeting_ids:
            return out
        marks = ",".join("?" * len(meeting_ids))
        with self._read() as conn:
            for row in conn.execute(f"SELECT {_ORDER_COLUMNS} FROM mt_orders WHERE meeting_id IN ({marks}) "
                                    "ORDER BY meeting_id, position, id", meeting_ids):
                out.setdefault(row["meeting_id"], []).append(dict(row))
        return out

    def all_orders(self, *, district: str | None = None) -> list[dict]:
        """Все поручения неотменённых встреч (для «Картины дня» R08 и аналитика R03)."""
        sql = (f"SELECT o.{_ORDER_COLUMNS.replace(', ', ', o.')}, m.district, m.title_ru AS meeting_title_ru, "
               "m.title_kk AS meeting_title_kk, m.at AS meeting_at, m.demo AS meeting_demo FROM mt_orders o "
               "JOIN mt_meetings m ON m.id = o.meeting_id WHERE m.status = 'scheduled'")
        args: list = []
        if district:
            sql += " AND m.district = ?"
            args.append(district)
        sql += " ORDER BY o.due ASC, o.id ASC"
        with self._read() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def order_log(self, meeting_ids: list[str], since: str | None) -> list[dict]:
        """Смены статуса поручений этих встреч после since (для ленты: «Поручение выполнено»)."""
        if not meeting_ids:
            return []
        marks = ",".join("?" * len(meeting_ids))
        sql = (f"SELECT l.id, l.order_id, l.meeting_id, l.at, l.action, l.from_status, l.to_status, o.text_ru, "
               f"o.text_kk, o.service FROM mt_order_log l JOIN mt_orders o ON o.id = l.order_id "
               f"WHERE l.meeting_id IN ({marks}) AND l.action = 'status'")
        args: list = list(meeting_ids)
        if since:
            sql += " AND l.at > ?"
            args.append(since)
        sql += " ORDER BY l.at ASC, l.id ASC"
        with self._read() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    # ------------------------------------------------------------------ засев
    def seed(self, meetings: list[dict], orders: list[dict]) -> tuple[int, int]:
        """Демо-набор: вставка по постоянным id; повтор ничего не дублирует и не трогает правки сотрудника."""
        inserted = skipped = 0
        with self._tx() as conn:
            for m in meetings:
                place = m.get("place") or {}
                point = m.get("point") or (None, None)
                cur = conn.execute(
                    "INSERT OR IGNORE INTO mt_meetings (id, district, title_ru, title_kk, at, duration_min, place_kind, "
                    "place_id, place_label_ru, place_label_kk, lon, lat, status, base_registered, result_ru, "
                    "result_kk, result_at, created_at, updated_at, demo) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (m["id"], m["district"], m["title_ru"], m.get("title_kk"), m["at"], int(m.get("duration_min") or 90),
                     place.get("kind"), place.get("id"), place.get("label_ru"), place.get("label_kk"), point[0],
                     point[1], m.get("status") or "scheduled", int(m.get("base_registered") or 0), m.get("result_ru"),
                     m.get("result_kk"), m.get("result_at"), m["created_at"], m["created_at"],
                     int(bool(m.get("demo", True)))))
                inserted += cur.rowcount
                skipped += 1 - cur.rowcount
            for position, o in enumerate(orders, start=1):
                link = o.get("link") or {}
                cur = conn.execute(
                    "INSERT OR IGNORE INTO mt_orders (id, meeting_id, position, text_ru, text_kk, service, due, status, "
                    "link_kind, link_id, created_at, updated_at, done_at, demo) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (o["id"], o["meeting_id"], int(o.get("position") or position), o["text_ru"], o.get("text_kk"),
                     o["service"], o["due"], o["status"], link.get("kind"), link.get("id"), o["created_at"],
                     o.get("updated_at") or o["created_at"], o.get("done_at"), int(bool(o.get("demo", True)))))
                if cur.rowcount:
                    inserted += 1
                    conn.execute("INSERT INTO mt_order_log (order_id, meeting_id, at, action, from_status, to_status, "
                                 "by_role) VALUES (?, ?, ?, 'created', NULL, 'todo', 'staff')",
                                 (o["id"], o["meeting_id"], o["created_at"]))
                    if o["status"] != "todo":
                        conn.execute("INSERT INTO mt_order_log (order_id, meeting_id, at, action, from_status, "
                                     "to_status, by_role) VALUES (?, ?, ?, 'status', 'todo', ?, 'staff')",
                                     (o["id"], o["meeting_id"], o.get("updated_at") or o["created_at"], o["status"]))
                else:
                    skipped += 1
        return inserted, skipped
