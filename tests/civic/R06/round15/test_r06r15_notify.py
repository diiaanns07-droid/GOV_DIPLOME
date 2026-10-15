"""R06 раунд 15, задача 3: лента «Что нового для меня» (CONTRACT §5.8, §7) и задача 4: идея → инициатива R16.

Соседи (R09, R16, R17, R13) подменяются фикстурами-модулями: проверяем сборку, нормализацию (только поля §5.8,
только внутренние ссылки), пропуск отсутствующего и упавшего соседа, прочитанное и приватность (чужие события и id
устройств наружу не уходят). Свои события R06 — настоящие: идеи, проекты, работы рядом.
"""

from __future__ import annotations

import types

import pytest

from r06r14_helpers import NURA_POINT, call, context, device, make_service
from ui.civic_store import notify as notify_mod
from ui.civic_store import v2 as v2mod

ALL_YES = {"land": "yes", "networks": "yes", "access": "yes", "maintenance": "yes"}
DEV_A, DEV_B = device(1), device(2)                 # id голосов/идей R06 (birge.device_id)
MAIN_A, MAIN_B = "resident-main-aaaaaaaaaaaa", "resident-main-bbbbbbbbbbbb"   # основной id (birge.device)


def new_idea(v2, n=1, title="Скамейки во дворе"):
    body = {"title": title, "description": "Нужны скамейки.", "geometry": {"type": "Point", "coordinates": NURA_POINT},
            "device_id": device(n), "lang": "ru"}
    result = call(v2, "POST", "/ideas", body, ctx=context(client_ip=f"10.0.0.{n}"))
    assert result["status"] == 201, result
    return result["body"]["data"]["item"]


def decide(staff, idea_id, **body):
    result = staff.call("POST", f"/ideas/{idea_id}/decide", body)
    assert result["status"] == 200, result
    return result["body"]["data"]


def feed(v2, main, ideas=None, since=None, **ctx):
    headers = {"X-Birge-Device": main}
    if ideas:
        headers["X-Birge-Ideas-Device"] = ideas
    c = context(**ctx)
    c["headers"].update(headers)
    query = f"since={since}" if since else None
    return call(v2, "GET", "/notifications", query=query, ctx=c)


def items(result):
    assert result["status"] == 200, result
    return result["body"]["data"]["items"]


@pytest.fixture
def no_neighbors(stack, monkeypatch):
    """Лента только из своих событий R06: соседи «не поставлены» (их модулей нет)."""
    svc, v2 = stack

    def importer(name):
        if name.startswith(("ui.civic_together", "ui.civic_agencies", "ui.civic_meetings", "ui.civic_feedback",
                            "ui.civic_akim", "engine.civic_geo")):
            raise ModuleNotFoundError(name=name)
        raise AssertionError(name)
    v2.notify = notify_mod.NotificationCenter(v2, importer=importer)
    return v2


# --- свои события R06: идеи и проекты --------------------------------------------------------------------------

def test_author_and_supporter_see_their_idea_events(stack, staff, no_neighbors):
    svc, v2 = stack
    idea = new_idea(v2, 1)
    assert items(feed(v2, MAIN_A, DEV_A)) == []                       # создание — не новость
    decide(staff, idea["id"], action="publish")
    call(v2, "POST", f"/ideas/{idea['id']}/support", {"device_id": DEV_B, "on": True}, ctx=context(client_ip="10.0.0.9"))
    v2.notify._cache.clear()
    a = items(feed(v2, MAIN_A, DEV_A))
    assert [e["kind"] for e in a] == ["idea.update"] and "опубликована" in a[0]["title_ru"]
    assert a[0]["link"] == "#ideas/" + idea["id"] and a[0]["module"] == "R06" and a[0]["read"] is False
    assert "жарияланды" in a[0]["title_kk"]
    assert items(feed(v2, MAIN_B, DEV_B)) == []                       # поддержавшему — только итог
    staff.clock = svc.clock
    svc.clock.advance(minutes=5)
    decide(staff, idea["id"], action="check", check=ALL_YES)
    svc.clock.advance(minutes=5)
    decide(staff, idea["id"], action="reject", reason="Нет места на участке")
    v2.notify._cache.clear()
    a = items(feed(v2, MAIN_A, DEV_A))
    assert [e["title_ru"].split("«")[0].strip() for e in a][:1] == ["Идея"]   # новые сверху: отказ
    assert "отклонена" in a[0]["title_ru"] and len(a) == 3                   # отказ, проверка, публикация
    b = items(feed(v2, MAIN_B, DEV_B))
    assert len(b) == 1 and "поддержали, отклонена" in b[0]["title_ru"]
    # без X-Birge-Ideas-Device свои события ищутся по основному id — у MAIN_A своих идей нет
    assert items(feed(v2, MAIN_A)) == []


