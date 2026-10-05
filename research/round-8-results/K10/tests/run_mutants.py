"""K10 round 8: do the oracle unit tests notice wrong rules? Each mutant changes one rule in a temporary copy of
k10plan/oracle.py and runs tests/test_oracle.py; a surviving mutant means the tests miss that rule.

    python3 tests/run_mutants.py [--json out.json]

Not listed: removing the [0, 1] clamp. It is an equivalent mutant here: a search over latitudes -89..89 and
longitude gaps 179.5..180 found no input where sqrt(a) exceeds 1 (a = 1.0000000000000002 still gives sqrt 1.0).
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
    ("tie: hypothetical before source", 'key = (m.cand[i][j], 1, m.cands[j]["id"])', 'key = (m.cand[i][j], -1, m.cands[j]["id"])'),
    ("mean: sum before unknown_count", '"mean": (met["unknown_count"], met["weighted_sum_mm"]', '"mean": (met["weighted_sum_mm"], met["unknown_count"]'),
    ("minimax: sum before max", '"minimax": (met["unknown_count"], mx, met["weighted_sum_mm"]', '"minimax": (met["unknown_count"], met["weighted_sum_mm"], mx'),
    ("coverage: ignore covered weight", '"coverage": (-met["covered_weight"],', '"coverage": (0,'),
    ("pareto: keep equal sums", 'if best_wsum is None or p["weighted_sum_mm"] < best_wsum:', 'if best_wsum is None or p["weighted_sum_mm"] <= best_wsum:'),
    ("pareto: include unknown plans", 'full = [p for p in plans if p["unknown_count"] == 0]', 'full = list(plans)'),
    ("radius boundary exclusive", 'if a[0] <= rad:', 'if a[0] < rad:'),
    ("mm rounding banker's", 'return int(math.floor(d_m * 1000 + 0.5))', 'return int(round(d_m * 1000))'),
    ("sensitivity duplicates", 'for b in sorted({0, sc["budget"] // 2, sc["budget"]}):', 'for b in [0, sc["budget"] // 2, sc["budget"]]:'),
    ("budget check strict", 'if sum(m.cands[j]["cost"] for j in sel) > sc["budget"]:', 'if sum(m.cands[j]["cost"] for j in sel) >= sc["budget"]:'),
    ("overlap allowed", 'if set(req) & set(exc):', 'if False:'),
    ("derived_results refused", 'OPTIONAL_TOP = {"derived_results"}', 'OPTIONAL_TOP = set()'),
    ("weighted mean with unknown", '"weighted_mean_mm": (wsum / m.total_weight) if unknown == 0 else None',
     '"weighted_mean_mm": (wsum / m.total_weight)'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    src = (ROOT / "k10plan/oracle.py").read_text(encoding="utf-8")
    res = []
    for name, old, new in MUTANTS:
        assert src.count(old) == 1, name
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(ROOT / "k10plan", Path(d) / "k10plan", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(ROOT / "tests", Path(d) / "tests", ignore=shutil.ignore_patterns("__pycache__"))
            (Path(d) / "k10plan/oracle.py").write_text(src.replace(old, new), encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_oracle.py"],
                               cwd=d, capture_output=True, text=True)
        res.append({"mutant": name, "killed": r.returncode != 0})
    out = {"mutants": len(res), "killed": sum(x["killed"] for x in res), "survived": [x["mutant"] for x in res if not x["killed"]],
           "results": res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    sys.exit(1 if out["survived"] else 0)


if __name__ == "__main__":
    main()
