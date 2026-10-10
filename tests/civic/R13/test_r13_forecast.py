"""R13 · прогноз проблемных территорий (прототип на синтетике): данные, генератор, модели, backtest, API.

Быстрые тесты работают на подмножестве территорий (детерминированность генератора по id это позволяет).
"""

import json
import math
import time

import pytest

from ml.civic_forecast import weather as wx
from ml.civic_forecast.backtest import run_one, summarize, results_markdown
from ml.civic_forecast.features import FeatureBuilder, MIN_ASOF, THRESHOLD
from ml.civic_forecast.history import (BASE, add_months, generate, load_categories, month_range, season)
from ml.civic_forecast.model import Forecaster, expected_counts, poisson_at_least, seasonal_ratios, sklearn_available, top_k
from ml.civic_forecast.reasons import render
from ml.civic_forecast.targets import KIND_TO_TARGET, load_targets


@pytest.fixture(scope="module")
def targets():
    return load_targets()


@pytest.fixture(scope="module")
def small(targets):
    # По 60 территорий каждого вида — быстро и с теми же значениями, что в полной истории.
    picked = []
    for kind in KIND_TO_TARGET:
        picked += [t for t in targets if t["kind"] == kind][:60]
    return generate(picked)


# --- территории и погода ------------------------------------------------------------------

def test_targets_are_real_osm_with_contract_kinds(targets):
    assert len(targets) > 2000
    ids = [t["id"] for t in targets]
    assert len(ids) == len(set(ids))
    for t in targets:
        assert t["target_kind"] in ("object", "segment", "area")
        assert t["district"] in ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
        lon, lat = t["point"]
        assert 71.1 < lon < 71.9 and 50.9 < lat < 51.4
        if t["kind"] == "segment":
            assert t["id"].startswith("osm-w") and t["target_kind"] == "segment"
        elif t["kind"] == "yard":
            assert t["id"].startswith("yard-")
        else:
            assert t["id"].startswith(("osm-node-", "osm-way-", "osm-relation-"))


def test_weather_fixture_is_marked_synthetic_and_parses_open_meteo_format(tmp_path):
    rows, meta = wx.load_daily(wx.FIXTURE_PATH)
    assert meta["evidence_type"] == "synthetic" and rows[0]["date"] == "2023-01-01"
    raw = ("latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation\n"
           "51.13,71.43,350.0,18000,Asia/Almaty,GMT+5\n\n"
           "time,temperature_2m_max (°C),temperature_2m_min (°C),precipitation_sum (mm),snowfall_sum (cm),"
           "rain_sum (mm),wind_speed_10m_max (km/h)\n"
           "2024-01-01,-10.0,-21.5,1.2,0.84,0.0,20.1\n2024-01-02,1.5,-3.0,,0.0,0.0,15.0\n")
    path = tmp_path / "openmeteo_daily.csv"
    path.write_text(raw, encoding="utf-8")
    rows2, meta2 = wx.load_daily(path)
    assert meta2["evidence_type"] == "real" and len(rows2) == 2
    assert rows2[0]["temperature_2m_min"] == -21.5 and rows2[1]["precipitation_sum"] is None
    month = wx.monthly(rows2)["2024-01"]
    assert month["frost_days"] == 1 and month["thaw_days"] == 1 and month["complete"] is False


def test_normals_use_only_past_years():
    rows, _ = wx.load_daily(wx.FIXTURE_PATH)
    table = wx.monthly(rows)
    norm = wx.normals(table, 11, "2025-11")
    assert norm["years"] == 2  # ноябрь 2023 и 2024; ноябрь 2025 — будущее для прогноза на 2025-11
    assert wx.normals(table, 11, "2023-11")["years"] == 0


# --- генератор --------------------------------------------------------------------------

def test_history_is_deterministic_and_marked(targets):
    sub = targets[:40]
    a, b = generate(sub), generate(sub)
    assert a.counts == b.counts and a.evidence_type == "synthetic"
    assert a.summary()["demo"] is True
    assert a.months[0] == "2024-01" and a.months[-1] == "2026-10" and len(a.months) == 34
    other = generate(sub, seed=7)
    assert other.counts != a.counts


def test_subset_values_match_full_history(targets, small):
    full_one = generate([small.targets[5]])
    assert full_one.counts[small.targets[5]["id"]] == small.counts[small.targets[5]["id"]]


