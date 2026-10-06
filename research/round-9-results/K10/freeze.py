"""K10 round 9: write the frozen reference values used by regress.py (run once; output committed in frozen/).

Everything is read byte-exact from git objects, never from a BUILD:
  frozen/r8_packs.json  sha256 of every file under research/round-8-results/K10/packs at K10 commit c8df74b
                        (the 37 r8 packs whose expectations were computed by the K10 oracle, not by BUILD)
  frozen/sources.json   sha256 of the K10 package files at K10 commit 602f0c0 (round 3) and, per city, every
                        source record (id, group, lon, lat) of places_social.geojson
    python3 research/round-9-results/K10/freeze.py
"""
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R8_COMMIT = "c8df74b500dd1d1c1ea39496307062e6c2db1ba3"
PKG_COMMIT = "602f0c0"
R8_PACKS = "research/round-8-results/K10/packs/"
PKG = "research/round-3-results/K10/"


def git_bytes(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=REPO)


def main():
    rows = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", R8_COMMIT, R8_PACKS], cwd=REPO).decode().split()
    packs = {p[len(R8_PACKS):]: hashlib.sha256(git_bytes(R8_COMMIT, p)).hexdigest() for p in rows}
    (HERE / "frozen/r8_packs.json").write_text(json.dumps(
        {"commit": R8_COMMIT, "path": R8_PACKS, "files": len(packs), "sha256": packs}, indent=1, sort_keys=True) + "\n")
    pkg_commit = subprocess.check_output(["git", "rev-parse", PKG_COMMIT], cwd=REPO).decode().strip()
    out = {"commit": pkg_commit, "path": PKG, "files": {}, "records": {}}
    for rel in ("package_manifest.json", "data/shymkent/places_social.geojson", "data/astana/places_social.geojson"):
        out["files"][rel] = hashlib.sha256(git_bytes(pkg_commit, PKG + rel)).hexdigest()
    for city in ("shymkent", "astana"):
        g = json.loads(git_bytes(pkg_commit, f"{PKG}data/{city}/places_social.geojson"))
        out["records"][city] = sorted([f["id"], f["properties"]["k10_group"], *f["geometry"]["coordinates"]] for f in g["features"])
    (HERE / "frozen/sources.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({"r8_pack_files": len(packs), "records": {c: len(v) for c, v in out["records"].items()}}))


if __name__ == "__main__":
    main()
