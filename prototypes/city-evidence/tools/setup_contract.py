"""Assemble the contract used by the demo: k05-obs-v1.2 (K05 r4) on top of k05r3_contract + K12 stress-fix patch.

Originals stay byte-exact where they were copied (inputs/k05_root, inputs/r4/K05, inputs/r4/K12).
This script builds a separate patched tree inputs/contract/ with the same relative layout the K05 modules
expect (research/next-round/K05, research/round-3-results/K05, research/round-4-results/K05) and writes
inputs/contract/CONTRACT_MANIFEST.json with original and patched sha256. The patched copy is NOT upstream.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
OUT = APP / "inputs" / "contract"
SRC = {
    "research/next-round/K05/k05_validator.py": APP / "inputs/k05_root/next-round/K05/k05_validator.py",
    "research/round-3-results/K05/k05r3_contract.py": APP / "inputs/k05_root/round-3-results/K05/k05r3_contract.py",
    "research/round-4-results/K05/k05r4_contract.py": APP / "inputs/r4/K05/k05r4_contract.py",
    "research/round-4-results/K05/schema/k05-obs-v1.2.schema.json": APP / "inputs/r4/K05/schema/k05-obs-v1.2.schema.json",
}
# Applied in this order (K05 r5 REPORT §3): K12 stress fixes, then COUNT_DOMAIN for records/segments (needs K12),
# then the v1.2 compatibility fix (BOUNDARY_MIX for bbox squares, expected_units pass-through).
PATCHES = [
    (APP / "inputs/r4/K12/patches/k05r3_contract_stress_fixes.patch", "K12 @ 3e84039"),
    (APP / "inputs/r5/K05/patches/k05r3_count_units_after_k12.patch", "K05 @ fb2dea6"),
    (APP / "inputs/r5/K05/patches/k05r4_contract_k12_compat.patch", "K05 @ fb2dea6"),
]
CONTRACT_ID = "k05-obs-v1.2+k12r4+k05r5"


def h(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    rows = []
    for rel, src in SRC.items():
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        rows.append({"path": rel, "from": str(src.relative_to(APP)), "original_sha256": h(src)})
    for patch, _ in PATCHES:
        subprocess.check_call(["patch", "-p1", "--quiet", "--no-backup-if-mismatch", "-d", str(OUT), "-i", str(patch)])
    for r in rows:
        r["used_sha256"] = h(OUT / r["path"])
        r["modified"] = r["used_sha256"] != r["original_sha256"]
    (OUT / "CONTRACT_MANIFEST.json").write_text(json.dumps({
        "contract_id": CONTRACT_ID,
        "composition": "K05 r4 k05r4_contract (v1.2 spatial_unit) + K05 r5 compat patch -> k05r3_contract + K12 r4 patch "
                       "+ K05 r5 count-units patch -> k05_validator v1",
        "patches": [{"path": str(p.relative_to(APP)), "sha256": h(p), "source": src} for p, src in PATCHES],
        "files": rows,
        "note": "modified=true files are local patched copies, not upstream files",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{CONTRACT_ID}: {sum(r['modified'] for r in rows)} file(s) patched")


if __name__ == "__main__":
    main()