def test_seasonality_snow_winter_waste_summer_heating_october(small):
    cats, _ = load_categories()
    ci = {c: i for i, c in enumerate(cats)}

    def by_month(cat, months):
        return sum(small.counts[t["id"]][small.months.index(m)][ci[cat]] for t in small.targets for m in months)

    assert by_month("snow_ice", ["2025-01", "2025-02"]) > 5 * by_month("snow_ice", ["2025-07", "2025-08"])
    assert by_month("waste", ["2025-07", "2025-08"]) > 1.5 * by_month("waste", ["2025-01", "2025-02"])
    assert by_month("utilities", ["2025-10"]) > 1.8 * by_month("utilities", ["2025-08"])
    assert by_month("roads", ["2025-04"]) > 1.8 * by_month("roads", ["2025-01"])


def test_season_reacts_to_weather():
    calm = {"snowfall_cm": 2, "thaw_days": 1, "frost_days": 0, "hot_days": 0}
    snowy = {"snowfall_cm": 30, "thaw_days": 10, "frost_days": 0, "hot_days": 0}
    assert season("snow_ice", "2025-12", snowy, None) > 3 * season("snow_ice", "2025-12", calm, None)
    assert season("smell_air", "2025-07", {**calm, "hot_days": 10}, None) > season("smell_air", "2025-07", calm, None)


def test_hot_places_persist_and_constructions_raise_roads(small):
    hot_months = [sum(flags) for flags in small.hot.values()]
    assert any(n >= 3 for n in hot_months)  # горячие эпизоды длятся месяцами
    assert small.constructions and all(c.start <= c.end for c in small.constructions)


def test_records_follow_contract_shape(small):
    from ml.civic_forecast.history import to_records
    recs = to_records(small, "2025-02", limit=20)
    assert recs and all(r["demo"] is True and r["target"]["kind"] in ("object", "segment", "area") for r in recs)
    assert {"id", "created_at", "text", "category", "point", "target", "district", "status"} <= set(recs[0])


# --- признаки и модели -------------------------------------------------------------------

def test_features_do_not_look_into_the_future(small):
    fb = FeatureBuilder(small)
    asof = small.months.index("2025-05")
    tid = small.targets[0]["id"]
    before = fb.row(tid, asof)
    # Меняем будущее (месяцы после asof) — признаки на asof не должны измениться.
    for mi in range(asof + 1, len(small.months)):
        small.counts[tid][mi] = [99] * len(small.categories)
    fb2 = FeatureBuilder(small)
    assert fb2.row(tid, asof) == before
    assert len(before) == len(fb.names)


def test_feature_names_cover_spec(small):
    names = FeatureBuilder(small).names
    for n in ("tot_1", "tot_3", "tot_12", "tot_ly", "trend_3", "snow_ice_1", "utilities_ly", "w_norm_snowfall_cm",
              "w_last_thaw_days", "construction_next", "kind_yard", "district_nura", "month_sin"):
        assert n in names
    with pytest.raises(ValueError):
        FeatureBuilder(small).matrix(MIN_ASOF - 1)


def test_poisson_tail():
    assert poisson_at_least(0, 4) == 0.0
    assert abs(poisson_at_least(4.0, 1) - (1 - math.exp(-4))) < 1e-12
    assert poisson_at_least(10, 4) > poisson_at_least(2, 4)


def test_seasonal_ratios_without_future(small):
    upto = small.months.index("2025-06")
    r1 = seasonal_ratios(small, upto)
    tid = small.targets[0]["id"]
    small.counts[tid][upto + 1] = [500] * len(small.categories)
    assert seasonal_ratios(small, upto) == r1


@pytest.mark.parametrize("kind", ["fallback", "last_month", "same_month_ly"] + (["gbm"] if sklearn_available() else []))
def test_models_score_every_territory(small, kind):
    asof = small.months.index("2025-11")
    model = Forecaster(kind).fit(small, asof - 1)
    scores = model.score(small, asof)
    assert set(scores) == {t["id"] for t in small.targets}
    assert all(math.isfinite(v) and v >= 0 for v in scores.values())
    top = top_k(scores, small, asof, 10)
    assert len(top) == 10 and top == top_k(scores, small, asof, 10)


def test_fallback_runs_without_sklearn(small, monkeypatch):
    import ml.civic_forecast.model as m
    monkeypatch.setattr(m, "sklearn_available", lambda: False)
    with pytest.raises(ImportError):
        m.Forecaster("gbm")
    asof = small.months.index("2026-01")
    assert m.Forecaster("fallback").fit(small, asof - 1).score(small, asof)


def test_backtest_table_and_honest_markdown(small):
    run = run_one(small, first_forecast="2026-07", models=["fallback", "last_month", "same_month_ly"])
    assert [r["month"] for r in run["months"]] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    s = summarize([run])
    for m in s["models"]:
        for k in (10, 20, 30):
            assert 0.0 <= s["mean"][m][k] <= 1.0
    md = results_markdown(s, {"targets": len(small.targets), "months": ["2024-01", "2026-10"],
                              "weather": {"evidence_type": "synthetic", "source": "фикстура"}, "threshold": THRESHOLD,
                              "forecast_months": ["2026-07", "2026-10"], "seeds": [2026], "env": "test"})
    assert "НА СИНТЕТИКЕ" in md and "precision@K" in md and "Случайный выбор" in md


