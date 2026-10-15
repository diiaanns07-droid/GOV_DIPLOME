"""Хранилище «Вопроса акиму» (R13, волна 2 п. 9): таблицы qa_* в той же SQLite, что у шлюза R01.

Что храним:
  qa_questions — вопрос жителя: текст (≤ 300), язык, район, статус pending → published | rejected, ответ акима
                 (ru и/или kk), пометка demo. Автор — только хэш id устройства (сырого id нет ни в базе, ни в WAL).
  qa_votes     — голос «Поддержать»: (вопрос, хэш устройства) — одно устройство, один голос (первичный ключ).
  qa_meta      — соль для хэша устройства (создаётся один раз, случайная).

Раунд 15 (встречи с акимом, ui/civic_meetings): вопрос к встрече — тот же вопрос с meeting_id; голосование за него
закрывается к началу встречи (votes_close_at). Вопросы встреч не попадают в общие списки «Вопроса акиму» и в «Топ-5
недели» (на них отвечают на встрече), но проверяются в общей очереди сотрудника. text_public — текст после фильтра
R04 moderate() (телефоны, ИИН, почта — «***»), flags — что нашёл фильтр (для сотрудника).

Число голосов = base_votes (только у демо-вопросов: «как будто проголосовали раньше», без выдуманных устройств —
R15 S20) + строки qa_votes. Логин сотрудника, который проверил или ответил, хранится, но наружу не отдаётся (R15 S28).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
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
            "device_hash, answer_ru, answer_kk, answered_at, answer_edited_at, demo, meeting_id, votes_close_at, "
            "text_public, flags")
# Поля, добавленные после первой версии таблицы: (имя, тип). Базы раунда 14 получают их при запуске.
_ADDED_COLUMNS = (("answer_edited_at", "TEXT"), ("meeting_id", "TEXT"), ("votes_close_at", "TEXT"),
                  ("text_public", "TEXT"), ("flags", "TEXT"))


def _meeting_filter(where: list, args: list, meeting, prefix: str) -> None:
    """False — общие вопросы, None — все, строка — вопросы этой встречи."""
    if meeting is False:
        where.append(f"{prefix}meeting_id IS NULL")
    elif isinstance(meeting, str):
        where.append(f"{prefix}meeting_id = ?")
        args.append(meeting)


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
        with self._write, self._read() as conn:
            conn.executescript(SCHEMA)
            # R15-S39 (дата правки ответа) и раунд 15 (встречи, фильтр R04): базы до этих полей получают их здесь.
            have = {r[1] for r in conn.execute("PRAGMA table_info(qa_questions)")}
            for name, kind in _ADDED_COLUMNS:
                if name not in have:
                    try:
                        conn.execute(f"ALTER TABLE qa_questions ADD COLUMN {name} {kind}")
                    except sqlite3.OperationalError as exc:  # второй процесс успел добавить поле раньше
                        if "duplicate column" not in str(exc).lower():
                            raise
            conn.execute("CREATE INDEX IF NOT EXISTS qa_questions_meeting ON qa_questions (meeting_id, status)")
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
               max_pending: int = 3, max_per_day: int = 5, meeting_id: str | None = None,
               votes_close_at: str | None = None, text_public: str | None = None, flags: list | None = None,
               max_per_meeting: int = 3) -> tuple[dict, bool]:
        """Новый вопрос на проверке. Повтор того же request_id с того же устройства — тот же вопрос (created=False).

        Ограничения устройства (лимиты по адресу ставит шлюз R01): не больше max_pending вопросов на проверке
        одновременно и max_per_day вопросов за сутки — иначе Conflict("too_many"). Вопрос к встрече (meeting_id) —
        ещё не больше max_per_meeting вопросов к одной встрече с устройства.
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
            if meeting_id:
                mine = conn.execute("SELECT COUNT(*) FROM qa_questions WHERE device_hash = ? AND meeting_id = ? "
                                    "AND status != 'rejected'", (dev, meeting_id)).fetchone()[0]
                if mine >= max_per_meeting:
                    raise Conflict("too_many_meeting", "К этой встрече с устройства уже есть 3 вопроса.")
            qid = "q-" + secrets.token_hex(6)
            conn.execute("INSERT INTO qa_questions (id, text, lang, district, status, created_at, device_hash, "
                         "request_hash, meeting_id, votes_close_at, text_public, flags) "
                         "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
                         (qid, text, lang, district, iso(now), dev, req, meeting_id, votes_close_at,
                          text_public if text_public and text_public != text else None,
                          json.dumps(sorted(set(flags)), ensure_ascii=False) if flags else None))
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
            row = conn.execute("SELECT status, answered_at, votes_close_at FROM qa_questions WHERE id = ?",
                               (question_id,)).fetchone()
            if row is None or row["status"] != "published":
                raise LookupError(question_id)
            if row["answered_at"]:
                raise Conflict("answered", "На этот вопрос уже ответили.")
            if row["votes_close_at"] and row["votes_close_at"] <= iso(self.now()):
                raise Conflict("closed", "Встреча уже началась — голосование закрыто.")
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

    def seed(self, rows: list[dict], *, refresh: bool = False) -> int:
        """Демо-набор (demo=1): вставка по постоянным id, повтор ничего не дублирует и не возвращает снятое.

        refresh=True (встречи раунда 15): у уже засеянных демо-вопросов обновить время, голоса-основу, ответ и встречу —
        от момента этого запуска (иначе вопросы «ближайшей» встречи стареют вместе с ней). Статус не трогаем: снятый
        сотрудником вопрос (личные данные) не возвращается (R15 S20)."""
        made = 0
        with self._tx() as conn:
            for r in rows:
                if refresh:
                    conn.execute(
                        "UPDATE qa_questions SET created_at = ?, published_at = CASE WHEN status = 'published' THEN ? "
                        "ELSE published_at END, base_votes = ?, answer_ru = ?, answer_kk = ?, answered_at = ?, "
                        "meeting_id = ?, votes_close_at = ? WHERE id = ? AND demo = 1",
                        (r["created_at"], r.get("published_at") or r["created_at"], int(r.get("base_votes") or 0),
                         r.get("answer_ru"), r.get("answer_kk"), r.get("answered_at"), r.get("meeting_id"),
                         r.get("votes_close_at"), r["id"]))
                cur = conn.execute(
                    "INSERT OR IGNORE INTO qa_questions (id, text, lang, district, status, created_at, published_at, "
                    "base_votes, answer_ru, answer_kk, answered_at, demo, meeting_id, votes_close_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (r["id"], r["text"], r["lang"], r["district"], r["status"], r["created_at"], r.get("published_at"),
                     int(r.get("base_votes") or 0), r.get("answer_ru"), r.get("answer_kk"), r.get("answered_at"),
                     r.get("meeting_id"), r.get("votes_close_at")))
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
             order: str = "votes", limit: int = 30, meeting: str | bool | None = False) -> list[dict]:
        """Вопросы со статусом status. order: votes (больше голосов, потом раньше опубликован), new, answered, queue.

        meeting: False — только общие вопросы (без встречи), None — все, строка — вопросы этой встречи.
        """
        where, args = ["q.status = ?"], [status]
        _meeting_filter(where, args, meeting, "q.")
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
              answered_since: str | None = None, meeting: str | bool | None = False) -> int:
        where, args = ["status = ?"], [status]
        _meeting_filter(where, args, meeting, "")
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

    # ------------------------------------------------------------------ встречи (раунд 15)
    def set_votes_close(self, meeting_id: str, close_at: str | None) -> int:
        """Встречу перенесли: голосование за её вопросы закрывается к новому началу."""
        with self._tx() as conn:
            return conn.execute("UPDATE qa_questions SET votes_close_at = ? WHERE meeting_id = ?",
                                (close_at, meeting_id)).rowcount

    def meeting_counts(self, meeting_ids: list[str]) -> dict[str, dict]:
        """{meeting_id: {"published": n, "pending": n, "answered": n}} — для списка встреч и сотрудника."""
        out = {mid: {"published": 0, "pending": 0, "answered": 0} for mid in meeting_ids}
        if not meeting_ids:
            return out
        marks = ",".join("?" * len(meeting_ids))
        sql = (f"SELECT meeting_id, status, answered_at IS NOT NULL AS answered, COUNT(*) FROM qa_questions "
               f"WHERE meeting_id IN ({marks}) GROUP BY meeting_id, status, answered")
        with self._read() as conn:
            for mid, status, answered, n in conn.execute(sql, meeting_ids):
                row = out.setdefault(mid, {"published": 0, "pending": 0, "answered": 0})
                if status == "published":
                    row["published"] += n
                    if answered:
                        row["answered"] += n
                elif status == "pending":
                    row["pending"] += n
        return out

    def device_meeting_questions(self, device_id: str) -> list[dict]:
        """Вопросы этого устройства к встречам (для ленты: «вопрос опубликован», «на встрече ответили»)."""
        dev = self.device_hash(device_id)
        with self._read() as conn:
            rows = conn.execute("SELECT id, meeting_id, status, published_at, answered_at, text, text_public "
                                "FROM qa_questions WHERE device_hash = ? AND meeting_id IS NOT NULL", (dev,))
            return [dict(r) for r in rows.fetchall()]

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
