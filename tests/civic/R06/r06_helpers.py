"""Хелперы тестов R06. БД — временный файл pytest, вне репозитория."""

from datetime import datetime, timedelta, timezone

import pytest

from ui.civic_feedback import FeedbackService
from ui.civic_feedback.fixtures import (FIXTURE_EDITOR, fixture_context,
                                        fixture_object_lookup)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def service(tmp_path, clock):
    svc = FeedbackService(tmp_path / "runtime" / "feedback.sqlite3", fixture_object_lookup, clock)
    yield svc
    svc.close()


def submit(service, body=None, ip="127.0.0.1", **overrides):
    payload = {"object_id": "demo-astana-work-01", "geometry": None, "category": "sidewalks",
               "text": "Нет безопасного прохода вдоль ограждения, люди идут по проезжей части.",
               "consent_public": True}
    payload.update(body or {})
    payload.update(overrides)
    return service.handle("POST", "/api/civic/v1/feedback", {}, payload, None, fixture_context(ip))


def staff(service, method, path, body=None, principal=FIXTURE_EDITOR, context=None, query=None):
    if context is None:
        csrf = principal.get("csrf_token") if isinstance(principal, dict) else None
        context = fixture_context(csrf=csrf)
    return service.handle(method, "/api/civic/v1" + path, query or {}, body, principal, context)


def public_list(service, object_id="demo-astana-work-01"):
    return service.handle("GET", f"/api/civic/v1/objects/{object_id}/feedback", {}, None, None,
                          fixture_context())


def queue_items(service, moderation="pending"):
    response = staff(service, "GET", "/staff/feedback", query={"moderation": moderation})
    assert response["status"] == 200, response
    return response["body"]["data"]["items"]


def moderate(service, staff_id, revision, action="approve", reason="Внутренняя причина R06-test",
             principal=FIXTURE_EDITOR, **extra):
    body = {"expected_revision": revision, "action": action, "reason": reason}
    body.update(extra)
    return staff(service, "POST", f"/staff/feedback/{staff_id}/moderate", body, principal=principal)
