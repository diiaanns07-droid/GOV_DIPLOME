"""R02: обновление, публикация, архив, история и оптимистичная блокировка."""

import json
import threading

import pytest

from ui.civic_store import objects as objects_module
from r02_helpers import call, context, sample_object


def item_of(result):
    assert result["body"]["ok"] is True, result
    return result["body"]["data"]["item"]


def public(service, object_id):
    return call(service, "GET", f"/objects/{object_id}")


def test_two_editors_with_same_revision_one_wins_other_gets_409(editor, editor2, service):
    item = editor.create()
    item = item_of(editor.update(item, {"title": "Ревизия 2"}))
    assert item["revision"] == 2
    first = editor.update(item, {"title": "Правка первого"})
    second = editor2.update(item, {"title": "Правка второго"})
    assert first["status"] == 200 and second["status"] == 409
    assert second["body"]["error"]["code"] == "stale_revision"
    assert second["body"]["error"]["current_revision"] == 3
    final = item_of(editor.get(f"/staff/objects/{item['id']}"))
    assert final["title"] == "Правка первого" and final["revision"] == 3
    history = editor.get(f"/staff/objects/{item['id']}")["body"]["data"]["history"]
    assert [h["revision"] for h in history] == [1, 2, 3]  # проигравшая правка не оставила следа


