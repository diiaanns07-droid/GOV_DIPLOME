"""Copy round-5 REVIEW files listed in research/round-6/snapshots.json byte-for-byte into review_inputs/<slot>/.
git show <sha>:<path> -> Path.write_bytes; sha256 in review_inputs/MANIFEST.json. Skips the BUILD's own (K04) files."""
import hashlib, json, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
SNAP_REF = "edee718366ee4f085ea540c4e53a8dabf3c93fce"
DEST = HERE / "review_inputs"


def main():
    snap = json.loads(subprocess.check_output(["git", "show", f"{SNAP_REF}:research/round-6/snapshots.json"], cwd=ROOT))
    rows = []
    for s in snap["sources"]:
        if s["slot"] == "K04":
            continue
        for path in s["files"]:
            data = subprocess.check_output(["git", "show", f"{s['sha']}:{path}"], cwd=ROOT)
            out = DEST / Path(path).relative_to("research/round-5-results")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            rows.append({"slot": s["slot"], "branch": s["branch"], "sha": s["sha"], "path": path,
                         "copied_to": str(out.relative_to(HERE)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (DEST / "MANIFEST.json").write_text(json.dumps({"snapshots": f"research/round-6/snapshots.json @ {SNAP_REF}",
        "target_build": "064ed25368341edaa50289bc29e21dda7bdd9440", "files": rows}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print(f"copied {len(rows)} files")


if __name__ == "__main__":
    main()
