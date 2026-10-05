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
K03_SHA = "44585de31be01dd131ecb7677c462fc85b4d4cc4"
# K03 code resolves paths relative to the repository root (geo_common.ROOT = HERE.parents[2]);
# mirror the needed files under inputs/k03_root/ with the same relative layout so it runs unmodified.
EXTRA = {
    "k03_root": ("claude/epic-curie-iitc43", K03_SHA, "", [
        "data/astana_districts.geojson",
        "data/geo_sources/astana_districts_overpass.json",
        "data/geo_sources/sara_osm.json",
        "research/round-3-results/K03/geo_common.py",
        "research/round-3-results/K03/boundary_validator.py",
        "research/round-3-results/K03/boundary_registry.json",
        "research/round-3-results/K03/ambiguity_zones.geojson",
        "research/round-3-results/K03/validator_selftest.json",
        "research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson",
        "research/round-3-results/K03/inputs/K10/shymkent_districts_overture.geojson",
        "research/round-3-results/K03/STATUS.md",
    ]),
    "k02": ("claude/clever-mccarthy-pywscu", "24c1750f70d9e444ae551030d116bb6aa8ce5b7b", "research/round-3-results/K02/", [
        "verified_explainer.py", "demo.py", "test_verified_explainer.py", "STATUS.md",
    ]),
    "k05_root": ("claude/optimistic-davinci-1oiqs9", "d913554bf2617a74d921af260ab8c22743ccb4b5", "research/", [
        "round-3-results/K05/schema/k05-obs-v1.1.schema.json", "round-3-results/K05/k05r3_contract.py",
        "round-3-results/K05/REPORT.md", "round-3-results/K05/STATUS.md",
        "next-round/K05/k05_validator.py", "next-round/K05/observation.schema.json",
    ]),
    "k08": ("claude/dazzling-mayer-drhsxk", "e1e3c7170f827550948afc0448695ecb8e9bc464", "research/round-3-results/K08/", [
        "AUDIT.md", "verdicts.json",
    ]),
    "k04": ("claude/beautiful-clarke-sbzomj", "7fb8bb897dc80150c85fef9e68ac7183d323e6c3", "research/round-3-results/K04/", [
        "acceptance.json", "PRODUCT_DECISION.md",
    ]),
}


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
                    "files": manifest}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"copied {len(manifest)} files")


if __name__ == "__main__":
    main()
