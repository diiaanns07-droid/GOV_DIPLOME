"""K11 round 5: extract a git snapshot of prototypes/city-evidence byte-exactly (no checkout, no merge).

Usage (inside a clone that has the commit, e.g. after `git fetch origin claude/beautiful-clarke-sbzomj`):
    python research/round-5-results/K11/extract_build.py --sha 0bf27deb8549b325b34a9610402613d745544edb --out <dir>
Writes <dir>/prototypes/city-evidence/... and <dir>/EXTRACT_MANIFEST.json (path, blob, sha256, bytes).
Each file: `git cat-file blob` -> Path.write_bytes, then the git blob id is recomputed from the written
bytes (no filters, independent of core.autocrlf) and compared with the source blob id.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PREFIX = "prototypes/city-evidence/"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default=PREFIX)
    a = ap.parse_args()
    out = Path(a.out)
    rows = []
    for line in git("ls-tree", "-r", "-z", a.sha, a.prefix).split(b"\0"):
        if not line:
            continue
        meta, path = line.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        if kind != "blob":
            continue
        rel = path.decode("utf-8")
        data = git("cat-file", "blob", blob)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        written = dst.read_bytes()
        rows.append({"path": rel, "mode": mode, "blob": blob, "sha256": hashlib.sha256(written).hexdigest(),
                     "bytes": len(written), "blob_matches": blob_id(written) == blob})
    bad = [r["path"] for r in rows if not r["blob_matches"]]
    (out / "EXTRACT_MANIFEST.json").write_text(json.dumps(
        {"source_sha": a.sha, "prefix": a.prefix, "files": rows, "all_blobs_match": not bad},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(rows)} files extracted to {out}; blob mismatches: {len(bad)}")
    return 1 if bad or not rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
