"""SQLite-хранилище civic-v1: путь к файлу, соединения, транзакции и миграции.

Политика:
- файл базы лежит вне репозитория либо в <repo>/.runtime/ (папка игнорируется Git);
  каталог web/ и остальные папки проекта запрещены, чтобы базу нельзя было раздать
  статикой или случайно закоммитить;
- одно соединение на операцию (ThreadingHTTPServer создаёт поток на запрос),
  WAL, busy_timeout, внешние ключи; запись — только BEGIN IMMEDIATE;
- миграции только добавляют таблицы/индексы с префиксом civic_; чужие таблицы
  (например feedback_* модуля R06) не читаются и не изменяются; PRAGMA user_version
  не используется, потому что он общий на файл.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / ".runtime"
DEFAULT_DB_PATH = RUNTIME_DIR / "civic.sqlite3"
BUSY_TIMEOUT_MS = 5000


class StorageError(RuntimeError):
    """Ошибка конфигурации или целостности хранилища (не ошибка клиента)."""


# Каждая миграция — список отдельных SQL-операторов. Применённые миграции
# никогда не редактируются: checksum в civic_schema_migrations это проверяет.
MIGRATIONS: list[tuple[int, str, tuple[str, ...]]] = [
    (1, "civic-v1 initial schema", (
        """CREATE TABLE civic_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 32),
            display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
            public_label TEXT NOT NULL CHECK (length(public_label) BETWEEN 1 AND 120),
            role TEXT NOT NULL CHECK (role IN ('editor', 'admin')),
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            password_changed_at TEXT NOT NULL,
            disabled_at TEXT
        )""",
        """CREATE TABLE civic_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES civic_users(id),
            csrf_token TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            revoked_at REAL
        )""",
        "CREATE INDEX civic_sessions_user ON civic_sessions(user_id)",
        """CREATE TABLE civic_login_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username_key TEXT NOT NULL,
            client_key TEXT NOT NULL,
            at REAL NOT NULL
        )""",
        "CREATE INDEX civic_login_failures_user ON civic_login_failures(username_key, client_key, at)",
        "CREATE INDEX civic_login_failures_client ON civic_login_failures(client_key, at)",
        # Рабочая (редакторская) копия объекта. Поля для фильтров вынесены в
        # колонки; полное содержимое civic-v1 — в data_json.
        """CREATE TABLE civic_objects (
            id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
            city TEXT NOT NULL CHECK (city = 'astana'),
            kind TEXT NOT NULL CHECK (kind IN ('construction', 'roadworks', 'landscaping', 'event')),
            status TEXT NOT NULL CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled', 'unknown')),
            publication TEXT NOT NULL CHECK (publication IN ('draft', 'published', 'archived')),
            planned_start TEXT,
            current_planned_end TEXT,
            data_json TEXT NOT NULL,
            internal_notes TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL CHECK (revision >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER REFERENCES civic_users(id),
            updated_by INTEGER REFERENCES civic_users(id),
            first_published_at TEXT,
            published_revision INTEGER,
            import_source TEXT,
            import_external_id TEXT,
            import_digest TEXT,
            import_revision INTEGER,
            UNIQUE (import_source, import_external_id)
        )""",
        "CREATE INDEX civic_objects_order ON civic_objects(updated_at DESC, id DESC)",
        # Публичная проекция: строка существует, только пока объект опубликован.
        # Публичное чтение обращается лишь к этой таблице и к публичной истории,
        # поэтому черновик не может попасть в ответ жителю даже при ошибке фильтра.
        """CREATE TABLE civic_public_objects (
            id TEXT PRIMARY KEY REFERENCES civic_objects(id),
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            planned_start TEXT,
            current_planned_end TEXT,
            revision INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            dto_json TEXT NOT NULL
        )""",
        "CREATE INDEX civic_public_order ON civic_public_objects(updated_at DESC, id DESC)",
        """CREATE TABLE civic_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id TEXT NOT NULL REFERENCES civic_objects(id),
            revision INTEGER NOT NULL,
            at TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('create', 'update', 'publish', 'archive',
                                                   'import_create', 'import_update')),
            publication TEXT NOT NULL,
            changed_fields_json TEXT NOT NULL,
            diff_json TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            actor_kind TEXT NOT NULL CHECK (actor_kind IN ('editor', 'import', 'system')),
            actor_user_id INTEGER REFERENCES civic_users(id),
            actor_label TEXT NOT NULL,
            public_actor_label TEXT NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 0 CHECK (is_public IN (0, 1)),
            public_changed_fields_json TEXT,
            public_dto_json TEXT,
            snapshot_json TEXT NOT NULL,
            UNIQUE (object_id, revision)
        )""",
        "CREATE INDEX civic_history_public ON civic_history(object_id, is_public, revision)",
        # История только дополняется: ни UPDATE, ни DELETE.
        """CREATE TRIGGER civic_history_no_update BEFORE UPDATE ON civic_history
           BEGIN SELECT RAISE(ABORT, 'civic_history is append-only'); END""",
        """CREATE TRIGGER civic_history_no_delete BEFORE DELETE ON civic_history
           BEGIN SELECT RAISE(ABORT, 'civic_history is append-only'); END""",
        # Физического удаления объектов в v1 нет.
        """CREATE TRIGGER civic_objects_no_delete BEFORE DELETE ON civic_objects
           BEGIN SELECT RAISE(ABORT, 'civic_objects rows are archived, not deleted'); END""",
        """CREATE TABLE civic_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            package_digest TEXT NOT NULL,
            at TEXT NOT NULL,
            actor_label TEXT NOT NULL,
            report_json TEXT NOT NULL
        )""",
        # Изменения из нового пакета для объектов, уже изменённых вручную или
        # опубликованных: ждут решения редактора, ничего не перезаписывают.
        """CREATE TABLE civic_import_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_id INTEGER NOT NULL REFERENCES civic_imports(id),
            object_id TEXT NOT NULL REFERENCES civic_objects(id),
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            digest TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (source, external_id, digest)
        )""",
    )),
    # Повторная отправка формы создания (двойной клик, повтор после обрыва сети)
    # с тем же Idempotency-Key возвращает уже созданный черновик.
    (2, "idempotent draft creation", (
        """CREATE TABLE civic_create_requests (
            user_id INTEGER NOT NULL REFERENCES civic_users(id),
            request_key TEXT NOT NULL CHECK (length(request_key) BETWEEN 8 AND 64),
            object_id TEXT NOT NULL REFERENCES civic_objects(id),
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, request_key)
        )""",
    )),
    # Измерено (PERF.txt): счётчик кандидатов импорта на каждую staff-карточку шёл полным проходом.
    (3, "index import candidates by object", (
        "CREATE INDEX civic_import_candidates_object ON civic_import_candidates(object_id)",
    )),
    # Решение редактора по кандидату импорта: applied | dismissed | superseded (строки не удаляются).
    (4, "import candidate resolution", (
        "ALTER TABLE civic_import_candidates ADD COLUMN resolved_at TEXT",
        "ALTER TABLE civic_import_candidates ADD COLUMN resolution TEXT",
        "ALTER TABLE civic_import_candidates ADD COLUMN resolved_by INTEGER REFERENCES civic_users(id)",
    )),
    # След решения редактора: причина, какие поля приняты (частичное принятие) и ревизия объекта
    # после решения. resolution дополнительно может быть partially_applied.
    (5, "import candidate review trail", (
        "ALTER TABLE civic_import_candidates ADD COLUMN resolution_reason TEXT",
        "ALTER TABLE civic_import_candidates ADD COLUMN resolution_fields_json TEXT",
        "ALTER TABLE civic_import_candidates ADD COLUMN resolved_revision INTEGER",
    )),
    # Раунд 14 (R06): этапы объекта, предложения акимата и голоса жителей.
    # Только новые таблицы: civic_objects и civic_history не меняются, поэтому старые записи
    # и их история сохраняются байт в байт. Этап хранится отдельным слоем поверх объекта.
    (6, "round 14 stages, proposals, votes", (
        # Текущий этап объекта. stage NULL — этап неизвестен (status unknown/cancelled).
        # source: migrated — выведен из status при миграции; editor — задан сотрудником; demo — демо-данные.
        """CREATE TABLE civic_object_stages (
            object_id TEXT PRIMARY KEY REFERENCES civic_objects(id),
            stage TEXT CHECK (stage IS NULL OR stage IN ('planned', 'design', 'procurement',
                                                         'construction', 'acceptance', 'operating')),
            planned_end TEXT,
            forecast_end TEXT,
            revision INTEGER NOT NULL CHECK (revision >= 1),
            updated_at TEXT NOT NULL,
            updated_by INTEGER REFERENCES civic_users(id),
            source TEXT NOT NULL CHECK (source IN ('migrated', 'editor', 'demo'))
        )""",
        # История этапов: только дополняется, как civic_history.
        """CREATE TABLE civic_stage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id TEXT NOT NULL REFERENCES civic_objects(id),
            revision INTEGER NOT NULL,
            at TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('migrate', 'set', 'demo')),
            stage TEXT,
            planned_end TEXT,
            forecast_end TEXT,
            reason TEXT NOT NULL DEFAULT '',
            actor_user_id INTEGER REFERENCES civic_users(id),
            actor_label TEXT NOT NULL,
            public_actor_label TEXT NOT NULL,
            UNIQUE (object_id, revision)
        )""",
        """CREATE TRIGGER civic_stage_history_no_update BEFORE UPDATE ON civic_stage_history
           BEGIN SELECT RAISE(ABORT, 'civic_stage_history is append-only'); END""",
        """CREATE TRIGGER civic_stage_history_no_delete BEFORE DELETE ON civic_stage_history
           BEGIN SELECT RAISE(ABORT, 'civic_stage_history is append-only'); END""",
        # Перенос старых записей: этап выводится из status (planned → planned, in_progress →
        # construction, completed → operating; unknown/cancelled → NULL). Плановый срок — исходный
        # original_planned_end (если был), иначе current_planned_end. Время обновления — время объекта,
        # чтобы «давно не обновлялось» считалось честно, а не с момента миграции.
        """INSERT INTO civic_object_stages(object_id, stage, planned_end, forecast_end, revision,
                                           updated_at, updated_by, source)
           SELECT id,
                  CASE status WHEN 'planned' THEN 'planned' WHEN 'in_progress' THEN 'construction'
                              WHEN 'completed' THEN 'operating' ELSE NULL END,
                  COALESCE(json_extract(data_json, '$.schedule.original_planned_end'), current_planned_end),
                  NULL, 1, updated_at, NULL, 'migrated'
           FROM civic_objects""",
        """INSERT INTO civic_stage_history(object_id, revision, at, action, stage, planned_end,
                                           forecast_end, reason, actor_user_id, actor_label, public_actor_label)
           SELECT object_id, 1, updated_at, 'migrate', stage, planned_end, forecast_end,
                  'Этап выведен из статуса при обновлении до раунда 14', NULL, 'migration', 'Birge'
           FROM civic_object_stages""",
        # Предложения акимата (3D-объекты R05). kind — 5 объектов каталога.
        """CREATE TABLE civic_proposals (
            id TEXT PRIMARY KEY CHECK (length(id) BETWEEN 1 AND 64),
            kind TEXT NOT NULL CHECK (kind IN ('square', 'playground', 'sports', 'stop', 'lighting')),
            geometry_json TEXT NOT NULL,
            rotation_deg REAL NOT NULL DEFAULT 0,
            title_ru TEXT NOT NULL,
            title_kk TEXT,
            status TEXT NOT NULL CHECK (status IN ('proposal', 'approved', 'rejected', 'withdrawn')),
            district TEXT,
            planned_year INTEGER,
            demo INTEGER NOT NULL DEFAULT 0 CHECK (demo IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by INTEGER REFERENCES civic_users(id),
            decided_at TEXT,
            decided_by INTEGER REFERENCES civic_users(id),
            decision_reason TEXT NOT NULL DEFAULT ''
        )""",
        "CREATE INDEX civic_proposals_order ON civic_proposals(created_at DESC, id DESC)",
        """CREATE TRIGGER civic_proposals_no_delete BEFORE DELETE ON civic_proposals
           BEGIN SELECT RAISE(ABORT, 'civic_proposals rows are withdrawn, not deleted'); END""",
        """CREATE TABLE civic_proposal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT NOT NULL REFERENCES civic_proposals(id),
            at TEXT NOT NULL,
            action TEXT NOT NULL CHECK (action IN ('create', 'approve', 'reject', 'withdraw')),
            status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            actor_user_id INTEGER REFERENCES civic_users(id),
            actor_label TEXT NOT NULL
        )""",
        """CREATE TRIGGER civic_proposal_history_no_update BEFORE UPDATE ON civic_proposal_history
           BEGIN SELECT RAISE(ABORT, 'civic_proposal_history is append-only'); END""",
        """CREATE TRIGGER civic_proposal_history_no_delete BEFORE DELETE ON civic_proposal_history
           BEGIN SELECT RAISE(ABORT, 'civic_proposal_history is append-only'); END""",
        # Голос: одна строка на (предложение, устройство). Хранится только хэш device_id с солью.
        # Повторное нажатие меняет value в той же строке — счёт не удваивается по построению.
        """CREATE TABLE civic_votes (
            proposal_id TEXT NOT NULL REFERENCES civic_proposals(id),
            device_hash TEXT NOT NULL CHECK (length(device_hash) = 64),
            value INTEGER NOT NULL CHECK (value IN (-1, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (proposal_id, device_hash)
        )""",
        # Соль для хэша устройства: случайная на каждую базу, в ответы не попадает.
        """CREATE TABLE civic_v2_settings (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",
        "INSERT INTO civic_v2_settings(name, value) VALUES ('vote_salt', lower(hex(randomblob(32))))",
    )),
]
SCHEMA_VERSION = MIGRATIONS[-1][0]


