"""R02: создание/чтение объектов, проверка civic-v1, публичная проекция и перезапуск."""

import json
import math

import pytest

from ui.civic_store.service import CivicService
from r06store_helpers import Editor, PASSWORD, call, context, sample_object


SENTINEL_NOTE = "СЛУЖЕБНО-не-для-публики-7781"


def public_get(service, object_id):
    return call(service, "GET", f"/objects/{object_id}")


def test_create_draft_assigns_server_fields_and_ignores_client_ones(editor, service):
    body = sample_object(id="evil-id", revision=99, publication="published",
                         updated_at="2000-01-01T00:00:00Z", actor="admin", role="admin",
                         created_by="mayor", schema_version="civic-v0")
    result = editor.post("/staff/objects", body)
    assert result["status"] == 201
    item = result["body"]["data"]["item"]
    assert item["id"] != "evil-id" and item["id"].startswith("ast-")
    assert item["revision"] == 1
    assert item["publication"] == "draft"
    assert item["schema_version"] == "civic-v1" and item["city"] == "astana"
    assert item["updated_at"] == "2026-10-06T09:00:00+00:00"
    assert item["staff"]["created_by"] == "editor1"
    assert set(result["body"]["data"]["ignored_fields"]) >= {"actor", "role", "revision", "publication", "id"}


def test_draft_is_invisible_publicly(editor, service):
    item = editor.create()
    detail = public_get(service, item["id"])
    assert detail["status"] == 404 and detail["body"]["ok"] is False
    assert detail["body"]["error"]["code"] == "not_found"
    listing = call(service, "GET", "/objects")
    assert listing["body"]["data"] == {"items": [], "next_cursor": None}


def test_missing_object_is_404_not_empty_success(editor, service):
    assert public_get(service, "ast-0000000000")["status"] == 404
    assert editor.get("/staff/objects/ast-0000000000")["status"] == 404


@pytest.mark.parametrize("path", ["/objects/", "/objects/%20", "/objects/..", "/objects/a%2Fb",
                                  "/objects/" + "x" * 65, "/staff/objects/"])
def test_empty_or_invalid_id_is_an_error(editor, service, path):
    result = call(service, "GET", path, ctx=editor.ctx())
    assert result["status"] == 400
    assert result["body"]["error"]["code"] == "bad_request"


BAD_PAYLOADS = [
    ("schedule.planned_start", {"schedule": {"planned_start": "2026-02-30"}}),
    ("schedule.planned_start", {"schedule": {"planned_start": "06.10.2026"}}),
    ("schedule.current_planned_end", {"schedule": {"planned_start": "2026-10-14",
                                                   "current_planned_end": "2026-10-01"}}),
    ("schedule.actual_end", {"status": "completed", "schedule": {"actual_end": "2027-01-01"}}),
    ("schedule.actual_end", {"status": "in_progress", "schedule": {"actual_end": "2026-10-01"}}),
    ("budget.amount_kzt", {"budget": {"amount_kzt": -5, "basis": "planned", "source_id": None}}),
    ("budget.amount_kzt", {"budget": {"amount_kzt": True, "basis": "planned", "source_id": None}}),
    ("budget.amount_kzt", {"budget": {"amount_kzt": "1000", "basis": "planned", "source_id": None}}),
    ("budget.source_id", {"budget": {"amount_kzt": 1000, "basis": "planned", "source_id": None},
                          "evidence_type": "observed"}),
    ("title", {"title": "x" * 201}),
    ("title", {"title": "   "}),
    ("title", {"title": "<script>alert(1)</script>"}),
    ("title", {"title": "Ремонт\u202eтекст"}),
    ("description", {"description": "д" * 5001}),
    ("kind", {"kind": "parade"}),
    ("status", {"status": "done"}),
    ("evidence_type", {"evidence_type": "verified"}),
    ("geometry.type", {"geometry": {"type": "MultiPoint", "coordinates": [[71.4, 51.1]]}}),
    ("geometry.coordinates", {"geometry": {"type": "Point", "coordinates": [51.17, 71.43]}}),
    ("geometry.coordinates", {"geometry": {"type": "Point", "coordinates": [71.43]}}),
    ("geometry.coordinates", {"geometry": {"type": "Point", "coordinates": [True, 51.1]}}),
    ("geometry", {"geometry": {"type": "LineString", "coordinates": [[71.4, 51.1]]}}),
    ("geometry.coordinates[0]", {"geometry": {"type": "Polygon", "coordinates": [
        [[71.4, 51.1], [71.5, 51.1], [71.5, 51.2], [71.41, 51.11]]]}}),
    ("geometry", {"geometry": {"type": "Point", "coordinates": [71.4, 51.1], "crs": "x"}}),
    ("source_refs[0].url", {"source_refs": [{"id": "s1", "url": "javascript:alert(1)",
                                             "access_status": "not_fetched"}]}),
    ("source_refs[0].url", {"source_refs": [{"id": "s1", "url": "https://user:pw@example.org/",
                                             "access_status": "not_fetched"}]}),
    ("source_refs[0].retrieved_at", {"source_refs": [{"id": "s1", "url": "https://example.org/",
                                                      "access_status": "fetched"}]}),
    ("source_refs[1].id", {"source_refs": [
        {"id": "s1", "url": "https://example.org/a", "access_status": "not_fetched"},
        {"id": "s1", "url": "https://example.org/b", "access_status": "not_fetched"}]}),
    ("source_refs[0].fields[0]", {"source_refs": [{"id": "s1", "url": "https://example.org/",
                                                   "access_status": "not_fetched",
                                                   "fields": ["password_hash"]}]}),
    ("internal_secret", {"internal_secret": "x"}),
    ("schedule.finished", {"schedule": {"finished": "2026-10-01"}}),
]


