"""Extract a BUILD tree byte-for-byte from git objects into a temp folder (no checkout, no merge).

Usage (from a GOV_DIPLOME clone, after `git fetch origin <branch>`):
  python3 extract_build.py --sha 0bf27deb8549b325b34a9610402613d745544edb [--path prototypes/city-evidence/] [--dest DIR]
Prints the extracted app root. Writes <dest>/EXTRACT_MANIFEST.json (blob, bytes, sha256 per file).
"""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--sha", required=True)
ap.add_argument("--path", default="prototypes/city-evidence/")
ap.add_argument("--dest", default=None)
a = ap.parse_args()
prefix = a.path.rstrip("/") + "/"
dest = Path(a.dest or tempfile.mkdtemp(prefix="k01r5_build_")).resolve()
root = dest / Path(prefix).name
out = subprocess.check_output(["git", "ls-tree", "-r", "-z", a.sha, "--", prefix])
files = []
for rec in filter(None, out.split(b"\0")):
    meta, path = rec.split(b"\t", 1)
    mode, typ, blob = meta.decode().split()
    path = path.decode("utf-8")
    if typ != "blob":
        continue
    data = subprocess.check_output(["git", "cat-file", "blob", blob])
    t = root / path[len(prefix):]
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_bytes(data)
    h = hashlib.sha256(data).hexdigest()
    if hashlib.sha256(t.read_bytes()).hexdigest() != h:
        raise SystemExit(f"byte mismatch after write: {path}")
    files.append({"path": path[len(prefix):], "mode": mode, "blob": blob, "bytes": len(data), "sha256": h})
if not files:
    raise SystemExit(f"no files under {prefix} at {a.sha}")
(dest / "EXTRACT_MANIFEST.json").write_text(json.dumps(
    {"sha": a.sha, "prefix": prefix, "files": files}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(root)
