"""R06 волна 2 п. 7: идеи жителей → поддержка → проект или отказ с причиной (R11 IA_WAVE2 §8).

Путь: житель присылает идею (на проверке, видна только ему) → сотрудник публикует → соседи поддерживают (одна
поддержка с устройства) → сотрудник проверяет реализуемость (4 строки) и делает проект «По идее жителей · N голосов»
или отказывает с причиной и «Можно доработать». Всё переживает перезапуск сервера.
"""

import pytest

from r06r14_helpers import NURA_POINT, call, context, device, make_service
from ui.civic_store import v2 as v2mod


def idea_body(n=1, **over):
    body = {"title": "Сквер у дома", "description": "Нужны деревья и скамейки.",
            "geometry": {"type": "Point", "coordinates": NURA_POINT}, "device_id": device(n), "lang": "ru"}
    body.update(over)
    return body


def new_idea(v2, n=1, ip="10.0.0.1", **over):
    result = call(v2, "POST", "/ideas", idea_body(n, **over), ctx=context(client_ip=ip))
    assert result["status"] == 201, result
    return result["body"]["data"]["item"]


def public_ids(v2, dev=None):
    query = f"device_id={dev}" if dev else None
    return [i["id"] for i in call(v2, "GET", "/ideas", query=query)["body"]["data"]["items"]]


def decide(staff, idea_id, **body):
    return staff.call("POST", f"/ideas/{idea_id}/decide", body)


def support(v2, idea_id, n, on=True, ip="10.0.0.2"):
    return call(v2, "POST", f"/ideas/{idea_id}/support", {"device_id": device(n), "on": on}, ctx=context(client_ip=ip))


# --- житель: новая идея --------------------------------------------------------------------