@pytest.mark.parametrize("field,overrides", BAD_PAYLOADS, ids=[f"{f}-{i}" for i, (f, _) in enumerate(BAD_PAYLOADS)])
def test_invalid_payloads_are_rejected_with_field(editor, service, field, overrides):
    body = sample_object()
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(body.get(key), dict):
            body[key] = {**body[key], **value}
        else:
            body[key] = value
    result = editor.post("/staff/objects", body)
    assert result["status"] == 422, result
    assert result["body"]["error"]["code"] == "validation_failed"
    assert field in result["body"]["error"]["fields"], result["body"]["error"]["fields"]
    staff = editor.get("/staff/objects")["body"]["data"]["items"]
    assert staff == []  # ничего не записано


BAD_JSON = {"nan": b'{"title": NaN}', "inf": b'{"title": Infinity}', "neg-inf": b'{"x": -Infinity}',
            "garbage": b"not json", "array": b"[1,2]", "deep": b"[" * 30000 + b"]" * 30000,
            "surrogate": "\ud800".encode("utf-8", "surrogatepass")}


@pytest.mark.parametrize("raw", list(BAD_JSON.values()), ids=list(BAD_JSON))
def test_non_finite_numbers_and_bad_json_are_400(editor, service, raw):
    result = call(service, "POST", "/staff/objects", raw, ctx=editor.ctx())
    assert result["status"] == 400
    assert result["body"]["error"]["code"] == "bad_request"


def test_too_large_body_is_413(editor, service):
    body = json.dumps({"title": "x", "description": "y" * 70000}).encode()
    result = call(service, "POST", "/staff/objects", body, ctx=editor.ctx())
    assert result["status"] == 413


def test_unknown_cost_stays_null_and_actual_end_never_appears(editor, service):
    item = editor.create(status="planned")
    assert item["budget"] == {"amount_kzt": None, "basis": "unknown", "source_id": None}
    updated = editor.update(item, {"status": "completed"})["body"]["data"]["item"]
    assert updated["status"] == "completed"
    assert updated["schedule"]["actual_end"] is None
    published = editor.publish(updated)["body"]["data"]["item"]
    assert published["schedule"]["actual_end"] is None
    public = public_get(service, item["id"])["body"]["data"]["item"]
    assert public["budget"]["amount_kzt"] is None and public["schedule"]["actual_end"] is None
    # null без даты не превращается в «сегодня»
    assert public["schedule"]["planned_start"] == "2026-10-14"


def test_zero_cost_is_kept_distinct_from_unknown(editor, service):
    source = {"id": "src-1", "url": "https://example.org/notice", "publisher": "Пример",
              "published_on": "2026-09-01", "retrieved_at": "2026-10-06T08:00:00Z",
              "access_status": "fetched", "license": None, "fields": ["budget.amount_kzt"]}
    item = editor.create(evidence_type="observed", source_refs=[source],
                         budget={"amount_kzt": 0, "basis": "contract", "source_id": "src-1"})
    assert item["budget"]["amount_kzt"] == 0


