"""R15: жалобы v2 (владелец R09, ui/civic_feedback/v2) — что видят другие жители, накрутки, ввод.

Сервис вызывается так же, как его вызывает шлюз R01 (handle(method, path, query, body, principal, context)),
на временной SQLite. Так тесты работают и на сборке R01, и в ветке R09 (R15_ROOT=...).
"""

from __future__ import annotations

import json
import types

import pytest

from r15_common import need_module, xfail

AUTHOR = "device-r15-author-000001"
STRANGER = "device-r15-stranger-00001"
POINT = [71.4123456, 51.1234567]
# Подпись цели, которую прислал сам житель (её можно подменить: в запросе — что угодно).
FAKE_LABEL = "<img src=x onerror=alert(1)> Остановка «Акимат берёт взятки»"


@pytest.fixture()
def svc(tmp_path):
    integration = need_module("ui.civic_feedback.v2.integration")
    service = integration.make_service(str(tmp_path / "civic.sqlite3"))
    yield service
    service.store.close()


def ctx(device=None, same_origin=True):
    headers = {"X-Birge-Device": device} if device else {}
    return {"headers": headers, "host_allowed": True, "is_same_origin": same_origin}


def call(svc, method, path, query="", body=None, principal=None, context=None):
    reply = svc.handle(method, "/api/civic/v2" + path, query, body, principal, context or ctx(STRANGER))
    assert reply is not None, path
    return reply["status"], reply["body"]


def create(svc, device=AUTHOR, **extra):
    body = {"text": "Яма у остановки, вечером опасно", "category": "roads", "point": list(POINT),
            "target": {"kind": "object", "id": "osm-node-123", "label_ru": FAKE_LABEL, "label_kk": FAKE_LABEL}}
    body.update(extra)
    status, data = call(svc, "POST", "/complaints", body=body, context=ctx(device))
    assert status in (200, 201), data
    return data["data"]["complaint"]


def staff_principal(svc, check_csrf=True):
    """Сотрудник, как его отдаёт R02 resolve_principal: is_staff + check_csrf(заголовок)."""
    principal = types.SimpleNamespace(is_staff=True, username="r15-staff", role="editor")
    if check_csrf:
        principal.check_csrf = lambda value: value == "csrf-r15"
    return principal


def public_items(svc, device=STRANGER):
    status, data = call(svc, "GET", "/complaints", context=ctx(device))
    assert status == 200, data
    return data["data"]["items"]


# --- 4. персональные данные: что видят другие жители --------------------------------------

def test_public_list_has_no_text_device_or_model(svc):
    create(svc)
    item = public_items(svc)[0]
    assert "text" not in item and "model" not in item and "code" not in item
    assert not {"device_id", "device_hash", "request_id"} & set(item)
    assert all(set(h) <= {"at", "status"} for h in item["status_history"])


def test_stranger_sees_no_text_author_sees_own(svc):
    created = create(svc)
    _s, stranger = call(svc, "GET", "/complaints/" + created["id"], context=ctx(STRANGER))
    assert "text" not in stranger["data"]["complaint"]
    _s, by_code = call(svc, "GET", "/complaints/" + created["code"], context=ctx(STRANGER))
    assert "text" not in by_code["data"]["complaint"]
    _s, author = call(svc, "GET", "/complaints/" + created["id"], context=ctx(AUTHOR))
    assert author["data"]["complaint"]["text"].startswith("Яма")


def test_staff_name_and_note_are_not_public(svc):
    created = create(svc)
    status, data = call(svc, "POST", "/complaints/%s/status" % created["id"], body={"status": "accepted",
                        "note": "звонил жителю"}, principal=staff_principal(svc),
                        context={"headers": {"X-CSRF-Token": "csrf-r15"}, "host_allowed": True, "is_same_origin": True})
    assert status == 200, data
    text = json.dumps(public_items(svc), ensure_ascii=False)
    assert "r15-staff" not in text and "звонил" not in text


def test_events_feed_has_no_personal_fields(svc):
    create(svc)
    status, data = call(svc, "GET", "/complaints/events", "after=0", context=ctx())
    assert status == 200
    for event in data["data"]["events"]:
        assert not {"text", "point", "device_id", "device_hash", "code"} & set(event)


@xfail("S03")
def test_public_views_do_not_reveal_exact_resident_point(svc):
    """Точка жителя (6 знаков ≈ 10 см) + время до секунды видны всем — можно понять, где живёт автор."""
    created = create(svc)
    _s, metoo = call(svc, "POST", "/complaints/%s/metoo" % created["id"], body={}, context=ctx(STRANGER))
    _s, summary = call(svc, "GET", "/complaints/summary", "target_id=osm-node-123", context=ctx(STRANGER))
    _s, detail = call(svc, "GET", "/complaints/" + created["id"], context=ctx(STRANGER))
    views = [public_items(svc)[0], metoo["data"]["complaint"], summary["data"]["top"], detail["data"]["complaint"]]
    for view in views:
        point = view.get("point")
        # Достаточно для карты района: не точнее 3 знаков (≈ 100 м) или точки нет вовсе.
        assert point is None or all(round(v, 3) == v for v in point), point


def test_author_keeps_exact_point(svc):
    created = create(svc)
    _s, author = call(svc, "GET", "/complaints/" + created["id"], context=ctx(AUTHOR))
    assert author["data"]["complaint"]["point"] == [round(v, 6) for v in POINT]


