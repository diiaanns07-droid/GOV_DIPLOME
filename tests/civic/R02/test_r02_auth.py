"""R02: вход редактора, сессии, CSRF, same-origin/Host, ограничение попыток и права."""

import logging
import sqlite3

import pytest

from ui.civic_store import auth
from ui.civic_store.service import CivicService
from r02_helpers import Editor, PASSWORD, call, context, cookie_from, sample_object


def login(service, username="editor1", password=PASSWORD, **ctx):
    return call(service, "POST", "/session/login", {"username": username, "password": password},
                ctx=context(**ctx))


def test_login_sets_hardened_cookie_and_session_reports_user(service):
    result = login(service)
    assert result["status"] == 200
    cookie = result["headers"]["Set-Cookie"]
    for part in ("civic_session=", "HttpOnly", "SameSite=Strict", "Path=/api/civic/v1", "Max-Age=28800"):
        assert part in cookie
    assert "Secure" not in cookie
    data = result["body"]["data"]
    assert data["authenticated"] is True
    assert data["user"] == {"name": "Редактор Один", "role": "editor"}
    assert len(data["csrf_token"]) >= 40
    token = cookie_from(result)
    assert token not in str(result["body"])  # токен сессии только в cookie
    state = call(service, "GET", "/session", ctx=context(token))["body"]["data"]
    assert state == data
    https = login(service, https=True)["headers"]["Set-Cookie"]
    assert https.endswith("; Secure")


def test_wrong_password_and_unknown_user_look_the_same(service):
    wrong = login(service, password="not-the-password-1")
    unknown = login(service, username="nobody", password="not-the-password-1")
    assert wrong["status"] == unknown["status"] == 401
    assert wrong["body"] == unknown["body"]
    assert "Set-Cookie" not in wrong["headers"]
    assert call(service, "GET", "/session")["body"]["data"] == {
        "authenticated": False, "user": None, "csrf_token": None}


@pytest.mark.parametrize("body", [{}, {"username": "editor1"}, {"username": 5, "password": PASSWORD},
                                  {"username": "editor1", "password": ["x"]}])
def test_malformed_login_is_422(service, body):
    assert call(service, "POST", "/session/login", body)["status"] == 422


def test_staff_endpoints_require_session(service):
    for method, path, body in (("GET", "/staff/objects", None), ("GET", "/staff/objects/ast-1", None),
                               ("POST", "/staff/objects", sample_object()),
                               ("POST", "/staff/objects/ast-1/publish", {"expected_revision": 1, "reason": "x"})):
        result = call(service, method, path, body)
        assert result["status"] == 401 and result["body"]["error"]["code"] == "unauthenticated"


def test_csrf_token_required_for_writes(editor, service):
    no_token = call(service, "POST", "/staff/objects", sample_object(), ctx=context(editor.cookie))
    wrong = call(service, "POST", "/staff/objects", sample_object(), ctx=context(editor.cookie, "x" * 43))
    other = Editor(service, "editor2", PASSWORD + "x")
    swapped = call(service, "POST", "/staff/objects", sample_object(), ctx=context(editor.cookie, other.csrf))
    for result in (no_token, wrong, swapped):
        assert result["status"] == 403 and result["body"]["error"]["code"] == "csrf_failed"
    assert editor.get("/staff/objects")["body"]["data"]["items"] == []  # ничего не создано
    assert editor.get("/staff/objects")["status"] == 200  # чтение без CSRF допустимо


def test_cross_origin_and_foreign_host_are_refused(editor, service):
    cross = call(service, "POST", "/staff/objects", sample_object(), ctx=editor.ctx(same_origin=False))
    assert cross["status"] == 403 and cross["body"]["error"]["code"] == "cross_origin"
    assert login(service, same_origin=False)["status"] == 403
    rebinding = call(service, "GET", "/staff/objects", ctx=editor.ctx(host_allowed=False))
    assert rebinding["status"] == 403 and rebinding["body"]["error"]["code"] == "forbidden_host"
    assert login(service, host_allowed=False)["status"] == 403
    assert service.resolve_principal(editor.ctx(host_allowed=False)) is None
    # Безопасное значение по умолчанию: контекст без ключей не даёт доступа.
    bare = {"headers": {"Cookie": f"civic_session={editor.cookie}", "X-CSRF-Token": editor.csrf}}
    assert service.resolve_principal(bare) is None
    assert service.handle("GET", "/api/civic/v1/staff/objects", "", None, bare)["status"] == 403
    # Публичное чтение не зависит от сессии.
    assert call(service, "GET", "/objects", ctx={})["status"] == 200


