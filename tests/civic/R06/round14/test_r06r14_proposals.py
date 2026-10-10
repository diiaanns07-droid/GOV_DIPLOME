"""R06 раунд 14: предложения акимата и голоса жителей (CONTRACT §7)."""

import sqlite3
import threading

import pytest

from ui.civic_store import proposals as propmod
from r06r14_helpers import NURA_POINT, call, context, device, make_service


def vote(v2, proposal_id, value, dev, **ctx):
    return call(v2, "POST", f"/proposals/{proposal_id}/vote", {"value": value, "device_id": dev},
                ctx=context(**ctx))


def counts(v2, proposal_id, dev=None):
    query = f"device_id={dev}" if dev else None
    item = call(v2, "GET", f"/proposals/{proposal_id}", query=query)["body"]["data"]["item"]
    return item["votes_up"], item["votes_down"], item["my_vote"]


def test_create_proposal_contract_shape(staff):
    item = staff.create_proposal()
    for key in ("id", "kind", "geometry", "status", "votes_up", "votes_down"):
        assert key in item
    assert item["status"] == "proposal" and item["votes_up"] == 0 and item["votes_down"] == 0
    assert item["district"] == "nura" and item["title_kk"] == "Мектеп жанындағы гүлзар"
    assert item["voting_open"] is True and item["demo"] is False


def test_default_titles_when_empty(staff):
    item = staff.create_proposal(title_ru=None, title_kk=None, kind="playground")
    assert (item["title_ru"], item["title_kk"]) == ("Детская площадка", "Балалар алаңы")
    only_ru = staff.create_proposal(title_ru="Площадка во дворе", title_kk=None, kind="playground")
    assert only_ru["title_kk"] is None  # интерфейс покажет русское название, а не чужой kk-текст


def test_vote_is_one_per_device_and_repeat_changes_vote(staff):
    p = staff.create_proposal()
    first = vote(staff.v2, p["id"], 1, device(1))
    assert first["status"] == 200 and first["body"]["data"]["changed"] is True
    again = vote(staff.v2, p["id"], 1, device(1))  # двойной клик
    assert again["body"]["data"]["changed"] is False
    assert counts(staff.v2, p["id"], device(1)) == (1, 0, 1)
    switched = vote(staff.v2, p["id"], -1, device(1))  # передумал
    assert switched["body"]["data"]["changed"] is True and switched["body"]["data"]["previous"] == 1
    assert counts(staff.v2, p["id"], device(1)) == (0, 1, -1)
    vote(staff.v2, p["id"], 1, device(2))
    vote(staff.v2, p["id"], 1, device(3))
    assert counts(staff.v2, p["id"]) == (2, 1, None)
    assert counts(staff.v2, p["id"], device(9)) == (2, 1, None)


def test_votes_survive_restart(staff, db_path, clock):
    p = staff.create_proposal()
    vote(staff.v2, p["id"], 1, device(1))
    vote(staff.v2, p["id"], -1, device(2))
    _, v2b = make_service(db_path, clock)
    assert counts(v2b, p["id"], device(1)) == (1, 1, 1)
    # После перезапуска тот же device_id всё так же узнаётся: соль хранится в базе.
    assert vote(v2b, p["id"], 1, device(1))["body"]["data"]["changed"] is False
    assert counts(v2b, p["id"]) == (1, 1, None)


def test_raw_device_id_is_not_stored(staff, db_path):
    p = staff.create_proposal()
    vote(staff.v2, p["id"], 1, device(7))
    raw = db_path.read_bytes()
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists():
        raw += wal.read_bytes()
    assert device(7).encode() not in raw
    item = call(staff.v2, "GET", f"/proposals/{p['id']}", query=f"device_id={device(7)}")["body"]["data"]["item"]
    assert "device" not in str(item.keys()) and device(7) not in str(item)


@pytest.mark.parametrize("body,field", [
    ({"value": 2, "device_id": "device-test-0001-abcdefgh"}, "value"),
    ({"value": True, "device_id": "device-test-0001-abcdefgh"}, "value"),
    ({"value": 1, "device_id": "short"}, "device_id"),
    ({"value": 1, "device_id": "bad id with spaces!!!"}, "device_id"),
    ({"value": 1}, "device_id"),
    ({"value": 1, "device_id": "device-test-0001-abcdefgh", "votes_up": 100}, "votes_up"),
])
def test_vote_validation(staff, body, field):
    p = staff.create_proposal()
    result = call(staff.v2, "POST", f"/proposals/{p['id']}/vote", body)
    assert result["status"] == 422 and field in result["body"]["error"]["fields"]
    assert counts(staff.v2, p["id"]) == (0, 0, None)


