"""R15: QR-паспорт объекта (волна 2 п. 6, владелец R12) — подмена ссылки, лишние данные, DOM-XSS.

- /?report=<id>: id проверяется строгим правилом (как на сервере); HTML/javascript:/хвосты ссылки — не id.
- Лист печати web/civic/qr/print.html: без встроенных скриптов (CSP R01); в QR — только адрес сайта и ?report=<id>.
- Подмена: адрес сайта на табличке берётся из ?base= ссылки. Подменённая ссылка, присланная сотруднику, печатает
  таблички, ведущие на чужой сайт, — страница должна заметно предупредить (S25).
Браузерная проверка — Node + Playwright (как в тестах R12); нет Node/Playwright — skip.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

import pytest

from r15_common import ROOT, xfail

REPORT_JS = ROOT / "web" / "civic" / "qr" / "report.js"
PRINT_HTML = ROOT / "web" / "civic" / "qr" / "print.html"
NODE = shutil.which("node")


def node(script, timeout=90):
    env = dict(os.environ)
    env.setdefault("NODE_PATH", subprocess.run([NODE, "-e", "process.stdout.write(require('path').join(process.execPath,'..','..','lib','node_modules'))"],
                                               capture_output=True, text=True).stdout)
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=timeout, env=env, cwd=str(ROOT))
    assert done.returncode == 0, done.stderr[-1500:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture()
def report_js():
    if not REPORT_JS.is_file():
        pytest.skip("в этой сборке нет web/civic/qr/report.js (R12, волна 2 п. 6)")
    if not NODE:
        pytest.skip("нет node")
    return REPORT_JS


@pytest.mark.parametrize("search", ["?report=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E", "?report=javascript:alert(1)",
                                    "?report=osm-node-1%26next%3Dhttps%3A%2F%2Fevil.example", "?report=..%2F..%2Fetc",
                                    "?report=osm-node-1%22%3E%3Cscript%3E", "?report=" + "9" * 400])
def test_report_link_accepts_only_target_ids(report_js, search):
    got = node("const R=require(%s);console.log(JSON.stringify(R.parseReportId(%s)))" % (json.dumps(str(report_js)), json.dumps(search)))
    assert got is None, (search, got)


def test_report_link_keeps_plain_ids(report_js):
    got = node("const R=require(%s);console.log(JSON.stringify(['?report=osm-node-123','?x=1&report=cell-239-232#f']"
               ".map(R.parseReportId)))" % json.dumps(str(report_js)))
    assert got == ["osm-node-123", "cell-239-232"]


def test_print_page_has_no_inline_scripts_or_external_hosts():
    if not PRINT_HTML.is_file():
        pytest.skip("в этой сборке нет web/civic/qr/print.html")
    html = PRINT_HTML.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html), "встроенный скрипт сломается под CSP R01"
    assert not re.search(r"""(src|href)=["']https?://""", html), "скрипты/стили только со своего сервера"
    assert not re.search(r"<[^>]+\son[a-z]+\s*=", re.sub(r"<!--.*?-->", "", html, flags=re.S)), "обработчик в атрибуте"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def static_web():
    """Статика web/ этой сборки на 127.0.0.1 (API нет — объекты «не найдены», для проверки адреса это не важно)."""
    if not PRINT_HTML.is_file():
        pytest.skip("в этой сборке нет web/civic/qr/print.html")
    if not NODE or subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True,
                                  env={**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "/opt/node22/lib/node_modules")}).returncode:
        pytest.skip("нет node/playwright")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                             "--directory", str(ROOT / "web")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield "http://127.0.0.1:%d" % port
    proc.terminate()
    proc.wait(timeout=5)


def _print_page(base_url, query):
    script = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto(%s, { waitUntil: 'load' }); await p.waitForTimeout(1500);
  const out = await p.evaluate(() => ({ base: (document.querySelector('#bqp-base') || {}).value || null,
    warn: [...document.querySelectorAll('.bqp-msg--warn, .bqp-msg--error')].map(e => e.textContent) }));
  console.log(JSON.stringify(out)); await b.close();
})().catch(e => { console.error(e); process.exit(1); });
""" % json.dumps(base_url + "/civic/qr/print.html" + query)
    return node(script, timeout=120)


@xfail("S25")
def test_foreign_site_in_print_link_is_flagged(static_web):
    """?base=https://evil.example: страница молча подставляет чужой сайт в QR всех табличек."""
    got = _print_page(static_web, "?ids=osm-node-10272524280&base=" + "https%3A%2F%2Fbirge-astana.example")
    assert got["base"] == "https://birge-astana.example", got   # параметр по-прежнему работает (печать для домена)
    assert any("birge-astana.example" in text for text in got["warn"]), got


def test_print_page_defaults_to_this_server(static_web):
    got = _print_page(static_web, "?ids=osm-node-10272524280")
    assert got["base"] == static_web, got
    assert not any(static_web.split("//")[1] in text for text in got["warn"]), got