def test_new_idea_waits_for_review_and_only_its_author_sees_it(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    assert item["status"] == "review" and item["mine"] is True and item["votes"] == 0
    assert item["title"] == "Сквер у дома" and item["district"] == "nura"
    assert item["id"] not in public_ids(v2)                       # чужим не видно
    assert item["id"] not in public_ids(v2, device(2))
    assert item["id"] in public_ids(v2, device(1))                # автору — видно («на проверке»)
    assert call(v2, "GET", f"/ideas/{item['id']}")["status"] == 404
    staff_list = staff.call("GET", "/staff/ideas")["body"]["data"]
    assert [i["id"] for i in staff_list["items"]] == [item["id"]] and staff_list["counts"]["review"] == 1


def test_device_id_is_stored_only_as_hash(stack):
    svc, v2 = stack
    new_idea(v2)
    with svc.db.read() as conn:
        row = conn.execute("SELECT * FROM civic_ideas").fetchone()
        dump = " ".join(str(row[k]) for k in row.keys())
    assert device(1) not in dump and len(row["author_hash"]) == 64


@pytest.mark.parametrize("over, field", [
    ({"title": None}, "title"),
    ({"title": "ab"}, "title"),
    ({"title": "x" * 61}, "title"),
    ({"title": "<b>Сквер</b>"}, "title"),
    ({"description": "y" * 301}, "description"),
    ({"geometry": None}, "geometry"),
    ({"geometry": {"type": "Point", "coordinates": [76.9, 43.2]}}, "geometry"),          # Алматы, не Астана
    ({"geometry": {"type": "LineString", "coordinates": [NURA_POINT, [71.351, 51.131]]}}, "geometry"),
    ({"object": {"kind": "fountain"}}, "object.kind"),
    ({"object": {"kind": "square", "geometry": {"type": "Point", "coordinates": [76.9, 43.2]}}}, "object.geometry"),
    ({"device_id": "x"}, "device_id"),
    ({"lang": "en"}, "lang"),
    ({"author": "Айгерим"}, "author"),
])
def test_bad_idea_is_refused_with_the_field(stack, over, field):
    svc, v2 = stack
    result = call(v2, "POST", "/ideas", idea_body(**over))
    assert result["status"] == 422, result
    fields = result["body"]["error"]["fields"]
    assert any(name == field or name.startswith(field + ".") for name in fields), fields


def test_idea_from_another_site_or_host_is_refused(stack):
    svc, v2 = stack
    assert call(v2, "POST", "/ideas", idea_body(), ctx=context(same_origin=False))["status"] == 403
    assert call(v2, "POST", "/ideas", idea_body(), ctx=context(host_allowed=False))["status"] == 403


def test_idea_flood_is_limited_per_address_and_per_device(stack):
    svc, v2 = stack
    for n in range(3):
        new_idea(v2, n=1)
    result = call(v2, "POST", "/ideas", idea_body(1), ctx=context(client_ip="10.0.0.1"))
    assert result["status"] == 409 and result["body"]["error"]["code"] == "limit"   # у устройства уже 3 на проверке
    new_idea(v2, n=2)
    new_idea(v2, n=3)
    result = call(v2, "POST", "/ideas", idea_body(4), ctx=context(client_ip="10.0.0.1"))
    assert result["status"] == 429 and "Retry-After" in result["headers"]          # 5 в час с одного адреса
    assert call(v2, "POST", "/ideas", idea_body(4), ctx=context(client_ip="10.0.0.9"))["status"] == 201


# --- поддержка ------------------------------------------------------------------------------

def test_support_is_one_per_device_toggles_and_survives_restart(stack, staff, db_path, clock):
    svc, v2 = stack
    item = new_idea(v2)
    assert support(v2, item["id"], 2)["status"] == 409                          # на проверке — голосовать нельзя
    assert decide(staff, item["id"], action="publish")["status"] == 200
    first = support(v2, item["id"], 2)["body"]["data"]
    assert first["changed"] is True and first["item"]["votes"] == 1 and first["item"]["my_support"] is True
    again = support(v2, item["id"], 2)["body"]["data"]
    assert again["changed"] is False and again["item"]["votes"] == 1             # повтор не удваивает
    assert support(v2, item["id"], 3)["body"]["data"]["item"]["votes"] == 2
    off = support(v2, item["id"], 3, on=False)["body"]["data"]
    assert off["changed"] is True and off["item"]["votes"] == 1 and off["item"]["my_support"] is False
    _, v2b = make_service(db_path, clock)                                        # перезапуск сервера
    got = call(v2b, "GET", f"/ideas/{item['id']}", query=f"device_id={device(2)}")["body"]["data"]["item"]
    assert got["votes"] == 1 and got["my_support"] is True and got["status"] == "voting"


def test_support_from_one_address_is_limited_per_idea_per_day(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    decide(staff, item["id"], action="publish")
    for n in range(20):
        assert support(v2, item["id"], 100 + n, ip="10.1.1.1")["status"] == 200
    result = support(v2, item["id"], 200, ip="10.1.1.1")
    assert result["status"] == 429 and "завтра" in result["body"]["error"]["message"]
    assert support(v2, item["id"], 200, ip="10.1.1.2")["status"] == 200


def test_support_needs_device_and_same_site(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    decide(staff, item["id"], action="publish")
    bad = call(v2, "POST", f"/ideas/{item['id']}/support", {"device_id": "x", "on": True})
    assert bad["status"] == 422
    cross = call(v2, "POST", f"/ideas/{item['id']}/support", {"device_id": device(2)}, ctx=context(same_origin=False))
    assert cross["status"] == 403


# --- сотрудник: проверка, проект, отказ -----------------------------------------------------

def test_staff_actions_need_session_and_csrf(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    assert call(v2, "GET", "/staff/ideas")["status"] == 401
    no_csrf = call(v2, "POST", f"/ideas/{item['id']}/decide", {"action": "publish"}, ctx=context(staff.cookie))
    assert no_csrf["status"] == 403
    with pytest.raises(v2mod.V2Error) as err:   # функции для шлюза R01 проверяют сессию сами (R15-S17)
        v2mod.bind(svc)
        v2mod.decide_idea(item["id"], {"action": "publish"}, context=context(staff.cookie))
    assert err.value.status in (401, 403)


def test_reject_needs_a_reason_and_shows_it_with_can_improve(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    decide(staff, item["id"], action="publish")
    support(v2, item["id"], 2)
    assert decide(staff, item["id"], action="reject")["status"] == 422
    check = {"land": "yes", "networks": "no", "access": "yes", "maintenance": "unknown"}
    result = decide(staff, item["id"], action="reject", reason="Нет водопровода на участке",
                    can_improve="Предложите место у сквера", check=check)
    assert result["status"] == 200, result
    got = call(v2, "GET", f"/ideas/{item['id']}")["body"]["data"]["item"]
    assert got["status"] == "rejected" and got["reason"] == "Нет водопровода на участке"
    assert got["reason_kk"] == got["reason"] and got["can_improve"] == "Предложите место у сквера"
    assert got["check"] == check and got["votes_at_decision"] == 1
    assert support(v2, item["id"], 3)["status"] == 409                         # голосование закрыто
    assert decide(staff, item["id"], action="publish")["status"] == 409         # решение уже принято


def test_checklist_is_private_until_decision(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    decide(staff, item["id"], action="publish")
    check = {"land": "yes", "networks": "yes", "access": "unknown", "maintenance": "yes"}
    assert decide(staff, item["id"], action="check", check=check)["status"] == 200
    assert call(v2, "GET", f"/ideas/{item['id']}")["body"]["data"]["item"]["check"] is None
    staff_item = staff.call("GET", "/staff/ideas")["body"]["data"]["items"][0]
    assert staff_item["check"] == check
    bad = decide(staff, item["id"], action="check", check={"land": "maybe"})
    assert bad["status"] == 422


def test_idea_becomes_project_by_residents_and_back_when_project_removed(stack, staff):
    svc, v2 = stack
    item = new_idea(v2, object={"kind": "square", "rotation_deg": 30})
    decide(staff, item["id"], action="publish")
    for n in (2, 3, 4):
        support(v2, item["id"], n)
    result = decide(staff, item["id"], action="project", near_street="улица Сыганак")
    assert result["status"] == 200, result
    data = result["body"]["data"]
    project = data["proposal"]
    assert data["item"]["status"] == "project" and data["item"]["project"]["id"] == project["id"]
    assert project["kind"] == "square" and project["status"] == "proposal" and project["rotation_deg"] == 30
    assert project["idea"] == {"id": item["id"], "votes": 3}                  # «По идее жителей · 3 голоса»
    assert project["title_ru"] == "Сквер у улицы Сыганак" and project["title_kk"] == "Гүлзар · Сыганак көшесі маңында"
    listed = call(v2, "GET", "/proposals")["body"]["data"]["items"]
    assert [p["idea"] for p in listed if p["id"] == project["id"]] == [{"id": item["id"], "votes": 3}]
    # «Удалить» проект в 3D (R05) — идея снова на голосовании; «Отменить» — снова проект, голоса целы.
    assert staff.call("DELETE", f"/proposals/{project['id']}")["status"] == 200
    assert call(v2, "GET", f"/ideas/{item['id']}")["body"]["data"]["item"]["status"] == "voting"
    restored = staff.call("POST", "/proposals", {"id": project["id"], "kind": "square",
                                                 "geometry": project["geometry"]})
    assert restored["status"] == 201 and restored["body"]["data"]["restored"] is True
    again = call(v2, "GET", f"/ideas/{item['id']}")["body"]["data"]["item"]
    assert again["status"] == "project" and again["votes"] == 3
    with svc.db.read() as conn:
        actions = [r["action"] for r in conn.execute(
            "SELECT action FROM civic_idea_history WHERE idea_id = ? ORDER BY id", (item["id"],))]
    assert actions == ["create", "publish", "project", "reopen", "project"]


def test_project_needs_a_catalog_kind_and_lighting_needs_a_street_line(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    decide(staff, item["id"], action="publish")
    assert decide(staff, item["id"], action="project")["body"]["error"]["fields"].keys() == {"kind"}
    assert "geometry" in decide(staff, item["id"], action="project", kind="lighting")["body"]["error"]["fields"]
    line = {"type": "LineString", "coordinates": [NURA_POINT, [71.3503, 51.1302]]}
    ok = decide(staff, item["id"], action="project", kind="lighting", geometry=line)
    assert ok["status"] == 200 and ok["body"]["data"]["proposal"]["kind"] == "lighting"


def test_hidden_idea_is_gone_for_others_and_author_sees_no_staff_reason(stack, staff):
    svc, v2 = stack
    item = new_idea(v2)
    assert decide(staff, item["id"], action="hide")["status"] == 422           # причина обязательна (служебная)
    assert decide(staff, item["id"], action="hide", reason="Телефон в тексте")["status"] == 200
    assert item["id"] not in public_ids(v2)
    mine = call(v2, "GET", "/ideas", query=f"device_id={device(1)}")["body"]["data"]["items"]
    assert [(i["status"], i["reason"]) for i in mine] == [("hidden", "")]


def test_public_list_filters_and_counts(stack, staff):
    svc, v2 = stack
    a, b, c = new_idea(v2, 1), new_idea(v2, 2), new_idea(v2, 3)
    for i in (a, b, c):
        decide(staff, i["id"], action="publish")
    decide(staff, c["id"], action="reject", reason="Нет места")
    support(v2, b["id"], 9)
    data = call(v2, "GET", "/ideas", query="status=voting")["body"]["data"]
    assert [i["id"] for i in data["items"]] == [b["id"], a["id"]]               # больше голосов — выше
    assert data["counts"] == {"voting": 2}
    assert call(v2, "GET", "/ideas", query="status=review")["status"] == 400   # на проверке — не публично
    assert call(v2, "GET", "/ideas", query="district=mars")["status"] == 400


def test_gateway_functions_follow_contract(stack, staff):
    svc, v2 = stack
    v2mod.bind(svc)
    status, created = v2mod.create_idea(idea_body(5), context=context(client_ip="10.9.9.9"))
    assert status == 201 and created["item"]["status"] == "review"
    with pytest.raises(v2mod.V2Error) as err:
        v2mod.create_idea(idea_body(5, title=""), context=context())
    assert err.value.status == 422 and "title" in err.value.fields
    with pytest.raises(v2mod.V2Error) as err:
        v2mod.create_idea(idea_body(6), context=context(same_origin=False))
    assert err.value.status == 403
    listed = v2mod.list_ideas_staff(context=staff.ctx())
    assert [i["id"] for i in listed["items"]] == [created["item"]["id"]]
    v2mod.decide_idea(created["item"]["id"], {"action": "publish"}, context=staff.ctx())
    supported = v2mod.support_idea(created["item"]["id"], {"device_id": device(7), "on": True}, context=context())
    assert supported["item"]["votes"] == 1
    assert v2mod.list_ideas(status="voting")["items"][0]["votes"] == 1
    assert v2mod.ideas_summary()["counts"]["voting"] == 1
