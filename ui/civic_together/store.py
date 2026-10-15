"""Хранилище «Бірге: жители вместе» (R16, раунд 15): таблицы tg_* в той же SQLite, что у шлюза R01 (CIVIC_DB_PATH).

Что храним (CONTRACT §5.2–5.3, §10):
  tg_meta        — версия схемы и соль для хэша устройства (случайная, создаётся один раз).
  tg_yards       — дворы, о которых модуль уже знает: подпись, район, точка; «старший по двору» (по желанию).
                   base_members — только у демо-двора: «соседи, вступившие раньше» числом, без выдуманных устройств.
  tg_members     — «Я живу здесь»: (двор, хэш устройства). Наружу — только число; кто и когда — никому.
  tg_initiatives — инициативы жителей: вид, название, текст (и публичная копия после модерации R04), цель-двор,
                   точка, даты, «что взять», статус, поддержка акимата. Автор — только хэш устройства.
  tg_joins       — «Я приду»: (инициатива, хэш устройства) — одно устройство, один голос (первичный ключ).
  tg_reports     — отчёт «Сделано вместе»: текст, сколько соседей пришло (число на момент «сделано»).
  tg_photos      — фото «после» (публичные, без EXIF и GPS) или статическая картинка демо-набора.
  tg_events      — что изменилось: для ленты двора и функции updates() (лента уведомлений R06, CONTRACT §5.8).
                   Событие хранит инициативу/двор и аудиторию (двор, пришедшие, автор), а не устройства —
                   по таблице событий нельзя узнать, кто живёт во дворе.

Время — ISO 8601 по Астане (+05:00), как у жалоб R09: строки одного формата сортируются как даты.
Запись — одной транзакцией BEGIN IMMEDIATE под блокировкой: проверка лимита и вставка не разрываются.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import sqlite3
import threading

SCHEMA_VERSION = 1
ASTANA = timezone(timedelta(hours=5))

SCHEMA = """
CREATE TABLE IF NOT EXISTS tg_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_yards (
    id TEXT PRIMARY KEY,
    label_ru TEXT,
    label_kk TEXT,
    district TEXT,
    lon REAL,
    lat REAL,
    base_members INTEGER NOT NULL DEFAULT 0,
    captain_name TEXT,
    captain_status TEXT,
    captain_hash TEXT,
    captain_since TEXT,
    demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_members (
    yard_id TEXT NOT NULL,
    device_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (yard_id, device_hash)
);
CREATE INDEX IF NOT EXISTS tg_members_device ON tg_members (device_hash);
CREATE TABLE IF NOT EXISTS tg_initiatives (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    title_public TEXT,
    text_public TEXT,
    lang TEXT NOT NULL DEFAULT 'ru',
    target_kind TEXT,
    target_id TEXT,
    label_ru TEXT,
    label_kk TEXT,
    lon REAL NOT NULL,
    lat REAL NOT NULL,
    district TEXT,
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    bring_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK (status IN ('on_review', 'published', 'done', 'cancelled', 'hidden')),
    author_hash TEXT,
    request_hash TEXT UNIQUE,
    base_joined INTEGER NOT NULL DEFAULT 0,
    support_json TEXT,
    moderation_json TEXT,
    hide_reason TEXT,
    moderated_by TEXT,
    moderated_at TEXT,
    from_idea TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    done_at TEXT,
    updated_at TEXT NOT NULL,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tg_initiatives_status ON tg_initiatives (status, starts_at);
CREATE INDEX IF NOT EXISTS tg_initiatives_target ON tg_initiatives (target_id, status);
CREATE INDEX IF NOT EXISTS tg_initiatives_author ON tg_initiatives (author_hash, status);
CREATE TABLE IF NOT EXISTS tg_joins (
    initiative_id TEXT NOT NULL,
    device_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (initiative_id, device_hash)
);
CREATE INDEX IF NOT EXISTS tg_joins_device ON tg_joins (device_hash);
CREATE TABLE IF NOT EXISTS tg_reports (
    initiative_id TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    text_public TEXT,
    status TEXT NOT NULL CHECK (status IN ('on_review', 'published', 'hidden')),
    joined_final INTEGER,
    by_role TEXT NOT NULL,
    moderation_json TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    updated_at TEXT NOT NULL,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tg_photos (
    id TEXT PRIMARY KEY,
    initiative_id TEXT NOT NULL,
    mime TEXT,
    data BLOB,
    thumb BLOB,
    thumb_mime TEXT,
    src TEXT,
    width INTEGER,
    height INTEGER,
    created_at TEXT NOT NULL,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tg_photos_initiative ON tg_photos (initiative_id, created_at);
CREATE TABLE IF NOT EXISTS tg_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    code TEXT NOT NULL,
    audience TEXT NOT NULL CHECK (audience IN ('yard', 'joined', 'author', 'public')),
    initiative_id TEXT,
    yard_id TEXT,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tg_events_initiative ON tg_events (initiative_id, seq);
CREATE INDEX IF NOT EXISTS tg_events_yard ON tg_events (yard_id, seq);
"""

# Сколько людей придёт: демо-основа («записались раньше», без выдуманных устройств) + настоящие «Я приду».
JOINED_SQL = "(i.base_joined + (SELECT COUNT(*) FROM tg_joins j WHERE j.initiative_id = i.id))"
MEMBERS_SQL = "(y.base_members + (SELECT COUNT(*) FROM tg_members m WHERE m.yard_id = y.id))"


def now_astana() -> datetime:
    return datetime.now(ASTANA)


def iso(moment: datetime) -> str:
    """Время по Астане без долей секунды: «2026-10-17T10:00:00+05:00»."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ASTANA)
    return moment.astimezone(ASTANA).replace(microsecond=0).isoformat()


def parse_iso(value) -> datetime | None:
    """ISO 8601 с поясом или без (тогда — время Астаны); «Z» тоже понимаем. Неверная строка — None."""
    if not isinstance(value, str) or not value.strip() or len(value) > 40:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA)


class Conflict(Exception):
    """Действие не подходит к состоянию записи (уже проверена, уже сделано…) — ответ 409."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class TooMany(Exception):
    """Лимит устройства (инициатив на проверке, вступлений) — ответ 429."""

    def __init__(self, code: str, message: str, retry_after: int = 3600):
        super().__init__(message)
        self.code, self.message, self.retry_after = code, message, retry_after


def _loads(raw, default=None):
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TogetherStore:
    """Доступ к таблицам tg_*. Безопасен для потоков сервера: соединение на вызов, запись под блокировкой."""

    def __init__(self, db_path, clock=now_astana):
        self.db_path = str(db_path)
        self.clock = clock
        self._write = threading.Lock()
        # executescript сам завершает транзакцию — поэтому схему создаём соединением без BEGIN IMMEDIATE.
        with self._read() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
        with self._tx() as conn:
            conn.execute("INSERT OR IGNORE INTO tg_meta (key, value) VALUES ('device_salt', ?)", (secrets.token_hex(16),))
            self._salt = conn.execute("SELECT value FROM tg_meta WHERE key = 'device_salt'").fetchone()[0]

    @staticmethod
    def _migrate(conn) -> None:
        """Миграция по номеру схемы. Версия 1 — первая; следующие добавляют колонки ALTER TABLE без потери строк."""
        row = conn.execute("SELECT value FROM tg_meta WHERE key = 'schema_version'").fetchone()
        current = int(row[0]) if row and str(row[0]).isdigit() else 0
        if current < SCHEMA_VERSION:
            conn.execute("INSERT OR REPLACE INTO tg_meta (key, value) VALUES ('schema_version', ?)",
                         (str(SCHEMA_VERSION),))

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
        moment = self.clock()
        return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA)

    def device_hash(self, device_id: str) -> str:
        return hashlib.sha256(f"birge-together:{self._salt}:{device_id}".encode()).hexdigest()

    @staticmethod
    def _event(conn, at: str, code: str, audience: str, *, initiative_id=None, yard_id=None, demo=False) -> None:
        conn.execute("INSERT INTO tg_events (at, code, audience, initiative_id, yard_id, demo) VALUES (?, ?, ?, ?, ?, ?)",
                     (at, code, audience, initiative_id, yard_id, int(bool(demo))))

    # ------------------------------------------------------------------ дворы
    def upsert_yard(self, conn, yard_id: str, *, label_ru=None, label_kk=None, district=None, point=None,
                    demo=False, base_members=None) -> None:
        """Запомнить двор (подписи и точка — с карты R12). Уже известный двор: пустые поля дополняются."""
        at = iso(self.now())
        lon, lat = (point[0], point[1]) if point else (None, None)
        conn.execute(
            "INSERT INTO tg_yards (id, label_ru, label_kk, district, lon, lat, base_members, demo, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "label_ru = COALESCE(tg_yards.label_ru, excluded.label_ru), "
            "label_kk = COALESCE(tg_yards.label_kk, excluded.label_kk), "
            "district = COALESCE(tg_yards.district, excluded.district), "
            "lon = COALESCE(tg_yards.lon, excluded.lon), lat = COALESCE(tg_yards.lat, excluded.lat)",
            (yard_id, label_ru, label_kk, district, lon, lat, int(base_members or 0), int(bool(demo)), at, at))

    def yard(self, yard_id: str) -> dict | None:
        with self._read() as conn:
            row = conn.execute(f"SELECT y.*, {MEMBERS_SQL} AS members FROM tg_yards y WHERE y.id = ?",
                               (yard_id,)).fetchone()
        return dict(row) if row else None

    def remember_yard(self, yard_id: str, **fields) -> dict:
        with self._tx() as conn:
            self.upsert_yard(conn, yard_id, **fields)
        return self.yard(yard_id)

    def meta(self, key: str, value: str | None = None) -> str | None:
        """Служебное значение модуля (например, двор сцены 7 демо — первым в списке дворов)."""
        if value is not None:
            with self._tx() as conn:
                conn.execute("INSERT OR REPLACE INTO tg_meta (key, value) VALUES (?, ?)", (key, value))
            return value
        with self._read() as conn:
            row = conn.execute("SELECT value FROM tg_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def yards(self, *, district: str | None = None, limit: int = 60) -> list[dict]:
        """Дворы, где уже есть соседи или инициативы, — для выбора двора: двор сцены демо первым (IA R11 §5.1),
        дальше — больше соседей выше."""
        where, args = [], []
        if district:
            where.append("y.district = ?")
            args.append(district)
        scene = self.meta("scene_yard") or ""
        # R15 S51: только дворы, где есть соседи или дела (и двор сцены демо), — не всё, что когда-то открывали.
        sql = (f"SELECT * FROM (SELECT y.*, {MEMBERS_SQL} AS members, "
               "(SELECT COUNT(*) FROM tg_initiatives i WHERE i.target_id = y.id AND i.status IN ('published', 'done')) "
               "AS initiatives FROM tg_yards y" + (" WHERE " + " AND ".join(where) if where else "") +
               ") WHERE members > 0 OR initiatives > 0 OR id = ? "
               "ORDER BY (id = ?) DESC, members DESC, initiatives DESC, id LIMIT ?")
        with self._read() as conn:
            return [dict(r) for r in conn.execute(sql, (*args, scene, scene, int(limit))).fetchall()]

    def is_member(self, yard_id: str, device_id: str | None) -> bool:
        if not device_id:
            return False
        with self._read() as conn:
            return conn.execute("SELECT 1 FROM tg_members WHERE yard_id = ? AND device_hash = ?",
                                (yard_id, self.device_hash(device_id))).fetchone() is not None

    def my_yards(self, device_id: str | None) -> list[str]:
        if not device_id:
            return []
        with self._read() as conn:
            rows = conn.execute("SELECT yard_id FROM tg_members WHERE device_hash = ? ORDER BY created_at DESC",
                                (self.device_hash(device_id),)).fetchall()
        return [r[0] for r in rows]

    def join_yard(self, yard_id: str, device_id: str, *, max_yards: int = 3, **yard_fields) -> tuple[int, bool]:
        """«Я живу здесь». Повтор — без изменений. Не больше max_yards дворов с одного устройства."""
        dev = self.device_hash(device_id)
        with self._tx() as conn:
            self.upsert_yard(conn, yard_id, **yard_fields)
            exists = conn.execute("SELECT 1 FROM tg_members WHERE yard_id = ? AND device_hash = ?",
                                  (yard_id, dev)).fetchone()
            created = False
            if exists is None:
                count = conn.execute("SELECT COUNT(*) FROM tg_members WHERE device_hash = ?", (dev,)).fetchone()[0]
                if count >= max_yards:
                    raise TooMany("too_many_yards",
                                  f"Можно отметить не больше {max_yards} дворов. Снимите отметку с другого двора.")
                conn.execute("INSERT INTO tg_members (yard_id, device_hash, created_at) VALUES (?, ?, ?)",
                             (yard_id, dev, iso(self.now())))
                created = True
            members = conn.execute(f"SELECT {MEMBERS_SQL} FROM tg_yards y WHERE y.id = ?", (yard_id,)).fetchone()[0]
        return members, created

    def leave_yard(self, yard_id: str, device_id: str) -> tuple[int, bool]:
        dev = self.device_hash(device_id)
        with self._tx() as conn:
            if conn.execute("SELECT 1 FROM tg_yards WHERE id = ?", (yard_id,)).fetchone() is None:
                raise LookupError(yard_id)
            cur = conn.execute("DELETE FROM tg_members WHERE yard_id = ? AND device_hash = ?", (yard_id, dev))
            # «Старший по двору» с этого устройства перестаёт им быть вместе с уходом из двора.
            conn.execute("UPDATE tg_yards SET captain_name = NULL, captain_status = NULL, captain_hash = NULL, "
                         "captain_since = NULL, updated_at = ? WHERE id = ? AND captain_hash = ?",
                         (iso(self.now()), yard_id, dev))
            members = conn.execute(f"SELECT {MEMBERS_SQL} FROM tg_yards y WHERE y.id = ?", (yard_id,)).fetchone()[0]
        return members, cur.rowcount == 1

    def set_captain(self, yard_id: str, device_id: str, display_name: str | None) -> dict:
        """«Старший по двору»: только соседу этого двора; имя — на проверку. None — снять себя одним действием."""
        dev = self.device_hash(device_id)
        at = iso(self.now())
        with self._tx() as conn:
            row = conn.execute("SELECT captain_hash FROM tg_yards WHERE id = ?", (yard_id,)).fetchone()
            if row is None:
                raise LookupError(yard_id)
            if conn.execute("SELECT 1 FROM tg_members WHERE yard_id = ? AND device_hash = ?",
                            (yard_id, dev)).fetchone() is None:
                raise Conflict("not_member", "Сначала отметьте «Я живу здесь».")
            if display_name is None:
                if row["captain_hash"] == dev:
                    conn.execute("UPDATE tg_yards SET captain_name = NULL, captain_status = NULL, captain_hash = NULL, "
                                 "captain_since = NULL, updated_at = ? WHERE id = ?", (at, yard_id))
            else:
                if row["captain_hash"] not in (None, dev):
                    raise Conflict("captain_taken", "У двора уже есть старший.")
                conn.execute("UPDATE tg_yards SET captain_name = ?, captain_status = 'on_review', captain_hash = ?, "
                             "captain_since = ?, updated_at = ? WHERE id = ?", (display_name, dev, at, at, yard_id))
        return self.yard(yard_id)

    def moderate_captain(self, yard_id: str, publish: bool) -> dict:
        at = iso(self.now())
        with self._tx() as conn:
            row = conn.execute("SELECT captain_status FROM tg_yards WHERE id = ?", (yard_id,)).fetchone()
            if row is None or row["captain_status"] is None:
                raise LookupError(yard_id)
            if publish:
                conn.execute("UPDATE tg_yards SET captain_status = 'published', updated_at = ? WHERE id = ?",
                             (at, yard_id))
            else:
                conn.execute("UPDATE tg_yards SET captain_name = NULL, captain_status = NULL, captain_hash = NULL, "
                             "captain_since = NULL, updated_at = ? WHERE id = ?", (at, yard_id))
        return self.yard(yard_id)

    def captains_on_review(self, limit: int = 50) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute("SELECT id, label_ru, label_kk, district, captain_name, captain_since FROM tg_yards "
                                "WHERE captain_status = 'on_review' ORDER BY captain_since LIMIT ?",
                                (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ инициативы: запись
    def create(self, fields: dict, *, device_id: str | None, request_id: str | None = None, status: str = "on_review",
               max_on_review: int = 3, max_per_day: int = 5, actor: str | None = None) -> tuple[dict, bool]:
        """Новая инициатива. Повтор того же request_id с того же устройства — та же запись (created=False).

        Лимиты устройства (лимиты по адресу клиента ставит шлюз R01): не больше max_on_review на проверке
        одновременно и max_per_day за сутки — иначе TooMany. Создание из идеи сотрудником (actor) — без лимитов.
        """
        dev = self.device_hash(device_id) if device_id else None
        req = hashlib.sha256(f"{dev}:{request_id}".encode()).hexdigest() if (request_id and dev) else None
        now = self.now()
        at = iso(now)
        with self._tx() as conn:
            if req:
                row = conn.execute("SELECT id FROM tg_initiatives WHERE request_hash = ?", (req,)).fetchone()
                if row is not None:
                    return self._get(conn, row[0]), False
            if dev and actor is None:
                pending = conn.execute("SELECT COUNT(*) FROM tg_initiatives WHERE author_hash = ? AND status = 'on_review'",
                                       (dev,)).fetchone()[0]
                if pending >= max_on_review:
                    raise TooMany("too_many_on_review",
                                  "С этого устройства уже есть инициативы на проверке. Дождитесь, пока их проверят.")
                today = conn.execute("SELECT COUNT(*) FROM tg_initiatives WHERE author_hash = ? AND created_at >= ?",
                                     (dev, iso(now - timedelta(days=1)))).fetchone()[0]
                if today >= max_per_day:
                    raise TooMany("too_many_today", "Сегодня с этого устройства уже предложено много дел. "
                                                    "Попробуйте завтра.", retry_after=6 * 3600)
            iid = fields.get("id") or ("i-" + secrets.token_hex(6))
            target = fields.get("target") or {}
            if target.get("kind") == "area" and target.get("id"):
                self.upsert_yard(conn, target["id"], label_ru=target.get("label_ru"), label_kk=target.get("label_kk"),
                                 district=fields.get("district"), point=fields.get("point"))
            conn.execute(
                "INSERT INTO tg_initiatives (id, kind, title, text, title_public, text_public, lang, target_kind, "
                "target_id, label_ru, label_kk, lon, lat, district, starts_at, ends_at, bring_json, status, author_hash, "
                "request_hash, moderation_json, from_idea, created_at, published_at, updated_at, moderated_by, "
                "moderated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (iid, fields["kind"], fields["title"], fields.get("text") or "", fields.get("title_public"),
                 fields.get("text_public"), fields.get("lang") or "ru", target.get("kind"), target.get("id"),
                 target.get("label_ru"), target.get("label_kk"), fields["point"][0], fields["point"][1],
                 fields.get("district"), fields["starts_at"], fields.get("ends_at"),
                 _dumps(fields.get("bring") or []), status, dev, req, _dumps(fields.get("moderation") or {}),
                 fields.get("from_idea"), at, at if status == "published" else None, at,
                 actor if status == "published" else None, at if status == "published" else None))
            if status == "published":
                self._published_events(conn, iid, target.get("id"), at)
            return self._get(conn, iid), True

    def _published_events(self, conn, iid: str, yard_id: str | None, at: str, demo: bool = False) -> None:
        self._event(conn, at, "published", "author", initiative_id=iid, yard_id=yard_id, demo=demo)
        if yard_id:
            self._event(conn, at, "published", "yard", initiative_id=iid, yard_id=yard_id, demo=demo)

    def moderate(self, iid: str, action: str, *, actor: str, reason: str | None = None) -> dict:
        """publish | hide | cancel — решение сотрудника. Проверенная запись не проверяется второй раз."""
        at = iso(self.now())
        with self._tx() as conn:
            row = conn.execute("SELECT status, target_id, demo FROM tg_initiatives WHERE id = ?", (iid,)).fetchone()
            if row is None:
                raise LookupError(iid)
            status, yard_id, demo = row["status"], row["target_id"], bool(row["demo"])
            if action == "publish":
                if status != "on_review":
                    raise Conflict("already_moderated", "Инициатива уже проверена.")
                conn.execute("UPDATE tg_initiatives SET status = 'published', published_at = ?, moderated_by = ?, "
                             "moderated_at = ?, updated_at = ? WHERE id = ?", (at, actor, at, at, iid))
                self._published_events(conn, iid, yard_id, at, demo)
            elif action == "hide":
                if status in ("hidden", "done"):
                    raise Conflict("already_moderated", "Эту инициативу уже нельзя снять.")
                conn.execute("UPDATE tg_initiatives SET status = 'hidden', hide_reason = ?, moderated_by = ?, "
                             "moderated_at = ?, updated_at = ? WHERE id = ?", (reason or "other", actor, at, at, iid))
                self._event(conn, at, "hidden", "author", initiative_id=iid, yard_id=yard_id, demo=demo)
            elif action == "cancel":
                if status != "published":
                    raise Conflict("not_published", "Отменить можно только опубликованную инициативу.")
                conn.execute("UPDATE tg_initiatives SET status = 'cancelled', moderated_by = ?, moderated_at = ?, "
                             "updated_at = ? WHERE id = ?", (actor, at, at, iid))
                self._event(conn, at, "cancelled", "joined", initiative_id=iid, yard_id=yard_id, demo=demo)
                if yard_id:
                    self._event(conn, at, "cancelled", "yard", initiative_id=iid, yard_id=yard_id, demo=demo)
            else:
                raise ValueError(action)
            return self._get(conn, iid)

    def support(self, iid: str, support: dict, *, actor: str) -> dict:
        """«Поддержать» (акимат): инвентарь, вывоз мусора службой (задача оператору вывоза — R17), заметка."""
        at = iso(self.now())
        with self._tx() as conn:
            row = conn.execute("SELECT status, target_id, support_json, demo FROM tg_initiatives WHERE id = ?",
                               (iid,)).fetchone()
            if row is None:
                raise LookupError(iid)
            if row["status"] != "published":
                raise Conflict("not_published", "Поддержать можно опубликованную инициативу до её проведения.")
            first = not (_loads(row["support_json"]) or {}).get("by_akimat")
            value = dict(support, by_akimat=True, at=at)
            conn.execute("UPDATE tg_initiatives SET support_json = ?, updated_at = ?, moderated_by = COALESCE(moderated_by, ?) "
                         "WHERE id = ?", (_dumps(value), at, actor, iid))
            # Первое «Поддержано акиматом» — событие пришедшим и двору; уточнение заметки — только пришедшим.
            self._event(conn, at, "supported", "joined", initiative_id=iid, yard_id=row["target_id"], demo=bool(row["demo"]))
            if first and row["target_id"]:
                self._event(conn, at, "supported", "yard", initiative_id=iid, yard_id=row["target_id"],
                            demo=bool(row["demo"]))
            return self._get(conn, iid)

    def join(self, iid: str, device_id: str) -> tuple[dict, bool]:
        """«Я приду»: только опубликованная инициатива; повтор с того же устройства не считается."""
        dev = self.device_hash(device_id)
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM tg_initiatives WHERE id = ?", (iid,)).fetchone()
            if row is None or row["status"] in ("on_review", "hidden"):
                raise LookupError(iid)
            if row["status"] != "published":
                raise Conflict("closed", "Запись закрыта: инициатива уже прошла или отменена.")
            cur = conn.execute("INSERT OR IGNORE INTO tg_joins (initiative_id, device_hash, created_at) VALUES (?, ?, ?)",
                               (iid, dev, iso(self.now())))
            joined = conn.execute(f"SELECT {JOINED_SQL} FROM tg_initiatives i WHERE i.id = ?", (iid,)).fetchone()[0]
        return {"id": iid, "joined": joined, "my_join": True}, cur.rowcount == 1

    def leave(self, iid: str, device_id: str) -> tuple[dict, bool]:
        dev = self.device_hash(device_id)
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM tg_initiatives WHERE id = ?", (iid,)).fetchone()
            if row is None or row["status"] in ("on_review", "hidden"):
                raise LookupError(iid)
            if row["status"] != "published":
                raise Conflict("closed", "Инициатива уже прошла или отменена.")
            cur = conn.execute("DELETE FROM tg_joins WHERE initiative_id = ? AND device_hash = ?", (iid, dev))
            joined = conn.execute(f"SELECT {JOINED_SQL} FROM tg_initiatives i WHERE i.id = ?", (iid,)).fetchone()[0]
        return {"id": iid, "joined": joined, "my_join": False}, cur.rowcount == 1

    def is_author(self, iid: str, device_id: str | None) -> bool:
        if not device_id:
            return False
        with self._read() as conn:
            row = conn.execute("SELECT author_hash FROM tg_initiatives WHERE id = ?", (iid,)).fetchone()
        return bool(row and row[0] and row[0] == self.device_hash(device_id))

    def report(self, iid: str, *, text: str | None, text_public: str | None, moderation: dict | None,
               by_role: str, publish: bool, photos: list[dict] | None = None, max_photos: int = 3) -> dict:
        """Отчёт «Сделано вместе». Сотрудник — публикуется сразу и инициатива становится «сделано»;
        автор — отчёт на проверку (инициатива остаётся опубликованной до решения сотрудника).
        photos — [{mime, data, thumb, thumb_mime, width, height}] уже без метаданных (photos.py)."""
        at = iso(self.now())
        with self._tx() as conn:
            row = conn.execute(f"SELECT status, target_id, demo, {JOINED_SQL} AS joined FROM tg_initiatives i "
                               "WHERE i.id = ?", (iid,)).fetchone()
            if row is None or row["status"] in ("on_review", "hidden"):
                raise LookupError(iid)
            if row["status"] == "cancelled":
                raise Conflict("cancelled", "Инициатива отменена.")
            old = conn.execute("SELECT * FROM tg_reports WHERE initiative_id = ?", (iid,)).fetchone()
            if row["status"] == "done" and by_role != "staff":
                raise Conflict("already_done", "Отчёт уже опубликован.")
            have = conn.execute("SELECT COUNT(*) FROM tg_photos WHERE initiative_id = ?", (iid,)).fetchone()[0]
            if photos and have + len(photos) > max_photos:
                raise Conflict("too_many_photos", f"Не больше {max_photos} фото «после».")
            if old is None and not text:
                raise ValueError("text")
            status = "published" if publish else "on_review"
            if old is None:
                conn.execute("INSERT INTO tg_reports (initiative_id, text, text_public, status, joined_final, by_role, "
                             "moderation_json, created_at, published_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (iid, text or "", text_public, status, row["joined"] if publish else None, by_role,
                              _dumps(moderation or {}), at, at if publish else None, at))
            else:
                conn.execute("UPDATE tg_reports SET text = COALESCE(?, text), text_public = CASE WHEN ? IS NULL THEN "
                             "text_public ELSE ? END, status = CASE WHEN status = 'published' THEN 'published' ELSE ? END, "
                             "joined_final = COALESCE(joined_final, ?), moderation_json = COALESCE(?, moderation_json), "
                             "published_at = COALESCE(published_at, ?), updated_at = ? WHERE initiative_id = ?",
                             (text, text, text_public, status, row["joined"] if publish else None,
                              _dumps(moderation) if moderation else None, at if publish else None, at, iid))
            for photo in photos or []:
                conn.execute("INSERT INTO tg_photos (id, initiative_id, mime, data, thumb, thumb_mime, width, height, "
                             "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             ("p-" + secrets.token_hex(6), iid, photo["mime"], photo["data"], photo.get("thumb"),
                              photo.get("thumb_mime"), photo.get("width"), photo.get("height"), at))
            if publish and row["status"] == "published":
                self._mark_done(conn, iid, row["target_id"], at, bool(row["demo"]))
            return self._get(conn, iid)

    def _mark_done(self, conn, iid: str, yard_id: str | None, at: str, demo: bool) -> None:
        conn.execute("UPDATE tg_initiatives SET status = 'done', done_at = ?, updated_at = ? WHERE id = ?", (at, at, iid))
        self._event(conn, at, "done", "joined", initiative_id=iid, yard_id=yard_id, demo=demo)
        self._event(conn, at, "done", "author", initiative_id=iid, yard_id=yard_id, demo=demo)
        if yard_id:
            self._event(conn, at, "done", "yard", initiative_id=iid, yard_id=yard_id, demo=demo)

    def moderate_report(self, iid: str, publish: bool) -> dict:
        """Отчёт автора: опубликовать (инициатива — «сделано») или снять (фото удаляются, инициатива как была)."""
        at = iso(self.now())
        with self._tx() as conn:
            row = conn.execute(f"SELECT status, target_id, demo, {JOINED_SQL} AS joined FROM tg_initiatives i "
                               "WHERE i.id = ?", (iid,)).fetchone()
            rep = conn.execute("SELECT status FROM tg_reports WHERE initiative_id = ?", (iid,)).fetchone()
            if row is None or rep is None:
                raise LookupError(iid)
            if rep["status"] != "on_review":
                raise Conflict("already_moderated", "Отчёт уже проверен.")
            if publish:
                conn.execute("UPDATE tg_reports SET status = 'published', published_at = ?, joined_final = ?, "
                             "updated_at = ? WHERE initiative_id = ?", (at, row["joined"], at, iid))
                if row["status"] == "published":
                    self._mark_done(conn, iid, row["target_id"], at, bool(row["demo"]))
            else:
                conn.execute("DELETE FROM tg_reports WHERE initiative_id = ?", (iid,))
                conn.execute("DELETE FROM tg_photos WHERE initiative_id = ? AND demo = 0", (iid,))
            return self._get(conn, iid)

    # ------------------------------------------------------------------ инициативы: чтение
    _COLUMNS = ("i.id, i.kind, i.title, i.text, i.title_public, i.text_public, i.lang, i.target_kind, i.target_id, "
                "i.label_ru, i.label_kk, i.lon, i.lat, i.district, i.starts_at, i.ends_at, i.bring_json, i.status, "
                "i.author_hash, i.support_json, i.moderation_json, i.hide_reason, i.from_idea, i.created_at, "
                "i.published_at, i.done_at, i.updated_at, i.demo")

    def _get(self, conn, iid: str) -> dict:
        row = conn.execute(f"SELECT {self._COLUMNS}, {JOINED_SQL} AS joined FROM tg_initiatives i WHERE i.id = ?",
                           (iid,)).fetchone()
        if row is None:
            raise LookupError(iid)
        return self._decorate(conn, dict(row))

    def _decorate(self, conn, item: dict) -> dict:
        item["bring"] = _loads(item.pop("bring_json", None), [])
        item["support"] = _loads(item.pop("support_json", None))
        item["moderation"] = _loads(item.pop("moderation_json", None), {})
        rep = conn.execute("SELECT text, text_public, status, joined_final, by_role, published_at, created_at, demo "
                           "FROM tg_reports WHERE initiative_id = ?", (item["id"],)).fetchone()
        item["report"] = dict(rep) if rep else None
        photos = conn.execute("SELECT id, mime, src, width, height, demo, thumb IS NOT NULL AS has_thumb, created_at "
                              "FROM tg_photos WHERE initiative_id = ? ORDER BY created_at, id", (item["id"],)).fetchall()
        item["photos"] = [dict(p) for p in photos]
        return item

    def get(self, iid: str) -> dict:
        with self._read() as conn:
            return self._get(conn, iid)

    def photo(self, photo_id: str, *, thumb: bool = False) -> dict | None:
        with self._read() as conn:
            row = conn.execute("SELECT p.id, p.mime, p.data, p.thumb, p.thumb_mime, p.src, p.demo, i.status AS istatus, "
                               "r.status AS rstatus FROM tg_photos p JOIN tg_initiatives i ON i.id = p.initiative_id "
                               "LEFT JOIN tg_reports r ON r.initiative_id = p.initiative_id WHERE p.id = ?",
                               (photo_id,)).fetchone()
        return dict(row) if row else None

    def photo_data(self, iid: str, *, thumbs: bool) -> list[dict]:
        """Фото «после» инициативы с байтами (для data URL в ответе): миниатюра или полное фото."""
        column = "thumb, thumb_mime" if thumbs else "data, mime"
        with self._read() as conn:
            rows = conn.execute(f"SELECT id, src, width, height, demo, {column} FROM tg_photos WHERE initiative_id = ? "
                                "ORDER BY created_at, id", (iid,)).fetchall()
        return [dict(r) for r in rows]

    def list(self, *, statuses, bbox=None, kind=None, yard=None, district=None, author_device=None,
             upcoming_only=False, supported=None, limit: int = 60, order: str = "soon") -> list[dict]:
        where, args = [f"i.status IN ({','.join('?' * len(statuses))})"], list(statuses)
        if supported is True:
            where.append("json_extract(i.support_json, '$.by_akimat') = 1")
        elif supported is False:
            where.append("(i.support_json IS NULL OR COALESCE(json_extract(i.support_json, '$.by_akimat'), 0) = 0)")
        if bbox is not None:
            where.append("i.lon BETWEEN ? AND ? AND i.lat BETWEEN ? AND ?")
            args += [bbox[0], bbox[2], bbox[1], bbox[3]]
        if kind:
            where.append("i.kind = ?")
            args.append(kind)
        if yard:
            where.append("i.target_id = ?")
            args.append(yard)
        if district:
            where.append("i.district = ?")
            args.append(district)
        if author_device:
            where.append("i.author_hash = ?")
            args.append(self.device_hash(author_device))
        if upcoming_only:
            # Ещё не закончилась: конец (или начало + 3 часа) позже, чем сейчас.
            where.append("COALESCE(i.ends_at, i.starts_at) >= ?")
            args.append(iso(self.now() - timedelta(hours=3)))
        order_sql = {
            # Опубликованные — ближайшие первыми; «сделано» — свежие первыми; остальное — по дате создания.
            "soon": "CASE i.status WHEN 'published' THEN 0 WHEN 'done' THEN 1 ELSE 2 END, "
                    "CASE WHEN i.status = 'published' THEN i.starts_at END ASC, "
                    "CASE WHEN i.status = 'done' THEN i.done_at END DESC, i.created_at DESC, i.id",
            "queue": "i.created_at ASC, i.id",
            "recent": "i.updated_at DESC, i.id",
        }[order]
        sql = (f"SELECT {self._COLUMNS}, {JOINED_SQL} AS joined FROM tg_initiatives i WHERE {' AND '.join(where)} "
               f"ORDER BY {order_sql} LIMIT ?")
        with self._read() as conn:
            rows = conn.execute(sql, (*args, int(limit))).fetchall()
            return [self._decorate(conn, dict(r)) for r in rows]

    def count(self, *, statuses, yard=None, district=None, supported=None) -> int:
        where, args = [f"status IN ({','.join('?' * len(statuses))})"], list(statuses)
        if supported is True:
            where.append("json_extract(support_json, '$.by_akimat') = 1")
        elif supported is False:
            where.append("(support_json IS NULL OR COALESCE(json_extract(support_json, '$.by_akimat'), 0) = 0)")
        if yard:
            where.append("target_id = ?")
            args.append(yard)
        if district:
            where.append("district = ?")
            args.append(district)
        with self._read() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM tg_initiatives WHERE {' AND '.join(where)}", args).fetchone()[0]

    def reports_on_review(self, limit: int = 50) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute(f"SELECT {self._COLUMNS}, {JOINED_SQL} AS joined FROM tg_initiatives i JOIN tg_reports r "
                                "ON r.initiative_id = i.id WHERE r.status = 'on_review' ORDER BY r.created_at LIMIT ?",
                                (int(limit),)).fetchall()
            return [self._decorate(conn, dict(r)) for r in rows]

    def joined_by(self, ids: list[str], device_id: str | None) -> set[str]:
        """На какие из инициатив это устройство уже нажало «Я приду»."""
        if not device_id or not ids:
            return set()
        marks = ",".join("?" * len(ids))
        with self._read() as conn:
            rows = conn.execute(f"SELECT initiative_id FROM tg_joins WHERE device_hash = ? AND initiative_id IN ({marks})",
                                (self.device_hash(device_id), *ids)).fetchall()
        return {r[0] for r in rows}

    # ------------------------------------------------------------------ события
    def events_for_device(self, device_id: str, since: str | None, limit: int = 50) -> list[dict]:
        """События для ленты жителя: его дворы, инициативы, куда он записался, и его собственные.

        Соединяем по хэшу устройства на чтении — в самих событиях устройств нет (CONTRACT §10)."""
        dev = self.device_hash(device_id)
        args = [dev, dev, dev]
        since_sql = ""
        if since:
            since_sql = " AND e.at > ?"
            args.append(since)
        sql = ("SELECT e.seq, e.at, e.code, e.audience, e.initiative_id, e.yard_id, e.demo FROM tg_events e WHERE ("
               "(e.audience = 'yard' AND e.yard_id IN (SELECT yard_id FROM tg_members WHERE device_hash = ?)) OR "
               "(e.audience = 'joined' AND e.initiative_id IN (SELECT initiative_id FROM tg_joins WHERE device_hash = ?)) OR "
               "(e.audience = 'author' AND e.initiative_id IN (SELECT id FROM tg_initiatives WHERE author_hash = ?)))"
               + since_sql + " ORDER BY e.at DESC, e.seq DESC LIMIT ?")
        with self._read() as conn:
            rows = conn.execute(sql, (*args, int(limit))).fetchall()
        # Одно событие могло попасть сразу в несколько аудиторий (сосед двора и записался) — одна строка на событие.
        seen, out = set(), []
        for r in rows:
            key = (r["code"], r["initiative_id"], r["yard_id"], r["at"])
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(r))
        return out

    def yard_events(self, yard_id: str, limit: int = 20) -> list[dict]:
        """Публичные события двора (для «Ленты двора»): что опубликовано, поддержано, сделано, отменено."""
        with self._read() as conn:
            rows = conn.execute("SELECT seq, at, code, initiative_id, yard_id, demo FROM tg_events WHERE yard_id = ? AND "
                                "audience = 'yard' ORDER BY at DESC, seq DESC LIMIT ?", (yard_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ демо и демо-мир
    def _reset_initiative(self, conn, iid: str) -> None:
        """Демо-запись — к виду демо-набора: без «Я приду» прошлых показов, событий, отчёта и фото."""
        for table in ("tg_joins", "tg_events", "tg_reports", "tg_photos"):
            conn.execute(f"DELETE FROM {table} WHERE initiative_id = ?", (iid,))
        conn.execute("DELETE FROM tg_initiatives WHERE id = ? AND demo = 1", (iid,))

    def seed_yard(self, conn, yard: dict, reset: bool = False) -> bool:
        exists = conn.execute("SELECT 1 FROM tg_yards WHERE id = ?", (yard["id"],)).fetchone() is not None
        at = iso(self.now())
        if exists and reset and yard.get("demo", True):
            # Повторный засев (R02, R01 при старте): соседи демо-двора — снова число демо-набора, без устройств прошлых
            # показов; старший — как в демо-наборе.
            captain = yard.get("captain") or None
            point = yard.get("point") or (None, None)
            conn.execute("DELETE FROM tg_members WHERE yard_id = ?", (yard["id"],))
            conn.execute("UPDATE tg_yards SET label_ru = COALESCE(?, label_ru), label_kk = COALESCE(?, label_kk), "
                         "district = COALESCE(?, district), lon = COALESCE(?, lon), lat = COALESCE(?, lat), "
                         "base_members = ?, captain_name = ?, captain_status = ?, captain_hash = NULL, captain_since = ?, "
                         "demo = 1, updated_at = ? WHERE id = ?",
                         (yard.get("label_ru"), yard.get("label_kk"), yard.get("district"), point[0], point[1],
                          int(yard.get("members") or 0), captain.get("display_name") if captain else None,
                          "published" if captain else None, captain.get("since") if captain else None, at, yard["id"]))
            return True
        if exists:
            # Демо-двор, уже известный модулю: подписи и число соседей «раньше» — из демо-набора.
            conn.execute("UPDATE tg_yards SET base_members = MAX(base_members, ?), demo = MAX(demo, ?), "
                         "label_ru = COALESCE(label_ru, ?), label_kk = COALESCE(label_kk, ?), "
                         "district = COALESCE(district, ?), lon = COALESCE(lon, ?), lat = COALESCE(lat, ?) WHERE id = ?",
                         (int(yard.get("members") or 0), int(bool(yard.get("demo", True))), yard.get("label_ru"),
                          yard.get("label_kk"), yard.get("district"), *(yard.get("point") or (None, None)), yard["id"]))
            return False
        point = yard.get("point") or (None, None)
        captain = yard.get("captain") or None
        conn.execute("INSERT INTO tg_yards (id, label_ru, label_kk, district, lon, lat, base_members, captain_name, "
                     "captain_status, captain_since, demo, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (yard["id"], yard.get("label_ru"), yard.get("label_kk"), yard.get("district"), point[0], point[1],
                      int(yard.get("members") or 0), captain.get("display_name") if captain else None,
                      "published" if captain else None, captain.get("since") if captain else None,
                      int(bool(yard.get("demo", True))), at, at))
        return True

    def seed_initiative(self, conn, item: dict, reset: bool = False) -> bool:
        """Демо-инициатива по постоянному id. reset=False — повтор ничего не трогает; reset=True — демо-запись
        возвращается к виду демо-набора от нового «сейчас» (сцену 7 можно показать снова: 14 «Я приду», не «сделано»).
        Записи жителей (demo = 0) засев не трогает никогда."""
        row = conn.execute("SELECT demo FROM tg_initiatives WHERE id = ?", (item["id"],)).fetchone()
        if row is not None:
            if not (reset and row["demo"] and item.get("demo", True)):
                return False
            self._reset_initiative(conn, item["id"])
        target = item.get("target") or {}
        status = item["status"]
        conn.execute(
            "INSERT INTO tg_initiatives (id, kind, title, text, title_public, text_public, lang, target_kind, target_id, "
            "label_ru, label_kk, lon, lat, district, starts_at, ends_at, bring_json, status, base_joined, support_json, "
            "moderation_json, from_idea, created_at, published_at, done_at, updated_at, demo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item["id"], item["kind"], item["title"], item.get("text") or "", item.get("title_public"),
             item.get("text_public"), item.get("lang") or "ru", target.get("kind"), target.get("id"),
             target.get("label_ru"), target.get("label_kk"), item["point"][0], item["point"][1], item.get("district"),
             item["starts_at"], item.get("ends_at"), _dumps(item.get("bring") or []), status,
             int(item.get("joined") or 0), _dumps(item["support"]) if item.get("support") else None,
             _dumps(item.get("moderation") or {}), item.get("from_idea"), item["created_at"],
             item.get("published_at"), item.get("done_at"), item.get("updated_at") or item["created_at"],
             int(bool(item.get("demo", True)))))
        demo = bool(item.get("demo", True))
        yard_id = target.get("id") if target.get("kind") == "area" else None
        if status in ("published", "done") and item.get("published_at"):
            self._event(conn, item["published_at"], "published", "yard", initiative_id=item["id"], yard_id=yard_id,
                        demo=demo)
        if item.get("support") and item["support"].get("at"):
            self._event(conn, item["support"]["at"], "supported", "yard", initiative_id=item["id"], yard_id=yard_id,
                        demo=demo)
        report = item.get("report")
        if report:
            conn.execute("INSERT OR IGNORE INTO tg_reports (initiative_id, text, text_public, status, joined_final, by_role, "
                         "moderation_json, created_at, published_at, updated_at, demo) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?, ?, ?)",
                         (item["id"], report.get("text") or "", report.get("text_public"),
                          report.get("status") or "published", report.get("joined"), report.get("by_role") or "staff",
                          report.get("at") or item["created_at"], report.get("at"), report.get("at") or item["created_at"],
                          int(demo)))
            for n, photo in enumerate(report.get("photos") or []):
                conn.execute("INSERT OR IGNORE INTO tg_photos (id, initiative_id, src, width, height, created_at, demo) "
                             "VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (photo["id"], item["id"], photo.get("src"), photo.get("width"), photo.get("height"),
                              report.get("at") or item["created_at"], int(demo)))
        if status == "done" and item.get("done_at"):
            self._event(conn, item["done_at"], "done", "yard", initiative_id=item["id"], yard_id=yard_id, demo=demo)
        return True

    def seed(self, yards: list[dict], initiatives: list[dict], reset: bool = False) -> dict:
        """Демо-набор или часть демо-мира R02: дворы и инициативы. reset=False — идемпотентно (повтор — skipped);
        reset=True — демо-записи заново от нового «сейчас» (reset), новые — inserted."""
        inserted = skipped = was_reset = 0
        with self._tx() as conn:
            for yard in yards:
                existed = conn.execute("SELECT 1 FROM tg_yards WHERE id = ?", (yard["id"],)).fetchone() is not None
                if self.seed_yard(conn, yard, reset=reset):
                    if existed:
                        was_reset += 1
                    else:
                        inserted += 1
                else:
                    skipped += 1
            for item in initiatives:
                target = item.get("target") or {}
                if target.get("kind") == "area" and target.get("id"):
                    # Двор инициативы известен модулю, даже если его нет в списке дворов демо-набора.
                    if conn.execute("SELECT 1 FROM tg_yards WHERE id = ?", (target["id"],)).fetchone() is None:
                        self.seed_yard(conn, {"id": target["id"], "label_ru": target.get("label_ru"),
                                              "label_kk": target.get("label_kk"), "district": item.get("district"),
                                              "point": item.get("point"), "members": 0, "demo": item.get("demo", True)})
                existed = conn.execute("SELECT 1 FROM tg_initiatives WHERE id = ?", (item["id"],)).fetchone() is not None
                if self.seed_initiative(conn, item, reset=reset):
                    if existed:
                        was_reset += 1
                    else:
                        inserted += 1
                else:
                    skipped += 1
        return {"inserted": inserted, "skipped": skipped, "reset": was_reset}
