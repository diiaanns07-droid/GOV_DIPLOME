"""Общие фикстуры R02: временная база, ручные часы, редактор и HTTP-подобный вызов."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from ui.civic_store import auth
from ui.civic_store.service import CivicService


PASSWORD = "Tulpar-Bayterek-2026"
FIXTURE = Path(__file__).parent / "fixtures"


class ManualClock:
    def __init__(self, start=datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_kdf: использовать боевые параметры scrypt")


@pytest.fixture(autouse=True)
def fast_kdf(request, monkeypatch):
    """Дешёвые параметры scrypt для скорости тестов; отдельный тест проверяет боевые."""
    if "real_kdf" not in request.keywords:
        monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 10)
        monkeypatch.setattr(auth, "SCRYPT_P", 1)


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "civic.sqlite3"


@pytest.fixture
def service(db_path, clock):
    svc = CivicService(db_path, clock=clock)
    svc.accounts.create_user("editor1", PASSWORD, display_name="Редактор Один",
                             public_label="Редакция платформы")
    svc.accounts.create_user("editor2", PASSWORD + "x", display_name="Редактор Два")
    return svc


def context(cookie=None, csrf=None, *, same_origin=True, host_allowed=True, client_ip="127.0.0.1",
            https=False, headers=None):
    hdrs = {"Host": "127.0.0.1:8501"}
    if cookie:
        hdrs["Cookie"] = f"{auth.COOKIE_NAME}={cookie}"
    if csrf:
        hdrs["X-CSRF-Token"] = csrf
    hdrs.update(headers or {})
    return {"headers": hdrs, "client_ip": client_ip, "host_allowed": host_allowed,
            "is_same_origin": same_origin, "is_https": https}


def call(svc, method, path, body=None, query=None, ctx=None):
    raw = json.dumps(body).encode("utf-8") if isinstance(body, (dict, list)) else body
    result = svc.handle(method, "/api/civic/v1" + path, query, raw, ctx if ctx is not None else context())
    assert result is not None, f"unrouted {method} {path}"
    # Ответ всегда сериализуем строгим JSON (без NaN) — как его отправит адаптер.
    json.dumps(result["body"], allow_nan=False)
    return result


def cookie_from(result):
    header = result["headers"].get("Set-Cookie", "")
    return header.split(";", 1)[0].split("=", 1)[1] if header else None


class Editor:
    def __init__(self, svc, username, password, client_ip="127.0.0.1"):
        result = call(svc, "POST", "/session/login", {"username": username, "password": password},
                      ctx=context(client_ip=client_ip))
        assert result["status"] == 200, result
        self.svc = svc
        self.cookie = cookie_from(result)
        self.csrf = result["body"]["data"]["csrf_token"]

    def ctx(self, **kwargs):
        return context(self.cookie, self.csrf, **kwargs)

    def get(self, path, query=None):
        return call(self.svc, "GET", path, query=query, ctx=self.ctx())

    def post(self, path, body, **kwargs):
        return call(self.svc, "POST", path, body, ctx=self.ctx(**kwargs))

    def create(self, payload=None, **overrides):
        body = copy.deepcopy(payload or sample_object())
        body.update(overrides)
        result = self.post("/staff/objects", body)
        assert result["status"] == 201, result
        return result["body"]["data"]["item"]

    def update(self, item, changes, reason="Уточнение данных", revision=None):
        return self.post(f"/staff/objects/{item['id']}/update",
                         {"expected_revision": revision or item["revision"], "changes": changes,
                          "reason": reason})

    def publish(self, item, reason="Публикация проверенной записи", revision=None):
        return self.post(f"/staff/objects/{item['id']}/publish",
                         {"expected_revision": revision or item["revision"], "reason": reason})

    def archive(self, item, reason="Снято с публикации", revision=None):
        return self.post(f"/staff/objects/{item['id']}/archive",
                         {"expected_revision": revision or item["revision"], "reason": reason})


@pytest.fixture
def editor(service):
    return Editor(service, "editor1", PASSWORD)


@pytest.fixture
def editor2(service):
    return Editor(service, "editor2", PASSWORD + "x")


def sample_object(**overrides):
    """Синтетический объект без реальных фактов (как fixtures/civic_object.json раунда)."""
    data = json.loads((FIXTURE / "civic_object.json").read_text(encoding="utf-8"))
    for key in ("schema_version", "id", "city", "publication", "updated_at", "revision"):
        data.pop(key)
    data["schedule"]["original_planned_end"] = None
    data["schedule"]["current_planned_end"] = "2026-10-20"
    data.update(overrides)
    return data
