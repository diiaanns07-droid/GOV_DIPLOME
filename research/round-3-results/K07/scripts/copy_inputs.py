#!/usr/bin/env python3
"""K07 round 3: copy K10 inputs byte-exactly from the fixed snapshot and write inputs/MANIFEST.json.

Run from the repository root after `git fetch origin claude/save-work-handoff-j7pc05`:
    python3 research/round-3-results/K07/scripts/copy_inputs.py
Copies with `git cat-file blob` (raw bytes, no shell redirection re-encoding) and checks that the git blob id of
every copy equals the blob id of the source.
"""
import hashlib, json, subprocess
from pathlib import Path

K10_SHA = "e91898d596164bcf6e853b921a49f82126074a35"
K10_BRANCH = "claude/save-work-handoff-j7pc05"
SRC = "research/next-round/K10"
FILES = [
    "samples/shymkent_districts_overture.geojson", "samples/astana_districts_overture.geojson",
    "samples/shymkent_places_social_sample.jsonl", "samples/astana_places_social_sample.jsonl",
    "samples/shymkent_road_segments_sample.geojson", "samples/astana_road_segments_sample.geojson",
    "provenance/shymkent_places.provenance.json", "provenance/astana_places.provenance.json",
    "provenance/shymkent_segment.provenance.json", "provenance/astana_segment.provenance.json",
    "provenance/shymkent_division_area.provenance.json", "provenance/astana_division_area.provenance.json",
    "provenance/raw_extracts.sha256", "datasets.json",
    "results/E02_social_poi_by_district.json", "results/E03_road_network_by_district.json",
]
K07 = Path(__file__).resolve().parents[1]
OUT = K07 / "inputs/k10"


def git(*a, inp=None):
    return subprocess.run(["git", *a], capture_output=True, check=True, input=inp).stdout


def main():
    rows = []
    for rel in FILES:
        data = git("cat-file", "blob", f"{K10_SHA}:{SRC}/{rel}")
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        src_blob = git("rev-parse", f"{K10_SHA}:{SRC}/{rel}").decode().strip()
        copy_blob = git("hash-object", str(dst)).decode().strip()
        rows.append({"copy": f"inputs/k10/{rel}", "source_path": f"{SRC}/{rel}", "source_blob": src_blob,
                     "copy_blob": copy_blob, "bytes_identical": src_blob == copy_blob,
                     "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    assert all(r["bytes_identical"] for r in rows)
    manifest = {"note": "Byte-exact copies (git cat-file blob) of K10 inputs used by the K07 round-3 prototype. Do not edit; regenerate with scripts/copy_inputs.py.",
                "source_branch": K10_BRANCH, "source_sha": K10_SHA,
                "source_listed_in": "origin/codex/research-import-2026-10-05:research/round-3/snapshots.json (commit 6602bb86f152d24edcb66f8b45122844323116bc)",
                "copy_command": "python3 research/round-3-results/K07/scripts/copy_inputs.py",
                "files": sorted(rows, key=lambda r: r["copy"])}
    (K07 / "inputs/MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(rows), "files copied; all byte-identical")


if __name__ == "__main__":
    main()
