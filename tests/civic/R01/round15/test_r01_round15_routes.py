"""R01 раунд 15: маршруты API v2 «Бірге — вместе» (research/round-15/CONTRACT.md §7) в шлюзе ui/web_server.py.

Что проверяем:
- все строки таблицы §7 есть в V2_ROUTES / V2_HANDLERS, у каждой — роль и модуль из контракта;
- пока модуля роли нет, каждый новый маршрут отвечает 503 module_not_ready (модуль и роль в ответе);
- маршрут сотрудника без сессии — 401, с сессией без CSRF — 403; модуль при этом не вызывается;
- форма параметров адреса и тела проверяется шлюзом до модуля: 400, поле и понятный текст по-русски;
- запись жителя — с лимитом по адресу (429 и Retry-After);
- настоящий HTTP: 503 и 403 «чужой сайт» на новых адресах, /modules показывает новые маршруты.
Модули ролей подменяются (modules=...): тест не зависит от того, сданы ли R16, R17 и др. в этой сборке.
"""

from __future__ import annotations

import http.client
import json
import threading
import types

import pytest

from ui import web_server
from ui.web_server import (CivicV2Gateway, V2_HANDLERS, V2_HANDLERS_ROUND15, V2_RATE_LIMITS, V2_ROUTES,
                           V2_ROUTES_ROUND15)

CTX = {"headers": {}, "cookies": {}, "client_ip": "127.0.0.1", "host_allowed": True,
       "is_same_origin": True, "is_https": False, "host": "127.0.0.1"}
STAFF = dict(CTX, cookies={"s": "staff-session"}, headers={"x-csrf-token": "csrf-ok"})
STAFF_NO_CSRF = dict(CTX, cookies={"s": "staff-session"})
DEVICE = "device-r01-r15-0001"
RESIDENT = dict(CTX, headers={"x-birge-device": DEVICE})

