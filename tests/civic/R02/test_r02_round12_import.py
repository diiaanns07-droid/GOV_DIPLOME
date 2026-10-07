"""R02 раунд 12: пакет реальных объектов — dry-run, черновики, повтор без дублей, изменение источника.

Записи ниже — тестовые (example.org), не реальные городские работы.
"""

import copy

import pytest

from ui.civic_store.importer import ImportRejected, import_package
from r02_helpers import call
from test_r02_import_cli import package, real_item


def counts(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def snapshot_tables(service):
    with service.db.read() as conn:
        return {table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
                for table in ("civic_objects", "civic_history", "civic_public_objects",
                              "civic_imports", "civic_import_candidates")}


def by_id(report):
    return {item["external_id"]: item for item in report["items"]}


def test_acceptance_dry_run_import_reimport(service):
    pkg = package([real_item("ast-r12-a"), real_item("ast-r12-b", title="Вторая тестовая запись")])
    before = snapshot_tables(service)
    dry = import_package(service.objects, pkg, dry_run=True)
    assert dry["status"] == "dry_run" and dry["counts"]["create"] == 2
    assert snapshot_tables(service) == before  # dry-run ничего не записал
    # Серверные поля пакета названы в отчёте как проигнорированные.
    assert by_id(dry)["ast-r12-a"]["ignored_fields"] == ["publication", "revision", "updated_at"]

    applied = import_package(service.objects, copy.deepcopy(pkg))
    assert applied["counts"]["create"] == 2
    again = import_package(service.objects, copy.deepcopy(pkg))
    assert again["counts"] == {"skip_unchanged": 2, "report_missing": 0}
    with service.db.read() as conn:
        assert counts(conn, "civic_objects") == 2
        assert counts(conn, "civic_public_objects") == 0
        assert counts(conn, "civic_history") == 2
    assert call(service, "GET", "/objects")["body"]["data"]["items"] == []


def test_dry_run_with_invalid_record_shows_exact_errors_and_valid_plan(service):
    import_package(service.objects, package([real_item("ast-r12-a")]))
    before = snapshot_tables(service)
    bad = real_item("ast-r12-bad", schedule={"planned_start": "2026-13-01", "current_planned_end": None,
                                             "original_planned_end": None, "actual_end": None},
                    budget={"amount_kzt": -5, "basis": "planned", "source_id": "src-1"})
    changed = real_item("ast-r12-a", title="Название изменилось в источнике")
    with pytest.raises(ImportRejected) as rejected:
        import_package(service.objects, package([changed, bad, "мусор"], version="v2"), dry_run=True)
    report = rejected.value.report
    assert report["status"] == "rejected" and report["dry_run"] is True
    entries = {item["index"]: item for item in report["items"]}
    assert entries[0]["action"] == "update_import_draft"          # допустимая запись показана
    assert entries[0]["changed_fields"] == ["title"]
    assert entries[1]["action"] == "invalid"
    assert set(entries[1]["fields"]) == {"schedule.planned_start", "budget.amount_kzt"}
    assert entries[2] == {"index": 2, "external_id": None, "action": "invalid",
                          "fields": {"item": "Объект civic-v1."}}
    assert report["counts"]["invalid"] == 2 and report["counts"]["valid"] == 1
    assert snapshot_tables(service) == before  # некорректная запись базу не повредила
    # Без dry-run — прежний контракт: отказ целиком, ничего не применено.
    with pytest.raises(ImportRejected):
        import_package(service.objects, package([changed, bad], version="v2"))
    assert snapshot_tables(service) == before


def test_source_change_is_detected_against_last_import(service, editor):
    import_package(service.objects, package([real_item("ast-r12-a"), real_item("ast-r12-b")]))
    item = editor.get("/staff/objects/ast-r12-b")["body"]["data"]["item"]
    item = editor.update(item, {"description": "Уточнено редактором"})["body"]["data"]["item"]
    editor.publish(item, reason="Проверено по источнику")

    refs = copy.deepcopy(real_item()["source_refs"])
    refs[0]["published_on"] = "2026-10-06"
    refs.append({"id": "src-2", "url": "https://example.org/n/2", "publisher": "Тест",
                 "published_on": "2026-10-06", "retrieved_at": "2026-10-07T10:00:00+05:00",
                 "access_status": "fetched", "license": None, "fields": ["schedule.current_planned_end"]})
    sched = {"planned_start": "2026-10-01", "original_planned_end": None,
             "current_planned_end": "2026-11-15", "actual_end": None}
    v2 = package([real_item("ast-r12-a", source_refs=refs, schedule=sched),
                  real_item("ast-r12-b", source_refs=refs, schedule=sched)], version="v2")
    report = by_id(import_package(service.objects, v2))
    a, b = report["ast-r12-a"], report["ast-r12-b"]
    assert a["action"] == "update_import_draft"
    assert b["action"] == "editor_review"
    for entry in (a, b):
        assert "schedule.current_planned_end" in entry["source_changed_fields"]
        assert entry["source_refs_change"] == {"added": ["src-2"], "removed": [],
                                               "changed": {"src-1": ["published_on"]}}
    # Для b: источник не трогал description, но карточка отличается правкой редактора.
    assert "description" in b["changed_fields"] and "description" not in b["source_changed_fields"]
    # Опубликованная карточка и её история не переписаны импортом.
    public = call(service, "GET", "/objects/ast-r12-b")["body"]["data"]
    assert public["item"]["description"] == "Уточнено редактором"
    assert public["item"]["schedule"]["current_planned_end"] == "2026-10-20"
    assert [h["revision"] for h in public["history"]] == [3]


def test_history_cannot_be_rewritten_by_reimport_of_old_version(service, editor):
    v1 = package([real_item("ast-r12-a")])
    import_package(service.objects, v1)
    item = editor.get("/staff/objects/ast-r12-a")["body"]["data"]["item"]
    item = editor.publish(item, reason="Первая публикация")["body"]["data"]["item"]
    item = editor.update(item, {"schedule": {"current_planned_end": "2026-12-01"}},
                         reason="Подрядчик сообщил о переносе")["body"]["data"]["item"]
    item = editor.publish(item, reason="Срок перенесён: подрядчик сообщил о переносе")["body"]["data"]["item"]
    history_before = service.objects.get_staff("ast-r12-a")["history"]
    # Тот же пакет — источник не менялся; пакет со старым сроком — только кандидат редактору.
    assert by_id(import_package(service.objects, copy.deepcopy(v1)))["ast-r12-a"]["action"] == "skip_unchanged"
    stale = package([real_item("ast-r12-a", title="Ремонт (старое название)")], version="v0-stale")
    report = import_package(service.objects, stale)
    assert by_id(report)["ast-r12-a"]["action"] == "editor_review"
    assert "schedule.current_planned_end" in by_id(report)["ast-r12-a"]["changed_fields"]
    staff = service.objects.get_staff("ast-r12-a")
    assert staff["history"] == history_before
    assert staff["item"]["schedule"]["original_planned_end"] == "2026-10-20"
    assert staff["item"]["schedule"]["current_planned_end"] == "2026-12-01"
    public = call(service, "GET", "/objects/ast-r12-a")["body"]["data"]
    assert [(h["revision"], h["reason"]) for h in public["history"]] == [
        (2, "Первая публикация"), (4, "Срок перенесён: подрядчик сообщил о переносе")]


def test_possible_duplicate_of_other_origin_is_flagged_not_merged(service, editor):
    manual = editor.create(title="Ремонт (тестовая запись)", evidence_type="observed",
                           source_refs=real_item()["source_refs"])
    report = import_package(service.objects, package([real_item("ast-r12-new")]))
    entry = by_id(report)["ast-r12-new"]
    assert entry["action"] == "create"
    assert entry["possible_duplicates"] == [{"object_id": manual["id"], "import_source": None,
                                             "match": ["kind_title", "source_url"]}]
    # Повторный импорт того же source не считает собственный объект дублем.
    again = by_id(import_package(service.objects, package([real_item("ast-r12-new")])))
    assert again["ast-r12-new"] == {"index": 0, "external_id": "ast-r12-new", "action": "skip_unchanged",
                                    "object_id": "ast-r12-new", "ignored_fields":
                                    ["publication", "revision", "updated_at"]}


def test_package_cannot_relabel_demo_records(service):
    # Демо-набор загружен; реальный пакет с тем же id не превращает его в «наблюдение».
    demo = {"schema_version": "civic-v1", "city": "astana",
            "slice": {"name": "demo", "version": "d1", "demo": True},
            "items": [real_item("ast-demo-1", evidence_type="synthetic", source_refs=[])]}
    import_package(service.objects, demo)
    report = import_package(service.objects, package([real_item("ast-demo-1")]))
    assert by_id(report)["ast-demo-1"]["action"] == "id_conflict"
    assert service.objects.get_staff("ast-demo-1")["item"]["evidence_type"] == "synthetic"


def test_same_work_twice_in_one_package_is_flagged(service):
    report = by_id(import_package(service.objects, package([
        real_item("ast-r12-d1"), real_item("ast-r12-d2"), real_item("ast-r12-d3", title="Другая работа")])))
    assert report["ast-r12-d2"]["possible_duplicates"] == [
        {"object_id": "ast-r12-d1", "import_source": "r05-astana-real", "match": ["kind_title", "source_url"]}]
    assert "possible_duplicates" not in report["ast-r12-d1"]
    assert "possible_duplicates" not in report["ast-r12-d3"]  # общий URL своего source — не дубль


def test_all_field_errors_of_a_record_are_reported_together(service):
    bad = real_item("ast-r12-bad", status="done", extra_field=1,
                    budget={"amount_kzt": 1000, "basis": "unknown", "source_id": None})
    with pytest.raises(ImportRejected) as rejected:
        import_package(service.objects, package([bad]), dry_run=True)
    # Неизвестное поле больше не скрывает ошибки типов; согласованность (сумма без источника)
    # проверяется вторым этапом, когда типы полей уже верны.
    assert set(rejected.value.report["items"][0]["fields"]) == {"extra_field", "status"}
    fixed = real_item("ast-r12-bad", extra_field=1,
                      budget={"amount_kzt": 1000, "basis": "unknown", "source_id": None})
    with pytest.raises(ImportRejected) as rejected:
        import_package(service.objects, package([fixed]), dry_run=True)
    assert set(rejected.value.report["items"][0]["fields"]) == {"extra_field", "budget.source_id",
                                                                "budget.basis"}