def test_vote_cross_origin_and_foreign_host_rejected(staff):
    p = staff.create_proposal()
    assert vote(staff.v2, p["id"], 1, device(1), same_origin=False)["status"] == 403
    assert vote(staff.v2, p["id"], 1, device(1), host_allowed=False)["status"] == 403
    assert counts(staff.v2, p["id"]) == (0, 0, None)
    assert vote(staff.v2, "no-such", 1, device(1))["status"] == 404


def test_vote_rate_limit(staff, monkeypatch):
    p = staff.create_proposal()
    staff.v2.proposals.limiter = propmod.RateLimiter(3)
    for n in range(3):
        assert vote(staff.v2, p["id"], 1, device(n))["status"] == 200
    limited = vote(staff.v2, p["id"], 1, device(10))
    assert limited["status"] == 429 and limited["headers"]["Retry-After"] == "60"
    assert vote(staff.v2, p["id"], 1, device(11), client_ip="10.0.0.2")["status"] == 200


def test_approve_reject_close_voting_and_need_staff(staff):
    p = staff.create_proposal()
    vote(staff.v2, p["id"], 1, device(1))
    anon = call(staff.v2, "POST", f"/proposals/{p['id']}/approve", {})
    assert anon["status"] == 401
    approved = staff.call("POST", f"/proposals/{p['id']}/approve", {"reason": "Поддержали жители"})
    assert approved["status"] == 200
    item = approved["body"]["data"]["item"]
    assert item["status"] == "approved" and item["voting_open"] is False and item["votes_up"] == 1
    closed = vote(staff.v2, p["id"], -1, device(1))
    assert closed["status"] == 409 and closed["body"]["error"]["code"] == "voting_closed"
    twice = staff.call("POST", f"/proposals/{p['id']}/reject", {})
    assert twice["status"] == 409 and twice["body"]["error"]["code"] == "already_decided"
    q = staff.create_proposal()
    assert staff.call("POST", f"/proposals/{q['id']}/reject", {})["body"]["data"]["item"]["status"] == "rejected"


def test_withdraw_hides_proposal_but_keeps_row(staff, db_path):
    p = staff.create_proposal()
    vote(staff.v2, p["id"], 1, device(1))
    result = staff.call("POST", f"/proposals/{p['id']}/withdraw", {})
    assert result["status"] == 200 and result["body"]["data"]["withdrawn"] == p["id"]
    assert call(staff.v2, "GET", f"/proposals/{p['id']}")["status"] == 404
    assert p["id"] not in [i["id"] for i in call(staff.v2, "GET", "/proposals")["body"]["data"]["items"]]
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT status FROM civic_proposals WHERE id = ?", (p["id"],)).fetchone() == ("withdrawn",)
        assert conn.execute("SELECT COUNT(*) FROM civic_votes").fetchone() == (1,)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM civic_proposals")
        actions = [r[0] for r in conn.execute("SELECT action FROM civic_proposal_history ORDER BY id")]
        assert actions == ["create", "withdraw"]
    finally:
        conn.close()


@pytest.mark.parametrize("override,field", [
    ({"kind": "castle"}, "kind"),
    ({"geometry": None}, "geometry"),
    ({"geometry": {"type": "Point", "coordinates": [37.6, 55.7]}}, "geometry.coordinates"),
    ({"kind": "lighting"}, "geometry"),  # освещение — только линия
    ({"geometry": {"type": "LineString", "coordinates": [NURA_POINT, [71.351, 51.131]]}}, "geometry"),
    ({"title_ru": "<script>x</script>"}, "title_ru"),
    ({"rotation_deg": "90"}, "rotation_deg"),
    ({"planned_year": 1999}, "planned_year"),
    ({"status": "approved"}, "status"),
])
def test_create_validation(staff, override, field):
    body = {"kind": "square", "geometry": {"type": "Point", "coordinates": NURA_POINT}, "title_ru": "Сквер"}
    body.update(override)
    result = staff.call("POST", "/proposals", body)
    assert result["status"] == 422, result
    assert field in result["body"]["error"]["fields"], result["body"]["error"]["fields"]