# Таблица CONTRACT §7 раунда 15: (метод, путь, роль, модуль, функция).
CONTRACT = [
    ("GET", "together/initiatives", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/initiatives", "R16", "ui.civic_together", "make_service"),
    ("GET", "together/initiatives/{id}", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/initiatives/{id}/join", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/initiatives/{id}/leave", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/initiatives/{id}/support", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/initiatives/{id}/moderate", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/initiatives/{id}/report", "R16", "ui.civic_together", "make_service"),
    ("GET", "together/yards/{id}", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/yards/{id}/join", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/yards/{id}/leave", "R16", "ui.civic_together", "make_service"),
    # R16 [доп.] (INTEGRATION R16 §1): выбор двора, «старший по двору» и его проверка акиматом.
    ("GET", "together/yards", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/yards/{id}/captain", "R16", "ui.civic_together", "make_service"),
    ("POST", "together/yards/{id}/moderate", "R16", "ui.civic_together", "make_service"),
    ("GET", "together/updates", "R16", "ui.civic_together", "make_service"),
    ("GET", "agencies", "R17", "ui.civic_agencies", "make_service"),
    ("GET", "agencies/board", "R17", "ui.civic_agencies", "make_service"),
    ("GET", "agencies/joint", "R17", "ui.civic_agencies", "make_service"),
    ("GET", "agencies/handoffs", "R17", "ui.civic_agencies", "make_service"),
    ("GET", "incidents", "R17", "ui.civic_agencies", "make_service"),
    ("GET", "incidents/{id}", "R17", "ui.civic_agencies", "make_service"),
    ("POST", "incidents", "R17", "ui.civic_agencies", "make_service"),
    ("POST", "incidents/{id}/task", "R17", "ui.civic_agencies", "make_service"),
    ("POST", "incidents/{id}/update", "R17", "ui.civic_agencies", "make_service"),
    ("POST", "incidents/{id}/close", "R17", "ui.civic_agencies", "make_service"),
    ("GET", "incidents/updates", "R17", "ui.civic_agencies", "make_service"),
    ("POST", "complaints/{id}/handoff", "R09", "ui.civic_feedback.v2.integration", "make_service"),
    ("POST", "complaints/{id}/services", "R09", "ui.civic_feedback.v2.integration", "make_service"),
    ("POST", "complaints/{id}/part", "R09", "ui.civic_feedback.v2.integration", "make_service"),
    ("GET", "works-calendar", "R12", "engine.civic_geo.api", "handle"),
    ("GET", "works-conflicts", "R12", "engine.civic_geo.api", "handle"),
    ("GET", "heat/replay", "R07", "ui.civic_heat.api", "handle_get"),
    ("GET", "akim/board", "R08", "ui.civic_akim.api", "handle_get"),
    ("GET", "akim/week", "R08", "ui.civic_akim.api", "handle_get"),
    ("GET", "meetings", "R13", "ui.civic_meetings", "make_service"),
    ("GET", "meetings/{id}", "R13", "ui.civic_meetings", "make_service"),
    ("GET", "meetings/updates", "R13", "ui.civic_meetings", "make_service"),
    ("POST", "meetings", "R13", "ui.civic_meetings", "make_service"),
    ("POST", "meetings/{id}/order", "R13", "ui.civic_meetings", "make_service"),
    ("POST", "meetings/{id}/result", "R13", "ui.civic_meetings", "make_service"),
    ("POST", "meetings/{id}/register", "R13", "ui.civic_meetings", "make_service"),
    ("POST", "meetings/{id}/question", "R13", "ui.civic_meetings", "make_service"),
    ("POST", "route", "R04", "ui.civic_ml_api", "route"),
    ("POST", "reply-draft", "R04", "ui.civic_ml_api", "reply_draft"),
    ("POST", "moderate", "R04", "ui.civic_ml_api", "moderate"),
    ("POST", "assistant/ask", "R03", "agent.civic_assistant.api", "ask"),
    ("GET", "notifications", "R06", "ui.civic_store.v2", "list_notifications"),
    ("POST", "notifications/read", "R06", "ui.civic_store.v2", "read_notifications"),
    ("POST", "ideas/{id}/to-initiative", "R06", "ui.civic_store.v2", "idea_to_initiative"),
]
# «Кто может» из §7: сотрудник (сессия + CSRF).
STAFF_ROUTES = {
    ("POST", "together/initiatives/{id}/support"), ("POST", "together/initiatives/{id}/moderate"),
    ("POST", "together/yards/{id}/moderate"),
    ("GET", "agencies/board"), ("GET", "agencies/joint"), ("GET", "agencies/handoffs"),
    ("POST", "incidents"), ("POST", "incidents/{id}/task"), ("POST", "incidents/{id}/update"),
    ("POST", "incidents/{id}/close"),
    ("POST", "complaints/{id}/handoff"), ("POST", "complaints/{id}/services"), ("POST", "complaints/{id}/part"),
    ("GET", "works-calendar"), ("GET", "works-conflicts"), ("GET", "akim/board"), ("GET", "akim/week"),
    ("POST", "meetings"), ("POST", "meetings/{id}/order"), ("POST", "meetings/{id}/result"),
    ("POST", "reply-draft"), ("POST", "assistant/ask"), ("POST", "ideas/{id}/to-initiative"),
}
# Правильный пример каждого запроса (путь с id, адрес, тело).
SAMPLE = {
    "together/initiatives": ("", {"kind": "cleanup", "title": "Субботник во дворе", "device_id": DEVICE}),
    "together/initiatives/{id}": ("", {"device_id": DEVICE}),
    "together/yards/{id}": ("", {"device_id": DEVICE}),
    "together/updates": ("since=2026-10-11T00:00:00%2B05:00", None),
    "agencies/board": ("days=30&district=nura", None),
    "agencies/handoffs": ("days=7", None),
    "incidents": ("", {"kind": "blizzard", "title_ru": "Буран"}),
    "incidents/updates": ("since=2026-10-11", None),
    "works-calendar": ("from=2026-05-01&to=2026-07-31&district=nura&street=Кабанбай батыра", None),
    "works-conflicts": ("from=2026-05-01&to=2026-07-31", None),
    "heat/replay": ("from=2026-10-01&to=2026-10-15&step=day&category=snow_ice&district=nura", None),
    "akim/week": ("date=2026-10-16", None),
    "meetings/updates": ("since=2026-10-11T10:00:00Z", None),
    "route": ("", {"text": "Яма после раскопок, водой заливает", "lang": "ru"}),
    "reply-draft": ("", {"complaint_id": "c-1", "lang": "kk"}),
    "moderate": ("", {"text": "Субботник в субботу, 10:00", "kind": "initiative"}),
    "assistant/ask": ("", {"question": "Сколько просрочено в Нуре?", "lang": "ru"}),
    "notifications": ("since=2026-10-11T00:00:00%2B05:00", None),
    "notifications/read": ("", {"ids": ["n-1", "n-2"]}),
}


def concrete(path):
    return "/" + path.replace("{id}", "x-1")


def sample(method, path):
    """Правильный запрос к маршруту: (адрес с id, строка адреса, тело)."""
    if path.startswith(("together/initiatives/{id}/", "together/yards/{id}/")):
        query, body = "", {"device_id": DEVICE}
    else:
        query, body = SAMPLE.get(path, ("", None))
    if method == "POST" and body is None:
        body = {"text": "Пример"}
    return concrete(path), query, body


def route_key(method, path):
    segments = tuple(path.split("/"))
    for m, pattern, key in V2_ROUTES:
        if m == method and pattern == segments:
            return key
    return None


# --- таблица -----------------------------------------------------------------------------------------------------

# Свой маршрут R01 (не из таблицы ролей): id сцен демо-мира для палитры — test_r01_round15_world.py.
R01_LOCAL = {"demo.scenes"}


def test_every_contract_row_is_in_the_gateway_table():
    keys = [route_key(m, p) for m, p, *_ in CONTRACT]
    assert None not in keys, [row for row, k in zip(CONTRACT, keys) if k is None]
    assert len(set(keys)) == len(CONTRACT)
    assert {k for _m, _p, k in V2_ROUTES_ROUND15} - R01_LOCAL == set(keys) == set(V2_HANDLERS_ROUND15) - R01_LOCAL
    for (method, path, role, module, function), key in zip(CONTRACT, keys):
        handler = V2_HANDLERS[key]
        assert (handler.role, handler.modules[0], handler.function) == (role, module, function), key
        assert handler.staff == ((method, path) in STAFF_ROUTES), key


def test_exact_paths_win_over_id_templates():
    # updates / board — не {id}: точные пути стоят раньше шаблонов
    gateway = CivicV2Gateway(modules={})
    for path, role in (("/incidents/updates", "R17"), ("/meetings/updates", "R13")):
        reply = gateway.handle("GET", path, "", None, CTX)
        assert reply["status"] == 503 and reply["body"]["role"] == role
    assert route_key("GET", "incidents/updates") == "incidents.updates"
    assert route_key("GET", "meetings/updates") == "meetings.updates"


# --- модуль ещё не сдан ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [(m, p) for m, p, *_ in CONTRACT])
def test_missing_module_answers_503_with_module_and_role(method, path):
    url, query, body = sample(method, path)
    context = STAFF if (method, path) in STAFF_ROUTES else RESIDENT
    reply = CivicV2Gateway(modules={}).handle(method, url, query, body, context)
    data = reply["body"]
    assert reply["status"] == 503 and data["error"] == "module_not_ready", (path, data)
    row = next(r for r in CONTRACT if r[:2] == (method, path))
    assert data["role"] == row[2] and data["module"] == row[3]
    assert data["message"] and "Traceback" not in json.dumps(data, ensure_ascii=False)


def test_modules_route_lists_round15_routes_as_not_ready():
    reply = CivicV2Gateway(modules={}).handle("GET", "/modules", "", None, CTX)
    modules = reply["body"]["modules"]
    for key, handler in V2_HANDLERS_ROUND15.items():
        if key in R01_LOCAL:
            continue
        assert modules[key] == {"role": handler.role, "module": handler.modules[0], "function": handler.function,
                                "status": "module_not_ready"}


# --- сотрудник: чтение — сессия, изменение — сессия + CSRF -------------------------------------------------------

class StaffStore:
    """Сессия R02 для шлюза: сотрудник — cookie "s", для изменения (unsafe) ещё и X-CSRF-Token (как require_staff R02)."""

    def __init__(self):
        self.calls = []

    def require_staff(self, context, unsafe):
        self.calls.append(unsafe)
        context = context or {}
        if context.get("cookies", {}).get("s") != "staff-session":
            return None, {"status": 401, "body": {"error": {"code": "unauthenticated", "message": "Войдите как редактор."}}}
        if unsafe and (context.get("headers") or {}).get("x-csrf-token") != "csrf-ok":
            return None, {"status": 403, "body": {"error": {"code": "csrf_failed", "message": "Неверный CSRF-токен."}}}
        return types.SimpleNamespace(username="operator", role="editor"), None

    def resolve_principal(self, context):
        principal, denied = self.require_staff(context, unsafe=False)
        return None if denied else principal


class Recorder:
    """Подменные модули всех ролей: записывают каждый вызов и отвечают 200."""

    def __init__(self):
        self.calls = []

    def service(self, db_path):
        recorder = self

        class Service:
            def handle(self, method, path, query, body, principal, context):
                recorder.calls.append(("service", method, path, query, body, principal))
                return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"path": path}}}

        return Service()

    def raw(self, path, query, staff=False):
        self.calls.append(("raw", path, query))
        return 200, {"path": path}

    def function(self, **kwargs):
        self.calls.append(("function", kwargs))
        return {"ok": True}

    def modules(self):
        services = {name: types.SimpleNamespace(make_service=self.service)
                    for name in ("ui.civic_together", "ui.civic_agencies", "ui.civic_meetings",
                                 "ui.civic_feedback.v2.integration")}
        return dict(services, **{
            "engine.civic_geo.api": types.SimpleNamespace(handle=self.raw),
            "ui.civic_heat.api": types.SimpleNamespace(handle_get=self.raw),
            "ui.civic_akim.api": types.SimpleNamespace(handle_get=self.raw),
            "ui.civic_ml_api": types.SimpleNamespace(route=self.function, reply_draft=self.function,
                                                     moderate=self.function),
            "agent.civic_assistant.api": types.SimpleNamespace(ask=self.function),
            "ui.civic_store.v2": types.SimpleNamespace(list_notifications=self.function,
                                                       read_notifications=self.function,
                                                       idea_to_initiative=self.function),
        })


