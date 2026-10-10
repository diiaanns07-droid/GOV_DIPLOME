"""R02 раунд 12: частичное обновление, 409, перенос срока из источника и сохранность истории."""

import threading

from ui.civic_store.importer import import_package
from r02_helpers import call
from test_r02_import_cli import package, real_item


def schedule(end, original=None):
    return {"planned_start": "2026-10-14", "original_planned_end": original,
            "current_planned_end": end, "actual_end": None}


def published_import(service, editor, object_id="ast-r12-h"):
    import_package(service.objects, package([real_item(object_id)]))
    item = editor.get(f"/staff/objects/{object_id}")["body"]["data"]["item"]
    return editor.publish(item, reason="Первая публикация")["body"]["data"]["item"]


def test_source_deadline_move_can_be_applied_after_publication(service, editor):
    """Регрессия: источник не знает первоначальный срок (null) — раньше apply давал 422 навсегда."""
    item = published_import(service, editor)
    assert item["schedule"]["original_planned_end"] == "2026-10-20"
    import_package(service.objects, package([real_item("ast-r12-h", schedule=schedule("2026-11-30"))],
                                            version="v2"))
    candidates = editor.get("/staff/objects/ast-r12-h/import-candidates")["body"]["data"]["items"]
    assert candidates[0]["original_planned_end_locked"] is True
    assert set(candidates[0]["diff"]) == {"schedule.current_planned_end"}
    result = editor.post(f"/staff/objects/ast-r12-h/import-candidates/{candidates[0]['id']}/apply",
                         {"expected_revision": item["revision"], "reason": "Источник перенёс срок"})
    assert result["status"] == 200, result["body"]
    staff = result["body"]["data"]["item"]
    assert staff["schedule"] == schedule("2026-11-30", original="2026-10-20")
    assert staff["staff"]["has_unpublished_changes"] is True
    # Публично — прежний срок, пока редактор не опубликует перенос.
    public = call(service, "GET", "/objects/ast-r12-h")["body"]["data"]["item"]
    assert public["schedule"]["current_planned_end"] == "2026-10-20"
    staff = editor.publish(staff, reason="Срок перенесён по данным источника")["body"]["data"]["item"]
    public = call(service, "GET", "/objects/ast-r12-h")["body"]["data"]
    assert public["item"]["schedule"]["original_planned_end"] == "2026-10-20"
    assert public["item"]["schedule"]["current_planned_end"] == "2026-11-30"
    assert public["history"][-1]["reason"] == "Срок перенесён по данным источника"
    assert "schedule.current_planned_end" in public["history"][-1]["changed_fields"]
    # Служебная история хранит автора и причину каждой правки.
    history = service.objects.get_staff("ast-r12-h")["history"]
    assert [(h["action"], h["actor_kind"]) for h in history] == [
        ("import_create", "import"), ("publish", "editor"), ("update", "editor"), ("publish", "editor")]
    assert history[2]["reason"] == "Источник перенёс срок" and history[2]["actor_label"] == "editor1"
    # Тот же пакет повторно — источник не менялся, новых кандидатов нет.
    again = import_package(service.objects, package([real_item("ast-r12-h", schedule=schedule("2026-11-30"))],
                                                    version="v2"))
    assert again["items"][0]["action"] == "skip_unchanged"


def test_editor_matching_source_on_published_object_supersedes_candidate(service, editor):
    item = published_import(service, editor)
    item = editor.update(item, {"schedule": {"current_planned_end": "2026-11-30"}},
                         reason="Звонок подрядчика")["body"]["data"]["item"]
    report = import_package(service.objects, package([real_item("ast-r12-h", schedule=schedule("2026-11-30"))],
                                                     version="v2"))
    assert report["items"][0]["action"] == "skip_unchanged"
    assert service.objects.get_staff("ast-r12-h")["item"]["staff"]["pending_import_candidates"] == 0


def test_partial_update_keeps_other_fields_and_stale_revision_is_409(service, editor, editor2):
    item = editor.create()
    first = editor.update(item, {"schedule": {"current_planned_end": "2026-10-25"}})
    assert first["status"] == 200
    updated = first["body"]["data"]["item"]
    assert updated["title"] == item["title"] and updated["schedule"]["planned_start"] == item["schedule"]["planned_start"]
    stale = editor2.update(item, {"title": "Чужая правка по старой карточке"})
    assert stale["status"] == 409
    assert stale["body"]["error"]["code"] == "stale_revision"
    assert stale["body"]["error"]["current_revision"] == updated["revision"]
    assert service.objects.get_staff(item["id"])["item"]["title"] == item["title"]


def test_import_and_editor_racing_on_same_draft_never_lose_history(service, editor):
    import_package(service.objects, package([real_item("ast-r12-r")]))
    item = editor.get("/staff/objects/ast-r12-r")["body"]["data"]["item"]
    results = {}

    def run_import():
        results["import"] = import_package(service.objects, package(
            [real_item("ast-r12-r", title="Название из нового пакета")], version="v2"))

    def run_edit():
        results["edit"] = editor.update(item, {"description": "Правка редактора"})

    threads = [threading.Thread(target=run_import), threading.Thread(target=run_edit)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    history = service.objects.get_staff("ast-r12-r")["history"]
    assert [h["revision"] for h in history] == list(range(1, len(history) + 1))
    staff = service.objects.get_staff("ast-r12-r")["item"]
    if results["edit"]["status"] == 200:
        # Правка прошла (первой или после импорта) — она сохранена.
        assert staff["description"] == "Правка редактора"
    else:
        assert results["edit"]["status"] == 409
    action = results["import"]["items"][0]["action"]
    if action == "update_import_draft":
        assert staff["title"] == "Название из нового пакета"
    else:
        # Редактор успел первым: новая версия ждёт решения и не затирает правку.
        assert action == "editor_review" and staff["staff"]["pending_import_candidates"] == 1
