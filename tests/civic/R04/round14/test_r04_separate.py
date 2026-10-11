"""R04 + R09 · волна мелочей п. 9: «Это разные проблемы» — разъединить ошибочно объединённое одним действием.

Проверяем на настоящем хранилище R09 (ComplaintStore с patch research/round-14-results/R04/patches/r09_polish_r04.patch):
  - отмена «дубля» возвращает людей ровно как было: собственные «Я тоже» на исходной остаются;
  - цепочка (A -> B, потом B -> C) и перепривязанные дубли (D -> A) восстанавливаются;
  - «Я тоже» из формы с текстом жителя выделяется в его отдельную жалобу (время — когда он сообщил);
  - всё видит и делает только сотрудник; повтор — 409, не двойная жалоба;
  - журнал решений R04 получает пары «одинаковые» (дубль) и «разные» (разделено) с оценкой модели.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

store_mod = pytest.importorskip("ui.civic_feedback.v2.store")
if not hasattr(store_mod.ComplaintStore, "separate"):
    pytest.skip("patch R09 п. 9 (r09_polish_r04.patch) ещё не применён", allow_module_level=True)

from ui.civic_feedback.v2 import record as rec  # noqa: E402
from ui.civic_feedback.v2.api import ComplaintsV2Service  # noqa: E402
from ui.civic_feedback.v2.store import ComplaintStore, Conflict, NotFound  # noqa: E402

from r04_helpers import clean_api  # noqa: E402,F401 — autouse: чистый ML-API

STOP = [71.4180, 51.0905]
FAR = [71.4400, 51.1000]            # ~1,8 км: другая цель
T_STOP = {"kind": "object", "id": "osm-node-1001"}
T_FAR = {"kind": "object", "id": "osm-node-2002"}
DEV = {name: f"device-{name}-0000000000" for name in ("a", "b", "c", "d", "m1", "m2", "m3", "x")}


class Clock:
    """Время идёт по шагам в 1 минуту: нажатие и объединение не совпадают по секунде (как в жизни)."""

    def __init__(self):
        self.now = datetime(2026, 10, 11, 9, 0, tzinfo=rec.ASTANA_TZ)

    def __call__(self):
        self.now += timedelta(minutes=1)
        return self.now


@pytest.fixture()
def store(tmp_path):
    s = ComplaintStore(tmp_path / "c.sqlite3", clock=Clock())
    yield s
    s.close()


def make(store, who, text, point=STOP, target=T_STOP, category="transport"):
    record, created = store.create({"text": text, "category": category, "point": point, "target": target}, DEV[who])
    assert created
    return record


def people(store, cid):
    return rec.reporters(store.get(cid))


def metoo_devices(store, cid):
    with store._lock:
        return {r[0] for r in store._db.execute("SELECT device_hash FROM complaint_metoo_v2 WHERE complaint_id = ?",
                                                (cid,))}


# --------------------------------------------------------------------------- дубль
def test_separate_duplicate_restores_people_exactly(store):
    a = make(store, "a", "Разбит павильон остановки, стекло на земле")
    b = make(store, "b", "На остановке разбито стекло павильона")
    store.metoo(a["id"], DEV["m1"])                      # m1 — «Я тоже» на A
    store.metoo(b["id"], DEV["m1"])                      # и сам по себе на B (раньше объединения)
    store.metoo(b["id"], DEV["m2"])
    before_b = metoo_devices(store, b["id"])
    assert people(store, b["id"]) == 3                   # b + m1 + m2
    store.mark_duplicate(a["id"], b["id"], actor="op")
    assert people(store, b["id"]) == 4                   # + автор A (m1 уже был)
    events = []
    store.subscribe(events.append)

    separated, original = store.separate(a["id"], actor="op")

    assert separated["duplicate_of"] is None and separated["status_history"][-1]["separated_from"] == b["id"]
    assert separated["status_history"][-1]["by"] == "op"
    assert metoo_devices(store, b["id"]) == before_b      # собственное «Я тоже» m1 на B осталось
    assert people(store, b["id"]) == 3 and original["id"] == b["id"] and rec.reporters(original) == 3
    assert people(store, a["id"]) == 2                    # A: автор + m1
    assert [e["type"] for e in events] == ["separated", "metoo"]
    assert events[0]["original_id"] == b["id"]
    assert {r["id"] for r in store.list()} == {a["id"], b["id"]}   # A снова на карте


def test_separate_duplicate_through_chain_and_moved_children(store):
    a = make(store, "a", "Не горит фонарь у остановки")
    b = make(store, "b", "Темно на остановке, фонарь не работает")
    c = make(store, "c", "Нет света возле остановки вечером")
    d = make(store, "d", "Фонарь у остановки снова не горит")
    store.metoo(c["id"], DEV["m3"])
    store.mark_duplicate(d["id"], a["id"])               # D -> A (люди D в A)
    store.mark_duplicate(a["id"], b["id"])               # A -> B (D перепривязан на B)
    store.mark_duplicate(b["id"], c["id"])               # B -> C (A и D перепривязаны на C)
    assert store.get(d["id"])["duplicate_of"] == c["id"] and store.get(a["id"])["duplicate_of"] == c["id"]
    assert people(store, c["id"]) == 5                   # c, m3, b, a, d

    store.separate(a["id"])

    assert store.get(a["id"])["duplicate_of"] is None
    assert store.get(d["id"])["duplicate_of"] == a["id"]  # дубль A снова ссылается на A
    assert store.get(b["id"])["duplicate_of"] == c["id"]  # B остаётся дублем C
    assert people(store, a["id"]) == 2                    # a + d
    assert people(store, b["id"]) == 1                    # только автор B: люди A ушли и из B
    assert people(store, c["id"]) == 3                    # c, m3, b


def test_separate_not_merged_or_missing(store):
    a = make(store, "a", "Яма на дороге у остановки")
    with pytest.raises(Conflict):
        store.separate(a["id"])
    with pytest.raises(NotFound):
        store.separate("c-0000000000000000")
    with pytest.raises(NotFound):
        store.separate("mt-0000000000000000")


# --------------------------------------------------------------------------- «Я тоже» с текстом
NOTE = {"text": "У остановки не горит фонарь, темно вечером", "point": FAR, "target": T_FAR, "category": "lighting"}


def test_metoo_note_is_split_into_own_complaint(store):
    x = make(store, "a", "Разбит павильон остановки")
    record, result = store.metoo(x["id"], DEV["m1"], note=NOTE)
    assert result == "added" and record["metoo"] == 1
    pressed_at = store.mine(DEV["m1"])[0]["metoo_at"]
    items = store.merged(T_STOP["id"])
    assert [(i["kind"], i["text"], i["into"]) for i in items] == [("metoo", NOTE["text"], x["id"])]

    own, original = store.separate(items[0]["id"], actor="op")

    assert own["text"] == NOTE["text"] and own["category"] == "lighting" and own["target"]["id"] == T_FAR["id"]
    assert own["created_at"] == pressed_at                # срок ответа — от момента, когда житель сообщил
    assert own["separated_from"] == x["id"] and own["status"] == "new" and own["demo"] is False
    assert original["id"] == x["id"] and original["metoo"] == 0
    mine = store.mine(DEV["m1"])
    assert [(m["id"], m["relation"]) for m in mine] == [(own["id"], "author")]   # теперь его собственная жалоба
    assert store.merged(T_STOP["id"]) == []
    with pytest.raises(Conflict):
        store.separate(items[0]["id"])                    # повтор — не вторая жалоба


def test_metoo_without_valid_note_still_counts(store):
    x = make(store, "a", "Разбит павильон остановки")
    record, result = store.metoo(x["id"], DEV["m1"], note={"text": "да", "point": STOP})
    assert result == "added" and record["metoo"] == 1
    assert store.merged(T_STOP["id"]) == []               # разделять нечего
    _, result = store.metoo(x["id"], DEV["a"], note=NOTE)   # автор — не «Я тоже», заметки нет
    assert result == "author" and store.merged(T_STOP["id"]) == []


def test_metoo_note_after_its_complaint_became_duplicate(store):
    x = make(store, "a", "Разбит павильон остановки")
    y = make(store, "b", "Сломан павильон на остановке")
    store.metoo(x["id"], DEV["m1"], note=NOTE)
    store.mark_duplicate(x["id"], y["id"])               # m1 скопирован в y
    assert people(store, y["id"]) == 3
    note_id = next(i["id"] for i in store.merged(T_STOP["id"]) if i["kind"] == "metoo")
    store.separate(note_id)
    assert people(store, y["id"]) == 2 and people(store, x["id"]) == 1   # m1 ушёл из обеих


def test_merged_lists_duplicates_with_codes(store):
    a = make(store, "a", "Разбит павильон остановки")
    b = make(store, "b", "Сломан павильон на остановке")
    store.mark_duplicate(a["id"], b["id"])
    items = store.merged(T_STOP["id"])
    assert len(items) == 1 and items[0]["kind"] == "duplicate" and items[0]["id"] == a["id"]
    assert items[0]["code"] == a["code"] and items[0]["into_code"] == b["code"] and items[0]["people"] == 1
    assert store.merged("osm-node-404") == []


# --------------------------------------------------------------------------- HTTP-слой R09
class Staff:
    is_staff = True
    username = "operator"

    @staticmethod
    def check_csrf(token):
        return token == "ok"


def call(service, method, path, body=None, principal=None, csrf=None, device=None):
    headers = {}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    if device:
        headers["X-Birge-Device"] = device
    path, _, query = path.partition("?")
    reply = service.handle(method, "/api/civic/v2" + path, query, json.dumps(body) if body is not None else None,
                           principal, {"headers": headers, "is_same_origin": True})
    return reply["status"], reply["body"]


def test_api_separate_is_staff_only(store):
    service = ComplaintsV2Service(store)
    x = make(store, "a", "Разбит павильон остановки")
    status, body = call(service, "POST", f"/complaints/{x['id']}/metoo", {"note": NOTE}, device=DEV["m1"])
    assert status == 200 and body["data"]["result"] == "added"
    status, body = call(service, "GET", f"/complaints/merged?target_id={T_STOP['id']}")
    assert status == 403
    status, body = call(service, "GET", f"/complaints/merged?target_id={T_STOP['id']}", principal=Staff())
    assert status == 200 and body["data"]["count"] == 1
    note_id = body["data"]["items"][0]["id"]
    assert call(service, "POST", f"/complaints/{note_id}/separate", {})[0] == 403
    assert call(service, "POST", f"/complaints/{note_id}/separate", {}, principal=Staff())[1]["error"]["code"] == "csrf_failed"
    status, body = call(service, "POST", f"/complaints/{note_id}/separate", {}, principal=Staff(), csrf="ok")
    assert status == 200 and body["data"]["complaint"]["text"] == NOTE["text"]
    assert body["data"]["original"]["metoo"] == 0
    status, body = call(service, "POST", f"/complaints/{note_id}/separate", {}, principal=Staff(), csrf="ok")
    assert status == 409


# --------------------------------------------------------------------------- журнал решений R04
def test_feedback_log_records_same_and_different(store, tmp_path):
    import ui.civic_ml_api as api
    from ml.civic_dedup.feedback import FeedbackLog

    log_path = tmp_path / "feedback.jsonl"
    api.connect_store(store, warm=False, feedback_path=log_path)
    a = make(store, "a", "Разбит павильон остановки, стекло на земле")
    b = make(store, "b", "На остановке разбито стекло павильона")
    store.mark_duplicate(a["id"], b["id"])
    store.separate(a["id"])
    rows = FeedbackLog(log_path).rows()
    assert [(r["decision"], r["source"], r["a"], r["b"]) for r in rows] == [
        ("same", "staff_duplicate", a["id"], b["id"]), ("different", "staff_separate", a["id"], b["id"])]
    assert all(isinstance(r["score"], float) and r["threshold"] and r["method"] for r in rows)
    assert "павильон" not in log_path.read_text(encoding="utf-8")     # тексты жителей в журнал не пишутся
    stats = api.status()["similar"]["feedback"]
    assert stats["same"] == 1 and stats["different"] == 1


def test_feedback_export_joins_texts_for_tune(store, tmp_path):
    from ml.civic_dedup.feedback import export_pairs

    a = make(store, "a", "Разбит павильон остановки, стекло на земле")
    b = make(store, "b", "На остановке разбито стекло павильона")
    rows = [{"a": a["id"], "b": b["id"], "decision": "same", "source": "staff_duplicate"},
            {"a": b["id"], "b": a["id"], "decision": "different", "source": "staff_separate"}]
    pairs = export_pairs(rows, store.db_path)
    assert len(pairs) == 1 and pairs[0]["same_incident"] is False   # последнее решение по паре главнее
    assert {pairs[0]["a"], pairs[0]["b"]} == {a["text"], b["text"]} and pairs[0]["split"] == "real"
