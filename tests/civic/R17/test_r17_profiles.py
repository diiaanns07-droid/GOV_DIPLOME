"""R17 · профили служб (CONTRACT §3, §5.4): один справочник id, названия из таблицы R08, читаемые цвета."""

import re

from ui.civic_agencies import profiles


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_on_white(hex_color: str) -> float:
    return (1.05) / (_luminance(hex_color) + 0.05)


def test_ids_are_the_one_directory_of_r08_and_r09():
    from ui.civic_akim.routing import SERVICES as R08
    from ui.civic_feedback.v2.lifecycle import SERVICES as R09
    assert set(profiles.SERVICE_IDS) == set(R08) == set(R09) == set(profiles.PROFILES)
    assert len(profiles.SERVICE_IDS) == 20


def test_profile_format_and_names_from_r08():
    from ui.civic_akim.routing import SERVICES as R08
    rows = profiles.all_profiles()
    assert [r["id"] for r in rows] == list(profiles.SERVICE_IDS)
    for r in rows:
        assert r["kind"] in profiles.KINDS
        assert re.fullmatch(r"#[0-9a-f]{6}", r["color"])
        assert isinstance(r["sla_answer_days"], int) and 1 <= r["sla_answer_days"] <= 30
        assert isinstance(r["sla_fix_days"], int) and r["sla_fix_source"] == "default"
        assert r["ru"] == R08[r["id"]]["ru"] and r["kk"] == R08[r["id"]]["kk"]


def test_answer_days_come_from_r09_categories():
    days = profiles.answer_days()
    assert days["street_cleaning"] == 1        # snow_ice — 1 рабочий день (R09 RESPONSE_DAYS)
    assert days["water"] == 1                  # utilities/no_water
    assert days["road"] == 10                  # roads, sidewalks


def test_colors_readable_and_not_heat_or_fixed():
    heat = {"#fac775", "#ef9f27", "#e24b4a", "#a32d2d", "#639922", "#3b8a2e", "#97c459"}
    for kind, color in profiles.KIND_COLORS.items():
        assert contrast_on_white(color) >= 4.5, kind
        assert color.lower() not in heat


def test_icons_exist_in_ui_kit_sprite():
    """Значок службы — из спрайта ui-kit. Спрайт раунда 15 (R11: radiator, zap, flame, paw, traffic, siren, broom,
    wrench) — icon; старый спрайт (FINAL-4) — icon_fallback, его экран берёт, если нового значка в спрайте нет."""
    from pathlib import Path
    sprite = (Path(__file__).resolve().parents[3] / "web" / "civic" / "ui-kit" / "icons.svg").read_text("utf-8")
    round15 = 'id="i-radiator"' in sprite
    for sid in profiles.SERVICE_IDS:
        p = profiles.profile(sid, names={}, answers={})
        assert f'id="i-{p["icon_fallback"]}"' in sprite or round15, sid
        if round15:
            assert f'id="i-{p["icon"]}"' in sprite, sid
    assert profiles.profile("heating", names={}, answers={})["icon"] == "radiator"
    assert profiles.profile("emergency", names={}, answers={})["icon"] == "siren"
