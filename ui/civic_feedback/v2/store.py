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
from . import joint
from . import lifecycle
from . import photos as photos_mod
from . import record as rec
from . import separate as sep
from .joint_store import JointMixin
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
""" + sep.SCHEMA_SQL + """
-- «Проверено жителями» (волна 2, п. 1): один голос устройства за раунд «служба сообщила об устранении».
CREATE TABLE IF NOT EXISTS complaint_votes_v2 (
  complaint_id TEXT NOT NULL,
  round INTEGER NOT NULL,
  device_hash TEXT NOT NULL,
  answer TEXT NOT NULL CHECK (answer IN ('yes', 'no', 'cant')),
  at TEXT NOT NULL,
  PRIMARY KEY (complaint_id, round, device_hash)
);
-- Фото (волна 1, п. 5): только очищенные байты (без EXIF/GPS); загрузка частями — шлюз R01 пропускает ≤ 64 КБ.
CREATE TABLE IF NOT EXISTS complaint_photos_v2 (
  id TEXT PRIMARY KEY,
  complaint_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('resident', 'after')),
  round INTEGER,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  data BLOB NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS complaint_photos_v2_complaint ON complaint_photos_v2 (complaint_id, kind);
CREATE TABLE IF NOT EXISTS complaint_uploads_v2 (
  id TEXT PRIMARY KEY,
  complaint_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  owner TEXT NOT NULL,
  size INTEGER NOT NULL,
  received BLOB NOT NULL,
  created_at TEXT NOT NULL
);
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


