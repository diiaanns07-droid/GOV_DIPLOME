"""R15 раунд 15 · CSP новых страниц и экранов (THREATS_R15 P10, T-R08-01, T-R12-01, T-R03-08).

Новые HTML-страницы раунда 15 (Ситуационный центр R08 web/civic/board/, стенды R17/R03 и др.) и модули экранов:
- в HTML нет обработчиков on…= и ссылок javascript:, нет внешних скриптов, стилей и шрифтов (CSP шлюза их не пустит,
  а с интернетом на ноутбуке они бы утекали адресом зрителя);
- в JS экранов нет eval / new Function / document.write и строковых таймеров (CSP без 'unsafe-eval');
- страница, которую шлюз уже отдаёт (ASSETS), приходит со строгой CSP: script-src 'self' без 'unsafe-inline'/'unsafe-eval',
  frame-ancestors 'none', object-src 'none'.
Нет новых страниц в сборке — NOT_RUN.
"""

from __future__ import annotations

import re

import pytest

from r15_common import ROOT, live_server, need_module, request
from r15_round15 import not_run

SECTIONS = ("board", "agencies", "meetings", "assistant", "works-calendar", "together", "notify")
HTML = sorted(p for s in SECTIONS for p in (ROOT / "web" / "civic" / s).glob("*.html")) \
    if (ROOT / "web" / "civic").is_dir() else []
JS = sorted(p for s in SECTIONS for p in (ROOT / "web" / "civic" / s).glob("*.js")) \
    if (ROOT / "web" / "civic").is_dir() else []
ON_HANDLER = re.compile(r"<[^>]+\son[a-z]{3,}\s*=", re.I)
EXTERNAL = re.compile(r"""<(?:script|link|img|iframe)[^>]+(?:src|href)\s*=\s*["']?(?:https?:)?//""", re.I)
UNSAFE_JS = re.compile(r"\beval\s*\(|\bnew\s+Function\s*\(|document\.write\s*\(|set(?:Timeout|Interval)\s*\(\s*[\"'`]")


def _rel(path):
    return str(path.relative_to(ROOT))


@pytest.mark.parametrize("page", HTML or [None], ids=[_rel(p) for p in HTML] or ["нет страниц"])
def test_new_html_pages_have_no_inline_handlers_or_external_resources(page):
    if page is None:
        not_run("в сборке нет новых HTML-страниц раунда 15")
    text = page.read_text(encoding="utf-8")
    assert not ON_HANDLER.search(text), f"{_rel(page)}: обработчик on…= в разметке"
    assert "javascript:" not in text.lower(), f"{_rel(page)}: ссылка javascript:"
    assert not EXTERNAL.search(text), f"{_rel(page)}: внешний ресурс: {EXTERNAL.search(text).group(0)[:80]}"


@pytest.mark.parametrize("script", JS or [None], ids=[_rel(p) for p in JS] or ["нет экранов"])
def test_new_screens_need_no_unsafe_eval(script):
    if script is None:
        not_run("в сборке нет новых экранов раунда 15")
    code = re.sub(r"/\*.*?\*/|(?<![:\"'\\])//[^\n]*", "", script.read_text(encoding="utf-8"), flags=re.S)
    found = UNSAFE_JS.search(code)
    assert not found, f"{_rel(script)}: {found.group(0)}"


@pytest.fixture(scope="module")
def served_pages(tmp_path_factory):
    ws = need_module("ui.web_server")
    pages = [p for p in ws.ASSETS if p.endswith(".html") and any(f"/civic/{s}/" in p for s in SECTIONS)]
    if not pages:
        not_run("шлюз ещё не отдаёт новых страниц раунда 15 (CIVIC_ASSETS R01)")
    return pages


def test_served_new_pages_have_strict_csp(served_pages, tmp_path):
    with live_server(tmp_path) as srv:
        for page in served_pages:
            status, headers, _body = request(srv, "GET", page)
            assert status == 200, page
            csp = headers.get("content-security-policy") or ""
            script = next((d for d in csp.split(";") if d.strip().startswith("script-src")), "")
            assert "'self'" in script and "unsafe-inline" not in script and "unsafe-eval" not in script, (page, csp)
            assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp, (page, csp)
