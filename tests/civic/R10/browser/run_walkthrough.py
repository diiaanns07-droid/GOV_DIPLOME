"""R10 launcher for the independent browser walkthrough (walkthrough.cjs).

  python3 -I tests/civic/R10/browser/run_walkthrough.py --code-root <checkout> \
      --out research/round-11-results/R10/runs/browser-<label>.json \
      --shots research/round-11-results/R10/shots/<label> [--tmp-root DIR] [--keep-db]

What it does (and nothing else):
  * starts `python3 -E -s -B app.py --port P --civic-db <tmp>/civic.sqlite3` in the checkout
    (own process group, PID kept; only this PID/group is ever signalled);
  * creates two editor accounts with the real CLI under a pseudo-terminal (getpass, twice):
    passwords are random, held in memory, passed to node only through its environment and never
    written to a file or printed;
  * runs walkthrough.cjs and serves its control line `R10CTL:RESTART` (stop the server, start it
    again on the same port and DB) so the browser can check persistence across a real restart;
  * merges a `harness` section (commands, exit codes, restart timing) into the JSON report.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from r10lib.target import clean_env, free_port, git_dirty, git_sha, run_with_tty  # noqa: E402

NODE = os.environ.get("R10_NODE", "node")
NODE_PATH = os.environ.get("R10_NODE_PATH", "/opt/node22/lib/node_modules")


def wait_ready(base: str, timeout: float = 90.0) -> float:
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout:
        try:
            with urllib.request.urlopen(base + "/api/civic/v1/modules", timeout=5) as resp:
                if resp.status == 200:
                    return round(time.monotonic() - started, 2)
        except Exception as exc:  # noqa: BLE001 - polling
            last = exc
        time.sleep(0.3)
    raise RuntimeError(f"server not ready after {timeout}s: {last}")


class Server:
    def __init__(self, root: Path, port: int, db: Path, log: Path, env: dict):
        self.root, self.port, self.db, self.log, self.env = root, port, db, log, env
        self.proc: subprocess.Popen | None = None
        self.cmd = ["python3", "-E", "-s", "-B", "app.py", "--port", str(port), "--civic-db", str(db)]
        self.journal: list[dict] = []

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> dict:
        logf = open(self.log, "ab")
        t0 = time.monotonic()
        self.proc = subprocess.Popen(self.cmd, cwd=self.root, env=self.env, stdout=logf, stderr=logf,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
        logf.close()
        ready = wait_ready(self.base)
        rec = {"action": "start", "pid": self.proc.pid, "cmd": " ".join(self.cmd), "cwd": str(self.root),
               "ready_seconds": ready, "total_seconds": round(time.monotonic() - t0, 2)}
        self.journal.append(rec)
        return rec

    def stop(self) -> dict:
        if not self.proc:
            return {"action": "stop", "skipped": True}
        pid = self.proc.pid
        t0 = time.monotonic()
        if self.proc.poll() is None:
            try:
                os.killpg(pid, signal.SIGTERM)  # our own process group only
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(pid, signal.SIGKILL)
                self.proc.wait(timeout=10)
        rec = {"action": "stop", "pid": pid, "exit_code": self.proc.returncode,
               "seconds": round(time.monotonic() - t0, 2)}
        self.journal.append(rec)
        self.proc = None
        return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--tmp-root", default=None)
    ap.add_argument("--keep-db", action="store_true")
    ap.add_argument("--label", default="walkthrough")
    args = ap.parse_args()

    root = Path(args.code_root).resolve()
    out = Path(args.out).resolve()
    shots = Path(args.shots).resolve()
    shots.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="r10-walk-", dir=args.tmp_root))
    db = tmp / "civic.sqlite3"
    env = clean_env()
    port = free_port()
    server = Server(root, port, db, tmp / "server.log", env)
    harness = {"code_root": str(root), "code_sha": git_sha(root), "code_dirty_before": git_dirty(root),
               "tmp_dir": str(tmp), "port": port, "server": server.journal, "editors": [], "node": None}

    editors = [("r10walk", secrets.token_urlsafe(18)), ("r10walk2", secrets.token_urlsafe(18))]
    node_rc = None
    try:
        for user, pw in editors:
            cmd = ["python3", "-E", "-s", "-B", "-m", "ui.civic_store", "--db", str(db), "create-editor", user]
            code, text = run_with_tty(cmd, root, env, [pw, pw])
            harness["editors"].append({"cmd": " ".join(cmd), "exit_code": code, "via": "pty+getpass x2",
                                       "output_tail": text.replace(pw, "<redacted>")[-300:]})
            if code != 0:
                raise RuntimeError(f"create-editor {user} failed: exit {code}")
        server.start()
        node_env = dict(os.environ)
        for k in list(node_env):
            if k.startswith("R10_"):
                del node_env[k]
        node_env.update({
            "NODE_PATH": NODE_PATH, "R10_BASE_URL": server.base, "R10_OUT_JSON": str(out), "R10_SHOTS": str(shots),
            "R10_CODE_SHA": harness["code_sha"] or "", "R10_LABEL": args.label,
            "R10_EDITOR_USER": editors[0][0], "R10_EDITOR_PASSWORD": editors[0][1],
            "R10_EDITOR2_USER": editors[1][0], "R10_EDITOR2_PASSWORD": editors[1][1],
        })
        t0 = time.monotonic()
        node = subprocess.Popen([NODE, str(HERE / "walkthrough.cjs")], env=node_env, cwd=str(HERE.parents[3]),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        assert node.stdin and node.stdout
        for line in node.stdout:
            line = line.rstrip("\n")
            for _, pw in editors:
                line = line.replace(pw, "<redacted>")
            print(line, flush=True)
            if line.startswith("R10CTL:RESTART"):
                try:
                    stop = server.stop()
                    start = server.start()
                    reply = f"R10CTL:OK stop={stop.get('seconds')}s start={start.get('total_seconds')}s pid={start.get('pid')}"
                except Exception as exc:  # noqa: BLE001
                    reply = f"R10CTL:ERR {type(exc).__name__}: {exc}"
                node.stdin.write(reply + "\n")
                node.stdin.flush()
        node_rc = node.wait()
        harness["node"] = {"cmd": f"NODE_PATH={NODE_PATH} {NODE} {HERE / 'walkthrough.cjs'}", "exit_code": node_rc,
                           "seconds": round(time.monotonic() - t0, 1)}
    finally:
        server.stop()
        harness["code_dirty_after"] = git_dirty(root)
        try:
            log_tail = (tmp / "server.log").read_text(encoding="utf-8", errors="replace")[-2000:]
        except OSError:
            log_tail = ""
        harness["server_log_tail"] = log_tail
        if not args.keep_db:
            shutil.rmtree(tmp, ignore_errors=True)
            harness["tmp_dir_removed"] = True
        try:
            report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        except (OSError, json.JSONDecodeError):
            report = {}
        report["harness"] = harness
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if node_rc == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
