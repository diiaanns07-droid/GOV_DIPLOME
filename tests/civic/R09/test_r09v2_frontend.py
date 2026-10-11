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
STAFF_JS = (WEB / "complaint-staff.js").read_text(encoding="utf-8")


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
    used = set(re.findall(r'\bt\("([a-z0-9_.]+)"', JS + STAFF_JS))
    # t("status." + x) и т. п. — составные ключи; каждый вариант проверяется ниже.
    dynamic_prefixes = {"status.", "complaint.example.", "cat.", "emergency.service.", "service.", "subtopic.",
                        "mine.passport.next_default.", "mine.update."}
    missing = sorted(k for k in used if k not in data["ru"] and k not in dynamic_prefixes)
    assert not missing, missing
    # Ключи, собираемые в коде из частей: status.<статус>, complaint.example.<категория>
    for status in ("new", "accepted", "in_progress", "fixed", "rejected"):
        assert "status." + status in data["ru"]
    for cat in categories.ids():
        assert "complaint.example." + cat in data["ru"]
    phones = {s.get("emergency_phone") for c in categories.ids() for s in categories.subtopics(c)} - {None}
    for phone in phones | {"104", "112"}:
        assert "emergency.service." + phone in data["ru"]
    from ui.civic_feedback.v2 import lifecycle
    for sid in lifecycle.SERVICES:                                   # service.<id> — ключи R11 по id R08
        assert "service." + sid in data["ru"]
    for cat in categories.ids():
        for sub in categories.subtopics(cat):
            assert "subtopic." + sub["id"] in data["ru"]
    for status in ("reported_fixed", "verified", "reopened"):         # статусы проверки ремонта (R11 §2.2)
        assert "status." + status in data["ru"]
    for status in ("new", "accepted", "in_progress", "fixed", "rejected"):
        assert "mine.passport.next_default." + status in data["ru"]
    for kind in ("fixed", "reopened", "passport", "note"):
        assert "mine.update." + kind in data["ru"]


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
    for name in ("complaint.js", "complaint-staff.js", "complaint.css", "kit-fallback.css", "complaint-strings.js"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "http://" not in text.replace("http://www.w3.org/2000/svg", "") and "https://" not in text, name
    # Тексты пользователей вставляются только через textContent/узлы, не через innerHTML.
    assignments = re.findall(r"innerHTML\s*=\s*([^;]+);", JS + STAFF_JS)
    assert assignments and all(value == '""' for value in assignments)   # только очистка контейнера


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


# ---- Стык с настоящими R12 /targets и R04 /classify, /similar ----

def test_r04_suggest_drives_the_chip():
    # R04: needs_review всегда true (пометка для сотрудника); подсказку жителю показываем по suggest.
    assert 'typeof data.suggest === "boolean" ? data.suggest : !data.needs_review' in JS


def test_r04_similar_threshold_not_refiltered_and_target_sent():
    assert "SIMILAR_MIN_SCORE" not in JS and "m.score >=" not in JS
    assert "body.target = { kind: state.target.kind, id: state.target.id }" in JS


def test_r12_candidate_approximate_flag_is_kept():
    assert "candidate.approximate ? { approximate: true } : {}" in JS


def test_r12_targets_timeout_covers_cold_graph_load():
    assert re.search(r"TARGETS_TIMEOUT_MS = (\d+)", JS) and int(re.search(r"TARGETS_TIMEOUT_MS = (\d+)", JS).group(1)) >= 5000
    assert '"/targets?lon=" + state.point[0] + "&lat=" + state.point[1], undefined, TARGETS_TIMEOUT_MS' in JS


def test_r12_approximate_only_skips_question_and_no_duplicate_other_place():
    assert "state.candidates.every(function (c) { return c.approximate" in JS
    assert "if (!hasApprox) {" in JS
    assert "GENERIC_APPROX[label]" in JS   # подробная подпись R12 не затирается общей


# ---------------------------------------------------------------- волна 1–2: JS и сервер решают одинаково
def run_complaint_js(expr: str):
    """Вычислить выражение над window.BirgeComplaint в node (без браузера и DOM)."""
    code = ("global.window={};for(const f of process.argv.slice(1))require(f);"
            "process.stdout.write(JSON.stringify((function(C){return " + expr + ";})(window.BirgeComplaint)))")
    files = [str(WEB / n) for n in ("categories_v2.js", "complaint-strings.js", "complaint.js")]
    try:
        out = subprocess.run(["node", "-e", code, *files], capture_output=True, text=True, check=True, timeout=30).stdout
    except FileNotFoundError:
        pytest.skip("node не установлен")
    return json.loads(out)


EMERGENCY_PHRASES = [
    ("smell_air", "gas", "Пахнет в подъезде"), ("lighting", "wire_down", "Висит над дорогой"),
    ("smell_air", "smoke_fire", ""), ("other", None, "Сильно пахнет газом в подъезде"),
    ("other", None, "Подъезде газ иісі шығып тұр"), ("other", None, "Утечка газа во дворе"),
    ("other", None, "На пустыре пожар, всё в дыму"), ("other", None, "Горит мусорный бак во дворе"),
    ("other", None, "Аулада өрт шықты"), ("other", None, "Түтін шығып жатыр"), ("other", None, "Оборван провод у школы"),
    ("other", None, "Сым үзіліп жерде жатыр"), ("other", None, "Загорелась трава"),
    ("lighting", None, "Не горят фонари во дворе"), ("lighting", None, "Фонарь горит весь день"),
    ("lighting", None, "Шамдар жанбайды"), ("parking", None, "Машины стоят на газоне"),
    ("other", None, "Газета в почтовом ящике"), ("roads", None, "Яма на дороге"), ("other", None, ""),
]


def test_emergency_js_matches_server():
    """Баннер «Звоните N» в браузере и отметка emergency на сервере не должны расходиться (волна 1, п. 3)."""
    from ui.civic_feedback.v2 import lifecycle
    js = run_complaint_js("%s.map(function(c){var r=C.emergency(c[0],c[1],c[2]);return r?r.phone:null;})"
                          % json.dumps(EMERGENCY_PHRASES, ensure_ascii=False))
    py = [(lifecycle.emergency(c, s, t) or {}).get("phone") for c, s, t in EMERGENCY_PHRASES]
    assert js == py
    assert py.count(None) == 7 and py.count("104") == 4


def test_seasonal_order_in_grid():
    """Волна 1, п. 11: ноябрь–март — «Снег и гололёд» первым, апрель–октябрь — «Дороги»; набор тот же (12)."""
    months = run_complaint_js("[0,1,2,3,4,5,6,7,8,9,10,11].map(function(m){"
                              "return C.seasonalCategories(Date.UTC(2026,m,15,6)).map(function(c){return c.id;});})")
    for month, order in enumerate(months, start=1):
        assert sorted(order) == sorted(categories.ids())
        assert order[0] == ("snow_ice" if month in (11, 12, 1, 2, 3) else "roads"), month
    assert months[6] == list(categories.ids())   # летом — порядок контракта


def test_staff_component_has_one_primary_and_required_what_done():
    """Волна 2, п. 1: «Отметить исправленным» требует строку «что сделали»; главная кнопка одна."""
    assert STAFF_JS.count("bk-btn--primary") == 1
    assert re.search(r'name: "what_done", maxlength: String\(WHAT_DONE_MAX\), required: true', STAFF_JS)
    assert "var WHAT_DONE_MAX = 120;" in STAFF_JS                     # R11 §2.3: одна строка ≤ 120 знаков
    assert "staff.fixed.need_what" in STAFF_JS


def test_wave_texts_come_from_r11_keys():
    """R11 IA_WAVE2 §2: тексты волны — ключами словаря R11 (verify.*, passport.*, service.assigned, deadline.*,
    broadcast.*, fix.*), а не своими копиями mine.verify.* / staff.* — иначе правка перевода у R11 до экрана не дойдёт."""
    for key in ("verify.wait_title", "verify.question", "verify.yes", "passport.next", "passport.fix_unknown",
                "service.assigned", "deadline.left", "deadline.overdue", "broadcast.metoo_hint", "mine.changes.more",
                "mine.waiting", "mine.subscriptions", "mine.unsubscribe", "complaint.subtopic.title",
                "complaint.subtopic.none", "complaint.emergency.still_send", "complaint.queue.offline"):
        assert f'"{key}"' in JS, key          # t("…") или таблица ключей кнопок
    for key in ("fix.title", "fix.what_done", "fix.send", "fix.will_see", "passport.edit", "passport.field.service",
                "passport.field.reason", "broadcast.title", "broadcast.send", "passport.update_overdue"):
        assert f't("{key}"' in STAFF_JS, key
    old = re.findall(r'"(mine\.verify\.[a-z_]+|mine\.state\.[a-z_]+|mine\.passport\.(?!next_default)[a-z_]+|'
                     r'staff\.(?:fixed|passport|update)\.[a-z_]+)"', JS + STAFF_JS)
    assert set(old) <= {"staff.fixed.need_what", "staff.fixed.what_hint"}, old   # у R11 таких ключей нет


def test_emergency_call_is_the_only_primary_button():
    """UX_SPEC §10: при срочном случае главная кнопка — звонок, «Далее/Отправить» становится второстепенной."""
    assert 'bk-btn bk-btn--primary bk-btn--block bc-emergency__call' in JS
    assert 'els.send.classList.toggle("bk-btn--primary", !emergencyNow())' in JS
