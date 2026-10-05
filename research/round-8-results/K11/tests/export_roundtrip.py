"""K11 round 8 stage 3: read an exported scenario file (any directory, any name) and solve it with the independent
Python oracle. Reads bytes and decodes UTF-8 itself, so the OS code page never matters.

    python tests/export_roundtrip.py <exported scenario.json> <context.json>
Prints ASCII-only JSON (safe for any console code page): status + selected ids per objective.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "oracle"))
from plan_oracle import solve  # noqa: E402

raw = Path(sys.argv[1]).read_bytes()
if raw.startswith(b"\xef\xbb\xbf"):
    raw = raw[3:]
sc = json.loads(raw.decode("utf-8"))
sc.pop("derived_results", None)
ctx = json.loads(Path(sys.argv[2]).read_bytes().decode("utf-8"))
r = solve(ctx, sc)
print(json.dumps({"status": r["status"], "objectives": {k: v["selected_ids"] for k, v in (r.get("objectives") or {}).items()}}))
