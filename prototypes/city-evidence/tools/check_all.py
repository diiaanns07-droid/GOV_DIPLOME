"""One command to check the demo: inputs -> contract -> facts catalog -> integration.

    python3 tools/check_all.py [--log FILE.json]

Steps (no network; each external script runs in its own process):
  1. inputs   — sha256 of every copied input against source_manifest.json, inputs/r4/MANIFEST.json and the
                manifests of the patched copies (contract, K03 v2, K02 v4); license texts equal K08 originals
  2. package  — K10 offline_check.py in a subprocess (its socket guard never touches this process; K01 #4)
  3. build    — web/data.js and web/evidence.js are byte-equal to a fresh in-memory rebuild
                (evidence rebuild needs shapely+pyproj; without them the committed file is validated by the contract)
  4. facts    — tools/explain_ref.py output equals tests/expected_explanations.json; node tests/conformance.cjs
  5. tests    — python -m unittest discover -s tests
Browser smoke test is separate: NODE_PATH="$(npm root -g)" node tests/smoke.cjs
Exit code 0 only if every executed step passed; skipped steps are reported, never counted as passed.
"""
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "tools"))
RESULTS = []


def h(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def record(step, name, ok, detail=""):
    RESULTS.append({"step": step, "check": name, "status": "pass" if ok is True else "skip" if ok is None else "FAIL",
                    "detail": detail})
    print(f"[{'PASS' if ok is True else 'SKIP' if ok is None else 'FAIL'}] {step}: {name}" + (f" — {detail}" if detail else ""))


def step_inputs():
    bad = []
    sm = json.loads((APP / "source_manifest.json").read_text(encoding="utf-8"))
    for f in sm["files"]:
        if h(APP / f["copied_to"]) != f["sha256"]:
            bad.append(f["copied_to"])
    r4 = json.loads((APP / "inputs/r4/MANIFEST.json").read_text(encoding="utf-8"))
    for f in r4["files"]:
        if h(APP / f["copied_to"]) != f["sha256"]:
            bad.append(f["copied_to"])
    record("inputs", f"{len(sm['files'])} + {len(r4['files'])} copied inputs match recorded sha256", not bad, ", ".join(bad[:5]))
    cm = json.loads((APP / "inputs/contract/CONTRACT_MANIFEST.json").read_text(encoding="utf-8"))
    cbad = [r["path"] for r in cm["files"] if h(APP / r["from"]) != r["original_sha256"]
            or h(APP / "inputs/contract" / r["path"]) != r["used_sha256"]]
    record("inputs", f"contract {cm['contract_id']}: originals and patched copy match manifest "
           f"({sum(r['modified'] for r in cm['files'])} modified)", not cbad, ", ".join(cbad))
    k3 = json.loads((APP / "inputs/k03v2_root/MANIFEST_K03V2.json").read_text(encoding="utf-8"))
    m = k3["modified"][0]
    ok3 = (h(APP / "inputs/k03_root" / m["path"]) == m["original_sha256"]
           and h(APP / "inputs/k03v2_root" / m["path"]) == m["patched_sha256"])
    record("inputs", "K03 v2: original byte-exact, patched copy matches manifest", ok3)
    k2 = json.loads((APP / "inputs/k02v4/MANIFEST.json").read_text(encoding="utf-8"))
    ok2 = h(APP / k2["original"]["path"]) == k2["original"]["sha256"] and h(APP / k2["adapted"]["path"]) == k2["adapted"]["sha256"]
    record("inputs", "K02 v4: original byte-exact, adapted copy matches manifest", ok2)
    att = ["ATTRIBUTION.md", "attribution.json", "LICENSES/Apache-2.0.txt", "LICENSES/CDLA-Permissive-2.0.txt", "LICENSES/ODbL-1.0.txt"]
    abad = [a for a in att if h(APP / "web/attribution" / a) != h(APP / "inputs/r4/K08/attribution" / a)]
    record("inputs", "web/attribution equals K08 r4 originals", not abad, ", ".join(abad))
    pm = next(f for f in sm["files"] if f["path"].endswith("K10/package_manifest.json"))
    record("inputs", "K10 package_manifest.json anchored by source_manifest sha256 (K01 #2)",
           h(APP / "inputs/k10/package_manifest.json") == pm["sha256"])


def step_package():
    r = subprocess.run([sys.executable, str(APP / "inputs/k10/scripts/offline_check.py")], capture_output=True, text=True,
                       encoding="utf-8")
    ok = r.returncode == 0 and '"ok": true' in r.stdout
    record("package", "K10 offline_check.py (subprocess) exit 0, ok=true", ok, r.stderr[-300:] if not ok else "")


def step_build():
    import build_data
    data_txt = build_data.render_text(build_data.build())
    record("build", "web/data.js == rebuild", data_txt == (APP / "web/data.js").read_text(encoding="utf-8"))
    import contract as K
    t = (APP / "web/evidence.js").read_text(encoding="utf-8")
    ev = K.loads_strict(t[t.index("{"):t.rstrip().rindex(";")])
    errs = [e for c in ev["cities"].values() for e in K.validate_all(c["observations"], ev["as_of"])[0]]
    record("build", f"committed evidence.js passes {K.CONTRACT_ID} (strict JSON, records, dataset)", not errs, "; ".join(errs[:3]))
    if importlib.util.find_spec("shapely") and importlib.util.find_spec("pyproj"):
        import build_evidence
        record("build", "web/evidence.js == rebuild (K03 v2 assign + K05 recount + QA)", build_evidence.render_text(build_evidence.build()) == t)
    else:
        record("build", "web/evidence.js rebuild", None, "shapely/pyproj not installed: pip install -r requirements-build.txt")


def step_facts():
    import explain_ref
    exp = json.loads((APP / "tests/expected_explanations.json").read_text(encoding="utf-8"))
    data, ev = explain_ref.load_evidence()
    diff = [c for c in exp["cases"] if {k: v for k, v in explain_ref.explain(data, ev, c["city"], set(c["groups"]), c["lang"]).items()}
            != {k: c[k] for k in ("text", "facts_used", "scenario", "catalog_digest")}]
    record("facts", f"Python K02 reference reproduces {len(exp['cases'])} expected explanations", not diff,
           ", ".join(f"{c['city']}/{c['lang']}" for c in diff))
    node = shutil.which("node")
    if not node:
        record("facts", "node tests/conformance.cjs", None, "node not installed")
        return
    r = subprocess.run([node, str(APP / "tests/conformance.cjs")], capture_output=True, text=True, encoding="utf-8")
    n = r.stdout.count("PASS ")
    record("facts", f"JS facts.js conformance ({n} checks)", r.returncode == 0, r.stdout[-400:] if r.returncode else "")


def step_tests():
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=APP, capture_output=True, text=True,
                       encoding="utf-8")
    tail = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""
    ran = next((l for l in r.stderr.splitlines() if l.startswith("Ran ")), "")
    record("tests", f"python -m unittest discover -s tests ({ran}; {tail})", r.returncode == 0, r.stderr[-600:] if r.returncode else "")


def main():
    for step in (step_inputs, step_package, step_build, step_facts, step_tests):
        try:
            step()
        except Exception as e:  # a crashing step is a failure, never a skip
            record(step.__name__[5:], "step crashed", False, f"{type(e).__name__}: {e}")
    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    summary = {"when_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "python": platform.python_version(),
               "platform": platform.platform(), "passed": sum(r["status"] == "pass" for r in RESULTS),
               "skipped": sum(r["status"] == "skip" for r in RESULTS), "failed": len(failed), "results": RESULTS}
    if "--log" in sys.argv:
        Path(sys.argv[sys.argv.index("--log") + 1]).write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
                                                               encoding="utf-8", newline="\n")
    print(f"\n{summary['passed']} passed, {summary['skipped']} skipped, {summary['failed']} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
