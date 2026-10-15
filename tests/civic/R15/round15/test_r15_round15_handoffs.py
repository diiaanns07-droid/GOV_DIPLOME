"""R15 раунд 15 · R09 обращение для нескольких служб и передачи (ui.civic_feedback.v2) — THREATS_R15 §7.

Маршруты POST complaints/{id}/handoff · /services · /part (CONTRACT §5.1, §7) — через сервис R09 напрямую (kind="service"):
- только сотрудник с CSRF и своим Origin; житель-автор — тоже нет (T-R09-01, T-R09-05);
- срок ответа жителю передачей не обнуляется (T-R09-02);
- причина передачи и роль сотрудника — только акимату; жителю — «Передано: служба» (T-R09-03);
- службы — только из справочника, 1–3, одна ведущая; неверный тип — 422, не 500 (T-R09-04, S43-подобное);
- функции чтения для R17/R16 без текстов, устройств и точной точки (T-R09-07).
Нет маршрута у R09 (404 на действие сотрудника) — NOT_RUN.
"""

from __future__ import annotations

import pytest

from r15_round15 import (CSRF, DEVICES, MARK, STAFF_LOGIN, Svc, XSS, data, device_needles, dump, leaks, module,
                         not_run, staff_principal, xmarks)

AUTHOR, STRANGER = DEVICES[50], DEVICES[51]
POINT = [71.4123456, 51.1234567]
REASON = f"{MARK}: оператор сказал, что нам некогда"


@pytest.fixture()
def r09(tmp_path):
    svc = Svc(module("ui.civic_feedback.v2.integration", "R09"), tmp_path / "civic.sqlite3")
    yield svc
    getattr(getattr(svc.svc, "store", None), "close", lambda: None)()


def _complaint(r09, device=AUTHOR):
    status, body = r09.resident("POST", "/complaints", {"text": "Яма после раскопок у остановки, опасно",
                                                       "category": "roads", "point": list(POINT)}, device=device)
    assert status in (200, 201), body
    return data(body)["complaint"]


def _staff_get(r09, cid):
    status, body = r09.staff("GET", "/complaints/" + cid, csrf=None)
    assert status == 200, body
    return data(body)["complaint"]


def _need_route(status, body, what):
    """404 «Адрес API не найден» на действие сотрудника — маршрута у R09 в этой сборке ещё нет: NOT_RUN."""
    if status == 404 and "Адрес" in dump(body):
        not_run(f"у R09 в этой сборке нет маршрута {what}")


def _handoff(r09, cid, **over):
    body = {"to": "water", "reason": REASON}
    body.update(over)
    status, reply = r09.staff("POST", f"/complaints/{cid}/handoff", body)
    _need_route(status, reply, "complaints/{id}/handoff")
    return status, reply


@pytest.mark.parametrize("who", ["anon", "author", "stranger", "no_csrf", "bad_csrf", "cross_origin", "resident_role"])
def test_joint_actions_need_staff_with_csrf(r09, who):
    """T-R09-01/05: передать, добавить службу, отметить часть — только сотрудник с CSRF со своего сайта."""
    cid = _complaint(r09)["id"]
    status, reply = r09.staff("POST", f"/complaints/{cid}/services",
                              {"services": [{"service": "road", "role": "lead"}]})   # проверка, что маршрут есть
    _need_route(status, reply, "complaints/{id}/services")
    before = _staff_get(r09, cid)
    calls = [(f"/complaints/{cid}/handoff", {"to": "water", "reason": "Сначала замена трубы"}),
             (f"/complaints/{cid}/services", {"services": [{"service": "water", "role": "lead"},
                                                           {"service": "road", "role": "partner"}]}),
             (f"/complaints/{cid}/part", {"service": "road", "status": "done", "note": "Сделано посторонним"})]
    for path, body in calls:
        if who == "anon":
            status, out = r09.anon("POST", path, body)
        elif who in ("author", "stranger"):
            status, out = r09.resident("POST", path, body, device=AUTHOR if who == "author" else STRANGER)
        elif who == "no_csrf":
            status, out = r09.staff("POST", path, body, csrf=None)
        elif who == "bad_csrf":
            status, out = r09.staff("POST", path, body, csrf="q" * len(CSRF))
        elif who == "cross_origin":
            status, out = r09.staff("POST", path, body, origin=False)
        else:
            status, out = r09.staff("POST", path, body, principal=staff_principal(role="resident"))
        assert status in (401, 403), (who, path, status, out)
    after = _staff_get(r09, cid)
    keys = ("service", "services", "handoffs", "status")
    assert {k: after.get(k) for k in keys} == {k: before.get(k) for k in keys}, (before, after)


def test_handoff_keeps_the_resident_deadline(r09):
    """T-R09-02: срок ответа жителю после передачи — тот же (CONTRACT §5.1)."""
    complaint = _complaint(r09)
    due = _staff_get(r09, complaint["id"]).get("due_at")
    status, reply = _handoff(r09, complaint["id"])
    assert status == 200, reply
    status, _r = _handoff(r09, complaint["id"], to="road", reason="Вернули: сначала дорога")
    assert _staff_get(r09, complaint["id"]).get("due_at") == due


