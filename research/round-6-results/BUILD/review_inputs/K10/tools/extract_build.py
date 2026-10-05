"""Extract prototypes/city-evidence from a BUILD commit into a directory (byte-exact).

Each file is read with `git show <sha>:<path>` via subprocess.check_output and written with
Path.write_bytes; its git blob id is recomputed and compared with `git ls-tree`.
Usage (inside a clone that has the commit):
    python3 extract_build.py --sha 0bf27deb8549b325b34a9610402613d745544edb --out /tmp/build_0bf27de
Then run the QA tools/tests with --app-root /tmp/build_0bf27de/prototypes/city-evidence
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PREFIX = "prototypes/city-evidence/"


def blob_id(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    rows = subprocess.check_output(["git", "ls-tree", "-r", a.sha, PREFIX]).decode().splitlines()
    files = []
    for row in rows:
        meta, path = row.split("\t", 1)
        _mode, kind, oid = meta.split()
        if kind != "blob":
            continue
        data = subprocess.check_output(["git", "show", f"{a.sha}:{path}"])
        if blob_id(data) != oid:
            raise SystemExit(f"blob mismatch: {path}")
        dst = out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        files.append({"path": path, "git_blob": oid, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    man = {"commit": a.sha, "prefix": PREFIX, "files": len(files), "entries": files}
    (out / "EXTRACT_MANIFEST.json").write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"commit": a.sha, "files": len(files), "app_root": str(out / PREFIX)}))


if __name__ == "__main__":
    main()
