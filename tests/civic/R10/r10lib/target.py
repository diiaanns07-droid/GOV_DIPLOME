"""Which server the acceptance suite talks to, and how it is (re)started.

R10_TARGET selects the system under test:
  oracle   (default) R10's own reference server in r10lib/oracle. It exists ONLY to
           prove the suite runs and detects defects; it is not product code.
  command  start a checkout yourself: R10_CODE_ROOT, R10_START_CMD, R10_CREATE_EDITOR_CMD
           (templates with {python} {port} {datadir} {db} {username}). Restartable.
  external an already running server: R10_BASE_URL, R10_EDITOR_USER, R10_EDITOR_PASSWORD
           (+ optional R10_EDITOR2_USER/R10_EDITOR2_PASSWORD). Not restartable.
Other knobs: R10_API_PREFIX (default /api/civic/v1), R10_ORACLE_MUTANT (oracle only).

Every spawned command is recorded in JOURNAL with exit code and duration.
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path
import secrets
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

from .client import CivicClient

HERE = Path(__file__).resolve().parent
R10_DIR = HERE.parent
REPO_ROOT = R10_DIR.parents[2]
JOURNAL: list[dict] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def git_sha(root: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def git_dirty(root: Path) -> bool | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                             capture_output=True, text=True, timeout=20)
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def clean_env(extra: dict | None = None) -> dict:
    """Environment for the system under test: no PYTHONPATH from the caller, no API keys."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTHON", "OPENAI", "ANTHROPIC", "R10_"))
           and "KEY" not in k and "TOKEN" not in k and "SECRET" not in k}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.update(extra or {})
    return env


def run_with_tty(cmd: list[str], cwd: Path, env: dict, answers: list[str],
                 timeout: float = 60.0) -> tuple[int, str]:
    """Run an interactive CLI under a pseudo-terminal and answer getpass prompts.

    getpass reads from /dev/tty; pty.fork gives the child a controlling terminal,
    so passwords never pass through argv, env or a file.
    """
    import pty

    started = time.monotonic()
    pid, fd = pty.fork()
    if pid == 0:  # child
        try:
            os.chdir(cwd)
            os.execvpe(cmd[0], cmd, env)
        finally:
            os._exit(127)
    output = b""
    pending = list(answers)
    last_data = time.monotonic()
    since_answer = b""
    status = None
    try:
        while time.monotonic() - started < timeout:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                output += chunk
                since_answer += chunk
                last_data = time.monotonic()
            elif pending and since_answer and time.monotonic() - last_data > 0.3:
                os.write(fd, (pending.pop(0) + "\n").encode())
                since_answer = b""
            done, raw_status = os.waitpid(pid, os.WNOHANG)
            if done:
                status = raw_status
                # drain remaining output
                try:
                    while select.select([fd], [], [], 0.05)[0]:
                        chunk = os.read(fd, 4096)
                        if not chunk:
                            break
                        output += chunk
                except OSError:
                    pass
                break
        if status is None:
            # EOF on the pty or timeout: give the child a moment, then stop it.
            grace = time.monotonic() + 5
            while time.monotonic() < grace:
                done, raw_status = os.waitpid(pid, os.WNOHANG)
                if done:
                    status = raw_status
                    break
                time.sleep(0.05)
        if status is None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status = os.waitpid(pid, 0)
    finally:
        os.close(fd)
    code = os.waitstatus_to_exitcode(status) if status is not None else -1
    text = output.decode("utf-8", errors="replace")
    for secret in answers:
        text = text.replace(secret, "<redacted>")
    JOURNAL.append({"cmd": " ".join(cmd), "cwd": str(cwd), "exit_code": code,
                    "seconds": round(time.monotonic() - started, 2), "interactive": True})
    return code, text


class Target:
    name = "abstract"
    can_restart = False

    def __init__(self):
        self.prefix = os.environ.get("R10_API_PREFIX", "/api/civic/v1")
        self.base_url = ""
        self.editors: list[tuple[str, str]] = []
        self.code_root: Path | None = None
        self.notes: list[str] = []

    def client(self, source_ip: str | None = None) -> CivicClient:
        return CivicClient(self.base_url, self.prefix, source_ip=source_ip)

    _next_resident = 10

    def resident(self) -> CivicClient:
        """Anonymous client from its own loopback address (127.0.0.x): a distinct resident."""
        Target._next_resident += 1
        n = Target._next_resident
        return self.client(source_ip=f"127.0.{n // 250}.{n % 250 + 2}")

    def editor(self, index: int = 0) -> CivicClient:
        """Fresh logged-in editor client (own cookie jar)."""
        user, password = self.editors[index]
        c = self.client()
        r = c.login(user, password)
        if r.status != 200:
            raise RuntimeError(f"editor login failed: {r.brief()}")
        return c

    def describe(self) -> dict:
        root = self.code_root
        return {"target": self.name, "base_url": self.base_url, "prefix": self.prefix,
                "code_root": str(root) if root else None,
                "code_sha": git_sha(root) if root else None,
                "code_dirty": git_dirty(root) if root else None,
                "can_restart": self.can_restart, "notes": self.notes,
                "mutant": os.environ.get("R10_ORACLE_MUTANT") or None}

    def restart(self):
        raise NotImplementedError

    def stop(self):
        pass


