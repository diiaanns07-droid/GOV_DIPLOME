"""Run the R10 suite against one target and write machine-readable evidence.

  python3 -I -B tests/civic/R10/run_acceptance.py --label oracle-clean \
      --out research/round-11-results/R10/runs/oracle-clean.json [--pattern 'test_api_*.py']

The JSON holds: target (code SHA, dirty flag, base URL), suite file hashes,
per-test status PASS/FAIL/ERROR/NOT_RUN with message, per-acceptance-ID rollup,
and the command journal (every spawned process with exit code).
Exit code: 0 when no FAIL/ERROR, 1 otherwise, 2 when the target could not start.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import time
import traceback
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from r10lib import target as target_mod  # noqa: E402

TAG = re.compile(r"\[([A-Z]\d{2})\]")


def suite_hashes() -> dict:
    files = sorted(HERE.glob("test_*.py")) + sorted((HERE / "r10lib").rglob("*.py"))
    return {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()[:16] for p in files}


class Collector(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self._t0 = {}

    def _row(self, test, status, message=""):
        case = getattr(test, "test_case", test)  # unittest _SubTest wraps the real case
        doc = (getattr(case, "_testMethodDoc", None) or "").strip().splitlines()
        first = doc[0] if doc else ""
        self.rows.append({
            "test": test.id(), "status": status, "ids": TAG.findall(first),
            "title": TAG.sub("", first).strip(), "message": message[-1500:],
            "seconds": round(time.monotonic() - self._t0.get(case.id(), time.monotonic()), 3),
        })

    def startTest(self, test):
        self._t0[test.id()] = time.monotonic()
        super().startTest(test)

    def addSuccess(self, test):
        self._row(test, "PASS")

    def addFailure(self, test, err):
        self._row(test, "FAIL", "".join(traceback.format_exception_only(err[0], err[1])))

    def addError(self, test, err):
        self._row(test, "ERROR", "".join(traceback.format_exception(*err))[-1500:])

    def addSkip(self, test, reason):
        self._row(test, "NOT_RUN", reason)

    def addExpectedFailure(self, test, err):
        self._row(test, "XFAIL", "".join(traceback.format_exception_only(err[0], err[1])))

    def addUnexpectedSuccess(self, test):
        self._row(test, "XPASS")

    def addSubTest(self, test, subtest, err):
        if err is not None:
            kind = "FAIL" if issubclass(err[0], test.failureException) else "ERROR"
            self._row(subtest, kind, "".join(traceback.format_exception_only(err[0], err[1])))
        super().addSubTest(test, subtest, err)


def rollup(rows):
    by_id: dict[str, list[str]] = {}
    for row in rows:
        for tag in row["ids"] or ["untagged"]:
            by_id.setdefault(tag, []).append(row["status"])
    out = {}
    for tag, statuses in sorted(by_id.items()):
        if any(s in ("FAIL", "ERROR") for s in statuses):
            status = "FAIL"
        elif all(s == "PASS" for s in statuses):
            status = "PASS"
        elif any(s == "PASS" for s in statuses):
            status = "PARTIAL"
        else:
            status = "NOT_RUN"
        out[tag] = {"status": status, "tests": len(statuses),
                    "counts": {s: statuses.count(s) for s in sorted(set(statuses))}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pattern", default="test_*.py")
    ap.add_argument("--start", default=None, help="sub-directory to discover in (e.g. standalone)")
    args = ap.parse_args()

    started = dt.datetime.now(dt.timezone.utc)
    loader = unittest.TestLoader()
    start = HERE / args.start if args.start else HERE
    suite = loader.discover(str(start), pattern=args.pattern, top_level_dir=str(start))
    result = Collector()
    t0 = time.monotonic()
    startup_error = None
    try:
        suite.run(result)
    except Exception:  # target start failures surface here when raised outside tests
        startup_error = traceback.format_exc()[-3000:]
    seconds = round(time.monotonic() - t0, 2)

    tgt = target_mod._TARGET
    rows = sorted(result.rows, key=lambda r: r["test"])
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in
              ("PASS", "FAIL", "ERROR", "NOT_RUN", "XFAIL", "XPASS")}
    doc = {
        "label": args.label,
        "started_utc": started.isoformat(timespec="seconds"),
        "seconds": seconds,
        "command": " ".join([Path(sys.executable).name, "-I", "-B", *sys.argv]),
        "python": platform.python_version(), "platform": platform.platform(),
        "target": tgt.describe() if tgt else {"target": None, "note": "no test started a server"},
        "suite_files": suite_hashes(),
        "counts": counts,
        "acceptance": rollup(rows),
        "tests": rows,
        "journal": target_mod.JOURNAL,
        "startup_error": startup_error,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.label}: {counts} in {seconds}s -> {out}")
    for tag, info in doc["acceptance"].items():
        print(f"  {tag:8} {info['status']:8} {info['counts']}")
    if startup_error:
        print(startup_error, file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if counts["FAIL"] or counts["ERROR"] else 0)


if __name__ == "__main__":
    main()