def test_project_voter_gets_decision(stack, staff, no_neighbors):
    svc, v2 = stack
    project = staff.create_proposal()
    vote = call(v2, "POST", f"/proposals/{project['id']}/vote", {"value": 1, "device_id": DEV_A})
    assert vote["status"] == 200, vote
    svc.clock.advance(minutes=10)
    assert staff.call("POST", f"/proposals/{project['id']}/approve", {})["status"] == 200
    v2.notify._cache.clear()
    a = items(feed(v2, MAIN_A, DEV_A))
    assert [e["kind"] for e in a] == ["project.update"] and "одобрен" in a[0]["title_ru"]
    assert a[0]["target"] == {"kind": "project", "id": project["id"]}
    assert items(feed(v2, MAIN_B, DEV_B)) == []                        # не голосовал — не новость


# --- соседи --------------------------------------------------------------------------------------------------

def neighbor(events=None, *, error=None, signature="db_path"):
    if signature == "db":
        def updates(device, since=None, db=None):
            if error:
                raise error
            return [dict(e) for e in events]
    elif signature == "plain":
        def updates(device, since=None):
            if error:
                raise error
            return [dict(e) for e in events]
    else:
        def updates(device, since=None, db_path=None, limit=50):
            if error:
                raise error
            return [dict(e) for e in events]
    return types.SimpleNamespace(updates=updates)


def center_with(v2, modules):
    def importer(name):
        if name in modules:
            return modules[name]
        raise ModuleNotFoundError(name=name)
    return notify_mod.NotificationCenter(v2, importer=importer)


EV_YARD = {"id": "tg-1", "at": "2026-10-11T09:30:00+05:00", "module": "R16", "kind": "yard.news",
           "target": {"kind": "area", "id": "yard-1"}, "title_ru": "Соседка создала «Субботник в субботу, 10:00»",
           "title_kk": "Көрші «Сенбілік» құрды", "link": "#together/i-7", "demo": True,
           "author_device": "secret-device-id-123", "text_private": "телефон 8 701 000 00 00"}
EV_CRISIS = {"id": "incident.u-1", "at": "2026-10-11T08:00:00+00:00", "module": "R17", "kind": "incident.update",
             "target": {"kind": "district", "id": "nura"}, "title_ru": "Буран: работают 4 службы",
             "title_kk": "Боран: 4 қызмет жұмыс істейді", "link": "#incident=inc-1"}


