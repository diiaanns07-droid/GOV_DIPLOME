#!/usr/bin/env python3
"""K07 round 6: extract prototypes/city-evidence/web/ of a BUILD commit (recursively) outside the repo.

Adapter of research/round-5-results/K07/scripts/extract_build.py (56c8bff): the r5 version listed only the top level of
web/ and read every entry as a blob; BUILD 064ed25 has a web/attribution/ subdirectory, so the r5 extractor would stop on
a tree entry (TEST_INCOMPATIBLE, not a product defect). Byte-safe: subprocess.check_output -> Path.write_bytes, SHA-256
re-read and compared. Usage (repo root):
    python3 research/round-6-results/K07/scripts/extract_build.py OUT_DIR [--sha COMMIT]
Default COMMIT: BUILD 064ed25 (research/round-6/snapshots.json). OUT_DIR gets web/…, usable as --app-root.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path

DEFAULT_SHA = "064ed25368341edaa50289bc29e21dda7bdd9440"
SRC = "prototypes/city-evidence/web"
R6 = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--sha", default=DEFAULT_SHA)
    a = ap.parse_args()
    out = Path(a.out)
    listing = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", a.sha, "--", SRC]).decode().split("\n")
    rows = []
    for full in filter(None, listing):
        rel = full[len("prototypes/city-evidence/"):]          # web/...
        data = subprocess.check_output(["git", "cat-file", "blob", f"{a.sha}:{full}"])
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        rows.append({"file": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                     "identical": dst.read_bytes() == data})
    assert rows and all(r["identical"] for r in rows)
    m = {"build_sha": a.sha, "source_dir": SRC, "files": rows}
    (R6 / "results").mkdir(exist_ok=True)
    (R6 / f"results/build_snapshot_{a.sha[:7]}.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} files extracted from {a.sha[:7]}, all byte-identical")


if __name__ == "__main__":
    main()
