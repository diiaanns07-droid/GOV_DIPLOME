"""R04 П3: «Создать задачи» — задачи разбора -> жалобы R09 только функциями хранилища R09 (create + «Я тоже» с
текстом). Повтор того же batch_id — без дублей; задачи без места не создаются; пример — demo: true."""

from __future__ import annotations

import json

import pytest

import ui.civic_ml_api as api
from ui.civic_ml_api.errors import MLServiceUnavailable
from ui.civic_ml_api.intake import analyze, commit

PII = ("87011234567", "880101300123")


class FakeStore:
    """Как ComplaintStore R09: create(payload, device, demo) -> (record, created), повтор request_id — тот же."""

    def __init__(self, fail_subtopic=False):
        self.records, self.by_request, self.metoos, self.calls = {}, {}, set(), []
        self.fail_subtopic = fail_subtopic

    def create(self, payload, device_id, *, demo=False):
        self.calls.append((payload, device_id, demo))
        if self.fail_subtopic and payload.get("subtopic"):
            raise ValueError("Уточнение не подходит к категории.")
        key = (device_id, payload.get("request_id"))
        if key in self.by_request:
            return self.records[self.by_request[key]], False
        rid = f"c-{len(self.records) + 1:08d}"
        self.records[rid] = dict(payload, id=rid, code=f"B-{len(self.records) + 1:04d}", demo=demo, metoo=0)
        self.by_request[key] = rid
        return self.records[rid], True

    def metoo(self, complaint_id, device_id, note=None):
        if (complaint_id, device_id) in self.metoos:
            return self.records[complaint_id], "already"
        self.metoos.add((complaint_id, device_id))
        self.records[complaint_id]["metoo"] += 1
        return self.records[complaint_id], "added"


@pytest.fixture(autouse=True)
def no_store():
    api.set_complaint_source(None)
    yield
    api.set_complaint_source(None)


def test_commit_creates_tasks_with_place_once():
    r = analyze(sample="night")
    store = FakeStore()
    res = commit(r["batch_id"], store=store)
    s = r["summary"]
    assert res["created"] == s["ready"] == len(store.records) and res["skipped_no_address"] == s["no_address"]
    assert res["failed"] == 0 and res["demo"] is True
    # каждое склеенное обращение — «Я тоже» к записи задачи: людей в записях столько же, сколько текстов с местом
    with_place = sum(t["people"] for t in r["tasks"] if t["target"])
    assert sum(1 + rec["metoo"] for rec in store.records.values()) == with_place
    assert res["joined"] == with_place - s["ready"]
    again = commit(r["batch_id"], store=store)
    assert again["created"] == 0 and again["existing"] == s["ready"] and again["joined"] == 0
    assert len(store.records) == s["ready"]


def test_payload_is_r09_shape_and_public_text_only():
    r = analyze(sample="night")
    store = FakeStore()
    commit(r["batch_id"], store=store)
    for payload, device, demo in store.calls:
        assert set(payload) >= {"text", "category", "category_source", "target", "point", "request_id"}
        assert payload["category_source"] == "model" and payload["source"] == "intake" and demo is True
        assert payload["target"]["kind"] in ("object", "segment", "area") and len(payload["point"]) == 2
        assert payload["request_id"].startswith("in-" + r["batch_id"]) and 8 <= len(payload["request_id"]) <= 64
        assert device.startswith("birge-intake-") and 16 <= len(device) <= 80
        assert not any(pii in json.dumps(payload, ensure_ascii=False) for pii in PII)
    assert len({d for _, d, _ in store.calls}) == len(store.calls)    # своё устройство у задачи (лимит R09 в час)


def test_commit_subset_of_tasks():
    r = analyze(sample="night")
    ready = [t["id"] for t in r["tasks"] if t["target"]][:3]
    no_place = [t["id"] for t in r["tasks"] if not t["target"]][:1]
    store = FakeStore()
    res = commit(r["batch_id"], ready + no_place, store=store)
    assert res["created"] == 3 and res["skipped_no_address"] == 1
    assert [x["task_id"] for x in res["records"]] == ready


def test_retry_without_subtopic_when_r09_rejects_it():
    r = analyze(sample="night")
    store = FakeStore(fail_subtopic=True)
    res = commit(r["batch_id"], store=store)
    assert res["created"] == r["summary"]["ready"] and res["failed"] == 0
    assert all("subtopic" not in rec for rec in store.records.values())


def test_commit_errors():
    with pytest.raises(ValueError):
        commit("../etc", store=FakeStore())
    with pytest.raises(ValueError):
        commit("0" * 16, "t1", store=FakeStore())
    with pytest.raises(LookupError):
        commit("f" * 16, store=FakeStore())              # разбор не найден (после перезапуска — разобрать снова)
    r = analyze(sample="night")
    with pytest.raises(MLServiceUnavailable):
        commit(r["batch_id"])                            # хранилище R09 не подключено -> 503


def test_commit_through_gateway_function_uses_connected_store(tmp_path):
    from ui.civic_feedback.v2.store import ComplaintStore
    store = ComplaintStore(tmp_path / "c.sqlite3")
    api.connect_store(store, warm=False)
    staff, ctx = {"username": "op", "role": "editor"}, {"headers": {}}
    r = api.intake_analyze(body={"sample": "night"}, principal=staff, context=ctx)
    res = api.intake_commit(body={"batch_id": r["batch_id"]}, principal=staff, context=ctx)
    assert res["created"] == r["summary"]["ready"] and res["failed"] == 0


def test_real_r09_store_with_map_check(tmp_path):
    """Настоящее хранилище R09 + проверка цели картой R12: цели задач не превращаются в «примерное место»."""
    from ui.civic_feedback.v2.store import ComplaintStore
    try:
        import engine.civic_geo as geo
    except ImportError:  # pragma: no cover — без R12 проверка цели пропускается
        geo = None
    store = ComplaintStore(tmp_path / "c.sqlite3")
    if geo is not None:
        store.target_lookup = geo.target_geometry
    r = analyze(sample="night")
    res = commit(r["batch_id"], store=store)
    assert res["created"] == r["summary"]["ready"] and res["failed"] == 0
    rows = [json.loads(row[0]) for row in store._db.execute("SELECT record_json FROM complaints_v2").fetchall()]
    assert len(rows) == r["summary"]["ready"]
    assert all(row["demo"] is True and not row["target"].get("approximate") for row in rows)
    assert not any(pii in json.dumps(rows, ensure_ascii=False) for pii in PII)
    with_place = sum(t["people"] for t in r["tasks"] if t["target"])
    assert sum(1 + (row.get("metoo") or 0) for row in rows) == with_place
    shelter = next(t for t in r["tasks"] if "n01" in t["text_ids"])
    merged = store.merged(shelter["target"]["id"])              # «Что объединено» в карточке акимата
    assert len(merged) == shelter["people"] - 1
    again = commit(r["batch_id"], store=store)
    assert again["created"] == 0 and again["existing"] == r["summary"]["ready"]
    assert store._db.execute("SELECT COUNT(*) FROM complaints_v2").fetchone()[0] == r["summary"]["ready"]
