"""R15: «Вопрос акиму» (волна 2 п. 9, владелец R13; ui/civic_qa, web/civic/qa) и его подключение к шлюзу R01.

Сервис вызывается так же, как его вызывает шлюз R01 (handle(method, path, query, body, principal, context)), на
временной SQLite; сотрудник — principal R02 (is_staff + check_csrf). Ревью R13 9db6dfb, 12 окт (агент R15,
воспроизведено и перепроверено R15).
- S34: шлюз не проверяет пометку staff=True у маршрутов-«сервисов» (R13 qa.publish/reject/answer, R09) — модерация
  держится только на проверке внутри модуля.
- S35 (важно): отвеченный вопрос с личными данными нельзя снять; подсказка «похоже на личные данные» пропускает
  «701 123 45 67», «8 (7172) 55-66-77», ИИН с пробелами.
- S36: «dev-same\\n» — новый id устройства (регулярное «$» пропускает перевод строки): второй голос с того же устройства.
- S37: новый вопрос не проверяет «с чужого сайта» сам (голос проверяет) — защита в глубину.
- S38: новые вопросы без суточного лимита с адреса: 480 в сутки, очередь модерации тонет.
- S39: ответ акима можно тихо переписать: дата прежняя, автор первого ответа и второй язык стираются.
- S40: без localStorage qa.js берёт новый id устройства на каждый запрос — «Поддержать» снова и снова.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from r15_common import ROOT, live_server, need_module, request, xfail

CTX = {"headers": {}, "host_allowed": True, "is_same_origin": True}
STAFF_CTX = dict(CTX, headers={"x-csrf-token": "tok"})


class Staff:
    role, is_staff = "editor", True

    def __init__(self, username="editor.one"):
        self.username = username

    def check_csrf(self, token):
        return token == "tok"


@pytest.fixture()
def qa(tmp_path):
    civic_qa = need_module("ui.civic_qa")
    now = [datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)]
    svc = civic_qa.make_service(str(tmp_path / "qa.sqlite3"), clock=lambda: now[0], demo=True)
    svc.r15_now, svc.r15_db = now, str(tmp_path / "qa.sqlite3")
    return svc


def call(svc, method, path, body=None, principal=None, ctx=CTX, query=""):
    reply = svc.handle(method, "/api/civic/v2" + path, query, body, principal, ctx)
    return reply["status"], reply["body"]


def ask(svc, text, device="device-r15-qa-000001"):
    status, body = call(svc, "POST", "/questions", {"text": text, "district": "nura", "device_id": device})
    assert status in (200, 201), body
    return body["question"]["id"]


def staff_items(svc, tab="queue"):
    return call(svc, "GET", "/questions/staff", principal=Staff(), ctx=STAFF_CTX, query="tab=" + tab)[1]["items"]


# --- S34: шлюз сам проверяет сотрудника и у маршрутов-«сервисов» ------------------------------------------

@xfail("S34")
def test_gateway_enforces_staff_flag_on_service_routes(tmp_path, monkeypatch):
    """Маршрут-«сервис» с staff=True: аноним получает отказ шлюза, а не ответ модуля (как у kind=function)."""
    ws = need_module("ui.web_server")
    if not hasattr(ws, "V2Handler"):
        pytest.skip("в этой сборке нет шлюза v2")
    monkeypatch.setattr(ws, "V2_ROUTES", ws.V2_ROUTES + (("POST", ("r15-probe",), "r15.probe"),))
    monkeypatch.setattr(ws, "V2_HANDLERS", dict(ws.V2_HANDLERS, **{"r15.probe": ws.V2Handler(
        "R09", ("ui.civic_feedback.v2.integration",), "make_service", kind="service", staff=True)}))
    with live_server(tmp_path) as srv:
        origin = "http://127.0.0.1:%d" % srv.server_address[1]
        status, _h, raw = request(srv, "POST", "/api/civic/v2/r15-probe", {}, headers={"Origin": origin})
    assert status in (401, 403), (status, raw[:200])


# --- S35: личные данные в отвеченном вопросе ----------------------------------------------------------------

@xfail("S35")
def test_answered_question_with_personal_data_can_be_taken_down(qa):
    qid = ask(qa, "Перезвоните насчёт парковки у дома, спросите Айгерим")
    call(qa, "POST", f"/questions/{qid}/publish", {}, Staff(), STAFF_CTX)
    call(qa, "POST", f"/questions/{qid}/answer", {"answer_ru": "Парковку разметят в мае."}, Staff(), STAFF_CTX)
    status, body = call(qa, "POST", f"/questions/{qid}/reject", {"reason": "personal_data"}, Staff(), STAFF_CTX)
    assert status == 200, body
    public = call(qa, "GET", "/questions", query="tab=answered")[1]["items"]
    assert qid not in [item["id"] for item in public]


@xfail("S35")
@pytest.mark.parametrize("text", ["Перезвоните 701 123 45 67 насчёт парковки", "Мой номер 8 (7172) 55-66-77, двор",
                                  "ИИН 950101 300 123, помогите с двором"])
def test_moderator_hint_flags_common_phone_and_iin_formats(qa, text):
    qid = ask(qa, text)
    item = next(i for i in staff_items(qa) if i["id"] == qid)
    assert item["pii"], (text, item["pii"])


def test_moderator_hint_ignores_dates_and_house_numbers(qa):
    qid = ask(qa, "Почему с 2024 года во дворе дома 12 до 23:00 шумят? 2026-10-12 12:30")
    item = next(i for i in staff_items(qa) if i["id"] == qid)
    assert not item["pii"], item["pii"]


# --- S36, S37: id устройства и «с чужого сайта» ---------------------------------------------------------------

@xfail("S36")
def test_newline_in_device_id_is_not_a_second_device(qa):
    first = call(qa, "POST", "/questions/q-demo-01/vote", {"device_id": "device-r15-same-0001"})
    assert first[0] in (200, 201), first
    status, body = call(qa, "POST", "/questions/q-demo-01/vote", {"device_id": "device-r15-same-0001\n"})
    assert status == 400 or not body.get("created"), (status, body)


@xfail("S36")
def test_gateway_device_id_rule_has_no_trailing_newline():
    ws = need_module("ui.web_server")
    if not hasattr(ws, "V2_DEVICE_ID"):
        pytest.skip("в этой сборке нет шлюза v2")
    assert not ws.V2_DEVICE_ID.match("device-r15-same-0001\n")


@xfail("S37")
def test_cross_site_question_is_refused_by_service_too(qa):
    status, _b = call(qa, "POST", "/questions", {"text": "Вопрос с чужого сайта про двор и парковку?",
                                                 "district": "nura", "device_id": "device-r15-x-000001"},
                      ctx=dict(CTX, is_same_origin=False))
    assert status == 403


# --- S38: суточный лимит новых вопросов с адреса -----------------------------------------------------------

@xfail("S38")
def test_new_questions_have_a_daily_limit_per_address():
    ws = need_module("ui.web_server")
    limits = getattr(ws, "V2_RATE_LIMITS", {}).get("qa.create")
    if limits is None:
        pytest.skip("в этой сборке нет маршрутов «Вопрос акиму» (R13)")
    daily = [count for window, count, _per_target in limits if window >= 86400]
    assert daily and min(daily) <= 50, limits


# --- S39: ответ акима не переписать тихо --------------------------------------------------------------------

@xfail("S39")
def test_rewritten_answer_is_marked_and_keeps_first_author(qa):
    answered = [i for i in call(qa, "GET", "/questions", query="tab=answered")[1]["items"] if i["answer"]]
    if not answered:
        pytest.skip("в демо R13 нет отвеченных вопросов")
    qid, first = answered[0]["id"], answered[0]["answer"]
    import sqlite3
    first_by = sqlite3.connect(qa.r15_db).execute("SELECT answered_by FROM qa_questions WHERE id = ?", (qid,)).fetchone()[0]
    qa.r15_now[0] += timedelta(days=30)
    call(qa, "POST", f"/questions/{qid}/answer", {"answer_ru": "Ремонт отменён."}, Staff("other.clerk"), STAFF_CTX)
    after = next(i for i in call(qa, "GET", "/questions", query="tab=answered")[1]["items"] if i["id"] == qid)["answer"]
    by = sqlite3.connect(qa.r15_db).execute("SELECT answered_by FROM qa_questions WHERE id = ?", (qid,)).fetchone()[0]
    assert after.get("edited_at"), "правка ответа не видна жителям"
    assert by == (first_by or "other.clerk"), "автор первого ответа стёрт"
    assert after.get("kk") == first.get("kk"), "второй язык ответа стёрт правкой одного языка"


# --- S40: id устройства без localStorage ---------------------------------------------------------------------

QA_JS = ROOT / "web" / "civic" / "qa" / "qa.js"


@xfail("S40")
def test_device_id_is_stable_without_local_storage():
    node = shutil.which("node")
    if not QA_JS.is_file() or not node:
        pytest.skip("нет web/civic/qa/qa.js (R13) или node")
    src = QA_JS.read_text(encoding="utf-8")
    start = src.index("function storage(")
    end = src.index("function toast(", start)
    probe = """
const root = { crypto: require("crypto").webcrypto, get localStorage() { throw new Error("SecurityError"); } };
const DEVICE_KEY = "birge.device";
const deviceId = new Function("root", "DEVICE_KEY", %s + "\\nreturn deviceId;")(root, DEVICE_KEY);
console.log(JSON.stringify([deviceId(), deviceId(), deviceId()]));
""" % json.dumps(src[start:end])
    done = subprocess.run([node, "-e", probe], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr[-500:]
    ids = json.loads(done.stdout.strip().splitlines()[-1])
    assert len(set(ids)) == 1 and re.match(r"^[A-Za-z0-9._:-]{8,128}$", ids[0]), ids
