"""R09 раунд 14: хранилище жалоб v2 — запись §5, «Я тоже», статусы, дубли, события, выборки."""

from datetime import datetime, timedelta

import pytest

from ui.civic_feedback.v2 import ComplaintStore, Conflict, LimitError, NotFound, RecordError, categories
from ui.civic_feedback.v2 import record as rec

DEV_A = "dev-aaaaaaaaaaaaaaaa"
DEV_B = "dev-bbbbbbbbbbbbbbbb"
DEV_C = "dev-cccccccccccccccc"
STOP = {"kind": "object", "id": "osm-node-123456", "label_ru": "Остановка «Нура»", "label_kk": "«Нұра» аялдамасы"}
NURA = [71.4135, 51.0915]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 11, 10, 0, tzinfo=rec.ASTANA_TZ)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    s = ComplaintStore(tmp_path / "c.sqlite3", clock=clock)
    yield s
    s.close()


def payload(**over):
    data = {"text": "Не убран снег на остановке, скользко", "category": "snow_ice",
            "category_source": "model", "point": NURA, "target": STOP,
            "model": {"label": "snow_ice", "score": 0.91, "version": "v2-test", "needs_review": False}}
    data.update(over)
    return data


def test_create_matches_contract_record(store):
    record, created = store.create(payload(district="nura"), DEV_A)
    assert created
    for key in ("id", "created_at", "text", "lang", "category", "category_source", "model", "point",
                "target", "district", "status", "status_history", "metoo", "duplicate_of", "demo"):
        assert key in record, key
    assert record["id"].startswith("c-") and record["code"] == "B-0001"
    assert record["created_at"] == "2026-10-11T10:00:00+05:00"
    assert record["status"] == "new" and record["status_history"] == [{"at": record["created_at"], "status": "new"}]
    assert record["target"]["kind"] == "object" and record["target"]["id"] == "osm-node-123456"
    assert record["model"] == {"label": "snow_ice", "score": 0.91, "version": "v2-test", "needs_review": False}
    assert record["metoo"] == 0 and record["duplicate_of"] is None and record["demo"] is False
    assert record["due_at"] == "2026-10-12T10:00:00+05:00"  # снег — 1 день
    assert store.get(record["id"]) == record


def test_complaint_always_has_target(store):
    record, _ = store.create(payload(target=None), DEV_A)
    assert record["target"]["kind"] == "area" and record["target"]["id"].startswith("cell-")
    assert record["target"]["approximate"] is True


@pytest.mark.parametrize("bad, field", [
    ({"text": "  "}, "text"), ({"text": "x" * 2001}, "text"), ({"category": "potholes"}, "category"),
    ({"point": [37.6, 55.7]}, "point"), ({"point": [71.4]}, "point"), ({"point": ["71", "51"]}, "point"),
    ({"point": [float("nan"), 51.1]}, "point"),
    ({"target": {"kind": "object", "id": "demo-r02-x"}}, "target.id"),
    ({"target": {"kind": "segment", "id": "osm-node-1"}}, "target.id"),
    ({"target": {"kind": "street", "id": "x"}}, "target.kind"),
])
def test_invalid_payload_rejected_with_field(store, bad, field):
    with pytest.raises(RecordError) as exc:
        store.create(payload(**bad), DEV_A)
    assert field in exc.value.fields


def test_bad_device_rejected(store):
    with pytest.raises(RecordError):
        store.create(payload(), "short")
    with pytest.raises(RecordError):
        store.create(payload(), None)


def test_garbage_model_not_stored_and_source_defaults(store):
    record, _ = store.create(payload(model={"label": "nonsense", "score": 5}, category_source="hacker"), DEV_A)
    assert record["model"] is None and record["category_source"] == "resident"
    record, _ = store.create(payload(model={"category": "roads", "score": 7, "model_version": "x"}), DEV_A)
    assert record["model"]["score"] is None and record["model"]["needs_review"] is True


@pytest.mark.parametrize("text, lang", [
    ("Яма на дороге у остановки", "ru"),
    ("Аялдамада қар тазаланбаған, өте тайғақ", "kk"),
    ("Аялдамада қар жатыр, уже неделю не убирают", "mixed"),
])
def test_language_detection(store, text, lang):
    record, _ = store.create(payload(text=text), DEV_A)
    assert record["lang"] == lang


def test_request_id_replay_returns_same_record(store):
    first, created1 = store.create(payload(request_id="req-12345678"), DEV_A)
    again, created2 = store.create(payload(request_id="req-12345678"), DEV_A)
    assert created1 and not created2 and again["id"] == first["id"]
    assert len(store.list()) == 1
    other, created3 = store.create(payload(request_id="req-12345678"), DEV_B)  # другое устройство — своя
    assert created3 and other["id"] != first["id"]


