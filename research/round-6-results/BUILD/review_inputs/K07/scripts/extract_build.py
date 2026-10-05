#!/usr/bin/env python3
"""K07 round 5 REVIEW: extract prototypes/city-evidence/web/ of a BUILD commit into a directory outside the repo.

Byte-safe (subprocess.check_output -> Path.write_bytes), SHA-256 of every written file is re-read and compared.
Usage (repo root): python3 research/round-5-results/K07/scripts/extract_build.py OUT_DIR [--sha COMMIT]
Default COMMIT: BUILD K04 @ 0bf27de (research/round-5/snapshots.json). OUT_DIR gets web/…, so it can be passed as --app-root.
Writes results/build_snapshot_<sha7>.json (manifest without local paths).
"""
import argparse, hashlib, json, subprocess
from pathlib import Path

DEFAULT_SHA = "0bf27deb8549b325b34a9610402613d745544edb"
SRC = "prototypes/city-evidence/web"
R5 = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--sha", default=DEFAULT_SHA)
    a = ap.parse_args()
    out = Path(a.out) / "web"
    out.mkdir(parents=True, exist_ok=True)
    names = subprocess.check_output(["git", "ls-tree", "--name-only", f"{a.sha}:{SRC}"]).decode().split()
    rows = []
    for n in names:
        data = subprocess.check_output(["git", "cat-file", "blob", f"{a.sha}:{SRC}/{n}"])
        (out / n).write_bytes(data)
        back = (out / n).read_bytes()
        rows.append({"file": f"web/{n}", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "identical": back == data})
    assert rows and all(r["identical"] for r in rows)
    m = {"build_sha": a.sha, "source_dir": SRC, "files": rows}
    (R5 / "results").mkdir(exist_ok=True)
    (R5 / f"results/build_snapshot_{a.sha[:7]}.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(m, indent=1))


if __name__ == "__main__":
    main()
