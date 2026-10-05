"""K11 round 8 stage 3: MODELED Windows registry MIME problem for the demo's serve.py (stdlib only).

    python tests/serve_mime_modeled.py --app-root <copy of prototypes/city-evidence> [--label X] [--out report.json]

Starts <app-root>/serve.py twice on free ports (normal, and with a sitecustomize that maps .js -> text/plain the way a
Windows registry entry can), requests a .js file and index.html, records Content-Type, and stops each server it
started (SIGINT, then terminate/kill). This models Windows; it is not a run on Windows.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_case(app_root: Path, poison: bool):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        if poison:
            (Path(td) / "sitecustomize.py").write_text(
                "import mimetypes\nmimetypes.add_type('text/plain', '.js')  # model of a Windows registry entry\n",
                encoding="utf-8")
            env["PYTHONPATH"] = td + os.pathsep + env.get("PYTHONPATH", "")
        port = free_port()
        kw = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        p = subprocess.Popen([sys.executable, "serve.py", str(port)], cwd=str(app_root), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
        try:
            for _ in range(100):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            js = sorted((app_root / "web").glob("*.js"))[0].name
            got = {}
            for name in (js, "index.html"):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/{name}", timeout=5) as r:
                    got[name] = r.headers.get("Content-Type")
            return {"poisoned_js_to_text_plain": poison, "js_file": js, "content_types": got}
        finally:
            if p.poll() is None and os.name == "posix":
                os.killpg(p.pid, signal.SIGINT)
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
            p.communicate(timeout=5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--out")
    a = ap.parse_args()
    root = Path(a.app_root).resolve()
    cases = [run_case(root, False), run_case(root, True)]
    js_ok = all((c["content_types"][c["js_file"]] or "").split(";")[0] in ("text/javascript", "application/javascript") for c in cases)
    report = {"tool": "tests/serve_mime_modeled.py", "label": a.label, "kind": "MODELED Windows registry (not a Windows run)",
              "cases": cases, "js_served_as_javascript_even_when_poisoned": js_ok}
    if a.out:
        Path(a.out).write_bytes((json.dumps(report, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    for c in cases:
        print(("poisoned" if c["poisoned_js_to_text_plain"] else "normal  "), c["content_types"])
    print(("PASS" if js_ok else "FAIL") + " .js served as JavaScript in both cases")
    return 0 if js_ok else 1


if __name__ == "__main__":
    sys.exit(main())
