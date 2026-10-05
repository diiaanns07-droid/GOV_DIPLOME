#!/usr/bin/env python3
"""K07 round 8: write a unified diff BASE web/ -> PATCHED web/ with -p1 paths a/prototypes/city-evidence/web/...
Default (proposal for a5b5e2d): patch/city_evidence_planner.patch — app.js, index.html and the four new modules, which
must be byte-identical to research/round-8-results/K07/web/ (the source of truth). Usage (repo root):
    python3 research/round-8-results/K07/scripts/make_patch.py BASE_DIR PATCHED_DIR
Fixes for an existing BUILD (no new files, BUILD modules are edited line by line, never replaced):
    python3 research/round-8-results/K07/scripts/make_patch.py BASE_DIR PATCHED_DIR --files web/app.js web/plan-ui.js web/index.html --out patch/NAME.patch
BASE_DIR / PATCHED_DIR contain web/ (BASE_DIR from scripts/extract_build.py).
"""
import subprocess, sys
from pathlib import Path

K07 = Path(__file__).resolve().parents[1]
CHANGED = ["web/app.js", "web/index.html"]
NEW = ["web/plan_calc.js", "web/plan_runner.js", "web/plan_demo.js", "web/planner_ui.js"]


def diff(a, b, rel, new):
    r = subprocess.run(["git", "diff", "--no-index", "--no-color", "--", "/dev/null" if new else str(a), str(b)], capture_output=True)
    if r.returncode != 1:
        raise SystemExit(f"no diff or error for {rel}: {r.returncode} {r.stderr.decode()[:200]}")
    lines, rp = r.stdout.decode().split("\n"), f"prototypes/city-evidence/{rel}"
    head = True
    for i, l in enumerate(lines):
        if l.startswith("diff --git "):
            lines[i], head = f"diff --git a/{rp} b/{rp}", True
        elif head and l.startswith("--- ") and not new:
            lines[i] = f"--- a/{rp}"
        elif head and l.startswith("+++ "):
            lines[i], head = f"+++ b/{rp}", False
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("patched")
    ap.add_argument("--files", nargs="+"); ap.add_argument("--out")
    a = ap.parse_args()
    base, pat = Path(a.base), Path(a.patched)
    if a.files:  # edits of existing files only
        out = "".join(diff(base / f, pat / f, f, False) for f in a.files)
        dst = K07 / a.out
    else:
        for f in NEW:
            if (pat / f).read_bytes() != (K07 / f).read_bytes():
                raise SystemExit(f"{f}: patched copy differs from research/round-8-results/K07/{f}")
        out = "".join(diff(base / f, pat / f, f, False) for f in CHANGED) + "".join(diff(None, pat / f, f, True) for f in NEW)
        dst = K07 / "patch" / "city_evidence_planner.patch"
    assert "/tmp/" not in out and "scratchpad" not in out
    dst.parent.mkdir(exist_ok=True)
    dst.write_text(out, encoding="utf-8")
    print(f"wrote {dst.relative_to(K07.parents[2])}: {out.count(chr(10))} lines")


if __name__ == "__main__":
    main()
