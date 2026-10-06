"""Serve web/ on http://127.0.0.1:8765 (stdlib only). Opening web/index.html directly (file://) also works.

    python serve.py [PORT] [--open]      (--open: open the page in the default browser after the server starts)

Round 9 (K11 r8): explicit MIME types — on Windows Python's mimetypes reads the registry, where .js is sometimes
registered as text/plain. A busy port gives a clear message and exit code 2; another process is never stopped.
"""
import errno
import functools
import http.server
import os
import sys
import threading
import webbrowser
from pathlib import Path

WEB = Path(__file__).resolve().parent / "web"
TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
         ".html": "text/html", ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml"}


class Handler(http.server.SimpleHTTPRequestHandler):
    # checked before mimetypes.guess_type, so a wrong registry entry cannot change these
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **TYPES}


class Server(http.server.ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind the same busy port silently; keep the default only elsewhere.
    allow_reuse_address = os.name != "nt"


def make_server(port, web=WEB):
    return Server(("127.0.0.1", port), functools.partial(Handler, directory=str(web)))


def main(argv):
    try:  # Windows consoles with a legacy code page must not crash on Cyrillic output
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    args = [a for a in argv if not a.startswith("--")]
    port = int(args[0]) if args else 8765
    if not (WEB / "index.html").exists() or not (WEB / "data.js").exists():
        print(f"Не найдены файлы демо в {WEB} (index.html, data.js). Проверьте checkout.", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{port}/"
    try:
        srv = make_server(port)
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1), 10048) or getattr(e, "winerror", None) == 10048:
            print(f"Порт {port} уже занят. Возможно, демо уже запущено — откройте {url}\n"
                  f"или запустите на другом порту: python serve.py {port + 1}", file=sys.stderr)
            return 2
        raise
    with srv:
        print(f"Городские данные: {url}  (Ctrl+C — остановить)", flush=True)
        if "--open" in argv:
            threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
