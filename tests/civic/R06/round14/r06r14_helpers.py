"""Хелперы тестов R06 раунда 14 (этапы, предложения, голоса). БД — временный файл pytest.

Уникальное имя модуля (r06r14_helpers), чтобы не столкнуться с r06_helpers старых тестов R06.
Все объекты — синтетические (evidence_type synthetic), реальных работ здесь нет.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json

import pytest

from ui.civic_store import auth
from ui.civic_store.service import CivicService
from ui.civic_store.v2 import CivicV2


PASSWORD = "Tulpar-Bayterek-2026"
# Нура (внутри полигона района из data/civic/astana/geofence.json) и Есиль.
NURA_POINT = [71.35, 51.13]
ESIL_POINT = [71.42, 51.09]

SAMPLE = {
    "kind": "roadworks",
    "title": "Демонстрационный ремонт прохода",
    "description": "Синтетическая запись для проверки интерфейса. Не сведения о реальных работах.",
    "status": "planned",
    "geometry": {"type": "Point", "coordinates": NURA_POINT},
    "geometry_precision": "approximate",
    "schedule": {"planned_start": "2026-10-14", "original_planned_end": None,
                 "current_planned_end": "2026-10-20", "actual_end": None},
    "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
    "responsible": {"organization": None, "public_contact": None},
    "evidence_type": "synthetic",
    "source_refs": [],
    "evidence_notes": "Тестовая запись R06; не публиковать как реальный ремонт.",
}


class ManualClock:
    def __init__(self, start=datetime(2026, 10, 11, 4, 0, tzinfo=timezone.utc)):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    monkeypatch.setattr(auth, "SCRYPT_N", 2 ** 10)
    monkeypatch.setattr(auth, "SCRYPT_P", 1)


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "civic.sqlite3"


def make_service(db_path, clock):
    # Длинная сессия: тесты «через 15–20 дней» двигают часы, а вход заново тут не проверяется.
    svc = CivicService(db_path, clock=clock, idle_seconds=90 * 86400, absolute_seconds=90 * 86400)
    return svc, CivicV2(svc)


@pytest.fixture
def stack(db_path, clock):
    svc, v2 = make_service(db_path, clock)
    svc.accounts.create_user("editor1", PASSWORD, display_name="Редактор Один", public_label="Акимат")
    return svc, v2


def context(cookie=None, csrf=None, *, same_origin=True, host_allowed=True, client_ip="127.0.0.1"):
    headers = {"Host": "127.0.0.1:8501"}
    if cookie:
        headers["Cookie"] = f"{auth.COOKIE_NAME}={cookie}"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": client_ip, "host_allowed": host_allowed,
            "is_same_origin": same_origin, "is_https": False}


def call(handler, method, path, body=None, query=None, ctx=None, prefix="/api/civic/v2"):
    raw = json.dumps(body).encode("utf-8") if isinstance(body, (dict, list)) else body
    result = handler.handle(method, prefix + path, query, raw, ctx if ctx is not None else context())
    assert result is not None, f"unrouted {method} {path}"
    json.dumps(result["body"], allow_nan=False)  # ответ — строгий JSON
    return result


class Staff:
    """Редактор: вход через v1 (сессия R02), запросы к v1 и v2 с cookie и CSRF."""

    def __init__(self, svc, v2, username="editor1", password=PASSWORD):
        result = call(svc, "POST", "/session/login", {"username": username, "password": password},
                      prefix="/api/civic/v1")
        assert result["status"] == 200, result
        self.svc, self.v2 = svc, v2
        self.cookie = result["headers"]["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
        self.csrf = result["body"]["data"]["csrf_token"]

    def ctx(self, **kwargs):
        return context(self.cookie, self.csrf, **kwargs)

    def v1(self, method, path, body=None):
        return call(self.svc, method, path, body, ctx=self.ctx(), prefix="/api/civic/v1")

    def call(self, method, path, body=None, query=None, **kwargs):
        return call(self.v2, method, path, body, query, ctx=self.ctx(**kwargs))

    def create_object(self, publish=True, **overrides):
        body = copy.deepcopy(SAMPLE)
        body.update(overrides)
        result = self.v1("POST", "/staff/objects", body)
        assert result["status"] == 201, result
        item = result["body"]["data"]["item"]
        if publish:
            result = self.v1("POST", f"/staff/objects/{item['id']}/publish",
                             {"expected_revision": item["revision"], "reason": "Публикация тестовой записи"})
            assert result["status"] == 200, result
            item = result["body"]["data"]["item"]
        return item

    def set_stage(self, object_id, revision, **fields):
        body = {"expected_revision": revision, **fields}
        return self.call("PUT", f"/objects/{object_id}/stage", body)

    def create_proposal(self, **overrides):
        body = {"kind": "square", "geometry": {"type": "Point", "coordinates": NURA_POINT},
                "title_ru": "Сквер у школы", "title_kk": "Мектеп жанындағы гүлзар", "planned_year": 2027}
        body.update(overrides)
        result = self.call("POST", "/proposals", body)
        assert result["status"] == 201, result
        return result["body"]["data"]["item"]


@pytest.fixture
def staff(stack):
    return Staff(*stack)


def device(n=1):
    return f"device-test-{n:04d}-abcdefgh"
