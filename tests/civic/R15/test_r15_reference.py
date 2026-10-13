"""R15: безопасность экранов «по эталону A + качество Linear» (research/round-14/design/README.md, 13 окт).

Эталон выводит на экраны чужой текст (цитата жалобы, идеи, вопросы, горячие места) и добавляет поиск с подсказками,
Ctrl+K, статус-иконки и шрифт Inter. Что держат тесты:
1. Шрифты в web/ — только сверенные R15 файлы: Inter 4.0 из Debian fonts-inter 4.0+ds-1, подмножество командой из
   web/civic/ui-kit/fonts/SOURCE.txt (R15 повторил её: fonttools 4.66.1 + brotli — sha256 совпали байт в байт).
   Шрифт с чужого сайта ловят CSP и test_r15_glass.py; здесь — подмена или новый файл без сверки.
2. Помощники ui-kit, которые возвращают HTML-строку для innerHTML (BirgeUI.icon, statusIcon, illustration), не
   пропускают разметку ни через один аргумент (S41: размер в statusIcon).
Экраны целиком (нагрузка во всех полях эталона, акимат 1366 и житель 375) — browser/r15_reference.cjs.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess

import pytest

from r15_common import ROOT, xfail

# sha256 подмножеств Inter 4.0 (R15 повторил сборку R11 из /usr/share/fonts/opentype/inter, 13 окт).
FONTS = {
    "civic/ui-kit/fonts/Inter-Regular.woff2": "47548ae8bd2ec9b3931e7f7f2e10e5f067c014db77b95c3aee20d3540f023a9d",
    "civic/ui-kit/fonts/Inter-Medium.woff2": "ddebf8e00f319dd19cac98a64dd00865a569f3ee32910bacd09f883102724d40",
    "civic/ui-kit/fonts/Inter-SemiBold.woff2": "1aa7be2efc99de93e7f09e03ffcf676ed469411acaf4f14a3afa93aa743a9d1d",
    "civic/ui-kit/fonts/Inter-Bold.woff2": "d363b8a6383d809c0075784e2f7f7c0437d68f036c2bdbb1328e963461cc7b1e",
}
FONT_EXT = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
BAD = '"><img src=x onerror=alert(1)>'

PROBE = r"""
const vm = require("vm"), fs = require("fs");
const self = {}; vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), { self });
const U = self.BirgeUI || {}, bad = process.argv[2], out = {};
const calls = { "icon(name)": ["icon", [bad]], "statusIcon(status)": ["statusIcon", [bad]],
  "statusIcon(status, size)": ["statusIcon", ["new", bad]], "illustration(name)": ["illustration", [bad]] };
for (const [label, [fn, args]] of Object.entries(calls)) if (typeof U[fn] === "function") out[label] = String(U[fn](...args));
console.log(JSON.stringify(out));
"""


def test_fonts_are_the_checked_inter_subsets():
    web = ROOT / "web"
    if not web.is_dir():
        pytest.skip("в этой сборке нет web/")
    wrong = []
    for path in sorted(p for p in web.rglob("*") if p.is_file() and p.suffix.lower() in FONT_EXT):
        rel = path.relative_to(web).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if FONTS.get(rel) != digest:
            wrong.append(f"{rel} sha256 {digest[:16]}… — {'новый файл' if rel not in FONTS else 'изменён'}")
    assert not wrong, ("шрифт не сверен R15 (повторить сборку по SOURCE.txt и дописать sha256 сюда):\n"
                       + "\n".join(wrong))


@pytest.fixture(scope="module")
def ui_kit_html():
    script = ROOT / "web" / "civic" / "ui-kit" / "ui-kit.js"
    node = shutil.which("node")
    if not script.is_file() or not node:
        pytest.skip("нет ui-kit.js или node")
    run = subprocess.run([node, "-e", PROBE, str(script), BAD], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr[-500:]
    return json.loads(run.stdout)


@pytest.mark.parametrize("call", ["icon(name)", "statusIcon(status)", "illustration(name)"])
def test_ui_kit_html_helpers_escape_data(ui_kit_html, call):
    if call not in ui_kit_html:
        pytest.skip(f"BirgeUI.{call} нет в этой сборке")
    assert "<img" not in ui_kit_html[call], (call, ui_kit_html[call])


@xfail("S41")
def test_status_icon_size_cannot_carry_markup(ui_kit_html):
    call = "statusIcon(status, size)"
    if call not in ui_kit_html:
        pytest.skip("BirgeUI.statusIcon нет в этой сборке")
    assert "<img" not in ui_kit_html[call], ui_kit_html[call]
