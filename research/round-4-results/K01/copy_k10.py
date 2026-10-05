"""K01 round-4: байтовая копия пакета K10 раунда 3 из git-объекта по закреплённому SHA.
Usage: python3 copy_k10.py <dest_dir>   (запускать из клона GOV_DIPLOME после git fetch ветки K10)
Пишет <dest_dir>/K10/... и <dest_dir>/COPY_MANIFEST.json (blob, sha256, bytes)."""
import hashlib, json, subprocess, sys
from pathlib import Path

SHA = "ea703f1ddd3a411430a981164a78a7dda64ec909"
BRANCH = "claude/save-work-handoff-j7pc05"
PREFIX = "research/round-3-results/K10/"

dest = Path(sys.argv[1]).resolve()
out = subprocess.check_output(["git", "ls-tree", "-r", "-z", SHA, "--", PREFIX])
entries = []
for rec in out.split(b"\0"):
    if not rec:
        continue
    meta, path = rec.split(b"\t", 1)
    mode, typ, blob = meta.decode().split()
    path = path.decode("utf-8")
    data = subprocess.check_output(["git", "cat-file", "blob", blob])
    target = dest / "K10" / path[len(PREFIX):]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()
    entries.append({"path": path[len(PREFIX):], "mode": mode, "blob": blob,
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
(dest / "COPY_MANIFEST.json").write_text(json.dumps(
    {"source_branch": BRANCH, "source_sha": SHA, "source_prefix": PREFIX,
     "files": entries}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"copied {len(entries)} files, {sum(e['bytes'] for e in entries)} bytes -> {dest}")
