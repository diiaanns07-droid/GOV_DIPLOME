"""Copy round-5 review inputs (research/round-5/snapshots.json) byte-for-byte into inputs/r4/<slot>/.

git show <sha>:<path> via subprocess.check_output -> Path.write_bytes; sha256 recorded in inputs/r4/MANIFEST.json.
Run from anywhere inside the repository after `git fetch origin <branch>` for the listed branches.
"""
import hashlib
import json
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
SNAP_REF = "2883aeb6eb68babc9b346b0aa927d4c633f5163d"   # codex/research-import-2026-10-05 at round-5 start
DEST = APP / "inputs" / "r4"


def main():
    snap = json.loads(subprocess.check_output(["git", "show", f"{SNAP_REF}:research/round-5/snapshots.json"], cwd=ROOT))
    rows = []
    for s in snap["sources"]:
        for path in s["files"]:
            data = subprocess.check_output(["git", "show", f"{s['sha']}:{path}"], cwd=ROOT)
            rel = Path(path).relative_to("research/round-4-results")
            out = DEST / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            rows.append({"slot": s["slot"], "branch": s["branch"], "sha": s["sha"], "path": path,
                         "copied_to": str(out.relative_to(APP)), "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
    (DEST / "MANIFEST.json").write_text(json.dumps({"snapshots": f"research/round-5/snapshots.json @ {SNAP_REF}",
                                                    "files": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"copied {len(rows)} files")


if __name__ == "__main__":
    main()
