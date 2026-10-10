"""R02 раунд 13: жизненный цикл источника, проверка кандидата по полям, конфликты и приёмка.

Все записи — тестовые (example.org), не реальные городские работы.
"""

import copy
import threading

from ui.civic_store.importer import import_package
from ui.civic_store.service import CivicService
from r02_helpers import Editor, PASSWORD, call
from test_r02_import_cli import package, real_item

OID = "ast-r13-x"


def schedule(end, start="2026-10-14"):
    return {"planned_start": start, "original_planned_end": None, "current_planned_end": end, "actual_end": None}


def refs(*extra, published="2026-10-01"):
    base = [{"id": "src-1", "url": "https://example.org/n/1", "publisher": "Тест", "published_on": published,
             "retrieved_at": "2026-10-05T10:00:00+05:00", "access_status": "fetched", "license": None,
             "fields": ["title", "schedule.planned_start", "schedule.current_planned_end"]}]
    return base + list(extra)


def version(tag, **overrides):
    overrides.setdefault("source_refs", refs())
    item = real_item(OID, **overrides)
    return package([item], version=tag)


def publish_import(service, editor, **overrides):
    import_package(service.objects, version("v1", **overrides))
    item = editor.get(f"/staff/objects/{OID}")["body"]["data"]["item"]
    return editor.publish(item, reason="Первая публикация")["body"]["data"]["item"]


def pending(editor):
    data = editor.get(f"/staff/objects/{OID}/import-candidates")["body"]["data"]
    return [c for c in data["items"] if c["resolution"] is None]


def apply(editor, cand, revision, reason="Принято по источнику", **extra):
    return editor.post(f"/staff/objects/{OID}/import-candidates/{cand['id']}/apply",
                       {"expected_revision": revision, "reason": reason, **extra})


def object_state(service):
    with service.db.read() as conn:
        obj = tuple(conn.execute("SELECT * FROM civic_objects WHERE id = ?", (OID,)).fetchone())
        hist = conn.execute("SELECT COUNT(*) FROM civic_history WHERE object_id = ?", (OID,)).fetchone()[0]
        cands = [tuple(r) for r in conn.execute("SELECT * FROM civic_import_candidates ORDER BY id")]
    return obj, hist, cands


# --- жизненный цикл источника -----------------------------------------------------------

def test_lifecycle_warnings_unknown_is_not_zero_or_forever(service):
    two = {"id": "src-2", "url": "https://example.org/n/2", "publisher": "Тест-2", "published_on": "2026-10-02",
           "retrieved_at": "2026-10-05T11:00:00+05:00", "access_status": "not_fetched", "license": None,
           "fields": ["schedule.current_planned_end"]}
    items = [
        real_item("ast-r13-expired", source_refs=refs(), status="in_progress",
                  schedule=schedule("2026-09-30", start="2026-09-01")),
        real_item("ast-r13-open", source_refs=refs(), status="planned", schedule=schedule(None)),
        real_item("ast-r13-two", source_refs=refs(two)),
    ]
    report = import_package(service.objects, package(items))
    codes = {i["external_id"]: [w["code"] for w in i.get("warnings", [])] for i in report["items"]}
    assert codes == {"ast-r13-expired": ["end_date_passed"], "ast-r13-open": ["end_date_unknown"],
                     "ast-r13-two": ["field_has_several_sources", "observed_source_not_fetched"]}
    # Ни статус, ни срок, ни бюджет не «додуманы»: прошедший срок не завершил работы, нет суммы — null.
    expired = service.objects.get_staff("ast-r13-expired")["item"]
    assert expired["status"] == "in_progress"
    opened = service.objects.get_staff("ast-r13-open")["item"]
    assert opened["schedule"]["current_planned_end"] is None and opened["budget"]["amount_kzt"] is None
    assert report["summary"]["budget_unknown"] == 3


def test_field_removed_by_source_is_proposed_as_null_not_zero(service, editor):
    amount = {"amount_kzt": 5000000, "basis": "planned", "source_id": "src-1"}
    item = publish_import(service, editor, budget=amount)
    import_package(service.objects, version("v2"))  # источник больше не называет сумму
    cand = pending(editor)[0]
    budget = {f["path"]: f for f in cand["review"]["fields"] if f["path"].startswith("budget.")}
    assert budget["budget.amount_kzt"]["current"] == 5000000
    assert budget["budget.amount_kzt"]["proposed"] is None
    assert budget["budget.amount_kzt"]["changed_by_source"] is True
    # Публичная карточка не меняется, пока редактор не решит.
    public = call(service, "GET", f"/objects/{OID}")["body"]["data"]["item"]
    assert public["budget"]["amount_kzt"] == 5000000
    assert item["revision"] == editor.get(f"/staff/objects/{OID}")["body"]["data"]["item"]["revision"]


