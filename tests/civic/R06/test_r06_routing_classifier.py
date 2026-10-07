"""Маршрутизация, необязательный классификатор R08 и подсказки похожих сообщений."""

import threading
import time

import pytest

from r06_helpers import moderate, queue_items, staff, submit
from ui.civic_feedback import FeedbackService
from ui.civic_feedback.classifier_adapter import load_r08_classifier
from ui.civic_feedback.fixtures import fixture_context, fixture_object_lookup


# ------------------------------------------------------------------ routing
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/civic/v1/objects/demo-astana-work-01"),
    ("GET", "/api/civic/v1/objects"),
    ("GET", "/api/civic/v1/staff/objects/demo-astana-work-01"),
    ("POST", "/api/civic/v1/staff/objects/demo-astana-work-01/update"),
    ("GET", "/api/civic/v1/session"),
    ("GET", "/"),
    ("GET", "/api/civic/v1"),
    ("GET", "/api/civic/v1/feedbackx"),
    ("GET", "/api/civic/v1/staff"),
])
def test_foreign_paths_are_not_claimed(service, method, path):
    assert service.handle(method, path, {}, None, None, fixture_context()) is None


def test_object_feedback_route_is_not_swallowed_by_object_route(service):
    for path in ("/api/civic/v1/objects/demo-astana-work-01/feedback",
                 "/api/civic/v1/objects/demo-astana-work-01/feedback?limit=5"):
        response = service.handle("GET", path, None, None, None, fixture_context())
        assert response is not None and response["status"] == 200, path
    assert service.handle("GET", "/api/civic/v1/objects/demo-astana-work-01/feedback?limit=x",
                          None, None, None, fixture_context())["status"] == 400


@pytest.mark.parametrize("method,path", [
    ("POST", "/feedback"), ("GET", "/objects/demo-astana-work-01/feedback"), ("GET", "/staff/feedback"),
    ("POST", "/staff/feedback/1/moderate"), ("GET", "/api/civic/v2/feedback"), ("GET", "/api/civic/v1feedback"),
])
def test_paths_without_api_prefix_are_not_claimed(service, method, path):
    # Как R02: возможная статическая страница /feedback не перехватывается сервисом.
    assert service.handle(method, path, {}, None, None, fixture_context()) is None


@pytest.mark.parametrize("method,path,status", [
    ("GET", "/api/civic/v1/feedback", 405),
    ("DELETE", "/api/civic/v1/feedback", 405),
    ("POST", "/api/civic/v1/objects/demo-astana-work-01/feedback", 405),
    ("POST", "/api/civic/v1/staff/feedback", 405),
    ("GET", "/api/civic/v1/staff/feedback/1/moderate", 405),
    ("GET", "/api/civic/v1/feedback/unknown", 404),
    ("GET", "/api/civic/v1/staff/feedback/1/delete", 404),
    ("GET", "/api/civic/v1/objects/demo-astana-work-01/feedback/1", 404),
])
def test_own_namespace_returns_json_errors(service, method, path, status):
    response = service.handle(method, path, {}, None, None, fixture_context())
    assert response["status"] == status and response["body"]["ok"] is False
    assert set(response["body"]["error"]) >= {"code", "message"}
    if status == 405:
        assert response["headers"]["Allow"]


def test_public_and_private_cache_headers(service):
    submit(service)
    public = service.handle("GET", "/api/civic/v1/objects/demo-astana-work-01/feedback", {}, None, None,
                            fixture_context())
    assert public["headers"]["Cache-Control"] == "no-cache"
    assert staff(service, "GET", "/staff/feedback")["headers"]["Cache-Control"] == "no-store"


# --------------------------------------------------------------- classifier
def make_service(tmp_path, clock, classifier, **limits):
    return FeedbackService(tmp_path / "c.sqlite3", fixture_object_lookup, clock,
                           classifier=classifier, limits=limits or None)


def test_classifier_suggestion_is_stored_but_never_changes_category(tmp_path, clock):
    calls = []

    def classifier(text, language):
        calls.append(language)
        return {"label": "lighting", "score": 0.61, "score_kind": "uncalibrated_margin",
                "needs_review": True, "model_version": "fixture-0", "training_data_status": "synthetic"}

    svc = make_service(tmp_path, clock, classifier)
    try:
        assert submit(svc, category="roads")["status"] == 201
        item = queue_items(svc)[0]
        assert calls == ["ru"]
        assert item["category"] == "roads" and item["moderation"] == "pending"
        assert item["classifier"]["status"] == "ok"
        assert item["classifier"]["suggestion"]["label"] == "lighting"
        assert item["classifier"]["suggestion"]["score_kind"] == "uncalibrated_margin"
    finally:
        svc.close()


