"""R15: раздел «Рядом» (волна 2 п. 4, владелец R08) — что в публичной ленте и как хранятся подписки жителя.

id устройства (birge.device) — ключ жителя к «Моим обращениям» R09 с его текстами. R09 и R06 хранят его только
хэшем; подписки «Рядом» должны так же (S27), и файл подписок не должен расти без предела от новых id.
"""

from __future__ import annotations

import json

import pytest

from r15_common import need_module, xfail

DEVICE = "device-r15-nearby-secret01"


@pytest.fixture()
def nearby():
    return need_module("ui.civic_akim.nearby")


@xfail("S27")
def test_subscriptions_file_has_no_raw_device_id(nearby, tmp_path):
    path = tmp_path / "subscriptions.json"
    nearby.subscribe(DEVICE, "district", "nura", path=path)
    assert nearby.subscriptions(DEVICE, path=path), "подписка не сохранилась"
    assert DEVICE not in path.read_text("utf-8")


@xfail("S27")
def test_subscriptions_have_a_global_cap(nearby, tmp_path, monkeypatch):
    monkeypatch.setattr(nearby, "MAX_DEVICES", 3, raising=False)
    path = tmp_path / "subscriptions.json"
    for i in range(3):
        nearby.subscribe("device-r15-nearby-cap%04d" % i, "district", "nura", path=path)
    with pytest.raises(Exception):
        nearby.subscribe("device-r15-nearby-cap9999", "district", "nura", path=path)


def test_subscription_validates_device_and_scope(nearby, tmp_path):
    path = tmp_path / "subscriptions.json"
    for device, scope, sid in (("short", "district", "nura"), (DEVICE, "everything", "nura"),
                               (DEVICE, "district", "../../etc"), (DEVICE, "item", "<script>")):
        with pytest.raises(Exception):
            nearby.subscribe(device, scope, sid, path=path)


def test_public_feed_has_no_personal_fields(nearby):
    feed = nearby.feed("nura")
    text = json.dumps(feed, ensure_ascii=False)
    for key in ('"device_id"', '"device_hash"', '"username"', '"phone"', '"author"', '"actor"'):
        assert key not in text, key