def test_concurrent_threads_same_revision_exactly_one_succeeds(editor, editor2, service):
    for attempt in range(5):
        item = editor.create(title=f"Гонка {attempt}")
        barrier = threading.Barrier(2)
        results = {}

        def worker(name, who):
            barrier.wait()
            results[name] = who.update(item, {"title": f"Правка {name}"})["status"]

        threads = [threading.Thread(target=worker, args=(name, who))
                   for name, who in (("a", editor), ("b", editor2))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(results.values()) == [200, 409]
    assert service.db.open_connections == 0


@pytest.mark.parametrize("bad", [None, "2", 0, -1, True, 1.5])
def test_expected_revision_must_be_positive_integer(editor, bad):
    item = editor.create()
    result = editor.post(f"/staff/objects/{item['id']}/update",
                         {"expected_revision": bad, "changes": {"title": "x"}, "reason": "r"})
    assert result["status"] == 422
    assert "expected_revision" in result["body"]["error"]["fields"]


def test_publish_flow_original_end_is_fixed_and_schedule_change_needs_reason(editor, service):
    item = editor.create()
    assert item["schedule"]["original_planned_end"] is None
    # Пока черновик не публиковался, причина необязательна и исходный срок можно менять.
    item = item_of(editor.update(item, {"schedule": {"current_planned_end": "2026-10-21"}}, reason=None))
    assert editor.publish(item, reason="")["status"] == 422  # публикация требует причину
    item = item_of(editor.publish(item, reason="Первая публикация"))
    assert item["publication"] == "published"
    assert item["schedule"]["original_planned_end"] == "2026-10-21"  # первый публичный срок
    assert item["staff"]["original_planned_end_locked"] is True

    no_reason = editor.update(item, {"schedule": {"current_planned_end": "2026-10-28"}}, reason="  ")
    assert no_reason["status"] == 422 and "reason" in no_reason["body"]["error"]["fields"]
    overwrite = editor.update(item, {"schedule": {"original_planned_end": "2026-10-28"}},
                              reason="Попытка переписать исходный срок")
    assert overwrite["status"] == 422
    assert "schedule.original_planned_end" in overwrite["body"]["error"]["fields"]

    item = item_of(editor.update(item, {"schedule": {"current_planned_end": "2026-10-28"}},
                                 reason="Служебно: подрядчик сообщил о задержке"))
    assert item["staff"]["has_unpublished_changes"] is True
    # Неопубликованная правка не видна жителю.
    seen = public(service, item["id"])["body"]["data"]["item"]
    assert seen["schedule"]["current_planned_end"] == "2026-10-21"

    item = item_of(editor.publish(item, reason="Срок перенесён из-за задержки поставки"))
    data = public(service, item["id"])["body"]["data"]
    assert data["item"]["schedule"] == {"planned_start": "2026-10-14", "original_planned_end": "2026-10-21",
                                        "current_planned_end": "2026-10-28", "actual_end": None}
    assert data["item"]["revision"] == item["revision"]
    history = data["history"]
    assert [h["reason"] for h in history] == ["Первая публикация", "Срок перенесён из-за задержки поставки"]
    assert history[0]["changed_fields"] == ["publication", "schedule.original_planned_end"]
    assert history[1]["changed_fields"] == ["schedule.current_planned_end"]
    # Служебная причина правки остаётся только в редакторской истории.
    assert "Служебно" not in str(data)
    staff_history = editor.get(f"/staff/objects/{item['id']}")["body"]["data"]["history"]
    assert [h["action"] for h in staff_history] == ["create", "update", "publish", "update", "publish"]
    assert staff_history[3]["diff"]["schedule.current_planned_end"] == {"before": "2026-10-21",
                                                                        "after": "2026-10-28"}


def test_explicit_original_end_before_first_publication_is_kept(editor, service):
    item = editor.create(schedule={"planned_start": "2026-10-14", "original_planned_end": "2026-10-20",
                                   "current_planned_end": "2026-10-22", "actual_end": None})
    item = item_of(editor.publish(item))
    assert item["schedule"]["original_planned_end"] == "2026-10-20"
    assert public(service, item["id"])["body"]["data"]["history"][0]["changed_fields"] == ["publication"]


def test_publish_without_changes_is_a_noop(editor, service):
    item = item_of(editor.publish(editor.create()))
    again = item_of(editor.publish(item, reason="Повторное нажатие"))
    assert again["revision"] == item["revision"]
    assert len(public(service, item["id"])["body"]["data"]["history"]) == 1


def test_internal_only_update_does_not_create_public_changes(editor, service):
    item = item_of(editor.publish(editor.create()))
    item = item_of(editor.update(item, {"internal_notes": "звонок подрядчику"}, reason="заметка"))
    assert item["staff"]["has_unpublished_changes"] is False
    assert item_of(editor.publish(item))["revision"] == item["revision"]


def test_noop_update_keeps_revision(editor):
    item = editor.create()
    same = item_of(editor.update(item, {"title": item["title"]}))
    assert same["revision"] == item["revision"]


def test_archive_hides_publicly_but_keeps_history_and_can_be_restored(editor, service):
    item = item_of(editor.publish(editor.create()))
    assert editor.archive(item, reason="")["status"] == 422
    item = item_of(editor.archive(item, reason="Работы отменены заказчиком"))
    assert item["publication"] == "archived"
    assert public(service, item["id"])["status"] == 404
    assert call(service, "GET", "/objects")["body"]["data"]["items"] == []
    staff = editor.get(f"/staff/objects/{item['id']}")["body"]["data"]
    assert [h["action"] for h in staff["history"]] == ["create", "publish", "archive"]
    item = item_of(editor.publish(item, reason="Работы возобновлены"))
    data = public(service, item["id"])["body"]["data"]
    assert [h["changed_fields"] for h in data["history"]] == [
        ["publication", "schedule.original_planned_end"], ["publication"], ["publication"]]
    archived_draft = item_of(editor.archive(editor.create(), reason="Дубликат черновика"))
    assert archived_draft["publication"] == "archived"


def test_observed_without_sources_cannot_be_published(editor):
    item = editor.create(evidence_type="observed", source_refs=[])
    result = editor.publish(item)
    assert result["status"] == 422 and "source_refs" in result["body"]["error"]["fields"]


def test_failed_publish_rolls_back_completely(editor, service, monkeypatch):
    item = item_of(editor.publish(editor.create()))
    item = item_of(editor.update(item, {"title": "Новое название"}, reason="уточнение"))
    before_staff = editor.get(f"/staff/objects/{item['id']}")["body"]["data"]
    before_public = public(service, item["id"])["body"]["data"]

    original = objects_module.ObjectRepository._history

    def failing_history(*args, **kwargs):
        if kwargs.get("action") == "publish":
            raise RuntimeError("disk full (simulated)")
        return original(*args, **kwargs)

    monkeypatch.setattr(objects_module.ObjectRepository, "_history", staticmethod(failing_history))
    result = editor.publish(item, reason="Должна откатиться")
    assert result["status"] == 500 and result["body"]["error"]["code"] == "internal_error"
    assert "disk full" not in str(result["body"])
    monkeypatch.undo()
    assert editor.get(f"/staff/objects/{item['id']}")["body"]["data"] == before_staff
    assert public(service, item["id"])["body"]["data"] == before_public
    assert service.db.open_connections == 0


def test_idempotency_key_prevents_duplicate_drafts(editor, service):
    headers = {"Idempotency-Key": "form-7f3a9c21"}
    first = call(service, "POST", "/api/civic/v1/staff/objects"[len("/api/civic/v1"):], sample_object(),
                 ctx=editor.ctx(headers=headers))
    second = call(service, "POST", "/staff/objects", sample_object(), ctx=editor.ctx(headers=headers))
    assert first["status"] == 201 and second["status"] == 200
    assert first["body"]["data"]["item"]["id"] == second["body"]["data"]["item"]["id"]
    assert len(editor.get("/staff/objects")["body"]["data"]["items"]) == 1
    bad = call(service, "POST", "/staff/objects", sample_object(), ctx=editor.ctx(headers={"Idempotency-Key": "x"}))
    assert bad["status"] == 400


def test_staff_list_filters_by_publication(editor, service):
    draft = editor.create(title="Черновик")
    published = item_of(editor.publish(editor.create(title="Опубликовано")))
    items = editor.get("/staff/objects", query="publication=draft")["body"]["data"]["items"]
    assert [entry["id"] for entry in items] == [draft["id"]]
    items = editor.get("/staff/objects", query="publication=published")["body"]["data"]["items"]
    assert [entry["id"] for entry in items] == [published["id"]]
    assert items[0]["staff"]["public_item"]["revision"] == published["revision"]


def test_lookup_public_object_returns_only_published(editor, service):
    draft = editor.create()
    assert service.lookup_public_object(draft["id"]) is None
    assert service.lookup_public_object("") is None and service.lookup_public_object("../x") is None
    published = item_of(editor.publish(draft))
    found = service.lookup_public_object(draft["id"])
    assert found["revision"] == published["revision"] and "internal_notes" not in found
    item_of(editor.archive(published, reason="снято"))
    assert service.lookup_public_object(draft["id"]) is None


def test_staff_audit_export_is_paginated_and_editor_only(editor, service):
    for index in range(3):
        item = editor.create(title=f"Аудит {index}", internal_notes="заметка")
        editor.publish(item)
    assert call(service, "GET", "/staff/audit")["status"] == 401
    page = editor.get("/staff/audit", query="limit=4")["body"]["data"]
    assert [entry["action"] for entry in page["entries"]] == ["create", "publish", "create", "publish"]
    assert page["next_after"] == str(page["entries"][-1]["id"])
    rest = editor.get("/staff/audit", query=f"after={page['next_after']}&limit=500")["body"]["data"]
    assert len(rest["entries"]) == 2 and rest["next_after"] is None
    only = editor.get("/staff/audit", query=f"object_id={item['id']}")["body"]["data"]["entries"]
    assert {entry["object_id"] for entry in only} == {item["id"]}
    for key in ("snapshot", "password_hash", "csrf"):
        assert key not in str(page)
    for bad in ("limit=0", "limit=501", "after=-1", "after=%C2%B2", "limit=%C2%B2", "since=yesterday", "object_id=..%2F"):
        assert editor.get("/staff/audit", query=bad)["status"] == 400, bad


def test_publish_revalidates_stored_content(editor, service):
    """Запись, ставшая невалидной в базе (старый код/ручная правка), не публикуется."""
    item = editor.create()
    with service.db.write() as conn:
        row = conn.execute("SELECT data_json FROM civic_objects WHERE id = ?", (item["id"],)).fetchone()
        data = json.loads(row["data_json"])
        data["geometry"] = {"type": "Point", "coordinates": [51.17, 71.43]}  # перепутаны lon/lat
        conn.execute("UPDATE civic_objects SET data_json = ? WHERE id = ?", (json.dumps(data), item["id"]))
    result = editor.publish(item)
    assert result["status"] == 422 and "geometry.coordinates" in result["body"]["error"]["fields"]
    assert public(service, item["id"])["status"] == 404
