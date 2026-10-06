"""K10 round 9: do tests/test_res_oracle.py notice wrong resilience rules? Each mutant changes one rule in a temporary
copy of k10res/oracle_res.py; a surviving mutant means the unit tests miss that rule.

    python3 tests/run_res_mutants.py [--json out.json]        # from research/round-9-results/K10
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
    ("robust: best case instead of worst", "rob_key = (max(losses), losses[0], cost, ids)", "rob_key = (min(losses), losses[0], cost, ids)"),
    ("robust: cost before base loss", "rob_key = (max(losses), losses[0], cost, ids)", "rob_key = (max(losses), cost, losses[0], ids)"),
    ("nominal: uses the worst case", "nom_key = (losses[0], cost, ids)", "nom_key = (max(losses), cost, ids)"),
    ("worst ids: only the first", "return w, sorted(cid for cid, lv in zip(case_ids, per_case_losses) if lv == w)",
     "return w, sorted(cid for cid, lv in zip(case_ids, per_case_losses) if lv == w)[:1]"),
    ("price sign reversed", "out.update(price_of_robustness_m=(a - b) / 1000, price_reason=None)",
     "out.update(price_of_robustness_m=(b - a) / 1000, price_reason=None)"),
    ("exclusions ignored", 'self.base.append([min((k for k in row if k[2] not in off), default=None) for row in src])',
     'self.base.append([min((k for k in row), default=None) for row in src])'),
    ("unknown max counted as 0", 'return (met["unknown_count"], met["weighted_sum_mm"], INF if met["max_mm"] is None else met["max_mm"])',
     'return (met["unknown_count"], met["weighted_sum_mm"], 0 if met["max_mm"] is None else met["max_mm"])'),
    ("unknown not compared first", 'return (met["unknown_count"], met["weighted_sum_mm"], INF if met["max_mm"] is None else met["max_mm"])',
     'return (met["weighted_sum_mm"], met["unknown_count"], INF if met["max_mm"] is None else met["max_mm"])'),
    ("label limit off by one", "LABEL_MAX = 120", "LABEL_MAX = 121"),
    ("candidate limit 16", "MAX_CANDIDATES = 12", "MAX_CANDIDATES = 16"),
    ("8 user cases allowed", "MAX_USER_CASES = 7", "MAX_USER_CASES = 8"),
    ("base id not reserved", 'if c["id"] == "base":', 'if c["id"] == "base!":'),
    ("derived results accepted", 'if isinstance(plan, dict) and "derived_results" in plan:', 'if False:'),
    ("candidate id accepted as source", "if x not in sources:", "if x not in sources | cand_ids:"),
    ("labels not in digest", 'sorted([c["id"], c["label"], sorted(c["disabled_source_ids"])] for c in env["cases"])',
     'sorted([c["id"], sorted(c["disabled_source_ids"])] for c in env["cases"])'),
    ("selected ids in problem digest", 'return "sha256:" + hashlib.sha256(_canon(_payload(env)).encode("utf-8")).hexdigest()',
     'return resilience_scenario_digest(env)'),
    ("NFC not required", 'unicodedata.normalize("NFC", v) == v', 'True'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    src = (ROOT / "k10res/oracle_res.py").read_text(encoding="utf-8")
    res = []
    for name, old, new in MUTANTS:
        if src.count(old) != 1:
            res.append({"mutant": name, "result": "not_applicable"})
            continue
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(ROOT / "k10res", Path(d) / "k10res", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(ROOT / "tests", Path(d) / "tests", ignore=shutil.ignore_patterns("__pycache__"))
            (Path(d) / "k10res/oracle_res.py").write_text(src.replace(old, new), encoding="utf-8")
            # oracle_res finds the r8 oracle relative to its own location; point it back to the repository
            p = Path(d) / "k10res/oracle_res.py"
            p.write_text(p.read_text(encoding="utf-8").replace(
                'Path(__file__).resolve().parents[3] / "round-8-results/K10"', repr(str(ROOT.parents[1] / "round-8-results/K10"))),
                encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_res_oracle.py"],
                               cwd=d, capture_output=True, text=True)
        res.append({"mutant": name, "result": "killed" if r.returncode != 0 else "survived"})
    out = {"mutants": len(res), "killed": sum(x["result"] == "killed" for x in res),
           "survived": [x["mutant"] for x in res if x["result"] == "survived"],
           "not_applicable": [x["mutant"] for x in res if x["result"] == "not_applicable"], "results": res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    sys.exit(1 if out["survived"] or out["not_applicable"] else 0)


if __name__ == "__main__":
    main()
