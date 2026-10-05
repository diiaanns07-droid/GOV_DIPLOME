"""K01 round-6 acceptance adapter for prototypes/city-evidence (stdlib only).

  python3 check_r6.py --app-root PATH [--extract-manifest EXTRACT_MANIFEST.json] [--json out.json]

Replaces round-5 N1/test_socket_side_effect (TEST_INCOMPATIBLE for builds that run offline_check in a subprocess):
  P1  no module of the build (outside inputs/k10) imports offline_check in-process (AST scan)
  P2  parent process after tools/check_all.step_package(): socket.* identical objects, localhost connect works
  P3  the subprocess path still blocks the network inside offline_check (guard not dropped by the fix)
Manifests:
  M1  app root bytes == git blobs of the target SHA (EXTRACT_MANIFEST from extract_build.py)
  M2  every file under inputs/ is anchored by some manifest of the build (no unlisted inputs)
  M3  tools/check_all.py run from a foreign cwd: exit 0, no FAIL (skips listed, not counted as pass)
Temporary / written files during check_all (audit hook in every Python child via sitecustomize):
  T1  no file written/created/removed outside the private TMPDIR and /dev (app root writes listed separately)
  T2  TMPDIR empty after the run (all temp dirs cleaned)
  T3  app root content unchanged after the run (only __pycache__ allowed, reported)
"""
import argparse, ast, hashlib, json, os, shutil, socket, subprocess, sys, tempfile, threading, time
from pathlib import Path

R = []


def rec(cid, verdict, detail, **kw):
    R.append({"id": cid, "verdict": verdict, "detail": detail, **kw})
    print(f"[{verdict}] {cid}: {detail}", flush=True)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def snapshot(app):
    return {str(p.relative_to(app)): sha(p) for p in app.rglob("*") if p.is_file()}


# ---------- P ----------
def p1(app):
    hits = []
    for f in app.rglob("*.py"):
        rel = f.relative_to(app).as_posix()
        if rel.startswith("inputs/"):
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), rel)
        for n in ast.walk(tree):
            if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "offline_check" for a in n.names):
                hits.append(f"{rel}:{n.lineno}")
            elif isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "offline_check":
                hits.append(f"{rel}:{n.lineno}")
            elif isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) in (
                    "spec_from_file_location", "import_module", "run_path", "__import__") and "offline_check" in ast.dump(n):
                hits.append(f"{rel}:{n.lineno}")
    rec("P1", "PASS" if not hits else "FAIL", "no in-process import of offline_check outside inputs/" if not hits else f"in-process load at {hits}")


def p2(app):
    sys.path.insert(0, str(app / "tools"))
    orig = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
    import check_all
    check_all.step_package()
    pkg = [r for r in check_all.RESULTS if r["step"] == "package"]
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    threading.Thread(target=srv.accept, daemon=True).start()
    try:
        socket.create_connection(srv.getsockname(), timeout=2).close(); conn = "ok"
    except Exception as e:
        conn = f"{type(e).__name__}: {e}"
    same = orig == (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)
    ok = same and conn == "ok" and pkg and pkg[0]["status"] == "pass"
    rec("P2", "PASS" if ok else "FAIL", f"check_all.step_package() -> {pkg[0]['status'] if pkg else 'no result'}; "
        f"socket attrs unchanged={same}; localhost connect after={conn}")


P3_SITE = r'''
import socket, os
_orig = socket.socket.connect
def _probe():
    try:
        s = socket.socket(); s.settimeout(1); s.connect(("127.0.0.1", int(os.environ["K01_PROBE_PORT"]))); s.close(); return "connected"
    except Exception as e:
        return type(e).__name__
import builtins
_open = builtins.open
_done = []
def _hook(ev, args):
    # first data-file open inside offline_check happens after install_guards(): probe the network there
    if ev == "open" and not _done and isinstance(args[0], str) and args[0].endswith(".geojson") and "K01_PROBE_PORT" in os.environ:
        _done.append(1)
        os.write(2, ("K01_PROBE " + _probe() + "\n").encode())
import sys; sys.addaudithook(_hook)
'''