# --- контракт проверки и частичное принятие -----------------------------------------------

def test_review_shows_origin_of_each_change_and_partial_accept_keeps_editor_choice(service, editor):
    item = publish_import(service, editor)
    item = editor.update(item, {"title": "Название уточнено редактором"},
                         reason="Опечатка в источнике")["body"]["data"]["item"]
    v2 = version("v2", title="Новое название из источника", schedule=schedule("2026-11-30"))
    import_package(service.objects, v2)
    cand = pending(editor)[0]
    review = {f["path"]: f for f in cand["review"]["fields"]}
    assert set(review) == {"title", "schedule.current_planned_end"}
    assert review["title"]["conflict"] is True  # менял и редактор, и источник
    assert review["schedule.current_planned_end"] == {
        "path": "schedule.current_planned_end", "current": "2026-10-20", "proposed": "2026-11-30",
        "proposed_sources": ["src-1"], "current_sources": ["src-1"], "previous_import": "2026-10-20",
        "changed_by_source": True, "changed_by_editor": False, "conflict": False}
    assert cand["review"]["locked_fields"] == [{
        "path": "schedule.original_planned_end", "kept": "2026-10-20", "source_value": None,
        "note": "Первоначальный срок зафиксирован первой публикацией и не меняется кандидатом."}]
    result = apply(editor, cand, item["revision"], fields=["schedule.current_planned_end"],
                   reason="Срок по источнику; название оставлено редакторское")
    assert result["status"] == 200, result["body"]
    staff = result["body"]["data"]["item"]
    assert staff["title"] == "Название уточнено редактором"
    assert staff["schedule"]["current_planned_end"] == "2026-11-30"
    assert staff["schedule"]["original_planned_end"] == "2026-10-20"
    decided = editor.get(f"/staff/objects/{OID}/import-candidates")["body"]["data"]["items"][0]
    assert decided["resolution"] == "partially_applied"
    assert decided["decision"] == {"by": "editor1", "reason": "Срок по источнику; название оставлено редакторское",
                                   "accepted_fields": ["schedule.current_planned_end"],
                                   "resulting_revision": staff["revision"]}
    # Тот же пакет повторно не предлагает отклонённое название снова.
    again = import_package(service.objects, copy.deepcopy(v2))
    assert again["items"][0]["action"] == "skip_unchanged" and pending(editor) == []


def test_bad_field_list_or_invalid_result_is_rejected_atomically(service, editor):
    item = publish_import(service, editor)
    amount = {"amount_kzt": 7000000, "basis": "contract", "source_id": "src-1"}
    import_package(service.objects, version("v2", budget=amount, schedule=schedule("2026-11-30")))
    cand = pending(editor)[0]
    before = object_state(service)
    for fields in (["title"], [], "schedule.current_planned_end", ["budget.amount_kzt"]):
        # title не менялся; пустой список; не список; сумма без source_id/basis -> недопустимый результат.
        result = apply(editor, cand, item["revision"], fields=fields)
        assert result["status"] == 422, (fields, result["body"])
        assert object_state(service) == before
    assert apply(editor, cand, item["revision"], fields=["budget.amount_kzt", "budget.basis",
                                                         "budget.source_id"])["status"] == 200


def test_source_changed_again_while_form_open_is_409(service, editor):
    item = publish_import(service, editor)
    import_package(service.objects, version("v2", schedule=schedule("2026-11-30")))
    open_form = pending(editor)[0]  # редактор открыл форму на v2
    import_package(service.objects, version("v3", schedule=schedule("2026-12-15")))
    before = object_state(service)
    stale = apply(editor, open_form, item["revision"])
    assert stale["status"] == 409 and stale["body"]["error"]["code"] == "candidate_superseded"
    assert "изменился ещё раз" in stale["body"]["error"]["message"]
    assert object_state(service) == before
    (current,) = pending(editor)
    assert current["review"]["fields"][0]["proposed"] == "2026-12-15"
    # Источник вернулся к v2 — актуальной снова становится v2, v3 заменена.
    import_package(service.objects, version("v2-again", schedule=schedule("2026-11-30")))
    (reopened,) = pending(editor)
    assert reopened["id"] == open_form["id"]
    assert reopened["review"]["fields"][0]["proposed"] == "2026-11-30"