def gateway_with_modules(tmp_path, rate_limits=None):
    recorder, store = Recorder(), StaffStore()
    stub = types.SimpleNamespace(service=lambda name: store if name == "store" else None,
                                 db_path=tmp_path / "civic.sqlite3")
    gateway = CivicV2Gateway(store_gateway=stub, modules=recorder.modules(), db_path=tmp_path / "civic.sqlite3",
                             rate_limits=rate_limits)
    return gateway, recorder, store


@pytest.mark.parametrize("method,path", sorted(STAFF_ROUTES))
def test_staff_route_needs_session_and_csrf_for_changes(tmp_path, method, path):
    gateway, recorder, _store = gateway_with_modules(tmp_path)
    url, query, body = sample(method, path)
    anonymous = gateway.handle(method, url, query, body, RESIDENT)
    assert anonymous["status"] == 401 and anonymous["body"]["error"] == "unauthenticated"
    assert recorder.calls == [], "модуль вызван без входа сотрудника"
    no_csrf = gateway.handle(method, url, query, body, STAFF_NO_CSRF)
    if method == "GET":   # чтение сотрудника — сессии достаточно (страница R08 /civic/board/ живёт без оболочки)
        assert no_csrf["status"] == 200 and len(recorder.calls) == 1
    else:                 # изменение — ещё и CSRF
        assert no_csrf["status"] == 403 and no_csrf["body"]["error"] == "csrf_failed" and recorder.calls == []
    signed_in = gateway.handle(method, url, query, body, STAFF)
    assert signed_in["status"] == 200, signed_in
    assert len(recorder.calls) == (2 if method == "GET" else 1)


