"""Локальные учётные записи редакторов, сессии, CSRF и ограничение попыток входа.

- Пароль: hashlib.scrypt (стандартная библиотека; параметры OWASP-эквивалент
  N=2^14, r=8, p=5), соль 16 байт, формат scrypt$N$r$p$salt$hash. Plaintext не хранится.
- Сессия: случайный токен 256 бит в cookie HttpOnly; SameSite=Strict; Path=/api/civic (v1 и v2)
  (+ Secure по HTTPS). В базе только SHA-256 токена. Простой и абсолютный срок жизни,
  logout отзывает запись на сервере.
- CSRF: отдельный токен сессии, отдаётся в GET /session и сверяется с X-CSRF-Token.
- Неудачные входы: не более 5 за 15 минут на пару логин+клиент и 20 на клиента → 429.
  Попытка резервируется в той же транзакции, что и проверка лимита (параллельные запросы
  не обходят лимит). Логин и адрес хранятся только как хэши.
Ни пароль, ни токены не пишутся в логи и не возвращаются в ошибках.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import re
import secrets
import sqlite3
import threading

from .db import Database
from .objects import Actor, iso, utc_now


SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 5
SCRYPT_MAXMEM = 64 * 1024 * 1024
SALT_BYTES = 16
MIN_PASSWORD = 12
MAX_PASSWORD = 1024
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}\Z")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}\Z")
COOKIE_NAME = "civic_session"
# Раунд 14 (сборка B1, правка R01 — передана R06): сессия нужна и API v2 (/api/civic/v2: статусы жалоб R09,
# этапы и предложения R06). С путём /api/civic/v1 браузер не отправлял cookie на v2. SameSite=Strict и HttpOnly те же.
COOKIE_PATH = "/api/civic"
IDLE_SECONDS = 60 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60
FAIL_WINDOW = 15 * 60
MAX_FAILS_PER_USER_CLIENT = 5
MAX_FAILS_PER_CLIENT = 20
TOUCH_INTERVAL = 60
ROLES = ("editor", "admin")
STAFF_ROLES = frozenset(ROLES)
COMMON_PASSWORDS = frozenset({
    "password1234", "123456789012", "qwertyuiopas", "admin1234567", "administrator",
    "passwordpassword", "111111111111", "000000000000", "astana123456", "qwerty123456",
})
# Ограничение параллельных scrypt (по 16 МиБ) — защита памяти от потока входов.
_KDF_SLOTS = threading.BoundedSemaphore(4)


class AuthError(Exception):
    """Неверные учётные данные или недопустимая сессия (HTTP 401)."""


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Слишком много попыток входа.")
        self.retry_after = max(1, int(retry_after))


class PasswordPolicyError(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    if not isinstance(password, str):
        raise PasswordPolicyError("Пароль должен быть строкой.")
    salt = secrets.token_bytes(SALT_BYTES)
    with _KDF_SLOTS:
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                                p=SCRYPT_P, maxmem=SCRYPT_MAXMEM, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        if not (2 ** 10 <= n <= 2 ** 20 and 1 <= r <= 32 and 1 <= p <= 16):
            return False
        salt_bytes = base64.b64decode(salt, validate=True)
        expected_bytes = base64.b64decode(expected, validate=True)
    except (ValueError, AttributeError):
        return False
    if not isinstance(password, str) or len(password) > MAX_PASSWORD:
        password = ""
    with _KDF_SLOTS:
        actual = hashlib.scrypt(password.encode("utf-8", "surrogatepass"), salt=salt_bytes, n=n,
                                r=r, p=p, maxmem=max(SCRYPT_MAXMEM, 256 * n * r * 2),
                                dklen=len(expected_bytes))
    return hmac.compare_digest(actual, expected_bytes)


_DUMMY_HASH = None
_DUMMY_LOCK = threading.Lock()


def _dummy_hash() -> str:
    global _DUMMY_HASH
    with _DUMMY_LOCK:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password(secrets.token_urlsafe(24))
        return _DUMMY_HASH


def check_password_policy(username: str, password: str) -> None:
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise PasswordPolicyError(f"Пароль: от {MIN_PASSWORD} до {MAX_PASSWORD} символов.")
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or username.lower() in lowered or len(set(password)) < 5:
        raise PasswordPolicyError("Слишком простой пароль: не используйте логин и распространённые пароли.")


def normalize_username(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if USERNAME_RE.match(value) else None


def _key(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8", "surrogatepass")).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Principal:
    """Серверная личность из сессии. Никогда не строится из тела запроса."""
    user_id: int
    username: str
    display_name: str
    role: str
    public_label: str
    csrf_token: str
    session_hash: str
    expires_at: float

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES

    def actor(self) -> Actor:
        return Actor(kind="editor", user_id=self.user_id, label=self.username,
                     public_label=self.public_label)

    def public_user(self) -> dict:
        return {"name": self.display_name, "role": self.role}

    def check_csrf(self, header_value) -> bool:
        return isinstance(header_value, str) and hmac.compare_digest(
            header_value.encode("utf-8", "surrogatepass"), self.csrf_token.encode("ascii"))

    def __repr__(self) -> str:  # токены не попадают в логи даже через repr
        return f"Principal(user_id={self.user_id}, username={self.username!r}, role={self.role!r})"


def parse_cookies(header) -> dict:
    cookies = {}
    if not isinstance(header, str) or len(header) > 8192:
        return cookies
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name and name not in cookies:
            cookies[name] = value.strip().strip('"')
    return cookies


def session_cookie(token: str, *, secure: bool, max_age: int = ABSOLUTE_SECONDS) -> str:
    cookie = f"{COOKIE_NAME}={token}; Path={COOKIE_PATH}; Max-Age={max_age}; HttpOnly; SameSite=Strict"
    return cookie + ("; Secure" if secure else "")


def clear_cookie(*, secure: bool) -> str:
    return session_cookie("", secure=secure, max_age=0)


class Accounts:
    """Учётные записи и сессии поверх Database. Часы внедряются для тестов истечения."""

    def __init__(self, database: Database, clock, *, idle_seconds=IDLE_SECONDS,
                 absolute_seconds=ABSOLUTE_SECONDS):
        self.db = database
        self.clock = clock
        self.idle_seconds = idle_seconds
        self.absolute_seconds = absolute_seconds
        # Заранее: иначе первый вход несуществующего пользователя считал бы два scrypt
        # и по времени отличался бы от неверного пароля существующего.
        _dummy_hash()

    def _now(self) -> float:
        return utc_now(self.clock).timestamp()

    # --- пользователи ---------------------------------------------------------

    def create_user(self, username, password, *, display_name=None, public_label=None,
                    role="editor") -> int:
        name = normalize_username(username)
        if name is None:
            raise PasswordPolicyError("Логин: 3–32 символа a-z, 0-9, точка, дефис, подчёркивание.")
        if role not in ROLES:
            raise PasswordPolicyError("Роль: editor или admin.")
        check_password_policy(name, password)
        display = (display_name or name).strip()[:120] or name
        label = (public_label or "Редактор платформы").strip()[:120] or "Редактор платформы"
        stamp = iso(utc_now(self.clock))
        hashed = hash_password(password)
        with self.db.write() as conn:
            if conn.execute("SELECT 1 FROM civic_users WHERE username = ?", (name,)).fetchone():
                raise PasswordPolicyError("Такой логин уже существует.")
            cursor = conn.execute(
                """INSERT INTO civic_users(username, display_name, public_label, role, password_hash,
                       created_at, password_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, display, label, role, hashed, stamp, stamp))
            return cursor.lastrowid

    def set_password(self, username, password) -> None:
        name = normalize_username(username)
        check_password_policy(name or "", password)
        hashed = hash_password(password)
        stamp = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = conn.execute("SELECT id FROM civic_users WHERE username = ?", (name,)).fetchone()
            if row is None:
                raise PasswordPolicyError("Пользователь не найден.")
            conn.execute("UPDATE civic_users SET password_hash = ?, password_changed_at = ? WHERE id = ?",
                         (hashed, stamp, row["id"]))
            conn.execute("UPDATE civic_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                         (self._now(), row["id"]))

    def disable_user(self, username) -> None:
        name = normalize_username(username)
        with self.db.write() as conn:
            row = conn.execute("SELECT id FROM civic_users WHERE username = ?", (name,)).fetchone()
            if row is None:
                raise PasswordPolicyError("Пользователь не найден.")
            conn.execute("UPDATE civic_users SET disabled_at = ? WHERE id = ?",
                         (iso(utc_now(self.clock)), row["id"]))
            conn.execute("UPDATE civic_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                         (self._now(), row["id"]))

    def list_users(self) -> list[dict]:
        with self.db.read() as conn:
            return [{"username": r["username"], "display_name": r["display_name"],
                     "public_label": r["public_label"], "role": r["role"],
                     "created_at": r["created_at"], "disabled": r["disabled_at"] is not None}
                    for r in conn.execute("SELECT * FROM civic_users ORDER BY id")]

    # --- вход/выход -------------------------------------------------------------

    def _fail_counts(self, conn, user_key, client_key, now):
        since = now - FAIL_WINDOW
        pair = conn.execute(
            "SELECT COUNT(*), MIN(at) FROM civic_login_failures WHERE username_key = ? AND client_key = ? AND at > ?",
            (user_key, client_key, since)).fetchone()
        client = conn.execute(
            "SELECT COUNT(*), MIN(at) FROM civic_login_failures WHERE client_key = ? AND at > ?",
            (client_key, since)).fetchone()
        return pair, client

    def _reserve_attempt(self, user_key, client_key, now) -> int:
        """Проверка лимита и резерв попытки в ОДНОЙ транзакции записи.

        Попытка сразу считается неудачной; при успешном входе запись снимается.
        Поэтому параллельные запросы не проходят мимо лимита (нет гонки проверки и записи).
        """
        with self.db.write() as conn:
            conn.execute("DELETE FROM civic_login_failures WHERE at <= ?", (now - FAIL_WINDOW,))
            pair, client = self._fail_counts(conn, user_key, client_key, now)
            for (count, oldest), limit in ((pair, MAX_FAILS_PER_USER_CLIENT), (client, MAX_FAILS_PER_CLIENT)):
                if count >= limit:
                    raise RateLimited(oldest + FAIL_WINDOW - now)
            return conn.execute("INSERT INTO civic_login_failures(username_key, client_key, at) VALUES (?, ?, ?)",
                                (user_key, client_key, now)).lastrowid

    def login(self, username, password, *, client_ip: str, previous_token=None):
        """Возвращает (token, Principal). AuthError/RateLimited при отказе."""
        now = self._now()
        name = normalize_username(username) or ""
        user_key = _key("user", (username if isinstance(username, str) else "")[:64].strip().lower())
        client_key = _key("client", str(client_ip or "unknown"))
        self._reserve_attempt(user_key, client_key, now)
        with self.db.read() as conn:
            user = conn.execute("SELECT * FROM civic_users WHERE username = ?", (name,)).fetchone() if name else None
        stored = user["password_hash"] if user is not None and user["disabled_at"] is None else _dummy_hash()
        ok = verify_password(password, stored) and user is not None and user["disabled_at"] is None
        if not ok:
            raise AuthError("Неверный логин или пароль.")  # резерв остаётся учтённой неудачей
        with self.db.write() as conn:
            # Пароль проверялся вне транзакции: если за это время его сменили или учётную запись
            # отключили, сессия по старому паролю не создаётся (иначе пережила бы set-password).
            fresh = conn.execute("SELECT password_hash, disabled_at FROM civic_users WHERE id = ?",
                                 (user["id"],)).fetchone()
            if fresh is None or fresh["password_hash"] != stored or fresh["disabled_at"] is not None:
                raise AuthError("Неверный логин или пароль.")
            conn.execute("DELETE FROM civic_login_failures WHERE username_key = ? AND client_key = ?",
                         (user_key, client_key))
            if previous_token and TOKEN_RE.match(previous_token):
                conn.execute("UPDATE civic_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                             (now, token_hash(previous_token)))
            # Старые записи сессий не нужны для истории изменений объектов.
            conn.execute("DELETE FROM civic_sessions WHERE expires_at < ?", (now - 7 * 86400,))
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            expires = now + self.absolute_seconds
            conn.execute(
                """INSERT INTO civic_sessions(token_hash, user_id, csrf_token, created_at,
                       last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (token_hash(token), user["id"], csrf, now, now, expires))
        return token, Principal(user_id=user["id"], username=user["username"],
                                display_name=user["display_name"], role=user["role"],
                                public_label=user["public_label"], csrf_token=csrf,
                                session_hash=token_hash(token), expires_at=expires)

    def resolve(self, token) -> Principal | None:
        if not isinstance(token, str) or not TOKEN_RE.match(token):
            return None
        hashed = token_hash(token)
        now = self._now()
        with self.db.read() as conn:
            row = conn.execute(
                """SELECT s.*, u.username, u.display_name, u.role, u.public_label, u.disabled_at
                   FROM civic_sessions s JOIN civic_users u ON u.id = s.user_id
                   WHERE s.token_hash = ?""", (hashed,)).fetchone()
        if (row is None or row["revoked_at"] is not None or row["disabled_at"] is not None
                or row["expires_at"] <= now or row["last_seen_at"] + self.idle_seconds <= now
                or row["role"] not in ROLES):
            return None
        if now - row["last_seen_at"] >= TOUCH_INTERVAL:
            # Продление простоя — по возможности: занятая база (импорт из CLI) не должна ломать чтение.
            try:
                with self.db.write() as conn:
                    conn.execute("UPDATE civic_sessions SET last_seen_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                                 (now, hashed))
            except sqlite3.OperationalError:
                pass
        return Principal(user_id=row["user_id"], username=row["username"],
                         display_name=row["display_name"], role=row["role"],
                         public_label=row["public_label"], csrf_token=row["csrf_token"],
                         session_hash=hashed, expires_at=row["expires_at"])

    def logout(self, token) -> None:
        if not isinstance(token, str) or not TOKEN_RE.match(token):
            return
        with self.db.write() as conn:
            conn.execute("UPDATE civic_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                         (self._now(), token_hash(token)))

    def revoke_all(self, username=None) -> int:
        with self.db.write() as conn:
            if username is None:
                cursor = conn.execute("UPDATE civic_sessions SET revoked_at = ? WHERE revoked_at IS NULL",
                                      (self._now(),))
            else:
                cursor = conn.execute(
                    """UPDATE civic_sessions SET revoked_at = ? WHERE revoked_at IS NULL AND user_id =
                       (SELECT id FROM civic_users WHERE username = ?)""",
                    (self._now(), normalize_username(username)))
            return cursor.rowcount
