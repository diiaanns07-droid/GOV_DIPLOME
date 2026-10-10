"""R09 раунд 14 (ночь): «сколько людей сообщили о том же на этом месте».

Демо R01 засевает у остановки три ОТДЕЛЬНЫЕ жалобы (не одну с «Я тоже»). Шаг «Я тоже» считает всех людей по месту и
категории (GET /complaints/summary), а «Мои обращения» — place_reporters: то же число, и после «исправлено» оно не
меняется. Отклонённые и дубли не считаются (люди дубля уже перенесены в исходную жалобу).
"""

import json
from datetime import datetime, timedelta

import pytest

from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service, record as rec

P = "/api/civic/v2"
STOP = {"kind": "object", "id": "osm-node-4109037549"}
POINT = [71.406553, 51.131155]


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 10, 18, 0, tzinfo=rec.ASTANA_TZ)

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    clock = Clock()
    store = ComplaintStore(tmp_path / "p.sqlite3", clock=clock)
    yield store, ComplaintsV2Service(store), clock
    store.close()


def create(store, device, category="lighting", text="Вечером на остановке нет света"):
    record, _ = store.create({"text": text, "category": category, "point": POINT, "target": dict(STOP)}, device)
    return record


def mine(api, device):
    reply = api.handle("GET", P + "/complaints/mine", None, None, None,
                       {"headers": {"X-Birge-Device": device}, "host_allowed": True, "is_same_origin": True})
    return {item["id"]: item for item in reply["body"]["data"]["items"]}


def test_place_reporters_counts_separate_complaints_like_the_metoo_step(setup):
    store, api, _ = setup
    a = create(store, "dev-aaaaaaaaaaaaaaaa")
    b = create(store, "dev-bbbbbbbbbbbbbbbb", text="Фонарь у остановки не горит")
    create(store, "dev-cccccccccccccccc", text="Аялдамада жарық жоқ")
    create(store, "dev-eeeeeeeeeeeeeeee", category="roads", text="Яма у остановки")          # другая категория
    rejected = create(store, "dev-ffffffffffffffff", text="Темно на остановке")
    store.set_status(rejected["id"], "rejected")                                               # отклонённая
    store.metoo(a["id"], "dev-dddddddddddddddd")

    summary = store.target_summary(STOP["id"], days=14, category="lighting")
    assert summary["complaints"] == 3 and summary["reporters"] == 4          # шаг «Я тоже»: 3 жалобы, 4 человека

    joined = mine(api, "dev-dddddddddddddddd")[a["id"]]
    assert joined["relation"] == "metoo" and joined["reporters"] == 2 and joined["place_reporters"] == 4
    assert mine(api, "dev-bbbbbbbbbbbbbbbb")[b["id"]]["place_reporters"] == 4
    assert mine(api, "dev-eeeeeeeeeeeeeeee").popitem()[1]["place_reporters"] == 1
    assert "text" not in joined                                                  # чужой текст не уходит

    for record in store.list(target_id=STOP["id"], category="lighting", status=rec.OPEN_STATUSES):
        store.set_status(record["id"], "fixed")
    after = mine(api, "dev-dddddddddddddddd")[a["id"]]
    assert after["status"] == "fixed" and after["place_reporters"] == 4         # после «исправлено» — то же число


def test_place_reporters_does_not_double_count_duplicates_or_old_complaints(setup):
    store, api, clock = setup
    old = create(store, "dev-0000000000000000", text="Темно на остановке")
    clock.now += timedelta(days=20)                                              # старая — вне ±14 дней
    a = create(store, "dev-aaaaaaaaaaaaaaaa")
    c = create(store, "dev-cccccccccccccccc", text="Аялдамада жарық жоқ")
    store.mark_duplicate(c["id"], a["id"])                                        # автор дубля переходит в «Я тоже»
    item = mine(api, "dev-aaaaaaaaaaaaaaaa")[a["id"]]
    assert item["reporters"] == 2 and item["place_reporters"] == 2
    assert mine(api, "dev-0000000000000000")[old["id"]]["place_reporters"] == 1
    assert store.place_reporters({"id": "x", "category": "lighting", "created_at": None, "target": dict(STOP)}) == 1


def test_place_reporters_is_in_the_mine_view_only(setup):
    store, api, _ = setup
    a = create(store, "dev-aaaaaaaaaaaaaaaa")
    reply = api.handle("GET", P + "/complaints/" + a["id"], None, None, None,
                       {"headers": {"X-Birge-Device": "dev-bbbbbbbbbbbbbbbb"}, "host_allowed": True, "is_same_origin": True})
    assert "place_reporters" not in json.dumps(reply["body"])