def test_staff_check_comes_before_the_parameter_check(tmp_path):
    # аноним с неверным параметром получает 401, а не подсказку о формате (ничего не узнаёт о параметрах)
    gateway, recorder, _store = gateway_with_modules(tmp_path)
    reply = gateway.handle("GET", "/agencies/board", "days=0", None, RESIDENT)
    assert reply["status"] == 401 and not recorder.calls
    reply = gateway.handle("GET", "/agencies/board", "days=0", None, STAFF)
    assert reply["status"] == 400 and reply["body"]["field"] == "days" and not recorder.calls


@pytest.mark.parametrize("method,path", [(m, p) for m, p, *_ in CONTRACT if (m, p) not in STAFF_ROUTES])
def test_resident_routes_open_without_staff_session(tmp_path, method, path):
    gateway, recorder, store = gateway_with_modules(tmp_path)
    url, query, body = sample(method, path)
    reply = gateway.handle(method, url, query, body, RESIDENT)
    assert reply["status"] == 200, (path, reply)
    assert len(recorder.calls) == 1 and store.calls == [False] * len(store.calls)


def test_raw_handlers_get_their_paths(tmp_path):
    gateway, recorder, _store = gateway_with_modules(tmp_path)
    gateway.handle("GET", "/works-calendar", "from=2026-05-01", None, STAFF)
    gateway.handle("GET", "/heat/replay", "step=day", None, CTX)
    gateway.handle("GET", "/akim/board", "", None, STAFF)
    assert [c[1] for c in recorder.calls] == ["/works-calendar", "/api/civic/v2/heat/replay", "/api/civic/v2/akim/board"]


