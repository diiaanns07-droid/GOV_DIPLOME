"""R02 · раунд 14 · файлы страницы разметки: категории сгенерированы из categories_v2.json, нет сети."""

import json
import re
from pathlib import Path

from ml.labeling import gen_categories_js

ROOT = Path(__file__).resolve().parents[4]
WEB = ROOT / "web" / "labeling"


def test_categories_js_is_generated_from_contract():
    current = (WEB / "categories.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == gen_categories_js.render(), "запустите python -m ml.labeling.gen_categories_js"
    data = json.loads((ROOT / "research/round-14/categories_v2.json").read_text(encoding="utf-8"))
    assert len(data["categories"]) == 12


def test_page_has_no_network_resources():
    # Офлайн-финал: ни одного http(s) в разметке, стилях и скриптах страницы.
    for name in ("index.html", "style.css", "app.js", "core.js", "categories.js"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert not re.search(r"https?://", text), name
        assert "@import" not in text and "fetch(" not in text, name


def test_every_category_icon_is_drawn():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    data = json.loads((ROOT / "research/round-14/categories_v2.json").read_text(encoding="utf-8"))
    for cat in data["categories"]:
        assert re.search(r"\b%s: '" % re.escape(cat["icon"]), app), cat["icon"]


def test_ui_strings_exist_in_both_languages():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    ru_block = app[app.index("    ru: {"):app.index("    kk: {")]
    kk_block = app[app.index("    kk: {"):app.index("  // Спорные случаи")]
    key_re = re.compile(r"\b([A-Za-z_]\w*): \"")
    ru_keys, kk_keys = set(key_re.findall(ru_block)), set(key_re.findall(kk_block))
    assert ru_keys == kk_keys, (ru_keys ^ kk_keys)
    for key in re.findall(r'data-t="(\w+)"', html):
        assert key in ru_keys, key