class ProcessTarget(Target):
    """Starts a server process on a private port with a private data dir."""

    can_restart = True

    def __init__(self, code_root: Path, start_cmd: str, editor_cmd: str | None):
        super().__init__()
        self.code_root = code_root.resolve()
        self.start_template = start_cmd
        self.editor_template = editor_cmd
        self.datadir = Path(tempfile.mkdtemp(prefix="r10-civic-"))
        self.db = self.datadir / "civic.sqlite3"
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None
        self.server_log = self.datadir / "server-output.txt"
        self.extra_env = {}

    def fmt(self, template: str, **kw) -> list[str]:
        values = {"python": sys.executable, "port": str(self.port),
                  "datadir": str(self.datadir), "db": str(self.db),
                  "r10": str(R10_DIR)}
        values.update(kw)
        return [part.format(**values) for part in shlex.split(template)]

    def start(self):
        cmd = self.fmt(self.start_template)
        log = open(self.server_log, "ab")
        started = time.monotonic()
        self.proc = subprocess.Popen(cmd, cwd=self.code_root, env=clean_env(self.extra_env),
                                     stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        log.close()
        deadline = time.monotonic() + 30
        last = None
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                break
            try:
                r = self.client().get("/session")
                last = r.status
                if r.status == 200:
                    JOURNAL.append({"cmd": " ".join(cmd), "cwd": str(self.code_root),
                                    "exit_code": None, "state": "running",
                                    "seconds_to_ready": round(time.monotonic() - started, 2)})
                    return
            except OSError:
                pass
            time.sleep(0.2)
        out = self.server_log.read_text(errors="replace")[-2000:]
        JOURNAL.append({"cmd": " ".join(cmd), "cwd": str(self.code_root),
                        "exit_code": self.proc.poll(), "state": "failed_to_start"})
        raise RuntimeError(f"server did not become ready (last status {last}):\n{out}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=10)
        self.proc = None

    def restart(self):
        self.stop()
        self.start()

    def create_editor(self, username: str) -> tuple[str, str]:
        password = "R10-" + secrets.token_urlsafe(18)
        cmd = self.fmt(self.editor_template, username=username)
        code, out = run_with_tty(cmd, self.code_root, clean_env(self.extra_env),
                                 [password, password, password])
        if code != 0:
            raise RuntimeError(f"create-editor failed ({code}): {out[-1500:]}")
        if password in out:
            raise AssertionError("create-editor echoed the password to the terminal")
        return username, password

    def cleanup(self):
        self.stop()
        shutil.rmtree(self.datadir, ignore_errors=True)


class OracleTarget(ProcessTarget):
    name = "oracle"

    def __init__(self):
        oracle = HERE / "oracle" / "server.py"
        super().__init__(R10_DIR, f"{{python}} -I -B {oracle} serve --db {{db}} --port {{port}}",
                         f"{{python}} -I -B {oracle} create-editor --db {{db}} --username {{username}}")
        # clean_env() drops R10_* for products; the oracle's own knobs are passed explicitly.
        for key, value in os.environ.items():
            if key.startswith("R10_ORACLE_"):
                self.extra_env[key] = value
        self.notes.append("Reference oracle written by R10 for suite self-test; not product code.")

    def describe(self):
        d = super().describe()
        d["code_root"] = "tests/civic/R10/r10lib/oracle"
        d["code_sha"] = git_sha(REPO_ROOT)
        return d


class CommandTarget(ProcessTarget):
    name = "command"

    def __init__(self):
        root = Path(os.environ["R10_CODE_ROOT"])
        super().__init__(root, os.environ["R10_START_CMD"], os.environ.get("R10_CREATE_EDITOR_CMD"))
        if (root / ".env").exists():
            self.notes.append("WARNING: .env present in code root; it was not read by R10")


class ExternalTarget(Target):
    name = "external"

    def __init__(self):
        super().__init__()
        self.base_url = os.environ["R10_BASE_URL"].rstrip("/")
        self.editors = [(os.environ["R10_EDITOR_USER"], os.environ["R10_EDITOR_PASSWORD"])]
        if os.environ.get("R10_EDITOR2_USER"):
            self.editors.append((os.environ["R10_EDITOR2_USER"], os.environ["R10_EDITOR2_PASSWORD"]))
        if os.environ.get("R10_CODE_ROOT"):
            self.code_root = Path(os.environ["R10_CODE_ROOT"])


_TARGET: Target | None = None


def get_target() -> Target:
    """Lazily start one shared target per test process."""
    global _TARGET
    if _TARGET is not None:
        return _TARGET
    kind = os.environ.get("R10_TARGET", "oracle")
    if kind == "oracle":
        t = OracleTarget()
    elif kind == "command":
        t = CommandTarget()
    elif kind == "external":
        t = ExternalTarget()
    else:
        raise ValueError(f"unknown R10_TARGET={kind}")
    if isinstance(t, ProcessTarget):
        if t.editor_template:
            # Editors must exist before the server caches anything; CLI writes the DB directly.
            t.editors.append(t.create_editor("r10_editor_alpha"))
            t.editors.append(t.create_editor("r10_editor_beta"))
        t.start()
        atexit.register(t.cleanup)
    _TARGET = t
    return t
