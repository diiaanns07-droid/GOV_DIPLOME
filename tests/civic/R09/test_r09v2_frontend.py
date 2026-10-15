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
LIST_JS = (WEB / "complaint-list.js").read_text(encoding="utf-8")


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
    used = set(re.findall(r'\bt\("([a-z0-9_.]+)"', JS + STAFF_JS + LIST_JS))
    # t("status." + x) и т. п. — составные ключи; каждый вариант проверяется ниже.
    dynamic_prefixes = {"status.", "complaint.example.", "cat.", "emergency.service.", "service.", "subtopic.",
                        "mine.passport.next_default.", "mine.update.", "inbox.tab.", "nearby.tab.",
                        # раунд 15: части служб, роли, причины передач (варианты — test_r09v21_frontend.py)
                        "handoff.reason.", "joint.by.", "joint.part.", "joint.role."}
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
    for tab in ("now", "done", "planned", "outages"):                 # вкладки «Рядом» R08 (события подписок)
        assert "nearby.tab." + tab in data["ru"]


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
    for name in ("complaint.js", "complaint-staff.js", "complaint-list.js", "complaint.css", "kit-fallback.css",
                 "complaint-strings.js"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "http://" not in text.replace("http://www.w3.org/2000/svg", "") and "https://" not in text, name
    # Тексты пользователей вставляются только через textContent/узлы, не через innerHTML.
    assignments = re.findall(r"innerHTML\s*=\s*([^;]+);", JS + STAFF_JS + LIST_JS)
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
    # В коде три главные кнопки, на экране одна: «Отметить исправленным» (форма свёрнута) или «Сообщить жителям»;
    # третья — в отдельной форме fixForm для карточки R07 (там кнопки карточки на время формы скрыты).
    assert STAFF_JS.count("bk-btn--primary") == 3
    assert "window.BirgeComplaintStaff = { mount: mount, fixForm: fixForm };" in STAFF_JS
    assert "if (opts.fix !== false && isOpen() && !fixing) {" in STAFF_JS
    # Раунд 15: у совместной жалобы форма «исправлено» — только когда другие службы закончили свою часть.
    assert "if (opts.fix !== false && isOpen() && fixing && !others.length) {" in STAFF_JS
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


def test_inbox_screen_contract_for_r01():
    """R01 INTEGRATION §11.2: window.BirgeComplaintList.mount(root, opts) -> {destroy, setLang}; вкладки R11 §2.5."""
    assert "window.BirgeComplaintList = { mount: mount, commands: commands };" in LIST_JS   # + команды палитры Ctrl+K (эталон, правило 2)
    assert all(k in LIST_JS for k in ("destroy:", "setLang:", "opts.api.v2", "opts.openTarget", "opts.titleTag"))
    assert 'var TABS = ["new", "in_progress", "waiting_check", "overdue", "reopened"];' in LIST_JS
    # Главная кнопка — у карточки действий (одна на экран); исключение — «Войти» без входа: карточки действий тогда нет
    # (R11 INTEGRATION 10.3).
    assert LIST_JS.count("bk-btn--primary") == 1
    assert "bk-btn--primary" in LIST_JS.split('if (state.error === "staff") {', 1)[1].split("if (state.error) {", 1)[0]
    from ui.civic_feedback.v2 import lifecycle
    assert list(lifecycle.INBOX_TABS) == ["new", "in_progress", "waiting_check", "overdue", "reopened"]


def test_clean_pass_r11_r09_items():
    """R11 CLEAN_PASS §3 R09 (чистый дизайн, решение владельца 12 окт): статус один раз, поле с заливкой,
    прилипающая главная кнопка, точки шага — <i> ui-kit, без лайма и бежевого, два веса."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    kit = (WEB / "kit-fallback.css").read_text(encoding="utf-8")
    # №1: точки шага рисует ui-kit только для <i> (.bk-wizard__dots > i)
    assert 'track.appendChild(h("i", {' in JS and ".bk-wizard__dots > i" in kit
    # №3: поле текста — .bk-field
    assert '"class": "bk-field bc-field"' in JS and "field.appendChild(els.textarea)" in JS
    # №5: главная кнопка шага прилипает к низу шторки
    assert re.search(r"\.bc-body > \.bk-btn--primary\.bk-btn--block \{\s*position: sticky; bottom: 0;", css)
    # №6: в карточке «Мои обращения» статус один раз (.bk-statusline), полоса этапов — в «Подробнее»
    card = JS.split('list.appendChild(h("li", { "class": "bk-card bc-mine__card"', 1)[1].split("body.appendChild(list)", 1)[0]
    assert "statusLine(item)" in card and "stepsBar(" not in card and "statusBadge(" not in card
    details = JS.split("function detailsBlock(item, open)", 1)[1].split("function historyTitle", 1)[0]
    # Дизайн-марафон: этапы в «Подробнее» — вертикальная лента (точки на линии), вместо полосы и списка истории.
    assert '"bk-details bc-more"' in details and '"bc-updates bc-history bc-timeline"' in details and "nextStage(item)" in details
    # №7 и правила 2, 4: ни лайма, ни бежевого, ни веса 700 в своих стилях. Эталон A (13 окт): лайм — только плитка «+»
    # у «Сообщить о проблеме» (.fab i эталона); больше нигде.
    for text in (css, kit):
        low = text.lower()
        assert low.count("#d7f57c") == (1 if text is css else 0), "лайм только у плитки «+»"
        assert ":where(.bc-fab__mark) { width: 26px; height: 26px; border-radius: 8px; background: #D7F57C;" in css   # запасной к .bk-fab__ic
        assert not any(c in low for c in ("#f1fbd3", "#f7f8f4", "#f1efe6")), "лайм/бежевый"
        assert "font-weight: 700" not in text


def test_inbox_shows_rude_mark_and_original_text():
    """R10 B-064: «Обращения» — пометка moderation.rude (ключ R11, как в карточке R07) в строке и текст-оригинал в карточке."""
    assert 'group.rude ? h("span", { "class": "bk-tag bc-tag--rude" }, t("moderation.rude"))' in LIST_JS
    assert '"bc-staff__text"' in STAFF_JS and 'current.moderation && current.moderation.rude' in STAFF_JS
    s = strings()
    assert s["ru"]["moderation.rude"] == "Содержит грубые слова" and s["kk"]["moderation.rude"] == "Дөрекі сөздер бар"


def test_inbox_without_staff_login_asks_to_sign_in():
    """R11 разбор FINAL-3 №1 (patch R09_inbox_need_staff, взят из сборки R01): 401/403 — «Войдите как сотрудник акимата»,
    а не «Нет связи»; марафон (R11 INTEGRATION 9.3 b, 10.3): одно состояние на все разделы — иллюстрация staff,
    подсказка «Учётную запись выдаёт администратор.», «Войти» — главная (единственная кнопка экрана); №12 и 9.3 a —
    заголовок «Обращений» 28 / 600."""
    assert 'res.status === 401 || res.status === 403 ? "staff" : true' in LIST_JS
    assert 't("proposal.need_staff")' in LIST_JS and 't("staff.login.submit")' in LIST_JS
    staff = LIST_JS.split('if (state.error === "staff") {', 1)[1].split("if (state.error) {", 1)[0]
    assert 'art("staff", "user")' in staff and 't("staff.login.note")' in staff and '"bk-btn bk-btn--primary"' in staff
    # R11 16.3: при ui-kit с BirgeUI.loginState — одно общее состояние ui-kit; своё — запасное того же вида.
    assert "window.BirgeUI.loginState(holder, openLogin);" in staff
    s = strings()
    assert s["ru"]["proposal.need_staff"] == "Войдите как сотрудник акимата" and s["kk"]["staff.login.submit"] == "Кіру"
    assert s["ru"]["staff.login.note"] == "Учётную запись выдаёт администратор." and s["kk"]["staff.login.note"] == "Тіркелгіні әкімші береді."
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    # Эталон A: заголовок листа 19/600 (был 28 по R11 9.3 a — эталон 13 окт важнее).
    assert re.search(r"\.bc-inbox__title \{[^}]*font-size: var\(--fs-title, 19px\); font-weight: var\(--fw-semi, 600\)", css)


def test_glass_only_on_mine_panel():
    """R11 GLASS.md (решение владельца 12 окт), R09: «Мои обращения» — стекло ui-kit (.bk-glass), мастер жалобы и формы
    сотрудника — непрозрачные; без ui-kit со стеклом — белый (:where, нулевая специфичность); под стеклом одна панель."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    assert 'panel.classList.toggle("bk-glass", mine);' in JS
    assert 'document.documentElement.classList.toggle("bc-mine-open", mine);' in JS
    assert '.bc-panel:not(.bk-glass) { background: var(--c-surface, #fff);' in css           # мастер — непрозрачный
    assert ':where(.bc-panel.bk-glass) { background-color: var(--glass-solid, #fff);' in css   # запасной белый
    assert "html.bc-mine-open body.civic-mode .civic-panel,\nhtml.bc-open body.civic-mode .civic-panel { visibility: hidden; }" in css
    assert ".bk-glass .bc-staff__form { background: var(--c-surface, #fff);" in css            # формы сотрудника
    assert ".bc-inbox__list { list-style: none; margin: 0; padding: 4px; background: var(--c-surface, #fff);" in css  # список «Обращений» — непрозрачный
    for media in ("prefers-reduced-transparency: reduce", "@supports not ((-webkit-backdrop-filter", ".bk-glass-off .bc-panel.bk-glass .bc-head"):
        assert media in css
    # Главная кнопка и тосты — не стекло.
    assert "bk-glass" not in JS.split('els.fab = h("button"', 1)[1].split(");", 1)[0]


def test_design_marathon_resident_path():
    """DESIGN_MARATHON R09 (12–14 окт): успех с галочкой и без «Шаг 5 из 5», шторка шагов 4–5 по содержимому, мягкая
    смена шага, лента статусов, три большие кнопки «Проблема решена?» (главная одна), «исправлено» службы — не
    «Исправлено», крупные карточки категорий, пустые состояния со значком; всё движение — с prefers-reduced-motion."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    assert "if (success) panel.appendChild(successMark());" in JS and 'if (!mine && state.step !== 5) {' in JS
    assert '(state.step === 3 ? "full" : "fit")' in JS and '.bc-panel[data-snap="fit"] { height: auto;' in css
    assert 'body.classList.add("bc-body--enter");' in JS and "@keyframes bc-step-fwd" in css
    verify = JS.split("function verifyCard(item, primary)", 1)[1].split("function renderWaitCheck", 1)[0]
    assert verify.count("bk-btn--block") == 3 and verify.count("bk-btn--primary") == 1 and '"bc-link"' not in verify
    assert 'item.status === "fixed" ? t("mine.update.fixed")' in JS
    assert ".bc-panel .bk-catgrid > button { min-height: 64px;" in css
    assert ".bc-panel .bk-empty > .ic, .bc-panel .bk-error > .ic" in css
    reduced = "".join(css.split("@media (prefers-reduced-motion: reduce)")[1:])   # все такие блоки
    for anim in (".bc-body--enter", ".bc-success__tick", ".bc-mine__card--verified-now"):
        assert anim in reduced
    # Срочный баннер — сразу под полем текста, до категорий.
    text_step = JS.split("function renderText(body)", 1)[1].split("// ---------------------------------------------------------------- шаг 4", 1)[0]
    assert text_step.index("els.emergencyBox = h(") < text_step.index("els.categoryBox = h(")


def test_design_marathon_round7_r11_edits():
    """Марафон, круг 7 — правки R11 для R09 (INTEGRATION 9.3 d/e, 10.3, 11.6, 12.2, D-1, D-5, D-7)."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    # 10.3: «нет связи» — иллюстрация offline ui-kit (запасной — значок), общая фраза, ⟳ в «Повторить» у обоих экранов.
    # Поправка владельца П1 (15 окт): вместо рисунков ill-* — значок набора R11 48 px той же толщины линий.
    assert 'function illustration(name, fallback)' in JS and '"ic ic--48 bc-state-ic"' in JS and "illustration: illustration," in JS
    assert 'illustration("offline", "wifi-off")' in JS and 'art("offline", "wifi-off")' in LIST_JS
    assert JS.count('t("common.state.network_text")') == 1 and LIST_JS.count('t("common.state.network_text")') == 1
    assert 't("mine.error.hint")' not in JS + LIST_JS
    err = LIST_JS.split("if (state.error) {", 1)[1].split("return;", 1)[0]
    assert 'C().icon("refresh")' in err
    s = strings()
    assert s["kk"]["common.state.network_text"] == "Интернетті тексеріп, қайталап көріңіз."
    # 9.3 d: галочка успеха — геометрия ill-done (круг r 8.5, «✓» m8.2 12.3…) с классами bk-ill bk-check-draw, рисуется.
    mark = JS.split("function successMark()", 1)[1].split("// ----", 1)[0]
    assert '"bk-check-draw bc-success__mark"' in mark and '"m8.2 12.3 2.6 2.6 5-5.4"' in mark and '"8.5"' in mark
    assert ".bc-success__mark .bc-success__tick { stroke-dasharray: 12;" in css
    # 9.3 e: под прилипшей «Далее» чип в фокусе виден.
    assert "scroll-padding-bottom: 80px;" in css
    # 11.6: ноль у вкладки не показываем.
    assert '"data-zero": n ? null : ""' in LIST_JS and ".bc-inbox__count[data-zero] { display: none; }" in css
    # 12.2: «Сообщить о проблеме» на ≥ 761 — без transform (сжатие на месте); области — через right.
    fab = css.split(".bc-fab {", 1)[1].split("}", 1)[0]
    assert "transform" not in fab and "left: 50%" not in fab
    assert ".bc-fab { left: 0; right: 0; margin-inline: auto; width: max-content; transform: none; }" in css
    assert "translateX(-50%)" not in css and "body.civic-mode .bc-fab { right: 56px; }" in css
    # D-1: колонка «Обращений» 720.  D-7: скелетон на стекле — белая карточка с волосяной линией.
    assert ".bc-inbox { display: flex; flex-direction: column; gap: 12px; max-width: 720px;" in css
    assert ".bk-glass .bc-skel-card { background: var(--c-surface, #fff); box-shadow: inset 0 0 0 1px rgba(16, 24, 22, .08); }" in css
    # D-5: «Пример» — одна сноска под списком; метка — у раскрытой карточки и у похожей на шаге «Я тоже».
    assert 'h("p", { "class": "bk-footnote bc-demo-note" }, t("common.tag.demo_hint"))' in JS
    assert 'h("p", { "class": "bk-footnote bc-demo-note" }, t("common.tag.demo_hint"))' in LIST_JS
    mine_card = JS.split('list.appendChild(h("li", { "class": "bk-card bc-mine__card"', 1)[1].split("detailsBlock(item, focused)", 1)[0]
    assert "bk-tag--demo" not in mine_card and 'item.demo) more.appendChild(h("span", { "class": "bk-tag bk-tag--demo bc-more__demo" }' in JS
    assert "bk-tag--demo" not in LIST_JS.split('var head = h("button"', 1)[1].split("var li = ", 1)[0]
    assert 'match.demo ? h("span", { "class": "bk-tag bk-tag--demo" }' in JS   # похожая на шаге 4 — с меткой
    assert s["ru"]["common.tag.demo_hint"] == "Пример для показа, не настоящие данные"


def test_design_marathon_round8_laptop_panel_hugs_content():
    """Марафон, круг 8: на ноутбуке панель R09 по содержимому на всех шагах и в «Моих обращениях» (как карточка
    Apple Maps): шаг 3 и короткий список не тянут пустой столб до низа экрана; длинное прокручивается внутри."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    block = css.split("@media (min-width: 1024px) {\n  .bc-panel { bottom: auto;", 1)
    assert len(block) == 2 and "max-height: calc(100vh - var(--header-h, 64px) - 24px); }" in block[1].split("}", 1)[0] + "}"
    assert '.bc-panel:not([data-step="mine"])[data-snap="peek"]' not in css
    # Телефон: список «Моих обращений» — шторка по содержимому (fit), загрузка — половина, пусто / нет связи — низкая.
    assert '(state.mine ? "fit" : "half")' in JS


def test_design_marathon_round9_r10_circle2():
    """Марафон, круг 9 — замечания R10 (DESIGN_REVIEW круг 2) к R09: B-070 одна главная кнопка при карточке места и на
    ноутбуке; B-071 тип места не дважды; пример «что сделали» — строкой под полем; одна левая линия текста в карточке
    «Моих обращений»; отступы по сетке 4/8."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    # B-070: правило не внутри @media телефона.
    head = css.split("@media", 1)[0]
    assert "body:has(.r07-card) .bc-fab { display: none; }" in head and css.count("body:has(.r07-card) .bc-fab") == 1
    # B-071: показ подписи без повтора типа.
    assert "function dedupeKind(label)" in JS and "if (label) label = dedupeKind(label);" in JS
    # Пример под полем «Что сделали» в обеих формах, без placeholder.
    assert STAFF_JS.count('"bc-meta bc-staff__hint"') == 2 and 'placeholder: t("staff.fixed.what_hint")' not in STAFF_JS
    # Подсказки полей — через aria-describedby (не placeholder): «что сделали» ×2, заметка части службы, «кого ждём» (р. 15).
    assert STAFF_JS.count('"aria-describedby"') == 4
    # Одна левая линия (эталон A, .card): плитка 48 и название рядом; всё ниже шапки — от левого поля карточки;
    # пояснение статуса — под словом (иконка ui-kit 14 + 8).
    assert ".bc-mine__status .bk-statusline__note { padding-left: 22px;" in css and ".bc-mine__head { display: flex; align-items: flex-start; gap: 12px; }" in css
    assert '"bk-tile bc-mine__tile"' in JS and '"bc-meta bc-mine__sub"' in JS and '"bc-mine__due"' in JS
    # Отступы 6/10/14 px в правилах R09 больше не встречаются (кроме смещений точек ленты).
    import re as _re
    # Исключение — «Сообщить о проблеме»: промежуток 10 px взят из эталона A (.fab gap: 10px).
    off = [m.group(0) for m in _re.finditer(r"(?:padding|gap|column-gap)(?:-[a-z]+)?: [^;]*\b(?:6|10|14)px", re.sub(r":where\([^{]*\{[^}]*\}", "", css.replace("padding: 0 20px; gap: 10px;", "").replace("display: flex; align-items: center; gap: 10px; flex: 1;", "")))]
    assert not off, off
    # R11 16.4: ряд вкладок «Обращений» — .bk-scroll-x с затуханием края ui-kit.
    assert '"bk-chips bk-scroll-x bc-inbox__tabs"' in LIST_JS and "window.BirgeUI.scrollFade(bar)" in LIST_JS


def test_reference_a_r09():
    """Эталон A (13 окт, research/round-14/design): кнопка «Сообщить о проблеме» — .bk-fab ui-kit с лаймовой плиткой;
    мастер — карточка слева под поиском (--panel-w 388, радиус 18, выезд слева); шторка телефона — радиус 26, ручка 38×5;
    «Мои обращения» — плотное стекло; статус значком ui-kit (BirgeUI.statusIcon) или своим тем же; «Обращения» как Linear."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    assert 'h("button", { "class": "bk-fab bc-fab"' in JS and '"bk-fab__ic bc-fab__mark"' in JS
    assert "left: var(--gap-edge, 20px);" in css and "width: var(--panel-w, 388px);" in css and "@keyframes bc-in-left" in css
    assert "border-radius: var(--r-sheet, 26px) var(--r-sheet, 26px) 0 0;" in css and "width: 38px; height: 5px;" in css
    assert 'panel.classList.toggle("bk-glass--strong", mine);' in JS
    assert "window.BirgeUI.statusIcon(status, 14)" in JS and '"text/html"' in JS and ".innerHTML" not in JS.split("function statusIcon", 1)[1].split("function statusBadge", 1)[0]
    # Linear: группы по статусу, меню статуса в строке, мгновенный отклик, события «список ↔ карта».
    for needle in ('"bc-inbox__group"', 'bc-inbox__ghead"', '"bk-llist bc-inbox__list"', '"bk-lrow bc-inbox__line"', '"bk-lrow__st bc-inbox__status',
                   "function statusControl(group)", "function take(group)",
                   '"birge:target-hover"', 'state.tab === "all"', "function onKey(e)"):
        assert needle in LIST_JS, needle
    assert ".bc-inbox__row { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; min-height: var(--tap, 44px);" in css
    # Мгновенный отклик: скелетон — только через 150 мс; «Мои обращения» из памяти при повторном открытии.
    assert "}, 150);" in LIST_JS and "}, 150);" in JS and "var mineCache = null;" in JS
    # Правило 2 (R01 — палитра Ctrl+K, R09 — смена статуса): команды «Взять в работу — место» и «Отметить исправленным — место».
    cmd = LIST_JS.split("function commands(opts)", 1)[1].split("function mount(root, opts)", 1)[0]
    assert 't("heat.take") + " — " + place' in cmd and 't("heat.mark_fixed") + " — " + place' in cmd and "if (g.demo && !g.world) return;" in cmd
    assert '"birge:inbox-open"' in LIST_JS and '"birge:inbox-changed"' in LIST_JS and "function takePending()" in LIST_JS
    # «Рядом с вами» (шторка телефона R07/R01): обращения жителя, ждущие его проверки, — waitingChecks().
    assert "waitingChecks: waitingChecks," in JS and 'return item.can_verify;' in JS.split("function waitingChecks()", 1)[1].split("return {", 1)[0]
    # Плотное стекло «Моих обращений» поверх правила оболочки — и запасные виды белые; серый текст — стеклянный (≥ 4,5 : 1).
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    assert "body.civic-mode .bc-panel.bk-glass.bk-glass--strong { background-color: var(--glass-strong, rgba(255, 255, 255, .86));" in css
    assert "--c-text-2: var(--glass-text-2, #3f4a46); }" in css
    assert "html.bk-glass-off body.civic-mode .bc-panel.bk-glass.bk-glass--strong { background-color: var(--glass-solid, #fff); }" in css
    # Шторка «Рядом с вами» (решение R11 §21.2): разметка ui-kit, данные /heat, 3 ближайших, ✓ «проверьте», «Все горячие места».
    near = JS.split("function mountNear(root, opts)", 1)[1].split("function mount(opts)", 1)[0]
    for needle in ('"bk-phsheet bk-glass bk-glass--strong bk-glass--sheet bc-near"', 'request("GET", "/heat?days=30&zoom=15")',
                   't("home.near.title")', 't("home.near.check")', 't("home.near.all_hot")', 't("home.near.empty")', '"bk-hot__cnt"',
                   'opts.map.on("moveend", onMove)', "BirgeUI.langSwitch(lang, { text: true })"):
        assert needle in near, needle
    assert "mountNear: mountNear" in JS
    s = strings()
    assert s["ru"]["home.near.title"] == "Рядом с вами" and s["kk"]["home.near.title"] == "Сіздің маңайыңызда"


def test_reference_a_r09_round2():
    """Эталон A, круг 2 (R11 §22.3 c, R10 §9): «×» одной толщины с остальными значками; повторное открытие «Моих
    обращений» — сразу из памяти, и пустой список тоже."""
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    # Правило 6 Linear: значок 16 при линии 2.25 — видимая 1,5 px (как значки 20 при линии 1.5–1.75), не 1,3.
    assert ".bc-x .ic { width: 16px; height: 16px; stroke-width: 2.25; }" in css
    assert ".bc-fab__mark .ic { width: 16px; height: 16px; stroke-width: 2.25; }" in css and "stroke-width: 2.4" not in css
    load = JS.split("function loadMine(focusCode, focusEvent)", 1)[1].split("function focusCard()", 1)[0]
    assert "var cached = mineCache;" in load and "items.length ? mineCache" not in load
    # Без связи при списке в памяти — «Нет связи» над списком, а не экран ошибки вместо него.
    assert "if (cached) { state.mineStale = true; render(); return; }" in load


def test_reference_a_r09_motion_rule6():
    """Правило 6 Linear: анимации 150–250 мс — у движений R09 длительность из --t-base / --t-slow или 150–250 мс
    (задержки ступенек списка и галочки после круга — не длительность)."""
    import re
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    for decl in re.findall(r"(?:animation|transition)\s*:\s*([^;}]+)", css):
        decl = re.sub(r"var\(--[\w-]+,\s*([^()]+)\)", r"\1", decl)              # var(--t-slow, 250ms) → 250ms
        decl = re.sub(r"cubic-bezier\([^()]*\)", "ease", decl)
        for part in decl.split(","):
            words = part.split()
            durations = [w for w in words if re.fullmatch(r"\d+ms", w)]
            if durations:   # первая длительность в части — продолжительность, вторая — задержка
                ms = int(durations[0][:-2])
                assert 150 <= ms <= 250, part
    assert "bc-flash var(--t-slow, 250ms)" in css and "bc-rise var(--t-slow, 250ms)" in css