def p3(app):
    d = Path(tempfile.mkdtemp(prefix="k01r6_p3_"))
    (d / "sitecustomize.py").write_text(P3_SITE, encoding="utf-8")
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(4)
    threading.Thread(target=lambda: [srv.accept() for _ in range(4)], daemon=True).start()
    env = dict(os.environ, PYTHONPATH=str(d), K01_PROBE_PORT=str(srv.getsockname()[1]))
    r = subprocess.run([sys.executable, str(app / "inputs/k10/scripts/offline_check.py")], capture_output=True, text=True,
                       env=env, cwd=tempfile.gettempdir())
    shutil.rmtree(d)
    probe = next((l.split()[1] for l in r.stderr.splitlines() if l.startswith("K01_PROBE")), "no probe")
    ok = r.returncode == 0 and probe == "NetworkBlocked"
    rec("P3", "PASS" if ok else "FAIL", f"offline_check subprocess exit {r.returncode}; network probe during check -> {probe}")


# ---------- M ----------
def m1(app, em):
    if not em:
        rec("M1", "SKIP", "no --extract-manifest given"); return
    m = json.loads(Path(em).read_text(encoding="utf-8"))
    bad = [f["path"] for f in m["files"] if not (app / f["path"]).is_file() or sha(app / f["path"]) != f["sha256"]]
    extra = sorted(k for k in set(snapshot(app)) - {f["path"] for f in m["files"]} if "__pycache__" not in k)
    rec("M1", "PASS" if not bad and not extra else "FAIL",
        f"{len(m['files'])} files == git blobs of {m['sha'][:7]}" + (f"; bad {bad[:5]}" if bad else "") + (f"; extra {extra[:5]}" if extra else ""),
        target_sha=m["sha"])