def test_lighting_along_segment_and_filters(staff):
    line = {"type": "LineString", "coordinates": [[71.40, 51.08], [71.41, 51.081], [71.42, 51.082]]}
    light = staff.create_proposal(kind="lighting", geometry=line, title_ru="Освещение улицы")
    square = staff.create_proposal()
    listed = lambda q: [i["id"] for i in call(staff.v2, "GET", "/proposals", query=q)["body"]["data"]["items"]]
    assert set(listed(None)) == {light["id"], square["id"]}
    assert listed("district=nura") == [square["id"]]
    assert listed("bbox=71.405,51.0,71.43,51.1") == [light["id"]]
    assert call(staff.v2, "GET", "/proposals", query="status=withdrawn")["status"] == 400


def test_create_needs_staff_and_csrf(staff):
    body = {"kind": "square", "geometry": {"type": "Point", "coordinates": NURA_POINT}}
    assert call(staff.v2, "POST", "/proposals", body)["status"] == 401
    assert call(staff.v2, "POST", "/proposals", body, ctx=context(staff.cookie, None))["status"] == 403


def test_summary_for_akim(staff, clock):
    a = staff.create_proposal()
    clock.advance(days=2)
    b = staff.create_proposal(kind="sports", title_ru="Спортплощадка")
    vote(staff.v2, a["id"], 1, device(1))
    vote(staff.v2, b["id"], 1, device(1))
    vote(staff.v2, b["id"], -1, device(2))
    data = staff.v2.proposals_summary(since="2026-10-12")
    assert data["total"] == 2 and data["new"] == 1
    assert data["votes_up"] == 2 and data["votes_down"] == 1
    assert data["top"][0]["id"] == b["id"]
    http = call(staff.v2, "GET", "/proposals/summary", query="since=2026-10-12")["body"]["data"]
    assert http == data


