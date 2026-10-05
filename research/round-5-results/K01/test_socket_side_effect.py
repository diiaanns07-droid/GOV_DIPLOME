"""Isolated regression test: offline_check.run() must not leave socket.* patched.

  K01_APP_ROOT=/path/to/city-evidence python3 -m unittest test_socket_side_effect -v
  (or: python3 test_socket_side_effect.py /path/to/city-evidence)
Each test runs in a fresh subprocess so global patches cannot leak between tests.
Baseline 0bf27de: test_connect_after_run and test_socket_attrs_restored are EXPECTED TO FAIL
(install_guards() restores only builtins.open). test_network_blocked_during_run must pass on any version.
"""
import os, subprocess, sys, unittest
from pathlib import Path

APP = Path(os.environ.get("K01_APP_ROOT") or (sys.argv.pop(1) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else ".")).resolve()
SCRIPTS = APP / "inputs" / "k10" / "scripts"

PRELUDE = r'''
import socket, sys, threading
sys.path.insert(0, sys.argv[1])
import offline_check
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(4); PORT = srv.getsockname()[1]
threading.Thread(target=lambda: [srv.accept() for _ in range(4)], daemon=True).start()
ORIG = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
'''


def run(code):
    r = subprocess.run([sys.executable, "-c", PRELUDE + code, str(SCRIPTS)], capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


@unittest.skipUnless((SCRIPTS / "offline_check.py").exists(), f"no offline_check.py under {SCRIPTS}")
class SocketSideEffect(unittest.TestCase):
    def test_connect_after_run(self):
        rc, out, err = run('rep = offline_check.run(); assert rep["ok"], rep["errors"]\n'
                           'socket.create_connection(("127.0.0.1", PORT), timeout=2).close(); print("OK")')
        self.assertEqual((rc, out), (0, "OK"), err[-500:])

    def test_socket_attrs_restored(self):
        rc, out, err = run('offline_check.run()\n'
                           'print((socket.socket.connect, socket.socket.connect_ex, socket.create_connection) == ORIG)')
        self.assertEqual(out, "True", err[-500:])

    def test_network_blocked_during_run(self):
        # the guard itself must still work while the check runs (fix must not drop the blocking)
        rc, out, err = run('import builtins\n'
                           'real = offline_check.check_city\n'
                           'seen = []\n'
                           'def probe(*a, **k):\n'
                           '    try:\n'
                           '        socket.create_connection(("127.0.0.1", PORT), timeout=2).close(); seen.append("connected")\n'
                           '    except offline_check.NetworkBlocked:\n'
                           '        seen.append("blocked")\n'
                           '    return real(*a, **k)\n'
                           'offline_check.check_city = probe\n'
                           'offline_check.run(); print(",".join(sorted(set(seen))))')
        self.assertEqual(out, "blocked", err[-500:])


if __name__ == "__main__":
    unittest.main(verbosity=2)
