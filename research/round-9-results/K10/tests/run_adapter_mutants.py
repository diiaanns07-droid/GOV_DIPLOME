"""K10 round 9: are the resilience packs strict enough to catch rule errors in a JavaScript implementation?
Each mutant changes one rule in a temporary copy of proposals/resilience.js; tests/run_res_adapter.cjs must then fail.

    python3 tests/run_adapter_mutants.py --app-root <BUILD prototypes/city-evidence> [--json out.json]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = [
    ("robust: best case instead of worst", "for (const l of losses) if (cmpLex(l, w) > 0) w = l;\n        const nk",
     "for (const l of losses) if (cmpLex(l, w) < 0) w = l;\n        const nk"),
    ("robust: cost before base loss", "rk = [...w, ...losses[0], cost]", "rk = [...w, cost, ...losses[0]]"),
    ("nominal: uses the worst case", "const nk = [...losses[0], cost]", "const nk = [...w, cost]"),
    ("worst ids: only the first", "ids: ids.filter((_, k) => cmpLex(losses[k], w) === 0).sort(cmpStr) }",
     "ids: ids.filter((_, k) => cmpLex(losses[k], w) === 0).sort(cmpStr).slice(0, 1) }"),
    ("price sign reversed", "price_of_robustness_m: a === null || b === null ? null : (a - b) / 1000",
     "price_of_robustness_m: a === null || b === null ? null : (b - a) / 1000"),
    ("exclusions ignored", "places: ctx.places.filter((p) => !off.has(p.id))", "places: ctx.places"),
    ("unknown max counted as 0", "m.max_mm === null ? Infinity : m.max_mm", "m.max_mm === null ? 0 : m.max_mm"),
    ("unknown not first in search", "return [unknown, wsum, unknown ? Infinity : max];", "return [0, wsum, unknown ? Infinity : max];"),
    ("label limit 121", "label: 120", "label: 121"),
    ("candidate limit 16", "candidates: 12,", "candidates: 16,"),
    ("base id not reserved", 'if (c.id === "base")', 'if (c.id === "base!")'),
    ("derived accepted", 'Object.prototype.hasOwnProperty.call(plan, "derived_results"))', 'false)'),
    ("candidate id accepted as source", "for (const x of ds) if (!sources.has(x))", "for (const x of ds) if (!sources.has(x) && !candIds.has(x))"),
    ("NFC not required", 'v.normalize("NFC") === v', "true"),
    ("cancel reported optimal", 'status: cancelled ? "cancelled" : "incomplete"', 'status: "optimal"'),
    ("budget check strict", "if (cnt > slots || cost > sc.budget) continue;", "if (cnt > slots || cost >= sc.budget) continue;"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    src = (ROOT / "proposals/resilience.js").read_text(encoding="utf-8")
    packs = sorted(str(p) for p in (ROOT / "envelopes").glob("*.json") if p.name != "INDEX.json")
    runner = [os.environ.get("NODE", "node"), str(ROOT / "tests/run_res_adapter.cjs"), a.app_root, *packs]
    base = subprocess.run(runner, capture_output=True, text=True)
    res = []
    for name, old, new in MUTANTS:
        if src.count(old) != 1:
            res.append({"mutant": name, "result": "not_applicable"})
            continue
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "resilience.js"
            f.write_text(src.replace(old, new), encoding="utf-8")
            r = subprocess.run(runner, capture_output=True, text=True, env={**os.environ, "K10_RES_JS": str(f)})
        res.append({"mutant": name, "result": "killed" if r.returncode != 0 else "survived"})
    out = {"unmutated_exit": base.returncode, "mutants": len(res), "killed": sum(x["result"] == "killed" for x in res),
           "survived": [x["mutant"] for x in res if x["result"] == "survived"],
           "not_applicable": [x["mutant"] for x in res if x["result"] == "not_applicable"], "results": res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    sys.exit(1 if base.returncode or out["survived"] or out["not_applicable"] else 0)


if __name__ == "__main__":
    main()