def test_rate_limit_per_device(tmp_path, clock):
    s = ComplaintStore(tmp_path / "r.sqlite3", clock=clock, limits={"creates_per_hour": 2})
    s.create(payload(), DEV_A)
    s.create(payload(), DEV_A)
    with pytest.raises(LimitError) as exc:
        s.create(payload(), DEV_A)
    assert 0 < exc.value.retry_after_s <= 3601
    s.create(payload(), DEV_B)
    clock.advance(hours=1, seconds=1)
    s.create(payload(), DEV_A)


def test_metoo_one_per_device_never_creates_record(store):
    record, _ = store.create(payload(), DEV_A)
    assert store.metoo(record["id"], DEV_B)[1] == "added"
    assert store.metoo(record["id"], DEV_B)[1] == "already"
    assert store.metoo(record["id"], DEV_A)[1] == "author"
    updated, result = store.metoo(record["id"], DEV_C)
    assert result == "added" and updated["metoo"] == 2 and rec.reporters(updated) == 3
    assert len(store.list(include_duplicates=True)) == 1


def test_metoo_unknown_complaint(store):
    with pytest.raises(NotFound):
        store.metoo("c-doesnotexist1", DEV_B)


def test_status_transitions_and_history(store, clock):
    record, _ = store.create(payload(), DEV_A)
    clock.advance(hours=2)
    store.set_status(record["id"], "accepted", actor="operator1")
    clock.advance(days=1)
    store.set_status(record["id"], "in_progress", actor="operator1", note="бригада выехала")
    clock.advance(days=1)
    done = store.set_status(record["id"], "fixed", actor="master")
    assert [h["status"] for h in done["status_history"]] == ["new", "accepted", "in_progress", "fixed"]
    assert done["status_history"][2]["note"] == "бригада выехала"
    with pytest.raises(RecordError):
        store.set_status(record["id"], "fixed")       # в тот же статус нельзя
    with pytest.raises(RecordError):
        store.set_status(record["id"], "rejected")    # из fixed — только повторно открыть
    reopened = store.set_status(record["id"], "in_progress")
    assert reopened["status"] == "in_progress"
    with pytest.raises(RecordError):
        store.set_status(record["id"], "done")


def test_status_conflict_two_operators(store):
    record, _ = store.create(payload(), DEV_A)
    store.set_status(record["id"], "accepted", expected="new")
    with pytest.raises(Conflict):
        store.set_status(record["id"], "rejected", expected="new")


def test_public_view_hides_text_and_device(store):
    record, _ = store.create(payload(text="Звоните мне +7 701 123 45 67, яма у подъезда"), DEV_A)
    store.set_status(record["id"], "accepted", actor="operator1", note="внутренняя заметка")
    view = rec.public_view(store.get(record["id"]))
    flat = repr(view)
    assert "701" not in flat and "text" not in view and "operator1" not in flat and "заметка" not in flat
    assert view["reporters"] == 1
    staff = rec.staff_view(store.get(record["id"]))
    assert staff["text"].startswith("Звоните") and "device_hash" not in staff


def test_author_view_has_steps(store):
    record, _ = store.create(payload(), DEV_A)
    steps = rec.author_view(record)["steps"]
    assert [s["state"] for s in steps] == ["current", "todo", "todo"]
    store.set_status(record["id"], "in_progress")
    steps = rec.author_view(store.get(record["id"]))["steps"]
    assert [s["state"] for s in steps] == ["done", "current", "todo"]
    store.set_status(record["id"], "fixed")
    assert [s["state"] for s in rec.author_view(store.get(record["id"]))["steps"]] == ["done", "done", "done"]
    other, _ = store.create(payload(), DEV_A)
    store.set_status(other["id"], "rejected")
    assert rec.author_view(store.get(other["id"]))["steps"][-1] == {"status": "rejected", "state": "current"}


def test_duplicate_moves_people_without_double_count(store):
    original, _ = store.create(payload(), DEV_A)
    dup, _ = store.create(payload(text="Снег на остановке не чистят"), DEV_B)
    store.metoo(dup["id"], DEV_C)
    store.metoo(dup["id"], DEV_A)  # автор исходной тоже нажал на дубль — не считается дважды
    merged = store.mark_duplicate(dup["id"], original["id"], actor="operator1")
    assert merged["id"] == original["id"]
    assert merged["metoo"] == 2  # B (автор дубля) и C; A — автор исходной
    assert store.get(dup["id"])["duplicate_of"] == original["id"]
    assert [r["id"] for r in store.list()] == [original["id"]]  # дубли не попадают в карту по умолчанию
    assert len(store.list(include_duplicates=True)) == 2
    # «Я тоже» на дубль засчитывается исходной
    _, result = store.metoo(dup["id"], DEV_C)
    assert result == "already"
    with pytest.raises(Conflict):
        store.mark_duplicate(original["id"], dup["id"])  # петля
    with pytest.raises(Conflict):
        store.mark_duplicate(dup["id"], original["id"])  # уже дубль


