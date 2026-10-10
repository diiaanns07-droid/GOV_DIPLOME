"""R09 раунд 14: статические проверки фронтенда пути жителя (без браузера).

Браузерная проверка — tests/civic/R09/browser_r09.cjs (Chromium, стенд)."""

import json
import re
import subprocess
from pathlib import Path

import pytest

from ui.civic_feedback.v2 import categories, web_assets

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web" / "civic" / "feedback"
JS = (WEB / "complaint.js").read_text(encoding="utf-8")


def strings():
    """Словарь complaint-strings.js через node (тот же разбор, что в браузере)."""
    code = ("global.window={};require(process.argv[1]);"
            "process.stdout.write(JSON.stringify(window.BirgeComplaintStrings))")
    try:
        out = subprocess.run(["node", "-e", code, str(WEB / "complaint-strings.js")], capture_output=True,
                             text=True, check=True, timeout=30).stdout
    except FileNotFoundError:
        pytest.skip("node не установлен")
    return json.loads(out)


def test_generated_categories_up_to_date():
    assert web_assets.main(["--check"]) == 0, "запустите python -m ui.civic_feedback.v2.web_assets"


def test_generated_categories_match_contract():
    text = (WEB / "categories_v2.js").read_text(encoding="utf-8")
    payload = json.loads(text.split("window.BirgeCategoriesV2 = ", 1)[1].rstrip().rstrip(";"))
    assert [c["id"] for c in payload["categories"]] == list(categories.ids())
    assert payload["heat_levels"] == categories.load()["heat_levels"]


def test_ru_kk_same_keys_and_no_empty():
    data = strings()
    assert set(data["ru"]) == set(data["kk"])
    for lang in ("ru", "kk"):
        for key, value in data[lang].items():
            if isinstance(value, dict):
                assert lang == "ru" and set(value) == {"one", "few", "many"}, key
                assert all(v.strip() for v in value.values()), key
            else:
                assert value.strip(), f"{lang}:{key}"


def test_every_key_used_in_code_exists():
    data = strings()
    used = set(re.findall(r'\bt\("([a-z0-9_.]+)"', JS))
    dynamic_prefixes = {"status.", "complaint.example.", "cat."}  # t("status." + x) — проверяются ниже
    missing = sorted(k for k in used if k not in data["ru"] and k not in dynamic_prefixes)
    assert not missing, missing
    # Ключи, собираемые в коде из частей: status.<статус>, complaint.example.<категория>
    for status in ("new", "accepted", "in_progress", "fixed", "rejected"):
        assert "status." + status in data["ru"]
    for cat in categories.ids():
        assert "complaint.example." + cat in data["ru"]


def test_placeholders_match_between_languages():
    data = strings()
    for key, ru in data["ru"].items():
        kk = data["kk"][key]
        ru_params = set(re.findall(r"\{(\w+)\}", json.dumps(ru, ensure_ascii=False)))
        kk_params = set(re.findall(r"\{(\w+)\}", json.dumps(kk, ensure_ascii=False)))
        assert ru_params == kk_params, key


def test_no_technical_words_in_texts():
    data = strings()
    banned = re.compile(r"ребр|граф|геометр|сценари|payload|target|null|undefined|demo-ring", re.IGNORECASE)
    for lang in ("ru", "kk"):
        for key, value in data[lang].items():
            assert not banned.search(json.dumps(value, ensure_ascii=False)), f"{lang}:{key}"


def test_no_runtime_internet_and_no_innerhtml_with_data():
    for name in ("complaint.js", "complaint.css", "kit-fallback.css", "complaint-strings.js"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "http://" not in text.replace("http://www.w3.org/2000/svg", "") and "https://" not in text, name
    # Тексты пользователей вставляются только через textContent/узлы, не через innerHTML.
    assert re.findall(r"innerHTML\s*=\s*([^;]+);", JS) == ['""', '""', '""']


def test_device_id_and_ml_fallback_present():
    assert "X-Birge-Device" in JS
    assert "ML_TIMEOUT_MS" in JS and "/classify" in JS and "/similar" in JS
    assert '"birge:complaint"' in JS


# ---- Ранний UX-разбор R11 (claude/r14-R11, UX_REVIEW.md «День 2», строки 1–6) ----

def test_r11_1_dasharray_without_data_expression():
    # MapLibre не принимает выражения по данным в line-dasharray: пунктир — отдельным слоем.
    for match in re.finditer(r'"line-dasharray":\s*([^}]+?)\s*[},]', JS):
        assert match.group(1).startswith("["), match.group(0)
        assert '"get"' not in match.group(1) and '"case"' not in match.group(1), match.group(0)
    assert '"bc-area-approx"' in JS and '"bc-area-line"' in JS


def test_r11_2_target_and_click_point_differ():
    assert '["case", ["coalesce", ["get", "pick"], false], 6, 11]' in JS
    assert "pick: false" in JS and "pick: true" in JS


def test_r11_3_send_enabled_after_classify():
    handler = JS[JS.index('request("POST", "/classify"'):JS.index("}, CLASSIFY_DEBOUNCE_MS)")]
    assert handler.rindex("updateSendButton();") > handler.rindex("renderCategory();")


def test_r11_4_question_without_label():
    data = strings()
    assert data["ru"]["complaint.step2.question"] == "Это здесь?"
    assert "{label}" not in data["kk"]["complaint.step2.question"]
    assert "complaint.step2.yes" not in data["ru"]          # «Да, Остановка …» больше нет
    assert 't("complaint.step2.question")' in JS


def test_r11_5_category_grid_is_ui_kit_catgrid():
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    assert '"bk-catgrid"' in JS and "bc-grid" not in JS and ".bc-grid" not in css
    fallback = (WEB / "kit-fallback.css").read_text(encoding="utf-8")
    assert "minmax(min(150px, 100%), 1fr)" in fallback      # те же колонки ≥ 150 px, что в ui-kit R11


def test_r11_6_single_check_mark_in_chip():
    assert '" ✓"' not in JS                                  # галочку рисует ui-kit через ::before
    fallback = (WEB / "kit-fallback.css").read_text(encoding="utf-8")
    assert '.bk-chip[aria-pressed="true"]::before { content: "✓"' in fallback
