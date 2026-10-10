"""R09 раунд 14: HTTP-слой /api/civic/v2 — конверт, права, приватность, ошибки."""

import json

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service

P = "/api/civic/v2"
DEV_A = "dev-aaaaaaaaaaaaaaaa"
DEV_B = "dev-bbbbbbbbbbbbbbbb"
STOP = {"kind": "object", "id": "osm-node-123456", "label_ru": "Остановка «Нура»"}


class Staff:
    is_staff = True
    username = "operator1"

    def __init__(self, csrf="tok"):
        self.csrf = csrf

    def check_csrf(self, value):
        return value == self.csrf


def ctx(device=None, csrf=None, same_origin=True):
    headers = {}
    if device:
        headers["X-Birge-Device"] = device
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "host_allowed": True, "is_same_origin": same_origin}


@pytest.fixture
def api(tmp_path):
    store = ComplaintStore(tmp_path / "a.sqlite3")
    yield ComplaintsV2Service(store)
    store.close()


def call(api, method, path, body=None, principal=None, context=None, query=None):
    raw = json.dumps(body).encode() if body is not None else None
    reply = api.handle(method, P + path, query, raw, principal, context or ctx(DEV_A))
    assert reply is not None
    json.dumps(reply["body"])  # всегда сериализуется
    return reply["status"], reply["body"]


def create(api, device=DEV_A, **over):
    body = {"text": "Не убран снег на остановке", "category": "snow_ice", "point": [71.4135, 51.0915],
            "target": STOP}
    body.update(over)
    return call(api, "POST", "/complaints", body, context=ctx(device))


def test_foreign_paths_return_none(api):
    assert api.handle("GET", "/api/civic/v1/feedback", None, None, None, ctx()) is None
    assert api.handle("GET", P + "/heat", None, None, None, ctx()) is None
    assert api.handle("GET", None, None, None, None, ctx()) is None


def test_categories(api):
    status, body = call(api, "GET", "/categories")
    assert status == 200 and len(body["data"]["categories"]) == 12
    assert body["data"]["categories"][1]["id"] == "snow_ice"
    assert all(c["response_days"] >= 1 for c in body["data"]["categories"])


def test_create_and_replay(api):
    status, body = create(api, request_id="req-00000001")
    assert status == 201 and body["ok"]
    complaint = body["data"]["complaint"]
    assert complaint["code"] == "B-0001" and complaint["text"] and complaint["steps"][0]["state"] == "current"
    status, body = create(api, request_id="req-00000001")
    assert status == 200 and body["data"]["replayed"] is True


def test_create_errors_are_human(api):
    status, body = create(api, text="")
    assert status == 422 and body["error"]["fields"]["text"]
    status, body = call(api, "POST", "/complaints", None)
    assert status == 422
    reply = api.handle("POST", P + "/complaints", None, b"{not json", None, ctx(DEV_A))
    assert reply["status"] == 400
    status, body = create(api, device=None)
    assert status == 422 and "device_id" in body["error"]["fields"]


def test_cross_origin_and_host(api):
    reply = api.handle("POST", P + "/complaints", None, b"{}", None, ctx(DEV_A, same_origin=False))
    assert reply["status"] == 403
    reply = api.handle("GET", P + "/categories", None, None, None, {"host_allowed": False})
    assert reply["status"] == 403


def test_public_list_has_no_texts(api):
    create(api, text="Мой телефон 87011234567, снег у остановки")
    status, body = call(api, "GET", "/complaints", query="bbox=71.3,51.0,71.5,51.2&days=14", context=ctx(DEV_B))
    assert status == 200 and body["data"]["count"] == 1
    item = body["data"]["items"][0]
    assert "text" not in item and "87011234567" not in json.dumps(body)
    assert item["reporters"] == 1
    status, body = call(api, "GET", "/complaints", principal=Staff())
    assert body["data"]["items"][0]["text"].startswith("Мой телефон")


@pytest.mark.parametrize("query", ["bbox=1,2,3", "bbox=a,b,c,d", "bbox=71.5,51,71.4,51.2", "days=x",
                                   "category=potholes", "status=done", "since=вчера"])
def test_list_bad_query(api, query):
    status, body = call(api, "GET", "/complaints", query=query)
    assert status == 422 and body["ok"] is False


def test_detail_views(api):
    _, body = create(api)
    cid = body["data"]["complaint"]["id"]
    _, mine = call(api, "GET", "/complaints/" + cid, context=ctx(DEV_A))
    assert "text" in mine["data"]["complaint"]
    _, other = call(api, "GET", "/complaints/" + cid, context=ctx(DEV_B))
    assert "text" not in other["data"]["complaint"]
    _, by_code = call(api, "GET", "/complaints/B-0001", context=ctx(DEV_B))
    assert by_code["data"]["complaint"]["id"] == cid
    status, _ = call(api, "GET", "/complaints/c-unknown00000")
    assert status == 404


