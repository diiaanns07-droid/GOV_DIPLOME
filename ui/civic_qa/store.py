"""Хранилище «Вопроса акиму» (R13, волна 2 п. 9): таблицы qa_* в той же SQLite, что у шлюза R01.

Что храним:
  qa_questions — вопрос жителя: текст (≤ 300), язык, район, статус pending → published | rejected, ответ акима
                 (ru и/или kk), пометка demo. Автор — только хэш id устройства (сырого id нет ни в базе, ни в WAL).
  qa_votes     — голос «Поддержать»: (вопрос, хэш устройства) — одно устройство, один голос (первичный ключ).
  qa_meta      — соль для хэша устройства (создаётся один раз, случайная).

Число голосов = base_votes (только у демо-вопросов: «как будто проголосовали раньше», без выдуманных устройств —
R15 S20) + строки qa_votes. Логин сотрудника, который проверил или ответил, хранится, но наружу не отдаётся (R15 S28).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qa_questions (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    lang TEXT NOT NULL,
    district TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'published', 'rejected')),
    created_at TEXT NOT NULL,
    published_at TEXT,
    rejected_at TEXT,
    reject_reason TEXT,
    reject_note TEXT,
    moderated_by TEXT,
    device_hash TEXT,
    request_hash TEXT UNIQUE,
    base_votes INTEGER NOT NULL DEFAULT 0,
    answer_ru TEXT,
    answer_kk TEXT,
    answered_at TEXT,
    answered_by TEXT,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS qa_questions_status ON qa_questions (status, published_at);
CREATE INDEX IF NOT EXISTS qa_questions_device ON qa_questions (device_hash, status);
CREATE TABLE IF NOT EXISTS qa_votes (
    question_id TEXT NOT NULL,
    device_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (question_id, device_hash)
);
"""

