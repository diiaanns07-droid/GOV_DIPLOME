"""R04 stand against the REAL R02 CivicService (not the contract mock).

Usage: python3 tests/civic/R12/editor/r02_stand.py --r02-root <checkout of an R02 commit> [--port 0]
R02 code is imported from --r02-root (e.g. a detached `git worktree` of the R02 branch); nothing of R02 is copied here.
The SQLite file lives in a fresh temporary directory; one editor account is created with a random password that
exists only in this process and is printed once as JSON on stdout for the test runner. Loopback only.
Static files: the R04 harness page, web/civic/editor/*, MapLibre from the pinned app snapshot (via `git show`).
Stand-only control (not R02 API): POST /__stand/import with header X-Stand-Token=<token printed on stdout> runs R02's own
importer (ui.civic_store.importer.import_package) on a civic-v1 package, so a test can create a changed-source candidate.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]  # tests/civic/R12/editor -> корень репозитория
APP_SNAPSHOT = "6de3f253d8ec0743450259f9f13722c16cd36099"


def vendor_dir() -> Path:
    local = REPO / "web" / "vendor"
    if (local / "maplibre-gl.js").is_file():
        return local
    out = Path(tempfile.gettempdir()) / ("civic-r04-vendor-" + APP_SNAPSHOT[:12])
    out.mkdir(parents=True, exist_ok=True)
    for name in ("maplibre-gl.js", "maplibre-gl.css"):
        target = out / name
        if not target.is_file():
            target.write_bytes(subprocess.run(["git", "-C", str(REPO), "show", f"{APP_SNAPSHOT}:web/vendor/{name}"],
                                              check=True, capture_output=True).stdout)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r02-root", required=True)
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    sys.path.insert(0, str(Path(args.r02_root).resolve()))
    from ui.civic_store import CivicHttpAdapter, CivicService  # noqa: E402  (R02 code under test)
    from ui.civic_store.importer import import_package  # noqa: E402

    tmp = tempfile.TemporaryDirectory(prefix="civic-r04-r02-")
    service = CivicService(Path(tmp.name) / "civic.sqlite3")
    username, password = "editor-test", secrets.token_urlsafe(18)
    service.accounts.create_user(username, password, display_name="Тестовый редактор")
    username2, password2 = "editor-two", secrets.token_urlsafe(18)
    service.accounts.create_user(username2, password2, display_name="Второй редактор")
    control = secrets.token_urlsafe(18)
    adapter = CivicHttpAdapter(service, bind_host="127.0.0.1")
    vend = vendor_dir()
    static = {
        "/": HERE / "harness" / "index.html",
        "/vendor/maplibre-gl.js": vend / "maplibre-gl.js",
        "/vendor/maplibre-gl.css": vend / "maplibre-gl.css",
    }
    dirs = {"/harness/": HERE / "harness", "/web/civic/editor/": REPO / "web" / "civic" / "editor"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # quiet; no tokens in logs
            pass

        def _static(self):
            path = self.path.split("?", 1)[0]
            target = static.get(path)
            if target is None:
                for prefix, root in dirs.items():
                    if path.startswith(prefix):
                        candidate = (root / path[len(prefix):]).resolve()
                        if candidate.is_file() and root.resolve() in candidate.parents:
                            target = candidate
            if target is None or not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/javascript")) else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if adapter.handles(self.path):
                return adapter.serve(self)
            return self._static()

        def do_POST(self):
            if adapter.handles(self.path):
                return adapter.serve(self)
            if self.path == "/__stand/import" and secrets.compare_digest(self.headers.get("X-Stand-Token", ""), control):
                size = int(self.headers.get("Content-Length") or 0)
                try:
                    report = import_package(service.objects, json.loads(self.rfile.read(size).decode("utf-8")), actor_label="r04-stand")
                    body, status = json.dumps(report, ensure_ascii=False, default=str).encode("utf-8"), 200
                except Exception as exc:  # report the importer's refusal to the test
                    body, status = json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False).encode("utf-8"), 400
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return None
            self.send_error(405)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    port = server.server_address[1]
    print(json.dumps({"url": f"http://127.0.0.1:{port}", "username": username, "password": password,
                      "username2": username2, "password2": password2, "control": control}), flush=True)
    try:
        server.serve_forever()
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    main()
