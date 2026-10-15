"""R15 раунд 15 · шлюз R01: новые маршруты CONTRACT §7 (THREATS_R15 T-R01-01…03).

1. Каждый маршрут «сотрудник» из CONTRACT §7, который R01 добавил в V2_ROUTES, помечен staff=True: шлюз проверяет
   сессию R02 + CSRF и для «сервисов» (R15-S34 раунда 14), и для raw.
2. raw-маршрут с staff=True шлюз действительно закрывает (S42): у raw-функции нет principal. R12 и R08 обошли это сами
   (staff_view=True + 401 в модуле без staff=True) — S42 остаётся защитой в глубину для будущих raw-маршрутов.
3. Запись жителя из CONTRACT §7 — в V2_RATE_LIMITS; «Я приду», «Я живу здесь», «Приду» — ещё и суточный предел на одну
   цель с адреса (S08: новый device_id = новый «житель»).
4. Через настоящий HTTP: маршрут сотрудника без сессии -> 401/403 (модуля нет — 503, тогда NOT_RUN по маршруту).
5. Режим показа ?show=1 не меняет защиту (CSP главной, сотрудник без сессии -> 401).
Маршрута ещё нет в таблице — NOT_RUN (R01 добавляет строки CONTRACT §7 в первый час раунда).
"""

from __future__ import annotations

import types

import pytest

from r15_common import live_server, need_module, request, xfail
from r15_round15 import DEVICES, not_run

# (метод, шаблон пути) — «сотрудник» в CONTRACT §7.
CONTRACT_STAFF = (
    ("POST", ("together", "initiatives", "{id}", "support")),
    ("POST", ("together", "initiatives", "{id}", "moderate")),
    ("GET", ("agencies", "board")),
    ("GET", ("agencies", "joint")),
    ("GET", ("agencies", "handoffs")),
    ("POST", ("incidents",)),
    ("POST", ("incidents", "{id}", "task")),
    ("POST", ("incidents", "{id}", "update")),
    ("POST", ("incidents", "{id}", "close")),
    ("POST", ("complaints", "{id}", "handoff")),
    ("POST", ("complaints", "{id}", "services")),
    ("POST", ("complaints", "{id}", "part")),
    ("GET", ("works-calendar",)),
    ("GET", ("works-conflicts",)),
    ("GET", ("akim", "board")),
    ("GET", ("akim", "week")),
    ("POST", ("meetings",)),
    ("POST", ("meetings", "{id}", "order")),
    ("POST", ("meetings", "{id}", "result")),
    ("POST", ("reply-draft",)),
    ("POST", ("assistant", "ask")),
    ("POST", ("ideas", "{id}", "to-initiative")),
    ("POST", ("together", "yards", "{id}", "moderate")),   # R16 [доп.]: имя «старшего по двору» — акимат
)
# Запись жителя (или «все») из CONTRACT §7 -> нужен ли суточный предел на одну цель с адреса (S08).
CONTRACT_RESIDENT_WRITES = (
    ("POST", ("together", "initiatives"), False),
    ("POST", ("together", "initiatives", "{id}", "join"), True),
    ("POST", ("together", "initiatives", "{id}", "report"), False),
    ("POST", ("together", "yards", "{id}", "join"), True),
    ("POST", ("together", "yards", "{id}", "leave"), False),
    ("POST", ("together", "initiatives", "{id}", "leave"), False),
    ("POST", ("together", "yards", "{id}", "captain"), False),   # R16 [доп.]: «старший по двору» — сосед
    ("POST", ("meetings", "{id}", "register"), True),
    ("POST", ("meetings", "{id}", "question"), False),
    ("POST", ("route",), False),
    ("POST", ("moderate",), False),
)
# Подходящие по виду id для шаблона {id} (CIVIC_ID шлюза) — модуль ответит 404, но только после проверки прав.
SAMPLE_ID = {"together": "i-r15probe0001", "incidents": "inc-r15probe0001", "complaints": "c-000000000001",
             "meetings": "m-r15probe0001", "ideas": "idea-r15probe0001"}


