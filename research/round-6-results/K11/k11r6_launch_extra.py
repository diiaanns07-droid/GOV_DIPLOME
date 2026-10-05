"""K11 round 6: launch checks added for the new BUILD (run-demo.bat arguments), stdlib only.

    python k11r6_launch_extra.py --app-root <copy>/prototypes/city-evidence [--out extra.json]

X1  serve.py <port> --open (the arguments run-demo.bat passes) starts and serves; the browser
    opener is neutralised with BROWSER=true (POSIX) so nothing is launched.
X2  serve.py on a port that is already taken: exits non-zero with a message (run-demo.bat uses a fixed 8765).
X3  serve.py in a copy without web/data.js: exits non-zero with its own message (no traceback).
Only processes started by this script are stopped. Windows itself is not run here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def start(cmd, cwd, env):
    kw = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)


def stop(p):
    if p.poll() is None and os.name == "posix":
        os.killpg(p.pid, signal.SIGINT)
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            pass
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(5)
    out, err = p.communicate(timeout=5)
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.app_root).resolve()
    env = dict(os.environ, PYTHONUNBUFFERED="1", BROWSER="true")
    res = []

    port = free_port()
    p = start([a.python, "serve.py", str(port), "--open"], str(root), env)
    t0, up = time.monotonic(), False
    while time.monotonic() - t0 < 10 and p.poll() is None:
        if listening(port):
            up = True
            break
        time.sleep(0.1)
    time.sleep(1.0)  # let the --open timer (0.5 s) fire
    alive_after_open = p.poll() is None and listening(port)
    rc, out, err = stop(p)
    res.append({"id": "X1", "status": "pass" if up and alive_after_open and not listening(port) else "fail",
                "title": "serve.py <port> --open starts, keeps serving after the opener fired, stops on Ctrl+C",
                "detail": {"listening": up, "alive_after_open": alive_after_open, "returncode": rc,
                           "traceback": "Traceback" in err, "stdout": out.strip().splitlines()[:1]}})

    port = free_port()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", port))
    blocker.listen(1)
    try:
        p = start([a.python, "serve.py", str(port)], str(root), env)
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            pass
        rc, out, err = stop(p)
    finally:
        blocker.close()
    last = err.strip().splitlines()[-1] if err.strip() else ""
    res.append({"id": "X2", "status": "pass" if rc not in (0, None) else "fail",
                "title": "port already in use: serve.py exits non-zero (run-demo.bat then pauses on errorlevel 1)",
                "detail": {"returncode": rc, "stderr_last_line": last[:200], "traceback": "Traceback" in err,
                           "note": "message clarity is informational; errno text differs on Windows"}})

    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "city-evidence"
        (copy / "web").mkdir(parents=True)
        shutil.copy2(root / "serve.py", copy / "serve.py")
        shutil.copy2(root / "web" / "index.html", copy / "web" / "index.html")
        p = start([a.python, "serve.py", str(free_port())], str(copy), env)
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            pass
        rc, out, err = stop(p)
    res.append({"id": "X3", "status": "pass" if rc not in (0, None) and "Traceback" not in err else "fail",
                "title": "copy without web/data.js: serve.py exits non-zero with its own message, no traceback",
                "detail": {"returncode": rc, "stderr": err.strip()[:200]}})

    report = {"tool": "research/round-6-results/K11/k11r6_launch_extra.py", "target": "app-root",
              "host": {"os": platform.system(), "python": platform.python_version()}, "checks": res}
    if a.out:
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    for r in res:
        print(f"{r['status']:6} {r['id']} {r['title']}")
    return 1 if any(r["status"] == "fail" for r in res) else 0


if __name__ == "__main__":
    raise SystemExit(main())
