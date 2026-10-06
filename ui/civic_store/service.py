"""CivicService — HTTP-независимый обработчик /api/civic/v1 (CONTRACT.txt, разделы 2–3).

service.handle(method, path, query, body, context) -> None | {status, headers, body}
  None — путь не принадлежит R02 (чужой модуль или не civic): решает диспетчер R01.
  body ответа — конверт {ok:true,data} либо {ok:false,error:{code,message,fields?}}.
service.resolve_principal(context) -> Principal | None — только из cookie сессии.

context (собирает HTTP-адаптер, см. http_adapter.py):
  headers        — заголовки запроса (Cookie, X-CSRF-Token, Idempotency-Key...)
  client_ip      — адрес клиента (для ограничения попыток входа)
  host_allowed   — Host входит в разрешённый список (loopback по умолчанию)
  is_same_origin — True/False, либо None если браузер не прислал Origin/Sec-Fetch-Site
  is_https       — запрос пришёл по HTTPS (тогда cookie получает Secure)
Отсутствующие ключи трактуются в безопасную сторону (staff-доступ закрыт).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
import sqlite3
from urllib.parse import parse_qs, unquote

from .auth import (COOKIE_NAME, Accounts, AuthError, Principal, RateLimited, clear_cookie,
                   parse_cookies, session_cookie)
from .db import Database, StorageError
from .objects import BadRequest, Conflict, NotFound, ObjectRepository, parse_filters
from .validate import ValidationError, is_valid_id


LOGGER = logging.getLogger("ui.civic_store")
PREFIX = "/api/civic/v1"
MAX_BODY = 64 * 1024
MAX_QUERY = 2048
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
BASE_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Cookie",
}


def _system_clock():
    return datetime.now(timezone.utc)


def response(status: int, body: dict, headers: dict | None = None) -> dict:
    return {"status": status, "headers": {**BASE_HEADERS, **(headers or {})}, "body": body}


def ok(data, status: int = 200, headers: dict | None = None) -> dict:
    return response(status, {"ok": True, "data": data}, headers)


def error(status: int, code: str, message: str, fields: dict | None = None,
          headers: dict | None = None, **extra) -> dict:
    payload = {"code": code, "message": message}
    if fields:
        payload["fields"] = fields
    payload.update(extra)
    return response(status, {"ok": False, "error": payload}, headers)


def not_found() -> dict:
    return error(404, "not_found", "Ресурс не найден.")


def header(context, name: str):
    headers = (context or {}).get("headers") or {}
    try:
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
    except AttributeError:
        value = None
    if value is None and isinstance(headers, dict):
        lowered = name.lower()
        for key, item in headers.items():
            if isinstance(key, str) and key.lower() == lowered:
                return item
    return value


def _invalid_constant(value):
    raise ValueError("NaN/Infinity не допускаются")


def parse_body(body):
    """bytes/str/dict/None → dict. Ошибки — BadRequest (400) или _TooLarge (413)."""
    if body is None or body == b"" or body == "":
        return {}
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        body = body.encode("utf-8", "surrogatepass")
    if not isinstance(body, (bytes, bytearray)):
        raise BadRequest("Тело запроса должно быть JSON-объектом.")
    if len(body) > MAX_BODY:
        raise _TooLarge()
    try:
        value = json.loads(bytes(body).decode("utf-8-sig"), parse_constant=_invalid_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise BadRequest("Некорректный JSON: ожидается объект с конечными числами.")
    if not isinstance(value, dict):
        raise BadRequest("Тело запроса должно быть JSON-объектом.")
    return value


class _TooLarge(Exception):
    pass


def parse_query(query) -> dict[str, list[str]]:
    if query is None or query == "":
        return {}
    if isinstance(query, bytes):
        query = query.decode("utf-8", "replace")
    if isinstance(query, str):
        if len(query) > MAX_QUERY:
            raise BadRequest("Слишком длинная строка запроса.")
        try:
            return parse_qs(query, keep_blank_values=False, max_num_fields=50)
        except ValueError:
            raise BadRequest("Слишком много параметров запроса.")
    if isinstance(query, dict):
        result = {}
        for key, value in query.items():
            values = value if isinstance(value, (list, tuple)) else [value]
            result[str(key)] = [str(item) for item in values if item is not None]
        return result
    raise BadRequest("Недопустимая строка запроса.")


class CivicService:
    """Сервис civic-v1 поверх одного файла SQLite. Безопасен для ThreadingHTTPServer."""

    def __init__(self, db_path, clock=None, *, auto_migrate: bool = True,
                 idle_seconds: int | None = None, absolute_seconds: int | None = None):
        self.clock = clock or _system_clock
        self.db = Database(db_path)
        if auto_migrate:
            self.db.migrate()
        self.db.require_current_schema()
        self.objects = ObjectRepository(self.db, self.clock)
        options = {}
        if idle_seconds is not None:
            options["idle_seconds"] = idle_seconds
        if absolute_seconds is not None:
            options["absolute_seconds"] = absolute_seconds
        self.accounts = Accounts(self.db, self.clock, **options)

    # --- идентичность -------------------------------------------------------------

    def _session_token(self, context):
        return parse_cookies(header(context, "Cookie")).get(COOKIE_NAME)

    def resolve_principal(self, context) -> Principal | None:
        """Личность только из серверной сессии (cookie). Тело запроса не читается."""
        if (context or {}).get("host_allowed") is not True:
            return None
        return self.accounts.resolve(self._session_token(context))

    def require_staff(self, context, *, unsafe: bool):
        """(principal, None) либо (None, ответ-ошибка). Для R01/R06: staff-маршруты."""
        context = context or {}
        if context.get("host_allowed") is not True:
            return None, error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        if unsafe and context.get("is_same_origin") is False:
            return None, error(403, "cross_origin", "Запрос с чужого сайта отклонён.")
        principal = self.accounts.resolve(self._session_token(context))
        if principal is None:
            return None, error(401, "unauthenticated", "Войдите как редактор.",
                               headers=self._clear_if_stale(context))
        if not principal.is_staff:
            return None, error(403, "forbidden", "Недостаточно прав.")
        if unsafe and not principal.check_csrf(header(context, "X-CSRF-Token")):
            return None, error(403, "csrf_failed", "Неверный CSRF-токен: обновите сессию (GET /session).")
        return principal, None

    def lookup_public_object(self, object_id):
        """Опубликованный объект (публичный DTO) либо None — для R06 object_lookup и R09 контекста."""
        if not is_valid_id(object_id):
            return None
        try:
            return self.objects.get_public(object_id)["item"]
        except NotFound:
            return None

    def _clear_if_stale(self, context):
        if self._session_token(context) is not None:
            return {"Set-Cookie": clear_cookie(secure=bool((context or {}).get("is_https")))}
        return None

    # --- точка входа ----------------------------------------------------------------

    def handle(self, method, path, query, body, context):
        if not isinstance(path, str) or not (path == PREFIX or path.startswith(PREFIX + "/")):
            return None
        method = (method or "").upper()
        segments = [unquote(part) for part in path[len(PREFIX):].split("/")[1:]]
        route = self._route(segments)
        if route is None:
            return None
        effective = "GET" if method == "HEAD" else method
        if effective not in route:
            allowed = set(route) | ({"HEAD"} if "GET" in route else set())
            return error(405, "method_not_allowed", "Метод не поддерживается.",
                         headers={"Allow": ", ".join(sorted(allowed))})
        handler, args = route[effective]
        try:
            params = parse_query(query)
            payload = parse_body(body) if effective == "POST" else {}
            return handler(context or {}, params, payload, *args)
        except _TooLarge:
            return error(413, "payload_too_large", f"Запрос больше {MAX_BODY // 1024} КиБ.")
        except ValidationError as exc:
            return error(422, "validation_failed", exc.message, exc.fields)
        except BadRequest as exc:
            return error(400, "bad_request", str(exc), exc.fields or None)
        except NotFound:
            return error(404, "not_found", "Объект не найден.")
        except Conflict as exc:
            return error(409, "stale_revision", str(exc), current_revision=exc.current_revision)
        except RateLimited as exc:
            return error(429, "rate_limited", "Слишком много попыток. Повторите позже.",
                         headers={"Retry-After": str(exc.retry_after)}, retry_after=exc.retry_after)
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) or "busy" in str(exc):
                LOGGER.warning("civic db busy on %s %s", effective, segments[:2])
                return error(503, "busy", "База занята, повторите запрос.", headers={"Retry-After": "1"})
            LOGGER.exception("civic db error on %s %s", effective, segments[:2])
            return error(500, "internal_error", "Внутренняя ошибка сервера.")
        except StorageError:
            LOGGER.exception("civic storage error")
            return error(500, "internal_error", "Хранилище недоступно.")
        except Exception:  # noqa: BLE001 — клиенту только конверт без traceback
            LOGGER.exception("civic handler failed on %s %s", effective, segments[:2])
            return error(500, "internal_error", "Внутренняя ошибка сервера.")

    def _route(self, s):
        """{метод: (функция, аргументы)} либо None для чужого пути."""
        n = len(s)
        if s == ["objects"]:
            return {"GET": (self._public_list, ())}
        if n == 2 and s[0] == "objects":
            return {"GET": (self._public_detail, (s[1],))}
        if s == ["session"]:
            return {"GET": (self._session_state, ())}
        if s == ["session", "login"]:
            return {"POST": (self._login, ())}
        if s == ["session", "logout"]:
            return {"POST": (self._logout, ())}
        if s == ["staff", "objects"]:
            return {"GET": (self._staff_list, ()), "POST": (self._staff_create, ())}
        if n == 3 and s[:2] == ["staff", "objects"]:
            return {"GET": (self._staff_detail, (s[2],))}
        if n == 4 and s[:2] == ["staff", "objects"] and s[3] in ("update", "publish", "archive"):
            return {"POST": (self._staff_action, (s[2], s[3]))}
        if s == ["staff", "audit"]:
            return {"GET": (self._staff_audit, ())}
        return None

    # --- публичное --------------------------------------------------------------------

    def _public_list(self, context, params, payload):
        return ok(self.objects.list_public(parse_filters(params, staff=False)))

    def _public_detail(self, context, params, payload, object_id):
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        return ok(self.objects.get_public(object_id))

    # --- сессия -----------------------------------------------------------------------

    @staticmethod
    def _session_data(principal: Principal | None) -> dict:
        if principal is None:
            return {"authenticated": False, "user": None, "csrf_token": None}
        return {"authenticated": True, "user": principal.public_user(),
                "csrf_token": principal.csrf_token}

    def _session_state(self, context, params, payload):
        if context.get("host_allowed") is not True:
            return error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        principal = self.resolve_principal(context)
        headers = self._clear_if_stale(context) if principal is None else None
        return ok(self._session_data(principal), headers=headers)

    def _login(self, context, params, payload):
        if context.get("host_allowed") is not True:
            return error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        if context.get("is_same_origin") is False:
            return error(403, "cross_origin", "Вход с чужого сайта отклонён.")
        username, password = payload.get("username"), payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
            raise ValidationError({"username": "Укажите логин и пароль."}, "Укажите логин и пароль.")
        if len(username) > 64 or len(password) > 1024:
            raise ValidationError({"username": "Слишком длинные учётные данные."})
        try:
            token, principal = self.accounts.login(
                username, password, client_ip=str(context.get("client_ip") or "unknown"),
                previous_token=self._session_token(context))
        except AuthError:
            LOGGER.info("civic login failed")
            return error(401, "invalid_credentials", "Неверный логин или пароль.")
        LOGGER.info("civic login ok user_id=%s", principal.user_id)
        cookie = session_cookie(token, secure=bool(context.get("is_https")),
                                max_age=self.accounts.absolute_seconds)
        return ok(self._session_data(principal), headers={"Set-Cookie": cookie})

    def _logout(self, context, params, payload):
        if context.get("host_allowed") is not True:
            return error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        if context.get("is_same_origin") is False:
            return error(403, "cross_origin", "Запрос с чужого сайта отклонён.")
        token = self._session_token(context)
        principal = self.accounts.resolve(token)
        if principal is not None:
            if not principal.check_csrf(header(context, "X-CSRF-Token")):
                return error(403, "csrf_failed", "Неверный CSRF-токен: обновите сессию (GET /session).")
            self.accounts.logout(token)
            LOGGER.info("civic logout user_id=%s", principal.user_id)
        return ok(self._session_data(None),
                  headers={"Set-Cookie": clear_cookie(secure=bool(context.get("is_https")))})

    # --- редактор ----------------------------------------------------------------------

    def _staff_list(self, context, params, payload):
        principal, denied = self.require_staff(context, unsafe=False)
        if denied:
            return denied
        return ok(self.objects.list_staff(parse_filters(params, staff=True)))

    def _staff_create(self, context, params, payload):
        principal, denied = self.require_staff(context, unsafe=True)
        if denied:
            return denied
        key = header(context, "Idempotency-Key")
        if key is not None and not (isinstance(key, str) and IDEMPOTENCY_RE.match(key)):
            raise BadRequest("Недопустимый Idempotency-Key.", {"Idempotency-Key": "8–64 символа [A-Za-z0-9._:-]."})
        item, ignored, created = self.objects.create(principal.actor(), payload, request_key=key)
        data = {"item": item}
        if ignored:
            data["ignored_fields"] = ignored
        return ok(data, status=201 if created else 200)

    def _staff_audit(self, context, params, payload):
        principal, denied = self.require_staff(context, unsafe=False)
        if denied:
            return denied
        return ok(self.objects.audit_page(params))

    def _staff_detail(self, context, params, payload, object_id):
        principal, denied = self.require_staff(context, unsafe=False)
        if denied:
            return denied
        return ok(self.objects.get_staff(object_id))

    def _staff_action(self, context, params, payload, object_id, action):
        principal, denied = self.require_staff(context, unsafe=True)
        if denied:
            return denied
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        expected = payload.get("expected_revision")
        reason = payload.get("reason")
        ignored = sorted(key for key in payload if key not in ("expected_revision", "reason", "changes"))
        if action == "update":
            item, ignored_fields = self.objects.update(
                principal.actor(), object_id, expected_revision=expected,
                changes=payload.get("changes"), reason=reason)
            ignored = sorted(set(ignored) | {f"changes.{name}" for name in ignored_fields})
        elif action == "publish":
            item = self.objects.publish(principal.actor(), object_id, expected_revision=expected,
                                        reason=reason)
        else:
            item = self.objects.archive(principal.actor(), object_id, expected_revision=expected,
                                        reason=reason)
        data = {"item": item}
        if ignored:
            data["ignored_fields"] = ignored
        return ok(data)
