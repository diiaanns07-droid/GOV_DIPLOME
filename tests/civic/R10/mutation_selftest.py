"""Mutation self-test of the R10 HTTP acceptance suite against the R10 oracle (stdlib only).

  python3 -I -B tests/civic/R10/mutation_selftest.py \
      [--out research/round-11-results/R10/MUTATION_RESULTS.json] [--jobs 3] [--only a,b]

For every deliberate defect the oracle knows (KNOWN_MUTANTS in r10lib/oracle/server.py)
the suite `python3 -I -B -m unittest discover -s tests/civic/R10 -p 'test_api_*.py'` runs in
its own subprocess with R10_ORACLE_MUTANT=<name>; each subprocess starts its own oracle on a
free port with its own temporary DB. A mutant is KILLED when at least one test that passes
on the clean oracle reports FAIL or ERROR. The clean baseline runs first and must be green.
A mutant run in which the oracle never started is reported as `invalid`, not as killed.

The oracle is test-only reference code; mutants model defects a product could have.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
ORACLE = HERE / "r10lib" / "oracle" / "server.py"
DEFAULT_OUT = REPO_ROOT / "research" / "round-11-results" / "R10" / "MUTATION_RESULTS.json"
PATTERN = "test_api_*.py"
RESULT_LINE = re.compile(r"^(FAIL|ERROR): (\S+) \(([^)\s]+)\)", re.MULTILINE)
RAN_LINE = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)
SUMMARY = re.compile(r"^(OK|FAILED)(?: \(([^)]*)\))?\s*$", re.MULTILINE)
STARTUP_FAILURE = ("server did not become ready", "create-editor failed")

# Survivors judged equivalent or meaningless for a black-box HTTP suite. Each entry says why;
# a listed mutant that is killed in a later run is simply reported as killed.
SURVIVOR_NOTES: dict[str, str] = {}


def known_mutants() -> list[str]:
    text = ORACLE.read_text(encoding="utf-8")
    m = re.search(r'KNOWN_MUTANTS\s*=\s*frozenset\("""(.*?)"""', text, re.DOTALL)
    if not m:
        raise SystemExit("KNOWN_MUTANTS not found in oracle")
    names = m.group(1).split()
    used = set(re.findall(r'\bM\("([a-z0-9_]+)"\)', text)) - {"name"}  # "name": the header comment
    if used != set(names):  # an unlisted switch is never tested; a listed but unused one is a no-op
        raise SystemExit(f"oracle mutant list mismatch: unlisted {sorted(used - set(names))}, "
                         f"unused {sorted(set(names) - used)}")
    return names


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def suite_hashes() -> dict:
    files = sorted(HERE.glob(PATTERN)) + sorted((HERE / "r10lib").rglob("*.py"))
    files = [p for p in files if p != ORACLE]
    return {str(p.relative_to(REPO_ROOT)): sha256(p) for p in files}


def child_env(mutant: str | None) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("R10_") and not k.startswith("PYTHON")}
    env["R10_TARGET"] = "oracle"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if mutant:
        env["R10_ORACLE_MUTANT"] = mutant
    return env


def run_suite(mutant: str | None, timeout: float) -> dict:
    cmd = [sys.executable, "-I", "-B", "-m", "unittest", "discover",
           "-s", str(HERE.relative_to(REPO_ROOT)), "-p", PATTERN]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=child_env(mutant), capture_output=True,
                              text=True, timeout=timeout)
        out, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        out += (exc.stderr or b"").decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code = None
    seconds = round(time.monotonic() - t0, 1)
    bad = sorted({f"{full}" for _kind, _name, full in RESULT_LINE.findall(out)})
    ran = RAN_LINE.search(out)
    summary = SUMMARY.findall(out)
    counts = {"ran": int(ran.group(1)) if ran else None, "failures": 0, "errors": 0, "skipped": 0}
    if summary:
        for part in (summary[-1][1] or "").split(","):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                counts[k] = int(v)
    counts["fail_or_error_tests"] = len(bad)
    return {"mutant": mutant, "exit_code": code, "seconds": seconds, "bad": bad, "counts": counts,
            "timed_out": code is None, "startup_failed": any(s in out for s in STARTUP_FAILURE),
            "tail": out[-1200:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--only", default="", help="comma-separated subset of mutants")
    ap.add_argument("--timeout", type=float, default=900.0)
    args = ap.parse_args()

    names = known_mutants()
    if args.only:
        wanted = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = sorted(set(wanted) - set(names))
        if unknown:
            raise SystemExit(f"unknown mutants: {unknown}")
        names = wanted
    started = dt.datetime.now(dt.timezone.utc)

    base = run_suite(None, args.timeout)
    print(f"baseline: {base['counts']} exit={base['exit_code']} in {base['seconds']}s", flush=True)
    if base["exit_code"] != 0 or base["bad"]:
        print(base["tail"], file=sys.stderr)
        raise SystemExit("baseline (clean oracle) is not green; mutation score would be meaningless")

    def one(name):
        res = run_suite(name, args.timeout)
        flag = "INVALID" if res["startup_failed"] or res["timed_out"] else (
            "killed" if res["bad"] else "SURVIVED")
        print(f"  {name:22} {flag:8} {len(res['bad']):3} failing  {res['seconds']}s", flush=True)
        return res

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(one, names))

    rows, survivors, invalid = [], [], []
    for res in results:
        name = res["mutant"]
        broken = res["startup_failed"] or res["timed_out"]
        killed = bool(res["bad"]) and not broken
        row = {"name": name, "killed": killed, "killing_tests": res["bad"] if killed else [],
               "seconds": res["seconds"], "counts": res["counts"]}
        if broken:
            row["invalid"] = "oracle did not start" if res["startup_failed"] else "timeout"
            row["tail"] = res["tail"]
            invalid.append(name)
        elif not killed:
            survivors.append(name)
            if name in SURVIVOR_NOTES:
                row["note"] = SURVIVOR_NOTES[name]
        rows.append(row)
    killed_n = sum(r["killed"] for r in rows)
    notes = [
        "Oracle = tests/civic/R10/r10lib/oracle/server.py, R10's test-only reference server; "
        "a mutant is one deliberate defect switched on by R10_ORACLE_MUTANT.",
        f"Each mutant: {Path(sys.executable).name} -I -B -m unittest discover -s tests/civic/R10 "
        f"-p '{PATTERN}' in a fresh subprocess with its own oracle, free port and temp DB "
        f"({args.jobs} in parallel). Killed = at least one FAIL/ERROR test id (clean baseline has none).",
        "killing_tests are unittest ids; subtests of one test collapse into that test id.",
    ]
    single = [r["name"] for r in rows if len(r["killing_tests"]) == 1]
    if single:
        notes.append("killed by exactly one test (keep those tests running on every target): "
                     + ", ".join(single))
    notes += [f"survivor {n}: {SURVIVOR_NOTES[n]}" for n in survivors if n in SURVIVOR_NOTES]
    notes += [f"survivor {n}: NOT YET ANALYSED" for n in survivors if n not in SURVIVOR_NOTES]
    notes += [f"invalid {n}: the run could not exercise the suite; not counted as killed" for n in invalid]
    notes += [f"{r['name']}: {r['counts'].get('skipped', 0)} skipped vs baseline "
              f"{base['counts'].get('skipped', 0)}; skips can hide a defect"
              for r in rows if r["counts"].get("skipped", 0) > base["counts"].get("skipped", 0)]
    doc = {
        "generated_utc": started.isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.executable).name, "-I", "-B",
                             str(Path(__file__).resolve().relative_to(REPO_ROOT)), *sys.argv[1:]]),
        "python": sys.version.split()[0],
        "oracle_sha256": sha256(ORACLE),
        "suite_sha256": suite_hashes(),
        "baseline": {"counts": base["counts"], "exit_code": base["exit_code"], "seconds": base["seconds"]},
        "mutants": rows,
        "score": f"{killed_n}/{len(rows)}",
        "survivors": survivors,
        "invalid": invalid,
        "notes": notes,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"score {doc['score']}; survivors: {', '.join(survivors) or 'none'}; "
          f"invalid: {', '.join(invalid) or 'none'} -> {out}")
    sys.exit(0 if not survivors and not invalid else 1)


if __name__ == "__main__":
    main()
