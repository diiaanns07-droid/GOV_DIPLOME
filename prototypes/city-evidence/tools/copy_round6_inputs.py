"""Copy the round-5 REVIEW patches the build applies (research/round-6/snapshots.json) into inputs/r5/<slot>/.

git show <sha>:<path> via subprocess.check_output -> Path.write_bytes; sha256 in inputs/r5/MANIFEST.json.
"""
import hashlib
import json
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
SNAP_REF = "edee718366ee4f085ea540c4e53a8dabf3c93fce"
WANT = {
    "K05": ["research/round-5-results/K05/patches/k05r3_count_units_after_k12.patch",
            "research/round-5-results/K05/patches/k05r4_contract_k12_compat.patch",
            "research/round-5-results/K05/proposed/k05r4_contract.py"],
    "K03": ["research/round-5-results/K03/patches/k03_assign_v2_1.patch",
            "research/round-5-results/K03/patches/build_p1_binding.patch"],
}
DEST = APP / "inputs" / "r5"


def main():
    snap = json.loads(subprocess.check_output(["git", "show", f"{SNAP_REF}:research/round-6/snapshots.json"], cwd=ROOT))
    sha = {s["slot"]: (s["branch"], s["sha"]) for s in snap["sources"]}
    rows = []
    for slot, paths in WANT.items():
        branch, commit = sha[slot]
        for path in paths:
            data = subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)
            out = DEST / Path(path).relative_to("research/round-5-results")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            rows.append({"slot": slot, "branch": branch, "sha": commit, "path": path, "copied_to": str(out.relative_to(APP)),
                         "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    (DEST / "MANIFEST.json").write_text(json.dumps({"snapshots": f"research/round-6/snapshots.json @ {SNAP_REF}", "files": rows},
                                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"copied {len(rows)} files")


if __name__ == "__main__":
    main()