def test_neighbors_are_merged_normalized_and_skipped_when_absent(stack):
    svc, v2 = stack
    bad = [{"id": "x1", "at": "2026-10-11T07:00:00+00:00", "kind": "meeting.result", "title_ru": "Ссылка наружу",
            "link": "javascript:alert(1)"},
           {"id": "x2", "at": "вчера", "kind": "meeting.result", "title_ru": "Без времени"},
           {"id": "x3", "at": "2026-10-11T07:00:00+00:00", "kind": "meeting.result"}]
    center = center_with(v2, {
        "ui.civic_together": neighbor([EV_YARD]),
        "ui.civic_agencies": neighbor([EV_CRISIS], signature="plain"),
        "ui.civic_meetings": neighbor(bad),
        # R09 — нет модуля
    })
    data = center.collect(MAIN_A, None, DEV_A)
    assert data["sources"] == {"R06": "ok", "R09": "absent", "R16": "ok", "R17": "ok", "R13": "ok"}
    ids = [e["id"] for e in data["items"]]
    assert ids == ["R17:incident.u-1", "R13:x1", "R16:tg-1"]                # новые сверху: 08:00, 07:00, 04:30 UTC
    yard = data["items"][2]
    assert set(yard) == {"id", "at", "module", "kind", "target", "title_ru", "title_kk", "link", "demo", "read"}
    assert yard["at"] == "2026-10-11T04:30:00+00:00"                       # время приведено к UTC
    assert "author_device" not in str(data) and "secret-device" not in str(data) and "телефон" not in str(data)
    assert data["items"][1]["link"] is None                                # javascript: — не ссылка
    assert data["unread"] == 3


def test_failing_neighbor_does_not_break_the_feed(stack):
    svc, v2 = stack
    center = center_with(v2, {"ui.civic_together": neighbor(error=RuntimeError("boom")),
                              "ui.civic_feedback.v2.integration": neighbor([dict(EV_CRISIS, id="r09.e1",
                                                                                 kind="complaint.update",
                                                                                 link="#mine/event=e1")],
                                                                           signature="db")})
    data = center.collect(MAIN_A, None, None)
    assert data["sources"]["R16"] == "error" and data["sources"]["R09"] == "ok"
    assert [e["id"] for e in data["items"]] == ["R09:r09.e1"] and data["items"][0]["link"] == "#mine/event=e1"


def test_read_state_since_and_privacy_between_devices(stack):
    svc, v2 = stack
    v2.notify = center_with(v2, {"ui.civic_together": neighbor([EV_YARD]),
                                 "ui.civic_agencies": neighbor([EV_CRISIS], signature="plain")})
    first = feed(v2, MAIN_A)["body"]["data"]
    assert first["unread"] == 2
    one = call(v2, "POST", "/notifications/read", {"ids": ["R17:incident.u-1"]},
               ctx=dict(context(), headers={"X-Birge-Device": MAIN_A}))
    assert one["status"] == 200, one
    data = feed(v2, MAIN_A)["body"]["data"]
    assert data["unread"] == 1 and [e["read"] for e in data["items"]] == [True, False]   # кризис (08:00) прочитан
    assert feed(v2, MAIN_B)["body"]["data"]["unread"] == 2                  # прочитанное — своё у каждого устройства
    since = feed(v2, MAIN_A, since="2026-10-11T06:00:00Z")["body"]["data"]
    assert [e["id"] for e in since["items"]] == ["R17:incident.u-1"] and since["unread"] == 1  # счётчик — по всей ленте
    everything = call(v2, "POST", "/notifications/read", {"all": True},
                      ctx=dict(context(), headers={"X-Birge-Device": MAIN_A}))
    assert everything["status"] == 200 and everything["body"]["data"]["read_until"]
    assert feed(v2, MAIN_A)["body"]["data"]["unread"] == 0
    with svc.db.read() as conn:                                             # в базе — только хэш устройства
        rows = conn.execute("SELECT device_hash FROM civic_notify_reads").fetchall()
    assert len(rows) == 1 and MAIN_A not in rows[0]["device_hash"] and len(rows[0]["device_hash"]) == 64


@pytest.mark.parametrize("body, field", [
    ({}, "ids"), ({"ids": "R16:tg-1"}, "ids"), ({"ids": [1]}, "ids"), ({"all": "yes"}, "all"),
    ({"until": "вчера"}, "until"), ({"ids": ["a"] * 201}, "ids"), ({"who": "me"}, "who"),
])
def test_bad_read_requests(stack, no_neighbors, body, field):
    svc, v2 = stack
    result = call(v2, "POST", "/notifications/read", body, ctx=dict(context(), headers={"X-Birge-Device": MAIN_A}))
    assert result["status"] == 422 and field in result["body"]["error"]["fields"], result


