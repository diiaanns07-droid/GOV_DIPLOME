#!/usr/bin/env python3
"""Байтовая копия web/ закреплённого BUILD в каталог (по умолчанию scratch) + MANIFEST (git blob и sha256).

  python3 scripts/pin_build.py --sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --out /tmp/k09_build_d865dd4
Копия не коммитится (это код BUILD); коммитится только manifest (inputs/BUILD_MANIFEST_<sha7>.json).
"""
import argparse, hashlib, json, subprocess
from pathlib import Path

K = Path(__file__).resolve().parents[1]
REPO = K.parents[2]
APP = "prototypes/city-evidence"


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", default="d865dd4a124291e10dd0b7bb1d9eada20d34c268")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sha = git("rev-parse", a.sha).decode().strip()
    out = Path(a.out)
    files = []
    for line in git("ls-tree", "-r", sha, f"{APP}/web", f"{APP}/tests", f"{APP}/tools").decode().splitlines():
        meta, path = line.split("\t", 1)
        mode, typ, blob = meta.split()
        raw = git("cat-file", "blob", blob)
        dst = out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        files.append({"path": path, "git_blob": blob, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    code_tree = git("rev-parse", f"{sha}:{APP}").decode().strip()
    man = {"build_sha": sha, "app_tree": code_tree, "copied": "web/, tests/, tools/ (байтовая копия через git cat-file)", "files": files}
    (K / "inputs").mkdir(exist_ok=True)
    (K / f"inputs/BUILD_MANIFEST_{sha[:7]}.json").write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{sha} app_tree={code_tree} files={len(files)} -> {out}")


if __name__ == "__main__":
    main()