def test_handoff_reason_is_staff_only(r09):
    """T-R09-03: причина передачи («оператор сказал…») и логин/роль — не жителю; «Передано: служба» — можно."""
    complaint = _complaint(r09)
    cid = complaint["id"]
    status, reply = _handoff(r09, cid)
    assert status == 200, reply
    assert MARK in dump(_staff_get(r09, cid)), "у сотрудника причины нет — тест ничего не проверяет"
    views = [r09.resident("GET", "/complaints/" + cid, device=AUTHOR)[1],
             r09.resident("GET", "/complaints/" + cid, device=STRANGER)[1],
             r09.anon("GET", "/complaints")[1], r09.resident("GET", "/complaints/mine", device=AUTHOR)[1]]
    assert not leaks(views, [MARK, STAFF_LOGIN, "by_role", "reason"]), dump(views)[:600]


@pytest.mark.parametrize("services", [
    [{"service": "kgb", "role": "lead"}],
    [{"service": XSS, "role": "lead"}],
    [{"service": "road", "role": "lead"}, {"service": "road", "role": "partner"}],
    [{"service": "road", "role": "lead"}, {"service": "water", "role": "lead"}],
    [{"service": s, "role": "lead" if i == 0 else "partner"} for i, s in enumerate(("road", "water", "lighting", "heating"))],
    [{"service": "road", "role": "boss"}],
    pytest.param([{"service": ["road"], "role": "lead"}], marks=xmarks("S49")),
    "road", [], None,
])
def test_services_must_come_from_directory(r09, services):
    """T-R09-04: 1–3 службы из справочника CONTRACT §3, ровно одна ведущая; неверный тип — 422, не 500."""
    cid = _complaint(r09)["id"]
    try:
        status, reply = r09.staff("POST", f"/complaints/{cid}/services", {"services": services})
    except TypeError as exc:
        pytest.fail(f"TypeError -> 500 у шлюза: {exc}")
    _need_route(status, reply, "complaints/{id}/services")
    assert status in (400, 422), (services, status, reply)


@pytest.mark.parametrize("body", [{"to": "kgb", "reason": "Причина передачи"}, {"to": XSS, "reason": "Причина"},
                                  pytest.param({"to": ["water"], "reason": "Причина передачи"}, marks=xmarks("S49")),
                                  {"to": "water"},
                                  {"to": "water", "reason": "x"}, {"to": "water", "reason_code": "bribe"},
                                  {"to": "water", "reason": ["список"]}])
def test_handoff_input_is_validated(r09, body):
    """T-R09-04: служба назначения из справочника, причина — чип или строка; неверный тип — 422, не 500."""
    cid = _complaint(r09)["id"]
    try:
        status, reply = r09.staff("POST", f"/complaints/{cid}/handoff", body)
    except TypeError as exc:
        pytest.fail(f"TypeError -> 500 у шлюза: {exc}")
    _need_route(status, reply, "complaints/{id}/handoff")
    assert status in (400, 422), (body, status, reply)


@pytest.mark.parametrize("body", [{"service": "road", "status": "hacked"}, {"service": "police", "status": "done"},
                                  {"service": ["road"], "status": "done"}, {"service": "road", "status": ["done"]},
                                  {"service": "road", "status": "done", "note": ["x"]}])
def test_part_input_is_validated(r09, body):
    """T-R09-05: статус части — из списка, служба — из частей обращения; неверный тип — 422/404, не 500."""
    cid = _complaint(r09)["id"]
    status, reply = r09.staff("POST", f"/complaints/{cid}/services", {"services": [{"service": "road", "role": "lead"}]})
    _need_route(status, reply, "complaints/{id}/services")
    try:
        status, reply = r09.staff("POST", f"/complaints/{cid}/part", body)
    except TypeError as exc:
        pytest.fail(f"TypeError -> 500 у шлюза: {exc}")
    assert status in (400, 404, 409, 422), (body, status, reply)


def test_read_functions_for_neighbours_have_no_private_data(r09):
    """T-R09-07: части служб и журнал передач для R17 — без текста жалобы, устройств и точной точки."""
    integration = r09.mod
    fns = [getattr(integration, name, None) for name in ("service_parts", "handoffs")]
    if not any(callable(fn) for fn in fns):
        not_run("у R09 нет функций чтения service_parts / handoffs для R17")
    complaint = _complaint(r09)
    _handoff(r09, complaint["id"])
    out = []
    for fn in fns:
        if callable(fn):
            try:
                out.append(fn(str(r09.db_path), days=30))
            except TypeError:
                out.append(fn(str(r09.db_path)))
    text = dump(out)
    assert "Яма после раскопок" not in text and "71.4123456" not in text and "51.1234567" not in text, text[:500]
    assert not leaks(out, device_needles([AUTHOR]) + [STAFF_LOGIN]), text[:500]