def test_raw_staff_route_tells_the_module_staff_true_only_if_it_takes_it(tmp_path):
    """R08 INTEGRATION §1.1: board/week — модуль ждёт staff=True от шлюза; R12 handle(path, query) без staff не ломается."""
    seen = []
    store = StaffStore()
    stub = types.SimpleNamespace(service=lambda name: store if name == "store" else None)
    gateway = CivicV2Gateway(store_gateway=stub, rate_limits=None, modules={
        "ui.civic_akim.api": types.SimpleNamespace(handle_get=lambda path, query, staff=False: seen.append(("R08", staff)) or (200, {})),
        "engine.civic_geo.api": types.SimpleNamespace(handle=lambda path, query: seen.append(("R12", None)) or (200, {}))})
    assert gateway.handle("GET", "/akim/board", "", None, STAFF_NO_CSRF)["status"] == 200
    assert gateway.handle("GET", "/works-calendar", "", None, STAFF)["status"] == 200
    assert seen == [("R08", True), ("R12", None)]
    assert gateway.handle("GET", "/akim/week", "", None, CTX)["status"] == 401 and len(seen) == 2


def test_service_gets_principal_and_full_path(tmp_path):
    gateway, recorder, _store = gateway_with_modules(tmp_path)
    reply = gateway.handle("POST", "/incidents/inc-1/update", "", {"text_ru": "Дороги чистят"}, STAFF)
    assert reply["status"] == 200 and reply["body"]["data"]["path"] == "/api/civic/v2/incidents/inc-1/update"
    _kind, method, path, _query, body, principal = recorder.calls[0]
    assert (method, body, principal.username) == ("POST", {"text_ru": "Дороги чистят"}, "operator")