def _name(method, pattern):
    return method + " " + "/".join(pattern)


@pytest.fixture(scope="module")
def ws():
    web_server = need_module("ui.web_server")
    if not hasattr(web_server, "V2_ROUTES"):
        not_run("в этой сборке нет шлюза /api/civic/v2 (R01)")
    return web_server


def _route(ws, method, pattern):
    for route_method, route_pattern, key in ws.V2_ROUTES:
        if route_method == method and tuple(route_pattern) == tuple(pattern):
            return key, ws.V2_HANDLERS.get(key)
    return None, None


@pytest.mark.parametrize("method,pattern", CONTRACT_STAFF, ids=[_name(m, p) for m, p in CONTRACT_STAFF])
def test_contract_staff_route_is_marked_staff(ws, method, pattern):
    """T-R01-02: «сотрудник» по CONTRACT §7 — staff=True в таблице шлюза (сессия + CSRF у шлюза и у модуля)."""
    key, handler = _route(ws, method, pattern)
    if key is None:
        not_run(f"R01 ещё не добавил {_name(method, pattern)} в V2_ROUTES")
    assert handler is not None, f"{key}: маршрут без обработчика"
    # raw-маршрут сотрудника R12/R08 объявлен staff_view=True: шлюз передаёт staff=True только после проверки сессии,
    # без него модуль сам отвечает 401 (INTEGRATION R12/R08). Что ответ действительно 401 — HTTP-тест ниже.
    raw_guarded = handler.kind == "raw" and getattr(handler, "staff_view", False)
    assert handler.staff or raw_guarded, (
        f"{_name(method, pattern)} ({key}, {handler.kind}): нет staff=True (или staff_view у raw) — шлюз не проверит сотрудника")


@pytest.mark.parametrize("method,pattern,per_target", CONTRACT_RESIDENT_WRITES,
                         ids=[_name(m, p) for m, p, _t in CONTRACT_RESIDENT_WRITES])
def test_contract_resident_write_is_rate_limited(ws, method, pattern, per_target):
    """T-R16-09/T-R13-01/T-R04-10: лимит по адресу; для «Я приду»/«Приду»/«Я живу здесь» — и на одну цель за сутки."""
    key, handler = _route(ws, method, pattern)
    if key is None:
        not_run(f"R01 ещё не добавил {_name(method, pattern)} в V2_ROUTES")
    rules = ws.V2_RATE_LIMITS.get(key)
    assert rules, f"{_name(method, pattern)} ({key}): нет строки в V2_RATE_LIMITS"
    if per_target:
        assert any(target and window >= 3600 for window, _limit, target in rules), (
            f"{key}: нужен предел на одну цель с адреса (окно ≥ 1 ч, per_target=True), как proposals.vote — {rules}")


def test_every_round15_write_route_is_staff_or_rate_limited(ws):
    """T-R01-03: любая запись раунда 15 — и из CONTRACT §7, и [доп.] ролей, которые R01 берёт в сборку, — либо
    сотрудник (staff=True), либо в V2_RATE_LIMITS. Новый маршрут без того и другого — запись без предела от любого."""
    routes = getattr(ws, "V2_ROUTES_ROUND15", None)
    if not routes:
        not_run("в шлюзе нет V2_ROUTES_ROUND15 (R01)")
    unguarded = []
    for method, pattern, key in routes:
        handler = ws.V2_HANDLERS.get(key)
        if method != "GET" and not (handler and handler.staff) and key not in ws.V2_RATE_LIMITS:
            unguarded.append(f"{_name(method, pattern)} ({key})")
    assert not unguarded, "запись без staff=True и без лимита: " + ", ".join(unguarded)


class _FakeRaw:
    """Подменный raw-модуль: если шлюз его вызвал без сессии — проверки сотрудника не было."""

    calls = 0

    @classmethod
    def handle_get(cls, path, query, staff=None):  # noqa: ARG003 — подпись raw R07/R08
        cls.calls += 1
        return 200, {"r15_internal": True}

    handle = handle_get