@xfail("S04")
def test_target_label_from_resident_is_not_shown_to_others(svc):
    """Подпись цели приходит из запроса жителя и показывается всем (и на карте акимата у R07)."""
    create(svc)
    for view in (public_items(svc)[0], public_items(svc, device=None)[0]):
        target = view["target"]
        assert FAKE_LABEL not in (target.get("label_ru"), target.get("label_kk")), target


# --- 2. доступ ------------------------------------------------------------------------------

@pytest.mark.parametrize("action,body", [("status", {"status": "fixed"}), ("duplicate", {"of": "c-000000000000"})])
def test_staff_actions_refuse_resident(svc, action, body):
    created = create(svc)
    status, data = call(svc, "POST", "/complaints/%s/%s" % (created["id"], action), body=body, context=ctx(AUTHOR))
    assert status == 403, data


def test_staff_action_needs_csrf_token(svc):
    created = create(svc)
    status, data = call(svc, "POST", "/complaints/%s/status" % created["id"], body={"status": "accepted"},
                        principal=staff_principal(svc), context={"headers": {}, "host_allowed": True, "is_same_origin": True})
    assert status == 403 and data["error"]["code"] == "csrf_failed"


@xfail("S05")
def test_staff_check_fails_closed_without_csrf_method(svc):
    """principal без check_csrf (другой формат сессии) — проверка CSRF молча пропускается."""
    created = create(svc)
    status, _data = call(svc, "POST", "/complaints/%s/status" % created["id"], body={"status": "accepted"},
                         principal=staff_principal(svc, check_csrf=False),
                         context={"headers": {}, "host_allowed": True, "is_same_origin": True})
    assert status == 403


def test_cross_origin_post_is_refused_by_service_too(svc):
    status, data = call(svc, "POST", "/complaints", body={"text": "яма"}, context=ctx(AUTHOR, same_origin=False))
    assert status == 403 and data["error"]["code"] == "cross_origin"


def test_other_device_cannot_read_mine(svc):
    create(svc)
    status, data = call(svc, "GET", "/complaints/mine", context=ctx(STRANGER))
    assert status == 200 and data["data"]["items"] == []


# --- 3. накрутки ------------------------------------------------------------------------------

def test_metoo_once_per_device_and_not_for_author(svc):
    created = create(svc)
    path = "/complaints/%s/metoo" % created["id"]
    assert call(svc, "POST", path, body={}, context=ctx(STRANGER))[1]["data"]["result"] == "added"
    assert call(svc, "POST", path, body={}, context=ctx(STRANGER))[1]["data"]["result"] == "already"
    assert call(svc, "POST", path, body={}, context=ctx(AUTHOR))[1]["data"]["result"] == "author"


def test_create_limit_per_device(svc):
    for i in range(30):
        status, data = call(svc, "POST", "/complaints", body={"text": "Яма номер %d у дома" % i, "category": "roads",
                                                              "point": POINT}, context=ctx(AUTHOR))
        if status == 429:
            assert i >= 1 and data["error"]["code"] == "too_many"
            return
    pytest.fail("30 жалоб подряд с одного устройства без ограничения")


# --- 5. ввод ----------------------------------------------------------------------------------

INJECTIONS = ["roads' OR '1'='1", "roads);DROP TABLE complaints_v2;--", "new,fixed' --", "\" OR 1=1 --"]


@pytest.mark.parametrize("value", INJECTIONS)
def test_sql_injection_in_filters_is_rejected(svc, value):
    create(svc)
    from urllib.parse import quote
    for name in ("category", "status", "bbox", "since"):
        status, _data = call(svc, "GET", "/complaints", "%s=%s" % (name, quote(value)))
        assert status == 422, (name, value, status)
    status, data = call(svc, "GET", "/complaints/summary", "target_id=" + quote(value))
    assert status == 200 and data["data"]["complaints"] == 0
    assert len(public_items(svc)) == 1  # таблица цела


@pytest.mark.parametrize("point", [[0, 0], [71.4, 91], ["71.4", "51.1"], [float("nan"), 51.1], [71.4], None, True])
def test_bad_point_is_rejected(svc, point):
    status, _data = call(svc, "POST", "/complaints", body={"text": "Яма у дома", "category": "roads", "point": point},
                         context=ctx(AUTHOR))
    assert status == 422


def test_long_text_and_short_device_are_rejected(svc):
    status, _d = call(svc, "POST", "/complaints", body={"text": "я" * 2001, "category": "roads", "point": POINT},
                      context=ctx(AUTHOR))
    assert status == 422
    status, _d = call(svc, "POST", "/complaints", body={"text": "Яма у дома", "category": "roads", "point": POINT},
                      context=ctx("short"))
    assert status == 422


@pytest.mark.parametrize("value", ["٣", "1e3", "-5", "999999999999", "abc", ""])
def test_summary_days_never_500(svc, value):
    status, _data = call(svc, "GET", "/complaints/summary", "target_id=osm-node-1&days=" + value)
    assert status < 500


@xfail("S06")
def test_summary_days_superscript_digit_is_not_500(svc):
    """str.isdigit() пропускает «²», а int() его не понимает -> 500 вместо 422."""
    status, _data = call(svc, "GET", "/complaints/summary", "target_id=osm-node-1&days=²")
    assert status < 500
