#!/usr/bin/env python3
"""K07 round 8: byte-exact extraction of prototypes/city-evidence/{web,tests} of a BUILD commit outside the repo.

Based on research/round-7-results/K07/scripts/extract_build.py (recursive: web/attribution/ is a subdirectory).
Byte-safe: subprocess.check_output -> Path.write_bytes, SHA-256 re-read and compared. Usage (repo root):
    python3 research/round-8-results/K07/scripts/extract_build.py OUT_DIR [--sha COMMIT] [--no-tests]
Default COMMIT: BUILD a5b5e2d (research/round-8/snapshots.json; code equal to 4e93f30). OUT_DIR gets web/… and
tests/…, usable as --app-root. The manifest goes to research/round-8-results/K07/results/build_snapshot_<sha7>.json.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path

DEFAULT_SHA = "a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d"
BASE = "prototypes/city-evidence/"
K07 = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--sha", default=DEFAULT_SHA)
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    dirs = [BASE + "web"] + ([] if a.no_tests else [BASE + "tests"])
    listing = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", a.sha, "--", *dirs]).decode().split("\n")
    rows = []
    for full in filter(None, listing):
        rel = full[len(BASE):]
        data = subprocess.check_output(["git", "cat-file", "blob", f"{a.sha}:{full}"])
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        rows.append({"file": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                     "identical": dst.read_bytes() == data})
    assert rows and all(r["identical"] for r in rows)
    m = {"build_sha": a.sha, "source_dirs": dirs, "files": rows}
    (K07 / "results").mkdir(parents=True, exist_ok=True)
    (K07 / f"results/build_snapshot_{a.sha[:7]}.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} files extracted from {a.sha[:7]}, all byte-identical")


if __name__ == "__main__":
    main()
