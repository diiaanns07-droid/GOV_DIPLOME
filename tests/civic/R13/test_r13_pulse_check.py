"""R13 · проверка метода «Пульса» R08 (ml/civic_forecast/pulse_check.py): вероятности и правило «не случайно ли».

Сама оценка на потоках зовёт модуль R08 (ui.civic_akim.pulse) — без него тест прогона пропускается.
"""

from __future__ import annotations

import importlib.util
import math

import pytest

from ml.civic_forecast import pulse_check as pc


def exact_binom_tail(k, n, q):
    return sum(math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(k, n + 1))


@pytest.mark.parametrize("k, lam", [(0, 2.0), (1, 0.5), (5, 2.5), (9, 3.0), (20, 4.0)])
def test_poisson_tail_matches_definition(k, lam):
    exact = 1 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k))
    assert pc.poisson_tail(k, lam) == pytest.approx(max(0.0, exact), abs=1e-12)


@pytest.mark.parametrize("k, n, q", [(8, 18, 0.2), (12, 24, 0.2), (6, 6, 0.2), (1, 10, 0.5), (11, 10, 0.2)])
def test_binom_tail_matches_definition(k, n, q):
    assert pc.binom_tail(k, n, q) == pytest.approx(exact_binom_tail(k, n, q) if k <= n else 0.0)


def test_surprise_ranks_weeks_as_the_akim_would():
    # 12 при обычных 3 — редкость; 8 при обычных 2,5 — «бывает» (1,6 % недель); новая тема 6 при 0 — редкость.
    assert pc.surprise(12, 3.0, 4, "binomial") < 0.01 < pc.surprise(8, 2.5, 4, "binomial") < 0.05
    assert pc.surprise(6, 0.0, 4, "binomial") == pytest.approx(0.2 ** 6)
    # binomial строже poisson: обычный уровень посчитан по 4 неделям и сам шумит
    assert pc.surprise(9, 3.0, 4, "binomial") > pc.surprise(9, 3.0, 4, "poisson")


def test_guard_keeps_city_alarm_if_any_district_is_surprising():
    city = {"kind": "spike_city", "weeks": 4, "districts": [
        {"district": "nura", "value": 10, "ratio": 5.0}, {"district": "esil", "value": 9, "ratio": 3.0}]}
    assert pc.guard(city)
    weak = {"kind": "spike_city", "weeks": 4, "districts": [{"district": "esil", "value": 8, "ratio": 3.2}]}
    assert not pc.guard(weak)
    assert pc.guard({"kind": "metoo", "value": 9})  # «Я тоже» и новые горячие места проверка не трогает
    assert pc.guard({"kind": "new_hot", "value": 6})


def test_covered_pairs_of_alarms():
    assert pc.covered({"kind": "spike", "district": "nura", "category": "waste"}) == {("nura", "waste")}
    city = {"kind": "spike_city", "category": "snow_ice", "districts": [{"district": "nura"}, {"district": "esil"}]}
    assert pc.covered(city) == {("nura", "snow_ice"), ("esil", "snow_ice")}


def test_saved_results_show_the_tradeoff():
    """results_pulse.json (200 недель на клетку): проверка снижает ложные тревоги, сильные всплески находятся."""
    import json
    data = json.loads((pc.HERE / "results_pulse.json").read_text(encoding="utf-8"))
    assert data["evidence_type"] == "synthetic"
    city = [v for v in data["results"].values() if v["scale"] == "city"]
    quiet = [v for v in city if v["factor"] == 1.0]
    strong = [v for v in city if v["factor"] == 5.0]
    assert all(v["binomial"]["false_per_week"] < v["r08"]["false_per_week"] / 4 for v in quiet)
    assert all(v["binomial"]["recall"] >= 0.85 for v in strong)


@pytest.mark.skipif(importlib.util.find_spec("ui.civic_akim") is None, reason="нужен модуль R08 ui.civic_akim (сборка R01)")
def test_run_on_r08_module_small():
    old = pc.MONTHS, pc.SCALES
    pc.MONTHS, pc.SCALES = ("2026-01",), {"city": 1.0}
    try:
        report = pc.run(trials=5)
    finally:
        pc.MONTHS, pc.SCALES = old
    assert set(report["results"]) == {"city:2026-01:x1", "city:2026-01:x2", "city:2026-01:x3", "city:2026-01:x5"}
