"""R16 · «Мой двор» и «Сделаем вместе»: API модуля ui.civic_together (без сети, временная SQLite).

Проверяем то, что видит житель и сотрудник: создание и модерация, «Я приду» один раз с устройства, лимиты, права
сотрудника (сессия + CSRF), приватность (в ответах нет id устройств, хэшей и времени вступления), фото «после» без EXIF,
лента событий (CONTRACT §5.8), демо-набор и демо-мир R02 (seed_world, идемпотентно), идея -> инициатива (R06).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import base64
import json
import re
from urllib.parse import quote

import pytest

from ui.civic_together import create_from_idea, initiatives_summary, pickups, seed_world, updates
from ui.civic_together import neighbors
from ui.civic_together.demo import SCENE, next_weekday, rows as demo_rows
from ui.civic_together.service import make_service
from ui.civic_together.store import ASTANA, iso

P = "/api/civic/v2/together"
DEV_A = "d-test-device-aaaa-0001"
DEV_B = "d-test-device-bbbb-0002"
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


class Staff:
    """Сотрудник как principal R02: is_staff, username и проверка CSRF."""

    is_staff = True
    username = "operator"
    role = "editor"

    @staticmethod
    def check_csrf(value):
        return value == "csrf-ok"


class Resident:
    is_staff = False
    username = "someone"
    role = "viewer"

    @staticmethod
    def check_csrf(value):
        return True


def ctx(device=None, csrf=None, same_origin=True):
    headers = {}
    if device:
        headers["x-birge-device"] = device
    if csrf:
        headers["x-csrf-token"] = csrf
    return {"headers": headers, "host_allowed": True, "is_same_origin": same_origin, "client_ip": "127.0.0.1"}


@pytest.fixture(autouse=True)
def offline_neighbors():
    """Соседи (R07/R06/R12) в тестах API — фикстуры: тесты не зависят от данных карты и чужих демо-наборов."""
    geo = {
        "yard-1454082638": {"label_ru": "Двор: GreenLine.Asyl Mura", "label_kk": "Аула: GreenLine.Asyl Mura",
                            "point": [71.3970633, 51.1348358], "approximate": False, "street": None,
                            "geometry": {"type": "Polygon", "coordinates": [[[71.3948, 51.1315], [71.3993, 51.1315],
                                                                             [71.3993, 51.1382], [71.3948, 51.1382],
                                                                             [71.3948, 51.1315]]]}},
    }
    neighbors.configure(
        yard_geo=lambda yid: geo.get(yid),
        yard_at=lambda lon, lat: {"id": "yard-1454082638"} if 71.3948 <= lon <= 71.3993 and 51.1315 <= lat <= 51.1382
        else None,
        district_of=lambda point: "nura",
        problems=lambda g: {"status": "ok", "items": [{"target": {"kind": "segment", "id": "osm-w1-1",
                                                                  "label_ru": "Участок ул. Пример", "label_kk": "Мысал"},
                                                       "level": 2, "count": 4, "state": "active",
                                                       "last_at": "2026-10-15T10:00:00+05:00", "subtopic": None,
                                                       "demo": True}],
                            "fixed": [], "count": 1, "people": 4},
        ideas=lambda g, d: neighbors.no_data("ideas_unavailable"),
        works=lambda g, d: neighbors.no_data("works_unavailable"),
    )
    yield
    for name in ("yard_geo", "yard_at", "district_of", "problems", "ideas", "works"):
        neighbors.configure(**{name: None})


@pytest.fixture()
def clock():
    state = {"now": datetime(2026, 10, 15, 12, 0, tzinfo=ASTANA)}

    def now():
        return state["now"]

    now.state = state
    return now


@pytest.fixture()
def svc(tmp_path, clock):
    return make_service(tmp_path / "civic.sqlite3", clock=clock, demo=True, autopublish=False)


def call(service, method, path, body=None, *, principal=None, context=None, query=""):
    return service.handle(method, P + path, query, body, principal, context or ctx())


def new_body(**extra):
    starts = datetime(2026, 10, 18, 10, 0, tzinfo=ASTANA)
    body = {"kind": "cleanup", "title": "Уберём двор вместе", "text": "Соберёмся у площадки.",
            "point": [71.397, 51.1348], "target": {"kind": "area", "id": "yard-1454082638"},
            "starts_at": iso(starts), "bring": ["перчатки", "Перчатки", "мешки"]}
    body.update(extra)
    return body


def dump(reply) -> str:
    return json.dumps(reply, ensure_ascii=False)


# --------------------------------------------------------------------------- создание и модерация
def test_create_goes_on_review_and_is_hidden_from_public(svc):
    r = call(svc, "POST", "/initiatives", new_body(), context=ctx(DEV_A))
    assert r["status"] == 201, r
    item = r["body"]["initiative"]
    assert item["status"] == "on_review" and item["mine"] is True
    assert item["bring"] == ["перчатки", "мешки"]                  # повтор без учёта регистра убран
    assert item["target"]["label_ru"] == "Двор: GreenLine.Asyl Mura"   # подпись — с карты R12, не из запроса
    public = call(svc, "GET", "/initiatives", context=ctx(DEV_B))["body"]["items"]
    assert item["id"] not in [i["id"] for i in public]
    assert call(svc, "GET", "/initiatives/" + item["id"], context=ctx(DEV_B))["status"] == 404
    mine = call(svc, "GET", "/initiatives", context=ctx(DEV_A), query="view=mine")["body"]["items"]
    assert [i["id"] for i in mine] == [item["id"]] and mine[0]["status"] == "on_review"
    assert call(svc, "GET", "/initiatives/" + item["id"], context=ctx(DEV_A))["status"] == 200


def test_request_id_makes_create_idempotent(svc):
    first = call(svc, "POST", "/initiatives", new_body(request_id="req-12345678"), context=ctx(DEV_A))
    again = call(svc, "POST", "/initiatives", new_body(request_id="req-12345678"), context=ctx(DEV_A))
    assert first["status"] == 201 and again["status"] == 200
    assert first["body"]["initiative"]["id"] == again["body"]["initiative"]["id"]


@pytest.mark.parametrize("patch, field", [
    ({"kind": "party"}, "kind"), ({"title": "Ой"}, "title"), ({"title": "x" * 81}, "title"),
    ({"point": [10, 10]}, "point"), ({"point": "71,51"}, "point"), ({"starts_at": "завтра"}, "starts_at"),
    ({"starts_at": "2026-10-14T10:00:00+05:00"}, "starts_at"), ({"starts_at": "2027-10-14T10:00:00+05:00"}, "starts_at"),
    ({"ends_at": "2026-10-18T09:00:00+05:00"}, "ends_at"), ({"bring": ["a"] * 9}, "bring"),
    ({"target": {"kind": "object", "id": "osm-node-1"}}, "target"), ({"target": {"kind": "area", "id": "yard-404"}}, "target"),
])
def test_create_validation(svc, patch, field):
    r = call(svc, "POST", "/initiatives", new_body(**patch), context=ctx(DEV_A))
    assert r["status"] in (400, 422), r
    assert r["body"]["field"] == field
    assert isinstance(r["body"]["message"], str) and r["body"]["message"]


def test_create_needs_device_and_same_origin(svc):
    assert call(svc, "POST", "/initiatives", new_body(), context=ctx())["status"] == 400
    assert call(svc, "POST", "/initiatives", new_body(), context=ctx(DEV_A, same_origin=False))["status"] == 403


def test_personal_data_is_flagged_and_masked_for_public(svc):
    body = new_body(text="Звоните +7 701 123-45-67 или пишите a.b@example.com, ИИН 900101300123")
    r = call(svc, "POST", "/initiatives", body, context=ctx(DEV_A))
    iid = r["body"]["initiative"]["id"]
    assert set(r["body"]["hints"]) >= {"phone", "email", "iin"}
    staff = call(svc, "GET", "/initiatives", principal=Staff(), query="view=staff&tab=queue")["body"]
    row = next(i for i in staff["items"] if i["id"] == iid)
    assert {"phone", "email", "iin"} <= set(row["flags"])
    assert "+7 701 123-45-67" in row["original"]["text"]
    assert call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "publish"}, principal=Staff(),
                context=ctx(csrf="csrf-ok"))["status"] == 200
    public = call(svc, "GET", "/initiatives/" + iid, context=ctx(DEV_B))["body"]["initiative"]
    assert "701" not in public["text"] and "example.com" not in public["text"] and "900101300123" not in public["text"]
    assert "***" in public["text"] and "original" not in public


def test_staff_rights_session_and_csrf(svc):
    iid = SCENE["initiative"]
    body = {"inventory": True, "pickup_service": "waste", "note": "Мешки и вывоз в 14:00"}
    assert call(svc, "POST", f"/initiatives/{iid}/support", body)["status"] == 401
    assert call(svc, "POST", f"/initiatives/{iid}/support", body, principal=Resident(),
                context=ctx(csrf="csrf-ok"))["status"] == 403
    assert call(svc, "POST", f"/initiatives/{iid}/support", body, principal=Staff(),
                context=ctx(csrf="wrong"))["body"]["error"] == "csrf_failed"
    assert call(svc, "POST", f"/initiatives/{iid}/support", body, principal=Staff(),
                context=ctx(csrf="csrf-ok", same_origin=False))["body"]["error"] == "cross_origin"
    ok = call(svc, "POST", f"/initiatives/{iid}/support", body, principal=Staff(), context=ctx(csrf="csrf-ok"))
    assert ok["status"] == 200
    support = ok["body"]["initiative"]["support"]
    assert support["by_akimat"] is True and support["pickup_service"] == "waste"
    assert call(svc, "GET", "/initiatives", query="view=staff")["status"] == 401
    assert call(svc, "GET", "/initiatives", principal=Resident(), query="view=staff")["status"] == 403


def test_support_validation_and_states(svc):
    iid = SCENE["initiative"]
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    assert call(svc, "POST", f"/initiatives/{iid}/support", {"pickup_service": "mars"}, **staff)["status"] == 422
    assert call(svc, "POST", f"/initiatives/{iid}/support", {"inventory": False, "pickup_service": None},
                **staff)["status"] == 422
    # На проверке и «сделано» поддержать нельзя.
    assert call(svc, "POST", "/initiatives/i-demo-review-flowers/support", {}, **staff)["status"] == 409
    assert call(svc, "POST", "/initiatives/i-demo-benches/support", {}, **staff)["status"] == 409


def test_moderation_hide_needs_reason_and_is_final(svc):
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    iid = "i-demo-review-flowers"
    assert call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "hide"}, **staff)["status"] == 422
    r = call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "hide", "reason": "spam"}, **staff)
    assert r["status"] == 200 and r["body"]["initiative"]["status"] == "hidden"
    assert call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "publish"}, **staff)["status"] == 409


# --------------------------------------------------------------------------- «Я приду»
def test_join_once_per_device_counts_from_14_to_15(svc):
    iid = SCENE["initiative"]
    before = call(svc, "GET", "/initiatives/" + iid)["body"]["initiative"]["joined"]
    assert before == 14
    first = call(svc, "POST", f"/initiatives/{iid}/join", {}, context=ctx(DEV_A))["body"]
    again = call(svc, "POST", f"/initiatives/{iid}/join", {}, context=ctx(DEV_A))["body"]
    assert (first["joined"], first["created"], again["joined"], again["created"]) == (15, True, 15, False)
    view = call(svc, "GET", "/initiatives/" + iid, context=ctx(DEV_A))["body"]["initiative"]
    assert view["my_join"] is True and view["joined"] == 15
    assert call(svc, "GET", "/initiatives/" + iid, context=ctx(DEV_B))["body"]["initiative"]["my_join"] is False
    left = call(svc, "POST", f"/initiatives/{iid}/leave", {}, context=ctx(DEV_A))["body"]
    assert left["joined"] == 14 and left["changed"] is True
    assert call(svc, "POST", f"/initiatives/{iid}/leave", {}, context=ctx(DEV_A))["body"]["changed"] is False
    # Демо-основу (14) «отписать» нельзя: устройств за ней нет.
    assert call(svc, "POST", f"/initiatives/{iid}/leave", {}, context=ctx(DEV_B))["body"]["joined"] == 14


def test_join_closed_or_hidden(svc):
    assert call(svc, "POST", "/initiatives/i-demo-review-flowers/join", {}, context=ctx(DEV_A))["status"] == 404
    assert call(svc, "POST", "/initiatives/i-demo-benches/join", {}, context=ctx(DEV_A))["status"] == 409
    assert call(svc, "POST", "/initiatives/i-unknown-1234/join", {}, context=ctx(DEV_A))["status"] == 404
    assert call(svc, "POST", "/initiatives/../join", {}, context=ctx(DEV_A))["status"] == 404


def test_join_rate_limit(svc):
    iid = SCENE["initiative"]
    codes = [call(svc, "POST", f"/initiatives/{iid}/{'join' if n % 2 == 0 else 'leave'}", {},
                  context=ctx(DEV_A))["status"] for n in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_create_limits_per_device(svc):
    codes = []
    for n in range(4):
        codes.append(call(svc, "POST", "/initiatives", new_body(title=f"Дело номер {n}"), context=ctx(DEV_A))["status"])
    assert codes == [201, 201, 201, 429]
    # Другое устройство — свой лимит.
    assert call(svc, "POST", "/initiatives", new_body(), context=ctx(DEV_B))["status"] == 201


# --------------------------------------------------------------------------- приватность
def test_privacy_no_devices_hashes_or_join_times_in_any_reply(svc):
    iid = SCENE["initiative"]
    replies = [
        call(svc, "POST", f"/initiatives/{iid}/join", {}, context=ctx(DEV_A)),
        call(svc, "POST", "/yards/yard-1454082638/join", {}, context=ctx(DEV_A)),
        call(svc, "POST", "/initiatives", new_body(), context=ctx(DEV_A)),
        call(svc, "GET", "/initiatives", context=ctx(DEV_A)),
        call(svc, "GET", "/initiatives", context=ctx(DEV_A), query="view=mine"),
        call(svc, "GET", "/initiatives/" + iid, context=ctx(DEV_A)),
        call(svc, "GET", "/yards/yard-1454082638", context=ctx(DEV_A)),
        call(svc, "GET", "/yards"),
        call(svc, "GET", "/updates", context=ctx(DEV_A)),
        call(svc, "GET", "/initiatives", principal=Staff(), query="view=staff&tab=queue"),
        call(svc, "GET", "/initiatives", principal=Staff(), query="view=staff&tab=published"),
    ]
    for reply in replies:
        text = dump(reply)
        assert reply["status"] in (200, 201), text[:300]
        assert DEV_A not in text and not HEX64.search(text), text[:300]
        assert "author_hash" not in text and "device" not in text and "operator" not in text
    yard = replies[6]["body"]
    assert isinstance(yard["yard"]["members"], int) and "member_list" not in yard and "members_at" not in dump(yard)


# --------------------------------------------------------------------------- отчёт «Сделано вместе» и фото
# Настоящая JPEG 8×6 (сохранена PIL один раз), в неё ниже вставляется сегмент APP1 «Exif» с маркой и GPS телефона.
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4pLSwzOko+MzZGNywtQFdBRkxOUlNSMj5aYVpQYEpR"
    "Uk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAARCAAGAAgDASIAAhEBAxEB"
    "/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2Jy"
    "ggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLD"
    "xMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3"
    "AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6"
    "goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwB1FFFc"
    "R5x//9k=")


def _jpeg_with_exif() -> bytes:
    payload = b"Exif\x00\x00MM\x00*\x00\x00\x00\x08PhoneMaker GPS 51.13N 71.43E"
    app1 = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    return TINY_JPEG[:2] + app1 + TINY_JPEG[2:]


def test_staff_report_marks_done_with_photo_without_exif(svc):
    iid = SCENE["initiative"]
    call(svc, "POST", f"/initiatives/{iid}/join", {}, context=ctx(DEV_A))
    raw = _jpeg_with_exif()
    assert b"Exif" in raw and b"PhoneMaker" in raw
    photo = {"data_url": "data:image/jpeg;base64," + base64.b64encode(raw).decode(), "width": 8, "height": 6}
    r = call(svc, "POST", f"/initiatives/{iid}/report", {"text": "Убрали двор и вывезли 20 мешков.", "photo": photo},
             principal=Staff(), context=ctx(csrf="csrf-ok"))
    assert r["status"] == 200, r
    item = call(svc, "GET", "/initiatives/" + iid)["body"]["initiative"]
    assert item["status"] == "done" and item["report"]["joined"] == 15
    url = item["report"]["photos"][0]["data_url"]
    clean = base64.b64decode(url.split(",", 1)[1])
    assert clean[:3] == b"\xff\xd8\xff" and b"Exif" not in clean and b"PhoneMaker" not in clean
    # «Я приду» после «сделано» закрыт.
    assert call(svc, "POST", f"/initiatives/{iid}/join", {}, context=ctx(DEV_B))["status"] == 409


def test_bad_photo_is_rejected(svc):
    iid = SCENE["initiative"]
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    bad = {"data_url": "data:image/jpeg;base64," + base64.b64encode(b"not a photo at all").decode()}
    assert call(svc, "POST", f"/initiatives/{iid}/report", {"photo": bad}, **staff)["body"]["field"] == "photo"
    big = {"data_url": "data:image/jpeg;base64," + "A" * 70_000}
    assert call(svc, "POST", f"/initiatives/{iid}/report", {"photo": big}, **staff)["status"] == 422
    svg = {"data_url": "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="}
    assert call(svc, "POST", f"/initiatives/{iid}/report", {"photo": svg}, **staff)["status"] == 422


def test_author_report_waits_for_review(svc, clock):
    body = new_body(starts_at=iso(datetime(2026, 10, 15, 14, 0, tzinfo=ASTANA)))
    iid = call(svc, "POST", "/initiatives", body, context=ctx(DEV_A))["body"]["initiative"]["id"]
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "publish"}, **staff)
    text = {"text": "Убрали листья у площадки, спасибо всем!"}
    assert call(svc, "POST", f"/initiatives/{iid}/report", text, context=ctx(DEV_B))["status"] == 403
    assert call(svc, "POST", f"/initiatives/{iid}/report", text, context=ctx(DEV_A))["body"]["error"] == "not_started"
    clock.state["now"] = datetime(2026, 10, 15, 17, 0, tzinfo=ASTANA)
    r = call(svc, "POST", f"/initiatives/{iid}/report", text, context=ctx(DEV_A))
    assert r["status"] == 200 and r["body"]["initiative"]["status"] == "published"
    assert r["body"]["initiative"]["report_status"] == "on_review" and r["body"]["initiative"]["report"] is None
    queue = call(svc, "GET", "/initiatives", principal=Staff(), query="view=staff&tab=queue")["body"]
    assert iid in [i["id"] for i in queue["reports"]]
    done = call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "publish_report"}, **staff)
    assert done["body"]["initiative"]["status"] == "done"


# --------------------------------------------------------------------------- двор
def test_yard_page_counts_and_membership(svc):
    page = call(svc, "GET", "/yards/yard-1454082638", context=ctx(DEV_A))["body"]
    assert page["yard"]["label_ru"] == "Двор: GreenLine.Asyl Mura" and page["yard"]["demo"] is True
    assert page["counts"] == {"members": 37, "problems": 1, "initiatives": 2}
    assert page["me"]["member"] is False
    assert page["ideas"]["status"] == "no_data" and page["works"]["status"] == "no_data"
    assert [i["id"] for i in page["initiatives"]["items"]] == [SCENE["initiative"]]
    joined = call(svc, "POST", "/yards/yard-1454082638/join", {}, context=ctx(DEV_A))["body"]
    assert joined == {"yard_id": "yard-1454082638", "members": 38, "member": True, "changed": True}
    assert call(svc, "GET", "/yards/yard-1454082638", context=ctx(DEV_A))["body"]["me"]["member"] is True
    left = call(svc, "POST", "/yards/yard-1454082638/leave", {}, context=ctx(DEV_A))["body"]
    assert left["members"] == 37 and left["member"] is False


def test_yard_unknown_and_neighbors_missing(svc):
    assert call(svc, "GET", "/yards/yard-0000")["status"] == 404
    assert call(svc, "GET", "/yards/bad id")["status"] == 404

    def broken(*_args):
        raise RuntimeError("R07 упал")

    neighbors.configure(problems=lambda g: neighbors.no_data("heat_unavailable"))
    page = call(svc, "GET", "/yards/yard-1454082638")["body"]
    assert page["problems"]["status"] == "no_data" and page["counts"]["problems"] is None
    assert page["initiatives"]["status"] == "ok"


def test_yard_limit_three_per_device(svc):
    for yid in ("yard-1454082638", "yard-1461758835", "yard-1424189376"):
        assert call(svc, "POST", f"/yards/{yid}/join", {}, context=ctx(DEV_A))["status"] == 200
    r = call(svc, "POST", "/yards/yard-1148721825/join", {}, context=ctx(DEV_A))
    assert r["status"] == 429 and r["body"]["error"] == "too_many_yards"


def test_captain_display_name_after_review_and_one_tap_removal(svc):
    yid = "yard-1454082638"
    assert call(svc, "POST", f"/yards/{yid}/captain", {"display_name": "Айгуль"}, context=ctx(DEV_A))["status"] == 409
    call(svc, "POST", f"/yards/{yid}/join", {}, context=ctx(DEV_A))
    assert call(svc, "POST", f"/yards/{yid}/captain", {"display_name": "Айгуль 8 701 123 45 67"},
                context=ctx(DEV_A))["status"] == 422
    r = call(svc, "POST", f"/yards/{yid}/captain", {"display_name": "Айгуль"}, context=ctx(DEV_A))
    assert r["body"]["captain_status"] == "on_review"
    assert call(svc, "GET", f"/yards/{yid}")["body"]["yard"]["captain"] is None
    call(svc, "POST", f"/yards/{yid}/moderate", {"action": "publish"}, principal=Staff(), context=ctx(csrf="csrf-ok"))
    assert call(svc, "GET", f"/yards/{yid}")["body"]["yard"]["captain"]["display_name"] == "Айгуль"
    call(svc, "POST", f"/yards/{yid}/captain", {"remove": True}, context=ctx(DEV_A))
    assert call(svc, "GET", f"/yards/{yid}")["body"]["yard"]["captain"] is None


# --------------------------------------------------------------------------- лента (R06) и сводка (R08)
def test_updates_for_joined_member_and_author(svc, clock):
    iid = SCENE["initiative"]
    call(svc, "POST", f"/initiatives/{iid}/join", {}, context=ctx(DEV_A))
    call(svc, "POST", "/yards/yard-1454082638/join", {}, context=ctx(DEV_B))
    since = iso(clock())
    clock.state["now"] += timedelta(minutes=5)
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    call(svc, "POST", f"/initiatives/{iid}/support", {"note": "Мешки и вывоз в 14:00"}, **staff)
    clock.state["now"] += timedelta(minutes=5)
    call(svc, "POST", f"/initiatives/{iid}/report", {"text": "Убрали двор и вывезли мешки."}, **staff)
    a = updates(DEV_A, since)
    assert [e["kind"] for e in a] == ["initiative.update", "initiative.update"]
    assert a[0]["title_ru"].startswith("Сделано вместе") and "15 соседей" in a[0]["title_ru"]
    assert a[0]["title_kk"].startswith("Бірге жасалды") and a[0]["link"] == "#together/" + iid
    assert a[0]["module"] == "R16" and set(a[0]) >= {"id", "at", "module", "kind", "target", "title_ru", "title_kk", "link"}
    b = updates(DEV_B, since)
    assert {e["kind"] for e in b} == {"yard.news"} and len(b) == 2
    assert b[0]["target"] == {"kind": "area", "id": "yard-1454082638"}
    route = call(svc, "GET", "/updates", context=ctx(DEV_B), query="since=" + quote(since))["body"]
    assert call(svc, "GET", "/updates", context=ctx(DEV_B), query="since=" + since)["status"] == 200  # «+» без кодирования
    assert len(route["items"]) == 2 and route["yards"] == ["yard-1454082638"]
    assert call(svc, "GET", "/updates")["status"] == 400
    assert call(svc, "GET", "/updates", context=ctx(DEV_B), query="since=вчера")["status"] == 400
    assert updates("bad id", None) == []


def test_author_gets_published_and_hidden_events(svc, clock):
    iid = call(svc, "POST", "/initiatives", new_body(), context=ctx(DEV_A))["body"]["initiative"]["id"]
    iid2 = call(svc, "POST", "/initiatives", new_body(title="Второе дело"), context=ctx(DEV_A))["body"]["initiative"]["id"]
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "publish"}, **staff)
    call(svc, "POST", f"/initiatives/{iid2}/moderate", {"action": "hide", "reason": "duplicate"}, **staff)
    titles = [e["title_ru"] for e in updates(DEV_A)]
    assert any(t.startswith("Ваша инициатива опубликована") for t in titles)
    assert any(t.startswith("Инициатива не опубликована") for t in titles)
    mine = call(svc, "GET", "/initiatives", context=ctx(DEV_A), query="view=mine")["body"]["items"]
    assert {i["id"]: i.get("hide_reason") for i in mine}[iid2] == "duplicate"


def test_summary_numbers_are_counted_by_code(svc):
    s = initiatives_summary("nura")
    assert s["status"] == "ok" and s["upcoming"] == 4 and s["done"] == 2
    assert s["joined_upcoming"] == 14 + 9 + 6 + 5 and s["neighbors_done"] == 11 + 15


# --------------------------------------------------------------------------- похожие, идея -> инициатива
def test_similar_nearby_same_kind(svc):
    q = "similar=1&lon=71.3972&lat=51.1349&kind=cleanup&title=Субботник"
    items = call(svc, "GET", "/initiatives", query=q)["body"]["items"]
    assert [i["id"] for i in items] == [SCENE["initiative"]] and items[0]["distance_m"] < 100
    assert call(svc, "GET", "/initiatives", query="similar=1&lon=71.3972&lat=51.1349&kind=snow")["body"]["items"] == []
    assert call(svc, "GET", "/initiatives", query="similar=1&lon=10&lat=10")["status"] == 400


def test_idea_to_initiative(svc):
    idea = {"id": "idea-demo-7", "lang": "ru", "title_ru": "Цветник у площадки", "description_ru": "Посадим цветы.",
            "geometry": {"type": "Point", "coordinates": [71.397, 51.1348]}, "object": {"kind": "square"}}
    item = create_from_idea(idea)
    assert item["status"] == "published" and item["from_idea"] == "idea-demo-7" and item["kind"] == "greening"
    assert item["support"]["by_akimat"] is True and item["target"]["id"] == "yard-1454082638"
    assert create_from_idea(idea)["id"] == item["id"]
    with pytest.raises(ValueError):
        create_from_idea({"id": "idea-x"})


# --------------------------------------------------------------------------- демо-набор и демо-мир R02
def test_demo_rows_scene_and_format():
    now = datetime(2026, 10, 15, 12, 0, tzinfo=ASTANA)
    yards, items = demo_rows(now)
    by_id = {i["id"]: i for i in items}
    scene = by_id[SCENE["initiative"]]
    assert scene["joined"] == 14 and scene["status"] == "published" and scene["support"] is None
    assert scene["starts_at"] == "2026-10-17T10:00:00+05:00"      # ближайшая суббота, 10:00
    assert 8 <= len(items) <= 12 and all(i["demo"] for i in items) and all(y["demo"] for y in yards)
    assert {i["status"] for i in items} >= {"published", "done", "on_review"}
    for item in items:
        assert item["kind"] in ("cleanup", "greening", "snow", "repair", "help", "other")
        assert item["target"]["id"].startswith("yard-") and item["district"]
        assert 71.1 < item["point"][0] < 71.6 and 51.0 < item["point"][1] < 51.3
    assert next_weekday(datetime(2026, 10, 17, 9, 0, tzinfo=ASTANA), 5, 10).day == 24   # «через час» — слишком рано


def test_seed_world_relative_times_and_reset(tmp_path):
    db = tmp_path / "w.sqlite3"
    world = {"yards": [{"id": "yard-1454082638", "label_ru": "Двор: GreenLine.Asyl Mura", "district": "nura",
                        "point": [71.3970633, 51.1348358], "members": 41,
                        "captain": {"display_name": "Айгуль", "since": {"ago_days": 40}}}],
             "initiatives": [{"id": "i-world-1", "kind": "cleanup", "title": "Субботник во дворе", "text": "…",
                              "target": {"kind": "area", "id": "yard-1454082638"}, "point": [71.397, 51.1348],
                              "district": "nura", "status": "published", "joined": 14, "ago_days": 2,
                              "starts_at": {"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}},
                              "ends_at": {"next_weekday": {"weekday": 5, "hour": 13, "minute": 0}}, "bring": ["перчатки"]},
                             {"id": "i-world-2", "kind": "greening", "title": "Посадили деревья", "point": [71.405, 51.122],
                              "status": "done", "joined": 15, "starts_at": {"day_at": {"day": -26, "hour": 10, "minute": 0}},
                              "done_at": {"ago_days": 5}, "report": {"text": "Посадили 6 саженцев", "joined": 15}}]}
    now = datetime(2026, 10, 15, 12, 0, tzinfo=ASTANA)
    first = seed_world(db, world, now=now)
    assert first == {"inserted": 3, "skipped": 0, "reset": 0, "source": "world"}
    svc = make_service(db, demo=False)
    item = svc.store.get("i-world-1")
    assert item["starts_at"] == "2026-10-17T10:00:00+05:00" and item["ends_at"] == "2026-10-17T13:00:00+05:00"
    assert item["joined"] == 14
    assert svc.store.get("i-world-2")["starts_at"] == "2026-09-19T10:00:00+05:00"
    yard = svc.store.yard("yard-1454082638")
    assert yard["members"] == 41 and yard["captain_name"] == "Айгуль" and yard["captain_status"] == "published"
    # Показ: житель пришёл и вступил, акимат отметил «сделано» — повторный засев (новый день) возвращает сцену.
    svc.store.join("i-world-1", DEV_A)
    svc.store.join_yard("yard-1454082638", DEV_A)
    svc.store.report("i-world-1", text="Убрали двор.", text_public=None, moderation=None, by_role="staff", publish=True)
    assert svc.store.get("i-world-1")["status"] == "done"
    later = datetime(2026, 10, 18, 12, 0, tzinfo=ASTANA)
    again = seed_world(db, world, now=later)
    assert again == {"inserted": 0, "skipped": 0, "reset": 3, "source": "world"}
    item = svc.store.get("i-world-1")
    assert item["status"] == "published" and item["joined"] == 14 and item["report"] is None
    assert item["starts_at"] == "2026-10-24T10:00:00+05:00"      # следующая суббота от нового «сейчас»
    assert svc.store.yard("yard-1454082638")["members"] == 41
    empty = seed_world(tmp_path / "e.sqlite3", {"complaints": []}, now=now)
    assert empty["source"] == "fixture" and empty["inserted"] > 0


def test_demo_reseed_resets_demo_but_never_resident_records(tmp_path, clock):
    db = tmp_path / "d.sqlite3"
    svc = make_service(db, clock=clock, demo=True)
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    call(svc, "POST", "/initiatives/i-demo-review-flowers/moderate", {"action": "hide", "reason": "other"}, **staff)
    call(svc, "POST", f"/initiatives/{SCENE['initiative']}/join", {}, context=ctx(DEV_A))
    own = call(svc, "POST", "/initiatives", new_body(), context=ctx(DEV_B))["body"]["initiative"]["id"]
    again = make_service(db, clock=clock, demo=True)       # перезапуск сервера с CIVIC_DEMO=1
    assert again.store.get("i-demo-review-flowers")["status"] == "on_review"   # демо — снова как в наборе
    assert again.store.get(SCENE["initiative"])["joined"] == 14
    assert again.store.get(own)["status"] == "on_review"                      # запись жителя на месте
    assert len(again.store.list(statuses=("published", "done"))) == 7


def test_unknown_routes_and_methods(svc):
    assert call(svc, "GET", "/nothing")["status"] == 404
    assert call(svc, "DELETE", "/initiatives")["status"] == 405
    assert call(svc, "PUT", "/initiatives/" + SCENE["initiative"])["status"] == 404
    assert svc.handle("GET", "/api/civic/v2/other", "", None, None, ctx())["status"] == 404


def test_pickups_for_waste_service(svc):
    assert pickups() == []
    call(svc, "POST", f"/initiatives/{SCENE['initiative']}/support", {"inventory": True, "pickup_service": "waste",
                                                                     "note": "Мешки и вывоз в 14:00"},
         principal=Staff(), context=ctx(csrf="csrf-ok"))
    rows = pickups("nura")
    assert [r["initiative_id"] for r in rows] == [SCENE["initiative"]]
    assert rows[0]["service"] == "waste" and rows[0]["note"] == "Мешки и вывоз в 14:00"
    assert "device" not in json.dumps(rows, ensure_ascii=False)


# --------------------------------------------------------------------------- находки R15 (S45–S47)
def test_r15_s47_bring_items_are_moderated(svc):
    body = new_body(bring=["перчатки", "звоните 8 701 123 45 67", "почта a.b@example.com"])
    r = call(svc, "POST", "/initiatives", body, context=ctx(DEV_A))
    iid = r["body"]["initiative"]["id"]
    assert {"phone", "email"} <= set(r["body"]["hints"])
    staff = call(svc, "GET", "/initiatives", principal=Staff(), query="view=staff&tab=queue")["body"]
    assert {"phone", "email"} <= set(next(i for i in staff["items"] if i["id"] == iid)["flags"])
    call(svc, "POST", f"/initiatives/{iid}/moderate", {"action": "publish"}, principal=Staff(), context=ctx(csrf="csrf-ok"))
    public = call(svc, "GET", "/initiatives/" + iid, context=ctx(DEV_B))["body"]["initiative"]
    text = json.dumps(public["bring"], ensure_ascii=False)
    assert "701" not in text and "example.com" not in text and "***" in text


@pytest.mark.parametrize("raw", ["ИИН 900101 300 125", "ИИН 900101-300-125", "мой 701 123 45 67", "(701) 123-45-67"])
def test_r15_s46_fallback_catches_spaced_iin_and_bare_mobile(raw):
    from ui.civic_together import moderation
    checked = moderation.local_check(raw)
    assert checked["flags"] and "***" in checked["text_public"]


def test_r15_s45_public_point_is_rounded_to_4_digits(svc):
    item = call(svc, "GET", "/initiatives/" + SCENE["initiative"])["body"]["initiative"]
    assert all(len(str(v).split(".")[1]) <= 4 for v in item["point"])


def test_staff_tabs_waiting_and_going(svc):
    staff = dict(principal=Staff(), context=ctx(csrf="csrf-ok"))
    waiting = call(svc, "GET", "/initiatives", query="view=staff&tab=waiting", **staff)["body"]
    going = call(svc, "GET", "/initiatives", query="view=staff&tab=going", **staff)["body"]
    assert SCENE["initiative"] in [i["id"] for i in waiting["items"]]
    assert all(not (i["support"] or {}).get("by_akimat") for i in waiting["items"])
    assert all(i["support"]["by_akimat"] for i in going["items"]) and going["items"]
    assert waiting["counts"]["waiting"] == len(waiting["items"]) and waiting["counts"]["going"] == len(going["items"])
    call(svc, "POST", f"/initiatives/{SCENE['initiative']}/support", {"note": "Мешки"}, **staff)
    going2 = call(svc, "GET", "/initiatives", query="view=staff&tab=going", **staff)["body"]
    assert SCENE["initiative"] in [i["id"] for i in going2["items"]]


def test_scene_yard_first_in_yard_list(svc):
    items = call(svc, "GET", "/yards")["body"]["items"]
    assert items[0]["id"] == SCENE["yard"]
