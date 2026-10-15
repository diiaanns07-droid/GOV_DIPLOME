"""R10 · раунд 15 · стенд сборки для проверок API: сервер с временной базой и HTTP-клиент (только stdlib).

    with Stand(root, world=True) as s:          # CIVIC_DEMO=1 (+ CIVIC_DEMO_WORLD=1 при world=True)
        anon = s.client()                       # житель без устройства
        res = s.client(device="r10-device-1")   # житель: заголовок X-Birge-Device
        staff = s.client(); staff.login(*s.staff)
        r = anon.get("/api/civic/v2/agencies")  # Reply(status, body, headers, ms)

Сервер поднимается как в tests/e2e/demo_flow.cjs: init → seed-demo → seed-r14-demo (если есть) → сотрудник
«r10-operator» → python3 -B app.py на свободном порту. Ничего не пишет в репозиторий; база удаляется при выходе.
Журнал сервера копится в Stand.log — по нему проверки ищут «Traceback» (модуль упал внутри).
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

PY = os.environ.get("PYTHON") or sys.executable


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class Reply:
    status: int
    body: object
    headers: dict = field(default_factory=dict)
    ms: float = 0.0
    text: str = ""

    def data(self):
        """Тело без конверта сервиса {"ok": true, "data": …} (R09, R13, сервисы раунда 15)."""
        body = self.body
        if isinstance(body, dict) and "ok" in body and "data" in body:
            return body["data"]
        return body


class Client:
    """Один «браузер»: свои cookie, CSRF и устройство жителя. Origin — как у страницы сервера."""

    def __init__(self, base: str, device: str | None = None):
        self.base = base.rstrip("/")
        self.device = device
        self.csrf = None
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, method: str, path: str, body=None, *, csrf: bool = True, headers: dict | None = None,
                timeout: float = 60) -> Reply:
        hdrs = {"Origin": self.base, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        if self.device:
            hdrs["X-Birge-Device"] = self.device
        if csrf and self.csrf:
            hdrs["X-CSRF-Token"] = self.csrf
        hdrs.update(headers or {})
        # Адрес как в браузере: не-ASCII (кириллица в параметрах) кодируется, уже закодированное не трогаем.
        path = urllib.parse.quote(path, safe="/?&=:%,+-._~")
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=hdrs)
        t0 = time.perf_counter()
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw, status, rh = resp.read(), resp.status, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            raw, status, rh = exc.read(), exc.code, dict(exc.headers or {})
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            return Reply(0, {"error": "network", "message": str(exc)}, {}, (time.perf_counter() - t0) * 1000)
        ms = (time.perf_counter() - t0) * 1000
        text = raw.decode("utf-8", "replace")
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            parsed = None
        return Reply(status, parsed, rh, ms, text[:400] if parsed is None else "")

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, {} if body is None else body, **kw)

    def login(self, username: str, password: str) -> bool:
        r = self.post("/api/civic/v1/session/login", {"username": username, "password": password}, csrf=False)
        data = r.data() if isinstance(r.body, dict) else None
        token = None
        if isinstance(data, dict):
            token = data.get("csrf_token") or (data.get("session") or {}).get("csrf_token")
        self.csrf = token
        return r.status == 200 and bool(token)


class Stand:
    """Сервер сборки на временной базе. world=True — CIVIC_DEMO_WORLD=1 (единый демо-мир R02, CONTRACT §11)."""

    def __init__(self, root, *, world: bool = False, demo: bool = True, extra_env: dict | None = None):
        self.root = Path(root).resolve()
        self.world, self.demo = world, demo
        self.extra_env = dict(extra_env or {})
        self.tmp = None
        self.proc = None
        self.base = None
        self.staff = None
        self.seeds = []
        self.log = ""
        self._reader = None

    def _env(self, db):
        env = {**os.environ, "CIVIC_DB_PATH": str(db), "PYTHONDONTWRITEBYTECODE": "1",
               "CIVIC_DEMO": "1" if self.demo else "", "CIVIC_DEMO_WORLD": "1" if self.world else ""}
        env.update(self.extra_env)
        return env

    def _cli(self, env, db, *argv, stdin=None):
        return subprocess.run([PY, "-B", "-m", "ui.civic_store", "--db", str(db), *argv], cwd=self.root, env=env,
                              input=stdin, capture_output=True, text=True, timeout=300)

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r10-api-"))
        db = self.tmp / "civic.sqlite3"
        env = self._env(db)
        for argv in (("init",), ("seed-demo", "--package", "data/civic/astana/demo_synthetic.json")):
            done = self._cli(env, db, *argv)
            if done.returncode != 0:
                raise RuntimeError(f"civic_store {' '.join(argv)}: {done.stderr[-800:]}")
            self.seeds.append(argv[0])
        if "seed-r14-demo" in self._cli(env, db, "--help").stdout:
            if self._cli(env, db, "seed-r14-demo").returncode == 0:
                self.seeds.append("seed-r14-demo")
        password = "R10-api-" + secrets.token_hex(8) + "-Aa1!"
        made = self._cli(env, db, "create-editor", "r10-operator", "--password-stdin", stdin=password + "\n")
        self.staff = ("r10-operator", password) if made.returncode == 0 else None
        port = free_port()
        self.proc = subprocess.Popen([PY, "-B", "app.py", "--host", "127.0.0.1", "--port", str(port)], cwd=self.root,
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self.base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("сервер сборки завершился: " + self.log[-1500:])
            try:
                with urllib.request.urlopen(self.base + "/api/health", timeout=2) as resp:
                    if resp.status == 200:
                        return self
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.2)
        raise RuntimeError("сервер сборки не ответил за 60 с: " + self.log[-1500:])

    def _read(self):
        for line in self.proc.stdout:
            self.log += line

    def client(self, device: str | None = None) -> Client:
        return Client(self.base, device=device)

    def tracebacks(self, since: int = 0) -> list[str]:
        """Ошибки модулей в журнале сервера после позиции since (последняя строка каждого Traceback)."""
        lines = self.log[since:].splitlines()
        out = []
        for i, line in enumerate(lines):
            if line.startswith("Traceback"):
                tail = next((lines[j] for j in range(i + 1, min(i + 80, len(lines)))
                             if lines[j] and not lines[j].startswith(" ") and not lines[j].startswith("Traceback")), "")
                out.append(tail[:300])
        return out

    def __exit__(self, *exc):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)
        return False
