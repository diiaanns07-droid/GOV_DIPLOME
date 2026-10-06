#!/usr/bin/env python3
"""K07 round 9: unified diff BASE -> PATCHED with -p1 paths a/prototypes/city-evidence/web/... (BUILD files are edited
line by line, never replaced; new files must be byte-identical to research/round-9-results/K07/web/).
Usage (repo root):
    python3 research/round-9-results/K07/scripts/make_patch.py BASE PATCHED --files web/index.html --new web/resilience_k07.js web/resilience_panel_k07.js --out patch/NAME.patch
BASE / PATCHED contain web/ (e.g. BASE = d865dd4 + earlier K07 patches, PATCHED = the tested copy).
"""
import argparse, subprocess
from pathlib import Path

K07 = Path(__file__).resolve().parents[1]


def diff(a, b, rel, new):
    r = subprocess.run(["git", "diff", "--no-index", "--no-color", "--", "/dev/null" if new else str(a), str(b)], capture_output=True)
    if r.returncode != 1:
        raise SystemExit(f"no diff or error for {rel}: {r.returncode} {r.stderr.decode()[:200]}")
    lines, rp, head = r.stdout.decode().split("\n"), f"prototypes/city-evidence/{rel}", True
    for i, l in enumerate(lines):
        if l.startswith("diff --git "):
            lines[i], head = f"diff --git a/{rp} b/{rp}", True
        elif head and l.startswith("--- ") and not new:
            lines[i] = f"--- a/{rp}"
        elif head and l.startswith("+++ "):
            lines[i], head = f"+++ b/{rp}", False
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("patched")
    ap.add_argument("--files", nargs="*", default=[]); ap.add_argument("--new", nargs="*", default=[]); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    base, pat = Path(a.base), Path(a.patched)
    for f in a.new:
        if (pat / f).read_bytes() != (K07 / f).read_bytes():
            raise SystemExit(f"{f}: patched copy differs from research/round-9-results/K07/{f}")
    out = "".join(diff(base / f, pat / f, f, False) for f in a.files) + "".join(diff(None, pat / f, f, True) for f in a.new)
    assert "/tmp/" not in out and "scratchpad" not in out
    dst = K07 / a.out
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(out, encoding="utf-8")
    print(f"wrote {dst.relative_to(K07.parents[2])}: {out.count(chr(10))} lines")


if __name__ == "__main__":
    main()
