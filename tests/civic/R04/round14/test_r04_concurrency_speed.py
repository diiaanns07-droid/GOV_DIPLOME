"""Одновременные запросы из потоков сервера и скорость (prompts/R04.txt п. 3–4)."""

import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import ui.civic_ml_api as api
from ml.civic_dedup import fixtures as F
from ml.civic_dedup import loader

from conftest import NOW, STOP, record

TEXTS = ["Во дворе не горят фонари", "Аялдамада қар тазаланбаған", "Yama na doroge", "Лифт не работает",
         "Мусор не вывозят", "", "Не убран снег на остановке, люди падают"]


def test_parallel_classify_and_similar_from_cold_start():
    """32 потока одновременно с холодного старта: без ошибок, ответы как в одном потоке, модели грузятся один раз."""
    recs = [record(f"c-par{i:05d}", "Аялдамада қар тазаланбаған", point=F.offset(STOP, i, 0), metoo=i % 3)
            for i in range(50)]
    api.set_complaint_source(api.records_source(recs, clock=lambda: NOW))
    expected_cls = {t: api.classify(t) for t in TEXTS}
    expected_sim = api.similar("Не убран снег на остановке", point=list(STOP))
    api.reset()
    api.set_complaint_source(api.records_source(recs, clock=lambda: NOW))
    built = {"n": 0}
    real_build = loader._build

    def counting_build(conf):
        built["n"] += 1
        time.sleep(0.05)  # медленная загрузка: шанс гонки, если блокировки нет
        return real_build(conf)

    loader._build = counting_build
    barrier = threading.Barrier(32)
    errors = []

    def work(i):
        try:
            barrier.wait(timeout=10)
            for k in range(20):
                t = TEXTS[(i + k) % len(TEXTS)]
                assert api.classify(t) == expected_cls[t]
                if k % 4 == 0:
                    res = api.similar("Не убран снег на остановке", point=list(STOP))
                    assert res["matches"] == expected_sim["matches"]
        except Exception as exc:  # noqa: BLE001 — собираем любые ошибки потоков
            errors.append(repr(exc))

    try:
        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(work, range(32)))
    finally:
        loader._build = real_build
    assert errors == []
    assert built["n"] == 1


def _p95(values):
    values = sorted(values)
    return values[int(round(0.95 * (len(values) - 1)))]


SLOW_FACTOR = float(os.environ.get("R04_SPEED_FACTOR", "1"))  # медленный CI: R04_SPEED_FACTOR=3


def test_classify_speed_under_50ms():
    api.classify("прогрев")
    ms = []
    for i in range(200):
        t0 = time.perf_counter()
        api.classify(TEXTS[i % len(TEXTS)] + f" {i}")
        ms.append((time.perf_counter() - t0) * 1000)
    assert _p95(ms) <= 50 * SLOW_FACTOR, f"p95 {_p95(ms):.1f} мс"


@pytest.mark.parametrize("scenario", ["city", "hotspot"])
def test_similar_speed_5000_under_150ms(scenario):
    kw = {"hotspot": F.NURA_CENTER, "n_targets": 50} if scenario == "hotspot" else {}
    recs = F.make_records(5000, now=NOW, **kw)
    api.set_complaint_source(api.records_source(recs, clock=lambda: NOW))
    phrases = [t for ts in F.PHRASES.values() for t in ts]
    centre = F.NURA_CENTER if scenario == "hotspot" else None
    ms = []
    for i in range(40):
        point = list(centre) if centre else recs[i * 97 % len(recs)]["point"]
        t0 = time.perf_counter()
        api.similar(phrases[i % len(phrases)], point=point, days=14)
        ms.append((time.perf_counter() - t0) * 1000)
    warm = ms[1:]  # первый запрос заполняет кэш признаков (см. bench.py: first_query_ms)
    assert _p95(warm) <= 150 * SLOW_FACTOR, f"{scenario}: p95 {_p95(warm):.1f} мс, медиана {statistics.median(warm):.1f}"
