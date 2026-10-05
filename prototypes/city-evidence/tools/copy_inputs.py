"""Copy pinned inputs byte-for-byte from git objects (no merge) and write source_manifest.json.

Run from the repository root after `git fetch origin <branch>` for every branch below.
Uses `git show <sha>:<path>` via subprocess.check_output -> Path.write_bytes (no text re-encoding).
"""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).resolve().parents[1] / "inputs"

SOURCES = {
    "k10": ("claude/save-work-handoff-j7pc05", "ea703f1ddd3a411430a981164a78a7dda64ec909", "research/round-3-results/K10/", [
        "package_manifest.json",
        "data/shymkent/places_social.geojson", "data/shymkent/segments.geojson", "data/shymkent/connectors.geojson",
        "data/astana/places_social.geojson", "data/astana/segments.geojson", "data/astana/connectors.geojson",
        "scripts/offline_check.py", "scripts/geo_util.py", "scripts/k10_rules.py",
        "INPUT_FOR_K07.md", "README.md",
    ]),
    "k07": ("claude/save-work-handoff-ku3ej3", "6778deda6d3f3a7f27698f651c1b0046d2a9aae9", "research/round-3-results/K07/", [
        "prototype/index.html", "prototype/app.js", "README.md",
    ]),
}
EXTRA = {}  # filled for stage 2 (K03/K05/K02/K08)


def copy(slot, branch, sha, base, files, manifest):
    for rel in files:
        data = subprocess.check_output(["git", "show", f"{sha}:{base}{rel}"], cwd=ROOT)
        out = DEST / slot / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        manifest.append({"slot": slot.upper(), "branch": branch, "sha": sha, "path": base + rel,
                         "copied_to": str(out.relative_to(DEST.parent)), "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})


def main():
    manifest = []
    for slot, (branch, sha, base, files) in {**SOURCES, **EXTRA}.items():
        copy(slot, branch, sha, base, files, manifest)
    (DEST.parent / "source_manifest.json").write_text(
        json.dumps({"snapshots": "research/round-4/snapshots.json @ codex/research-import-2026-10-05 cadba4d",
                    "files": manifest}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"copied {len(manifest)} files")


if __name__ == "__main__":
    main()
