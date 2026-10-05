"""K11 round 8 stage 3: Windows launcher check of the demo WITHOUT Windows (stdlib only).

    python tests/launcher_check.py --app-root <copy of prototypes/city-evidence> [--label X] [--out report.json]

static  : reads run-demo.bat / .gitattributes / serve.py as bytes; nothing is executed by cmd.exe.
runtime : really runs <app-root>/serve.py on THIS OS (copied into a folder whose name has Kazakh letters and spaces;
          with an ASCII-only console encoding; on a busy port) and stops every server it started.
windows : cmd.exe, the py launcher, the registry and Windows socket semantics are not available here -> not_run.
Each item: PASS / FAIL / INFO / NOT_RUN. Exit 1 only if a static or runtime item FAILs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

ITEMS = []


def item(kind, name, status, detail=None):
    ITEMS.append({"kind": kind, "name": name, "status": status, "detail": detail})
    print(f"{status:7} [{kind}] {name}" + (f" :: {json.dumps(detail, ensure_ascii=True)[:240]}" if detail is not None and status != "PASS" else ""))


def static_checks(app: Path):
    bat_path = app / "run-demo.bat"
    if not bat_path.exists():
        item("static", "run-demo.bat present", "FAIL", str(bat_path))
        return
    raw = bat_path.read_bytes()
    lines = raw.split(b"\r\n")
    bare_lf = sum(line.count(b"\n") for line in lines)
    item("static", "run-demo.bat: CRLF line endings only (cmd.exe misparses LF-only batch files around labels/blocks)",
         "PASS" if bare_lf == 0 and b"\r\n" in raw else "FAIL", {"bare_lf": bare_lf})
    non_ascii = [i + 1 for i, line in enumerate(raw.split(b"\n")) if any(b > 0x7E or (b < 0x20 and b not in (0x09, 0x0D)) for b in line)]
    item("static", "run-demo.bat: ASCII only (after chcp 65001 cmd re-reads the file in a new code page)",
         "PASS" if not non_ascii else "FAIL", {"lines": non_ascii})
    text = raw.decode("ascii", "replace").replace("\r\n", "\n")
    low = [line.strip().lower() for line in text.split("\n")]
    def first(pred):
        return next((i for i, line in enumerate(low) if pred(line)), None)
    run_line = first(lambda line: "serve.py" in line and not line.startswith("rem"))
    chcp = first(lambda line: line.startswith("chcp 65001"))
    cd = first(lambda line: line.startswith('cd /d "%~dp0"'))
    item("static", 'run-demo.bat: cd /d "%~dp0" (quoted, other drive, spaces) before serve.py',
         "PASS" if cd is not None and run_line is not None and cd < run_line else "FAIL", {"cd": cd, "run": run_line})
    item("static", "run-demo.bat: chcp 65001 and PYTHONIOENCODING=utf-8 before serve.py",
         "PASS" if chcp is not None and run_line is not None and chcp < run_line and "set pythonioencoding=utf-8" in low else "FAIL")
    item("static", "run-demo.bat: py -3 with fallback to python",
         "PASS" if any(line.startswith("py -3 ") for line in low) and any(line.startswith("python ") for line in low) else "FAIL")
    item("static", "run-demo.bat: window stays open on error (pause)", "PASS" if any("pause" in line for line in low) else "FAIL")
    port = re.search(r"serve\.py\s+(\d+)", text)
    item("static", "run-demo.bat: fixed port (a busy port is reported by serve.py, see runtime)", "INFO", {"port": port and int(port.group(1))})
    ga = app / ".gitattributes"
    ga_text = ga.read_text(encoding="utf-8", errors="replace") if ga.exists() else ""
    keeps = bool(re.search(r"^\*\s+-text\b", ga_text, re.M) or re.search(r"^\*\.bat\s+.*eol=crlf", ga_text, re.M))
    item("static", ".gitattributes keeps run-demo.bat bytes (no autocrlf conversion on checkout)", "PASS" if keeps else "FAIL", ga_text.strip()[:120])
    serve = (app / "serve.py").read_text(encoding="utf-8")
    item("static", "serve.py listens on 127.0.0.1 only", "PASS" if '("127.0.0.1", PORT)' in serve and "0.0.0.0" not in serve else "FAIL")
    explicit = re.search(r"extensions_map\s*=.*['\"]\.js['\"]", serve, re.S) is not None
    item("static", "serve.py sets an explicit .js MIME type (registry-independent; see proposed_serve_mime.patch)",
         "PASS" if explicit else "FAIL")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(app: Path, port: int, env_extra=None, cwd=None):
    env = dict(os.environ, PYTHONUNBUFFERED="1", **(env_extra or {}))
    kw = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return subprocess.Popen([sys.executable, str(app / "serve.py"), str(port)], cwd=str(cwd or app), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)


def stop(p):
    if p.poll() is None:
        if os.name == "posix":
            os.killpg(p.pid, signal.SIGINT)
        else:
            p.send_signal(signal.CTRL_BREAK_EVENT)
    try:
        out, err = p.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate(timeout=5)
    return out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def wait_port(port, p, seconds=10):
    end = time.time() + seconds
    while time.time() < end and p.poll() is None:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def get(port, name):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/{name}", timeout=5) as r:
        return r.status, r.headers.get("Content-Type"), len(r.read())


def runtime_checks(app: Path):
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "Қала демо К11" / "city-evidence"
        shutil.copytree(app / "web", copy / "web")
        shutil.copy2(app / "serve.py", copy / "serve.py")
        other_cwd = Path(td) / "басқа"
        other_cwd.mkdir()
        # R1: path with Kazakh letters and spaces, started from another cwd (double-click starts in an arbitrary cwd)
        port = free_port()
        p = start(copy, port, {"PYTHONIOENCODING": "utf-8"}, cwd=other_cwd)
        try:
            up = wait_port(port, p)
            got = {n: get(port, n) for n in ("index.html", "app.js", "data.js")} if up else {}
        finally:
            out, err = stop(p)
        ok = up and all(s == 200 and n > 0 for s, _, n in got.values())
        item("runtime", "serve.py from a folder 'Қала демо К11' (Kazakh letters, spaces), other cwd: index/app/data served",
             "PASS" if ok else "FAIL", {"got": got, "stdout": out[:120], "stderr": err[-200:]})
        # R2: console that cannot encode Cyrillic (model of a legacy code page when serve.py is run without the .bat)
        port = free_port()
        p = start(copy, port, {"PYTHONIOENCODING": "ascii"})
        try:
            up = wait_port(port, p)
            st = get(port, "index.html")[0] if up else None
        finally:
            out, err = stop(p)
        item("runtime", "serve.py with an ASCII-only console encoding starts and prints the URL (no UnicodeEncodeError)",
             "PASS" if up and st == 200 and "http://127.0.0.1" in out and "UnicodeEncodeError" not in err else "FAIL",
             {"stdout": out[:120], "stderr": err[-200:]})
        # R3: busy port (second launch or another program on 8765)
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        p = start(copy, port)
        try:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                pass
            still_running = p.poll() is None
        finally:
            out, err = stop(p)
            blocker.close()
        last = (err.strip().splitlines() or [""])[-1]
        item("runtime", f"serve.py on a busy port fails loudly on {sys.platform} (does not hang)",
             "PASS" if not still_running and p.returncode != 0 else "FAIL", {"exit": p.returncode, "last_stderr_line": last})
        friendly = not last.startswith(("OSError", "Traceback")) and "Errno" not in last
        item("runtime", "busy port message is a short hint rather than a Python traceback", "INFO",
             {"friendly": friendly, "last_stderr_line": last})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--out")
    a = ap.parse_args()
    app = Path(a.app_root).resolve()
    static_checks(app)
    runtime_checks(app)
    import http.server
    reuse = http.server.ThreadingHTTPServer.allow_reuse_address
    item("windows", "double-click run-demo.bat in cmd.exe, py launcher, registry MIME, Windows Defender prompt", "NOT_RUN",
         "no Windows machine in this environment")
    item("windows", "HYPOTHESIS: busy port on Windows may NOT fail (ThreadingHTTPServer.allow_reuse_address=%s; on Windows "
         "SO_REUSEADDR lets a second socket bind a port in use)" % reuse, "NOT_RUN", "needs a Windows run: start run-demo.bat twice")
    counts = {s: sum(1 for i in ITEMS if i["status"] == s) for s in ("PASS", "FAIL", "INFO", "NOT_RUN")}
    report = {"tool": "tests/launcher_check.py", "label": a.label, "platform": sys.platform, "python": sys.version.split()[0],
              "kind": "static + runtime on this OS; Windows execution not_run", "counts": counts, "items": ITEMS}
    if a.out:
        Path(a.out).write_bytes((json.dumps(report, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    print(json.dumps(counts))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
