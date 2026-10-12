"""Стенд R07 (ui/civic_heat/devserver.py): подставной ответ жителя «Проблема решена?» (двойник R09 /verify).

Служба отмечает все открытые жалобы места исправленными → «служба сообщила»; житель отвечает «да» → «проверено
жителями». Данные синтетические, только в памяти стенда.
"""
from ui.civic_heat import api
from ui.civic_heat.devserver import DemoStore


def _items(store):
    status, body = api.handle_get(api.PREFIX + "/heat", {"days": ["30"], "zoom": ["15"]}, service=store.service)
    assert status == 200
    return (body.get("data") or body)["items"]


def _item(store, key):
    return next(it for it in _items(store) if (it["target"]["kind"], it["target"]["id"]) == key)


def test_verify_turns_reported_place_into_verified():
    store = DemoStore()
    place = next(it for it in _items(store) if it["state"] == "active" and it.get("open_ids"))
    key = (place["target"]["kind"], place["target"]["id"])
    first = place["open_ids"][0]
    assert store.verify(first, "yes")[0] == 409          # ещё не исправлена — отвечать не на что
    for cid in place["open_ids"]:
        assert store.set_status(cid, "fixed")[0] == 200
    it = _item(store, key)
    assert (it["state"], it["fixed_kind"]) == ("fixed", "reported")
    assert store.verify(first, "maybe")[0] == 400
    assert store.verify("нет-такой", "yes")[0] == 404
    assert store.verify(first, "yes")[0] == 200
    it = _item(store, key)
    assert (it["state"], it["fixed_kind"]) == ("fixed", "verified")


def test_verify_no_reopens_place():
    store = DemoStore()
    place = next(it for it in _items(store) if it["state"] == "active" and it.get("open_ids"))
    key = (place["target"]["kind"], place["target"]["id"])
    for cid in place["open_ids"]:
        store.set_status(cid, "fixed")
    assert store.verify(place["open_ids"][0], "no")[0] == 200
    it = _item(store, key)
    assert it["state"] == "active" and it.get("reopened")
