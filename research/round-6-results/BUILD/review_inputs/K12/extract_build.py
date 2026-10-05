"""Extract prototypes/city-evidence at a given commit into a directory, byte-for-byte.

git ls-tree -> git show <sha>:<path> via subprocess.check_output -> Path.write_bytes; every file is
re-hashed as a git blob and compared with the tree entry. No network, no checkout, no merge.

Usage (from the repository root, after `git fetch origin <branch>`):
    python research/round-5-results/K12/extract_build.py <commit> <dest_dir> [--json manifest.json]
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PREFIX = "prototypes/city-evidence/"


def git(*args):
    return subprocess.check_output(["git", *args])


def blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def extract(commit, dest):
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} is not empty")
    entries = []
    for line in git("ls-tree", "-r", "-z", commit, PREFIX).split(b"\0"):
        if not line:
            continue
        meta, path = line.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        if kind != "blob":
            continue
        path = path.decode()
        data = git("show", f"{commit}:{path}")
        if blob_id(data) != oid:
            raise SystemExit(f"blob mismatch for {path}")
        out = dest / path[len(PREFIX):]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        entries.append({"path": path[len(PREFIX):], "git_blob": oid, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    return {"commit": git("rev-parse", commit).decode().strip(), "prefix": PREFIX, "files": entries}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("commit")
    ap.add_argument("dest")
    ap.add_argument("--json")
    a = ap.parse_args()
    man = extract(a.commit, a.dest)
    if a.json:
        Path(a.json).write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    print(f"{len(man['files'])} files from {man['commit']} -> {a.dest}", file=sys.stderr)