# --- форма параметров: 400 до модуля -----------------------------------------------------------------------------

BAD = [
    # (метод, путь, адрес, тело, контекст, поле)
    ("GET", "/together/initiatives", "bbox=1,2,3", None, CTX, "bbox"),
    ("GET", "/together/initiatives", "bbox=37.5,55.6,37.7,55.8", None, CTX, "bbox"),   # Москва — вне Астаны
    ("GET", "/together/initiatives", "yard=bad%20id", None, CTX, "yard"),
    ("GET", "/together/initiatives", "status=Опубликовано", None, CTX, "status"),
    ("GET", "/together/initiatives", "district=Нура", None, CTX, "district"),
    ("GET", "/together/updates", "since=вчера", None, RESIDENT, "since"),
    ("GET", "/incidents/updates", "since=2026-10-32", None, RESIDENT, "since"),
    ("GET", "/agencies/board", "days=0", None, STAFF, "days"),
    ("GET", "/agencies/board", "days=1000", None, STAFF, "days"),
    ("GET", "/agencies/handoffs", "days=семь", None, STAFF, "days"),
    ("GET", "/works-calendar", "from=2026-10-20&to=2026-10-01", None, STAFF, "from"),
    ("GET", "/works-calendar", "from=2025-01-01&to=2026-12-31", None, STAFF, "to"),
    ("GET", "/works-calendar", "street=" + "а" * 121, None, STAFF, "street"),
    ("GET", "/works-conflicts", "to=31.07.2026", None, STAFF, "to"),
    ("GET", "/heat/replay", "step=1%20day", None, CTX, "step"),
    ("GET", "/heat/replay", "category=potholes", None, CTX, "category"),
    ("GET", "/heat/replay", "from=2026-13-01", None, CTX, "from"),
    ("GET", "/akim/week", "date=16.10.2026", None, STAFF, "date"),
    ("GET", "/meetings", "district=Нура", None, CTX, "district"),
    ("GET", "/notifications", "", None, CTX, "device_id"),
    ("GET", "/notifications", "device_id=x", None, CTX, "device_id"),
    ("POST", "/notifications/read", "", {"ids": "all"}, RESIDENT, "ids"),
    ("POST", "/notifications/read", "", {"ids": ["bad id"]}, RESIDENT, "ids"),
    ("POST", "/notifications/read", "", {"all": True}, CTX, "device_id"),
    ("POST", "/route", "", {}, CTX, "text"),
    ("POST", "/route", "", {"category": "roads", "subtopic": "Яма"}, CTX, "subtopic"),
    ("POST", "/route", "", {"text": "яма", "point": [0, 0]}, CTX, "point"),
    ("POST", "/route", "", {"text": "яма", "category": "potholes"}, CTX, "category"),
    ("POST", "/route", "", {"text": "яма", "lang": "en"}, CTX, "lang"),
    ("POST", "/route", "", {"text": "яма", "target": 5}, CTX, "target"),
    ("POST", "/moderate", "", {"text": "   "}, CTX, "text"),
    ("POST", "/moderate", "", {"text": "я" * 5001}, CTX, "text"),
    ("POST", "/moderate", "", {"text": "Субботник", "kind": "Инициатива"}, CTX, "kind"),
    ("POST", "/assistant/ask", "", {}, STAFF, "question"),
    ("POST", "/assistant/ask", "", {"question": "Сколько?", "district": "Нура"}, STAFF, "district"),
    ("POST", "/reply-draft", "", {"complaint_id": "bad id"}, STAFF, "complaint_id"),
]


