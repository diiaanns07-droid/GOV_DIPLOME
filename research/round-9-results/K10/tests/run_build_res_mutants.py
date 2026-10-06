"""K10 round 9: are the K10 resilience packs strict enough to catch rule errors in the BUILD's web/resilience.js?
Each mutant changes one rule in a temporary copy of the app root; tests/run_build_resilience.cjs must then fail.

    python3 tests/run_build_res_mutants.py --app-root <BUILD prototypes/city-evidence> [--json out.json]

Mutant texts match web/resilience.js of BUILD 33cc635; on another version a text may be absent -> "not_applicable".
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = [  # (name, [(old, new), ...]) - every old text must occur exactly once
    ("robust: best case instead of worst", [("for (let c = 1; c < nCase; c++) if (lexCmp(L[c], W) > 0) W = L[c];",
                                             "for (let c = 1; c < nCase; c++) if (lexCmp(L[c], W) < 0) W = L[c];")]),
    ("robust: cost before base loss", [("const kR = [...W, ...L[0], cost]", "const kR = [...W, cost, ...L[0]]")]),
    ("nominal: uses the worst case", [("kN = [...L[0], cost]", "kN = [...W, cost]")]),
    ("worst ids: only the first", [(".map((r) => r.case_id).sort(cmpStr) };", ".map((r) => r.case_id).sort(cmpStr).slice(0, 1) };")]),
    ("price sign reversed", [("? (a - b) / 1000 : null", "? (b - a) / 1000 : null")]),
    ("exclusions ignored", [("return { ...ctx, places: ctx.places.filter((p) => !off.has(p.id)) };", "return { ...ctx, places: ctx.places };")]),
    ("unknown max counted as 0", [("m.max_mm === null ? Infinity : m.max_mm", "m.max_mm === null ? 0 : m.max_mm")]),
    ("unknown not first in search", [("return [u, s, u ? Infinity : mx];", "return [0, s, u ? Infinity : mx];")]),
    ("label limit 121", [("label: 120 }", "label: 121 }")]),
    ("candidate limit 16", [("candidates: 12,", "candidates: 16,")]),
    ("8 user cases allowed", [("user_cases: 7,", "user_cases: 8,")]),
    ("base id not reserved", [('if (c.id === "base")', 'if (c.id === "base!")')]),
    ("derived results accepted", [('if ("derived_results" in plan) fail(', "if (false) fail(")]),
    ("candidate id accepted as source", [("if (candIds.has(id) && !srcIds.has(id)) fail(", "if (false) fail("),
                                         ('if (!srcIds.has(id)) fail("unknown_source"', 'if (!srcIds.has(id) && !candIds.has(id)) fail("unknown_source"')]),
    ("case id rule dropped", [('if (!PL.isId(c.id)) fail("bad_id"', 'if (typeof c.id !== "string") fail("bad_id"')]),
    ("duplicate case ids allowed", [('if (seen.has(c.id)) fail("duplicate_id"', 'if (false) fail("duplicate_id"')]),
    ("cancel reported optimal", [('status: cancelled ? "cancelled" : "incomplete"', 'status: "optimal"')]),
    ("budget check strict", [("if (cost > sc.budget) continue;", "if (cost >= sc.budget) continue;")]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    app = Path(a.app_root)
    src = (app / "web/resilience.js").read_text(encoding="utf-8")
    packs = sorted(str(p) for p in (ROOT / "envelopes").glob("*.json") if p.name != "INDEX.json")
    runner = str(ROOT / "tests/run_build_resilience.cjs")
    base = subprocess.run(["node", runner, str(app), *packs], capture_output=True, text=True)
    res = []
    for name, pairs in MUTANTS:
        if any(src.count(old) != 1 for old, _ in pairs):
            res.append({"mutant": name, "result": "not_applicable"})
            continue
        text = src
        for old, new in pairs:
            text = text.replace(old, new)
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "app"
            shutil.copytree(app, copy)
            (copy / "web/resilience.js").write_text(text, encoding="utf-8")
            r = subprocess.run(["node", runner, str(copy), *packs], capture_output=True, text=True)
        res.append({"mutant": name, "result": "killed" if r.returncode != 0 else "survived"})
    out = {"app_root": str(app), "unmutated_exit": base.returncode, "mutants": len(res),
           "killed": sum(x["result"] == "killed" for x in res), "survived": [x["mutant"] for x in res if x["result"] == "survived"],
           "not_applicable": [x["mutant"] for x in res if x["result"] == "not_applicable"], "results": res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    sys.exit(1 if base.returncode or out["survived"] else 0)


if __name__ == "__main__":
    main()