def test_device_is_required_and_cross_site_write_refused(stack, no_neighbors):
    svc, v2 = stack
    result = call(v2, "GET", "/notifications")
    assert result["status"] == 422 and "device_id" in result["body"]["error"]["fields"]
    bad_since = feed(v2, MAIN_A, since="вчера")
    assert bad_since["status"] == 400
    cross = call(v2, "POST", "/notifications/read", {"all": True},
                 ctx=dict(context(same_origin=False), headers={"X-Birge-Device": MAIN_A}))
    assert cross["status"] == 403
    other_host = call(v2, "GET", "/notifications", ctx=dict(context(host_allowed=False), headers={"X-Birge-Device": MAIN_A}))
    assert other_host["status"] == 403


# --- работы рядом ---------------------------------------------------------------------------------------------

def test_work_near_by_district_subscription_and_yard(stack, staff, monkeypatch):
    svc, v2 = stack
    why = {"problem": "п", "reason": "п", "result": "р", "inconvenience": "н"}
    work = staff.call("POST", "/works", {"type": "work", "status": "in_progress", "district": "nura", "lang": "ru",
                                         "title": "Замена водопровода", "service": "water", "kind": "dig",
                                         "planned_end": "2026-11-20", "why": why,
                                         "geometry": {"type": "Point", "coordinates": [71.3690, 51.1360]}})
    assert work["status"] == 201, work
    wid = work["body"]["data"]["item"]["id"]
    akim = types.SimpleNamespace(subscriptions=lambda d: [{"scope": "district", "id": "nura"}] if d == MAIN_A else [])
    yard_geo = types.SimpleNamespace(target_geometry=lambda t: {"point": [71.3695, 51.1362]} if t["id"] == "yard-7" else None)
    together = types.SimpleNamespace(yards_of_device=lambda d: ["yard-7"] if d == MAIN_B else [])
    v2.notify = center_with(v2, {"ui.civic_akim.nearby": akim, "engine.civic_geo": yard_geo, "ui.civic_together": together})
    a = [e for e in v2.notify.collect(MAIN_A)["items"] if e["kind"] == "work.near"]
    assert len(a) == 1 and a[0]["title_ru"] == "В вашем районе: Замена водопровода" and a[0]["link"] == "#nearby/" + wid
    b = [e for e in v2.notify.collect(MAIN_B)["items"] if e["kind"] == "work.near"]
    assert len(b) == 1 and b[0]["title_ru"].startswith("Рядом с вашим двором") and b[0]["title_kk"].startswith("Аулаңыздың")
    c = [e for e in v2.notify.collect("resident-main-cccccccccccc")["items"] if e["kind"] == "work.near"]
    assert c == []                                                         # без двора и подписки — не шумим


# --- функции для шлюза R01 -------------------------------------------------------------------------------------

def test_gateway_functions(stack, staff, no_neighbors):
    svc, v2 = stack
    v2mod.bind(svc)
    v2mod._BOUND.notify = v2.notify
    idea = new_idea(v2, 1)
    decide(staff, idea["id"], action="publish")
    ctx = dict(context(), headers={"x-birge-device": MAIN_A, "x-birge-ideas-device": DEV_A})   # шлюз: нижний регистр
    data = v2mod.list_notifications(context=ctx)
    assert data["unread"] == 1 and data["items"][0]["kind"] == "idea.update"
    assert v2mod.read_notifications({"all": True}, context=ctx)["read_until"]
    assert v2mod.list_notifications(context=ctx)["unread"] == 0
    with pytest.raises(v2mod.V2Error) as exc:
        v2mod.list_notifications(context=dict(context(), headers={}))
    assert exc.value.status == 422
    with pytest.raises(v2mod.V2Error) as exc:
        v2mod.read_notifications({"all": True}, context=dict(context(same_origin=False), headers={"x-birge-device": MAIN_A}))
    assert exc.value.status == 403


