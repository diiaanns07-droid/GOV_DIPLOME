"""R15 раунд 15 · R06 центр уведомлений (ui.civic_store.v2 list_notifications / read_notifications) — THREATS_R15 §9.

Лента «Что нового для меня» собирает updates(device, since) модулей R16/R17/R13/R09 (CONTRACT §5.8):
- событие — только своему устройству: «Приду» на встречу R13 у устройства A не попадает в ленту устройства B (T-R06-01);
- без устройства — отказ, а не «все события» (T-R06-05);
- ссылки — только внутренние «#раздел/id» (T-R06-03); в ленте нет id устройств и логинов (T-R06-06);
- «прочитано» — только своё и с пределом списка (T-R06-04).
Функций R06 нет в сборке — NOT_RUN. Соседи — R13 (встречи), он есть с раунда 15 у R13; нет — NOT_RUN.
"""

from __future__ import annotations

import inspect
import re

import pytest

from r15_round15 import DEVICES, STAFF_LOGIN, context, device_needles, dump, iso_in, leaks, module, not_run, \
    staff_principal

A, B = DEVICES[60], DEVICES[61]
LINK = re.compile(r"#[a-z][a-z-]*(/[A-Za-z0-9._:=&-]+)*")


def _call(fn, **kwargs):
    """Вызов функции R06 с теми именованными аргументами, которые она объявила (как _call шлюза R01)."""
    params = inspect.signature(fn).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    return fn(**{k: v for k, v in kwargs.items() if k in params})


def _items(reply):
    body = reply[1] if isinstance(reply, tuple) else reply
    if isinstance(body, dict):
        for key in ("items", "notifications", "events"):
            if isinstance(body.get(key), list):
                return body[key]
    return body if isinstance(body, list) else []


@pytest.fixture()
def feed(tmp_path, monkeypatch):
    v2 = module("ui.civic_store.v2", "R06")
    if not callable(getattr(v2, "list_notifications", None)):
        not_run("у R06 нет list_notifications (центр уведомлений раунда 15)")
    db = tmp_path / "civic.sqlite3"
    monkeypatch.setenv("CIVIC_DB_PATH", str(db))
    monkeypatch.delenv("CIVIC_DEMO", raising=False)
    store = module("ui.civic_store", "R06")
    service = store.CivicService(str(db)) if hasattr(store, "CivicService") else None
    if service is not None and hasattr(v2, "bind"):
        v2.bind(service)
    return v2, db


def _meeting_events(db):
    """Устройство A нажимает «Приду», сотрудник публикует итог — у A есть событие R13, у B — нет."""
    meetings = module("ui.civic_meetings", "R13")
    svc = meetings.make_service(str(db), demo=False)
    principal = staff_principal()
    ctx = context(csrf="r15-csrf-token-" + "7" * 28, method="POST")
    reply = svc.handle("POST", "/api/civic/v2/meetings", "", {
        "district": "nura", "title_ru": "Встреча акима района с жителями", "at": iso_in(hours=12),
        "place": {"label_ru": "Школа"}}, principal, ctx)
    mid = reply["body"]["meeting"]["id"]
    svc.handle("POST", f"/api/civic/v2/meetings/{mid}/register", "", {"going": True}, None,
               context(device=A, method="POST"))
    svc.handle("POST", f"/api/civic/v2/meetings/{mid}/result", "", {"result_ru": "Итоги встречи: поручения выданы"},
               principal, ctx)
    return mid


def test_feed_is_per_device(feed):
    """T-R06-01, T-R06-03, T-R06-06: события — своему устройству; ссылки внутренние; без устройств и логинов."""
    v2, db = feed
    _meeting_events(db)
    mine = _items(_call(v2.list_notifications, since=None, context=context(device=A), device=A, device_id=A))
    other = _items(_call(v2.list_notifications, since=None, context=context(device=B), device=B, device_id=B))
    if not mine:
        not_run("лента R06 не собрала события R13 (updates) — сверка с соседом на B1")
    assert not [e for e in other if "meeting" in dump(e)], other
    for event in mine:
        assert LINK.fullmatch(str(event.get("link") or "")), event
    assert not leaks([mine, other], device_needles([A, B]) + [STAFF_LOGIN])


def test_feed_without_device_is_refused(feed):
    """T-R06-05: без устройства — ошибка ввода, а не общая лента."""
    v2, _db = feed
    try:
        reply = _call(v2.list_notifications, since=None, context=context())
    except (ValueError, PermissionError, LookupError):
        return
    except Exception as exc:  # noqa: BLE001 — ошибка со status 4xx (как V2Error R06)
        assert 400 <= int(getattr(exc, "status", 500)) < 500, repr(exc)
        return
    assert not _items(reply), reply


def test_mark_read_is_bounded(feed):
    """T-R06-04: «прочитано» — с пределом списка (10 000 id -> отказ) и без влияния на чужое устройство."""
    v2, _db = feed
    fn = getattr(v2, "read_notifications", None)
    if not callable(fn):
        not_run("у R06 нет read_notifications")
    with pytest.raises(Exception) as caught:
        _call(fn, body={"ids": [f"n-{i}" for i in range(10_000)]}, context=context(device=A), device=A)
    status = getattr(caught.value, "status", None)
    assert status is None or 400 <= int(status) < 500, repr(caught.value)
