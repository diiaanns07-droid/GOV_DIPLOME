"""Build inputs/k03v2_root/: copy of the byte-exact K03 mirror (inputs/k03_root) with K03 r4 k03_assign_v2.patch applied.

The original mirror stays untouched; MANIFEST_K03V2.json records original and patched sha256.
The patched boundary_validator.py is a local copy, not the upstream file.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "inputs" / "k03_root"
OUT = APP / "inputs" / "k03v2_root"
PATCH = APP / "inputs" / "r4" / "K03" / "patches" / "k03_assign_v2.patch"
TARGET = "research/round-3-results/K03/boundary_validator.py"


def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.check_call(["patch", "-p1", "--quiet", "--no-backup-if-mismatch", "-d", str(OUT), "-i", str(PATCH)])
    (OUT / "MANIFEST_K03V2.json").write_text(json.dumps({
        "rule": "k03_assign_v2",
        "base": "inputs/k03_root (K03 @ 44585de, byte-exact)",
        "patch": {"path": str(PATCH.relative_to(APP)), "sha256": h(PATCH), "source": "K03 @ 3660527"},
        "modified": [{"path": TARGET, "original_sha256": h(SRC / TARGET), "patched_sha256": h(OUT / TARGET)}],
        "note": "patched local copy; other files identical to inputs/k03_root",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("k03_assign_v2 applied:", h(OUT / TARGET)[:16])


if __name__ == "__main__":
    main()
