#!/usr/bin/env python3
"""K07 round 4 REVIEW: extract the fixed round-3 K07 prototype from Git into a directory (outside the repo by default).

Byte-safe: subprocess.check_output + Path.write_bytes; SHA-256 of every file is compared with the Git blob content.
Usage (repo root): python3 research/round-4-results/K07/scripts/extract_snapshot.py [OUT_DIR]
Default OUT_DIR: $TMPDIR/k07r4-snapshot. Prints a JSON manifest; the same manifest is stored in results/snapshot_manifest.json.
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

SNAP_SHA = "6778deda6d3f3a7f27698f651c1b0046d2a9aae9"   # research/round-4/snapshots.json, slot K07
SNAP_BRANCH = "claude/save-work-handoff-ku3ej3"
SRC = "research/round-3-results/K07/prototype"
FILES = ["index.html", "app.js", "data.js"]
K07R4 = Path(__file__).resolve().parents[1]


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("TMPDIR", tempfile.gettempdir())) / "k07r4-snapshot"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in FILES:
        data = subprocess.check_output(["git", "cat-file", "blob", f"{SNAP_SHA}:{SRC}/{f}"])
        (out / f).write_bytes(data)
        back = (out / f).read_bytes()
        rows.append({"file": f, "bytes": len(data), "sha256_git": hashlib.sha256(data).hexdigest(),
                     "sha256_written": hashlib.sha256(back).hexdigest(), "identical": back == data})
    assert all(r["identical"] for r in rows)
    m = {"snapshot_branch": SNAP_BRANCH, "snapshot_sha": SNAP_SHA, "source_dir": SRC, "out_dir": str(out), "files": rows}
    res = {k: v for k, v in m.items() if k != "out_dir"}
    (K07R4 / "results").mkdir(exist_ok=True)
    (K07R4 / "results/snapshot_manifest.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()