# --- причины -------------------------------------------------------------------------------

@pytest.mark.parametrize("reason,ru,kk", [
    ({"key": "forecast.reason.same_month_ly", "params": {"category": "snow_ice", "n": 12, "month": "2025-02"}},
     "«Снег и гололёд»: 12 жалоб в феврале прошлого года", "«Қар және көктайғақ»: өткен жылы ақпанда 12 шағым"),
    ({"key": "forecast.reason.same_month_ly", "params": {"category": "roads", "n": 1, "month": "2025-04"}},
     "«Дороги»: 1 жалоба в апреле прошлого года", "«Жолдар»: өткен жылы сәуірде 1 шағым"),
    ({"key": "forecast.reason.streak", "params": {"n": 3}}, "Проблема держится 3 месяца подряд",
     "Мәселе 3 ай қатарынан сақталып тұр"),
    ({"key": "forecast.reason.recent_3m", "params": {"n": 21}}, "За последние 3 месяца — 21 жалоба", "Соңғы 3 айда — 21 шағым"),
    ({"key": "forecast.reason.climate_snow", "params": {"month": "2026-11", "cm": 24, "years": 3}},
     "В ноябре обычно снег: 24 см за месяц (норма за 3 г.)", "Қарашада әдетте қар жауады: айына 24 см (3 жылдың нормасы)"),
    ({"key": "forecast.reason.construction", "params": {"start": "2026-09", "end": "2027-03"}},
     "Рядом стройка по плану: сентябрь 2026 — март 2027", "Жанында жоспарлы құрылыс: қыркүйек 2026 — наурыз 2027"),
])
def test_reason_texts_ru_kk(reason, ru, kk):
    assert render(reason, "ru") == ru
    assert render(reason, "kk") == kk


# --- API -----------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api():
    import ui.civic_forecast as api
    from ui.civic_forecast.build import CACHE_PATH
    if not CACHE_PATH.is_file():
        pytest.skip("нет кэша прогноза: python3 -m ml.civic_forecast build-cache")
    return api


def test_forecast_shape_and_speed(api):
    api.forecast("2026-11", None, 1)  # загрузка кэша
    t0 = time.perf_counter()
    items = api.forecast("2026-11", "nura", 30)
    elapsed = (time.perf_counter() - t0) * 1000
    assert elapsed < 300, f"{elapsed:.0f} мс"
    assert len(items) == 30 and all(i["district"] == "nura" for i in items)
    risks = [i["risk"] for i in items]
    assert risks == sorted(risks, reverse=True)
    for i in items:
        assert set(i["target"]) == {"kind", "id", "label_ru", "label_kk"}
        assert 0 <= i["risk"] <= 1 and i["level"] in ("high", "medium", "low")
        assert 1 <= len(i["top_reasons"]) <= 3
        for r in i["top_reasons"]:
            assert r["ru"] and r["kk"] and r["key"].startswith("forecast.reason.")
            assert "{" not in r["ru"] + r["kk"]


def test_cold_load_under_300ms(api, monkeypatch):
    monkeypatch.setattr(api, "_cache", None)
    t0 = time.perf_counter()
    api.forecast("2026-11", None, 10)
    assert (time.perf_counter() - t0) * 1000 < 300


def test_response_is_marked_synthetic_and_validates(api):
    data = api.forecast_response("2026-11", None, 10)
    assert data["evidence_type"] == "synthetic" and data["demo"] is True and len(data["items"]) == 10
    json.dumps(data, allow_nan=False)
    for bad in ({"month": "2026-13"}, {"district": "mars"}, {"k": 0}, {"k": 51}, {"k": "x"}):
        with pytest.raises(api.ForecastError) as exc:
            api.forecast_response(**bad)
        assert exc.value.status == 400


def test_attention_block_for_r08(api):
    from datetime import date
    block = api.attention_next_month(None, 5, today=date(2026, 10, 11))
    assert block["month"] == "2026-11" and len(block["items"]) == 5 and block["demo"] is True
    assert all(len(i["reasons"]) <= 2 for i in block["items"])


def test_score_month_fallback_without_sklearn(small):
    from ui.civic_forecast.build import score_month
    block = score_month(small, "2026-10", model_kind="fallback")
    assert block["model"] == "fallback" and block["check"] is not None
    assert len(block["rank_city"]) == 60 and set(block["rank_district"]) == {
        "almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"}
    first = block["items"][block["rank_city"][0]]
    assert "confirmed" in first and first["reasons"]
