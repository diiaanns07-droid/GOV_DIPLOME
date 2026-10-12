"""R15: сторож для стиля «стекло» (FINAL-3, Apple Liquid Glass: R11 GLASS.md, .bk-glass; R01/R07/R08/R09 — свои панели).

Стекло — только CSS (backdrop-filter, полупрозрачный белый, тень, радиусы); безопасность оно менять не должно. Риски
смены стиля, которые ловят тесты:
1. CSP страниц не ослаблена: ни внешних шрифтов (Google Fonts, Apple CDN), ни «*»/«https:» — только свой сайт и подложка
   карты (S01). Внешний шрифт ещё и отдаёт адрес каждого жителя чужому сервису.
2. Стили и страницы не тянут ничего с чужих сайтов: @import, url(http…), <link>/<script>/<img>/<iframe> с внешним
   адресом; нет исполняемого CSS (expression(), behavior:, -moz-binding).
Проверяется сборка R15_ROOT (по умолчанию — этот репозиторий). Нет страницы в сборке — она пропускается.
"""

from __future__ import annotations

import re

import pytest

from r15_common import ROOT, live_server, request

PAGES = ["/", "/civic/akim/index.html", "/civic/ui-kit/index.html", "/civic/akim/services.html",
         "/civic/nearby/index.html", "/civic/qr/print.html?ids=osm-node-1", "/civic/qa/index.html"]
TILES = "https://tiles.openfreemap.org"
ALLOWED = {"'self'", "'none'", "data:", "blob:", TILES}
INLINE_OK = {"style-src"}          # MapLibre и модули ставят style="" (S01: риск много ниже скриптов)

EXTERNAL_CSS = re.compile(r"@import|url\(\s*[\"']?\s*(?:https?:)?//|expression\s*\(|-moz-binding|(?:^|[\s;{])behavior\s*:",
                          re.I)
EXTERNAL_TAG = re.compile(r"<(?:link|script|img|iframe|source|video|audio)\b[^>]*\b(?:href|src|srcset)\s*=\s*[\"']?\s*"
                          r"(?:https?:)?//", re.I)
SKIP_DIRS = {"node_modules", "vendor", "__pycache__"}


def _files(pattern):
    web = ROOT / "web"
    if not web.is_dir():
        pytest.skip("в этой сборке нет web/")
    return [p for p in web.rglob(pattern) if not SKIP_DIRS & set(p.relative_to(web).parts)]


@pytest.fixture(scope="module")
def csp_by_page(tmp_path_factory):
    out = {}
    with live_server(tmp_path_factory.mktemp("glass")) as srv:
        for page in PAGES:
            status, headers, _ = request(srv, "GET", page)
            if status == 200:
                out[page] = headers.get("content-security-policy", "")
    return out


@pytest.mark.parametrize("page", PAGES)
def test_page_csp_allows_only_own_site_and_map_tiles(csp_by_page, page):
    if page not in csp_by_page:
        pytest.skip(f"страницы {page} нет в этой сборке")
    csp = csp_by_page[page]
    if "script-src" not in csp:
        pytest.skip("в этой сборке нет строгой CSP (S01) — это проверяет test_r15_server.py")
    assert "object-src 'none'" in csp, csp
    wrong = []
    for part in filter(None, (p.strip() for p in csp.split(";"))):
        name, *sources = part.split()
        for src in sources:
            if src in ALLOWED or src.startswith("'sha256-") or (src == "'unsafe-inline'" and name in INLINE_OK):
                continue
            wrong.append(f"{name} {src}")
    assert not wrong, f"CSP {page} ослаблена: " + ", ".join(wrong)


def test_styles_load_nothing_from_other_sites():
    hits = [f"{p.relative_to(ROOT)}:{n}: {line.strip()[:120]}"
            for p in _files("*.css") for n, line in enumerate(p.read_text("utf-8", "replace").splitlines(), 1)
            if EXTERNAL_CSS.search(line)]
    assert not hits, "CSS тянет внешнее или исполняемое:\n" + "\n".join(hits)


def test_pages_link_nothing_from_other_sites():
    hits = []
    for p in _files("*.html"):
        text = p.read_text("utf-8", "replace")
        hits += [f"{p.relative_to(ROOT)}: {m.group(0)[:120]}" for m in EXTERNAL_TAG.finditer(text)]
        hits += [f"{p.relative_to(ROOT)} <style>: {m.group(0)}" for m in EXTERNAL_CSS.finditer(text)
                 if m.group(0).lower().startswith(("@import", "url"))]
    assert not hits, "страница загружает ресурс с чужого сайта:\n" + "\n".join(hits)