def test_parallel_votes_from_one_device_never_double(staff):
    p = staff.create_proposal()
    errors = []

    def worker(value):
        try:
            result = vote(staff.v2, p["id"], value, device(1))
            assert result["status"] in (200, 503), result
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    staff.v2.proposals.limiter = propmod.RateLimiter(1000)
    threads = [threading.Thread(target=worker, args=(1 if n % 2 else -1,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    up, down, _ = counts(staff.v2, p["id"])
    assert up + down == 1


def test_routing_leaves_other_v2_paths_and_405(staff):
    assert staff.v2.handle("POST", "/api/civic/v2/classify", None, b"{}", context()) is None
    assert staff.v2.handle("GET", "/api/civic/v2/heat", None, None, context()) is None
    assert staff.v2.handle("GET", "/api/civic/v1/objects", None, None, context()) is None
    result = call(staff.v2, "DELETE", "/proposals")
    assert result["status"] == 405 and "POST" in result["headers"]["Allow"]
    meta = call(staff.v2, "GET", "/meta")["body"]["data"]
    assert meta["proposal_kinds"] == ["square", "playground", "sports", "stop", "lighting"]
    assert meta["stale_after_days"] == 14


def test_seed_r14_demo_is_marked_and_idempotent(tmp_path, clock, capsys):
    from ui.civic_store import cli
    path = tmp_path / "demo.sqlite3"
    assert cli.main(["--db", str(path), "init"]) == 0
    assert cli.main(["--db", str(path), "seed-r14-demo"]) == 0
    assert cli.main(["--db", str(path), "seed-r14-demo"]) == 0  # повтор ничего не дублирует
    capsys.readouterr()
    _, v2 = make_service(path, clock)
    items = v2.list_proposals()["items"]
    assert len(items) == 5 and all(i["demo"] for i in items)
    assert sorted(i["kind"] for i in items) == sorted(propmod.KINDS)
    light = next(i for i in items if i["kind"] == "lighting")
    assert light["geometry"]["type"] == "LineString" and light["district"] == "nura"
    assert all(i["district"] == "nura" for i in items)
    objects = v2.list_objects()["items"]
    assert objects and all(o["demo"] for o in objects)
    assert {o["id"] for o in objects if o["stage_source"] == "demo"} == {"demo-r02-sidewalk-delay",
                                                                         "demo-r02-yard-landscaping"}
    # Просьба R08 (день 3): у демо-объектов есть казахское название; у остальных записей title_kk = None.
    from ui.civic_store.stages import DEMO_TITLES_KK
    assert all(o["title_kk"] == DEMO_TITLES_KK[o["id"]] for o in objects)
    assert all(i["title_kk"] for i in v2.stages.lagging(None)["late"])


def test_build_demo_set_has_kk_titles(tmp_path, clock, capsys):
    """R10 B-018: сборка R01 засевает data/civic/astana/demo_synthetic.json (CIVIC_DEMO=1) — у каждого публичного
    демо-объекта должно быть казахское название, иначе «Картина дня» в ҚАЗ показывает русские строки."""
    from pathlib import Path
    from ui.civic_store import cli
    from ui.civic_store.stages import DEMO_TITLES_KK
    package = Path(__file__).resolve().parents[4] / "data" / "civic" / "astana" / "demo_synthetic.json"
    if not package.is_file():
        pytest.skip("нет data/civic/astana/demo_synthetic.json")
    path = tmp_path / "build.sqlite3"
    assert cli.main(["--db", str(path), "init"]) == 0
    assert cli.main(["--db", str(path), "seed-demo", "--package", str(package)]) == 0
    assert cli.main(["--db", str(path), "seed-r14-demo"]) == 0
    capsys.readouterr()
    _, v2 = make_service(path, clock)
    objects = v2.list_objects()["items"]
    assert len(objects) >= 5 and all(o["demo"] for o in objects)
    missing = [o["id"] for o in objects if not o["title_kk"]]
    assert missing == [], missing
    assert all("Демо" not in DEMO_TITLES_KK[o["id"]] for o in objects)
    late = v2.stages.lagging(None)["late"]
    assert late and all(i["title_kk"] for i in late)


@pytest.mark.parametrize("package", [None, "data/civic/astana/demo_synthetic.json"])
def test_demo_stages_agree_with_record_status(tmp_path, clock, capsys, package):
    """Свой проход UX_BRIEF: этап демо-объекта не спорит с его статусом и названием (оба демо-набора)."""
    from pathlib import Path
    from ui.civic_store import cli
    path = tmp_path / "plausible.sqlite3"
    args = ["--db", str(path), "seed-demo"]
    if package:
        full = Path(__file__).resolve().parents[4] / package
        if not full.is_file():
            pytest.skip(f"нет {package}")
        args += ["--package", str(full)]
    assert cli.main(["--db", str(path), "init"]) == 0
    assert cli.main(args) == 0
    assert cli.main(["--db", str(path), "seed-r14-demo"]) == 0
    capsys.readouterr()
    _, v2 = make_service(path, clock)
    objects = v2.list_objects()["items"]
    for o in objects:
        if o["status"] == "completed":
            assert o["stage"] == "operating" and not o["late"], o["id"]
        if o["status"] == "in_progress":
            assert o["stage"] == "construction" and o["late"] and o["delay_days"] == 23, o["id"]
        if o["status"] in ("cancelled", "unknown") or o["kind"] == "event":
            assert o["stage_source"] != "demo", o["id"]
    late = [o for o in objects if o["late"]]
    assert 1 <= len(late) <= len(objects) // 2  # отстаёт часть, а не всё (правдоподобно для показа)


def test_title_kk_only_for_known_demo_records(staff):
    item = staff.create_object()
    listed = next(o for o in call(staff.v2, "GET", "/objects")["body"]["data"]["items"] if o["id"] == item["id"])
    assert listed["demo"] is True and listed["title_kk"] is None  # синтетика теста, но не из демо-набора


def test_session_cookie_reaches_v2_routes(stack):
    # Браузер отправляет cookie только на пути внутри Path. Раньше было /api/civic/v1 → v2 получал 401.
    svc, _ = stack
    from r06r14_helpers import PASSWORD
    result = call(svc, "POST", "/session/login", {"username": "editor1", "password": PASSWORD}, prefix="/api/civic/v1")
    path = [p.strip()[5:] for p in result["headers"]["Set-Cookie"].split(";") if p.strip().startswith("Path=")][0]
    assert "/api/civic/v2/proposals".startswith(path + "/") and "/api/civic/v1/session".startswith(path + "/")
    assert not "/civic/proposals/demo.html".startswith(path)
