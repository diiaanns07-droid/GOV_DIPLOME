"""Хранилище жалоб v2 (SQLite, только стандартная библиотека).

Источник истины — JSON записи (record_json, ровно CONTRACT §5 + служебные поля).
Колонки рядом — индексы для выборок по bbox/дате/категории/цели; пишутся вместе с JSON в _save().

Функции для соседей (R07 тепловая карта, R08 «Картина дня», R01 маршруты):
  create, metoo, set_status, mark_duplicate, get, get_by_code, list, mine,
  target_summary, events_since, subscribe.
Все времена — ISO с +05:00. Устройство жителя хранится только как солёный хэш.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import categories
from . import record as rec
from .record import RecordError

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS complaint_meta_v2 (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaints_v2 (
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL UNIQUE,
  created_ts REAL NOT NULL,
  lon REAL NOT NULL,
  lat REAL NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  district TEXT,
  duplicate_of TEXT,
  demo INTEGER NOT NULL DEFAULT 0,
  device_hash TEXT,
  request_id TEXT,
  legacy_v1_id INTEGER UNIQUE,
  record_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS complaints_v2_request ON complaints_v2 (device_hash, request_id);
CREATE INDEX IF NOT EXISTS complaints_v2_place ON complaints_v2 (lon, lat);
CREATE INDEX IF NOT EXISTS complaints_v2_time ON complaints_v2 (created_ts);
CREATE INDEX IF NOT EXISTS complaints_v2_target ON complaints_v2 (target_id, status);
CREATE INDEX IF NOT EXISTS complaints_v2_device ON complaints_v2 (device_hash, created_ts);
CREATE TABLE IF NOT EXISTS complaint_metoo_v2 (
  complaint_id TEXT NOT NULL,
  device_hash TEXT NOT NULL,
  at TEXT NOT NULL,
  PRIMARY KEY (complaint_id, device_hash)
);
CREATE INDEX IF NOT EXISTS complaint_metoo_v2_device ON complaint_metoo_v2 (device_hash);
CREATE TABLE IF NOT EXISTS complaint_events_v2 (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  type TEXT NOT NULL,
  complaint_id TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  category TEXT NOT NULL,
  status TEXT NOT NULL,
  reporters INTEGER NOT NULL,
  demo INTEGER NOT NULL DEFAULT 0
);
"""

DEFAULT_LIMITS = {
    "creates_per_hour": 20,   # с одного устройства; защита от случайного «залипшего» повтора
    "list_max": 5000,
}


class LimitError(RecordError):
    def __init__(self, message: str, retry_after_s: int):
        super().__init__(message)
        self.retry_after_s = retry_after_s


class NotFound(RecordError):
    pass


class Conflict(RecordError):
    pass


