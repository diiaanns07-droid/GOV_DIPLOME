"""K11 round 8: portable smoke for the plan-search modules (Python 3.8+ stdlib only; nothing is installed).

    python smoke/portable_smoke.py [--app-root <prototypes/city-evidence>] [--out report.json] [--quick]

Works from any cwd and on Windows/macOS/Linux (paths via pathlib, subprocess argument lists, UTF-8 decoding of child
output, ASCII-safe console). Each step is PASS / FAIL / NOT_RUN; a missing tool (node, Playwright, --app-root) is
NOT_RUN, never PASS. Exit 1 if any step FAILs, else 0.

Steps
  oracle         Python oracle re-solves all 11 fixtures (+ budget sensitivity) and equals expected_oracle.json
  bundle_fresh   example/worker_bundle.js and fixture_data.js match src/ and fixtures/ (else: python tools/make_worker_bundle.py)
  harness        node tests/harness.cjs                       (core = oracle, worker/chunks, cancel, supersede, release)
  export         node tests/export_unicode.cjs                (UTF-8 export/import; Python + browser parts when available)
  browser        node tests/browser_example.cjs --file        (Playwright Chromium: http and file://)
  protocols      node tests/protocol_matrix.cjs               (Worker by URL vs Blob on http / file:// / text/plain)
  launcher       python tests/launcher_check.py --app-root    (run-demo.bat static + serve.py runtime; Windows not_run)
  serve_mime     python tests/serve_mime_modeled.py --app-root (modeled registry text/plain for .js)
--quick skips browser and protocols.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
STEPS = []


def step(name, status, seconds=None, detail=None):
    STEPS.append({"step": name, "status": status, "seconds": seconds, "detail": detail})
    tail = "" if detail is None else " :: " + (detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=True))[:300]
    print(f"{status:7} {name}" + (f" ({seconds:.1f} s)" if seconds is not None else "") + tail, flush=True)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_oracle():
    t = time.time()
    oracle = load_module(ROOT / "oracle" / "plan_oracle.py", "k11_plan_oracle")
    bad, n = [], 0
    for d in ("synthetic", "real"):
        exp = json.loads((ROOT / "fixtures" / d / "expected_oracle.json").read_bytes().decode("utf-8"))
        for name, want in sorted(exp.items()):
            fx = json.loads((ROOT / "fixtures" / d / name).read_bytes().decode("utf-8"))
            sc = fx["scenario"]
            got = {"main": oracle.solve(fx["context"], sc),
                   "sensitivity": {str(b): oracle.solve(fx["context"], sc, b) for b in sorted({0, sc["budget"] // 2, sc["budget"]})}}
            n += 1
            if json.loads(json.dumps(got, default=str)) != want:
                bad.append(d + "/" + name)
    step("oracle", "PASS" if n == 11 and not bad else "FAIL", time.time() - t, {"fixtures": n, "mismatch": bad})


def check_bundle():
    t = time.time()
    js = (ROOT / "example" / "worker_bundle.js").read_bytes().decode("utf-8")
    line = next((x for x in js.splitlines() if x.startswith("window.CITY_PLAN_WORKER_SOURCES_SHA256 = ")), "")
    recorded = json.loads(line.split(" = ", 1)[1].rstrip(";")) if line else {}
    actual = {p: hashlib.sha256((ROOT / "src" / p).read_bytes()).hexdigest() for p in ("plan_core.js", "plan_worker.js")}
    tool = load_module(ROOT / "tools" / "make_worker_bundle.py", "k11_make_bundle")
    data_js = (ROOT / "example" / "fixture_data.js").read_bytes().decode("utf-8")
    body = data_js.split("window.K11_EXAMPLE = ", 1)[1].rstrip().rstrip(";")
    shipped = json.loads(body)
    want = {}
    for d, f in tool.EXAMPLE_FIXTURES:
        fx = json.loads((ROOT / "fixtures" / d / f).read_bytes().decode("utf-8"))
        want[f] = {"provenance": fx["provenance"], "context": fx["context"], "scenario": fx["scenario"]}
    stale = [k for k in actual if recorded.get(k) != actual[k]] + (["fixture_data.js"] if shipped != want else [])
    step("bundle_fresh", "PASS" if not stale else "FAIL", time.time() - t,
         None if not stale else {"stale": stale, "fix": "python tools/make_worker_bundle.py"})


def node_env():
    node = shutil.which("node")
    if not node:
        return None, None, "node not found on PATH"
    env = dict(os.environ)
    if not env.get("NODE_PATH"):  # Playwright installed globally is found through NODE_PATH; nothing is installed here
        npm = shutil.which("npm")
        if npm:
            try:
                r = subprocess.run([npm, "root", "-g"], capture_output=True, timeout=60)
                root = r.stdout.decode("utf-8", "replace").strip()
                if r.returncode == 0 and root:
                    env["NODE_PATH"] = root
            except (OSError, subprocess.SubprocessError):
                pass
    return node, env, None


def run(name, argv, env=None, timeout=600, not_run_codes=(3,), cwd=None):
    t = time.time()
    try:
        r = subprocess.run(argv, cwd=str(cwd or ROOT), env=env, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        step(name, "FAIL", time.time() - t, f"timeout after {timeout} s")
        return
    out = r.stdout.decode("utf-8", "replace")
    lines = [x for x in out.splitlines() if x.strip()]
    last = lines[-1] if lines else ""
    if r.returncode in not_run_codes:
        step(name, "NOT_RUN", time.time() - t, last)
        return
    fails = [x for x in lines if x.startswith("FAIL")]
    nr = [x for x in lines if x.startswith("NOT_RUN")]
    detail = {"exit": r.returncode, "last": last}
    if fails:
        detail["fail"] = fails[:5]
    if nr:
        detail["inner_not_run"] = nr[:5]
    if r.returncode != 0 and r.stderr:
        detail["stderr"] = r.stderr.decode("utf-8", "replace")[-300:]
    step(name, "PASS" if r.returncode == 0 else "FAIL", time.time() - t, detail)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--app-root", help="prototypes/city-evidence of the BUILD checkout (for launcher/serve_mime)")
    ap.add_argument("--out")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    env_info = {"platform": platform.platform(), "python": sys.version.split()[0], "cwd": os.getcwd(), "k11_root": str(ROOT)}
    print("K11 portable smoke:", json.dumps(env_info, ensure_ascii=True), flush=True)
    for f in (check_oracle, check_bundle):
        try:
            f()
        except Exception as e:  # a crash in a step is a FAIL of that step, the others still run
            step(f.__name__.replace("check_", ""), "FAIL", None, f"{type(e).__name__}: {e}")
    node, env, why = node_env()
    if node:
        env_info["node"] = subprocess.run([node, "--version"], capture_output=True).stdout.decode().strip()
        env_info["NODE_PATH_set"] = bool(env.get("NODE_PATH"))
        run("harness", [node, str(ROOT / "tests" / "harness.cjs")], env)
        export_args = [node, str(ROOT / "tests" / "export_unicode.cjs")] + (["--no-browser"] if a.quick else [])
        run("export", export_args, env)
        if a.quick:
            step("browser", "NOT_RUN", None, "--quick")
            step("protocols", "NOT_RUN", None, "--quick")
        else:
            run("browser", [node, str(ROOT / "tests" / "browser_example.cjs"), "--file"], env)
            run("protocols", [node, str(ROOT / "tests" / "protocol_matrix.cjs")], env)
    else:
        for s in ("harness", "export", "browser", "protocols"):
            step(s, "NOT_RUN", None, why)
    if a.app_root:
        app = Path(a.app_root).resolve()
        run("launcher", [sys.executable, str(ROOT / "tests" / "launcher_check.py"), "--app-root", str(app)], timeout=180)
        run("serve_mime", [sys.executable, str(ROOT / "tests" / "serve_mime_modeled.py"), "--app-root", str(app)], timeout=180)
    else:
        step("launcher", "NOT_RUN", None, "no --app-root")
        step("serve_mime", "NOT_RUN", None, "no --app-root")
    counts = {s: sum(1 for x in STEPS if x["status"] == s) for s in ("PASS", "FAIL", "NOT_RUN")}
    print(json.dumps(counts), flush=True)
    if a.out:
        Path(a.out).write_bytes((json.dumps({"tool": "smoke/portable_smoke.py", "environment": env_info, "counts": counts,
                                             "steps": STEPS}, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
