"""R15: транспорт ui/web_server.py (владелец R01) — статика, заголовки, Origin/CSRF, доступ сотрудника.

Всё через настоящий HTTP на 127.0.0.1 и временную базу. PASS-тесты фиксируют то, что уже защищено
(регрессия), xfail — открытые находки из SECURITY_REVIEW.md.
"""

from __future__ import annotations

import json

import pytest

from r15_common import error_code, live_server, need_module, request, xfail

EVIL = "http://evil.example"


@pytest.fixture()
def srv(tmp_path):
    with live_server(tmp_path) as server:
        yield server


@pytest.fixture()
def v2srv(srv):
    """Сервер со шлюзом API v2 (раунд 14, R01); в старой оболочке без v2 — skip, а не ложное падение."""
    if not hasattr(srv, "civic_v2"):
        pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
    return srv


# --- 5. статика: только белый список, выхода за web/ нет ---------------------------------

TRAVERSAL = [
    "/../ui/web_server.py", "/civic/../../ui/web_server.py", "/%2e%2e/ui/web_server.py",
    "/civic/shell/..%2f..%2f..%2fui%2fweb_server.py", "/.env", "/.git/config", "/web/index.html",
    "/civic/", "/vendor/", "/civic/shell/", "/..%5c..%5cui%5cweb_server.py", "//etc/passwd",
    "/research/round-14/CONTRACT.md", "/.runtime/civic.sqlite3", "/private/form.csv",
]


@pytest.mark.parametrize("path", TRAVERSAL)
def test_static_has_no_path_traversal(srv, path):
    status, _headers, body = request(srv, "GET", path)
    assert status == 404, path
    assert b"import " not in body and b"[core]" not in body


def test_index_is_served_with_basic_security_headers(srv):
    status, headers, _ = request(srv, "GET", "/")
    assert status == 200
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("referrer-policy") == "same-origin"
    assert "frame-ancestors 'none'" in headers.get("content-security-policy", "")


@xfail("S01")
def test_csp_limits_scripts_on_html(srv):
    """Без script-src любая XSS в одном из 14 модулей получает полный доступ к странице сотрудника."""
    _status, headers, _ = request(srv, "GET", "/")
    csp = headers.get("content-security-policy", "")
    directives = {part.strip().split(" ")[0]: part.strip() for part in csp.split(";") if part.strip()}
    script = directives.get("script-src") or directives.get("default-src") or ""
    assert "'self'" in script and "'unsafe-inline'" not in script and "'unsafe-eval'" not in script
    assert "object-src 'none'" in csp
    assert "base-uri" in csp


# --- 2. Origin / CSRF для изменяющих запросов --------------------------------------------

V2_WRITES = [
    ("POST", "/api/civic/v2/complaints", {"text": "Яма у остановки", "point": [71.41, 51.11]}),
    ("POST", "/api/civic/v2/complaints/c-abcdef12/metoo", {"device_id": "device-r15-000001"}),
    ("POST", "/api/civic/v2/proposals/p-1/vote", {"value": 1, "device_id": "device-r15-000001"}),
    ("POST", "/api/civic/v2/complaints/c-abcdef12/status", {"status": "fixed"}),
    ("PUT", "/api/civic/v2/objects/o-1/stage", {"stage": "design"}),
]


@pytest.mark.parametrize("method,path,body", V2_WRITES)
def test_cross_origin_write_is_rejected(v2srv, method, path, body):
    srv = v2srv
    status, _h, data = request(srv, method, path, body, headers={"Origin": EVIL})
    assert status == 403, data
    assert json.loads(data)["error"] == "cross_origin"


@pytest.mark.parametrize("method,path,body", V2_WRITES)
def test_cross_site_fetch_metadata_is_rejected(v2srv, method, path, body):
    srv = v2srv
    status, _h, _data = request(srv, method, path, body, headers={"Sec-Fetch-Site": "cross-site"})
    assert status == 403


def test_simple_form_post_cannot_reach_api(v2srv):
    srv = v2srv
    # Чужая страница без preflight может послать только text/plain / form — шлюз требует JSON.
    status, _h, _ = request(srv, "POST", "/api/civic/v2/proposals/p-1/vote",
                            raw=b'{"value":1,"device_id":"device-r15-000001"}',
                            headers={"Content-Type": "text/plain"})
    assert status == 415