# --- идея → инициатива R16 --------------------------------------------------------------------------------------

def test_idea_to_initiative_with_r16(stack, staff, no_neighbors, monkeypatch):
    svc, v2 = stack
    calls = []

    def create_from_idea(idea, *, starts_at=None, db_path=None, actor="staff"):
        calls.append((idea["id"], idea.get("object"), starts_at, db_path, actor))
        return {"id": "i-r16-0001", "status": "published", "title": idea["title_ru"], "support": {"inventory": True},
                "author_device": "never-leaks"}
    monkeypatch.setattr(v2mod, "together_create", lambda: create_from_idea)
    idea = new_idea(v2, 1, title="Беседка и скамейки")
    review = staff.call("POST", f"/ideas/{idea['id']}/to-initiative", {})
    assert review["status"] == 409                                        # на проверке — нельзя
    decide(staff, idea["id"], action="publish")
    made = staff.call("POST", f"/ideas/{idea['id']}/to-initiative", {"starts_at": "2026-10-17T10:00:00+05:00"})
    assert made["status"] == 201, made
    body = made["body"]["data"]
    assert body["created"] is True and body["initiative"]["id"] == "i-r16-0001"
    assert "author_device" not in body["initiative"]
    assert body["item"]["initiative"]["id"] == "i-r16-0001"
    assert calls[0][1] == {"kind": "benches"}                              # у идеи без объекта — её тема
    assert calls[0][2] == "2026-10-17T10:00:00+05:00" and calls[0][4] == "staff"
    again = staff.call("POST", f"/ideas/{idea['id']}/to-initiative", {})
    assert again["status"] == 201 and again["body"]["data"]["created"] is False and len(calls) == 1
    public = call(v2, "GET", f"/ideas/{idea['id']}")["body"]["data"]["item"]
    assert public["initiative"]["id"] == "i-r16-0001"
    caps = staff.call("GET", "/staff/ideas")["body"]["data"]["capabilities"]
    assert caps == {"to_initiative": True}
    v2.notify._cache.clear()
    events = items(feed(v2, MAIN_A, DEV_A))
    together = [e for e in events if e["link"] == "#together/i-r16-0001"]
    assert len(together) == 1 and "сделаем вместе" in together[0]["title_ru"]
    # без входа — нельзя
    anon = call(v2, "POST", f"/ideas/{idea['id']}/to-initiative", {})
    assert anon["status"] == 401


def test_idea_to_initiative_without_r16_or_with_bad_idea(stack, staff, no_neighbors, monkeypatch):
    svc, v2 = stack
    idea = new_idea(v2, 1)
    decide(staff, idea["id"], action="publish")
    monkeypatch.setattr(v2mod, "together_create", lambda: None)
    missing = staff.call("POST", f"/ideas/{idea['id']}/to-initiative", {})
    assert missing["status"] == 503 and missing["body"]["error"]["code"] == "module_not_ready"
    assert staff.call("GET", "/staff/ideas")["body"]["data"]["capabilities"] == {"to_initiative": False}

    def refuses(idea, **kw):
        raise ValueError("idea: у идеи нет места на карте")
    monkeypatch.setattr(v2mod, "together_create", lambda: refuses)
    bad = staff.call("POST", f"/ideas/{idea['id']}/to-initiative", {})
    assert bad["status"] == 422 and "места" in bad["body"]["error"]["fields"]["idea"]
    assert staff.call("POST", f"/ideas/{idea['id']}/to-initiative", {"when": "завтра"})["status"] == 422
    with svc.db.read() as conn:
        assert conn.execute("SELECT initiative_id FROM civic_ideas WHERE id = ?", (idea["id"],)).fetchone()[0] is None