def _checksum(statements) -> str:
    digest = hashlib.sha256()
    for statement in statements:
        digest.update(" ".join(statement.split()).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def resolve_db_path(db_path) -> Path:
    """Проверяет, что база не окажется в раздаваемом или коммитимом каталоге."""
    if db_path is None:
        raise StorageError("Укажите путь к файлу базы civic (например .runtime/civic.sqlite3).")
    text = os.fspath(db_path)
    if not text or text == ":memory:" or text.startswith("file:"):
        # Соединение на каждую операцию: база в памяти исчезала бы между запросами.
        raise StorageError("Нужен путь к файлу SQLite; :memory: и URI не поддерживаются.")
    path = Path(text).expanduser().resolve()
    if path.is_relative_to(REPO_ROOT) and not path.is_relative_to(RUNTIME_DIR):
        raise StorageError(
            "База civic должна лежать вне репозитория или в .runtime/: "
            "каталоги проекта (в том числе web/) раздаются или попадают в Git.")
    if path == RUNTIME_DIR:
        raise StorageError("Укажите файл внутри .runtime/, а не сам каталог.")
    return path


def create_private_file(path: Path, *, exclusive: bool = False) -> bool:
    """Создаёт пустой файл с 0600 ДО того, как SQLite его откроет (без окна 0644).

    Пустой файл — корректная пустая база SQLite; -wal/-shm SQLite создаёт с правами основного файла.
    exclusive=True: вернуть False, если файл уже есть (ничего не перезаписывать).
    """
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return not exclusive
    os.close(fd)
    return True


def restrict_permissions(path: Path) -> None:
    """0600 для файла базы/копии на POSIX: внутри хэши паролей и служебные заметки."""
    if os.name == "posix" and path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # чужой файл или ФС без прав — не мешаем запуску


def _prepare_parent(path: Path) -> None:
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_relative_to(RUNTIME_DIR):
        # Самозащита на случай, если корневой .gitignore ещё не знает о .runtime/.
        marker = RUNTIME_DIR / ".gitignore"
        if not marker.exists():
            marker.write_text("# runtime data (SQLite, WAL/SHM, backups) never goes to Git\n*\n",
                              encoding="utf-8")


class Database:
    """Файл SQLite и фабрика коротких соединений. Объект безопасен для потоков."""

    def __init__(self, db_path, *, busy_timeout_ms: int = BUSY_TIMEOUT_MS):
        self.path = resolve_db_path(db_path)
        self.busy_timeout_ms = int(busy_timeout_ms)
        self._lock = threading.Lock()
        self._open = 0  # число открытых соединений (для проверки корректного закрытия)
        # Очередь писателей внутри процесса: потоки ждут на блокировке Python, а не опрашивают
        # SQLite с паузами (под нагрузкой опрос давал «голодание» дольше busy_timeout → 503).
        # busy_timeout остаётся для других процессов (CLI, второй сервер).
        self._writer = threading.Lock()
        self._writer_owner = None
        self.write_queue_timeout = self.busy_timeout_ms / 1000 * 3

    @property
    def open_connections(self) -> int:
        with self._lock:
            return self._open

    def _raw_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000,
                               isolation_level=None, check_same_thread=True)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA synchronous = FULL")
            conn.execute("PRAGMA trusted_schema = OFF")
        except BaseException:
            conn.close()
            raise
        return conn

    @contextmanager
    def connect(self):
        """Соединение на одну операцию; закрывается при любом исходе."""
        conn = self._raw_connect()
        with self._lock:
            self._open += 1
        try:
            yield conn
        finally:
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
            finally:
                conn.close()
                with self._lock:
                    self._open -= 1

    @contextmanager
    def write(self):
        """Транзакция записи: BEGIN IMMEDIATE сразу берёт блокировку записи.

        Так конкурирующие запросы ждут busy_timeout, а не получают
        SQLITE_BUSY при повышении блокировки с чтения до записи.
        Любое исключение откатывает всю транзакцию целиком.
        """
        me = threading.get_ident()
        if self._writer_owner == me:
            raise RuntimeError("Вложенная транзакция записи в том же потоке (передайте conn).")
        if not self._writer.acquire(timeout=self.write_queue_timeout):
            raise sqlite3.OperationalError("database is locked (writer queue timeout)")
        self._writer_owner = me
        try:
            with self.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    yield conn
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                conn.execute("COMMIT")
        finally:
            self._writer_owner = None
            self._writer.release()

    @contextmanager
    def read(self):
        """Согласованное чтение нескольких запросов (снимок WAL)."""
        with self.connect() as conn:
            conn.execute("BEGIN")
            try:
                yield conn
            finally:
                if conn.in_transaction:
                    conn.execute("COMMIT")

    # --- миграции -------------------------------------------------------------

    def applied_migrations(self) -> dict[int, str]:
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='civic_schema_migrations'"
            ).fetchone()
            if not exists:
                return {}
            return {row["version"]: row["checksum"]
                    for row in conn.execute("SELECT version, checksum FROM civic_schema_migrations")}

    def migrate(self, *, now_iso: str | None = None) -> list[int]:
        """Применяет недостающие миграции; повторный вызов ничего не меняет."""
        _prepare_parent(self.path)
        create_private_file(self.path)
        applied_now = []
        with self.connect() as conn:
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            raise StorageError("SQLite не включил WAL; сетевые/только-для-чтения диски не поддерживаются.")
        restrict_permissions(self.path)
        stamp = now_iso or time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        with self.write() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS civic_schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL)""")
            known = {version: checksum for version, _, checksum in
                     ((v, n, _checksum(s)) for v, n, s in MIGRATIONS)}
            rows = conn.execute("SELECT version, checksum FROM civic_schema_migrations").fetchall()
            for row in rows:
                if row["version"] not in known:
                    raise StorageError(
                        f"База создана более новой версией civic_store (миграция {row['version']}). "
                        "Обновите код; понижение версии не выполняется.")
                if row["checksum"] != known[row["version"]]:
                    raise StorageError(f"Миграция {row['version']} в базе отличается от кода.")
            done = {row["version"] for row in rows}
            for version, name, statements in MIGRATIONS:
                if version in done:
                    continue
                for statement in statements:
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO civic_schema_migrations(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                    (version, name, _checksum(statements), stamp))
                applied_now.append(version)
        return applied_now

    def require_current_schema(self) -> None:
        applied = self.applied_migrations()
        if not applied:
            raise StorageError("База civic не инициализирована: выполните "
                               "python -m ui.civic_store init")
        expected = {version for version, _, _ in MIGRATIONS}
        if set(applied) != expected:
            missing = sorted(expected - set(applied))
            raise StorageError(f"Схема базы не совпадает с кодом (нет миграций {missing or '—'}, "
                               f"ожидается {SCHEMA_VERSION}): выполните python -m ui.civic_store init.")

    def checkpoint(self) -> None:
        """Переносит WAL в основной файл (для резервной копии и чистого закрытия)."""
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
