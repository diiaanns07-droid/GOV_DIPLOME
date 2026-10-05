"""K11 round 5: launch smoke test for the city-evidence demo (BUILD), stdlib only.

Re-runnable on any copy of the BUILD:
    python k11_demo_smoke.py --app-root <path>/prototypes/city-evidence [--out report.json] [--browser]
    python k11_demo_smoke.py --url http://127.0.0.1:8765/ [--out report.json] [--browser]

--app-root: static checks of the copy, then starts `<python> serve.py <free port>` itself, runs HTTP checks
            against http://127.0.0.1:<port>/ and stops exactly that process (Ctrl+C equivalent first, then
            terminate, then kill), verifying it exited and the port is closed.
--url:      HTTP checks only against an already running server (nothing is started or stopped).
--browser:  optional headless check through Node + Playwright (needs `require("playwright")` to resolve,
            e.g. NODE_PATH=$(npm root -g)); otherwise reported as not_run.

Status per check: pass | fail | modeled_pass | modeled_fail | not_run | info.
"modeled_*" = Windows behaviour reproduced on another OS (encoding of a redirected stdout, Windows path
semantics); it is NOT a run on Windows. Exit code 1 if any fail or modeled_fail.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

TEXT_EXT = {".html", ".js", ".cjs", ".py", ".json", ".md", ".txt", ".css", ".bat", ".cmd", ".ps1", ".geojson"}
ABS_PATH_RE = re.compile(r"(?<![\w.])(/tmp/|/home/\w|/root/|/mnt/|/opt/\w|[A-Za-z]:\\\\?[A-Za-z])")
CHECKS: list[dict] = []
STATE: dict = {}  # facts shared between checks (e.g. S4 -> M3)


def check(cid, status, title, detail=None):
    CHECKS.append({"id": cid, "status": status, "title": title, "detail": detail})
    return status


# ---------------------------------------------------------------- HTTP helpers
class Refs(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.links, self.meta_charset, self.module_scripts = [], [], None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
            if (a.get("type") or "").lower() == "module":
                self.module_scripts.append(a["src"])
        if tag == "link" and a.get("href"):
            self.links.append(a["href"])
        if tag == "meta" and a.get("charset"):
            self.meta_charset = a["charset"].lower()


def get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "k11-demo-smoke"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def raw_get(host, port, path, timeout=5):
    """GET with a path sent verbatim (urllib would normalise ../)."""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("ascii"))
        buf = b""
        while chunk := s.recv(65536):
            buf += chunk
    head, _, body = buf.partition(b"\r\n\r\n")
    return int(head.split()[1]), body


def http_checks(base, app_root=None):
    if not base.endswith("/"):
        base += "/"
    status, headers, body = get(base)
    if check("H1", "pass" if status == 200 else "fail", "GET / returns the start page", {"status": status}) != "pass":
        return
    ctype = headers.get("content-type", "")
    try:
        text = body.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError as e:
        text, utf8 = body.decode("utf-8", "replace"), False
    refs = Refs()
    refs.feed(text)
    check("H2", "pass" if utf8 and refs.meta_charset == "utf-8" else "fail",
          "start page is valid UTF-8 and declares <meta charset=utf-8>",
          {"content_type": ctype, "meta_charset": refs.meta_charset, "strict_utf8": utf8})
    check("H3", "info", "Content-Type headers carry a charset (browser otherwise relies on <meta charset>)",
          {"/": ctype})
    external = [u for u in refs.scripts + refs.links if urllib.parse.urlsplit(u).scheme in ("http", "https", "file")
                or u.startswith("//")]
    check("H4", "pass" if not external else "fail", "start page loads no external or file:// resources", external)
    check("H5", "pass" if not refs.module_scripts else "fail",
          "no type=module scripts (they need correct JS MIME and do not run from file://)", refs.module_scripts)
    res = {}
    for src in refs.scripts + [h for h in refs.links if h.endswith(".css")]:
        st, hd, b = get(urllib.parse.urljoin(base, src))
        row = {"status": st, "content_type": hd.get("content-type"), "bytes": len(b)}
        try:
            b.decode("utf-8")
            row["strict_utf8"] = True
        except UnicodeDecodeError:
            row["strict_utf8"] = False
        row["bom"] = b.startswith(b"\xef\xbb\xbf")
        if app_root:
            disk = Path(app_root) / "web" / urllib.parse.unquote(src)
            row["same_bytes_as_disk"] = disk.is_file() and hashlib.sha256(disk.read_bytes()).hexdigest() == \
                hashlib.sha256(b).hexdigest()
        res[src] = row
    ok = res and all(r["status"] == 200 and r["strict_utf8"] and r.get("same_bytes_as_disk", True)
                     and "javascript" in (r["content_type"] or "") for r in res.values() if r is not None)
    check("H6", "pass" if ok else "fail", "every referenced script is served 200, JS MIME, strict UTF-8, same bytes as disk", res)
    st404, _, _ = get(urllib.parse.urljoin(base, "__k11_missing__.js"))
    check("H7", "pass" if st404 == 404 else "fail", "missing file returns 404", {"status": st404})
    u = urllib.parse.urlsplit(base)
    if u.hostname in ("127.0.0.1", "localhost"):
        leaks = {}
        for p in ("/../serve.py", "/%2e%2e/serve.py", "/..%2fserve.py", "/../README.md"):
            st, b = raw_get(u.hostname, u.port or 80, p)
            leaks[p] = {"status": st, "leaked_serve_py": b"http.server" in b and b"serve_forever" in b,
                        "leaked_readme": b"# " in b[:200] and b"<html" not in b[:200].lower()}
        bad = [p for p, r in leaks.items() if r["leaked_serve_py"] or (p.endswith("README.md") and r["status"] == 200)]
        check("H8", "pass" if not bad else "fail", "files outside web/ are not served (path traversal)", leaks)


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET, no packet is sent for UDP connect
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------- server lifecycle
def launch_and_test(app_root, python, browser):
    serve = Path(app_root) / "serve.py"
    if not serve.is_file():
        check("L1", "fail", "serve.py exists", str(serve))
        return
    port = free_port()
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    kw = {"start_new_session": True} if os.name == "posix" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    t0 = time.monotonic()
    proc = subprocess.Popen([python, str(serve), str(port)], cwd=str(Path(app_root)), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    ready = False
    while time.monotonic() - t0 < 15 and proc.poll() is None:
        if port_open("127.0.0.1", port):
            ready = True
            break
        time.sleep(0.1)
    check("L1", "pass" if ready else "fail", "serve.py starts and listens on 127.0.0.1:<port> (port from argv)",
          {"port": port, "seconds": round(time.monotonic() - t0, 2), "exited_early": proc.poll()})
    try:
        if ready:
            base = f"http://127.0.0.1:{port}/"
            http_checks(base, app_root)
            ip = lan_ip()
            if ip:
                exposed = port_open(ip, port)
                check("H9", "fail" if exposed else "pass", "server is not reachable on the LAN address (loopback only)",
                      {"lan_ip": ip, "reachable": exposed})
            else:
                check("H9", "not_run", "server is not reachable on the LAN address (loopback only)", "no non-loopback IPv4")
            if browser:
                browser_check(base, app_root)
    finally:
        stop = stop_process(proc)
        out, err = stop.pop("_streams")
        check("L2", "pass" if stop["exited"] and not port_open("127.0.0.1", port) else "fail",
              "the launched server process is stopped explicitly and the port is released", stop)
        tb = "Traceback" in err
        check("L3", "info", "server output on start/stop",
              {"stdout_first_line": out.splitlines()[0] if out else "", "stderr_has_traceback": tb,
               "stderr_tail": err.strip().splitlines()[-1:] if err.strip() else []})


def stop_process(proc):
    """Ctrl+C equivalent first (POSIX SIGINT to the process group), then terminate, then kill."""
    steps = []
    if proc.poll() is None and os.name == "posix":
        os.killpg(proc.pid, signal.SIGINT)
        steps.append("SIGINT(process group)")
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            pass
    if proc.poll() is None:
        proc.terminate()
        steps.append("terminate")
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            pass
    if proc.poll() is None:
        proc.kill()
        steps.append("kill")
        proc.wait(5)
    out, err = proc.communicate(timeout=5)
    return {"steps": steps, "returncode": proc.returncode, "exited": proc.poll() is not None,
            "_streams": (out.decode("utf-8", "replace"), err.decode("utf-8", "replace"))}


# ---------------------------------------------------------------- static checks of the copy
def static_checks(app_root):
    root = Path(app_root)
    need = ["serve.py", "README.md", "web/index.html", "web/app.js", "web/data.js", "web/evidence.js", "web/facts.js"]
    missing = [p for p in need if not (root / p).is_file()]
    check("S1", "pass" if not missing else "fail", "start page, server and documentation files exist", {"missing": missing})

    own = [p for p in root.rglob("*") if p.is_file() and "inputs" not in p.relative_to(root).parts
           and p.suffix.lower() in TEXT_EXT]
    bad_utf8, bom, crlf = [], [], []
    for p in own:
        b = p.read_bytes()
        try:
            b.decode("utf-8")
        except UnicodeDecodeError as e:
            bad_utf8.append(f"{p.relative_to(root).as_posix()}: {e}")
        if b.startswith(b"\xef\xbb\xbf"):
            bom.append(p.relative_to(root).as_posix())
        if b"\r\n" in b:
            crlf.append(p.relative_to(root).as_posix())
    check("S2", "pass" if not bad_utf8 else "fail", "all own text files (outside inputs/) are strict UTF-8",
          {"files": len(own), "invalid": bad_utf8, "bom": bom, "crlf": crlf})

    hits = []
    for p in own:
        if p.suffix.lower() in (".json", ".geojson") or p.name in ("data.js", "evidence.js"):
            continue  # generated data; scanned separately below
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if ABS_PATH_RE.search(line):
                hits.append(f"{p.relative_to(root).as_posix()}:{i}: {line.strip()[:140]}")
    for name in ("web/data.js", "web/evidence.js", "web/facts.js", "web/app.js"):
        p = root / name
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"(/tmp/|/home/\w+|/root/|[A-Za-z]:\\\\)[^\"'\s]{0,60}", t):
                hits.append(f"{name}: …{m.group(0)}")
    check("S3", "pass" if not hits else "fail", "no hidden absolute paths in code, docs and generated web files", hits)

    file_url = {}
    for p in sorted((root / "tests").glob("*.cjs")) + sorted((root / "tests").glob("*.js")):
        t = p.read_text(encoding="utf-8", errors="replace")
        concat = [f"L{i}: {l.strip()[:120]}" for i, l in enumerate(t.splitlines(), 1)
                  if re.search(r"""["'`]file://["'`]?\s*\+|`file://\$\{""", l)]
        file_url[p.name] = {"string_concatenation": concat, "uses_pathToFileURL": "pathToFileURL" in t}
    bad = {k: v for k, v in file_url.items() if v["string_concatenation"]}
    STATE["file_url_concat"] = {k: v["string_concatenation"] for k, v in bad.items()}
    check("S4", "pass" if not bad else "fail",
          "Node tests build file:// URLs with url.pathToFileURL, not string concatenation", file_url or "no Node tests")

    launchers = sorted(p.name for p in root.iterdir() if p.is_file() and p.suffix.lower() in (".bat", ".cmd", ".ps1"))
    check("S5", "pass" if launchers else "fail", "a Windows launcher (.bat/.cmd/.ps1) exists next to serve.py", launchers)

    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace") if (root / "README.md").is_file() else ""
    # a command line (not prose) that starts the demo on Windows; run.bat is the main hackathon site
    win_cmd = [l.strip() for l in re.findall(
        r"(?im)^\s*(?:[>$]\s*)?(?:\.\\)?(?:[\w-]+\.(?:bat|cmd|ps1)|py(?:\s+-3[\w.]*)?\s+serve\.py|python\s+serve\.py)\b.*$",
        readme) if not re.match(r"\s*(?:[>$]\s*)?(?:\.\\)?run\.bat\b", l)]
    check("S6", "pass" if win_cmd else "fail", "README gives a Windows start command (launcher, `py serve.py` or `python serve.py`)",
          win_cmd[:5])

    py_issues = []
    for p in [root / "serve.py"] + sorted((root / "tools").glob("*.py")) + sorted((root / "tests").glob("*.py")):
        if not p.is_file():
            continue
        for i, l in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(r"\b(read_text|write_text)\(\s*\)", l) or (
                    re.search(r"(?<![\w.])open\(", l) and "encoding" not in l and not re.search(r"""["']\w*b\w*["']""", l)):
                py_issues.append(f"{p.relative_to(root).as_posix()}:{i}: {l.strip()[:120]}")
    check("S7", "pass" if not py_issues else "fail",
          "Python text I/O names an encoding (Windows default is the ANSI code page)", py_issues)

    smoke = root / "tests" / "smoke.cjs"
    if smoke.is_file():
        t = smoke.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"process\.argv\[2\]\s*\|\|\s*([^;\n]+)", t)
        outside = bool(m and re.search(r"""["']\.\.["']\s*,\s*["']\.\.["']""", m.group(1)))
        check("S8", "fail" if outside else "pass",
              "browser smoke writes its default output inside the app copy (not into ../../../research)",
              m.group(1).strip()[:160] if m else "no default output found")