def test_geometry_null_forces_unknown_precision_and_is_listable(editor, service):
    item = editor.create(geometry=None, geometry_precision="source")
    assert item["geometry"] is None and item["geometry_precision"] == "unknown"
    editor.publish(item)
    listing = call(service, "GET", "/objects")["body"]["data"]["items"]
    assert [entry["id"] for entry in listing] == [item["id"]]
    assert listing[0]["geometry"] is None


def test_valid_geometries_round_trip(editor, service):
    line = {"type": "LineString", "coordinates": [[71.40, 51.10], [71.41, 51.11]]}
    polygon = {"type": "Polygon", "coordinates": [[[71.4, 51.1], [71.5, 51.1], [71.5, 51.2], [71.4, 51.1]]]}
    for geometry in (line, polygon):
        item = editor.create(geometry=geometry, geometry_precision="approximate")
        assert item["geometry"] == geometry


def public_texts(service, object_id):
    """Все публичные ответы об объекте одним текстом (detail+history+list)."""
    parts = [public_get(service, object_id), call(service, "GET", "/objects")]
    return json.dumps([part["body"] for part in parts], ensure_ascii=False)


def test_internal_notes_and_staff_meta_never_reach_public_projection(editor, service):
    item = editor.create(internal_notes=SENTINEL_NOTE)
    assert item["internal_notes"] == SENTINEL_NOTE
    item = editor.update(item, {"internal_notes": SENTINEL_NOTE + " v2"},
                         reason=SENTINEL_NOTE)["body"]["data"]["item"]
    editor.publish(item)
    text = public_texts(service, item["id"])
    for forbidden in (SENTINEL_NOTE, "internal_notes", "editor1", "password", "staff",
                      "csrf", "civic_session", "import_", "diff", "snapshot"):
        assert forbidden not in text, forbidden
    detail = public_get(service, item["id"])["body"]["data"]
    assert set(detail["item"]) == {
        "schema_version", "id", "city", "kind", "title", "description", "status", "publication",
        "geometry", "geometry_precision", "schedule", "budget", "responsible", "evidence_type",
        "source_refs", "evidence_notes", "updated_at", "revision"}
    for entry in detail["history"]:
        assert set(entry) == {"id", "object_id", "revision", "at", "changed_fields", "reason",
                              "public_actor_label"}
        assert entry["public_actor_label"] == "Редакция платформы"


def test_errors_do_not_echo_secrets_or_tracebacks(editor, service):
    result = editor.post("/staff/objects", sample_object(title="<b>" + SENTINEL_NOTE))
    text = json.dumps(result["body"], ensure_ascii=False)
    assert SENTINEL_NOTE not in text and "Traceback" not in text
    login = call(service, "POST", "/session/login", {"username": "editor1", "password": "wrong-" + SENTINEL_NOTE})
    assert SENTINEL_NOTE not in json.dumps(login, ensure_ascii=False)


def test_data_and_history_survive_restart(editor, service, db_path, clock):
    source = {"id": "src-a", "url": "https://example.org/a", "publisher": "Издатель",
              "published_on": "2026-09-30", "retrieved_at": "2026-10-06",
              "access_status": "fetched", "license": "CC BY 4.0",
              "fields": ["schedule.planned_start", "title"]}
    item = editor.create(evidence_type="derived", source_refs=[source],
                         evidence_notes="Даты взяты из объявления, место приблизительно.")
    item = editor.publish(item, reason="Первая публикация")["body"]["data"]["item"]
    item = editor.update(item, {"schedule": {"current_planned_end": "2026-10-25"}},
                         reason="Перенос: погодные условия")["body"]["data"]["item"]
    editor.publish(item, reason="Перенос срока: погодные условия")
    before = public_get(service, item["id"])["body"]["data"]

    restarted = CivicService(db_path, clock=clock)
    after = public_get(restarted, item["id"])["body"]["data"]
    assert after == before
    assert after["item"]["source_refs"] == [source]  # исходный источник сохранён дословно
    assert after["item"]["evidence_type"] == "derived"
    assert after["item"]["schedule"]["original_planned_end"] == "2026-10-20"
    assert after["item"]["schedule"]["current_planned_end"] == "2026-10-25"
    assert [h["reason"] for h in after["history"]] == ["Первая публикация", "Перенос срока: погодные условия"]
    # Сессия тоже переживает перезапуск сервера.
    again = call(restarted, "GET", "/session", ctx=editor.ctx())
    assert again["body"]["data"]["authenticated"] is True