@pytest.mark.parametrize("method,path,query,body,context,field", BAD)
def test_bad_parameters_are_400_with_a_clear_text_and_module_is_not_called(tmp_path, method, path, query, body,
                                                                          context, field):
    gateway, recorder, _store = gateway_with_modules(tmp_path)
    reply = gateway.handle(method, path, query, body, context)
    data = reply["body"]
    assert reply["status"] == 400 and data["error"] == "bad_request" and data["field"] == field, data
    assert isinstance(data["message"], str) and len(data["message"]) > 8 and any("а" <= ch <= "я" for ch in data["message"])
    assert not recorder.calls


def test_plus_of_the_time_zone_may_come_as_space(tmp_path):
    # «+05:00» без %2B parse_qs превращает в пробел — шлюз не отказывает (модуль получает адрес как есть)
    gateway, recorder, _store = gateway_with_modules(tmp_path)
    reply = gateway.handle("GET", "/together/updates", "since=2026-10-11T00:00:00+05:00", None, RESIDENT)
    assert reply["status"] == 200 and len(recorder.calls) == 1


def test_function_arguments_are_parsed_and_filtered(tmp_path):
    seen = {}

    def route(text, lang=None):            # объявила только text и lang — остальное ей не передаётся
        seen["route"] = (text, lang)
        return {"services": ["water", "road"], "joint": True}

    def list_notifications(device_id, since=None):
        seen["list"] = (device_id, since)
        return {"items": []}

    def read_notifications(body, device_id):
        seen["read"] = (device_id, body)
        return {"read": 2}

    def ask(question, principal=None):
        seen["ask"] = (question, principal)
        return {"answer": "…"}

    store = StaffStore()
    stub = types.SimpleNamespace(service=lambda name: store if name == "store" else None)
    gateway = CivicV2Gateway(store_gateway=stub, rate_limits=None, modules={
        "ui.civic_ml_api": types.SimpleNamespace(route=route),
        "ui.civic_store.v2": types.SimpleNamespace(list_notifications=list_notifications,
                                                   read_notifications=read_notifications),
        "agent.civic_assistant.api": types.SimpleNamespace(ask=ask)})
    assert gateway.handle("POST", "/route", "", {"text": "Яма", "lang": "kk", "extra": 1}, CTX)["status"] == 200
    assert seen["route"] == ("Яма", "kk")
    # без текста — по категории (R04 умеет): text=None доходит до функции
    assert gateway.handle("POST", "/route", "", {"category": "roads"}, CTX)["status"] == 200
    assert seen["route"] == (None, None)
    assert gateway.handle("GET", "/notifications", "since=2026-10-11", None, RESIDENT)["status"] == 200
    assert seen["list"] == (DEVICE, "2026-10-11")
    # устройство: заголовок X-Birge-Device, запасной вариант — device_id в теле
    body = {"ids": ["n-1"], "device_id": "device-body-0001"}
    assert gateway.handle("POST", "/notifications/read", "", body, CTX)["status"] == 200
    assert seen["read"] == ("device-body-0001", body)
    assert gateway.handle("POST", "/assistant/ask", "", {"text": "Сколько просрочено?"}, STAFF)["status"] == 200
    assert seen["ask"][0] == "Сколько просрочено?" and seen["ask"][1] == {"username": "operator", "role": "editor"}


@pytest.mark.parametrize("exc,status,code", [
    (ValueError("Инициатива без даты"), 400, "bad_request"),
    (LookupError("i-1"), 404, "not_found"),
    (PermissionError(), 403, "forbidden"),
    (RuntimeError("секретная подробность"), 500, "internal"),
])
def test_module_errors_become_clear_answers(exc, status, code):
    def route(text):
        raise exc

    reply = CivicV2Gateway(modules={"ui.civic_ml_api": types.SimpleNamespace(route=route)}, rate_limits=None).handle(
        "POST", "/route", "", {"text": "яма"}, CTX)
    assert (reply["status"], reply["body"]["error"]) == (status, code)
    assert reply["body"]["message"] and "секретная" not in json.dumps(reply["body"], ensure_ascii=False)


