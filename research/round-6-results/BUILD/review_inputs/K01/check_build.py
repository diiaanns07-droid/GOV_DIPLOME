"""K01 round-5 REVIEW: reproducibility check of the city-evidence BUILD (stdlib; browser check optional).

  python3 check_build.py --app-root PATH [--url http://127.0.0.1:8765/] [--browser] [--json report.json]

--app-root  extracted copy of prototypes/city-evidence (see extract_build.py). Checks:
  I1 source_manifest.json: every copied input exists, bytes + sha256 match
  I2 inputs/k10/package_manifest.json: data files bytes + sha256 + feature count match
  I3 no symlinks / no files pointing outside the app root
  I4 web/data.js is reproducible: tools/build_data.py run on a temp copy gives identical bytes
  S1 serve.py started from a foreign cwd serves index.html + every <script src> byte-identical to web/
  S2 path traversal (/../serve.py, %2e%2e) is refused
  S3 runtime audit (sys.addaudithook) of serve.py: no file opened outside app-root/web and the Python install,
     no outbound socket.connect
  N1 socket side effect: after inputs/k10/scripts/offline_check.run() returns, a localhost connect still works
  B1 (--browser, Node + Playwright) page loads with no request to a non-local host and no console errors
--url       check an already running server instead of starting serve.py (S1/S2 against that URL; S3 skipped).
Exit code: 0 if every check passed, 1 otherwise. Baseline-known failures are labelled, not hidden.
"""
import argparse, hashlib, json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_SHA = "0bf27deb8549b325b34a9610402613d745544edb"
KNOWN_BASELINE_FAIL = {"N1": "offline_check.install_guards() never restores socket.* (round-4 K01 finding 4)"}

results = []


