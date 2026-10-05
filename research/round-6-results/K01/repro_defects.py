"""Minimal repro of K01 round-6 defects D1/D2 on an extracted prototype (stdlib).
  python3 repro_defects.py --app-root PATH     (PATH = extract_build.py output, NOT inside the repo tree)
D1: tools/check_all.py 'facts' step crashes outside the repo (verified_explainer looks for ../agent/evidence.py).
D2: a byte flip in an unmodified inputs/k03v2_root file is not detected by check_all 'inputs'.
Works on a temp copy; the given app root is not modified. Exit 0 = both defects reproduced."""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

ap = argparse.ArgumentParser(); ap.add_argument("--app-root", type=Path, required=True); a = ap.parse_args()
tmp = Path(tempfile.mkdtemp(prefix="k01r6_repro_"))
try:
    app = tmp / "city-evidence"
    shutil.copytree(a.app_root.resolve(), app, ignore=shutil.ignore_patterns("__pycache__"))

    def run():
        log = tmp / "log.json"
        subprocess.run([sys.executable, str(app / "tools/check_all.py"), "--log", str(log)], cwd=tmp, capture_output=True)
        return json.loads(log.read_text(encoding="utf-8"))["results"]

    r = run()
    d1 = [x for x in r if x["step"] == "facts" and x["status"] == "FAIL"]
    print("D1", "REPRODUCED" if d1 else "not reproduced", d1[:1])
    f = app / "inputs/k03v2_root/data/astana_districts.geojson"
    b = bytearray(f.read_bytes()); i = b.index(b'"name"') + 1; b[i] = ord("N"); f.write_bytes(bytes(b))
    r2 = run()
    inp = [x["status"] for x in r2 if x["step"] == "inputs"]
    d2 = bool(inp) and all(s == "pass" for s in inp)
    print("D2", "REPRODUCED" if d2 else "not reproduced", f"inputs checks after byte flip: {inp}")
    sys.exit(0 if d1 and d2 else 1)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