# ---------------------------------------------------------------- modeled Windows checks
def modeled_windows(app_root, python):
    serve = Path(app_root) / "serve.py"
    if not serve.is_file():
        return
    for enc, cid in (("cp1251", "M1"), ("cp1252", "M2")):
        port = free_port()
        env = dict(os.environ, PYTHONIOENCODING=enc, PYTHONUNBUFFERED="1")
        kw = {"start_new_session": True} if os.name == "posix" else {}
        proc = subprocess.Popen([python, str(serve), str(port)], cwd=str(serve.parent), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
        t0, up = time.monotonic(), False
        while time.monotonic() - t0 < 8 and proc.poll() is None:
            if port_open("127.0.0.1", port):
                up = True
                break
            time.sleep(0.1)
        early = proc.poll()
        stop = stop_process(proc)
        _, err = stop.pop("_streams")
        last = err.strip().splitlines()[-1] if err.strip() else ""
        check(cid, "modeled_pass" if up else "modeled_fail",
              f"serve.py starts with a redirected stdout encoded as {enc} (Windows ANSI code page, MODELED on {platform.system()})",
              {"listening": up, "exited_before_listen": early, "stderr_last_line": last[:200]})
    node = shutil.which("node")
    if node:
        js = ("const p=require('path'),u=require('url');const r='C:\\\\Users\\\\u\\\\city-evidence';"
              "const a='file://'+p.win32.resolve(r,'web','index.html');"
              "let b;try{b=u.pathToFileURL(p.win32.join(r,'web','index.html'),{windows:true}).href}catch(e){b='unsupported:'+e.message}"
              "console.log(JSON.stringify({concatenated:a,pathToFileURL:b}))")
        out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=20).stdout.strip()
        try:
            r = json.loads(out)
            concat = STATE.get("file_url_concat", {})
            r["tests_using_concatenation"] = concat
            # the app's own tests decide: concatenation present -> the Windows URL they would build is broken
            broken = bool(concat) and "\\" in r["concatenated"]
            check("M3", "modeled_fail" if broken else "modeled_pass",
                  "file:// URLs of the Node tests are valid for a Windows path (MODELED with path.win32)", r)
        except ValueError:
            check("M3", "not_run", "file:// URL for a Windows path", out[:200])
    else:
        check("M3", "not_run", "file:// URL for a Windows path", "node not found")
    check("W1", "not_run", "real Windows run of the launcher, serve.py and browser", "no Windows host in this environment")