def rec(cid, ok, detail, **extra):
    r = {"id": cid, "ok": bool(ok), "detail": detail, **extra}
    if not ok and cid in KNOWN_BASELINE_FAIL:
        r["known_on_baseline"] = f"{BASELINE_SHA[:7]}: {KNOWN_BASELINE_FAIL[cid]}"
    results.append(r)
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}", flush=True)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# ---------- I: integrity ----------
def check_integrity(app):
    sm = app / "source_manifest.json"
    if not sm.exists():
        rec("I1", False, "source_manifest.json missing"); return
    m = json.loads(sm.read_text(encoding="utf-8"))
    bad = []
    for f in m["files"]:
        p = app / f["copied_to"]
        if not p.is_file():
            bad.append(f"missing {f['copied_to']}"); continue
        b = p.read_bytes()
        if len(b) != f["bytes"] or sha(b) != f["sha256"]:
            bad.append(f"hash/size {f['copied_to']}")
    rec("I1", not bad, f"{len(m['files'])} inputs vs source_manifest.json" + (f"; {bad[:5]}" if bad else ""),
        sources=sorted({(f["slot"], f["sha"][:7]) for f in m["files"]}))

    pm = app / "inputs" / "k10" / "package_manifest.json"
    bad, n = [], 0
    if pm.exists():
        man = json.loads(pm.read_text(encoding="utf-8"))
        for city, cm in man["cities"].items():
            for name, f in cm["files"].items():
                n += 1
                p = app / "inputs" / "k10" / f["path"]
                if not p.is_file():
                    bad.append(f"missing {city}/{name}"); continue
                b = p.read_bytes()
                if len(b) != f["bytes"] or sha(b) != f["sha256"] or len(json.loads(b)["features"]) != f["features"]:
                    bad.append(f"mismatch {city}/{name}")
    else:
        bad.append("package_manifest.json missing")
    rec("I2", not bad, f"{n} K10 data files vs package_manifest.json" + (f"; {bad}" if bad else ""))

    links = [str(p.relative_to(app)) for p in app.rglob("*") if p.is_symlink()]
    rec("I3", not links, "no symlinks in app root" if not links else f"symlinks: {links}")

    tmp = Path(tempfile.mkdtemp(prefix="k01r5_rebuild_"))
    try:
        cp = tmp / "app"
        shutil.copytree(app, cp, ignore=shutil.ignore_patterns("__pycache__"))
        r = subprocess.run([sys.executable, str(cp / "tools" / "build_data.py")], cwd=tmp, capture_output=True, text=True, timeout=120)
        same = r.returncode == 0 and (cp / "web" / "data.js").read_bytes() == (app / "web" / "data.js").read_bytes()
        rec("I4", same, f"tools/build_data.py on temp copy: exit {r.returncode}, web/data.js "
            + ("byte-identical" if same else "DIFFERENT") + (f"; stderr: {r.stderr.strip()[-300:]}" if r.returncode else ""),
            rebuilt_sha256=sha((cp / "web" / "data.js").read_bytes()) if (cp / "web" / "data.js").exists() else None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------- S: serving ----------
AUDIT_WRAPPER = r'''
import os, sys, runpy
LOG = int(os.environ["K01_AUDIT_FD"])
def hook(ev, args):
    if ev == "open" and args and isinstance(args[0], (str, bytes)):
        os.write(LOG, ("open\t" + os.path.abspath(os.fsdecode(args[0])) + "\n").encode("utf-8", "replace"))
    elif ev == "socket.connect":
        os.write(LOG, ("connect\t" + repr(args[1]) + "\n").encode())
    elif ev in ("subprocess.Popen", "os.system"):
        os.write(LOG, (ev + "\t" + repr(args)[:200] + "\n").encode())
sys.addaudithook(hook)
serve = sys.argv[1]
sys.argv = [serve] + sys.argv[2:]
runpy.run_path(serve, run_name="__main__")
'''


def expected_assets(web):
    html = (web / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'''(?:src|href)\s*=\s*["']([^"'#?]+)''', html)
    return ["index.html"] + [r for r in refs if not re.match(r"^[a-z]+:", r)]


def check_served(base, web, label):
    assets = expected_assets(web)
    bad = []
    for a in assets:
        st, body = http_get(base + ("" if a == "index.html" else a))
        if st != 200 or body != (web / a).read_bytes():
            bad.append(f"{a}: status {st}, {'same' if body == (web / a).read_bytes() else 'bytes differ'}")
    rec("S1", not bad, f"{label}: {len(assets)} assets ({', '.join(assets)}) " + ("byte-identical to web/" if not bad else f"{bad}"))
    trav = {}
    for path in ("../serve.py", "%2e%2e/serve.py", "..%2fserve.py", "%2e%2e%2fREADME.md"):
        st, body = http_get(base + path)
        leaked = st == 200 and (body == (web.parent / "serve.py").read_bytes() or body == (web.parent / "README.md").read_bytes())
        trav[path] = st
        if leaked:
            bad.append(path)
    rec("S2", not any(p in bad for p in trav), f"traversal requests -> {trav}")


def check_serve(app):
    port = free_port()
    cwd = Path(tempfile.mkdtemp(prefix="k01r5_cwd_"))
    rfd, wfd = os.pipe()
    env = dict(os.environ, K01_AUDIT_FD=str(wfd), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.Popen([sys.executable, "-c", AUDIT_WRAPPER, str(app / "serve.py"), str(port)],
                            cwd=cwd, env=env, pass_fds=(wfd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.close(wfd)
    base = f"http://127.0.0.1:{port}/"
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close(); break
            except OSError:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
        if proc.poll() is not None:
            rec("S1", False, f"serve.py exited early: {proc.stderr.read().decode()[-400:]}"); return
        check_served(base, app / "web", f"serve.py started with cwd={cwd} (outside app root)")
    finally:
        proc.terminate(); proc.wait(5)
        shutil.rmtree(cwd, ignore_errors=True)
    log = b""
    while True:
        chunk = os.read(rfd, 65536)
        if not chunk:
            break
        log += chunk
    os.close(rfd)
    web = str((app / "web").resolve()) + os.sep
    py_roots = {os.path.realpath(p) + os.sep for p in {sys.prefix, sys.base_prefix, sys.exec_prefix}}
    allowed_misc = ("/dev/", "/proc/", "/etc/mime.types", "/etc/localtime", "/usr/share/zoneinfo/")
    foreign, connects, opened_web = [], [], set()
    for line in log.decode("utf-8", "replace").splitlines():
        kind, _, val = line.partition("\t")
        if kind == "open":
            rp = os.path.realpath(val)
            if rp.startswith(web):
                opened_web.add(os.path.relpath(rp, web) + ("" if os.path.exists(rp) else " (absent, 404)"))
            elif rp == str((app / "serve.py").resolve()):
                pass
            elif any(rp.startswith(r) for r in py_roots) or rp.startswith(allowed_misc) or "/mime" in rp:
                pass
            else:
                foreign.append(rp)
        elif kind in ("connect", "subprocess.Popen", "os.system"):
            connects.append(line)
    rec("S3", not foreign and not connects,
        f"audited serve.py: opened in web/ {sorted(opened_web)}; foreign opens {sorted(set(foreign))[:10]}; connect/subprocess {connects[:5]}")


# ---------- N: socket side effect ----------
N1_CHILD = r'''
import socket, sys, threading
sys.path.insert(0, sys.argv[1])
import offline_check
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
threading.Thread(target=lambda: srv.accept(), daemon=True).start()
rep = offline_check.run()
print("offline_check_ok", rep["ok"])
try:
    socket.create_connection(("127.0.0.1", port), timeout=2).close()
    print("connect_after_run OK")
except Exception as e:
    print("connect_after_run FAIL", type(e).__name__, e)
'''


def check_socket_side_effect(app):
    scripts = app / "inputs" / "k10" / "scripts"
    r = subprocess.run([sys.executable, "-c", N1_CHILD, str(scripts)], capture_output=True, text=True, timeout=120,
                       cwd=tempfile.gettempdir())
    out = r.stdout.strip().replace("\n", " | ")
    rec("N1", r.returncode == 0 and "offline_check_ok True" in out and "connect_after_run OK" in out,
        f"localhost connect after offline_check.run(): {out or r.stderr.strip()[-300:]}")


# ---------- B: browser ----------
def check_browser(target, label):
    js = HERE / "browser_check.cjs"
    npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip() if shutil.which("npm") else ""
    if not shutil.which("node") or not npm_root:
        rec("B1", False, "node/npm not found — browser check not run", skipped=True); return
    r = subprocess.run(["node", str(js), target], capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, NODE_PATH=npm_root))
    try:
        rep = json.loads(r.stdout)
    except json.JSONDecodeError:
        rec("B1", False, f"browser check crashed: {r.stderr.strip()[-400:]}"); return
    ok = rep.get("ok", False)
    rec("B1", ok, f"{label}: {rep.get('requests')} requests, external {rep.get('external')}, "
        f"failed {rep.get('failed')}, console errors {rep.get('console_errors')}, title {rep.get('title')!r}", browser=rep)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app-root", type=Path)
    ap.add_argument("--url")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    if not a.app_root and not a.url:
        ap.error("need --app-root and/or --url")
    app = a.app_root.resolve() if a.app_root else None
    if app:
        check_integrity(app)
        check_socket_side_effect(app)
    if a.url:
        base = a.url if a.url.endswith("/") else a.url + "/"
        if app:
            check_served(base, app / "web", f"--url {base}")
        else:
            st, body = http_get(base)
            rec("S1", st == 200 and b"<script" in body, f"--url {base}: status {st}, {len(body)} bytes (no app-root to compare)")
        if a.browser:
            check_browser(base, f"--url {base}")
    elif app:
        check_serve(app)
        if a.browser:
            check_browser((app / "web" / "index.html").as_uri(), "file:// web/index.html")
    report = {"app_root": str(app) if app else None, "url": a.url, "python": sys.version.split()[0],
              "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "ok": all(r["ok"] for r in results if not r.get("skipped")), "results": results}
    if a.json:
        a.json.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("OVERALL", "PASS" if report["ok"] else "FAIL",
          "| failed:", [r["id"] + (" (known on baseline)" if r.get("known_on_baseline") else "") for r in results if not r["ok"]])
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