def test_actor_and_role_from_body_are_ignored(editor, editor2, service):
    item = editor.create()
    result = editor2.post(f"/staff/objects/{item['id']}/update", {
        "expected_revision": 1, "reason": "проверка", "actor": "editor1", "role": "admin",
        "user_id": 1, "publication": "published",
        "changes": {"title": "Изменил второй", "publication": "published", "revision": 50,
                    "actor": "mayor", "updated_by": "editor1"}})
    assert result["status"] == 200
    data = result["body"]["data"]
    assert data["item"]["publication"] == "draft" and data["item"]["revision"] == 2
    assert data["item"]["staff"]["updated_by"] == "editor2"
    assert {"actor", "role", "user_id", "publication", "changes.publication", "changes.revision",
            "changes.actor", "changes.updated_by"} <= set(data["ignored_fields"])
    history = editor.get(f"/staff/objects/{item['id']}")["body"]["data"]["history"]
    assert history[-1]["actor_label"] == "editor2"
    assert call(service, "GET", f"/objects/{item['id']}")["status"] == 404
    # Роль из тела входа тоже не принимается.
    result = call(service, "POST", "/session/login",
                  {"username": "editor2", "password": PASSWORD + "x", "role": "admin"})
    assert result["body"]["data"]["user"]["role"] == "editor"
    principal = service.resolve_principal(context(cookie_from(result)))
    assert principal.role == "editor" and principal.username == "editor2"


def test_idle_and_absolute_expiry(service, clock):
    editor = Editor(service, "editor1", PASSWORD)
    clock.advance(minutes=59)
    assert editor.get("/staff/objects")["status"] == 200  # продлевает простой
    clock.advance(minutes=59)
    assert editor.get("/staff/objects")["status"] == 200
    clock.advance(minutes=61)
    expired = editor.get("/staff/objects")
    assert expired["status"] == 401
    assert "Max-Age=0" in expired["headers"]["Set-Cookie"]
    state = call(service, "GET", "/session", ctx=editor.ctx())
    assert state["body"]["data"]["authenticated"] is False
    assert "Max-Age=0" in state["headers"]["Set-Cookie"]

    active = Editor(service, "editor1", PASSWORD)
    for _ in range(9):  # активная работа, но абсолютный срок 8 часов
        clock.advance(minutes=55)
        status = active.get("/staff/objects")["status"]
    assert status == 401


def test_logout_revokes_server_session(service):
    editor = Editor(service, "editor1", PASSWORD)
    no_csrf = call(service, "POST", "/session/logout", {}, ctx=context(editor.cookie))
    assert no_csrf["status"] == 403
    result = editor.post("/session/logout", {})
    assert result["status"] == 200
    assert result["body"]["data"] == {"authenticated": False, "user": None, "csrf_token": None}
    assert "Max-Age=0" in result["headers"]["Set-Cookie"]
    # Старая cookie больше не работает, даже если браузер её сохранил.
    assert editor.get("/staff/objects")["status"] == 401
    assert editor.post("/staff/objects", sample_object())["status"] == 401
    # Повторный logout без живой сессии безопасен.
    assert call(service, "POST", "/session/logout", {})["status"] == 200


def test_login_rotates_and_revokes_previous_session(service):
    first = Editor(service, "editor1", PASSWORD)
    second = call(service, "POST", "/session/login", {"username": "editor1", "password": PASSWORD},
                  ctx=context(first.cookie))
    assert cookie_from(second) != first.cookie
    assert first.get("/staff/objects")["status"] == 401


def test_failed_logins_are_rate_limited(service, clock):
    for _ in range(auth.MAX_FAILS_PER_USER_CLIENT):
        assert login(service, password="wrong-password-123")["status"] == 401
    limited = login(service)  # даже правильный пароль не проверяется
    assert limited["status"] == 429
    retry = int(limited["headers"]["Retry-After"])
    assert 1 <= retry <= auth.FAIL_WINDOW
    assert login(service, client_ip="10.0.0.9")["status"] == 200  # другой клиент
    clock.advance(seconds=auth.FAIL_WINDOW + 1)
    assert login(service)["status"] == 200


