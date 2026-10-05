"""Serve web/ on http://127.0.0.1:8765 (stdlib only). Opening web/index.html directly (file://) also works.

    python serve.py [PORT] [--open]      (--open: open the page in the default browser after the server starts)
"""
import functools
import http.server
import sys
import threading
import webbrowser
from pathlib import Path

try:  # Windows consoles with a legacy code page must not crash on Cyrillic output
    sys.stdout.reconfigure(errors="replace")
except AttributeError:
    pass

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PORT = int(args[0]) if args else 8765
WEB = Path(__file__).resolve().parent / "web"
if not (WEB / "index.html").exists() or not (WEB / "data.js").exists():
    sys.exit(f"Не найдены файлы демо в {WEB} (index.html, data.js). Проверьте checkout.")
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as srv:
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Городские данные: {url}  (Ctrl+C — остановить)", flush=True)
    if "--open" in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