def test_list_filters(store, clock):
    a, _ = store.create(payload(category="roads", point=[71.41, 51.09]), DEV_A)
    clock.advance(days=10)
    b, _ = store.create(payload(category="snow_ice", point=[71.50, 51.15]), DEV_A)
    assert {r["id"] for r in store.list(bbox=(71.40, 51.08, 71.42, 51.10))} == {a["id"]}
    assert {r["id"] for r in store.list(since=clock.now - timedelta(days=1))} == {b["id"]}
    assert {r["id"] for r in store.list(category="roads")} == {a["id"]}
    assert {r["id"] for r in store.list(category=["roads", "snow_ice"])} == {a["id"], b["id"]}
    assert store.list(status="fixed") == []
    assert [r["id"] for r in store.list()] == [b["id"], a["id"]]  # новые сверху
    with pytest.raises(RecordError):
        store.list(since="вчера")


def test_mine_lists_own_and_metoo(store):
    own, _ = store.create(payload(), DEV_A)
    other, _ = store.create(payload(), DEV_B)
    store.metoo(other["id"], DEV_A)
    mine = store.mine(DEV_A)
    assert [(m["id"], m["relation"]) for m in mine] == [(own["id"], "author"), (other["id"], "metoo")]
    assert store.mine(DEV_C) == []


def test_target_summary_for_metoo_without_ml(store, clock):
    a, _ = store.create(payload(), DEV_A)
    store.metoo(a["id"], DEV_B)
    store.create(payload(), DEV_C)
    store.create(payload(category="roads"), DEV_C)
    summary = store.target_summary(STOP["id"], category="snow_ice")
    assert summary["complaints"] == 2 and summary["reporters"] == 3
    assert summary["top"]["id"] == a["id"] and "text" not in summary["top"]
    clock.advance(days=15)
    assert store.target_summary(STOP["id"], category="snow_ice")["reporters"] == 0


def test_events_for_heat_map(store):
    seen = []
    unsubscribe = store.subscribe(seen.append)
    record, _ = store.create(payload(), DEV_A)
    store.metoo(record["id"], DEV_B)
    store.set_status(record["id"], "accepted")
    unsubscribe()
    store.metoo(record["id"], DEV_C)
    assert [e["type"] for e in seen] == ["created", "metoo", "status"]
    assert seen[1]["target"] == {"kind": "object", "id": STOP["id"]} and seen[1]["reporters"] == 2
    events = store.events_since(0)
    assert [e["type"] for e in events] == ["created", "metoo", "status", "metoo"]
    assert store.events_since(events[1]["seq"])[0]["type"] == "status"
    assert all("text" not in e for e in events)


def test_failing_listener_does_not_break_create(store):
    store.subscribe(lambda e: 1 / 0)
    record, created = store.create(payload(), DEV_A)
    assert created and store.get(record["id"])


def test_overdue_by_category_deadline(store, clock):
    snow, _ = store.create(payload(category="snow_ice"), DEV_A)
    road, _ = store.create(payload(category="roads"), DEV_A)
    clock.advance(days=2)
    assert [r["id"] for r in store.overdue()] == [snow["id"]]
    store.set_status(snow["id"], "accepted")
    assert store.overdue() == []
    clock.advance(days=9)
    assert [r["id"] for r in store.overdue()] == [road["id"]]


def test_device_stored_only_as_salted_hash(tmp_path, store):
    store.create(payload(), DEV_A)
    raw = (tmp_path / "c.sqlite3").read_bytes()
    assert DEV_A.encode() not in raw


def test_every_category_has_response_deadline():
    categories.validate_response_days()
    assert set(categories.RESPONSE_DAYS) == set(categories.ids())
    assert len(categories.ids()) == 12


def test_v1_labels_map_to_v2():
    assert categories.v1_to_v2("transport_stops") == "transport"
    assert categories.v1_to_v2("landscaping") == "yards"
    assert categories.v1_to_v2("roads") == "roads"
    assert categories.v1_to_v2("unknown-label") == "other"
    assert categories.v1_to_v2(None) == "other"


def test_cell_target_is_stable_and_polygon_contains_point():
    target = rec.cell_target(*NURA)
    assert target == rec.cell_target(*NURA) and target["id"].startswith("cell-")
    ring = rec.cell_polygon(target["id"])
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    assert min(lons) <= NURA[0] <= max(lons) and min(lats) <= NURA[1] <= max(lats)
    # сторона ячейки ~150 м
    assert 140 < (max(lats) - min(lats)) * 111_320 < 160


def test_metoo_times_for_heat_weight(store, clock):
    a, _ = store.create(payload(), DEV_A)
    b, _ = store.create(payload(), DEV_B)
    clock.advance(days=3)
    store.metoo(a["id"], DEV_B)
    clock.advance(days=1)
    store.metoo(a["id"], DEV_C)
    times = store.metoo_times([a["id"], b["id"]])
    assert times == {a["id"]: ["2026-10-14T10:00:00+05:00", "2026-10-15T10:00:00+05:00"], b["id"]: []}
    assert store.metoo_times([]) == {}
