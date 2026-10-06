"""Call one function of a module from a pinned checkout in an isolated interpreter.

Usage (normally via call_module() below):
  python -I -B modrun.py ROOT module.path:function < args.json

-I drops PYTHONPATH/user site, so the module can only come from ROOT. The reply
records the imported file and ROOT's git SHA, which is the "exact tested SHA".
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time


def _child(root: str, target: str) -> None:
    sys.path.insert(0, root)
    module_name, func_name = target.split(":")
    args = json.loads(sys.stdin.read() or "[]")
    import importlib

    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        result = func(*args)
        out = {"ok": True, "result": result, "module_file": getattr(module, "__file__", None)}
    except Exception as exc:  # report, the caller decides PASS/FAIL
        out = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:2000]}
    print(json.dumps(out, ensure_ascii=False, default=str, allow_nan=True))


def call_module(root, target: str, *args, timeout: float = 120.0) -> dict:
    """Run module:function(*args) under ROOT in a fresh `python -I`; return the JSON reply."""
    root = str(Path(root).resolve())
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-I", "-B", __file__, root, target],
                          input=json.dumps(list(args), ensure_ascii=False),
                          capture_output=True, text=True, timeout=timeout, cwd=root)
    try:
        reply = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        reply = {"ok": False, "error_type": "NoJSON", "error": (proc.stderr or proc.stdout)[-2000:]}
    sha = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True)
    reply["root_sha"] = sha.stdout.strip() or None
    reply["exit_code"] = proc.returncode
    reply["seconds"] = round(time.monotonic() - started, 3)
    return reply


def module_available(root, module_path: str) -> bool:
    """True when ROOT contains the package/module file (no import performed)."""
    base = Path(root) / Path(*module_path.split("."))
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


if __name__ == "__main__":
    _child(sys.argv[1], sys.argv[2])