# ---------------------------------------------------------------- optional browser
BROWSER_JS = r"""
const {chromium}=require('playwright');const {pathToFileURL}=require('url');
(async()=>{const urls=JSON.parse(process.argv[2]);const out={};const b=await chromium.launch();
for(const [k,u] of Object.entries(urls)){const pg=await b.newPage();const errs=[];const net=[];
pg.on('pageerror',e=>errs.push(String(e.message)));pg.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
pg.on('request',r=>{const s=r.url();if(!s.startsWith('file:')&&!s.startsWith(urls.http.split('/').slice(0,3).join('/')))net.push(s)});
let ok=true;try{await pg.goto(k==='file'?pathToFileURL(u).href:u,{waitUntil:'load',timeout:20000});}catch(e){ok=false;errs.push('goto: '+e.message)}
const st=ok?await pg.evaluate(()=>({title:document.title,hasData:typeof window.CITY_EVIDENCE==='object',
 cities:window.CITY_EVIDENCE?Object.keys(window.CITY_EVIDENCE.cities||{}):[],bodyText:document.body.innerText.length})):{};
out[k]={loaded:ok,errors:errs,external_requests:net,...st};await pg.close();}
await b.close();console.log(JSON.stringify(out));})().catch(e=>{console.log(JSON.stringify({fatal:String(e)}));process.exit(2)});
"""