def test_preflight_gets_no_cors_permission(srv):
    status, headers, _ = request(srv, "OPTIONS", "/api/civic/v2/proposals/p-1/vote",
                                 headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"})
    assert status in (404, 405)
    assert "access-control-allow-origin" not in headers


def test_foreign_host_header_is_rejected(srv):
    # Защита от DNS rebinding: имя чужого сайта в Host -> 403 даже для чтения.
    paths = ["/api/civic/v1/modules"] + (["/api/civic/v2/complaints"] if hasattr(srv, "civic_v2") else [])
    for path in paths:
        status, _h, _ = request(srv, "GET", path, headers={"Host": "evil.example:%d" % srv.server_address[1]})
        assert status == 403, path


# --- 2. действия сотрудника недоступны анониму -------------------------------------------

STAFF_ONLY = [
    ("POST", "/api/civic/v2/complaints/c-abcdef12/status", {"status": "fixed"}),
    ("POST", "/api/civic/v2/proposals", {"kind": "park", "title_ru": "Сквер"}),
    ("PUT", "/api/civic/v2/objects/o-1/stage", {"stage": "design"}),
    ("POST", "/api/civic/v1/staff/objects", {"title": "x"}),
    ("GET", "/api/civic/v1/staff/feedback", None),
    ("GET", "/api/civic/v1/staff/audit", None),
]


@pytest.mark.parametrize("method,path,body", STAFF_ONLY)
def test_staff_actions_need_session(srv, method, path, body):
    if "/api/civic/v2/" in path and not hasattr(srv, "civic_v2"):
        pytest.skip("в этой сборке нет шлюза /api/civic/v2 (R01)")
    status, _h, data = request(srv, method, path, body,
                               headers={"Origin": "http://127.0.0.1:%d" % srv.server_address[1]})
    payload = json.loads(data)
    if status == 404 and error_code(payload) == "not_found":
        pytest.skip(f"маршрута {path} нет в этой сборке")
    if status == 503:
        # Модуль ещё не подключён в этой сборке — значит, и действие недоступно.
        assert error_code(payload) in ("module_not_ready", "module_unavailable"), payload
        return
    assert status in (401, 403), (status, payload)


def _staff_login(srv, tmp_path):
    store = srv.civic.service("store")
    if store is None:
        pytest.skip("в этой сборке нет хранилища сотрудников (ui.civic_store)")
    store.accounts.create_user("r15-editor", "R15-Strong-Pass-2026", display_name="R15", role="editor")
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    status, headers, data = request(srv, "POST", "/api/civic/v1/session/login",
                                    {"username": "r15-editor", "password": "R15-Strong-Pass-2026"},
                                    headers={"Origin": origin})
    assert status == 200, data
    return headers.get("set-cookie", ""), json.loads(data)


def test_session_cookie_is_httponly_strict(srv, tmp_path):
    cookie, _ = _staff_login(srv, tmp_path)
    attrs = [part.strip().lower() for part in cookie.split(";")]
    assert "httponly" in attrs
    assert "samesite=strict" in attrs
    assert not any(a.startswith("domain=") for a in attrs)


def test_csrf_token_is_required_for_staff_write(srv, tmp_path):
    cookie, _session = _staff_login(srv, tmp_path)
    token = cookie.split(";")[0]
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    status, _h, data = request(srv, "POST", "/api/civic/v1/staff/objects", {"title": "x"},
                               headers={"Cookie": token, "Origin": origin})
    assert status == 403 and json.loads(data)["error"]["code"] == "csrf_failed"


def test_session_cookie_reaches_api_v2(v2srv, tmp_path):
    """R15-S09 исправлено (R06 ef35fb6, сборка R01 d3c33d9): Path=/api/civic — cookie доходит и до v1, и до v2."""
    srv = v2srv
    cookie, _ = _staff_login(srv, tmp_path)
    path = next((a.split("=", 1)[1] for a in (p.strip() for p in cookie.split(";")) if a.lower().startswith("path=")), "/")
    assert "/api/civic/v2/complaints/c-1/status".startswith(path.rstrip("/") + "/")


def test_public_akim_summary_has_no_resident_texts(srv):
    """«Картина дня» доступна без входа: в ней только агрегаты, без текстов и точек жителей."""
    need_module("ui.civic_akim")
    status, _h, data = request(srv, "GET", "/api/civic/v2/akim/summary")
    if status == 503:
        pytest.skip("akim.summary не подключён")
    assert status == 200
    text = data.decode("utf-8")
    payload = json.loads(text)

    # .text / .text_parts — это сгенерированная фраза сводки («Сегодня 19 новых обращений…»), не жалоба.
    def keys(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if path == "" and key in ("text", "text_parts"):
                    continue
                yield key
                yield from keys(value, path + "." + key)
        elif isinstance(obj, list):
            for item in obj:
                yield from keys(item, path + "[]")

    found = set(keys(payload)) & {"text", "texts", "quote", "quotes", "point", "device_id", "device_hash",
                                  "phone", "username", "author"}
    assert not found, found


# --- 3. частота запросов: накрутки и отказ в обслуживании --------------------------------

def _v2_ready(srv, key):
    status, _h, data = request(srv, "GET", "/api/civic/v2/modules")
    modules = json.loads(data).get("modules", {}) if status == 200 else {}
    if (modules.get(key) or {}).get("status") != "ready":
        pytest.skip(f"маршрут {key} не подключён в этой сборке")


def _burst(srv, method, path, bodies, headers=None):
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    statuses = []
    for body, extra in bodies:
        status, hdrs, data = request(srv, method, path, body, headers={"Origin": origin, **(headers or {}), **extra})
        statuses.append(status)
        if status == 429:
            assert hdrs.get("retry-after"), "429 без Retry-After"
            break
    return statuses


@xfail("S02")
def test_complaint_spam_from_one_address_is_limited(srv):
    """Лимит R09 — 20 жалоб в час на device_id; новый device_id на каждый запрос обходит его."""
    _v2_ready(srv, "complaints.create")
    bodies = [({"text": "Спам %d: яма у дома" % i, "category": "roads", "point": [71.41, 51.11]},
               {"X-Birge-Device": "device-r15-spam-%010d" % i}) for i in range(60)]
    assert 429 in _burst(srv, "POST", "/api/civic/v2/complaints", bodies)


@xfail("S08")
def test_metoo_with_new_device_ids_is_limited(srv):
    """«Я тоже» — одно на устройство, но устройство — любая строка: 60 новых id = +60 человек."""
    _v2_ready(srv, "complaints.metoo")
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    status, _h, data = request(srv, "POST", "/api/civic/v2/complaints",
                               {"text": "Не горят фонари во дворе", "category": "lighting", "point": [71.41, 51.11]},
                               headers={"Origin": origin, "X-Birge-Device": "device-r15-author-0000001"})
    assert status in (200, 201), data
    complaint_id = json.loads(data)["data"]["complaint"]["id"]
    bodies = [({}, {"X-Birge-Device": "device-r15-voter-%010d" % i}) for i in range(60)]
    statuses = _burst(srv, "POST", "/api/civic/v2/complaints/%s/metoo" % complaint_id, bodies)
    assert 429 in statuses, "накручено %d «Я тоже» за секунды" % statuses.count(200)


# --- 4. персональные данные в журнале сервера ---------------------------------------------

@xfail("S10")
def test_server_log_has_no_resident_coordinates(srv, capsys):
    """Строка запроса /targets?lon&lat и /complaints/place?lon&lat попадает в журнал вместе с адресом и временем."""
    request(srv, "GET", "/api/civic/v2/complaints/place?lon=71.412345&lat=51.123456")
    request(srv, "GET", "/api/civic/v2/targets?lon=71.412345&lat=51.123456&category=roads")
    logged = capsys.readouterr().err
    assert "/api/civic/v2/complaints/place" in logged or "/api/civic/v2/targets" in logged, "журнал не перехвачен"
    assert "51.123456" not in logged and "71.412345" not in logged


# --- 2. вход сотрудника: перебор паролей и слабые пароли (регрессия, R06 ui/civic_store/auth.py) ---------

def test_staff_login_bruteforce_is_throttled(srv, tmp_path):
    """Подбор пароля: после нескольких неверных попыток с одного адреса — 429, а не бесконечные попытки."""
    store = srv.civic.service("store")
    if store is None:
        pytest.skip("в этой сборке нет хранилища сотрудников (ui.civic_store)")
    store.accounts.create_user("r15-victim", "R15-Strong-Pass-2026", display_name="R15", role="editor")
    origin = "http://127.0.0.1:%d" % srv.server_address[1]
    statuses = []
    for i in range(30):
        status, _h, _data = request(srv, "POST", "/api/civic/v1/session/login",
                                    {"username": "r15-victim", "password": "wrong-password-%04d" % i},
                                    headers={"Origin": origin})
        statuses.append(status)
        if status == 429:
            break
    assert 429 in statuses, statuses
    assert statuses.count(429) == 1 and all(s in (401, 403) for s in statuses[:-1]), statuses


@pytest.mark.parametrize("password", ["short-pass", "password1234", "r15-editor-2026-x", "aaaaaaaaaaaaaa"])
def test_weak_staff_password_is_refused(tmp_path, password):
    auth = need_module("ui.civic_store.auth")
    with pytest.raises(auth.PasswordPolicyError):
        auth.check_password_policy("r15-editor", password)


@xfail("S15")
@pytest.mark.parametrize("password", ["password12345", "Astana2026!!!", "akimat123456", "Qwerty-2026-10"])
def test_common_base_with_digits_is_refused(password):
    """Список простых паролей — 10 точных строк: «password12345» и «Astana2026!!!» проходят (подбираются первыми)."""
    auth = need_module("ui.civic_store.auth")
    with pytest.raises(auth.PasswordPolicyError):
        auth.check_password_policy("r15-editor", password)


@pytest.mark.parametrize("password", ["R15-Strong-Pass-2026", "Tulpar-Bayterek-2026", "Tz7-qerB-91vk-Lmsd"])
def test_strong_staff_password_is_accepted(password):
    auth = need_module("ui.civic_store.auth")
    auth.check_password_policy("r15-editor", password)


def test_every_inline_script_is_allowed_by_its_page_csp(srv):
    """Строгая CSP (S01): у каждой HTML-страницы из белого списка хэш каждого встроенного <script> есть в её CSP —
    иначе браузер молча заблокирует скрипт (ui-kit, «Картина дня»). Скрипты по src — только со своего сервера."""
    import base64
    import hashlib
    import re
    web_server = need_module("ui.web_server")
    pages = [url for url, (_f, ctype) in web_server.ASSETS.items() if ctype.startswith("text/html")]
    assert pages, "в белом списке нет HTML"
    inline = re.compile(rb"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.S | re.I)
    for url in pages:
        status, headers, body = request(srv, "GET", url)
        assert status == 200, url
        csp = headers.get("content-security-policy", "")
        for match in inline.finditer(body):
            digest = base64.b64encode(hashlib.sha256(match.group(1)).digest()).decode("ascii")
            assert "'sha256-%s'" % digest in csp, (url, digest)
        for src in re.findall(rb"<script[^>]*\bsrc\s*=\s*[\"']([^\"']+)", body):
            # свой сервер: /путь или ../путь; чужой — со схемой (https:) или «//хост»
            assert not re.match(rb"^([a-zA-Z][a-zA-Z0-9+.-]*:|//)", src), (url, src)


# --- 5. офлайн-подложка (R01 ночь 3c, web/civic/offline/serve.py): тот же белый список, без выхода за папку --------

OFFLINE_TRAVERSAL = [
    "/civic/offline/serve.py", "/civic/offline/../../../ui/web_server.py", "/civic/offline/%2e%2e/%2e%2e/%2e%2e/ui/web_server.py",
    "/civic/offline/fonts/Noto%20Sans%20Regular/../../serve.py", "/civic/offline/fonts/..%2f..%2fserve.py",
    "/civic/offline/fonts/Noto%20Sans%20Regular/0-255.pbf/../../../serve.py", "/civic/offline/fonts/Noto%20Sans%20Regular/1-256.pbf",
    "/civic/offline/sprites/", "/civic/offline/", "/civic/offline/astana.pmtiles/../../../../.git/config",
    "/civic/offline/..%5c..%5c..%5cui%5cweb_server.py", "/civic/offline/style.json/..%2f..%2f..%2f..%2f.env",
]


@pytest.mark.parametrize("path", OFFLINE_TRAVERSAL)
def test_offline_basemap_server_has_no_path_traversal(srv, path):
    need_module("web.civic.offline.serve")
    status, _headers, body = request(srv, "GET", path)
    assert status == 404, (path, status)
    assert b"import " not in body and b"[core]" not in body


def test_offline_basemap_status_and_bad_range(srv):
    need_module("web.civic.offline.serve")
    status, _h, body = request(srv, "GET", "/civic/offline/status.json")
    assert status == 200 and isinstance(json.loads(body).get("available"), bool)
    # Range разбирается только для архива; кривой Range у JSON просто игнорируется (200, не 500).
    status, _h, _b = request(srv, "GET", "/civic/offline/style.json", headers={"Range": "bytes=abc-"})
    assert status in (200, 404)
