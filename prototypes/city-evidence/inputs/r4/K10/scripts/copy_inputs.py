"""K10 round-4 review: byte-exact copy of fixed inputs from git objects, with SHA256 manifest.

Uses subprocess.check_output(["git","show",...]) + Path.write_bytes (no text pipeline).
Usage (repo root): python3 research/round-4-results/K10/scripts/copy_inputs.py
"""
import hashlib
import json
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "inputs"
K10_SHA = "ea703f1ddd3a411430a981164a78a7dda64ec909"
K10_BASE = "research/round-3-results/K10/"
SOURCES = {
    "K07": ("claude/save-work-handoff-ku3ej3", "6778deda6d3f3a7f27698f651c1b0046d2a9aae9", "research/round-3-results/K07/",
            ["scripts/graph_check.py", "scripts/requirements.txt", "K10_REQUEST.md", "results/graph_check.json"]),
}


def main():
    man = {"note": "byte copies via git show <sha>:<path>; sha256 of copied bytes", "files": []}
    for slot, (branch, sha, base, files) in SOURCES.items():
        for rel in files:
            data = subprocess.check_output(["git", "show", f"{sha}:{base}{rel}"])
            dst = OUT / slot / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
            man["files"].append({"slot": slot, "branch": branch, "commit": sha, "source_path": base + rel,
                                 "copy": str(dst.relative_to(OUT.parent)), "bytes": len(data),
                                 "sha256": hashlib.sha256(data).hexdigest()})
    # K10 package is NOT copied: it lives unchanged in this branch at research/round-3-results/K10/
    # (commit ea703f1); its files are verified in place against its own package_manifest.json.
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip())
    pm_bytes = subprocess.check_output(["git", "show", f"{K10_SHA}:{K10_BASE}package_manifest.json"])
    pm = json.loads(pm_bytes)
    ref = []
    for city in pm["cities"].values():
        for f in city["files"].values():
            disk = (root / K10_BASE / f["path"]).read_bytes()
            ref.append({"path": K10_BASE + f["path"], "commit": K10_SHA, "sha256_manifest": f["sha256"],
                        "sha256_on_disk": hashlib.sha256(disk).hexdigest(),
                        "match": hashlib.sha256(disk).hexdigest() == f["sha256"]})
    man["k10_package_referenced_in_place"] = {"branch": "claude/save-work-handoff-j7pc05", "commit": K10_SHA,
                                              "package_manifest_sha256": hashlib.sha256(pm_bytes).hexdigest(),
                                              "files": ref}
    (OUT / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(man["files"]), "files copied")


if __name__ == "__main__":
    main()