def m2(app):
    listed = set()
    for mf in app.rglob("*MANIFEST*.json"):
        listed.add(mf.relative_to(app).as_posix())
        txt = mf.read_text(encoding="utf-8")
        for f in app.joinpath("inputs").rglob("*"):
            if f.is_file():
                rel = f.relative_to(app).as_posix()
                rel_in = f.relative_to(app / "inputs").as_posix()
                if f'"{rel}"' in txt or f'"{rel_in}"' in txt or any(f'"{rel[len(p):]}"' in txt for p in ("inputs/contract/", "inputs/k03v2_root/", "inputs/k03_root/"))\
                        or f'"{rel.split("/", 2)[-1]}"' in txt:
                    listed.add(rel)
    sm = (app / "source_manifest.json").read_text(encoding="utf-8")
    files = sorted(f.relative_to(app).as_posix() for f in app.joinpath("inputs").rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    unlisted = [f for f in files if f not in listed and f'"{f}"' not in sm]
    rec("M2", "PASS" if not unlisted else "FAIL", f"{len(files)} files under inputs/; not named in any manifest: {len(unlisted)}",
        unlisted=unlisted)


SITE = r'''
import os, sys
_LOG = os.environ.get("K01_WLOG")
def _w(s):
    fd = os.open(_LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600); os.write(fd, (s + "\n").encode("utf-8", "replace")); os.close(fd)
def _hook(ev, a):
    try:
        if ev == "open" and isinstance(a[0], (str, bytes)):
            mode, flags = a[1], a[2] or 0
            if (mode and any(c in mode for c in "wax+")) or (flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
                p = os.path.abspath(os.fsdecode(a[0]))
                if p != _LOG: _w("write\t" + p)
        elif ev in ("os.mkdir", "os.remove", "os.rename", "os.rmdir", "shutil.rmtree", "shutil.copytree", "shutil.copyfile"):
            ps = [os.fsdecode(x) for x in a if isinstance(x, (str, bytes, os.PathLike))]
            # os.remove/os.rmdir inside shutil.rmtree use dir_fd + relative names: covered by the shutil.rmtree event
            ps = [x for x in ps if os.path.isabs(x)] if ev in ("os.remove", "os.rmdir", "os.mkdir") and a[-1] is not None and isinstance(a[-1], int) else ps
            if ev in ("shutil.copyfile", "shutil.copytree") and ps:
                ps = ps[-1:]  # (src, dst): only the destination is written
            if ps: _w(ev + "\t" + "\t".join(os.path.abspath(x) for x in ps))
        elif ev == "socket.connect":
            _w("connect\t" + repr(a[1]))
    except Exception:
        pass
if _LOG: sys.addaudithook(_hook)
'''


def m3_t(app):
    before = snapshot(app)
    work = Path(tempfile.mkdtemp(prefix="k01r6_run_"))
    tmpd, site, cwd = work / "tmp", work / "site", work / "cwd"
    for d in (tmpd, site, cwd):
        d.mkdir()
    (site / "sitecustomize.py").write_text(SITE, encoding="utf-8")
    wlog = work / "writes.log"
    env = dict(os.environ, TMPDIR=str(tmpd), TEMP=str(tmpd), TMP=str(tmpd), PYTHONPATH=str(site), K01_WLOG=str(wlog))
    t0 = time.time()
    r = subprocess.run([sys.executable, str(app / "tools/check_all.py"), "--log", str(work / "check_all.json")],
                       capture_output=True, text=True, encoding="utf-8", cwd=cwd, env=env)
    log = json.loads((work / "check_all.json").read_text(encoding="utf-8")) if (work / "check_all.json").exists() else {}
    fails = [x for x in log.get("results", []) if x["status"] == "FAIL"]
    skips = [x["check"] + " — " + x["detail"] for x in log.get("results", []) if x["status"] == "skip"]
    rec("M3", "PASS" if r.returncode == 0 and log and not fails else "FAIL",
        f"check_all.py from foreign cwd: exit {r.returncode}; {log.get('passed')} pass, {log.get('skipped')} skip, {log.get('failed')} fail; "
        f"{time.time() - t0:.1f}s", skipped=skips, failed=fails, check_all=log)
    lines = wlog.read_text(encoding="utf-8").splitlines() if wlog.exists() else []
    allow = (str(tmpd) + os.sep, str(work) + os.sep, "/dev/")
    app_s = str(app) + os.sep
    outside, in_app, connects, pyc_out = set(), set(), set(), set()
    for ln in lines:
        kind, *paths = ln.split("\t")
        if kind == "connect":
            connects.add(paths[0]); continue
        for p in paths:
            if p.startswith(app_s):
                if "__pycache__" not in p:
                    in_app.add(kind + " " + p[len(app_s):])
            elif not p.startswith(allow) and p not in (str(tmpd), str(work)):
                (pyc_out if "__pycache__" in p else outside).add(kind + " " + p)
    rec("T1", "PASS" if not outside and not in_app else "FAIL",
        f"{len(lines)} write/fs events; outside TMPDIR+app: {sorted(outside)[:8]}; in app root (non-pycache): {sorted(in_app)[:8]}; "
        f"socket.connect: {sorted(connects)[:3]}; __pycache__ writes outside app (informational): {sorted({x.split(' ',1)[1].split('__pycache__')[0] for x in pyc_out})}")
    left = sorted(str(p.relative_to(tmpd)) for p in tmpd.rglob("*"))
    rec("T2", "PASS" if not left else "FAIL", f"TMPDIR leftovers after run: {left[:10]}")
    after = snapshot(app)
    changed = sorted(k for k in before if after.get(k) != before[k])
    added = sorted(k for k in after if k not in before)
    pyc = [k for k in added if "__pycache__" in k]
    other = [k for k in added if "__pycache__" not in k]
    rec("T3", "PASS" if not changed and not other else "FAIL",
        f"app root after run: changed {changed[:5]}, new non-pycache {other[:5]}, new __pycache__ files {len(pyc)} (informational)")
    for p in app.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-root", type=Path, required=True)
    ap.add_argument("--extract-manifest")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    app = a.app_root.resolve()
    for fn in (lambda: m1(app, a.extract_manifest), lambda: m2(app), lambda: p1(app), lambda: p3(app), lambda: m3_t(app), lambda: p2(app)):
        try:
            fn()
        except Exception as e:
            rec("CRASH", "FAIL", f"{type(e).__name__}: {e}")
    if a.json:
        a.json.write_text(json.dumps({"app_root": str(app), "python": sys.version.split()[0], "results": R}, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    bad = [r["id"] for r in R if r["verdict"] == "FAIL"]
    print("OVERALL", "PASS" if not bad else "FAIL", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
