"""HTTP-адаптер /api/civic/v1 для существующего ui/web_server.Handler (BaseHTTPRequestHandler).

R01 подключает так (полный патч: research/round-11-results/R02/web_server.patch):

    adapter = CivicHttpAdapter(CivicService(db_path), bind_host=host)
    server.civic = adapter
    # в Handler.do_GET/do_HEAD/do_POST/do_PUT/do_PATCH/do_DELETE первой строкой:
    if adapter.handles(self.path): return adapter.serve(self)

Адаптер:
- собирает context для CivicService: headers, client_ip, host_allowed (Host из
  разрешённого списка — защита от DNS rebinding), is_same_origin (Origin/Sec-Fetch-Site),
  is_https (TLS-сокет);
- читает тело только JSON и не больше max_body (413), иначе 415/411;
- вызывает обработчики по очереди: CivicService R02, затем, например, R06;
  если путь под /api/civic/v1 никто не взял — 404 в конверте civic-v1;
- пишет JSON (allow_nan=False) с no-store/nosniff; ошибки — конверт без traceback.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import ssl
from urllib.parse import unquote, urlsplit

from .service import MAX_BODY, PREFIX, error, not_found


LOGGER = logging.getLogger("ui.civic_store.http")
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
CLIENT_DISCONNECTED = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
EXTRA_HEADERS = {"Referrer-Policy": "same-origin", "X-Frame-Options": "DENY",
                 "Cross-Origin-Resource-Policy": "same-origin"}


def _hostname(host_header):
    if not isinstance(host_header, str) or not host_header or len(host_header) > 255:
        return None
    try:
        return urlsplit("http://" + host_header).hostname
    except ValueError:
        return None


class CivicHttpAdapter:
    def __init__(self, civic, *, extra_handlers=(), bind_host="127.0.0.1", allowed_hosts=(),
                 max_body: int = MAX_BODY):
        """civic — CivicService; extra_handlers — функции (method, path, query, body, context).

        allowed_hosts — дополнительные имена Host (по умолчанию только loopback и адрес
        привязки; при 0.0.0.0 — ещё частные IP-адреса, как у существующего Handler).
        """
        self.civic = civic
        self.handlers = [civic.handle, *extra_handlers]
        self.bind_host = bind_host
        self.allowed_hosts = LOOPBACK_HOSTS | {h.lower() for h in allowed_hosts}
        if bind_host and bind_host not in ("0.0.0.0", "::"):
            self.allowed_hosts |= {bind_host.lower()}
        self.max_body = max_body

    # --- контекст ------------------------------------------------------------------

    def handles(self, raw_path) -> bool:
        path = urlsplit(raw_path or "").path
        return path == PREFIX or path.startswith(PREFIX + "/")

    def host_allowed(self, host_header) -> bool:
        hostname = _hostname(host_header)
        if hostname is None:
            return False
        hostname = hostname.lower()
        if hostname in self.allowed_hosts:
            return True
        if self.bind_host in ("0.0.0.0", "::"):
            try:
                address = ipaddress.ip_address(hostname)
            except ValueError:
                return False
            return address.is_private or address.is_loopback
        return False

    @staticmethod
    def same_origin(headers, host_header, is_https):
        origin = headers.get("Origin")
        if origin is not None:
            if origin == "null":
                return False
            try:
                parsed = urlsplit(origin)
            except ValueError:
                return False
            expected = "https" if is_https else "http"
            return (parsed.scheme == expected and isinstance(host_header, str)
                    and parsed.netloc.lower() == host_header.lower() and not parsed.path)
        site = headers.get("Sec-Fetch-Site")
        if site is not None:
            return site in ("same-origin", "none")
        return None  # не браузер (curl, тесты): решает CSRF-токен

    def context(self, handler) -> dict:
        headers = handler.headers
        host = headers.get("Host")
        is_https = isinstance(getattr(handler, "connection", None), ssl.SSLSocket)
        return {
            "headers": headers,
            "client_ip": handler.client_address[0] if handler.client_address else "unknown",
            "host_allowed": self.host_allowed(host),
            "is_same_origin": self.same_origin(headers, host, is_https),
            "is_https": is_https,
        }

    # --- запрос/ответ ------------------------------------------------------------------

    def _read_body(self, handler, method):
        """bytes либо готовый ответ-ошибка."""
        headers = handler.headers
        if headers.get("Transfer-Encoding"):
            handler.close_connection = True
            return error(411, "length_required", "Нужен Content-Length; chunked не поддерживается.")
        raw_length = headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else 0
        except ValueError:
            handler.close_connection = True
            return error(400, "bad_request", "Некорректный Content-Length.")
        if length < 0:
            handler.close_connection = True
            return error(400, "bad_request", "Некорректный Content-Length.")
        if length > self.max_body:
            # Небольшое превышение дочитываем (иначе Windows может послать RST раньше ответа).
            if length <= self.max_body * 2:
                handler.rfile.read(length)
            handler.close_connection = True
            return error(413, "payload_too_large", f"Запрос больше {self.max_body // 1024} КиБ.")
        data = handler.rfile.read(length) if length else b""
        if method in BODY_METHODS and data and headers.get_content_type() != "application/json":
            return error(415, "unsupported_media_type", "Ожидается Content-Type: application/json.")
        return data

    def serve(self, handler) -> None:
        method = handler.command.upper()
        parsed = urlsplit(handler.path)
        try:
            body = self._read_body(handler, method)
            if isinstance(body, dict):
                return self._write(handler, body)
            context = self.context(handler)
            result = None
            payload = body if method in BODY_METHODS else None
            # Декодированные непустые сегменты: /%73taff/ и //staff/ тоже staff-маршруты.
            segments = [unquote(part) for part in parsed.path[len(PREFIX):].split("/") if part]
            is_staff = bool(segments) and segments[0] == "staff"
            for index, handle in enumerate(self.handlers):
                if index > 0 and is_staff:
                    # Защита по умолчанию для staff-маршрутов других модулей (R06...):
                    # сессия редактора обязательна, для записи — ещё CSRF и same-origin.
                    principal, denied = self.civic.require_staff(context, unsafe=method not in ("GET", "HEAD"))
                    if denied:
                        result = denied
                        break
                result = handle(method, parsed.path, parsed.query, payload, context)
                if result is not None:
                    break
            self._write(handler, result or not_found())
        except CLIENT_DISCONNECTED:
            handler.close_connection = True
        except Exception:  # noqa: BLE001
            LOGGER.exception("civic adapter failure on %s", parsed.path[:80])
            self._write(handler, error(500, "internal_error", "Внутренняя ошибка сервера."))

    def _write(self, handler, result) -> None:
        try:
            payload = json.dumps(result["body"], ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            LOGGER.exception("civic response not serialisable")
            result = error(500, "internal_error", "Внутренняя ошибка сервера.")
            payload = json.dumps(result["body"], ensure_ascii=False).encode("utf-8")
        try:
            handler.send_response(result["status"])
            for name, value in {**result["headers"], **EXTRA_HEADERS}.items():
                handler.send_header(name, value)
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            if handler.command.upper() != "HEAD":
                handler.wfile.write(payload)
        except CLIENT_DISCONNECTED:
            handler.close_connection = True


def make_reference_handler(adapter):
    """Минимальный самостоятельный Handler (для тестов и примера, без остального приложения)."""
    from http.server import BaseHTTPRequestHandler

    class CivicOnlyHandler(BaseHTTPRequestHandler):
        server_version = "CivicR02/1.0"

        def log_message(self, fmt, *args):  # без строк запросов в stderr (cookies не логируются и так)
            LOGGER.debug("http %s", self.command)

        def _route(self):
            if adapter.handles(self.path):
                adapter.serve(self)
            else:
                adapter._write(self, not_found())

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _route

    return CivicOnlyHandler
