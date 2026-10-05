"""K10 round 8: every K10 check against one extracted BUILD, results in one folder.

    python3 tests/run_build_suite.py --app-root <BUILD prototypes/city-evidence> --commit <BUILD sha> [--out results/<sha7>]

Steps (each PASS/FAIL/SKIP in summary.json):
  check_packs     packs vs this build's data + oracle recomputation + JS geometry + input immutability
  unit_tests      tests/test_oracle.py + tests/test_cli.py with K10_APP_ROOT set
  verify_inputs   data files = INDEX.json = git blobs of --commit = K10 package files
  build_v2        packs through the build's web/plan.js (SKIP if the build has no plan.js)
  build_exports   the build's own exports (exportPlanScenario) accepted by the K10 oracle with the same optimum
  build_mutants   injected rule errors in a copy of web/plan.js are caught by the packs
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]


def sh(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    app = str(Path(a.app_root).resolve())
    out = Path(a.out or ROOT / "results" / a.commit[:7])
    out.mkdir(parents=True, exist_ok=True)
    packs = sorted(str(p) for p in (ROOT / "packs").glob("*.json") if p.name != "INDEX.json")
    s = {"commit": a.commit, "steps": {}}

    r = sh([sys.executable, "tests/check_packs.py", "--app-root", app, "--json", str(out / "check_packs.json")])
    s["steps"]["check_packs"] = "PASS" if r.returncode == 0 else "FAIL"

    r = sh([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"], env={**os.environ, "K10_APP_ROOT": app})
    (out / "unittest.txt").write_text(r.stderr + r.stdout, encoding="utf-8")
    s["steps"]["unit_tests"] = "PASS" if r.returncode == 0 else "FAIL"

    r = sh([sys.executable, "-m", "k10plan.cli", "verify-inputs", "--app-root", app, "--index", "packs/INDEX.json",
            "--git-sha", a.commit, "--k10-package", str(REPO / "research/round-3-results/K10")])
    (out / "verify_inputs.json").write_text(r.stdout, encoding="utf-8")
    s["steps"]["verify_inputs"] = "PASS" if r.returncode == 0 else "FAIL"

    with tempfile.TemporaryDirectory() as d:
        r = sh(["node", "tests/run_build_v2.cjs", app, *packs], env={**os.environ, "K10_EXPORT_DIR": d})
        (out / "build_v2.json").write_text(r.stdout, encoding="utf-8")
        s["steps"]["build_v2"] = {0: "PASS", 3: "SKIP(no web/plan.js)"}.get(r.returncode, "FAIL")
        exports = sorted(glob.glob(os.path.join(d, "*.json")))
        if not exports:
            s["steps"]["build_exports"] = "SKIP(no exportPlanScenario)"
        else:
            bad = []
            for f in exports:
                pid = Path(f).stem
                rr = sh([sys.executable, "-m", "k10plan.cli", "run", f, "--app-root", app, "--format", "json"])
                want = json.loads((ROOT / "packs" / f"{pid}.json").read_text(encoding="utf-8"))["expected"]["optimize"]
                if rr.returncode != 0 or json.loads(rr.stdout)["result"]["optimize"] != want:
                    bad.append(pid)
            s["steps"]["build_exports"] = "PASS" if not bad else "FAIL"
            s["build_exports"] = {"files": len(exports), "differ": bad}

    if s["steps"]["build_v2"].startswith("SKIP"):
        s["steps"]["build_mutants"] = "SKIP(no web/plan.js)"
    else:
        r = sh([sys.executable, "tests/run_build_mutants.py", "--app-root", app, "--json", str(out / "build_mutants.json")])
        m = json.loads((out / "build_mutants.json").read_text(encoding="utf-8"))
        s["steps"]["build_mutants"] = "PASS" if r.returncode == 0 else "FAIL"
        s["build_mutants"] = {k: m[k] for k in ("mutants", "killed", "survived", "not_applicable")}

    scratch = os.path.dirname(app)
    for f in out.glob("*"):  # do not store local absolute paths in results
        f.write_text(f.read_text(encoding="utf-8").replace(scratch, "<app-parent>"), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(s, ensure_ascii=False))
    sys.exit(0 if all(v == "PASS" or v.startswith("SKIP") for v in s["steps"].values()) else 1)


if __name__ == "__main__":
    main()
