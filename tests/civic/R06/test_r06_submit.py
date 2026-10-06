"""POST /feedback: валидация тела, объекта, места, лимиты частоты и повторы."""

import json

import pytest

from r06_helpers import queue_items, submit
from ui.civic_feedback import FeedbackService
from ui.civic_feedback.fixtures import failing_object_lookup, fixture_context


def error(response):
    assert response["body"]["ok"] is False, response
    return response["status"], response["body"]["error"]


@pytest.mark.parametrize("object_id", ["no-such-object", "demo-astana-draft-04",
                                       "demo-astana-archived-05", "demo-other-city-06"])
def test_unknown_draft_archived_or_foreign_object_is_rejected_identically(service, object_id):
    status, err = error(submit(service, object_id=object_id))
    assert status == 422 and err["code"] == "object_not_found"
    # Черновик неотличим от отсутствующего объекта: тот же текст ошибки.
    assert err["message"] == error(submit(service, object_id="no-such-object"))[1]["message"]
    assert "Черновик" not in json.dumps(err, ensure_ascii=False)


@pytest.mark.parametrize("object_id", ["../etc/passwd", "", " ", "a" * 101, 42, ["x"]])
def test_malformed_object_id_is_rejected(service, object_id):
    status, err = error(submit(service, object_id=object_id))
    assert status == 422 and "object_id" in err["fields"]


def test_neither_object_nor_place_gives_clear_error(service):
    status, err = error(submit(service, object_id=None, geometry=None))
    assert status == 422 and err["code"] == "location_required"
    assert "место" in err["fields"]["location"]


def test_place_without_object_is_accepted(service):
    response = submit(service, object_id=None, geometry={"type": "Point", "coordinates": [71.45, 51.16]})
    assert response["status"] == 201
    item = queue_items(service)[0]
    assert item["object_id"] is None and item["geometry"]["coordinates"] == [71.45, 51.16]


@pytest.mark.parametrize("geometry", [
    {"type": "Point", "coordinates": [69.59, 42.32]},          # Шымкент
    {"type": "Point", "coordinates": [51.17, 71.43]},          # перепутаны широта/долгота
    {"type": "Point", "coordinates": [float("nan"), 51.1]},
    {"type": "Point", "coordinates": [71.4]},
    {"type": "Point", "coordinates": [True, 51.1]},
    {"type": "LineString", "coordinates": [[71.4, 51.1], [71.5, 51.1]]},
    {"type": "Point", "coordinates": [71.4, 51.1], "properties": {"x": 1}},
    "71.4,51.1",
])
def test_bad_or_out_of_city_geometry_is_rejected(service, geometry):
    status, err = error(submit(service, object_id=None, geometry=geometry))
    assert status == 422 and "geometry" in err["fields"]


def test_object_and_far_point_conflict(service):
    status, err = error(submit(service, geometry={"type": "Point", "coordinates": [71.60, 51.25]}))
    assert status == 422 and err["code"] == "location_conflict"
    near = submit(service, geometry={"type": "Point", "coordinates": [71.431, 51.171]})
    assert near["status"] == 201


def test_point_inside_polygon_object_is_consistent(service):
    response = submit(service, object_id="demo-astana-park-02",
                      geometry={"type": "Point", "coordinates": [71.405, 51.125]})
    assert response["status"] == 201


@pytest.mark.parametrize("override,field", [
    ({"category": "potholes"}, "category"),
    ({"category": None}, "category"),
    ({"kind": "complaint"}, "kind"),
    ({"text": "коротко"}, "text"),
    ({"text": "x" * 2001}, "text"),
    ({"text": 123}, "text"),
    ({"text": "  \n\t  "}, "text"),
    ({"consent_public": "yes"}, "consent_public"),
    ({"consent_public": None}, "consent_public"),
    ({"client_request_id": "short"}, "client_request_id"),
])
def test_invalid_fields_are_rejected(service, override, field):
    status, err = error(submit(service, override))
    assert status == 422 and field in err["fields"]