def test_two_editors_deciding_same_candidate_one_wins(service, editor, editor2):
    item = publish_import(service, editor)
    import_package(service.objects, version("v2", schedule=schedule("2026-11-30")))
    cand = pending(editor)[0]
    results = []
    barrier = threading.Barrier(2)

    def run(who, action):
        barrier.wait()
        results.append(who.post(f"/staff/objects/{OID}/import-candidates/{cand['id']}/{action}",
                                {"expected_revision": item["revision"], "reason": f"{action} решение"}))

    threads = [threading.Thread(target=run, args=(editor, "apply")),
               threading.Thread(target=run, args=(editor2, "dismiss"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r["status"] for r in results) == [200, 409]
    decided = editor.get(f"/staff/objects/{OID}/import-candidates")["body"]["data"]["items"]
    assert len(decided) == 1 and decided[0]["resolution"] in ("applied", "dismissed")
    history = service.objects.get_staff(OID)["history"]
    assert [h["revision"] for h in history] == list(range(1, len(history) + 1))


# --- приёмочная последовательность -----------------------------------------------------------

def test_acceptance_draft_publish_source_change_review_accept_conflict_restart(service, editor, editor2, db_path,
                                                                                clock):
    # 1. create draft (импорт источника)
    report = import_package(service.objects, version("v1"))
    assert report["items"][0]["action"] == "create"
    item = editor.get(f"/staff/objects/{OID}")["body"]["data"]["item"]
    assert (item["publication"], item["revision"]) == ("draft", 1)
    # 2. publish
    clock.advance(minutes=10)
    item = editor.publish(item, reason="Работы начинаются по плану")["body"]["data"]["item"]
    assert (item["revision"], item["schedule"]["original_planned_end"]) == (2, "2026-10-20")
    # 3. changed source
    clock.advance(minutes=10)
    report = import_package(service.objects, version("v2", schedule=schedule("2026-11-30"),
                                                     source_refs=refs(published="2026-10-09")))
    entry = report["items"][0]
    assert entry["action"] == "editor_review"
    assert entry["source_refs_change"] == {"added": [], "removed": [], "changed": {"src-1": ["published_on"]}}
    # 4. review (второй редактор держит форму на старой ревизии)
    cand = pending(editor)[0]
    stale_form_revision = item["revision"]
    # 5. accepted update (служебная причина) + публикация с публичным объяснением
    clock.advance(minutes=5)
    accepted = apply(editor, cand, item["revision"], reason="Внутренне: письмо подрядчика №12")
    assert accepted["status"] == 200
    item = accepted["body"]["data"]["item"]
    item = editor.publish(item, reason="Срок перенесён на 30 ноября по данным источника")["body"]["data"]["item"]
    # 6. conflict rejection: второй редактор с устаревшей ревизией
    before = object_state(service)
    conflict = editor2.update({"id": OID, "revision": stale_form_revision},
                              {"schedule": {"current_planned_end": "2026-10-25"}}, reason="Старая форма")
    assert conflict["status"] == 409 and conflict["body"]["error"]["current_revision"] == item["revision"]
    assert object_state(service) == before

    # Перезапуск: новый сервис на том же файле.
    restarted = CivicService(db_path, clock=clock)
    staff = restarted.objects.get_staff(OID)
    assert staff["item"]["revision"] == 4
    assert staff["item"]["schedule"]["original_planned_end"] == "2026-10-20"
    assert staff["item"]["schedule"]["current_planned_end"] == "2026-11-30"
    assert [(h["revision"], h["action"], h["actor_label"]) for h in staff["history"]] == [
        (1, "import_create", "import:r05-astana-real:cli"), (2, "publish", "editor1"),
        (3, "update", "editor1"), (4, "publish", "editor1")]
    assert staff["history"][2]["reason"] == "Внутренне: письмо подрядчика №12"
    public = call(restarted, "GET", f"/objects/{OID}")["body"]["data"]
    assert public["item"]["revision"] == 4 and public["item"]["schedule"]["current_planned_end"] == "2026-11-30"
    assert [(h["revision"], h["reason"]) for h in public["history"]] == [
        (2, "Работы начинаются по плану"), (4, "Срок перенесён на 30 ноября по данным источника")]
    assert "письмо подрядчика" not in str(public)  # служебная причина не стала публичной
    assert public["history"][0]["at"] < public["history"][1]["at"]
    decided = restarted.objects.list_candidates(OID)["items"][0]
    assert decided["decision"]["resulting_revision"] == 3 and decided["resolution"] == "applied"
    # Новый вход после перезапуска работает; старая форма по-прежнему 409.
    again = Editor(restarted, "editor1", PASSWORD)
    assert again.update({"id": OID, "revision": 2}, {"title": "x"})["status"] == 409