def test_public_list_filters_and_cursor_pagination(editor, service, clock):
    created = []
    plans = [("roadworks", "planned", "2026-10-01", "2026-10-10"),
             ("roadworks", "in_progress", "2026-09-01", None),
             ("event", "planned", None, "2026-12-01"),
             ("landscaping", "unknown", None, None),
             ("construction", "completed", "2025-01-01", "2025-06-01")]
    for kind, status, start, end in plans:
        clock.advance(seconds=10)
        item = editor.create(kind=kind, status=status, title=f"{kind} {status}",
                             schedule={"planned_start": start, "original_planned_end": None,
                                       "current_planned_end": end, "actual_end": None})
        created.append(editor.publish(item)["body"]["data"]["item"])

    def ids(query):
        result = call(service, "GET", "/objects", query=query)
        assert result["status"] == 200, result
        return [item["title"] for item in result["body"]["data"]["items"]], result["body"]["data"]

    titles, _ = ids("")
    assert len(titles) == 5 and titles[0] == "construction completed"  # новые сверху
    titles, _ = ids("kind=roadworks")
    assert set(titles) == {"roadworks planned", "roadworks in_progress"}
    titles, _ = ids("kind=event,landscaping&status=planned")
    assert titles == ["event planned"]
    titles, data = ids("from=2026-10-05&to=2026-10-31")
    assert set(titles) == {"roadworks planned", "roadworks in_progress", "event planned"}
    by_title = {item["title"]: item["id"] for item in created}
    assert set(data["date_filter"]["incomplete_interval_ids"]) == {
        by_title["roadworks in_progress"], by_title["event planned"]}
    titles, _ = ids("to=2025-12-31")
    # Объект без дат исключён; у «event planned» известен только конец — он включён как неполный.
    assert set(titles) == {"construction completed", "event planned"}

    seen, cursor = [], None
    while True:
        query = "limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = call(service, "GET", "/objects", query=query)["body"]["data"]
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 5 and len(set(seen)) == 5


@pytest.mark.parametrize("query", ["kind=parade", "status=done", "from=2026-13-01", "from=2026-10-10&to=2026-10-01", "limit=%C2%B2", "limit=%D9%A1",
                                   "cursor=abc", "limit=0", "limit=1000", "limit=-1", "from=a&from=b"])
def test_bad_filters_are_400(service, query):
    result = call(service, "GET", "/objects", query=query)
    assert result["status"] == 400 and result["body"]["error"]["code"] == "bad_request"


def test_date_filter_bounds_are_inclusive(editor, service):
    item = editor.create(schedule={"planned_start": "2026-10-14", "original_planned_end": None,
                                   "current_planned_end": "2026-10-20", "actual_end": None})
    editor.publish(item)
    for query, expected in (("from=2026-10-20", 1), ("to=2026-10-14", 1), ("from=2026-10-21", 0),
                            ("to=2026-10-13", 0)):
        items = call(service, "GET", "/objects", query=query)["body"]["data"]["items"]
        assert len(items) == expected, query


def test_unknown_civic_paths_are_not_claimed_and_methods_are_checked(service):
    for path in ("/api/civic/v1/feedback", "/api/civic/v1/objects/x/feedback", "/api/civic/v1/staff/feedback",
                 "/api/civic/v1/nope"):
        assert service.handle("GET", path, "", None, context()) is None
    assert service.handle("GET", "/api/bootstrap", "", None, context()) is None
    assert service.handle("GET", "/api/civic/v1x/objects", "", None, context()) is None
    result = service.handle("DELETE", "/api/civic/v1/staff/objects/ast-1", "", None, context())
    assert result["status"] == 405 and "POST" not in result["headers"]["Allow"]
    result = service.handle("POST", "/api/civic/v1/objects", "", b"{}", context())
    assert result["status"] == 405 and result["headers"]["Allow"] == "GET, HEAD"


@pytest.mark.parametrize("field,value", [
    ("budget", {"amount_kzt": 10 ** 400, "basis": "planned", "source_id": None}),
    ("geometry", {"type": "Point", "coordinates": [10 ** 400, 51.1]}),
    ("geometry", {"type": "Point", "coordinates": [71.4, -(10 ** 400)]}),
])
def test_huge_integers_are_422_not_500(editor, service, field, value):
    raw = json.dumps(sample_object(**{field: value})).encode()
    result = call(service, "POST", "/staff/objects", raw, ctx=editor.ctx())
    assert result["status"] == 422, result