class ComplaintStore(sep.SeparateMixin, JointMixin):
    # «Это разные проблемы» (separate, merged, текст «Я тоже») — separate.py (R04 + R09, волна мелочей п. 9).
    """Потокобезопасно: одно соединение под RLock (как FeedbackService v1)."""

    def __init__(self, db_path, *, clock: Callable[[], datetime] | None = None, limits: dict | None = None):
        self.clock = clock or (lambda: datetime.now(rec.ASTANA_TZ))
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        # R15-S04/S12: target_lookup(target) -> форма и подписи цели с карты R12 (подключает R01) или None.
        self.target_lookup = None
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
            # Волна 1, п. 9: «Я тоже», перенесённые из дубля, помнят дубль (via) — чтобы разъединить ошибочное
            # объединение. Старые базы дополняются колонкой без потери строк.
            columns = {row[1] for row in self._db.execute("PRAGMA table_info(complaint_metoo_v2)")}
            if "via" not in columns:
                self._db.execute("ALTER TABLE complaint_metoo_v2 ADD COLUMN via TEXT")
            # Волна 2 (R11 IA_WAVE2 §2.1): «Отписаться» — голос остаётся, обновления и «Мои обращения» — нет.
            if "muted" not in columns:
                self._db.execute("ALTER TABLE complaint_metoo_v2 ADD COLUMN muted INTEGER NOT NULL DEFAULT 0")
        # Раунд 15: записи v2 → v2.1 (service, services, handoffs, route_hint) — один раз на базу, без потерь.
        self.migrate_v21()
        # decision_lookup(complaint_id) -> {option, at} | None — выбор акима (R08 decisions.choice_for).
        self.decision_lookup = None
        # nearby_lookup(device_id, since) -> [карточки «Рядом»] — подписки R08 для «Что изменилось».
        self.nearby_lookup = None
        # assignee_lookup(category, subtopic) — таблица R08 (подключает R01): лучше routing.service_for
        # ({"id","ru","kk","name_edited"}), можно и routing.assignee_lookup (строка). None — таблица R09.
        self.assignee_lookup = None
        # route_lookup(text=, category=, subtopic=, point=) — R04 ui.civic_ml_api.route (раунд 15): подсказка
        # «Похоже, нужны 2 службы» сохраняется в route_hint при подаче. None — подсказки нет, всё работает.
        self.route_lookup = None

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
        """Вставить или обновить запись: JSON + индексные колонки одним оператором.
        Раунд 15: каждая сохраняемая запись — v2.1 (joint.upgrade только добавляет недостающие поля)."""
        joint.upgrade(record)
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

    def _route_hint(self, text, category, subtopic, point) -> dict | None:
        """Подсказка R04 route() для новой жалобы или None (R04 нет, модель не готова, ошибка — жалоба важнее)."""
        if self.route_lookup is None:
            return None
        try:
            found = self.route_lookup(text=text, category=category, subtopic=subtopic, point=point)
        except Exception:  # noqa: BLE001 — подсказка не причина не принять жалобу
            return None
        return joint.parse_route_hint(found)

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
        target = rec.checked_target(rec.parse_target(payload["target"]), point, self.target_lookup) \
            if payload.get("target") is not None else rec.cell_target(*point)
        district = payload.get("district")
        if district is not None and (not isinstance(district, str) or not rec.DISTRICT.match(district)):
            district = None
        lang = payload.get("lang")
        if lang not in ("ru", "kk", "mixed"):
            lang = rec.detect_lang(text)
        # Уточнение (волна 1, п. 2) — только из списка категории; чужое или выдуманное не сохраняем.
        subtopic = payload.get("subtopic")
        if subtopic is not None and categories.subtopic(category, subtopic) is None:
            raise RecordError("Уточнение не подходит к категории.", {"subtopic": "одно из уточнений категории"})
        # Срочный случай (п. 3): сервер сам пересчитывает по уточнению и тексту; клиент сообщает, показал ли баннер.
        urgent = lifecycle.emergency(category, subtopic, text)
        if urgent is not None:
            urgent["banner_shown"] = payload.get("emergency_shown") is True
        # Раунд 15 (CONTRACT §5.1): ведущая служба по таблице R08/R09 на момент подачи (следует за таблицей, пока
        # сотрудник не передаст) и подсказка R04 «нужны 2 службы» — вызов в процессе, без R04 подсказки просто нет.
        lead = joint.lead_service({"category": category, "subtopic": subtopic}, self.assignee_lookup)
        hint = self._route_hint(text, category, subtopic, point)
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
                "category": category, "category_source": source, "subtopic": subtopic,
                "emergency": urgent,
                "model": rec.parse_model(payload.get("model")),
                "point": point, "target": target, "district": district,
                "status": "new",
                "status_history": [{"at": created_at, "status": "new"}],
                "metoo": 0, "duplicate_of": None, "demo": bool(demo),
                "due_at": rec.due_at(created_at, category),
                "service": lead, "service_source": "table", "services": [], "handoffs": [], "route_hint": hint,
                "schema": rec.SCHEMA,
            }
            flag = rec.moderation(record.get("text"))   # п. 8 (R04): акимат видит оригинал с пометкой
            if flag:
                record["moderation"] = flag
            self._save(db, record, device_hash=device, request_id=request_id)
            event = self._event(db, "created", record, created_at)
        self._emit([event])
        return record, True

    # ------------------------------------------------------------ «Я тоже»
    def metoo(self, complaint_id: str, device_id: str, note: dict | None = None) -> tuple[dict, str]:
        """«Я тоже» — одно на устройство. -> (исходная запись, result):
        added | already (уже нажимал) | author (это его собственная жалоба).
        Новую запись не создаёт никогда; если нажали на дубль — засчитывается исходной.
        note — текст, место, цель, категория из формы жалобы (R04, п. 9): видит только акимат; если «Похоже на»
        ошиблось, сотрудник одним действием выделит это в отдельную жалобу жителя (separate.py)."""
        device = self.device_hash(device_id)
        now = rec.iso(self._now())
        parsed = self.parse_metoo_note(note)
        with self._tx() as db:
            record = self._root(db, complaint_id)
            author = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (record["id"],)).fetchone()[0]
            if author == device:
                return record, "author"
            cur = db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) "
                             "VALUES (?,?,?)", (record["id"], device, now))
            if cur.rowcount == 0:
                # Повторное «Я тоже» после «Отписаться» снова подписывает (голос не удваивается).
                db.execute("UPDATE complaint_metoo_v2 SET muted = 0 WHERE complaint_id = ? AND device_hash = ?",
                           (record["id"], device))
                return record, "already"
            if parsed:
                self._add_metoo_note(db, record["id"], device, now, parsed)
            self._recount_metoo(db, record)
            self._save(db, record)
            event = self._event(db, "metoo", record, now)
        self._emit([event])
        return record, "added"

    # ------------------------------------------------------------ статус
    def set_status(self, complaint_id: str, status: str, *, actor: str | None = None,
                   note: str | None = None, expected: str | None = None,
                   what_done: str | None = None, photos: list | None = None) -> dict:
        """Смена статуса сотрудником. expected — статус, который сотрудник видел
        (защита от одновременной правки двумя людьми: иначе Conflict).
        status="fixed" = «Служба сообщила об устранении» (волна 2, п. 1): what_done — одна строка «что сделали»,
        photos — id фото «после», загруженных сотрудником; жители потом проверяют (verify). Оба поля необязательны,
        чтобы старые вызовы {status: "fixed"} (R07, демо R01) продолжали работать."""
        if what_done is not None and not isinstance(what_done, str):
            raise RecordError("«Что сделали» — строка.", {"what_done": "строка"})
        what_done = (what_done or "").strip()[:lifecycle.WHAT_DONE_MAX] or None
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
            # Раунд 15: у совместной жалобы статус ведущей части следует за статусом жалобы; «исправлено» — только
            # когда остальные службы закончили (joint_store.JointMixin._lead_follows_status).
            what_done = self._lead_follows_status(record, status, now, what_done)
            self._apply_status(db, record, status, now, actor=actor, note=note, what_done=what_done, photos=photos)
            self._save(db, record)
            event = self._event(db, "status", record, now)
        self._emit([event])
        return record

    def _apply_status(self, db, record: dict, status: str, now: str, *, actor=None, note=None, what_done=None,
                      photos=None, extra: dict | None = None) -> None:
        """Один шаг статуса внутри транзакции: история, раунд «служба сообщила об устранении», фото «после».
        Общий для set_status и частей служб (совместное исполнение: «исправлено», когда все части сделаны)."""
        entry = {"at": now, "status": status}
        if actor:
            entry["by"] = str(actor)[:80]
        if isinstance(note, str) and note.strip():
            entry["note"] = note.strip()[:500]
        if extra:
            entry.update(extra)
        if status == "fixed":
            after = self._photo_ids(db, record["id"], "after", photos)
            record["resolution"] = lifecycle.new_resolution(record.get("resolution"), now, what_done, actor, after)
            # R15-S24: кто нажал «Я тоже» до этой минуты, может проверить ремонт; кто после — нет. Порядок вставки
            # (rowid) точнее времени: «Я тоже» и «исправлено» могут прийти в одну секунду.
            record["resolution"]["metoo_upto"] = db.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM complaint_metoo_v2").fetchone()[0]
            db.execute("UPDATE complaint_photos_v2 SET round = ? WHERE complaint_id = ? AND kind = 'after' "
                       "AND round IS NULL", (record["resolution"]["round"], record["id"]))
            self._add_update(record, now, "fixed", what_done)
        elif record["status"] == "fixed" and record.get("resolution"):
            # Служба сама вернула в работу (не жители): раунд проверки закрыт без итога.
            record["resolution"]["state"] = "withdrawn"
        record["status"] = status
        record["status_history"].append(entry)

    # ------------------------------------------------------------ жители проверяют ремонт (волна 2, п. 1)
    def _participant(self, db, record: dict, device: str) -> str | None:
        """author | metoo | None — кто это устройство для исходной жалобы."""
        row = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (record["id"],)).fetchone()
        if row and row[0] == device:
            return "author"
        if db.execute("SELECT 1 FROM complaint_metoo_v2 WHERE complaint_id = ? AND device_hash = ? AND muted = 0",
                      (record["id"], device)).fetchone():
            return "metoo"
        return None

    def _subscribers(self, db, record: dict) -> int:
        """Сколько человек увидят обновление: автор + «Я тоже» без «Отписаться»."""
        return 1 + db.execute("SELECT COUNT(*) FROM complaint_metoo_v2 WHERE complaint_id = ? AND muted = 0",
                              (record["id"],)).fetchone()[0]

    def subscribers(self, complaint_id: str) -> int:
        with self._lock:
            if self._load(self._db, complaint_id) is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            return self._subscribers(self._db, self._root(self._db, complaint_id))

    def unsubscribe(self, complaint_id: str, device_id: str) -> str:
        """«Отписаться» от «Я тоже»: голос («сообщили N») остаётся, обновления и карточка в «Мои обращения» — нет.
        -> unsubscribed | not_subscribed (не нажимал «Я тоже» или уже отписался) | author (своя жалоба)."""
        device = self.device_hash(device_id)
        with self._tx() as db:
            if self._load(db, complaint_id) is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            record = self._root(db, complaint_id)
            author = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (record["id"],)).fetchone()[0]
            if author == device:
                return "author"
            cur = db.execute("UPDATE complaint_metoo_v2 SET muted = 1 WHERE complaint_id = ? AND device_hash = ? "
                             "AND muted = 0", (record["id"], device))
            return "unsubscribed" if cur.rowcount else "not_subscribed"

    def _verifier(self, db, record: dict, device: str) -> str | None:
        """Кто может проверить ремонт (R15-S24): автор и «Я тоже», нажатые ДО «служба сообщила об устранении».
        Иначе любой посторонний: «Я тоже» после ремонта -> «Проблема осталась» -> проверенный ремонт снова «в работе»."""
        relation = self._participant(db, record, device)
        if relation != "metoo":
            return relation
        resolution = record.get("resolution") or {}
        row = db.execute("SELECT rowid, at FROM complaint_metoo_v2 WHERE complaint_id = ? AND device_hash = ?",
                         (record["id"], device)).fetchone()
        if row is None:
            return None
        if isinstance(resolution.get("metoo_upto"), int):
            return "metoo" if row[0] <= resolution["metoo_upto"] else None
        reported = resolution.get("reported_at")      # записи до patch: по времени
        return "metoo" if reported and row[1] <= reported else None

    def participant(self, complaint_id: str, device_id) -> str | None:
        try:
            device = self.device_hash(device_id)
        except RecordError:
            return None
        with self._lock:
            record = self._load(self._db, complaint_id)
            if record is None:
                return None
            record = self._root(self._db, complaint_id)
            return self._participant(self._db, record, device)

    def can_verify(self, complaint_id: str, device_id) -> bool:
        """Показать жителю «Проблема решена?»: участник, служба сообщила об устранении, в этом раунде ещё не отвечал."""
        try:
            device = self.device_hash(device_id)
        except RecordError:
            return False
        with self._lock:
            if self._load(self._db, complaint_id) is None:
                return False
            record = self._root(self._db, complaint_id)
            resolution = record.get("resolution") or {}
            if record["status"] != "fixed" or resolution.get("state") not in ("reported", "verified"):
                return False
            if self._verifier(self._db, record, device) is None:
                return False
            voted = self._db.execute("SELECT 1 FROM complaint_votes_v2 WHERE complaint_id = ? AND round = ? "
                                     "AND device_hash = ?", (record["id"], resolution["round"], device)).fetchone()
            return voted is None

    def verify(self, complaint_id: str, device_id: str, answer: str) -> tuple[dict, str]:
        """Ответ автора или «Я тоже» после «Служба сообщила об устранении»: yes | no | cant.
        -> (запись, result): recorded | already (уже отвечал в этом раунде) | not_participant | not_waiting.
        Правило (объяснимое): первое «Да» -> «проверено жителями»; любое «Проблема осталась» -> та же карточка
        снова «в работе» с отметкой «вернули жители» и историей; «Не могу проверить» только считается."""
        if answer not in lifecycle.VERIFY_ANSWERS:
            raise RecordError("Ответ: да, проблема осталась или не могу проверить.", {"answer": "yes | no | cant"})
        device = self.device_hash(device_id)
        now = rec.iso(self._now())
        events = []
        with self._tx() as db:
            record = self._root(db, complaint_id)
            if self._verifier(db, record, device) is None:
                return record, "not_participant"
            resolution = record.get("resolution")
            if record["status"] != "fixed" or not resolution or resolution.get("state") not in ("reported", "verified"):
                return record, "not_waiting"
            cur = db.execute("INSERT OR IGNORE INTO complaint_votes_v2 (complaint_id, round, device_hash, answer, at) "
                             "VALUES (?,?,?,?,?)", (record["id"], resolution["round"], device, answer, now))
            if cur.rowcount == 0:
                return record, "already"
            resolution["votes"][answer] = resolution["votes"].get(answer, 0) + 1
            if answer == "yes" and resolution["state"] == "reported":
                resolution["state"] = "verified"
                resolution["verified_at"] = now
                events.append("verified")
            elif answer == "no":
                resolution["state"] = "reopened"
                resolution["reopened_at"] = now
                resolution["reopen_count"] = int(resolution.get("reopen_count") or 0) + 1
                record["status"] = "in_progress"
                record["status_history"].append({"at": now, "status": "in_progress", "reopened_by_residents": True})
                self._add_update(record, now, "reopened", None)
                self._lead_reopened(record, now)   # совместная жалоба: ведущая служба снова «в работе»
                events += ["reopened", "status"]
            self._save(db, record)
            emitted = [self._event(db, kind, record, now) for kind in events]
        self._emit(emitted)
        return record, "recorded"

    # ------------------------------------------------------------ паспорт решения и обновления (волна 2, п. 2–3)
    @staticmethod
    def _add_update(record: dict, at: str, kind: str, text: str | None) -> None:
        """Одна лента обновлений на жалобу: её видят автор и все «Я тоже» (одно действие — всем)."""
        record.setdefault("updates", []).append({"at": at, "kind": kind, "text": text})

    def update_passport(self, complaint_id: str, fields: dict, *, actor: str | None = None,
                        role: str | None = None) -> tuple[dict, int]:
        """Сотрудник заполняет паспорт (R11 IA_WAVE2 §2.3 — 3 поля): service (id службы из lifecycle.SERVICES,
        пусто = по таблице R08/R09), next_step, fix_eta (YYYY-MM-DD или пусто = «пока не определено»); при задержке
        ещё delay_reason, temp_measure, next_update_at (YYYY-MM-DD). -> (запись, сколько человек увидят обновление)."""
        if not isinstance(fields, dict):
            raise RecordError("Пустой запрос.")
        clean = {}
        service = fields.get("service")
        if service not in (None, "") and service not in lifecycle.SERVICES:
            raise RecordError("Неизвестная служба.", {"service": ",".join(lifecycle.SERVICES)})
        clean["service"] = service or None
        for name in ("next_step", "delay_reason", "temp_measure", "decision", "option_1", "option_2"):
            value = fields.get(name)
            if value is None or value == "":
                clean[name] = None
                continue
            if not isinstance(value, str):
                raise RecordError("Поле должно быть строкой.", {name: "строка"})
            clean[name] = " ".join(value.split())[:lifecycle.PASSPORT_TEXT_MAX] or None
        for name in ("fix_eta", "next_update_at"):
            value = fields.get(name)
            if value in (None, ""):
                clean[name] = None
                continue
            try:
                clean[name] = datetime.strptime(str(value), "%Y-%m-%d").date().isoformat()
            except ValueError:
                raise RecordError("Дата в формате ГГГГ-ММ-ДД.", {name: "YYYY-MM-DD"}) from None
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._load(db, complaint_id)
            if record is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            lead_before = joint.lead_service(record, self.assignee_lookup)
            passport = dict(record.get("passport") or {})
            for name in ("next_step", "fix_eta"):
                if name in fields:
                    passport[name] = clean[name]
            if "service" in fields:
                passport["assignee_id"] = clean["service"]
                passport.pop("assignee", None)          # свободный текст старых версий уступает выбору из списка
            if any(name in fields for name in ("delay_reason", "temp_measure", "next_update_at", "needs_decision")):
                delay = {"reason": clean["delay_reason"], "temp_measure": clean["temp_measure"],
                         "next_update_at": clean["next_update_at"]}
                # «Нужно решение руководителя» (R08 «Нужно решение акима», волна 2 п. 5): два варианта и что нужно
                # от акима. Формат читает ui.civic_akim.decisions: delay.needs_decision, options [{ru}], decision.
                if fields.get("needs_decision") is True:
                    delay["needs_decision"] = True
                    delay["options"] = [{"ru": clean[k]} for k in ("option_1", "option_2") if clean[k]]
                    delay["decision"] = clean["decision"]
                passport["delay"] = delay if any(v for k, v in delay.items()) else None
            passport["updated_at"] = now
            if actor:
                passport["by"] = str(actor)[:80]
            record["passport"] = passport
            if "service" in fields:
                # Раунд 15: выбор службы в паспорте — та же передача (части служб и журнал передач для R17).
                self._passport_service(record, clean["service"], lead_before, now, role)
            summary = clean.get("next_step") or clean.get("delay_reason")
            self._add_update(record, now, "passport", summary)
            self._save(db, record)
            event = self._event(db, "update", record, now)
            notified = self._subscribers(db, record)
        self._emit([event])
        return record, notified

    def post_update(self, complaint_id: str, text, *, actor: str | None = None) -> tuple[dict, int]:
        """Одно сообщение сотрудника всем затронутым (автор + «Я тоже»). -> (запись, сколько человек увидят)."""
        if not isinstance(text, str) or len(" ".join(text.split())) < 3:
            raise RecordError("Напишите обновление.", {"text": "не короче 3 символов"})
        now = rec.iso(self._now())
        with self._tx() as db:
            record = self._root(db, complaint_id)
            self._add_update(record, now, "note", " ".join(text.split())[:lifecycle.PASSPORT_TEXT_MAX * 2])
            self._save(db, record)
            event = self._event(db, "update", record, now)
            notified = self._subscribers(db, record)
        self._emit([event])
        return record, notified

    def changes(self, device_id: str, since: str | None = None) -> dict:
        """«Что изменилось с вашим участием» (волна 2, п. 10): события по жалобам устройства после since."""
        return lifecycle.changes(self.mine(device_id), since)

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
                    db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at, via) "
                               "VALUES (?,?,?,?)", (original["id"], device, now, duplicate["id"]))
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

    def unmark_duplicate(self, complaint_id: str, *, actor: str | None = None) -> dict:
        """Волна 1, п. 9: «Это разные проблемы» — отменить ошибочное объединение (то же, что separate(c-…) R04:
        снимает «Я тоже» дубля по всей цепочке исходных и возвращает перепривязанные дубли)."""
        return self.separate(complaint_id, actor=actor)[0]

    def _unmark_duplicate_simple(self, complaint_id: str, *, actor: str | None = None) -> dict:
        """Прежняя простая отмена (только прямая исходная, по via) — оставлена для сравнения в тестах."""
        now = rec.iso(self._now())
        with self._tx() as db:
            duplicate = self._load(db, complaint_id)
            if duplicate is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            original_id = duplicate.get("duplicate_of")
            if not original_id:
                raise Conflict("Обращение не объединено с другим.")
            original = self._load(db, original_id)
            db.execute("DELETE FROM complaint_metoo_v2 WHERE complaint_id = ? AND via = ?", (original_id, duplicate["id"]))
            duplicate["duplicate_of"] = None
            entry = {"at": now, "status": duplicate["status"], "unmerged_from": original_id}
            if actor:
                entry["by"] = str(actor)[:80]
            duplicate["status_history"].append(entry)
            self._recount_metoo(db, duplicate)
            self._save(db, duplicate)
            events = [self._event(db, "unmerged", duplicate, now)]
            if original is not None:
                self._recount_metoo(db, original)
                self._save(db, original)
                events.append(self._event(db, "metoo", original, now))
        self._emit(events)
        return duplicate

    # ------------------------------------------------------------ фото (волна 1, п. 5)
    def _photo_ids(self, db, complaint_id: str, kind: str, ids) -> list[str]:
        """id фото «после» текущего раунда: переданные (должны принадлежать жалобе) или все ещё не привязанные."""
        rows = db.execute("SELECT id FROM complaint_photos_v2 WHERE complaint_id = ? AND kind = ? AND round IS NULL "
                          "ORDER BY created_at", (complaint_id, kind)).fetchall()
        available = [row[0] for row in rows]
        if ids is None:
            return available[:photos_mod.MAX_AFTER]
        if not isinstance(ids, list) or any(i not in available for i in ids):
            raise RecordError("Фото «после» не найдено.", {"photos": "загрузите фото к этому обращению"})
        return ids[:photos_mod.MAX_AFTER]

    def start_upload(self, complaint_id: str, kind: str, size, *, device_id=None, actor: str | None = None) -> dict:
        """Начать загрузку фото: житель (автор) — kind «resident», сотрудник — «after». -> {upload_id, chunk_bytes}."""
        if kind not in ("resident", "after"):
            raise RecordError("Неизвестный вид фото.", {"kind": "resident | after"})
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= photos_mod.MAX_BYTES:
            raise RecordError("Фото слишком большое.", {"size": f"до {photos_mod.MAX_BYTES} байт"})
        now = self._now()
        with self._tx() as db:
            record = self._load(db, complaint_id)
            if record is None:
                raise NotFound("Обращение не найдено.", {"id": complaint_id})
            if kind == "resident":
                device = self.device_hash(device_id)
                author = db.execute("SELECT device_hash FROM complaints_v2 WHERE id = ?", (complaint_id,)).fetchone()[0]
                if author != device:
                    raise Conflict("Фото добавляет только автор обращения.")
                owner = "device:" + device
                count = db.execute("SELECT COUNT(*) FROM complaint_photos_v2 WHERE complaint_id = ? AND kind = 'resident'",
                                   (complaint_id,)).fetchone()[0]
                limit = photos_mod.MAX_RESIDENT
            else:
                owner = "staff:" + str(actor or "staff")[:80]
                count = db.execute("SELECT COUNT(*) FROM complaint_photos_v2 WHERE complaint_id = ? AND kind = 'after' "
                                   "AND round IS NULL", (complaint_id,)).fetchone()[0]
                limit = photos_mod.MAX_AFTER
            if count >= limit:
                raise Conflict(f"Можно не больше {limit} фото.")
            # Брошенные загрузки старше часа не держим.
            db.execute("DELETE FROM complaint_uploads_v2 WHERE created_at < ?", (rec.iso(now - timedelta(hours=1)),))
            upload_id = "u-" + secrets.token_hex(8)
            db.execute("INSERT INTO complaint_uploads_v2 (id, complaint_id, kind, owner, size, received, created_at) "
                       "VALUES (?,?,?,?,?,?,?)", (upload_id, complaint_id, kind, owner, size, b"", rec.iso(now)))
        return {"upload_id": upload_id, "chunk_bytes": photos_mod.CHUNK_BYTES}

    def upload_chunk(self, complaint_id: str, upload_id: str, offset, data: bytes, *, device_id=None,
                     actor: str | None = None) -> dict:
        """Следующая часть. Когда пришли все байты — фото очищается (без EXIF/GPS) и сохраняется.
        -> {"done": False, "received"} | {"done": True, "photo": {id, kind}}."""
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise RecordError("Неверная часть фото.", {"offset": "число"})
        if not data or len(data) > photos_mod.CHUNK_BYTES:
            raise RecordError("Неверная часть фото.", {"data": f"1–{photos_mod.CHUNK_BYTES} байт"})
        now = rec.iso(self._now())
        events = []
        with self._tx() as db:
            row = db.execute("SELECT * FROM complaint_uploads_v2 WHERE id = ? AND complaint_id = ?",
                             (upload_id, complaint_id)).fetchone()
            if row is None:
                raise NotFound("Загрузка не найдена — начните заново.", {"upload_id": upload_id})
            owner = ("device:" + self.device_hash(device_id)) if row["kind"] == "resident" \
                else "staff:" + str(actor or "staff")[:80]
            if owner != row["owner"]:
                raise Conflict("Эту загрузку начал другой пользователь.")
            received = bytes(row["received"])
            if offset != len(received):
                # Повтор уже принятой части (слабая сеть) — не ошибка: сообщаем, сколько есть.
                if offset + len(data) <= len(received):
                    return {"done": False, "received": len(received)}
                raise Conflict("Части фото пришли не по порядку.", {"received": len(received)})
            received += data
            if len(received) > row["size"]:
                db.execute("DELETE FROM complaint_uploads_v2 WHERE id = ?", (upload_id,))
                raise RecordError("Фото больше заявленного размера.")
            if len(received) < row["size"]:
                db.execute("UPDATE complaint_uploads_v2 SET received = ? WHERE id = ?", (received, upload_id))
                return {"done": False, "received": len(received)}
            db.execute("DELETE FROM complaint_uploads_v2 WHERE id = ?", (upload_id,))
            try:
                mime, clean = photos_mod.sanitize(received)
            except photos_mod.PhotoError as exc:
                raise RecordError(str(exc), {"photo": "jpeg, png или webp до 1,5 МБ"}) from None
            photo_id = "p-" + secrets.token_hex(8)
            db.execute("INSERT INTO complaint_photos_v2 (id, complaint_id, kind, round, mime, size, sha256, data, "
                       "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (photo_id, complaint_id, row["kind"], None, mime, len(clean),
                        hashlib.sha256(clean).hexdigest(), clean, now))
            record = self._load(db, complaint_id)
            if row["kind"] == "resident":
                record.setdefault("photos", []).append({"id": photo_id, "kind": "resident", "at": now})
                self._save(db, record)
        return {"done": True, "photo": {"id": photo_id, "kind": row["kind"], "mime": mime}}

    def get_photo(self, complaint_id: str, photo_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT id, kind, round, mime, size, data FROM complaint_photos_v2 "
                                   "WHERE id = ? AND complaint_id = ?", (photo_id, complaint_id)).fetchone()
        return dict(row) if row else None

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
                "WHERE m.device_hash = ? AND m.muted = 0 ORDER BY m.at DESC", (device,)).fetchall()
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

    def place_reporters(self, record: dict, *, days: int = 14) -> int:
        """Сколько людей сообщили о том же на этом месте: жалобы той же цели и категории (кроме отклонённых и дублей —
        люди дубля уже перенесены в исходную), поданные в пределах ±days от этой. Для «Мои обращения»: то же число, что
        житель видел на шаге «Я тоже», даже если о проблеме подали несколько отдельных жалоб; после «исправлено» не меняется."""
        own = rec.reporters(record)
        target_id = (record.get("target") or {}).get("id")
        created = rec.parse_iso(record.get("created_at"))
        if not target_id or not record.get("category") or created is None:
            return own
        span = timedelta(days=days).total_seconds()
        with self._lock:
            rows = self._db.execute(
                "SELECT record_json FROM complaints_v2 WHERE target_id = ? AND category = ? AND status != 'rejected' "
                "AND duplicate_of IS NULL AND created_ts BETWEEN ? AND ?",
                (target_id, record["category"], created.timestamp() - span, created.timestamp() + span)).fetchall()
        return max(own, sum(rec.reporters(json.loads(row[0])) for row in rows))

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

    def metoo_times(self, complaint_ids) -> dict[str, list[str]]:
        """Даты «Я тоже» по жалобам — для веса тепловой карты R07 (каждое «Я тоже» стареет само,
        CONTRACT §6). -> {complaint_id: [ISO, ...]} по возрастанию."""
        ids = list(complaint_ids)
        result: dict[str, list[str]] = {cid: [] for cid in ids}
        with self._lock:
            for start in range(0, len(ids), 500):  # лимит параметров SQLite
                chunk = ids[start:start + 500]
                rows = self._db.execute(
                    f"SELECT complaint_id, at FROM complaint_metoo_v2 WHERE complaint_id IN ({','.join('?' * len(chunk))}) "
                    "ORDER BY at", chunk).fetchall()
                for row in rows:
                    result[row[0]].append(row[1])
        return result

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
    def migrate_v21(self, *, force: bool = False) -> dict:
        """Записи v2 → v2.1 в этой базе: только добавляются поля CONTRACT §5.1 (joint.upgrade), ничего не удаляется.
        Один раз на базу (отметка в complaint_meta_v2); повтор — ничего не делает. -> {"upgraded", "total"}."""
        with self._tx() as db:
            mark = db.execute("SELECT value FROM complaint_meta_v2 WHERE key = 'migrated_v21'").fetchone()
            if mark and not force:
                return {"upgraded": 0, "total": None, "at": mark[0]}
            upgraded = total = 0
            for row in db.execute("SELECT record_json FROM complaints_v2").fetchall():
                total += 1
                record = json.loads(row[0])
                if joint.upgrade(record):
                    self._save(db, record)
                    upgraded += 1
            db.execute("INSERT OR REPLACE INTO complaint_meta_v2 (key, value) VALUES ('migrated_v21', ?)",
                       (rec.iso(self._now()),))
        return {"upgraded": upgraded, "total": total}

    def reset_demo_record(self, record: dict, metoo_devices: list[tuple[str, str]] | None = None) -> str:
        """Демо-запись (demo: true) — в исходное состояние при каждом запуске демо-сборки (R10 B-048, B-049):
        статус «Новое», исходные синтетические «Я тоже», время — от текущего запуска. После репетиции (исправлено,
        «Я тоже» ведущего, проверка ремонта) и через две недели после первой настройки шаг 2 демо снова такой же.
        Настоящие жалобы не трогаются; если id занят настоящей записью — ничего не делаем.
        -> added | reset | skipped."""
        if not record.get("demo"):
            raise RecordError("Сбрасывать можно только демо-запись.")
        now = rec.iso(self._now())
        with self._tx() as db:
            old = self._load(db, record["id"])
            if old is not None and not old.get("demo"):
                return "skipped"
            fresh = dict(record)
            fresh["code"] = (old or {}).get("code") or fresh.get("code") or self._next_code(db)
            fresh["metoo"] = len(metoo_devices or [])
            self._save(db, fresh)
            if old is not None:
                for table in ("complaint_metoo_v2", "complaint_votes_v2", "complaint_photos_v2", "complaint_uploads_v2"):
                    db.execute(f"DELETE FROM {table} WHERE complaint_id = ?", (record["id"],))
            for device, at in metoo_devices or []:
                db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) VALUES (?,?,?)",
                           (record["id"], device, at))
            event = self._event(db, "update" if old is not None else "created", fresh, now)
        self._emit([event])
        return "reset" if old is not None else "added"

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
                db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) VALUES (?,?,?)",
                           (record["id"], device, at))
            return True
