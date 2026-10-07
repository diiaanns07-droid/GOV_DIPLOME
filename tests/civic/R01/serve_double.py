"""Run the real app (same Handler, same page) with the civic TEST DOUBLE gateway.

    python -B tests/civic/R01/serve_double.py --port 8612

For browser smoke tests only. Data lives in memory and disappears on exit; this is
NOT the R02/R06 backend. The editor password is taken from CIVIC_TEST_PASSWORD or
generated and printed once; nothing is written to disk.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contract_double import make_double_gateway  # noqa: E402
from ui.web_server import create_server  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "civic_object.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8612)
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    gateway, store = make_double_gateway([fixture])
    password = os.environ.get("CIVIC_TEST_PASSWORD") or secrets.token_urlsafe(12)
    store.add_editor("test-editor", password)
    server = create_server(ROOT, port=args.port, host="127.0.0.1", civic=gateway)
    print("TEST DOUBLE civic backend (in memory, not R02/R06).", flush=True)
    if "CIVIC_TEST_PASSWORD" not in os.environ:
        print(f"test-editor password: {password}", flush=True)
    print(f"http://127.0.0.1:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