def test_broken_service_is_500_without_details(tmp_path):
    class Broken:
        def handle(self, *args):
            raise RuntimeError("секретная подробность")

    gateway = CivicV2Gateway(modules={"ui.civic_agencies": types.SimpleNamespace(make_service=lambda db: Broken())},
                             db_path=tmp_path / "civic.sqlite3")
    reply = gateway.handle("GET", "/agencies", "", None, CTX)
    assert reply["status"] == 500 and reply["body"]["error"] == "internal"
    assert "секретная" not in json.dumps(reply["body"], ensure_ascii=False)


# --- лимиты записи жителя ------------------------------------------------------------------------------------------

def test_every_resident_write_has_a_rate_limit():
    open_writes = [key for m, _p, key in V2_ROUTES_ROUND15 if m == "POST" and not V2_HANDLERS[key].staff]
    assert open_writes and not [key for key in open_writes if key not in V2_RATE_LIMITS]


def test_new_initiatives_are_limited_per_address(tmp_path):
    gateway, recorder, _store = gateway_with_modules(tmp_path, rate_limits="default")
    body = {"kind": "cleanup", "title": "Субботник", "device_id": DEVICE}
    codes = [gateway.handle("POST", "/together/initiatives", "", body, RESIDENT)["status"] for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    limited = gateway.handle("POST", "/together/initiatives", "", body, RESIDENT)
    assert limited["status"] == 429 and int(limited["headers"]["Retry-After"]) >= 1
    other = dict(RESIDENT, client_ip="10.0.0.9")  # другой адрес — свой счёт
    assert gateway.handle("POST", "/together/initiatives", "", body, other)["status"] == 200


def test_join_is_limited_per_initiative(tmp_path):
    gateway, _recorder, _store = gateway_with_modules(tmp_path, rate_limits="default")
    for _ in range(20):
        assert gateway.handle("POST", "/together/initiatives/i-1/join", "", {}, RESIDENT)["status"] == 200
    assert gateway.handle("POST", "/together/initiatives/i-1/join", "", {}, RESIDENT)["status"] == 429
    assert gateway.handle("POST", "/together/initiatives/i-2/join", "", {}, RESIDENT)["status"] == 200


# --- настоящий HTTP ------------------------------------------------------------------------------------------------

@pytest.fixture()
def server(tmp_path):
    v2 = CivicV2Gateway(modules={})
    srv = web_server.create_server(port=0, civic_db=tmp_path / "civic.sqlite3", civic_v2=v2)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Host": f"127.0.0.1:{srv.server_address[1]}"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    conn.request(method, path, body=data, headers=hdrs)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    return resp.status, (json.loads(raw) if raw else None)


def test_http_new_routes_answer_503_json(server):
    for method, path, body in (("GET", "/api/civic/v2/together/initiatives", None),
                               ("GET", "/api/civic/v2/incidents/updates?since=2026-10-11", None),
                               ("POST", "/api/civic/v2/route", {"text": "яма"})):
        status, data = request(server, method, path, body)
        assert status == 503 and data["error"] == "module_not_ready" and data["message"]


def test_http_foreign_origin_is_refused_on_new_writes(server):
    status, data = request(server, "POST", "/api/civic/v2/incidents", {"kind": "blizzard"},
                           headers={"Origin": "https://evil.example"})
    assert status == 403 and data["error"] == "cross_origin"


def test_http_wrong_method_on_new_route(server):
    status, data = request(server, "PUT", "/api/civic/v2/agencies/board", {"days": 1})
    assert status == 405 and data["error"] == "method_not_allowed"


def test_http_modules_lists_round15(server):
    status, data = request(server, "GET", "/api/civic/v2/modules")
    assert status == 200
    assert {"together.initiatives.list", "incidents.updates", "assistant.ask", "heat.replay"} <= set(data["modules"])