# Сколько голосов у вопроса: демо-основа + настоящие голоса устройств.
_VOTES = "(q.base_votes + (SELECT COUNT(*) FROM qa_votes v WHERE v.question_id = q.id))"
_COLUMNS = ("id, text, lang, district, status, created_at, published_at, rejected_at, reject_reason, reject_note, "
            "device_hash, answer_ru, answer_kk, answered_at, answer_edited_at, demo")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class Conflict(Exception):
    """Действие не подходит к текущему состоянию вопроса (уже проверен, ещё не опубликован…) — ответ 409."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class QuestionStore:
    """Доступ к таблицам qa_*. Безопасен для потоков сервера: запись — под блокировкой, соединение на вызов."""

    def __init__(self, db_path: str, clock=utc_now):
        self.db_path = str(db_path)
        self.clock = clock
        self._write = threading.Lock()
        with self._read() as conn:
            conn.executescript(SCHEMA)
            # R15-S39: правка ответа видна всем (дата правки); базы до этого поля получают его здесь.
            if "answer_edited_at" not in {r[1] for r in conn.execute("PRAGMA table_info(qa_questions)")}:
                conn.execute("ALTER TABLE qa_questions ADD COLUMN answer_edited_at TEXT")
        with self._tx() as conn:
            conn.execute("INSERT OR IGNORE INTO qa_meta (key, value) VALUES ('device_salt', ?)", (secrets.token_hex(16),))
            self._salt = conn.execute("SELECT value FROM qa_meta WHERE key = 'device_salt'").fetchone()[0]

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
        """Запись одной транзакцией (BEGIN IMMEDIATE): проверка лимитов и вставка не разрываются другим потоком."""
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
        return hashlib.sha256(f"birge-qa:{self._salt}:{device_id}".encode()).hexdigest()

    # ------------------------------------------------------------------ запись
    def create(self, *, text: str, lang: str, district: str, device_id: str, request_id: str | None = None,
               max_pending: int = 3, max_per_day: int = 5) -> tuple[dict, bool]:
        """Новый вопрос на проверке. Повтор того же request_id с того же устройства — тот же вопрос (created=False).

        Ограничения устройства (лимиты по адресу ставит шлюз R01): не больше max_pending вопросов на проверке
        одновременно и max_per_day вопросов за сутки — иначе Conflict("too_many").
        """
        dev = self.device_hash(device_id)
        req = hashlib.sha256(f"{dev}:{request_id}".encode()).hexdigest() if request_id else None
        now = self.now()
        with self._tx() as conn:
            if req:
                row = conn.execute(f"SELECT {_COLUMNS}, {_VOTES} AS votes FROM qa_questions q WHERE request_hash = ?",
                                   (req,)).fetchone()
                if row is not None:
                    return dict(row), False
            pending = conn.execute("SELECT COUNT(*) FROM qa_questions WHERE device_hash = ? AND status = 'pending'",
                                   (dev,)).fetchone()[0]
            today = conn.execute("SELECT COUNT(*) FROM qa_questions WHERE device_hash = ? AND created_at >= ?",
                                 (dev, iso(now - timedelta(days=1)))).fetchone()[0]
            if pending >= max_pending or today >= max_per_day:
                raise Conflict("too_many", "Слишком много вопросов с этого устройства. Дождитесь проверки.")
            qid = "q-" + secrets.token_hex(6)
            conn.execute("INSERT INTO qa_questions (id, text, lang, district, status, created_at, device_hash, "
                         "request_hash) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
                         (qid, text, lang, district, iso(now), dev, req))
            # Автор поддерживает свой вопрос сам: голос с его устройства (после публикации виден как «Вы поддержали»).
            conn.execute("INSERT OR IGNORE INTO qa_votes (question_id, device_hash, created_at) VALUES (?, ?, ?)",
                         (qid, dev, iso(now)))
            row = conn.execute(f"SELECT {_COLUMNS}, {_VOTES} AS votes FROM qa_questions q WHERE id = ?",
                               (qid,)).fetchone()
        return dict(row), True

    def vote(self, question_id: str, device_id: str) -> tuple[dict, bool]:
        """Голос «Поддержать»: только опубликованный вопрос без ответа; повтор с того же устройства не считается."""
        dev = self.device_hash(device_id)
        with self._tx() as conn:
            row = conn.execute("SELECT status, answered_at FROM qa_questions WHERE id = ?", (question_id,)).fetchone()
            if row is None or row["status"] != "published":
                raise LookupError(question_id)
            if row["answered_at"]:
                raise Conflict("answered", "На этот вопрос уже ответили.")
            cur = conn.execute("INSERT OR IGNORE INTO qa_votes (question_id, device_hash, created_at) VALUES (?, ?, ?)",
                               (question_id, dev, iso(self.now())))
            created = cur.rowcount == 1
            votes = conn.execute(f"SELECT {_VOTES} FROM qa_questions q WHERE id = ?", (question_id,)).fetchone()[0]
        return {"id": question_id, "votes": votes, "my_vote": True}, created

    def publish(self, question_id: str, actor: str) -> dict:
        with self._tx() as conn:
            row = conn.execute("SELECT status FROM qa_questions WHERE id = ?", (question_id,)).fetchone()
            if row is None:
                raise LookupError(question_id)
            if row["status"] != "pending":
                raise Conflict("already_moderated", "Вопрос уже проверен.")
            conn.execute("UPDATE qa_questions SET status = 'published', published_at = ?, moderated_by = ? "
                         "WHERE id = ?", (iso(self.now()), actor, question_id))
        return self.get(question_id)

    def reject(self, question_id: str, reason: str, note: str | None, actor: str) -> dict:
        """Отказ на проверке или снятие опубликованного вопроса; вопрос с ответом не снимаем (ответ видели все)."""
        with self._tx() as conn:
            row = conn.execute("SELECT status, answered_at FROM qa_questions WHERE id = ?", (question_id,)).fetchone()
            if row is None:
                raise LookupError(question_id)
            if row["status"] == "rejected":
                raise Conflict("already_moderated", "Вопрос уже отклонён.")
            # Личные данные снимаем и после ответа (закон о персональных данных); по другим причинам — нет.
            if row["answered_at"] and reason != "personal_data":
                raise Conflict("answered", "На этот вопрос уже ответили — его нельзя снять.")
            conn.execute("UPDATE qa_questions SET status = 'rejected', rejected_at = ?, reject_reason = ?, "
                         "reject_note = ?, moderated_by = ? WHERE id = ?",
                         (iso(self.now()), reason, note, actor, question_id))
        return self.get(question_id)

    def answer(self, question_id: str, answer_ru: str | None, answer_kk: str | None, actor: str) -> dict:
        """Ответ акима на опубликованный вопрос. Повторный ответ правит текст, дата первого ответа сохраняется.

        R15-S39: правка не стирает автора первого ответа (answered_by) и второй язык, если его не прислали; дата
        правки (answer_edited_at) видна жителям — тихо переписать ответ акима нельзя."""
        with self._tx() as conn:
            row = conn.execute("SELECT status, answered_at, answer_ru, answer_kk FROM qa_questions WHERE id = ?",
                               (question_id,)).fetchone()
            if row is None:
                raise LookupError(question_id)
            if row["status"] != "published":
                raise Conflict("not_published", "Сначала опубликуйте вопрос.")
            new_ru = answer_ru if answer_ru is not None else row["answer_ru"]
            new_kk = answer_kk if answer_kk is not None else row["answer_kk"]
            edited = bool(row["answered_at"]) and (new_ru, new_kk) != (row["answer_ru"], row["answer_kk"])
            conn.execute("UPDATE qa_questions SET answer_ru = ?, answer_kk = ?, answered_at = ?, "
                         "answered_by = COALESCE(answered_by, ?), "
                         "answer_edited_at = CASE WHEN ? THEN ? ELSE answer_edited_at END WHERE id = ?",
                         (new_ru, new_kk, row["answered_at"] or iso(self.now()), actor, int(edited), iso(self.now()),
                          question_id))
        return self.get(question_id)

    def seed(self, rows: list[dict]) -> int:
        """Демо-набор (demo=1): вставка по постоянным id, повтор ничего не дублирует и не возвращает снятое."""
        made = 0
        with self._tx() as conn:
            for r in rows:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO qa_questions (id, text, lang, district, status, created_at, published_at, "
                    "base_votes, answer_ru, answer_kk, answered_at, demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (r["id"], r["text"], r["lang"], r["district"], r["status"], r["created_at"], r.get("published_at"),
                     int(r.get("base_votes") or 0), r.get("answer_ru"), r.get("answer_kk"), r.get("answered_at")))
                made += cur.rowcount
        return made

    # ------------------------------------------------------------------ чтение
    def get(self, question_id: str) -> dict:
        with self._read() as conn:
            row = conn.execute(f"SELECT {_COLUMNS}, {_VOTES} AS votes FROM qa_questions q WHERE id = ?",
                               (question_id,)).fetchone()
        if row is None:
            raise LookupError(question_id)
        return dict(row)

    def list(self, *, status: str, answered: bool | None = None, district: str | None = None,
             order: str = "votes", limit: int = 30) -> list[dict]:
        """Вопросы со статусом status. order: votes (больше голосов, потом раньше опубликован), new, answered, queue."""
        where, args = ["q.status = ?"], [status]
        if answered is True:
            where.append("q.answered_at IS NOT NULL")
        elif answered is False:
            where.append("q.answered_at IS NULL")
        if district:
            where.append("q.district = ?")
            args.append(district)
        order_sql = {
            "votes": "votes DESC, q.published_at ASC, q.id ASC",
            "new": "q.published_at DESC, q.id DESC",
            "answered": "q.answered_at DESC, q.id DESC",
            "queue": "q.created_at ASC, q.id ASC",
        }[order]
        sql = (f"SELECT {_COLUMNS}, {_VOTES} AS votes FROM qa_questions q WHERE {' AND '.join(where)} "
               f"ORDER BY {order_sql} LIMIT ?")
        with self._read() as conn:
            return [dict(r) for r in conn.execute(sql, (*args, int(limit))).fetchall()]

    def count(self, *, status: str, answered: bool | None = None, district: str | None = None,
              answered_since: str | None = None) -> int:
        where, args = ["status = ?"], [status]
        if answered is True:
            where.append("answered_at IS NOT NULL")
        elif answered is False:
            where.append("answered_at IS NULL")
        if district:
            where.append("district = ?")
            args.append(district)
        if answered_since:
            where.append("answered_at >= ?")
            args.append(answered_since)
        with self._read() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM qa_questions WHERE {' AND '.join(where)}", args).fetchone()[0]

    def voted(self, question_ids: list[str], device_id: str | None) -> set[str]:
        """За какие из вопросов уже проголосовало это устройство (для «Вы поддержали»)."""
        if not device_id or not question_ids:
            return set()
        dev = self.device_hash(device_id)
        marks = ",".join("?" * len(question_ids))
        with self._read() as conn:
            rows = conn.execute(f"SELECT question_id FROM qa_votes WHERE device_hash = ? AND question_id IN ({marks})",
                                (dev, *question_ids)).fetchall()
        return {r[0] for r in rows}
