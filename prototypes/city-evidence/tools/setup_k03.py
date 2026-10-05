"""Build inputs/k03v21_root/: copy of the byte-exact K03 mirror (inputs/k03_root, K03 @ 44585de) with the K03 r5
k03_assign_v2_1.patch applied (rule v2 + guard against empty ambiguity zones, D3).

Replaces the round-5 copy k03v21_root (v2 patch of K03 r4). The original mirror stays untouched.
MANIFEST_K03.json records the original and patched sha256 of the code and sha256 of every file of the copy;
tools/build_evidence.py refuses to run if the copy differs from this manifest (INTEGRITY).
The patched boundary_validator.py is a local copy, not the upstream file.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SRC = APP / "inputs" / "k03_root"
OUT = APP / "inputs" / "k03v21_root"
PATCH = APP / "inputs" / "r5" / "K03" / "patches" / "k03_assign_v2_1.patch"
TARGET = "research/round-3-results/K03/boundary_validator.py"


def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SRC, OUT, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.check_call(["patch", "-p1", "--quiet", "--no-backup-if-mismatch", "-d", str(OUT), "-i", str(PATCH)])
    files = {str(p.relative_to(OUT)): h(p) for p in sorted(OUT.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
    (OUT / "MANIFEST_K03.json").write_text(json.dumps({
        "rule_patch": "k03_assign_v2_1 (K03 r5 @ 5715a7f: v2 + empty-zone guard D3)",
        "base": "inputs/k03_root (K03 @ 44585de, byte-exact)",
        "patch": {"path": str(PATCH.relative_to(APP)), "sha256": h(PATCH)},
        "modified": [{"path": TARGET, "original_sha256": h(SRC / TARGET), "patched_sha256": h(OUT / TARGET)}],
        "files": files,
        "note": "patched local copy; all other files identical to inputs/k03_root",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("k03_assign_v2_1 applied:", h(OUT / TARGET)[:16], f"({len(files)} files)")


if __name__ == "__main__":
    main()
