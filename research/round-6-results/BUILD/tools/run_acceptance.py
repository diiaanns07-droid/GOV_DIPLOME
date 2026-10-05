"""Run the round-5 independent REVIEW tests against one exact BUILD commit (extracted with git archive).

    python tools/run_acceptance.py <SHA> [--venv-python PY] [--out results/<label>]

Each test runs as its own process against an extracted copy of prototypes/city-evidence at <SHA>
(byte-exact from git, nothing from the working tree). Raw stdout/stderr and the test's own JSON report are kept.
No expected-failure files of the old baseline 0bf27de are passed to any test; interpretation is in ACCEPTANCE.json.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]          # research/round-6-results/BUILD
ROOT = HERE.parents[2]
RI = HERE / "review_inputs"


def extract(sha, dest):
    data = subprocess.check_output(["git", "archive", "--format=tar", sha, "prototypes/city-evidence"], cwd=ROOT)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=data, check=True)
    return dest / "prototypes" / "city-evidence"


def main():
    sha = sys.argv[1]
    py = sys.argv[sys.argv.index("--venv-python") + 1] if "--venv-python" in sys.argv else sys.executable
    full = subprocess.check_output(["git", "rev-parse", sha], cwd=ROOT, text=True).strip()
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else HERE / "results" / full[:7]
    out.mkdir(parents=True, exist_ok=True)
    node = shutil.which("node")
    env = dict(os.environ, NODE_PATH=subprocess.check_output(["npm", "root", "-g"], text=True).strip(), PYTHONIOENCODING="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="acc-"))
    try:
        app = extract(full, tmp)
        R = lambda p: str(RI / p)  # noqa: E731
        J = lambda n: str(out / f"{n}.json")  # noqa: E731
        tests = [
            ("K03_boundaries", [py, R("K03/test_boundaries_demo.py"), "--app-root", str(app), "--json", J("K03_boundaries")]),
            # TEST_INCOMPATIBLE adapter: the build's contract in use is inputs/contract/research (v1.2 + K12 patch);
            # inputs/k05_root is the immutable original v1.1 copy kept for provenance and is not used by the build.
            ("K05_compat", [py, R("K05/k05r5_compat.py"), "--app-root", str(app),
                            "--contract-root", str(app / "inputs/contract/research"),
                            "--k05r4", str(app / "inputs/contract/research/round-4-results/K05/k05r4_contract.py"),
                            "--json", J("K05_compat")]),
            ("K12_negative", [py, R("K12/k12r5_negative_build.py"), "--app-root", str(app), "--python", py, "--out", J("K12_negative")]),
            ("K11_smoke", [py, R("K11/k11_demo_smoke.py"), "--app-root", str(app), "--python", sys.executable, "--browser", "--label", full, "--out", J("K11_smoke")]),
            ("K08_attribution", [py, R("K08/check_demo_attribution.py"), "--app-root", str(app), "--repo", str(ROOT), "--json", J("K08_attribution")]),
            ("K01_check_build", [py, R("K01/check_build.py"), "--app-root", str(app), "--browser", "--json", J("K01_check_build")]),
            ("K06_audit_numbers", [py, R("K06/audit_numbers.py"), "--app-root", str(app), "--json", J("K06_audit_numbers")]),
            ("K10_run_qa", [py, R("K10/tests/run_qa.py"), "--app-root", str(app), "--json", J("K10_run_qa")]),
        ]
        if node:
            tests += [
                ("K02_facts_regression", [node, R("K02/tests/facts_regression.cjs"), "--app-root", str(app)]),
                ("K07_regressions", [node, R("K07/tests/k07r5_regressions.cjs"), "--app-root", str(app), "--sha", full, "--out", str(out / "K07")]),
                ("K10_ui_coord_group", [node, R("K10/tests/ui_coord_group.cjs"), "--app-root", str(app), "--json", J("K10_ui_coord_group")]),
            ]
        tests.append(("BUILD_check_all", [py, str(app / "tools/check_all.py"), "--log", J("BUILD_check_all")]))
        summary = []
        for name, cmd in tests:
            t0 = time.time()
            r = subprocess.run(cmd, cwd=str(app) if name == "BUILD_check_all" else str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env, timeout=1800)
            (out / f"{name}.txt").write_text(f"$ {' '.join(cmd)}\nexit={r.returncode}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}",
                                             encoding="utf-8", newline="\n")
            summary.append({"test": name, "exit": r.returncode, "seconds": round(time.time() - t0, 1)})
            print(f"{name}: exit {r.returncode} ({summary[-1]['seconds']} s)", flush=True)
        (out / "RUN.json").write_text(json.dumps({"target_sha": full, "python": py, "node": node, "tests": summary},
                                                 indent=1) + "\n", encoding="utf-8", newline="\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
