"""Small HTTP client for black-box civic-v1 checks (stdlib only).

http.client is used instead of urllib so a test can send a wrong Host/Origin,
a wrong Content-Type or a raw broken body exactly as written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.cookies import SimpleCookie
import http.client
import json
from urllib.parse import urlencode, urlsplit

PREFIX = "/api/civic/v1"
DEFAULT = object()


@dataclass
class Resp:
    status: int
    headers: dict
    raw: bytes
    set_cookies: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.raw.decode("utf-8", errors="replace")

    @property
    def json(self):
        try:
            return json.loads(self.raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    @property
    def data(self):
        body = self.json
        return body.get("data") if isinstance(body, dict) else None

    @property
    def error(self):
        body = self.json
        return body.get("error") if isinstance(body, dict) else None

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    def brief(self) -> str:
        return f"HTTP {self.status} {self.content_type} {self.text[:300]!r}"


class CivicClient:
    """One browser-like actor: own cookie jar and CSRF token."""

    def __init__(self, base_url: str, prefix: str = PREFIX, timeout: float = 15.0):
        parts = urlsplit(base_url)
        self.scheme = parts.scheme or "http"
        self.netloc = parts.netloc
        self.host = parts.hostname
        self.port = parts.port or (443 if self.scheme == "https" else 80)
        self.base_url = f"{self.scheme}://{self.netloc}"
        self.prefix = prefix.rstrip("/")
        self.timeout = timeout
        self.cookies: dict[str, str] = {}
        self.csrf_token: str | None = None

    # ---- transport -------------------------------------------------
    def raw(self, method: str, path: str, *, body: bytes | None = None,
            headers: dict | None = None, host=DEFAULT, origin=DEFAULT,
            send_cookies: bool = True) -> Resp:
        hdrs = {}
        hdrs["Host"] = self.netloc if host is DEFAULT else host
        if origin is DEFAULT:
            if method not in ("GET", "HEAD"):
                hdrs["Origin"] = self.base_url
        elif origin is not None:
            hdrs["Origin"] = origin
        if send_cookies and self.cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        if body is not None:
            hdrs["Content-Length"] = str(len(body))
        for key, value in (headers or {}).items():
            if value is None:
                hdrs.pop(key, None)
            else:
                hdrs[key] = value
        conn_cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(self.host, self.port, timeout=self.timeout)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for key, value in hdrs.items():
                conn.putheader(key, value)
            conn.endheaders()
            if body:
                conn.send(body)
            resp = conn.getresponse()
            raw = resp.read()
            headers_out = {k.lower(): v for k, v in resp.getheaders()}
            set_cookies = resp.msg.get_all("Set-Cookie") or []
        finally:
            conn.close()
        for line in set_cookies:
            jar = SimpleCookie()
            try:
                jar.load(line)
            except Exception:  # malformed cookie is itself a finding; keep raw line
                continue
            for name, morsel in jar.items():
                expired = morsel["max-age"] in ("0",) or (not morsel.value)
                if expired:
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = morsel.value
        return Resp(resp.status, headers_out, raw, set_cookies)

    def call(self, method: str, path: str, body=None, *, query: dict | None = None,
             csrf=DEFAULT, content_type: str | None = "application/json",
             raw_body: bytes | None = None, **kw) -> Resp:
        """API call relative to the civic prefix. csrf=DEFAULT sends own token on writes."""
        url = self.prefix + path
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None})
        headers = dict(kw.pop("headers", {}) or {})
        data = raw_body
        if data is None and body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if data is not None and content_type:
            headers.setdefault("Content-Type", content_type)
        if method not in ("GET", "HEAD"):
            token = self.csrf_token if csrf is DEFAULT else csrf
            if token:
                headers.setdefault("X-CSRF-Token", token)
            if data is None:
                data = b""
        return self.raw(method, url, body=data, headers=headers, **kw)

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, body, **kw)

    # ---- session -----------------------------------------------------
    def refresh_session(self) -> Resp:
        r = self.get("/session")
        data = r.data if r.status == 200 else None
        if isinstance(data, dict):
            self.csrf_token = data.get("csrf_token")
        return r

    def login(self, username: str, password: str) -> Resp:
        if self.csrf_token is None:
            # Some servers hand a pre-session token to anonymous clients; harmless otherwise.
            self.refresh_session()
        r = self.post("/session/login", {"username": username, "password": password})
        data = r.data if r.status == 200 else None
        if isinstance(data, dict) and data.get("csrf_token"):
            self.csrf_token = data["csrf_token"]
        elif r.status == 200:
            self.refresh_session()
        return r

    def logout(self) -> Resp:
        return self.post("/session/logout", {})

    def clone_credentials(self) -> "CivicClient":
        """A second actor holding a copy of this one's cookies/token (stolen-session tests)."""
        other = CivicClient(self.base_url, self.prefix, self.timeout)
        other.cookies = dict(self.cookies)
        other.csrf_token = self.csrf_token
        return other