@xfail("S42")
def test_gateway_enforces_staff_on_raw_routes(ws, monkeypatch):
    """S42 / T-R01-01: raw-маршрут с staff=True без сессии сотрудника не должен дойти до функции модуля.

    В FINAL-4 ветка kind == "raw" в CivicV2Gateway.handle() отвечает раньше проверки handler.staff.
    """
    _FakeRaw.calls = 0
    monkeypatch.setitem(ws.V2_HANDLERS, "akim.summary",
                        ws.V2Handler("R08", ("r15.fake_raw",), "handle_get", kind="raw", staff=True))
    gateway = ws.CivicV2Gateway(modules={"r15.fake_raw": _FakeRaw}, rate_limits=None)
    ctx = {"method": "GET", "path": "/akim/summary", "headers": {"x-birge-device": DEVICES[0]}, "cookies": {},
           "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True, "host": "127.0.0.1"}
    reply = gateway.handle("GET", "/akim/summary", "", None, ctx)
    assert _FakeRaw.calls == 0 and reply["status"] in (401, 403, 503), (reply["status"], reply["body"])


def test_real_raw_staff_routes_are_closed(ws):
    """T-R01-01 на настоящей таблице: каждый raw-маршрут с staff=True закрыт без сессии (подменённый модуль)."""
    raw_staff = {key for key, h in ws.V2_HANDLERS.items() if h.kind == "raw" and h.staff}
    if not raw_staff:
        not_run("в таблице шлюза нет raw-маршрутов с staff=True (works-calendar, akim/board — ещё не добавлены)")
    opened = []
    for method, pattern, key in ws.V2_ROUTES:
        if key not in raw_staff:
            continue
        handler, calls = ws.V2_HANDLERS[key], []
        fake = type("FakeRaw", (), {handler.function: staticmethod(
            lambda path, query, staff=None, _calls=calls: _calls.append(path) or (200, {"r15_internal": True}))})
        gateway = ws.CivicV2Gateway(modules={name: fake for name in handler.modules}, rate_limits=None)
        path = _concrete(pattern)
        reply = gateway.handle(method, path, "", None, {"headers": {}, "cookies": {}, "client_ip": "127.0.0.1",
                                                        "host_allowed": True, "is_same_origin": True})
        if calls or reply["status"] == 200:
            opened.append(f"{method} {path} ({key}) -> {reply['status']}")
    assert not opened, "raw-маршрут сотрудника открыт без сессии:\n" + "\n".join(opened)


class _StaffStore:
    """Сессия R02 для шлюза без базы: context["r15_staff"] — вошёл; CSRF — заголовок x-csrf-token = "t"."""

    @staticmethod
    def require_staff(context, unsafe):
        if not context.get("r15_staff"):
            return None, {"status": 401, "body": {"error": {"code": "unauthenticated", "message": "Войдите"}}}
        if unsafe and (context.get("headers") or {}).get("x-csrf-token") != "t":
            return None, {"status": 403, "body": {"error": {"code": "csrf_failed", "message": "CSRF"}}}
        return types.SimpleNamespace(username="r15", role="editor", is_staff=True), None

    def resolve_principal(self, context):
        return self.require_staff(context, False)[0]


@xfail("S50")
def test_raw_staff_route_reaches_module_for_signed_in_staff(ws, tmp_path):
    """S50: raw-маршрут сотрудника (R08 akim/board и akim/week, R12 календарь) — вошедший сотрудник доходит до модуля и
    модуль узнаёт об этом (staff=True); аноним — 401, модуль не вызван. Иначе Ситуационный центр — 401 всем."""
    raw_staff = [(m, p, k) for m, p, k in ws.V2_ROUTES
                 if ws.V2_HANDLERS.get(k) is not None and ws.V2_HANDLERS[k].kind == "raw" and ws.V2_HANDLERS[k].staff]
    if not raw_staff:
        not_run("в таблице шлюза нет raw-маршрутов с staff=True")
    store = _StaffStore()
    broken = []
    for method, pattern, key in raw_staff:
        handler, seen = ws.V2_HANDLERS[key], []

        def fn(path, query, staff=None, _seen=seen):
            _seen.append(staff)
            return (200, {"r15": True}) if staff is True else (401, {"error": "staff_only"})

        fake = type("FakeRaw", (), {handler.function: staticmethod(fn)})
        gateway = ws.CivicV2Gateway(store_gateway=types.SimpleNamespace(service=lambda n: store if n == "store" else None,
                                                                        db_path=tmp_path / "c.sqlite3"),
                                    modules={name: fake for name in handler.modules}, rate_limits=None)
        path = _concrete(pattern)
        base = {"headers": {}, "cookies": {}, "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True}
        anon = gateway.handle(method, path, "", None, dict(base))
        staff = gateway.handle(method, path, "", None, dict(base, r15_staff=True, headers={"x-csrf-token": "t"}))
        if anon["status"] not in (401, 403) or seen[:1] not in ([], [True]) or staff["status"] != 200:
            broken.append(f"{method} {path} ({key}): аноним {anon['status']}, сотрудник {staff['status']}, staff={seen}")
    assert not broken, "\n".join(broken)


@pytest.fixture()
def srv(tmp_path):
    with live_server(tmp_path) as server:
        yield server


def _concrete(pattern):
    head = pattern[0]
    return "/" + "/".join(SAMPLE_ID.get(head, "x-r15probe0001") if part == "{id}" else part for part in pattern)


@pytest.mark.parametrize("method,pattern", CONTRACT_STAFF, ids=[_name(m, p) for m, p in CONTRACT_STAFF])
def test_contract_staff_route_refuses_resident_over_http(ws, srv, method, pattern):
    """T-R16-12, T-R17-02/03/06, T-R09-01, T-R13-04, T-R03-06, T-R04-11, T-R06-07: без сессии -> 401/403."""
    key, _handler = _route(ws, method, pattern)
    if key is None:
        not_run(f"R01 ещё не добавил {_name(method, pattern)} в V2_ROUTES")
    port = srv.server_address[1]
    body = {"text_ru": "R15", "text_kk": "R15", "status": "done", "to": "road", "reason": "R15", "question": "R15",
            "services": [{"service": "road", "role": "lead"}], "kind": "blizzard",
            "zone": {"kind": "district", "district": "nura"}} if method == "POST" else None
    for headers in ({"Origin": f"http://127.0.0.1:{port}"},
                    {"Origin": f"http://127.0.0.1:{port}", "X-Birge-Device": DEVICES[1]}):
        status, _h, raw = request(srv, method, "/api/civic/v2" + _concrete(pattern), body, headers=headers)
        if status == 503:
            not_run(f"{key}: модуль не подключён в этой сборке (503)")
        assert status in (401, 403), (key, status, raw[:200])


def test_show_mode_keeps_protection(srv, ws):
    """T-R01-03: ?show=1 (режим показа) меняет вид, а не защиту: та же CSP главной, сотрудник без сессии -> 401/403."""
    port = srv.server_address[1]
    status, plain, _b = request(srv, "GET", "/")
    status_show, shown, _b = request(srv, "GET", "/?show=1")
    assert status == status_show == 200
    assert shown.get("content-security-policy") == plain.get("content-security-policy")
    assert "script-src 'self'" in (shown.get("content-security-policy") or "")
    for method, pattern in CONTRACT_STAFF:
        key, _h = _route(ws, method, pattern)
        if key is None or method != "GET":
            continue
        status, _h2, raw = request(srv, "GET", "/api/civic/v2" + _concrete(pattern) + "?show=1",
                                   headers={"Origin": f"http://127.0.0.1:{port}"})
        assert status in (401, 403, 503), (key, status, raw[:200])