def browser_check(base, app_root):
    node = shutil.which("node")
    if not node:
        check("B1", "not_run", "headless browser loads the demo (http and file://)", "node not found")
        return
    urls = {"http": base}
    if app_root:
        urls["file"] = str((Path(app_root) / "web" / "index.html").resolve())
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "k11_browser.cjs"
        script.write_text(BROWSER_JS, encoding="utf-8", newline="\n")
        r = subprocess.run([node, str(script), json.dumps(urls)], capture_output=True, text=True, timeout=120)
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        check("B1", "not_run", "headless browser loads the demo (http and file://)",
              {"reason": "playwright not resolvable or browser failed", "stderr": r.stderr.strip()[-300:]})
        return
    if "fatal" in res:
        check("B1", "not_run", "headless browser loads the demo (http and file://)", res)
        return
    ok = all(v.get("loaded") and v.get("hasData") and not v.get("errors") and not v.get("external_requests")
             and set(v.get("cities", [])) >= {"shymkent", "astana"} for v in res.values())
    over = "http and file:// (pathToFileURL)" if "file" in urls else "http"
    check("B1", "pass" if ok else "fail", f"headless browser loads the demo over {over}, data for both cities, "
          "no console errors, no external requests", res)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root", help="path to a copy of prototypes/city-evidence")
    g.add_argument("--url", help="base URL of an already running demo server")
    ap.add_argument("--python", default=sys.executable, help="interpreter used to start serve.py")
    ap.add_argument("--browser", action="store_true", help="also run a headless Playwright check")
    ap.add_argument("--no-modeled", action="store_true", help="skip modeled Windows checks")
    ap.add_argument("--label", default="", help="free text stored in the report, e.g. the BUILD SHA")
    ap.add_argument("--out", help="write the JSON report here")
    a = ap.parse_args()
    if a.app_root:
        root = str(Path(a.app_root).resolve())
        static_checks(root)
        launch_and_test(root, a.python, a.browser)
        if not a.no_modeled:
            modeled_windows(root, a.python)
    else:
        http_checks(a.url)
        if a.browser:
            browser_check(a.url, None)
    summary = {}
    for c in CHECKS:
        summary[c["status"]] = summary.get(c["status"], 0) + 1
    report = {"tool": "research/round-5-results/K11/k11_demo_smoke.py", "label": a.label,
              "mode": "app-root" if a.app_root else "url", "target": a.app_root or a.url,
              "host": {"os": platform.system(), "release": platform.release(), "python": platform.python_version()},
              "summary": summary, "checks": CHECKS}
    text = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    for c in CHECKS:
        print(f"{c['status']:13} {c['id']:3} {c['title']}")
    print("summary:", json.dumps(summary))
    return 1 if summary.get("fail") or summary.get("modeled_fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
