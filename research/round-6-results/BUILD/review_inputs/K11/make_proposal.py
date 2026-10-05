"""K11 round 5: produce the PROPOSED launch fix on a COPY of prototypes/city-evidence (never on the BUILD itself).

Run from the root of a copy (e.g. after extract_build.py --sha 0bf27de... --out <dir>):  cd <dir> && python make_proposal.py
The result is the source of proposed_launch_fix.patch. A proposal, not a fix applied by BUILD.
"""
from pathlib import Path
A = Path("prototypes/city-evidence")
NL = "\n"

serve = A / "serve.py"
t = serve.read_text(encoding="utf-8")
a1 = "import sys\nfrom pathlib import Path\n"
assert t.count(a1) == 1, "serve.py imports"
t = t.replace(a1, a1 + "\ntry:  # a redirected stdout on Windows uses the ANSI code page (cp1252 has no Cyrillic): never crash on the banner\n"
              "    sys.stdout.reconfigure(errors=\"replace\")\nexcept (AttributeError, ValueError):\n    pass\n")
a2 = '    print(f"Городские данные: http://127.0.0.1:{PORT}/  (Ctrl+C — остановить)")\n    srv.serve_forever()\n'
assert t.count(a2) == 1, "serve.py body"
t = t.replace(a2, '    print(f"Городские данные: http://127.0.0.1:{PORT}/  (Ctrl+C — остановить)", flush=True)\n'
              '    try:\n        srv.serve_forever()\n    except KeyboardInterrupt:\n        print("Остановлено.")\n')
serve.write_text(t, encoding="utf-8", newline=NL)

(A / "run-demo.bat").write_text(
    "@echo off\r\n"
    "rem Windows launcher for the city-evidence demo (stdlib Python only). Usage: run-demo.bat [port]\r\n"
    "setlocal\r\n"
    "cd /d \"%~dp0\"\r\n"
    "set PYTHONUTF8=1\r\n"
    "where py >nul 2>nul\r\n"
    "if %errorlevel%==0 (\r\n"
    "  py -3 serve.py %*\r\n"
    ") else (\r\n"
    "  python serve.py %*\r\n"
    ")\r\n", encoding="ascii", newline="")

smoke = A / "tests" / "smoke.cjs"
t = smoke.read_text(encoding="utf-8")
for a, b in [
    ('const fs = require("fs");\nconst out = process.argv[2] || path.join(__dirname, "..", "..", "..", "research", "round-4-results", "BUILD", "smoke");',
     'const fs = require("fs");\nconst { pathToFileURL } = require("url");\nconst out = process.argv[2] || path.join(__dirname, "_smoke_out");'),
    ('const url = "file://" + path.resolve(__dirname, "..", "web", "index.html");',
     'const url = pathToFileURL(path.resolve(__dirname, "..", "web", "index.html")).href;'),
    ('await p2.goto("file://" + path.join(dir, "index.html"));',
     'await p2.goto(pathToFileURL(path.join(dir, "index.html")).href);'),
]:
    assert t.count(a) == 1, a[:60]
    t = t.replace(a, b)
smoke.write_text(t, encoding="utf-8", newline=NL)

readme = A / "README.md"
t = readme.read_text(encoding="utf-8")
anchor = "# или открыть web/index.html в браузере (file:// тоже работает)\n```\n"
assert t.count(anchor) == 1, "readme anchor"
t = t.replace(anchor, anchor + "\nWindows (cmd) — **не проверено на Windows**; команда подготовлена по Linux-проверке и моделированию:\n\n"
              "```\ncd prototypes\\city-evidence\nrun-demo.bat\n```\n\nили `py -3 serve.py`, затем http://127.0.0.1:8765/.\n")
b = "скриншоты → research/round-4-results/BUILD/smoke/"
assert t.count(b) == 1, "readme smoke line"
t = t.replace(b, "скриншоты → tests/_smoke_out/ (или каталог из первого аргумента)")
readme.write_text(t, encoding="utf-8", newline=NL)
print("edited")
