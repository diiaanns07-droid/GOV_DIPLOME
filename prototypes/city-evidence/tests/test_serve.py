"""serve.py: explicit MIME types under a MODELLED wrong Windows registry (.js -> text/plain) and a busy port.
This is a model on Linux, not a test of real Windows. Usage: python3 -m unittest tests.test_serve"""
import mimetypes
import socket
import subprocess
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import serve  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Serve(unittest.TestCase):
    def test_mime_with_modelled_wrong_registry(self):
        saved = dict(mimetypes.types_map)
        mimetypes.add_type("text/plain", ".js")  # what a broken Windows registry entry does
        mimetypes.add_type("text/plain", ".css")
        mimetypes.add_type("text/plain", ".json")
        try:
            self.assertEqual(mimetypes.guess_type("x.js")[0], "text/plain")  # the model is in effect
            srv = serve.make_server(free_port())
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                base = f"http://127.0.0.1:{srv.server_address[1]}/"
                for name, want in (("app.js", "text/javascript"), ("plan.js", "text/javascript"), ("index.html", "text/html")):
                    with urllib.request.urlopen(base + name) as r:
                        self.assertEqual(r.headers.get_content_type(), want, name)
            finally:
                srv.shutdown()
                srv.server_close()
        finally:
            mimetypes.types_map.clear()
            mimetypes.types_map.update(saved)

    def test_busy_port_message_and_exit_code(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            port = s.getsockname()[1]
            r = subprocess.run([sys.executable, str(APP / "serve.py"), str(port)], capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("уже занят", r.stderr)
            self.assertIn(str(port + 1), r.stderr)
            # the process holding the port is untouched
            s.getsockname()


if __name__ == "__main__":
    unittest.main()
