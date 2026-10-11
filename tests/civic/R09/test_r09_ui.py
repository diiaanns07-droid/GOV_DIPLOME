"""CP5: UI CivicAssistant — статические правила и проверка в реальном Chromium (Playwright).

Браузерный прогон требует node + playwright + chromium; без них тест помечается skip
(в отчёте это NOT_RUN, а не PASS).
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
JS = (ROOT / "web/civic/assistant/assistant.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/civic/assistant/assistant.css").read_text(encoding="utf-8")


def test_no_html_sinks_or_globals_in_component():
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", JS, flags=re.S)
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function",
                 "document.body", "localStorage", "sessionStorage"):
        assert sink not in code, sink
    assert "global.CivicAssistant = Object.assign" in code
    assert re.findall(r"window\.\w+\s*=", code) == []


def test_component_request_body_has_no_facts():
    m = re.search(r'api\.request\("POST", "/assistant", (\{[^}]*\})', JS)
    assert m and set(re.findall(r"(\w+):", m.group(1))) == {"question", "object_id", "scenario_id", "revision"}
    assert "revision: objectId ? revision : null" in m.group(1)  # редакция — только вместе с объектом


def test_css_is_prefixed():
    selectors = re.findall(r"(^|})\s*([^{}@]+)\{", CSS)
    for _, sel in selectors:
        for part in sel.split(","):
            part = part.strip()
            if part and not part.startswith(":root"):
                assert ".civic-r09" in part, part


def _node_ready():
    if not shutil.which("node"):
        return False
    probe = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True,
                           env={**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "/opt/node22/lib/node_modules")})
    return probe.returncode == 0


@pytest.mark.skipif(not _node_ready(), reason="NOT_RUN: node/playwright недоступны")
def test_ui_in_real_chromium(tmp_path):
    srv = subprocess.Popen([sys.executable, str(HERE / "demo_server.py"), "0"], stdout=subprocess.PIPE, text=True)
    try:
        line = srv.stdout.readline().strip()
        assert line.startswith("READY "), line
        port = int(line.split()[1])
        shots = Path(os.environ.get("R09_SCREENSHOT_DIR", tmp_path))
        out = subprocess.run(["node", str(HERE / "ui_check.cjs"), f"http://127.0.0.1:{port}", str(shots)],
                             capture_output=True, text=True, timeout=240,
                             env={**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "/opt/node22/lib/node_modules")})
        report = json.loads(out.stdout.strip().splitlines()[-1])
        failed = [c for c in report["checks"] if c["status"] != "PASS"]
        assert not failed, failed
        assert len(report["checks"]) >= 15
        (tmp_path / "ui_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    finally:
        srv.terminate()
        srv.wait(timeout=10)
        time.sleep(0.1)