class ComplaintStore:
    """Потокобезопасно: одно соединение под RLock (как FeedbackService v1)."""

    def __init__(self, db_path, *, clock: Callable[[], datetime] | None = None, limits: dict | None = None):
        self.clock = clock or (lambda: datetime.now(rec.ASTANA_TZ))
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self._lock = threading.RLock()
        self._listeners: list[Callable[[dict], None]] = []
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        categories.validate_response_days()
        with self._lock:
            self._db.executescript(SCHEMA_SQL)
            self._db.execute("INSERT OR REPLACE INTO complaint_meta_v2 (key, value) VALUES ('schema', ?)",
                             (rec.SCHEMA,))
            # Соль для хэша устройства живёт только в runtime-БД, не в Git.
            self._db.execute("INSERT OR IGNORE INTO complaint_meta_v2 (key, value) VALUES ('device_salt', ?)",
                             (secrets.token_hex(32),))
            self._salt = self._db.execute(
                "SELECT value FROM complaint_meta_v2 WHERE key = 'device_salt'").fetchone()[0].encode()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------ служебное
    def _now(self) -> datetime:
        moment = self.clock()
        return moment if moment.tzinfo else moment.replace(tzinfo=rec.ASTANA_TZ)

    def device_hash(self, device_id) -> str:
        if not isinstance(device_id, str) or not rec.DEVICE_ID.match(device_id):
            raise RecordError("Не удалось определить устройство. Обновите страницу.",
                              {"device_id": "16–80 символов: латиница, цифры, - и _"})
        return hashlib.sha256(self._salt + device_id.encode()).hexdigest()

    @contextmanager
    def _tx(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def _save(self, db, record: dict, *, device_hash=None, request_id=None, legacy_v1_id=None) -> None:
        """Вставить или обновить запись: JSON + индексные колонки одним оператором."""
        created = rec.parse_iso(record["created_at"])
        values = (record["id"], record["code"], created.timestamp(), record["point"][0], record["point"][1],
                  record["category"], record["status"], record["target"]["kind"], record["target"]["id"],
                  record.get("district"), record.get("duplicate_of"), 1 if record.get("demo") else 0,
                  json.dumps(record, ensure_ascii=False, sort_keys=True))
        exists = db.execute("SELECT 1 FROM complaints_v2 WHERE id = ?", (record["id"],)).fetchone()
        if exists:
            db.execute("UPDATE complaints_v2 SET code=?, created_ts=?, lon=?, lat=?, category=?, status=?, "
                       "target_kind=?, target_id=?, district=?, duplicate_of=?, demo=?, record_json=? "
                       "WHERE id = ?", values[1:] + (record["id"],))
        else:
            db.execute("INSERT INTO complaints_v2 (id, code, created_ts, lon, lat, category, status, target_kind, "
                       "target_id, district, duplicate_of, demo, record_json, device_hash, request_id, legacy_v1_id) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       values + (device_hash, request_id, legacy_v1_id))

    def _load(self, db, complaint_id) -> dict | None:
        row = db.execute("SELECT record_json FROM complaints_v2 WHERE id = ?", (complaint_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def _root(self, db, complaint_id: str) -> dict:
        """Запись, а если она дубль — исходная (цепочка duplicate_of, защита от петли)."""
        record = self._load(db, complaint_id)
        if record is None:
            raise NotFound("Обращение не найдено.", {"id": complaint_id})
        seen = {record["id"]}
        while record.get("duplicate_of"):
            parent = self._load(db, record["duplicate_of"])
            if parent is None or parent["id"] in seen:
                break
            seen.add(parent["id"])
            record = parent
        return record

    def _next_code(self, db) -> str:
        """Номер для жителя: B-0001, B-0002 … (коротко, легко продиктовать по телефону)."""
        row = db.execute("SELECT COALESCE(MAX(rowid), 0) + 1 FROM complaints_v2").fetchone()
        return f"B-{row[0]:04d}"

    def _event(self, db, kind: str, record: dict, at: str) -> dict:
        event = {"type": kind, "at": at, "complaint_id": record["id"], "target": {
                     "kind": record["target"]["kind"], "id": record["target"]["id"]},
                 "category": record["category"], "status": record["status"],
                 "reporters": rec.reporters(record), "demo": bool(record.get("demo"))}
        cur = db.execute("INSERT INTO complaint_events_v2 (at, type, complaint_id, target_kind, target_id, category, "
                         "status, reporters, demo) VALUES (?,?,?,?,?,?,?,?,?)",
                         (at, kind, record["id"], record["target"]["kind"], record["target"]["id"],
                          record["category"], record["status"], event["reporters"], 1 if event["demo"] else 0))
        event["seq"] = cur.lastrowid
        return event

    def _emit(self, events: list[dict]) -> None:
        # После COMMIT: подписчик (R07) не должен видеть событие, которого нет в БД.
        for event in events:
            for listener in list(self._listeners):
                try:
                    listener(dict(event))
                except Exception:  # чужой подписчик не ломает приём жалобы
                    pass

    def subscribe(self, listener: Callable[[dict], None]) -> Callable[[], None]:
        """Подписка на события created / metoo / status / duplicate. Возвращает функцию отписки."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def _recount_metoo(self, db, record: dict) -> None:
        record["metoo"] = db.execute("SELECT COUNT(*) FROM complaint_metoo_v2 WHERE complaint_id = ?",
                                     (record["id"],)).fetchone()[0]

    # ------------------------------------------------------------ создание
    def create(self, payload: dict, device_id: str, *, demo: bool = False) -> tuple[dict, bool]:
        """Новая жалоба. -> (запись, created). created=False — повтор того же request_id
        с того же устройства (слабая сеть): возвращается уже сохранённая запись, дубля нет."""
        if not isinstance(payload, dict):
            raise RecordError("Пустой запрос.")
        device = self.device_hash(device_id)
        request_id = payload.get("request_id")
        if request_id is not None and (not isinstance(request_id, str) or not rec.REQUEST_ID.match(request_id)):
            raise RecordError("Неверный номер запроса.", {"request_id": "8–64 символа: латиница, цифры, -"})
        text = rec.parse_text(payload.get("text"))
        category = payload.get("category")
        if not categories.is_category(category):
            raise RecordError("Выберите категорию.", {"category": "одна из 12 категорий"})
        source = payload.get("category_source", "resident")
        if source not in ("resident", "model"):
            source = "resident"
        point = rec.parse_point(payload.get("point"))
        # Жалоба всегда имеет цель: нет выбранной цели -> ячейка «примерное место».
        target = rec.parse_target(payload["target"]) if payload.get("target") is not None \
            else rec.cell_target(*point)
        district = payload.get("district")
        if district is not None and (not isinstance(district, str) or not rec.DISTRICT.match(district)):
            district = None
        lang = payload.get("lang")
        if lang not in ("ru", "kk", "mixed"):
            lang = rec.detect_lang(text)
        now = self._now()
        created_at = rec.iso(now)
        with self._tx() as db:
            if request_id:
                row = db.execute("SELECT record_json FROM complaints_v2 WHERE device_hash = ? AND request_id = ?",
                                 (device, request_id)).fetchone()
                if row:
                    return json.loads(row[0]), False
            hour_ago = (now - timedelta(hours=1)).timestamp()
            recent = db.execute("SELECT COUNT(*), MIN(created_ts) FROM complaints_v2 "
                                "WHERE device_hash = ? AND created_ts > ?", (device, hour_ago)).fetchone()
            if recent[0] >= self.limits["creates_per_hour"]:
                wait = int(recent[1] + 3600 - now.timestamp()) + 1
                raise LimitError("Слишком много обращений подряд. Повторите позже.", max(wait, 1))
            record = {
                "id": "c-" + secrets.token_hex(8),
                "code": self._next_code(db),
                "created_at": created_at,
                "text": text, "lang": lang,
                "category": category, "category_source": source,
                "model": rec.parse_model(payload.get("model")),
                "point": point, "target": target, "district": district,
                "status": "new",
                "status_history": [{"at": created_at, "status": "new"}],
                "metoo": 0, "duplicate_of": None, "demo": bool(demo),
                "due_at": rec.due_at(created_at, category),
                "schema": rec.SCHEMA,
            }
            self._save(db, record, device_hash=device, request_id=request_id)
            event = self._event(db, "created", record, created_at)
        self._emit([event])
        return record, True

    # ------------------------------------------------------------ «Я тоже»
    def metoo(self, complaint_id: str, device_id: str) -> tuple[dict, str]:
        """«Я тоже» — одно на устройство. -> (исходная запись, result):
        added | already (уже нажимал) | author (это его собственная жалоба).
        Новую запись не создаёт никогда; если нажали на дубль — засчитывается исходной."""
        device = self.device_hash(device_id)
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._root(db, complaint_id)
            author = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (record["id"],)).fetchone()[0]
            if author == device:
                return record, "author"
            cur = db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) "
                             "VALUES (?,?,?)", (record["id"], device, now))
            if cur.rowcount == 0:
                return record, "already"
            self._recount_metoo(db, record)
            self._save(db, record)
            event = self._event(db, "metoo", record, now)
        self._emit([event])
        return record, "added"

    # ------------------------------------------------------------ статус
    def set_status(self, complaint_id: str, status: str, *, actor: str | None = None,
                   note: str | None = None, expected: str | None = None) -> dict:
        """Смена статуса сотрудником. expected — статус, который сотрудник видел
        (защита от одновременной правки двумя людьми: иначе Conflict)."""
        if status not in rec.STATUSES:
            raise RecordError("Неизвестный статус.", {"status": ", ".join(rec.STATUSES)})
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._load(db, complaint_id)
            if record is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            if expected is not None and record["status"] != expected:
                raise Conflict("Статус уже изменили. Обновите карточку.", {"status": record["status"]})
            if status not in rec.TRANSITIONS[record["status"]]:
                raise RecordError("Такой переход статуса недоступен.",
                                  {"status": f"из «{record['status']}» можно: "
                                             + ", ".join(sorted(rec.TRANSITIONS[record['status']]))})
            entry = {"at": now, "status": status}
            if actor:
                entry["by"] = str(actor)[:80]
            if isinstance(note, str) and note.strip():
                entry["note"] = note.strip()[:500]
            record["status"] = status
            record["status_history"].append(entry)
            self._save(db, record)
            event = self._event(db, "status", record, now)
        self._emit([event])
        return record

    def mark_duplicate(self, complaint_id: str, original_id: str, *, actor: str | None = None) -> dict:
        """Сотрудник отмечает дубль: duplicate_of = исходная, люди дубля (автор и его «Я тоже»)
        переходят в «Я тоже» исходной — число «сообщили N человек» не теряется и не удваивается."""
        now = rec.iso(self._now())
        with self._tx() as db:
            duplicate = self._load(db, complaint_id)
            if duplicate is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            original = self._root(db, original_id)
            # Корень исходной = сам дубль -> получилась бы петля (A дубль B, B дубль A).
            if original["id"] == duplicate["id"]:
                raise Conflict("Нельзя отметить обращение дублем самого себя.")
            # Перепривязка дубля к другой исходной не поддерживается: его люди уже засчитаны там.
            if duplicate.get("duplicate_of"):
                raise Conflict("Обращение уже отмечено дублем.", {"duplicate_of": duplicate["duplicate_of"]})
            row = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (duplicate["id"],)).fetchone()
            original_author = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?",
                                         (original["id"],)).fetchone()[0]
            devices = [row[0]] + [r[0] for r in db.execute(
                "SELECT device_hash FROM complaint_metoo_v2 WHERE complaint_id = ?", (duplicate["id"],))]
            for device in devices:
                if device and device != original_author:
                    db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) "
                               "VALUES (?,?,?)", (original["id"], device, now))
            # Дубли, которые ссылались на этот, теперь ссылаются на исходную.
            for child in db.execute("SELECT id FROM complaints_v2 WHERE duplicate_of = ?",
                                    (duplicate["id"],)).fetchall():
                other = self._load(db, child[0])
                other["duplicate_of"] = original["id"]
                self._save(db, other)
            duplicate["duplicate_of"] = original["id"]
            entry = {"at": now, "status": duplicate["status"], "duplicate_of": original["id"]}
            if actor:
                entry["by"] = str(actor)[:80]
            duplicate["status_history"].append(entry)
            self._recount_metoo(db, original)
            self._save(db, duplicate)
            self._save(db, original)
            events = [self._event(db, "duplicate", duplicate, now), self._event(db, "metoo", original, now)]
        self._emit(events)
        return original

    # ------------------------------------------------------------ чтение
    def get(self, complaint_id: str) -> dict | None:
        with self._lock:
            return self._load(self._db, complaint_id)

    def get_by_code(self, code: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT record_json FROM complaints_v2 WHERE code = ?", (code,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, bbox=None, since=None, category=None, *, status=None, target_id=None,
             include_duplicates: bool = False, limit: int | None = None) -> list[dict]:
        """Записи (полные, для сервера/соседей; наружу — через record.public_view).
        bbox = (lon_min, lat_min, lon_max, lat_max); since — datetime или ISO; category — id или список."""
        where, args = [], []
        if bbox is not None:
            lon_min, lat_min, lon_max, lat_max = (float(v) for v in bbox)
            where.append("lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?")
            args += [lon_min, lon_max, lat_min, lat_max]
        if since is not None:
            moment = rec.parse_iso(since) if isinstance(since, str) else since
            if moment is None:
                raise RecordError("Неверная дата.", {"since": "ISO-дата"})
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=rec.ASTANA_TZ)
            where.append("created_ts >= ?")
            args.append(moment.timestamp())
        for column, value in (("category", category), ("status", status)):
            if value is None:
                continue
            values = [value] if isinstance(value, str) else list(value)
            where.append(f"{column} IN ({','.join('?' * len(values))})")
            args += values
        if target_id is not None:
            where.append("target_id = ?")
            args.append(target_id)
        if not include_duplicates:
            where.append("duplicate_of IS NULL")
        cap = min(int(limit or self.limits["list_max"]), self.limits["list_max"])
        sql = "SELECT record_json FROM complaints_v2"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_ts DESC, rowid DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(sql, args + [cap]).fetchall()
        return [json.loads(row[0]) for row in rows]

    def mine(self, device_id: str) -> list[dict]:
        """«Мои обращения»: созданные этим устройством и те, где оно нажало «Я тоже»."""
        device = self.device_hash(device_id)
        with self._lock:
            own = self._db.execute("SELECT record_json FROM complaints_v2 WHERE device_hash = ? "
                                   "ORDER BY created_ts DESC", (device,)).fetchall()
            joined = self._db.execute(
                "SELECT c.record_json, m.at FROM complaint_metoo_v2 m JOIN complaints_v2 c ON c.id = m.complaint_id "
                "WHERE m.device_hash = ? ORDER BY m.at DESC", (device,)).fetchall()
        result = []
        for row in own:
            item = json.loads(row[0])
            item["relation"] = "author"
            result.append(item)
        for row in joined:
            item = json.loads(row[0])
            item["relation"] = "metoo"
            item["metoo_at"] = row[1]
            result.append(item)
        return result

    def is_author(self, complaint_id: str, device_id: str) -> bool:
        try:
            device = self.device_hash(device_id)
        except RecordError:
            return False
        with self._lock:
            row = self._db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (complaint_id,)).fetchone()
        return bool(row and row[0] == device)

    def target_summary(self, target_id: str, *, days: int = 14, category: str | None = None) -> dict:
        """Сколько людей сообщили о цели за N дней (открытые жалобы). Нужен для «Я тоже»,
        когда /similar (ML) недоступен: та же цель + та же категория = скорее всего то же."""
        since = self._now() - timedelta(days=days)
        items = self.list(since=since, category=category, status=rec.OPEN_STATUSES, target_id=target_id)
        top = max(items, key=lambda r: (rec.reporters(r), r["created_at"]), default=None)
        return {"target_id": target_id, "days": days, "category": category,
                "complaints": len(items), "reporters": sum(rec.reporters(r) for r in items),
                "top": rec.public_view(top) if top else None}

    def events_since(self, after: int = 0, limit: int = 500) -> list[dict]:
        """События для R07 (пульс на цели) и R08: опрос по возрастанию seq."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM complaint_events_v2 WHERE seq > ? ORDER BY seq LIMIT ?",
                                    (int(after), min(int(limit), 2000))).fetchall()
        return [{"seq": r["seq"], "type": r["type"], "at": r["at"], "complaint_id": r["complaint_id"],
                 "target": {"kind": r["target_kind"], "id": r["target_id"]}, "category": r["category"],
                 "status": r["status"], "reporters": r["reporters"], "demo": bool(r["demo"])} for r in rows]

    def overdue(self) -> list[dict]:
        now = self._now()
        return [r for r in self.list(status="new") if rec.is_overdue(r, now)]

    # ------------------------------------------------------------ импорт (миграция, демо)
    def import_record(self, record: dict, *, legacy_v1_id: int | None = None,
                      metoo_devices: list[tuple[str, str]] | None = None) -> bool:
        """Сохранить готовую запись v2 (миграция v1, синтетика R02). Идемпотентно по id и legacy_v1_id.
        -> True, если запись новая. metoo_devices — [(device_hash, at)] уже хэшированные."""
        with self._tx() as db:
            if self._load(db, record["id"]) is not None:
                return False
            if legacy_v1_id is not None and db.execute(
                    "SELECT 1 FROM complaints_v2 WHERE legacy_v1_id = ?", (legacy_v1_id,)).fetchone():
                return False
            record = dict(record)
            if not record.get("code"):
                record["code"] = self._next_code(db)
            self._save(db, record, legacy_v1_id=legacy_v1_id)
            for device, at in metoo_devices or []:
                db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 VALUES (?,?,?)", (record["id"], device, at))
            return True
