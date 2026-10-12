"""R11: ui-kit и i18n — статические проверки (pytest или `python3 tests/civic/R11/test_r11_ui_kit.py`)."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import i18n_tools  # noqa: E402

KIT = ROOT / "web/civic/ui-kit"
TOKENS = (KIT / "tokens.css").read_text("utf-8")
COMPONENTS = (KIT / "components.css").read_text("utf-8")
ICONS = (KIT / "icons.svg").read_text("utf-8")
SHOWCASE = (KIT / "index.html").read_text("utf-8")
CATS = json.loads((ROOT / "research/round-14/categories_v2.json").read_text("utf-8"))


def token(name):
    m = re.search(r"--" + re.escape(name) + r":\s*(#[0-9a-fA-F]{6})", TOKENS)
    assert m, f"нет токена --{name}"
    return m.group(1).lower()


def contrast(a, b):
    def lum(h):
        rgb = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def test_dictionaries_complete():
    assert i18n_tools.check() == []


def test_heat_colors_match_categories():
    levels = {l["level"]: l["color"] for l in CATS["heat_levels"] if l["color"]}
    for level, color in levels.items():
        assert token(f"heat-{level}") == color.lower()
    assert token("fixed") == CATS["fixed_state"]["color"].lower()
    hs = CATS["heat_states"]  # волна 2
    assert token("fixed") == hs["verified_fixed"]["color"].lower()
    assert token("reported-fixed") == hs["reported_fixed"]["color"].lower()
    assert token("nodata") == hs["no_data"]["color"].lower()
    for sel in ('data-level="reported_fixed"', 'data-level="nodata"', 'data-status="reported_fixed"',
                'data-status="verified"', 'data-status="reopened"', ".bk-banner--danger"):
        assert sel in COMPONENTS, sel


def test_text_contrast_at_least_4_5():
    white = "#ffffff"
    pairs = [("c-ink", None), ("c-text-2", None), ("c-brand", None), ("c-danger", None), ("c-warn", None),
             ("c-info", None), ("c-ok", None), ("c-demo", None)]
    for fg, _ in pairs:
        assert contrast(token(fg), white) >= 4.5, fg
    for badge in ("heat-1", "heat-2", "heat-3", "heat-4", "fixed"):
        bg, on = token(f"{badge}-badge"), token(f"{badge}-on")
        assert contrast(bg, on) >= 4.5, f"{badge}: {bg} / {on} = {contrast(bg, on):.2f}"
    # Статусы: цвет слова на своём мягком фоне
    for name in ("info", "warn", "ok", "danger", "demo"):
        assert contrast(token(f"c-{name}"), token(f"c-{name}-soft")) >= 4.5, name
    assert contrast(token("c-ink"), token("c-accent")) >= 4.5


def test_icons_cover_categories_and_showcase():
    ids = set(re.findall(r'<symbol id="i-([a-z0-9-]+)"', ICONS))  # иконки; иллюстрации ill-* проверяются отдельно
    ills = set(re.findall(r'<symbol id="ill-([a-z0-9-]+)"', ICONS))
    assert {"list", "map", "search", "done", "offline", "idea", "question"} <= ills, ills
    assert ICONS.count('vector-effect="non-scaling-stroke"') >= 7  # линия иллюстраций не толстеет при 96 px
    assert len(ids) >= 30
    for c in CATS["categories"]:
        assert c["icon"] in ids, c["icon"]
    listed = re.search(r'var ICONS = \(([^;]+)\)\.split', SHOWCASE).group(1)
    names = set(" ".join(re.findall(r'"([^"]*)"', listed)).split())
    assert names == ids, f"витрина и спрайт расходятся: {names ^ ids}"
    for used in re.findall(r'data-kit-icon="([a-z0-9-]+)"', SHOWCASE):
        assert used in ids, used


def test_icon_sprite_is_well_formed_xml():
    # битый спрайт = ни одной иконки на всех экранах (так было при вставке иллюстраций в комментарий)
    import xml.dom.minidom
    xml.dom.minidom.parseString(ICONS.encode("utf-8"))


def test_icons_are_local_and_symbols_have_viewbox():
    assert "http" not in ICONS.replace("http://www.w3.org/2000/svg", "")
    assert ICONS.count("<symbol") == ICONS.count('viewBox="0 0 24 24"')


def test_no_runtime_internet():
    for text in (TOKENS, COMPONENTS, SHOWCASE, (KIT / "ui-kit.js").read_text("utf-8"),
                 (ROOT / "web/civic/i18n/i18n.js").read_text("utf-8")):
        assert not re.search(r"https?://(?!www\.w3\.org)", text), "внешний адрес в рантайме"


def test_showcase_keys_exist():
    ru = i18n_tools.load("ru")
    keys = set(re.findall(r'data-i18n="([^"]+)"', SHOWCASE))
    for attr in re.findall(r'data-i18n-attr="([^"]+)"', SHOWCASE):
        keys |= {pair.split(":", 1)[1] for pair in attr.split(";")}
    keys |= set(re.findall(r'\bt\("([a-z0-9_.]+)"', SHOWCASE))
    keys = {k for k in keys if not k.endswith(".")}  # t("cat." + id) — динамический префикс
    missing = sorted(k for k in keys if k not in ru)
    assert not missing, missing


def test_prototype_keys_exist():
    """Все ключи, которые вызывают макеты (t("..."), data-i18n), есть в ru.json и kk.json."""
    ru, kk = i18n_tools.load("ru"), i18n_tools.load("kk")
    missing = []
    for f in sorted((KIT / "prototypes").glob("*.*")):
        if f.suffix not in (".html", ".js") or f.name == "proto-streets.js":
            continue
        text = f.read_text("utf-8")
        keys = set(re.findall(r'data-i18n="([^"]+)"', text)) | set(re.findall(r'\bt\("([a-z0-9_.]+)"', text))
        keys |= set(re.findall(r'"((?:common|target|heat|akim|complaint|mine|proposal|status|stage|object|district|proto)\.[a-z0-9_.]+)"', text))
        for attr in re.findall(r'data-i18n-attr="([^"]+)"', text):
            keys |= {pair.split(":", 1)[1] for pair in attr.split(";") if ":" in pair and "'" not in pair}
        keys = {k for k in keys if not re.search(r"\.(css|js|html|json|svg)$", k)}  # имена файлов — не ключи
        missing += [f"{f.name}: {k}" for k in sorted(keys) if not k.endswith(".") and (k not in ru or k not in kk)]
    assert not missing, missing


def test_prototype_streets_are_generated_from_graph():
    js = (KIT / "prototypes/proto-streets.js").read_text("utf-8")
    assert js.startswith("/* СГЕНЕРИРОВАНО") and "OpenStreetMap" in js
    data = json.loads(js.split("=", 1)[1].strip().rstrip(";"))
    for seg in data["segments"].values():
        assert seg["edges"] and all(e.startswith("osm-w") for e in seg["edges"])  # участки — рёбра графа OSM


def test_touch_targets_and_font_sizes():
    assert re.search(r"--tap:\s*48px", TOKENS)
    # Чистый дизайн (владелец, 12 окт): шкала 13/15/17/22/28 — подписи не меньше 13, текст не меньше 15, два веса.
    sizes = [int(x) for x in re.findall(r"font-size:\s*(\d+)px", COMPONENTS)]
    assert all(s >= 13 for s in sizes), sizes
    for name, px in (("caption", 13), ("body", 15), ("lead", 17), ("title", 22), ("h1", 28)):
        assert f"--fs-{name}: {px}px" in TOKENS, name
    weights = set(re.findall(r"font-weight:\s*(\d+)", TOKENS + COMPONENTS))
    assert weights <= {"400", "600"}, weights
    assert "--fw-bold: 600" in TOKENS


def test_local_font_files_and_license():
    for w in ("Regular", "SemiBold"):
        f = KIT / "fonts" / f"Inter-{w}.woff2"
        assert f.exists() and f.read_bytes()[:4] == b"wOF2", f
        assert f.stat().st_size < 120_000
        assert f"fonts/Inter-{w}.woff2" in TOKENS
    # 700 не подключаем (два веса); файл остаётся, пока он в списке статики шлюза R01
    assert "Inter-Bold.woff2" not in TOKENS
    assert "SIL OPEN FONT LICENSE" in (KIT / "fonts/OFL.txt").read_text("utf-8")


def test_focus_visible_and_reduced_motion():
    assert ":focus-visible" in COMPONENTS
    assert "prefers-reduced-motion" in TOKENS and "prefers-reduced-motion" in COMPONENTS


def test_kazakh_letters_in_dictionary():
    kk_text = json.dumps(i18n_tools.load("kk"), ensure_ascii=False)
    for ch in "әғқңөұүі":
        assert ch in kk_text, ch


def test_phone_legend_is_one_row():
    """UX_SPEC v1.3: на телефоне легенда — одна строка, заголовок и пояснение скрыты."""
    m = re.search(r"@media \(max-width: 1023px\) \{\s*\.bk-legend \{(?P<rule>[^}]*)\}(?P<rest>.*?)\n\}", COMPONENTS, re.S)
    assert m, "нет телефонного правила .bk-legend"
    assert "flex-wrap: nowrap" in m.group("rule") and "overflow-x: auto" in m.group("rule")
    assert ".bk-legend__title" in m.group("rest") and ".bk-legend__note" in m.group("rest") and "display: none" in m.group("rest")


def test_ru_plural_other_is_optional():
    """ru: one/few/many обязательны, other — по желанию (дробные); лишние формы — ошибка."""
    ru, kk = i18n_tools.load("ru"), i18n_tools.load("kk")
    assert set(ru["akim.delta.ratio"]) == {"one", "few", "many", "other"}
    assert not [x for x in i18n_tools.check(ru, kk) if "akim.delta.ratio" in x]
    ru2 = dict(ru, **{"test.plural.bad": {"one": "{n}", "few": "{n}", "many": "{n}", "two": "{n}"}})
    kk2 = dict(kk, **{"test.plural.bad": "{n}"})
    assert any("test.plural.bad" in x for x in i18n_tools.check(ru2, kk2))


def test_i18n_js_in_node():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("нет node")
    r = subprocess.run([node, str(HERE / "i18n.test.cjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_ui_kit_js_in_node():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("нет node")
    r = subprocess.run([node, str(HERE / "ui_kit.test.cjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_lang_order_in_node():
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("нет node")
    r = subprocess.run([node, str(HERE / "i18n_lang_order.test.cjs")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr



def _contrast(a, b):
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    la, lb = (0.2126 * lin(x[0]) + 0.7152 * lin(x[1]) + 0.0722 * lin(x[2]) for x in (a, b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_glass_contrast_on_any_map_background():
    """Стекло (GLASS.md): текст ≥ 4.5:1 даже если под стеклом чёрный — худший фон карты."""
    tok = lambda name: re.search(r"--" + name + r":\s*([^;]+);", TOKENS).group(1).strip()
    hexrgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    alpha = lambda v: float(re.search(r"rgba\(\s*255,\s*255,\s*255,\s*([0-9.]+)\)", v).group(1))
    a_panel, a_ctrl = alpha(tok("glass-panel")), alpha(tok("glass-control"))
    assert 0.72 <= a_panel <= 0.80 and 0.55 <= a_ctrl <= 0.65, (a_panel, a_ctrl)  # диапазоны владельца
    worst_panel = tuple(round(a_panel * 255) for _ in range(3))
    worst_ctrl = tuple(round(a_ctrl * 255) for _ in range(3))
    ink = hexrgb(tok("c-ink"))
    assert _contrast(ink, worst_ctrl) >= 4.5, _contrast(ink, worst_ctrl)
    for name in ("c-ink", "glass-text-2", "glass-danger", "glass-warn", "glass-ok", "glass-info", "glass-demo"):
        c = _contrast(hexrgb(tok(name)), worst_panel)
        assert c >= 4.5, (name, round(c, 2))
    blur = int(re.search(r"(\d+)px", tok("glass-blur")).group(1))
    assert 20 <= blur <= 24 and tok("glass-saturate") == "170%"


def test_glass_has_opaque_fallbacks_and_scope():
    css = COMPONENTS
    assert "prefers-reduced-transparency: reduce" in css
    assert "@supports not ((-webkit-backdrop-filter: blur(1px)) or (backdrop-filter: blur(1px)))" in css
    assert ".bk-glass-off .bk-glass" in css and "forced-colors: active" in css
    # текст внутри стекла — затемнённые цвета
    block = css[css.index(".bk-glass,\n.bk-glass--control {"):]
    block = block[:block.index("}")]
    for v in ("--c-text-2: var(--glass-text-2)", "--c-danger: var(--glass-danger)", "--c-ok: var(--glass-ok)"):
        assert v in block, v
    # поля форм внутри стекла — непрозрачные
    assert ".bk-glass input" in css and "background-color: var(--c-surface)" in css

if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, "—", e)
    sys.exit(1 if failed else 0)