def test_trailing_newline_ids_are_rejected(editor, service):
    assert call(service, "GET", "/objects/road-1%0A")["status"] == 400
    from ui.civic_store.validate import is_valid_id
    assert not is_valid_id("road-1\n") and is_valid_id("road-1")


INVISIBLE_TITLES = ["​", "‎", "﻿", "\U000e0041", "́", "ㅤ", "­", "⁠",
                    "​​", "a b"]


@pytest.mark.parametrize("title", INVISIBLE_TITLES, ids=[hex(ord(t[0])) for t in INVISIBLE_TITLES])
def test_invisible_or_format_only_titles_are_rejected(editor, title):
    result = editor.post("/staff/objects", sample_object(title=title))
    assert result["status"] == 422 and "title" in result["body"]["error"]["fields"]


@pytest.mark.parametrize("url", ["https://‮astana.gov.kz/", "https://astana.gov.kz/‮txt.exe",
                                 "https://astana.gov.kz/​", "https://astana​.gov.kz/",
                                 "https://⁦evil.kz⁩/", "https://astana.gov.kz/\ud800"])
def test_spoofing_or_unencodable_urls_are_rejected(editor, service, url):
    source = {"id": "s1", "url": url, "access_status": "not_fetched"}
    raw = json.dumps(sample_object(source_refs=[source])).encode()  # \ud800 как JSON-escape
    result = call(service, "POST", "/staff/objects", raw, ctx=editor.ctx())
    assert result["status"] in (400, 422), result
    assert editor.get("/staff/objects")["body"]["data"]["items"] == []


def test_cyrillic_url_path_is_still_allowed(editor):
    source = {"id": "s1", "url": "https://astana.gov.kz/ru/новости/1", "access_status": "not_fetched"}
    assert editor.post("/staff/objects", sample_object(source_refs=[source]))["status"] == 201


@pytest.mark.parametrize("ref_id", [["s1"], {"a": 1}])
def test_unhashable_source_ref_id_is_422_not_500(editor, ref_id):
    source = {"id": ref_id, "url": "https://example.org/", "access_status": "not_fetched"}
    result = editor.post("/staff/objects", sample_object(source_refs=[source]))
    assert result["status"] == 422 and "source_refs[0].id" in result["body"]["error"]["fields"]


def test_surrogate_keys_are_rejected_before_any_write(editor, service):
    item = editor.create()
    for raw in (b'{"expected_revision": 1, "changes": {"title": "x"}, "reason": "r", "\\udfff": 1}',
                b'{"expected_revision": 1, "changes": {"title": "x", "schedule": {"\\ud800": 1}}, "reason": "r"}'):
        result = call(service, "POST", f"/staff/objects/{item['id']}/update", raw, ctx=editor.ctx())
        assert result["status"] == 400, result
        json.dumps(result["body"], ensure_ascii=False).encode("utf-8")  # ответ кодируется
    assert editor.get(f"/staff/objects/{item['id']}")["body"]["data"]["item"]["revision"] == 1
    # Длинные/странные имена полей не возвращаются клиенту как есть.
    result = editor.post("/staff/objects", {**sample_object(), "<script>" * 20: 1, "x" * 5000: 2})
    assert result["status"] == 422
    assert set(result["body"]["error"]["fields"]) == {"<недопустимое имя поля>"}


def test_negative_zero_amount_is_normalised(editor, service):
    source = {"id": "s1", "url": "https://example.org/", "access_status": "not_fetched"}
    raw = json.dumps(sample_object(evidence_type="observed", source_refs=[source])).replace(
        '"amount_kzt": null', '"amount_kzt": -0.0').replace('"basis": "unknown"', '"basis": "contract"').replace(
        '"source_id": null', '"source_id": "s1"').encode()
    result = call(service, "POST", "/staff/objects", raw, ctx=editor.ctx())
    assert result["status"] == 201, result
    amount = result["body"]["data"]["item"]["budget"]["amount_kzt"]
    assert amount == 0 and json.dumps(amount) == "0"


@pytest.mark.parametrize("field", ["kind.zzz", "title.x.y", "schedule.nonexistent", "budget.amount_kzt.extra",
                                   "source_refs.id", "internal_notes", "password_hash"])
def test_source_fields_must_be_real_civic_paths(editor, field):
    source = {"id": "s1", "url": "https://example.org/", "access_status": "not_fetched", "fields": [field]}
    result = editor.post("/staff/objects", sample_object(source_refs=[source]))
    assert result["status"] == 422 and "source_refs[0].fields[0]" in result["body"]["error"]["fields"]