@pytest.mark.parametrize("behaviour,status", [
    ("raise", "error"), ("garbage", "invalid"), ("bad_label", "invalid"), ("none", "unavailable"),
])
def test_classifier_failure_never_loses_submission(tmp_path, clock, behaviour, status):
    def classifier(text, language):
        if behaviour == "raise":
            raise RuntimeError("model crashed")
        if behaviour == "garbage":
            return "lighting"
        return {"label": "urgent-call-akim", "score": 2}

    svc = make_service(tmp_path, clock, None if behaviour == "none" else classifier)
    try:
        response = submit(svc)
        assert response["status"] == 201 and response["body"]["data"]["moderation"] == "pending"
        item = queue_items(svc)[0]
        assert item["classifier"]["status"] == status and item["classifier"]["suggestion"] is None
    finally:
        svc.close()


def test_hanging_classifier_times_out_without_losing_submission(tmp_path, clock):
    release = threading.Event()

    def classifier(text, language):
        release.wait(5)
        return {"label": "roads"}

    svc = make_service(tmp_path, clock, classifier, classifier_timeout_s=0.2)
    try:
        started = time.monotonic()
        response = submit(svc)
        assert response["status"] == 201 and time.monotonic() - started < 2
        assert queue_items(svc)[0]["classifier"]["status"] == "timeout"
    finally:
        release.set()
        svc.close()


def test_missing_r08_module_returns_none():
    assert load_r08_classifier("ml.civic_classifier_does_not_exist") is None


def test_kazakh_text_language_hint(tmp_path, clock):
    seen = []
    svc = make_service(tmp_path, clock, lambda text, language: seen.append(language) or {"label": "other"})
    try:
        submit(svc, text="Аялдамада жарық жоқ, кешке қараңғы және қауіпті.")
        assert seen == ["kk"]
    finally:
        svc.close()


# ------------------------------------------------------------------ similar
def test_similar_messages_are_suggested_not_merged(service):
    submit(service, text="Нет освещения у прохода вдоль ограждения, вечером очень темно.", ip="10.0.0.1")
    submit(service, text="Вечером темно: нет освещения вдоль ограждения у прохода!", ip="10.0.0.2")
    submit(service, text="Предлагаю поставить урны у входа на площадку.", ip="10.0.0.3")
    items = queue_items(service)
    assert len(items) == 3 and all(i["moderation"] == "pending" for i in items)
    detail = staff(service, "GET", f"/staff/feedback/{items[0]['id']}")["body"]["data"]
    assert [s["id"] for s in detail["similar"]] == [items[1]["id"]]
    assert "не объединяет" in detail["similar_note"]
    assert items[0]["similar_count"] == 1 and items[2]["similar_count"] == 0
    # Отклонение одного не трогает похожее.
    moderate(service, items[0]["id"], items[0]["revision"], action="reject", reason="Дубликат по смыслу")
    assert staff(service, "GET", f"/staff/feedback/{items[1]['id']}")["body"]["data"]["item"]["moderation"] == "pending"


def test_similar_by_place_for_messages_without_object(service):
    near = {"type": "Point", "coordinates": [71.4500, 51.1600]}
    close = {"type": "Point", "coordinates": [71.4510, 51.1605]}
    far = {"type": "Point", "coordinates": [71.5000, 51.1600]}
    text = "Сломан бордюр на переходе, коляски не проезжают."
    submit(service, object_id=None, geometry=near, text=text, ip="10.0.0.1")
    submit(service, object_id=None, geometry=close, text=text, ip="10.0.0.2")
    submit(service, object_id=None, geometry=far, text=text, ip="10.0.0.3")
    first = queue_items(service)[0]
    similar = staff(service, "GET", f"/staff/feedback/{first['id']}")["body"]["data"]["similar"]
    assert len(similar) == 1 and similar[0]["exact_text"] is True


def test_staff_detail_includes_object_context(service):
    submit(service)
    detail = staff(service, "GET", "/staff/feedback/1")["body"]["data"]
    assert detail["object"]["title"] == "Демонстрационный ремонт прохода"
    assert detail["object"]["evidence_type"] == "synthetic"


def test_purge_antispam_keeps_messages(service, clock):
    submit(service)
    clock.advance(days=31)
    assert service.purge_antispam(30) == 1
    item = queue_items(service)[0]
    assert item["text"].startswith("Нет безопасного") and item["antispam"]["same_sender_24h"] == 0


def test_maintenance_cli_stats_and_purge(tmp_path, clock, capsys):
    import json as _json

    from ui.civic_feedback.__main__ import main as cli
    db = tmp_path / "cli.sqlite3"
    svc = FeedbackService(db, fixture_object_lookup, clock)
    submit(svc, text="Секретный текст жителя про яму у въезда.")
    svc.close()
    assert cli(["stats", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    stats = _json.loads(out)
    assert stats["moderation"]["pending"] == 1 and stats["public"] == 0
    assert "Секретный" not in out and "127.0.0.1" not in out
    assert cli(["purge-antispam", "--db", str(db), "--days", "1"]) == 0
    assert cli(["stats", "--db", str(tmp_path / "missing.sqlite3")]) == 2
    assert not (tmp_path / "missing.sqlite3").exists()
