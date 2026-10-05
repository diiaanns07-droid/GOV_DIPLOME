"""K11 round 7: one reproducible launch smoke for the "if an object is added" scenario.

    python research/round-7-results/K11/run_k11r7.py --app-root <copy>/prototypes/city-evidence --label <SHA> [--browser] [--out report.json]

Steps (each reported separately; a step that cannot run is not_run, never pass):
  1. launcher smoke  research/round-5-results/K11/k11_demo_smoke.py --app-root ... (starts and stops its own serve.py)
  2. launch extras   research/round-6-results/K11/k11r6_launch_extra.py (run-demo.bat arguments, busy port, missing files)
  3. scenario files  test_whatif_io.py with K11_APP_ROOT=<app-root> (Cyrillic/Kazakh names and ids, reopen from
                     another directory, strict import; fixtures are pinned to MANIFEST app_sha)
  4. feature in app  is city-whatif-v1 present in web/? absent -> integration checks not_run
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parents[1]
SMOKE = RESEARCH / "round-5-results" / "K11" / "k11_demo_smoke.py"
EXTRA = RESEARCH / "round-6-results" / "K11" / "k11r6_launch_extra.py"


def run(cmd, env=None, timeout=900):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, **(env or {})), timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    root = str(Path(a.app_root).resolve())
    steps = []

    if SMOKE.is_file():
        cmd = [sys.executable, str(SMOKE), "--app-root", root] + (["--browser"] if a.browser else [])
        rc, out, err = run(cmd)
        summary = next((json.loads(l.split(":", 1)[1]) for l in out.splitlines() if l.startswith("summary:")), None)
        steps.append({"step": "launcher_smoke", "status": "pass" if rc == 0 else "fail", "exit": rc,
                      "summary": summary, "failing": [l for l in out.splitlines() if l.startswith(("fail", "modeled_fail"))]})
    else:
        steps.append({"step": "launcher_smoke", "status": "not_run", "reason": f"{SMOKE} missing"})

    if EXTRA.is_file():
        rc, out, err = run([sys.executable, str(EXTRA), "--app-root", root])
        steps.append({"step": "launch_extra", "status": "pass" if rc == 0 else "fail", "exit": rc,
                      "lines": out.strip().splitlines()})
    else:
        steps.append({"step": "launch_extra", "status": "not_run", "reason": f"{EXTRA} missing"})

    # run the file itself (unittest.main): `-m unittest <abs path>` breaks when cwd is another directory
    rc, out, err = run([sys.executable, str(HERE / "test_whatif_io.py")], env={"K11_APP_ROOT": root})
    tail = [l for l in err.splitlines() if l.startswith(("Ran ", "OK", "FAILED"))]
    stale = "regenerate fixtures for this SHA" in err
    steps.append({"step": "scenario_files", "status": "pass" if rc == 0 else ("fixtures_stale" if stale else "fail"),
                  "exit": rc, "result": tail,
                  "note": "fixtures_stale = this app's data.js differs from MANIFEST app_sha; rerun make_fixtures.py for it"
                  if stale else ""})

    web = Path(root) / "web"
    hits = sorted(p.name for p in web.glob("*") if p.suffix in (".js", ".html")
                  and re.search(r"city-whatif-v1", p.read_text(encoding="utf-8", errors="replace")))
    steps.append({"step": "feature_in_app", "status": "present" if hits else "not_present", "files": hits,
                  "integration_checks": "not_run (no browser-level scenario checks exist yet; see RUNBOOK manual steps)"
                  if hits else "not_run (feature absent in this copy)"})

    report = {"tool": "research/round-7-results/K11/run_k11r7.py", "label": a.label, "app_root": "<given>",
              "host": {"os": platform.system(), "python": platform.python_version()}, "steps": steps}
    if a.out:
        Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    for s in steps:
        print(f"{s['status']:12} {s['step']}")
    bad = [s for s in steps if s["status"] in ("fail", "fixtures_stale")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
