"""R15: «Службы» и «Нужно решение акима» R08 (волна 2 п. 5, 8; ui/civic_akim) — публичное чтение и запись сотрудника.

Шлюз R01 (patch R08 r01_wave2_r08.patch) отдаёт GET /akim/routing и GET /akim/summary всем без входа, а запись
(PUT /akim/routing, POST /akim/decisions/{id}) — функциям R08 с principal сотрудника (staff=True: сессия + CSRF).
- S28: логин сотрудника, который правил службы или выбрал вариант, не должен попадать в публичные ответы.
- S29: функции записи сами отказывают без principal (защита в глубину, как S17 у R06).
Модуль вызывается так же, как его вызывает шлюз; файлы правок и выборов — во временной папке.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from r15_common import need_module, xfail

STAFF = "r15markerstaff"
PRINCIPAL = {"username": STAFF, "role": "editor"}
TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 12, 10, 0, tzinfo=TZ)
PREFIX = "/api/civic/v2"


@pytest.fixture()
def akim(tmp_path, monkeypatch):
    api = need_module("ui.civic_akim.api")
    if not hasattr(api, "routing_update"):
        pytest.skip("в этой сборке нет функций записи R08 для шлюза (волна 2)")
    routing = need_module("ui.civic_akim.routing")
    decisions = need_module("ui.civic_akim.decisions")
    monkeypatch.setattr(routing, "OVERRIDE_PATH", tmp_path / "routing.json")
    monkeypatch.setattr(decisions, "STORE_PATH", tmp_path / "decisions.json")
    return api


def _service():
    """«Картина дня» на одной просроченной жалобе, которой нужно решение акима (два варианта от службы)."""
    akim_pkg = need_module("ui.civic_akim")
    created = NOW - timedelta(days=20)
    record = {"id": "c-r15-decision-1", "created_at": created.isoformat(), "text": "секретный текст жителя", "lang": "ru",
              "category": "roads", "category_source": "resident", "model": None, "point": [71.415, 51.1],
              "target": {"kind": "area", "id": "cell-r15-1"}, "district": "nura", "status": "in_progress",
              "status_history": [{"at": created.isoformat(), "status": "new"},
                                 {"at": (created + timedelta(days=1)).isoformat(), "status": "in_progress"}],
              "metoo": 2, "duplicate_of": None, "demo": False,
              "delay": {"reason_code": "needs_decision", "problem_ru": "Проблема", "blocker_ru": "Блокер",
                        "decision_ru": "Решить", "options": [{"ru": "Вариант 1"}, {"ru": "Вариант 2"}]}}
    return akim_pkg.AkimService(heat=False, records=lambda since: [record], objects=None, proposals=None,
                                clock=lambda: NOW)


@xfail("S28")
def test_public_routing_table_has_no_staff_login(akim):
    akim.routing_update({"rules": {"roads/marking": "road"}}, principal=PRINCIPAL)
    status, body = akim.handle_get(PREFIX + "/akim/routing", {})
    assert status == 200 and any(r["key"] == "roads/marking" and r["service"] == "road" for r in body["rules"])
    assert STAFF not in json.dumps(body, ensure_ascii=False)


@xfail("S28")
def test_public_summary_has_no_staff_login_of_decision(akim):
    service = _service()
    items = service.summary(now=NOW)["decisions"]["items"]
    if not any(i["id"] == "c-r15-decision-1" for i in items):
        pytest.skip("критерий «Нужно решение акима» в этой сборке другой")
    status, body = akim.handle_post(PREFIX + "/akim/decisions/c-r15-decision-1", {"option": 2}, staff=True, actor=STAFF,
                                    service=service)
    assert status == 200, body
    status, public = akim.handle_get(PREFIX + "/akim/summary", {}, service=service)
    assert status == 200
    item = next(i for i in public["decisions"]["items"] if i["id"] == "c-r15-decision-1")
    assert item["chosen"]["option"] == 2                    # выбор виден акиму и жителям
    assert STAFF not in json.dumps(public, ensure_ascii=False)


@xfail("S29")
@pytest.mark.parametrize("call", ["routing", "decision"])
def test_write_functions_refuse_without_staff_principal(akim, call, monkeypatch):
    """Шлюз даёт principal только маршрутам с staff=True; без него функция записи должна отказать (403).
    Сейчас без principal выбор акима записывается (by: null), правка служб — тоже."""
    monkeypatch.setattr(akim, "default_service", _service)
    with pytest.raises(Exception) as exc:
        if call == "routing":
            akim.routing_update({"rules": {"roads/marking": "road"}})
        else:
            akim.decision_choose("c-r15-decision-1", {"option": 1})
    assert isinstance(exc.value, PermissionError) or getattr(exc.value, "status", None) == 403, exc.value


def test_resident_cannot_write_through_handlers(akim):
    """Старые обработчики R08 (handle_put/handle_post) отказывают не-сотруднику."""
    assert akim.handle_put(PREFIX + "/akim/routing", {"rules": {"roads": "road"}})[0] == 403
    assert akim.handle_post(PREFIX + "/akim/decisions/c-r15-decision-1", {"option": 1}, service=_service())[0] == 403


def test_routing_edit_rejects_unknown_service_and_long_names(akim):
    for body in ({"rules": {"roads": "nasa"}}, {"rules": {"../etc": "road"}},
                 {"services": {"road": {"ru": "<script>alert(1)</script>" * 20}}}):
        with pytest.raises(ValueError):
            akim.routing_update(body, principal=PRINCIPAL)
