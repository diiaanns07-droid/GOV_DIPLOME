"""R09 · раунд 15 · статические проверки экранов «несколько служб» (без браузера; браузер — joint_r09.cjs).

Ключи R11 для частей служб, ролей, причин передач — в ru и kk; причины передач — те же коды, что в joint.py;
поправка владельца П1 («без ИИ-слопа»): пустые состояния — значок R11 48 px, без больших рисунков и свечения."""

import re

from ui.civic_feedback.v2 import joint, lifecycle

from test_r09v2_frontend import JS, LIST_JS, STAFF_JS, WEB, strings


def test_dynamic_joint_keys_exist_in_both_languages():
    data = strings()
    keys = [f"joint.part.{s}" for s in joint.PART_STATUSES] + [f"joint.role.{r}" for r in joint.PART_ROLES] + \
           ["joint.by.operator", "joint.by.admin"] + [f"handoff.reason.{c}" for c in joint.HANDOFF_REASONS] + \
           [f"mine.update.{k}" for k in lifecycle.JOINT_UPDATE_KINDS] + [f"mine.changes.{k}" for k in lifecycle.JOINT_UPDATE_KINDS]
    for lang in ("ru", "kk"):
        missing = [k for k in keys if k not in data[lang]]
        assert not missing, (lang, missing)
    # Подписи причин в интерфейсе совпадают с теми, что сервер пишет в журнал передач (joint.HANDOFF_REASONS).
    for code, names in joint.HANDOFF_REASONS.items():
        assert data["ru"][f"handoff.reason.{code}"] == names["ru"]
        assert data["kk"][f"handoff.reason.{code}"] == names["kk"]


def test_reason_chips_and_part_statuses_match_server():
    chips = re.search(r'var REASONS = \[([^\]]+)\]', STAFF_JS).group(1)
    assert [c.strip(' "') for c in chips.split(",")] == list(joint.HANDOFF_REASONS)
    statuses = re.search(r'var PART_STATUSES = \[([^\]]+)\]', STAFF_JS).group(1)
    assert [c.strip(' "') for c in statuses.split(",")] == list(joint.PART_STATUSES)
    # Значки статуса частей: сделано — «служба сообщила» (кольцо с галочкой), не зелёное «проверено жителями».
    for code in (STAFF_JS, LIST_JS):
        assert 'done: "reported_fixed"' in code and "verified" not in re.search(r"PART_ICON = \{[^}]+\}|todo: \"new\", in_progress: \"in_progress\", done: \"reported_fixed\"", code).group(0)


def test_routes_used_by_screens():
    for action in ("handoff", "services", "part"):
        assert f'"/{action}"' in STAFF_JS
    assert '"/part"' in LIST_JS and '"service=" + encodeURIComponent' in LIST_JS and '"district=" + encodeURIComponent' in LIST_JS
    # Подсказка R04 — из route_hint записи (без запроса с экрана: 404 до подключения); черновик — только если готов.
    assert '"/route"' not in STAFF_JS and 'rawCall("/reply-draft"' in STAFF_JS and 'API + "/modules"' in STAFF_JS



def test_r17_agencies_filter_handoff():
    # R17 «Штаб ведомств» → «Открыть в «Обращениях»» (INTEGRATION R17 §4): sessionStorage + событие на document.
    assert '"birge.inbox.filter"' in LIST_JS and 'document.addEventListener("birge:inbox-filter", onFilter)' in LIST_JS
    assert 'document.removeEventListener("birge:inbox-filter", onFilter)' in LIST_JS      # снимается при destroy
    assert "sessionStorage.removeItem(FILTER_KEY)" in LIST_JS                              # фильтр берётся один раз

def test_amendment_p1_no_large_illustrations_no_glow():
    css = (WEB / "complaint.css").read_text(encoding="utf-8")
    assert "#ill-" not in JS and "#ill-" not in LIST_JS and "#ill-" not in STAFF_JS   # рисунки ui-kit не берём
    assert '"ic ic--48 bc-state-ic"' in JS                                             # значок R11 48 px
    assert "bc-glow" not in css and "glow" not in re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert ".bc-success__mark { width: 48px; height: 48px;" in css
    assert "width: 96px" not in css and "width: 80px; height: 80px" not in css               # прежние размеры рисунков
    # Без эмодзи в интерфейсе (П1, правило 4).
    emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
    for code in (JS, STAFF_JS, LIST_JS, (WEB / "complaint-strings.js").read_text(encoding="utf-8")):
        code = re.sub(r"(^|\s)//[^\n]*", "", re.sub(r"/\*.*?\*/", "", code, flags=re.S))   # комментарии — не интерфейс
        found = emoji.search(code)
        assert not found, code[max(0, found.start() - 60):found.end() + 20]