def test_client_wide_limit(service):
    for index in range(auth.MAX_FAILS_PER_CLIENT):
        login(service, username=f"user{index:03d}", password="wrong-password-123", client_ip="10.1.1.1")
    assert login(service, client_ip="10.1.1.1")["status"] == 429


def test_secrets_are_not_stored_or_logged(service, db_path, caplog):
    caplog.set_level(logging.DEBUG)
    good = login(service)
    login(service, password="Wrong-Secret-Value-9")
    token = cookie_from(good)
    csrf = good["body"]["data"]["csrf_token"]
    Editor(service, "editor1", PASSWORD).post("/session/logout", {})
    logs = caplog.text
    for secret in (PASSWORD, "Wrong-Secret-Value-9", token, csrf):
        assert secret not in logs
    with sqlite3.connect(db_path) as conn:
        dump = "\n".join(conn.iterdump())
    assert PASSWORD not in dump and token not in dump
    assert auth.token_hash(token) in dump
    hashes = [row[0] for row in sqlite3.connect(db_path).execute("SELECT password_hash FROM civic_users")]
    assert all(value.startswith("scrypt$") for value in hashes)
    principal = service.resolve_principal(context(token))
    assert principal is None or token not in repr(principal)


@pytest.mark.real_kdf
def test_production_kdf_parameters_and_verification():
    assert (auth.SCRYPT_N, auth.SCRYPT_R, auth.SCRYPT_P) == (2 ** 14, 8, 5)
    stored = auth.hash_password("Correct-Horse-Battery-9")
    scheme, n, r, p, salt, digest = stored.split("$")
    assert (scheme, int(n), int(r), int(p)) == ("scrypt", 2 ** 14, 8, 5)
    assert auth.verify_password("Correct-Horse-Battery-9", stored)
    assert not auth.verify_password("correct-horse-battery-9", stored)
    assert auth.hash_password("Correct-Horse-Battery-9") != stored  # уникальная соль
    assert not auth.verify_password("x", "plaintext-password")


@pytest.mark.parametrize("username,password", [
    ("editor9", "short"), ("editor9", "password1234"), ("editor9", "my-editor9-password"),
    ("editor9", "aaaaaaaaaaaaaaaa"), ("Bad Name", "Fine-Password-2026"), ("ab", "Fine-Password-2026"),
])
def test_password_and_username_policy(service, username, password):
    with pytest.raises(auth.PasswordPolicyError):
        service.accounts.create_user(username, password)


def test_duplicate_and_disabled_users(service):
    with pytest.raises(auth.PasswordPolicyError):
        service.accounts.create_user("EDITOR1", "Another-Strong-Pass-1")
    editor = Editor(service, "editor1", PASSWORD)
    service.accounts.disable_user("editor1")
    assert editor.get("/staff/objects")["status"] == 401
    assert login(service)["status"] == 401


def test_password_change_revokes_sessions(service):
    editor = Editor(service, "editor1", PASSWORD)
    service.accounts.set_password("editor1", "New-Strong-Pass-2026")
    assert editor.get("/staff/objects")["status"] == 401
    assert login(service, password="New-Strong-Pass-2026")["status"] == 200


def test_no_default_accounts_exist(tmp_path):
    fresh = CivicService(tmp_path / "fresh.sqlite3")
    assert fresh.accounts.list_users() == []
    for username, password in (("admin", "admin"), ("admin", "admin123"), ("editor", "editor")):
        assert login(fresh, username=username, password=password)["status"] == 401


def test_parallel_wrong_passwords_cannot_exceed_limit(service):
    import threading
    barrier = threading.Barrier(12)
    statuses = []

    def attempt():
        barrier.wait()
        statuses.append(login(service, password="wrong-password-123", client_ip="10.9.9.9")["status"])

    threads = [threading.Thread(target=attempt) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert statuses.count(401) == auth.MAX_FAILS_PER_USER_CLIENT  # ровно 5 проверок пароля
    assert statuses.count(429) == 12 - auth.MAX_FAILS_PER_USER_CLIENT
    assert login(service, client_ip="10.9.9.9")["status"] == 429
