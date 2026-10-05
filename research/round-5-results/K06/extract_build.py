"""Extract prototypes/city-evidence from a BUILD commit byte-exactly (git show -> write_bytes) and record SHA256.
Usage (repo root, after git fetch origin claude/beautiful-clarke-sbzomj):
  python3 research/round-5-results/K06/extract_build.py <out_dir> [<commit_sha>]"""
import hashlib, json, pathlib, subprocess, sys
out = pathlib.Path(sys.argv[1]); sha = sys.argv[2] if len(sys.argv) > 2 else "0bf27deb8549b325b34a9610402613d745544edb"
root = "prototypes/city-evidence"
files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", sha, root]).decode().split("\n")
man = {"commit": sha, "path": root, "files": {}}
for f in filter(None, files):
    b = subprocess.check_output(["git", "show", f"{sha}:{f}"])
    blob = subprocess.check_output(["git", "rev-parse", f"{sha}:{f}"]).decode().strip()
    # git blob id recomputed from the written bytes proves the copy is exact
    assert hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest() == blob, f
    p = out / f[len(root) + 1:]; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
    man["files"][f[len(root) + 1:]] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
(out / "_extract_manifest.json").write_text(json.dumps(man, indent=1))
print(len(man["files"]), "files extracted from", sha, "-> git blob ids verified")
