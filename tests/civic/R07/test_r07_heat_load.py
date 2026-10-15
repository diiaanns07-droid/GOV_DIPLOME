"""R07 раунд 15 · R10 B-124: первая загрузка карты — районы (zoom 0) и места (zoom 14) одним расчётом.

Страница при загрузке спрашивает /heat/meta, районы и места одновременно. Раньше районы и места считались дважды и
параллельно (под общей нагрузкой сервера — 1,6–2 с каждый); теперь один расчёт мест на (данные, период, фильтры,
минуту), второй одновременный запрос ждёт первый. Плюс warm_up() для R01 — тем же циклом, что прогрев R03 / R16.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import ui.civic_heat as civic_heat
from ui.civic_heat import HeatService, demo_seed, engine, service as heat_service
from ui.civic_heat.targets import TargetResolver

TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 15, 16, 0, tzinfo=TZ)


def make_svc():
    records = demo_seed.demo_records(NOW)
    return HeatService(source=lambda since: [r for r in records if engine.parse_time(r["created_at"]) >= since],
                       resolver=TargetResolver(graph_path=None, use_r12=False), clock=lambda: NOW)


def counting(svc, delay=0.0):
    calls = []
    real = svc._compute

    def wrapped(**kw):
        calls.append(kw)
        if delay:
            time.sleep(delay)
        return real(**kw)

    svc._compute = wrapped
    return calls


def test_districts_and_places_share_one_computation():
    svc = make_svc()
    calls = counting(svc)
    districts = svc.heat(days=30, zoom=0)
    places = svc.heat(days=30, zoom=14)
    assert len(calls) == 1
    assert districts["mode"] == "districts" and places["mode"] == "targets"
    assert {it["target"]["kind"] for it in districts["items"]} == {"district"}
    assert places["items"] and all(it["target"]["kind"] != "district" for it in places["items"])
    # те же числа, что у двух отдельных расчётов
    fresh = make_svc()
    assert fresh.heat(days=30, zoom=14)["items"] == places["items"]
    fresh2 = make_svc()
    assert fresh2.heat(days=30, zoom=0)["items"] == districts["items"]


def test_simultaneous_requests_compute_once():
    svc = make_svc()
    calls = counting(svc, delay=0.3)        # медленный расчёт: второй запрос приходит, пока первый ещё считает
    out = {}

    def ask(zoom):
        out[zoom] = svc.heat(days=30, zoom=zoom)

    threads = [threading.Thread(target=ask, args=(z,)) for z in (0, 14)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(calls) == 1
    assert out[0]["mode"] == "districts" and out[14]["mode"] == "targets"


def test_invalidate_and_other_filters_compute_again():
    svc = make_svc()
    calls = counting(svc)
    svc.heat(days=30, zoom=0)
    svc.heat(days=30, zoom=14, category="snow_ice")          # другой фильтр — свой расчёт
    assert len(calls) == 2
    svc.invalidate()                                          # новая жалоба / «Я тоже» — общий расчёт сброшен
    svc.heat(days=30, zoom=14)
    assert len(calls) == 3


def test_failed_computation_does_not_block_the_waiting_request():
    svc = make_svc()
    real = svc._compute
    state = {"n": 0}

    def flaky(**kw):
        state["n"] += 1
        if state["n"] == 1:
            time.sleep(0.2)
            raise RuntimeError("источник упал")
        return real(**kw)

    svc._compute = flaky
    errors, out = [], {}

    def ask(zoom):
        try:
            out[zoom] = svc.heat(days=30, zoom=zoom)
        except RuntimeError as e:
            errors.append(str(e))

    first = threading.Thread(target=ask, args=(0,))
    first.start()
    time.sleep(0.05)
    second = threading.Thread(target=ask, args=(14,))
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert errors == ["источник упал"]                         # ошибка — у того, кто считал
    assert out[14]["mode"] == "targets" and out[14]["items"]   # ждавший не завис и посчитал сам


def test_warm_up_fills_the_cache_for_the_first_page(monkeypatch):
    svc = make_svc()
    monkeypatch.setattr(heat_service, "_default", svc)
    civic_heat.warm_up()
    calls = counting(svc)
    svc.heat(days=30, zoom=0)
    svc.heat(days=30, zoom=14.5)
    assert calls == []                                       # оба вида — из прогрева


def test_warm_up_never_raises(monkeypatch):
    svc = make_svc()

    def boom(**kw):
        raise RuntimeError("нет базы")

    svc._compute = boom
    monkeypatch.setattr(heat_service, "_default", svc)
    civic_heat.warm_up("лишний аргумент от R01")           # R01 может передать аргументы, как R16 (db_path)
