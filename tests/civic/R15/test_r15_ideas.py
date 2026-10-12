"""R15: идеи жителей и «Работы и отключения» (волна 2 п. 7, владелец R06; ui/civic_store/{ideas,nearby}.py).

Функции модуля вызываются так, как их вызывает шлюз R01 (v2.create_idea(body, context), v2.decide_idea(id, body,
context, principal)); сотрудник — настоящая сессия R02 (cookie + CSRF) на временной базе.
- S30 (важно): «Отклонить» без проверки делает текст идеи публичным; отклонённую идею и идею-проект нельзя скрыть.
- S31: телефон, почта, ИИН в тексте идеи принимаются — идею увидят все.
- S32: очередь проверки на весь город (300) заполняет скрипт с десятков адресов — приём закрыт для всех.
- S33: формы сотрудника отвечают 500 на неверный тип (район списком, вид объекта списком, год 9999).
Ревью R06 ae9ba29 (ветка claude/r14-R06), 12 окт: агент R15, воспроизведено и перепроверено R15.
"""

from __future__ import annotations

import json

import pytest

from r15_common import need_module, xfail

PASSWORD = "Tulpar-Bayterek-2026"
POINT = {"type": "Point", "coordinates": [71.35, 51.13]}


def ctx(cookie=None, csrf=None, ip="127.0.0.1"):
    auth = need_module("ui.civic_store.auth")
    headers = {"Host": "127.0.0.1:8501"}
    if cookie:
        headers["Cookie"] = f"{auth.COOKIE_NAME}={cookie}"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": ip, "host_allowed": True, "is_same_origin": True, "is_https": False}


@pytest.fixture()
def r06(tmp_path, monkeypatch):
    need_module("ui.civic_store.ideas")
    auth = need_module("ui.civic_store.auth")
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 10, raising=False)
    monkeypatch.setattr(auth, "SCRYPT_P", 1, raising=False)
    service_mod = need_module("ui.civic_store.service")
    v2 = need_module("ui.civic_store.v2")
    svc = service_mod.CivicService(str(tmp_path / "civic.sqlite3"))
    svc.accounts.create_user("r15ideas", PASSWORD)
    v2.bind(svc)
    reply = svc.handle("POST", "/api/civic/v1/session/login", None,
                       json.dumps({"username": "r15ideas", "password": PASSWORD}).encode(), ctx())
    cookie = reply["headers"]["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
    v2.staff_ctx = ctx(cookie, reply["body"]["data"]["csrf_token"])
    return v2


def body_of(result):
    return result[1] if isinstance(result, tuple) else result


def new_idea(v2, n=1, ip="10.0.0.1", **over):
    payload = {"title": "Площадка у дома", "description": "Нужна детская площадка во дворе", "geometry": POINT,
               "device_id": "device-r15-idea-%06d" % n}
    payload.update(over)
    return body_of(v2.create_idea(payload, context=ctx(ip=ip)))["item"]["id"]


def public_ids(v2):
    return [item["id"] for item in body_of(v2.list_ideas(context=ctx()))["items"]]


def status_of(exc):
    return getattr(exc, "status", None) or getattr(exc, "http_status", None)


@xfail("S30")
def test_rejected_unpublished_idea_text_stays_private(r06):
    idea = new_idea(r06)
    r06.decide_idea(idea, {"action": "reject", "reason": "Нет места"}, context=r06.staff_ctx)
    assert idea not in public_ids(r06), "отклонённая без публикации идея — в публичном списке"
    with pytest.raises(Exception) as exc:
        r06.get_idea(idea, context=ctx())
    assert status_of(exc.value) == 404


@xfail("S30")
def test_decided_idea_can_still_be_hidden(r06):
    idea = new_idea(r06)
    r06.decide_idea(idea, {"action": "publish"}, context=r06.staff_ctx)
    r06.decide_idea(idea, {"action": "reject", "reason": "Нет места"}, context=r06.staff_ctx)
    r06.decide_idea(idea, {"action": "hide", "reason": "Просьба автора: личные данные"}, context=r06.staff_ctx)
    assert idea not in public_ids(r06)


def test_published_idea_is_public_and_hidden_is_not(r06):
    """Обратная сторона S30: обычный путь «опубликовать → видно всем», «скрыть на проверке → не видно» не сломан."""
    shown, hidden = new_idea(r06, 1), new_idea(r06, 2)
    r06.decide_idea(shown, {"action": "publish"}, context=r06.staff_ctx)
    r06.decide_idea(hidden, {"action": "hide", "reason": "Не по теме"}, context=r06.staff_ctx)
    ids = public_ids(r06)
    assert shown in ids and hidden not in ids


@xfail("S31")
@pytest.mark.parametrize("text", ["Звоните +7 701 123 45 67", "пишите a.k@mail.kz", "мой ИИН 900101300123"])
def test_idea_with_contact_or_iin_is_refused(r06, text):
    with pytest.raises(Exception) as exc:
        new_idea(r06, description="Площадка во дворе. " + text)
    assert status_of(exc.value) == 422, exc.value


def test_idea_with_house_numbers_and_years_is_accepted(r06):
    """Обратная сторона S31: обычные числа (дом, год, время) — не личные данные."""
    assert new_idea(r06, description="Двор дома 12 на Кабанбай батыра, с 2024 года без лавочек, до 23:00")


@xfail("S32")
def test_full_review_queue_does_not_lock_out_new_residents(r06):
    ideas = need_module("ui.civic_store.ideas")
    limit = ideas.REVIEW_QUEUE_MAX
    for n in range(limit):                       # скрипт: по 5 идей с каждого адреса (лимит адреса — 5 в час)
        new_idea(r06, n, ip="10.66.%d.%d" % (n // 5 // 250, n // 5 % 250))
    with pytest.raises(Exception):               # тот же скрипт дальше — отказ
        new_idea(r06, limit + 1, ip="10.66.0.0")
    assert new_idea(r06, limit + 2, ip="192.0.2.77"), "новый житель с нового адреса не может подать идею"


OUTAGE = {"type": "outage", "utility": "water", "source": "water", "district": "nura", "title": "Нет воды",
          "zone": "дома 1–5", "start": "2026-10-13T10:00", "end": "2026-10-13T18:00",
          "why": {"problem": "Ремонт сети", "reason": "Авария", "result": "Вода будет", "inconvenience": "8 часов"}}


def test_outage_form_accepts_valid_input(r06):
    """Обратная сторона S33: верная форма отключения проходит (иначе 422 ниже ничего бы не значил)."""
    status, data = r06.create_work(dict(OUTAGE), context=r06.staff_ctx)
    assert status == 201, data


@xfail("S33")
@pytest.mark.parametrize("call", ["work_district_list", "work_year_9999", "project_kind_list"])
def test_staff_forms_answer_422_not_500(r06, call):
    with pytest.raises(Exception) as exc:
        if call == "work_district_list":
            r06.create_work(dict(OUTAGE, district=["nura"]), context=r06.staff_ctx)
        elif call == "work_year_9999":
            r06.create_work(dict(OUTAGE, start="9999-12-31T20:00-12:00", end="9999-12-31T23:00-12:00"),
                            context=r06.staff_ctx)
        else:
            idea = new_idea(r06)
            r06.decide_idea(idea, {"action": "publish"}, context=r06.staff_ctx)
            r06.decide_idea(idea, {"action": "project", "kind": ["square"]}, context=r06.staff_ctx)
    assert status_of(exc.value) in (400, 422), repr(exc.value)
