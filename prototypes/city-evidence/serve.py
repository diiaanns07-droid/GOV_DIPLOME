"""Serve web/ on http://127.0.0.1:8765 (stdlib only). Opening web/index.html directly (file://) also works."""
import functools
import http.server
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
WEB = Path(__file__).resolve().parent / "web"
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(WEB))
with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler) as srv:
    print(f"Городские данные: http://127.0.0.1:{PORT}/  (Ctrl+C — остановить)")
    srv.serve_forever()
