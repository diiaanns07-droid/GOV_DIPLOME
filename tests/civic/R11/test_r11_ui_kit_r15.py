"""R11 раунд 15: компоненты новых экранов ui-kit (IA_ROUND15 §5) — статические проверки.

pytest tests/civic/R11/test_r11_ui_kit_r15.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KIT = ROOT / "web/civic/ui-kit"
TOKENS = (KIT / "tokens.css").read_text("utf-8")
COMPONENTS = (KIT / "components.css").read_text("utf-8")
ICONS = (KIT / "icons.svg").read_text("utf-8")
SHOWCASE = (KIT / "index.html").read_text("utf-8")

# Компонент → классы, на которые опираются роли (разметка — в комментариях components.css и в витрине)
R15_CLASSES = {
    "двор (R16)": ["bk-yard", "bk-yard__title", "bk-yard__stats", "bk-yard__stat", "bk-yard__captain", "bk-yard__actions"],
    "лента (R16, R06, R17)": ["bk-feed", "bk-feed__item", "bk-feed__ic", "bk-feed__title", "bk-feed__meta", "bk-feed__group"],
    "инициатива (R16)": ["bk-join", "bk-join__n", "bk-support", "bk-support--block", "bk-init", "bk-init__media", "bk-init__kind",
                         "bk-init__cta", "bk-done", "bk-done--nophoto", "bk-done__note", "bk-thumb--kind", "bk-pc__foot--wrap"],
    "службы (R09, R17)": ["bk-svcs", "bk-svc", "bk-svc__name", "bk-svc__st", "bk-deadline", "bk-deadline__track"],
    "табло (R17)": ["bk-board", "bk-board--dense", "bk-board__svc", "bk-board__ic", "bk-board__late"],
    "передачи (R17, R09)": ["bk-handoffs", "bk-handoff", "bk-handoff__route", "bk-handoff__why"],
    "календарь работ (R12)": ["bk-wcal", "bk-wcal__months", "bk-wcal__name", "bk-wcal__track", "bk-wcal__bar", "bk-wcal__link",
                              "bk-wcal__today"],
    "конфликт (R12)": ["bk-conflict", "bk-advice", "bk-advice__title"],
    "кризис (R17)": ["bk-crisis", "bk-crisis__dot", "bk-crisis-hd", "bk-svcchips", "bk-svcchip", "bk-svcchip__ring", "bk-zone",
                     "bk-zone__swatch", "bk-live-dot"],
    "хроника (R07)": ["bk-replay", "bk-replay__play", "bk-replay__date", "bk-replay__scrub", "bk-replay__tick", "bk-range"],
    "встречи (R13)": ["bk-meet", "bk-meet__date", "bk-meet__cta", "bk-orders", "bk-order", "bk-order__due"],
    "уведомления (R06)": ["bk-bell", "bk-notify", "bk-notify__hd", "bk-notify__readall"],
    "Спросить Birge (R03)": ["bk-answer", "bk-answer__nums", "bk-answer__num", "bk-answer__text"],
    "ситуационный центр (R08)": ["bk-sc", "bk-sc__top", "bk-sc__grid", "bk-sc-tile", "bk-sc-num", "bk-sc__dots"],
}
R15_ICONS = ["bell", "play", "pause", "monitor", "sparkle", "handoff", "shovel", "cone", "broom", "sprout", "wrench", "expand",
             "megaphone", "bench", "paw", "traffic", "radiator", "zap", "flame", "siren"]
R15_ILLS = ["together", "calendar", "bell", "chart", "handoff"]
# П1 (AMENDMENTS.md, 15 окт): сценки убраны — вид объекта или дела показывается значком i-*
R15_KIND_ICONS = ["trees", "playground", "ball", "bus", "bulb", "bench", "sprout", "broom", "snowflake", "wrench", "heart"]


def r15_section():
    start = COMPONENTS.rfind("/*", 0, COMPONENTS.index("Раунд 15 «Бірге — вместе»: компоненты новых экранов"))
    end = COMPONENTS.rfind("/*", 0, COMPONENTS.index("Стекло Apple Liquid Glass (GLASS.md)"))
    assert start < end, "раздел раунда 15 должен стоять до стекла (стекло в конце перекрывает фон компонентов)"
    return COMPONENTS[start:end]


def test_r15_classes_exist_and_are_shown():
    css = r15_section()
    missing, not_shown = [], []
    for group, classes in R15_CLASSES.items():
        for cls in classes:
            if not re.search(r"\." + re.escape(cls) + r"(?![a-z0-9_-])", css):
                missing.append(f"{group}: .{cls}")
            if cls not in SHOWCASE and cls not in ("bk-board--dense", "bk-pc__foot--wrap", "bk-init__media"):
                not_shown.append(f"{group}: .{cls}")
    assert not missing, missing
    assert not not_shown, f"нет примера в витрине: {not_shown}"


def test_r15_does_not_redefine_reference_classes():
    """Только новые классы: селекторы раздела раунда 15 начинаются с новых имён (эталон A не трогаем)."""
    css = re.sub(r"/\*.*?\*/", "", r15_section(), flags=re.S)
    new_roots = {c.split("__")[0].split("--")[0] for group in R15_CLASSES.values() for c in group}
    new_roots |= {"bk-dark", "bk-pc__foot", "bk-thumb", "bk-btn__count", "bk-bump"}  # точечные дополнения с модификатором
    allowed = tuple("." + r for r in sorted(new_roots, key=len, reverse=True))
    for block in re.findall(r"([^{}]+)\{", css):
        for sel in block.split(","):
            sel = sel.strip()
            if not sel or sel.startswith("@") or sel.startswith(("from", "to")) or re.match(r"^\d+%", sel):
                continue
            parts = sel.split()
            if re.fullmatch(r":lang\([a-z]+\)", parts[0]) and len(parts) > 1:  # :lang(kk) .bk-feed__title — правило языка
                parts = parts[1:]
            first = re.sub(r"^[a-z]+(?=\.)", "", parts[0])  # a.bk-feed__item, button.bk-conflict
            assert first.startswith(allowed), f"селектор раунда 15 трогает класс эталона: {sel}"


def test_r15_dark_tokens_only_for_situation_centre():
    assert re.search(r"^\.bk-dark \{", TOKENS, re.M), "нет блока тёмных токенов .bk-dark"
    root_blocks = re.findall(r":root \{(.*?)\n\}", TOKENS, re.S)
    for block in root_blocks:
        assert "color-scheme: dark" not in block
        assert "--c-paper: #0b100e" not in block, "тёмная бумага попала в :root — тёмной темы всему продукту нет"
    assert "--c-paper: #f3f1ec" in TOKENS
    for name in ("--zone-fill", "--zone-line", "--sc-gap", "--sc-fs-num"):
        assert name in TOKENS, name


def test_r15_icons_and_illustrations():
    ids = set(re.findall(r'<symbol id="([a-z0-9-]+)"', ICONS))
    for name in R15_ICONS:
        assert "i-" + name in ids, name
        assert re.search(r'"[^"]*\b' + re.escape(name) + r'\b[^"]*"', SHOWCASE.split("var ICONS = ")[1].split(".split")[0]), name
    for name in R15_ILLS:
        assert "ill-" + name in ids, name
        sym = re.search(r'<symbol id="ill-' + re.escape(name) + r'".*?</symbol>', ICONS, re.S).group(0)
        shapes = re.findall(r"<(path|circle|rect)\b[^>]*>", sym)
        assert shapes and sym.count('vector-effect="non-scaling-stroke"') == len(shapes), f"ill-{name}: линия должна не толстеть"


def test_r15_reduced_motion_and_focus():
    css = r15_section()
    assert "@media (prefers-reduced-motion: reduce)" in css
    for anim in ("bk-bump", "bk-crisis-pulse", "bk-sc-in"):
        assert f"@keyframes {anim}" in css, anim
    for cls in ("bk-join", "bk-replay__play", "bk-wcal__bar", "bk-range", "bk-notify__readall"):
        assert re.search(r"\." + cls + r":focus-visible", css), f".{cls}: нет видимого фокуса"


def test_r15_tap_targets():
    """Кнопки раунда 15 — 44 px или зона нажатия ::after до 44 (VISUAL_BRIEF §4.10)."""
    css = r15_section()
    assert re.search(r"\.bk-join::after \{\s*content: \"\";\s*position: absolute;\s*inset: -6px 0;", css)  # 32 + 12
    assert re.search(r"button\.bk-conflict::after \{\s*content: \"\";\s*position: absolute;\s*inset: -8px 0;", css)  # 28 + 16
    assert re.search(r"\.bk-replay__play \{[^}]*width: var\(--tap\)", css)


def test_p1_no_ai_slop():
    """Поправка владельца П1 «Без ИИ-слопа»: малые монохромные значки, без сценок, рисунков и декоративных градиентов."""
    ids = set(re.findall(r'<symbol id="([a-z0-9-]+)"', ICONS))
    banned = [i for i in ids if i.startswith("ill-kind-") or i in ("ill-yard", "ill-meeting")]
    assert not banned, f"сценки в спрайте: {banned}"
    for name in R15_KIND_ICONS:
        assert "i-" + name in ids, name
    rule = re.search(r"\n\.bk-ill \{(.*?)\n\}", COMPONENTS, re.S).group(1)
    size = int(re.search(r"width: (\d+)px", rule).group(1))
    assert size <= 48, f".bk-ill {size} px > 48"
    css = r15_section()
    assert "radial-gradient" not in css, "декоративный градиент в компонентах раунда 15"
    sc = re.search(r"\n\.bk-sc \{(.*?)\n\}", css, re.S).group(1)
    assert "gradient" not in sc and "backdrop-filter" not in re.search(r"\n\.bk-sc-tile \{(.*?)\n\}", css, re.S).group(1)
    assert "bk-yard__ill" not in css and "bk-yard__ill" not in SHOWCASE, "рисунок в шапке двора"
    assert "ill-kind-" not in SHOWCASE and '<svg class="bk-done__photo"' not in SHOWCASE, "нарисованное «фото» или сценка в витрине"


def test_module_inside_glass_sheet_has_veil_not_paper():
    """Обзор R11 круг 5: модуль .bk-app внутри стеклянного листа — без бежевой бумаги («лист в листе»), но с белой
    вуалью 50 %: на тёмной карте под стеклом 72 % текст на серых плашках держит ≥ 4.5 : 1 (замер B0: 5.95, без вуали 4.15)."""
    css = re.sub(r"/\*.*?\*/", "", COMPONENTS, flags=re.S)
    rule = re.search(r"\n\.bk-glass \.bk-app:not\(\.bk-glass\) \{([^}]*)\}", css)
    assert rule, "нет правила для модуля внутри стекла"
    assert "background: rgba(255, 255, 255, 0.5)" in rule.group(1)
    assert "c-paper" not in rule.group(1)
    dark = re.search(r"\n\.bk-dark \.bk-glass \.bk-app:not\(\.bk-glass\) \{([^}]*)\}", css)
    assert dark and "transparent" in dark.group(1), "в тёмном ситуационном центре вуали нет"
    # бумага у самого .bk-app остаётся (страницы без стекла) — эталон не трогаем
    assert re.search(r"\n\.bk-app \{[^}]*background: var\(--c-paper\)", css)


def test_tabs_fit_four_kk_tabs_on_phone():
    """Обзор R11 круг 5: на телефоне промежуток вкладок 14 px — «Шолу · Мәселелер · Бастамалар · Жұмыстар» в строке 375."""
    css = re.sub(r"/\*.*?\*/", "", COMPONENTS, flags=re.S)
    phone = re.findall(r"@media \(max-width: 480px\) \{(.*?)\n\}", css, re.S)
    assert any(re.search(r"\.bk-tabs \{\s*gap: 14px;", block) for block in phone)
    assert re.search(r"\n\.bk-tabs \{[^}]*gap: 18px;", css), "на ноутбуке — как эталон .tabs (18)"


def test_feed_title_keeps_kazakh_predicate():
    """Обзор R11 круг 5: в казахском сказуемое в конце — заголовок ленты в ҚАЗ до 4 строк (было 2: «…жобасы…»)."""
    css = re.sub(r"/\*.*?\*/", "", COMPONENTS, flags=re.S)
    rule = re.search(r"\n:lang\(kk\) \.bk-feed__title \{([^}]*)\}", css)
    assert rule and "-webkit-line-clamp: 4" in rule.group(1)
