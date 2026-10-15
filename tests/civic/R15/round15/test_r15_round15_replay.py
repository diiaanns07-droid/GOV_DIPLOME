"""R15 раунд 15 · R07 «Хроника города» (GET heat/replay, ui.civic_heat.api.handle_get) — THREATS_R15 T-R07-01.

Маршрут открыт всем и тяжёлый (кадр на каждый день той же формулой): один запрос не должен занимать сервер.
- период длиннее квартала, старее года, шаг не «день», мусор в датах/районе/категории/формате -> 400 сразу;
- обычный запрос — быстро и с ограниченным числом кадров.
Нет heat/replay в сборке — NOT_RUN.
"""

from __future__ import annotations

import time

import pytest

from r15_round15 import XSS, module, not_run

PATH = "/api/civic/v2/heat/replay"


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    api = module("ui.civic_heat.api", "R07")
    if "replay" not in (api.__doc__ or "") and not hasattr(module("ui.civic_heat", "R07"), "replay"):
        not_run("в ui.civic_heat нет heat/replay (R07 раунда 15)")
    return lambda query: api.handle_get(PATH, {k: [v] for k, v in query.items()})


@pytest.mark.parametrize("query", [
    {"from": "2025-01-01", "to": "2026-10-15"}, {"from": "1900-01-01", "to": "1900-01-02"},
    {"from": "2026-10-15", "to": "2026-10-01"}, {"from": "2026-13-45"}, {"step": "hour"}, {"step": "minute"},
    {"days": "100000"}, {"days": "-5"}, {"district": XSS}, {"category": "x" * 5000}, {"format": "xml"},
])
def test_replay_rejects_heavy_or_bad_requests_fast(replay, query):
    """T-R07-01: тяжёлый или кривой запрос — 400 без расчёта (быстро)."""
    started = time.perf_counter()
    status, body = replay(query)
    assert status == 400, (query, status, str(body)[:200])
    assert time.perf_counter() - started < 0.5


def test_replay_default_is_bounded(replay):
    """Обычная хроника: ответ ограничен по кадрам (≤ 92) и по времени (< 5 с даже на холодном кэше)."""
    started = time.perf_counter()
    status, body = replay({})
    assert status == 200, body
    assert len(body.get("frames") or []) <= 92
    assert time.perf_counter() - started < 5