def test_missing_consent_is_rejected_not_defaulted(service):
    payload = {"object_id": "demo-astana-work-01", "category": "roads",
               "text": "Яма на въезде во двор, машины объезжают по тротуару."}
    response = service.handle("POST", "/api/civic/v1/feedback", {}, payload, None, fixture_context())
    status, err = error(response)
    assert status == 422 and "consent_public" in err["fields"]


@pytest.mark.parametrize("extra", [{"role": "editor"}, {"moderation": "approved"},
                                   {"phone": "+77011234567"}, {"iin": "900101300123"},
                                   {"revision": 7}, {"public_id": "x"}])
def test_unknown_fields_including_fake_role_are_rejected(service, extra):
    status, err = error(submit(service, extra))
    assert status == 400 and err["code"] == "unknown_fields"
    assert set(extra) <= set(err["fields"])
    assert queue_items(service) == []


def test_body_must_be_json_object_and_not_too_large(service):
    ctx = fixture_context()
    assert error(service.handle("POST", "/api/civic/v1/feedback", {}, b"{not json", None, ctx))[0] == 400
    assert error(service.handle("POST", "/api/civic/v1/feedback", {}, b"[1,2]", None, ctx))[0] == 400
    assert error(service.handle("POST", "/api/civic/v1/feedback", {}, None, None, ctx))[0] == 400
    huge = json.dumps({"text": "x" * 20000}).encode()
    assert error(service.handle("POST", "/api/civic/v1/feedback", {}, huge, None, ctx)) [0] == 413
    big_dict = {"object_id": "demo-astana-work-01", "category": "roads", "consent_public": True,
                "text": "я" * 9000}
    assert error(service.handle("POST", "/api/civic/v1/feedback", {}, big_dict, None, ctx))[0] == 413


def test_bytes_body_is_accepted(service):
    payload = json.dumps({"object_id": "demo-astana-work-01", "category": "lighting",
                          "text": "Не горят фонари вдоль временного ограждения вечером.",
                          "consent_public": False}, ensure_ascii=False).encode()
    response = service.handle("POST", "/api/civic/v1/feedback", "", payload, None, fixture_context())
    assert response["status"] == 201


def test_cross_origin_submission_is_rejected(service):
    response = service.handle("POST", "/api/civic/v1/feedback", {}, {"text": "x"}, None,
                              fixture_context(same_origin=False))
    assert error(response) == (403, error(response)[1]) and error(response)[1]["code"] == "cross_origin"
    missing = service.handle("POST", "/api/civic/v1/feedback", {}, {"text": "x"}, None, {"client_ip": "1.2.3.4"})
    assert missing["status"] == 403


def test_text_is_cleaned_of_control_characters(service):
    response = submit(service, text="Плохо‮ видно \x00знак\r\nобъезда на углу.")
    assert response["status"] == 201
    stored = queue_items(service)[0]["text"]
    assert "‮" not in stored and "\x00" not in stored and "\r" not in stored
    assert stored == "Плохо видно знак\nобъезда на углу."


def test_object_lookup_failure_returns_json_error_not_traceback(tmp_path, clock):
    svc = FeedbackService(tmp_path / "f.sqlite3", failing_object_lookup, clock)
    try:
        status, err = error(submit(svc))
        assert status == 503 and err["code"] == "object_lookup_unavailable"
    finally:
        svc.close()


# ----------------------------------------------------------------- rate limit
def test_rate_limit_per_sender_with_few_local_requests(service, clock):
    texts = [f"Сообщение номер {n}: нужен пешеходный переход у остановки." for n in range(6)]
    statuses = [submit(service, text=t)["status"] for t in texts[:5]]
    assert statuses == [201] * 5
    limited = submit(service, text=texts[5])
    assert limited["status"] == 429 and limited["headers"]["Retry-After"]
    # Другой отправитель не блокируется чужим лимитом.
    assert submit(service, text=texts[5], ip="10.0.0.2")["status"] == 201
    clock.advance(minutes=11)
    assert submit(service, text=texts[5])["status"] == 201


