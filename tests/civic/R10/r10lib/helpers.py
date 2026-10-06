"""Shared steps for acceptance tests: one vocabulary for create/publish/update/feedback.

Contract gaps (body shape of POST /staff/objects, nested vs dotted `changes`) are
handled here in one place; see ACCEPTANCE.txt "contract ambiguities".
Tests tag themselves with acceptance IDs in the first docstring line, e.g. "[A04] ...".
"""

from __future__ import annotations

import os
import secrets
import time
import unittest

from . import contract
from .client import CivicClient, Resp
from .target import get_target

CREATE_WRAP = os.environ.get("R10_CREATE_WRAP")  # e.g. "item" -> {"item": {...}}


def token(prefix: str = "r10") -> str:
    """Unique marker so a test can find its own rows among other tests' data."""
    return f"{prefix}-{secrets.token_hex(4)}"


def object_payload(**overrides) -> dict:
    """Valid synthetic civic-v1 editable fields; never claims to be a real Astana work."""
    marker = overrides.pop("marker", None) or token("obj")
    payload = {
        "kind": "roadworks",
        "title": f"R10 проверочный объект {marker}",
        "description": "Синтетическая запись приёмочного теста R10. Не сведения о реальных работах.",
        "status": "planned",
        "geometry": {"type": "Point", "coordinates": [71.43, 51.17]},
        "geometry_precision": "approximate",
        "schedule": {"planned_start": "2026-10-14", "original_planned_end": "2026-10-20",
                     "current_planned_end": "2026-10-20", "actual_end": None},
        "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
        "responsible": {"organization": None, "public_contact": None},
        "evidence_type": "synthetic",
        "source_refs": [],
        "evidence_notes": "R10 acceptance fixture; synthetic.",
    }
    for key, value in overrides.items():
        payload[key] = value
    return payload


def wrap_create(payload: dict) -> dict:
    return {CREATE_WRAP: payload} if CREATE_WRAP else payload


def expect_ok(tc: unittest.TestCase, r: Resp, what: str, statuses=(200, 201)) -> dict:
    tc.assertIn(r.status, statuses, f"{what}: {r.brief()}")
    tc.assertEqual(contract.check_envelope(r.json, r.status), [], f"{what}: {r.brief()}")
    return r.data


def expect_error(tc: unittest.TestCase, r: Resp, what: str, statuses) -> dict:
    tc.assertIn(r.status, statuses, f"{what}: {r.brief()}")
    tc.assertFalse(contract.has_traceback(r.text), f"{what}: traceback/internal text in error: {r.text[:400]}")
    tc.assertEqual(contract.check_envelope(r.json, r.status), [], f"{what}: {r.brief()}")
    return r.error


def create_draft(tc, editor: CivicClient, **overrides) -> dict:
    r = editor.post("/staff/objects", wrap_create(object_payload(**overrides)))
    data = expect_ok(tc, r, "create draft")
    item = data.get("item") if isinstance(data, dict) else None
    tc.assertIsInstance(item, dict, f"create draft: data.item missing: {r.brief()}")
    return item


def publish(tc, editor: CivicClient, item: dict, reason: str = "R10: публикация для приёмки") -> dict:
    r = editor.post(f"/staff/objects/{item['id']}/publish",
                    {"expected_revision": item["revision"], "reason": reason})
    return expect_ok(tc, r, "publish")["item"]


def update(editor: CivicClient, item: dict, changes: dict, reason: str | None,
           expected_revision: int | None = None) -> Resp:
    body = {"expected_revision": item["revision"] if expected_revision is None else expected_revision,
            "changes": changes}
    if reason is not None:
        body["reason"] = reason
    return editor.post(f"/staff/objects/{item['id']}/update", body)


def archive(editor: CivicClient, item: dict, reason: str = "R10: архивирование") -> Resp:
    return editor.post(f"/staff/objects/{item['id']}/archive",
                       {"expected_revision": item["revision"], "reason": reason})


def published_object(tc, editor: CivicClient | None = None, **overrides) -> tuple[CivicClient, dict]:
    editor = editor or get_target().editor()
    item = create_draft(tc, editor, **overrides)
    return editor, publish(tc, editor, item)


def public_detail(obj_id: str) -> Resp:
    return get_target().client().get(f"/objects/{obj_id}")


def public_ids(query: dict | None = None, max_pages: int = 50) -> list[str]:
    """All IDs in the public list, following next_cursor."""
    c = get_target().client()
    ids, cursor = [], None
    for _ in range(max_pages):
        q = dict(query or {})
        if cursor:
            q["cursor"] = cursor
        r = c.get("/objects", query=q)
        if r.status != 200 or not isinstance(r.data, dict):
            raise AssertionError(f"public list failed: {r.brief()}")
        ids += [it.get("id") for it in r.data.get("items", [])]
        cursor = r.data.get("next_cursor")
        if not cursor:
            break
    return ids


def staff_detail(editor: CivicClient, obj_id: str) -> Resp:
    return editor.get(f"/staff/objects/{obj_id}")


def feedback_body(object_id=None, geometry=None, text=None, consent_public=True,
                  category="roads") -> dict:
    return {"object_id": object_id, "geometry": geometry, "category": category,
            "text": text or f"R10 тестовое сообщение {token('fb')}", "consent_public": consent_public}


def submit_feedback(tc, client: CivicClient, body: dict) -> Resp:
    r = client.post("/feedback", body)
    if r.status == 429:
        raise unittest.SkipTest("feedback rate limit reached during suite; check NOT_RUN, not FAIL")
    return r


def find_staff_feedback(editor: CivicClient, needle: str, max_pages: int = 20) -> list[dict]:
    found, cursor = [], None
    for _ in range(max_pages):
        r = editor.get("/staff/feedback", query={"cursor": cursor} if cursor else None)
        if r.status != 200 or not isinstance(r.data, dict):
            raise AssertionError(f"staff feedback list failed: {r.brief()}")
        found += [it for it in r.data.get("items", []) if needle in str(it.get("text", ""))]
        cursor = r.data.get("next_cursor")
        if not cursor:
            break
    return found


def moderate(editor: CivicClient, fb: dict, action: str, public_reply=None,
             reason: str = "R10 модерация") -> Resp:
    return editor.post(f"/staff/feedback/{fb['id']}/moderate",
                       {"expected_revision": fb.get("revision", 1), "action": action,
                        "reason": reason, "public_reply": public_reply})


def wait_until(predicate, timeout: float = 3.0, interval: float = 0.1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return predicate()
