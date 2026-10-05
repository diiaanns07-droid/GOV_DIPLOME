"""K10 round 8: are the packs strict enough to catch wrong rules in the BUILD's web/plan.js?
Each mutant changes one rule in a temporary copy of the app root; tests/run_build_v2.cjs must then fail.

    python3 tests/run_build_mutants.py --app-root <BUILD prototypes/city-evidence> [--json out.json]

The mutant texts match web/plan.js of BUILD 60f44d9; on another version a text may be absent -> "not_applicable".
Not listed: swapping -covered and unknown in the coverage key. In this contract it is equivalent: unknown_count > 0
happens only for the empty plan over an empty baseline, whose covered weight is 0.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = [
    ("mm rounding floor", "const mmOf = (m) => Math.round(m * 1000);", "const mmOf = (m) => Math.floor(m * 1000);"),
    ("tie: hypothetical may beat source", '(d.mm === best.mm && best.kind === "hypothetical" && c.id < best.id)', "(d.mm === best.mm && c.id < best.id)"),
    ("radius boundary exclusive", "if (a <= radiusMm) covered += weights[j]; }", "if (a < radiusMm) covered += weights[j]; }"),
    ("pareto keeps equal sums", "if (w < bestW)", "if (w <= bestW)"),
    ("mean: cost before max", "mean: (e) => [e.unknown, e.wsum, e.max, e.cost]", "mean: (e) => [e.unknown, e.wsum, e.cost, e.max]"),
    ("minimax: cost before sum", "minimax: (e) => [e.unknown, e.max, e.wsum, e.cost]", "minimax: (e) => [e.unknown, e.max, e.cost, e.wsum]"),
    ("coverage: cost before sum", "coverage: (e) => [-e.covered, e.unknown, e.wsum, e.max, e.cost]",
     "coverage: (e) => [-e.covered, e.unknown, e.cost, e.wsum, e.max]"),
    ("budget check strict", "if (cost > sc.budget) return null;", "if (cost >= sc.budget) return null;"),
    ("max_selected off by one", "if (popcount(mask) > slots) continue;", "if (popcount(mask) > slots + 1) continue;"),
    ("excluded ignored", "if (!req.includes(i) && !exc.has(i)) free.push(i);", "if (!req.includes(i)) free.push(i);"),
    ("required count check dropped", "if (req.length > sc.max_selected) reasons.push(", "if (false) reasons.push("),
    ("weighted mean over known only", "weighted_mean_mm: unknown === 0 && total > 0 ? wsum / total : null",
     "weighted_mean_mm: total > 0 ? wsum / total : null"),
    ("delta when before unknown", "delta_mm: b && best ? b.mm - best.mm : null", "delta_mm: best ? (b ? b.mm : 0) - best.mm : null"),
    ("sensitivity duplicates kept", "const bs = [...new Set([0, Math.floor(sc.budget / 2), sc.budget])]",
     "const bs = [0, Math.floor(sc.budget / 2), sc.budget]"),
    ("overlap allowed", "if (both.length) fail(", "if (false) fail("),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--packs", default=str(ROOT / "packs"))
    ap.add_argument("--json")
    a = ap.parse_args()
    app = Path(a.app_root)
    src = (app / "web/plan.js").read_text(encoding="utf-8")
    packs = sorted(str(q) for q in Path(a.packs).glob("*.json") if q.name != "INDEX.json")
    runner = str(ROOT / "tests/run_build_v2.cjs")
    base = subprocess.run(["node", runner, str(app), *packs], capture_output=True, text=True)
    res = []
    for name, old, new in MUTANTS:
        if src.count(old) != 1:
            res.append({"mutant": name, "result": "not_applicable"})
            continue
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "app"
            shutil.copytree(app, copy)
            (copy / "web/plan.js").write_text(src.replace(old, new), encoding="utf-8")
            r = subprocess.run(["node", runner, str(copy), *packs], capture_output=True, text=True)
        res.append({"mutant": name, "result": "killed" if r.returncode != 0 else "survived"})
    out = {"app_root": str(app), "unmutated_exit": base.returncode, "mutants": len(res),
           "killed": sum(x["result"] == "killed" for x in res), "survived": [x["mutant"] for x in res if x["result"] == "survived"],
           "not_applicable": [x["mutant"] for x in res if x["result"] == "not_applicable"], "results": res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    sys.exit(1 if base.returncode != 0 or out["survived"] else 0)


if __name__ == "__main__":
    main()