def test_metoo_flow(api):
    _, body = create(api)
    cid = body["data"]["complaint"]["id"]
    status, body = call(api, "POST", f"/complaints/{cid}/metoo", {}, context=ctx(DEV_B))
    assert status == 200 and body["data"]["result"] == "added" and body["data"]["complaint"]["reporters"] == 2
    _, body = call(api, "POST", f"/complaints/{cid}/metoo", {}, context=ctx(DEV_B))
    assert body["data"]["result"] == "already" and body["data"]["complaint"]["reporters"] == 2
    _, body = call(api, "POST", f"/complaints/{cid}/metoo", {}, context=ctx(DEV_A))
    assert body["data"]["result"] == "author"
    _, mine = call(api, "GET", "/complaints/mine", context=ctx(DEV_B))
    assert mine["data"]["items"][0]["relation"] == "metoo" and "text" not in mine["data"]["items"][0]
    assert mine["data"]["items"][0]["steps"]


def test_status_requires_staff_and_csrf(api):
    _, body = create(api)
    cid = body["data"]["complaint"]["id"]
    status, _ = call(api, "POST", f"/complaints/{cid}/status", {"status": "accepted"})
    assert status == 403
    status, _ = call(api, "POST", f"/complaints/{cid}/status", {"status": "accepted"}, principal=Staff(),
                     context=ctx(csrf="wrong"))
    assert status == 403
    status, body = call(api, "POST", f"/complaints/{cid}/status", {"status": "accepted", "expected": "new"},
                        principal=Staff(), context=ctx(csrf="tok"))
    assert status == 200 and body["data"]["complaint"]["status_history"][-1]["by"] == "operator1"
    status, body = call(api, "POST", f"/complaints/{cid}/status", {"status": "fixed", "expected": "new"},
                        principal=Staff(), context=ctx(csrf="tok"))
    assert status == 409
    status, body = call(api, "POST", f"/complaints/{cid}/status", {"status": "new"},
                        principal=Staff(), context=ctx(csrf="tok"))
    assert status == 422
    # житель видит смену статуса в «Мои обращения», но не имя сотрудника
    _, mine = call(api, "GET", "/complaints/mine", context=ctx(DEV_A))
    assert mine["data"]["items"][0]["status"] == "accepted" and "operator1" not in json.dumps(mine)


def test_duplicate_route(api):
    _, a = create(api)
    _, b = create(api, device=DEV_B)
    a_id, b_id = a["data"]["complaint"]["id"], b["data"]["complaint"]["id"]
    status, _ = call(api, "POST", f"/complaints/{b_id}/duplicate", {"of": a_id})
    assert status == 403
    status, body = call(api, "POST", f"/complaints/{b_id}/duplicate", {"of": a_id}, principal=Staff(),
                        context=ctx(csrf="tok"))
    assert status == 200 and body["data"]["complaint"]["metoo"] == 1
    status, _ = call(api, "POST", f"/complaints/{b_id}/duplicate", {}, principal=Staff(), context=ctx(csrf="tok"))
    assert status == 422


def test_events_summary_place(api):
    _, body = create(api)
    cid = body["data"]["complaint"]["id"]
    call(api, "POST", f"/complaints/{cid}/metoo", {}, context=ctx(DEV_B))
    _, events = call(api, "GET", "/complaints/events", query="after=0")
    assert [e["type"] for e in events["data"]["events"]] == ["created", "metoo"]
    assert events["data"]["last"] == events["data"]["events"][-1]["seq"]
    _, summary = call(api, "GET", "/complaints/summary", query=f"target_id={STOP['id']}&category=snow_ice")
    assert summary["data"]["reporters"] == 2
    status, _ = call(api, "GET", "/complaints/summary", query="")
    assert status == 422
    _, place = call(api, "GET", "/complaints/place", query="lon=71.4135&lat=51.0915")
    assert place["data"]["target"]["approximate"] is True
    assert place["data"]["geometry"]["type"] == "Polygon"
    status, _ = call(api, "GET", "/complaints/place", query="lon=10&lat=10")
    assert status == 422


def test_method_not_allowed(api):
    reply = api.handle("DELETE", P + "/complaints", None, None, None, ctx())
    assert reply["status"] == 405 and "Allow" in reply["headers"]


def test_rate_limit_429(tmp_path):
    store = ComplaintStore(tmp_path / "l.sqlite3", limits={"creates_per_hour": 1})
    api = ComplaintsV2Service(store)
    create(api)
    status, body = create(api)
    assert status == 429 and "мин" in body["error"]["message"]