def test_global_rate_limit(tmp_path, clock):
    from ui.civic_feedback.fixtures import fixture_object_lookup
    svc = FeedbackService(tmp_path / "g.sqlite3", fixture_object_lookup, clock,
                          limits={"global_max": 3})
    try:
        results = [submit(svc, ip=f"10.0.0.{n}")["status"] for n in range(4)]
        assert results == [201, 201, 201, 429]
    finally:
        svc.close()


# ------------------------------------------------------------------ duplicates
def test_repeated_identical_submit_warns_instead_of_silently_duplicating(service):
    assert submit(service)["status"] == 201
    again = submit(service, text="  нет безопасного прохода вдоль ограждения, люди идут по проезжей части!! ")
    status, err = error(again)
    assert status == 409 and err["code"] == "duplicate_warning" and err["can_confirm"] is True
    assert len(queue_items(service)) == 1
    confirmed = submit(service, confirm_duplicate=True)
    assert confirmed["status"] == 201
    items = queue_items(service)
    assert len(items) == 2 and items[1]["antispam"]["duplicate_confirmed_by_sender"] is True


def test_same_client_request_id_replays_receipt(service):
    request_id = "0f8fad5b-d9cb-469f-a165-70867728950e"
    first = submit(service, client_request_id=request_id)
    second = submit(service, client_request_id=request_id)
    assert first["status"] == 201 and second["status"] == 200
    assert second["body"]["data"]["receipt_id"] == first["body"]["data"]["receipt_id"]
    assert second["body"]["data"]["replayed"] is True
    assert len(queue_items(service)) == 1
    # Тот же id с другим текстом — конфликт, а не подмена.
    other = submit(service, client_request_id=request_id, text="Совсем другое сообщение про освещение.")
    assert error(other)[1]["code"] == "request_id_conflict"
    # Чужой отправитель с тем же id не получает чужую квитанцию.
    foreign = submit(service, client_request_id=request_id, ip="10.9.9.9")
    assert foreign["status"] == 201
    assert foreign["body"]["data"]["receipt_id"] != first["body"]["data"]["receipt_id"]


def test_receipt_warns_about_contact_data(service):
    response = submit(service, text="Позвоните мне +7 701 123 45 67, яма у подъезда очень глубокая.")
    warnings = response["body"]["data"]["warnings"]
    assert response["status"] == 201 and warnings and "не будут опубликованы" in warnings[0]


@pytest.mark.parametrize("raw", [
    b'{"object_id":"demo-astana-work-01","category":"roads","consent_public":true,"text":"\\ud800 \xd1\x8f\xd0\xbc\xd0\xb0 \xd1\x83 \xd0\xb2\xd1\x8a\xd0\xb5\xd0\xb7\xd0\xb4\xd0\xb0"}',
    b'{"\\udc00":1}',
])
def test_lone_surrogate_gives_json_400_not_exception(service, raw):
    response = service.handle("POST", "/api/civic/v1/feedback", {}, raw, None, fixture_context())
    assert response["status"] == 400 and response["body"]["error"]["code"] in ("invalid_text", "unknown_fields")
    assert queue_items(service) == []


def test_surrogate_in_dict_body_is_rejected(service):
    response = submit(service, text="Яма у въезда \ud800 во двор, глубокая.")
    assert response["status"] == 400 and response["body"]["error"]["code"] == "invalid_text"


def test_unexpected_exception_becomes_json_500(service, monkeypatch):
    def boom(object_id):
        raise KeyError("boom /srv/secret.py")

    monkeypatch.setattr(service, "_lookup", boom)
    response = submit(service)
    assert response["status"] == 500 and response["body"]["error"]["code"] == "internal_error"
    dumped = json.dumps(response, ensure_ascii=False)
    assert "boom" not in dumped and "secret" not in dumped and "KeyError" not in dumped
