"""R02 раунд 12: публичный API никогда не отдаёт черновики, служебные заметки, логины и кандидатов.

Маркеры расставлены во все служебные места; затем обходятся все публичные ответы
(список с фильтрами и страницами, карточка, история, HEAD, /session без входа).
"""

import json

from ui.civic_store.importer import import_package
from r06store_helpers import Editor, PASSWORD, call, context
from test_r06store_import_cli import package, real_item


SECRET_MARKERS = ("MARK-INTERNAL", "MARK-DRAFT", "MARK-ARCHIVED", "MARK-CANDIDATE", "MARK-REASON-ARCH",
                  "MARK-UNPUBLISHED", "editor1", "editor2", "Редактор Один", "import:")


def build_world(service, editor):
    pub = editor.create(title="Опубликованная тестовая запись", internal_notes="MARK-INTERNAL телефон +7 700 000 00 00")
    pub = editor.publish(pub, reason="Публикация")["body"]["data"]["item"]
    # Неопубликованная правка опубликованного объекта.
    editor.update(pub, {"description": "MARK-UNPUBLISHED правка ещё не опубликована"})
    editor.create(title="MARK-DRAFT черновик", internal_notes="MARK-INTERNAL")
    arch = editor.create(title="MARK-ARCHIVED запись")
    arch = editor.publish(arch, reason="Публикация")["body"]["data"]["item"]
    editor.archive(arch, reason="MARK-REASON-ARCH служебная причина")
    # Опубликованный импорт + кандидат с новым содержимым.
    import_package(service.objects, package([real_item("ast-r12-p")]))
    imp = editor.get("/staff/objects/ast-r12-p")["body"]["data"]["item"]
    editor.publish(imp, reason="Публикация импорта")
    import_package(service.objects, package([real_item("ast-r12-p", title="MARK-CANDIDATE новое название")],
                                            version="v2"))
    return pub


def public_responses(service):
    out = []
    lst = call(service, "GET", "/objects", query={"limit": ["1"]})
    out.append(lst)
    cursor = lst["body"]["data"]["next_cursor"]
    ids = [item["id"] for item in lst["body"]["data"]["items"]]
    while cursor:
        page = call(service, "GET", "/objects", query={"limit": ["1"], "cursor": [cursor]})
        out.append(page)
        ids += [item["id"] for item in page["body"]["data"]["items"]]
        cursor = page["body"]["data"]["next_cursor"]
    out.append(call(service, "GET", "/objects", query={"from": ["2020-01-01"], "to": ["2030-12-31"]}))
    for object_id in ids:
        out.append(call(service, "GET", f"/objects/{object_id}"))
        out.append(call(service, "HEAD", f"/objects/{object_id}"))
    out.append(call(service, "GET", "/session"))
    return ids, out


def test_public_api_never_leaks_staff_data(service, editor):
    build_world(service, editor)
    ids, responses = public_responses(service)
    assert len(ids) == 2  # опубликованная ручная и опубликованный импорт; без черновика и архива
    text = json.dumps([r["body"] for r in responses], ensure_ascii=False)
    for marker in SECRET_MARKERS:
        assert marker not in text, marker
    for forbidden_key in ("internal_notes", "staff", "created_by", "actor_label", "diff",
                          "snapshot", "import", "password_hash", "token"):
        assert f"\"{forbidden_key}\"" not in text, forbidden_key
    assert call(service, "GET", "/session")["body"]["data"] == {
        "authenticated": False, "user": None, "csrf_token": None}
    # Черновик и архив публично неотличимы от отсутствия.
    staff_ids = [i["id"] for i in editor.get("/staff/objects")["body"]["data"]["items"]]
    for object_id in set(staff_ids) - set(ids):
        assert call(service, "GET", f"/objects/{object_id}")["status"] == 404


def test_staff_routes_refuse_anonymous_and_stale_sessions(service, editor):
    pub = build_world(service, editor)
    staff_paths = ["/staff/objects", f"/staff/objects/{pub['id']}", "/staff/audit", "/staff/meta",
                   "/staff/objects/ast-r12-p/import-candidates"]
    for path in staff_paths:
        assert call(service, "GET", path)["status"] == 401
    # Старые сессии: после выхода, после revoke-sessions и после отключения редактора.
    old = Editor(service, "editor1", PASSWORD)
    call(service, "POST", "/session/logout", {}, ctx=old.ctx())
    assert old.get("/staff/objects")["status"] == 401
    revoked = Editor(service, "editor1", PASSWORD)
    service.accounts.revoke_all("editor1")
    assert revoked.get("/staff/objects")["status"] == 401
    assert revoked.post(f"/staff/objects/{pub['id']}/archive",
                        {"expected_revision": 99, "reason": "Попытка"})["status"] == 401
    victim = Editor(service, "editor2", PASSWORD + "x")
    service.accounts.disable_user("editor2")
    for path in staff_paths:
        assert victim.get(path)["status"] == 401
    # Подделанная cookie и чужой CSRF не дают записи.
    forged = context("x" * 43, editor.csrf)
    assert call(service, "POST", "/staff/objects", {"title": "x"}, ctx=forged)["status"] == 401
    fresh = Editor(service, "editor1", PASSWORD)
    wrong_csrf = context(fresh.cookie, editor.csrf)
    assert call(service, "POST", "/staff/objects", {"title": "x"}, ctx=wrong_csrf)["status"] == 403
