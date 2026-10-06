"""Сгенерировать примеры DTO R06 реальным прогоном FeedbackService на FIXTURE-данных.

    python research/round-11-results/R06/make_examples.py

Пишет research/round-11-results/R06/examples/*.json. Объекты и учётные записи —
синтетические fixtures; номера квитанций/ID случайны в каждом прогоне.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from ui.civic_feedback import FeedbackService  # noqa: E402
from ui.civic_feedback.fixtures import FIXTURE_EDITOR, FIXTURE_NOTICE, fixture_context, fixture_object_lookup  # noqa: E402

OUT = Path(__file__).resolve().parent / "examples"


def main():
    OUT.mkdir(exist_ok=True)
    moment = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        svc = FeedbackService(Path(tmp) / "examples.sqlite3", fixture_object_lookup, lambda: moment,
                              classifier=lambda text, language: {
                                  "label": "sidewalks", "score": 0.42, "score_kind": "uncalibrated_margin",
                                  "needs_review": True, "model_version": "fixture-classifier-0",
                                  "training_data_status": "synthetic_fixture"})
        editor_ctx = fixture_context(csrf=FIXTURE_EDITOR["csrf_token"])

        def call(method, path, body=None, principal=None, context=None, query=None):
            return svc.handle(method, "/api/civic/v1" + path, query or {}, body, principal,
                              context or fixture_context())

        submit_body = {"object_id": "demo-astana-work-01", "geometry": None, "kind": "problem",
                       "category": "sidewalks", "consent_public": True,
                       "client_request_id": "3b1f8a52-6a7e-4c1e-9d55-0d5c2a5e8f10",
                       "text": "Нет прохода вдоль ограждения, люди идут по проезжей части. Тел. +7 701 000 00 00"}
        receipt = call("POST", "/feedback", submit_body)
        call("POST", "/feedback", {"object_id": None, "geometry": {"type": "Point", "coordinates": [71.45, 51.16]},
                                   "kind": "suggestion", "category": "transport_stops", "consent_public": False,
                                   "text": "Предлагаю поставить навес на остановке."},
             context=fixture_context("10.0.0.2"))
        queue = call("GET", "/staff/feedback", principal=FIXTURE_EDITOR)
        blocked = call("POST", "/staff/feedback/1/moderate",
                       {"expected_revision": 1, "action": "approve", "reason": "Проверено: по теме объекта"},
                       principal=FIXTURE_EDITOR, context=editor_ctx)
        approved = call("POST", "/staff/feedback/1/moderate",
                        {"expected_revision": 1, "action": "approve", "reason": "Проверено: по теме объекта",
                         "public_text": "Нет прохода вдоль ограждения, люди идут по проезжей части. Тел. [скрыто]",
                         "public_reply": "Спасибо. Сообщение проверено модератором платформы; "
                                         "это не официальное обращение."},
                        principal=FIXTURE_EDITOR, context=editor_ctx)
        detail = call("GET", "/staff/feedback/1", principal=FIXTURE_EDITOR)
        public = call("GET", "/objects/demo-astana-work-01/feedback")
        stale = call("POST", "/staff/feedback/1/moderate",
                     {"expected_revision": 1, "action": "reject", "reason": "Поздно"},
                     principal=FIXTURE_EDITOR, context=editor_ctx)
        anonymous = call("POST", "/staff/feedback/1/moderate",
                         {"expected_revision": 2, "action": "reject", "reason": "x x x", "role": "admin"})
        missing_place = call("POST", "/feedback", dict(submit_body, object_id=None, client_request_id=None),
                             context=fixture_context("10.0.0.3"))
        svc.close()

    examples = {
        "post_feedback_request.json": submit_body,
        "post_feedback_receipt_201.json": receipt,
        "staff_queue_200.json": queue,
        "staff_moderate_blocked_personal_data_422.json": blocked,
        "staff_moderate_approve_200.json": approved,
        "staff_detail_200.json": detail,
        "public_object_feedback_200.json": public,
        "staff_moderate_stale_409.json": stale,
        "staff_moderate_anonymous_fake_role_401.json": anonymous,
        "post_feedback_no_location_422.json": missing_place,
    }
    for name, payload in examples.items():
        document = {"_note": FIXTURE_NOTICE + " Сгенерировано make_examples.py.", "example": payload}
        (OUT / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(examples)} examples to {OUT}")


if __name__ == "__main__":
    main()
