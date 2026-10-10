"""Поиск дублей ml/civic_dedup: правило «текст ≥ порога И (та же цель ИЛИ ≤ 200 м) И за N дней»."""

import json

import pytest

from ml.civic_dedup import config as C
from ml.civic_dedup import get_deduper, loader
from ml.civic_dedup.fixtures import offset
from ml.civic_dedup.geo import bbox_around, distance_m, parse_point
from ml.civic_dedup.scorers import NgramConceptScorer
from ml.civic_dedup.search import Deduper, FeatureCache, clamp_days

from conftest import NOW, STOP, record

SNOW = "Не убран снег на остановке, люди падают"


@pytest.fixture
def dd():
    return get_deduper()


def find(dd, text, recs, **kw):
    kw.setdefault("point", STOP)
    return dd.find(text, recs, now=NOW, **kw)


def test_paraphrase_nearby_is_found(dd):
    recs = [record("c-aaaaaa01", "На остановке не чистят снег, скользко", point=offset(STOP, 80, 0), metoo=6)]
    m = find(dd, SNOW, recs)
    assert [x.complaint_id for x in m] == ["c-aaaaaa01"]
    assert m[0].as_dict()["people"] == 7 and m[0].distance_m == pytest.approx(80, abs=1)


def test_russian_kazakh_paraphrase_is_found(dd):
    recs = [record("c-aaaaaa02", "Аялдамада қар тазаланбаған, адамдар құлап жатыр")]
    assert find(dd, SNOW, recs)


def test_kazakh_without_special_letters_is_found(dd):
    recs = [record("c-aaaaaa03", "Аялдамада қар тазаланбаған, тайғақ")]
    assert find(dd, "Аялдамада кар тазаланбаган, тайгак", recs)


def test_translit_is_found(dd):
    recs = [record("c-aaaaaa04", SNOW)]
    assert find(dd, "Ne ubran sneg na ostanovke", recs)


def test_other_problem_same_place_is_not_a_duplicate(dd):
    recs = [record("c-aaaaaa05", "На остановке сломана скамейка, негде сесть"),
            record("c-aaaaaa06", "Во дворе не горят фонари", category="lighting")]
    assert find(dd, SNOW, recs) == []


def test_distance_200m_boundary(dd):
    near = record("c-aaaaaa07", SNOW, point=offset(STOP, 0, 190), target={"kind": "area", "id": "cell-1"})
    far = record("c-aaaaaa08", SNOW, point=offset(STOP, 0, 260), target={"kind": "area", "id": "cell-2"})
    ids = [x.complaint_id for x in find(dd, SNOW, [near, far])]
    assert ids == ["c-aaaaaa07"]


def test_same_target_far_away_counts(dd):
    seg = {"kind": "segment", "id": "osm-w123-4"}
    rec = record("c-aaaaaa09", SNOW, point=offset(STOP, 900, 0), target=seg)
    assert find(dd, SNOW, [rec], target=seg)
    assert find(dd, SNOW, [rec], target="osm-w123-4")       # id строкой тоже
    assert find(dd, SNOW, [rec]) == []                       # без цели 900 м — не рядом


def test_days_window_and_statuses(dd):
    recs = [record("c-old00001", SNOW, days_ago=20), record("c-fixed0001", SNOW, status="fixed"),
            record("c-rej000001", SNOW, status="rejected"), record("c-dup000001", SNOW, duplicate_of="c-x"),
            record("c-inprog001", SNOW, status="in_progress")]
    assert [x.complaint_id for x in find(dd, SNOW, recs, days=14)] == ["c-inprog001"]
    assert {x.complaint_id for x in find(dd, SNOW, recs, days=30)} == {"c-old00001", "c-inprog001"}


def test_no_location_or_empty_text_gives_nothing(dd):
    recs = [record("c-aaaaaa10", SNOW)]
    assert dd.find(SNOW, recs, point=None, target=None, now=NOW) == []
    assert find(dd, "", recs) == [] and find(dd, "...", recs) == [] and find(dd, "12 34", recs) == []


def test_bad_records_are_skipped(dd):
    recs = [None, "x", {"id": 5}, {"id": "c-bad", "text": SNOW}, record("c-aaaaaa11", SNOW, point=None),
            record("c-aaaaaa12", None), record("c-aaaaaa13", SNOW)]
    assert [x.complaint_id for x in find(dd, SNOW, recs)] == ["c-aaaaaa13"]


def test_order_and_limit(dd):
    recs = [record(f"c-ord{i:05d}", SNOW, point=offset(STOP, 10 * i, 0), metoo=i) for i in range(8)]
    m = find(dd, SNOW, recs, limit=3)
    assert len(m) == 3 and [x.distance_m for x in m] == sorted(x.distance_m for x in m)


def test_very_long_text_is_fast(dd):
    import time
    long = ("Не убран снег на остановке. " * 2000)[:60000]
    t0 = time.perf_counter()
    find(dd, long[:2000], [record("c-aaaaaa14", long)])
    assert time.perf_counter() - t0 < 2.0


def test_cache_recomputes_when_text_changes():
    sc = NgramConceptScorer()
    cache = FeatureCache(max_items=2)
    a1 = cache.get_many(sc, [("c-1", "снег")])[0]
    assert cache.get_many(sc, [("c-1", "снег")])[0] is a1
    assert cache.get_many(sc, [("c-1", "мусор")])[0] is not a1
    cache.get_many(sc, [("c-2", "яма"), ("c-3", "фонарь")])
    assert len(cache) == 2  # LRU не растёт сверх лимита


def test_clamp_days():
    assert clamp_days(None) == 14 and clamp_days(0) == 1 and clamp_days(1000) == 365
    with pytest.raises(ValueError):
        clamp_days("7")


def test_geo_helpers():
    assert distance_m((71.0, 51.0), (71.0, 52.0)) == pytest.approx(111_195, rel=0.01)
    box = bbox_around(STOP, 200)
    for dx, dy in ((200, 0), (-200, 0), (0, 200), (0, -200)):
        lon, lat = offset(STOP, dx * 0.999, dy * 0.999)
        assert box[0] <= lon <= box[2] and box[1] <= lat <= box[3]
    assert parse_point([71.4, 51.1]) == (71.4, 51.1)
    assert parse_point({"lon": 71.4, "lat": 51.1}) == (71.4, 51.1)
    for bad in (None, [1], ["a", "b"], [float("nan"), 1], [200, 1], "71,51"):
        assert parse_point(bad) is None


def test_corrupted_config_falls_back_to_defaults(tmp_path):
    bad = tmp_path / "dedup_config.json"
    bad.write_text("{not json", encoding="utf-8")
    conf = C.load_config(bad)
    assert conf["methods"][C.FALLBACK_METHOD]["threshold"] == C.DEFAULTS["methods"][C.FALLBACK_METHOD]["threshold"]


def test_e5_without_tuned_threshold_or_files_uses_fallback(monkeypatch, tmp_path):
    conf = json.loads(json.dumps(C.DEFAULTS))
    monkeypatch.setattr(C, "load_config", lambda path=None: conf)
    loader.reset()
    assert get_deduper().scorer.method == C.FALLBACK_METHOD          # порог e5 не подобран
    conf["methods"]["e5-onnx"]["threshold"] = 0.85
    monkeypatch.setattr(C, "E5_DIR", tmp_path / "no-model")
    loader.reset()
    assert get_deduper().scorer.method == C.FALLBACK_METHOD          # порог есть, файлов нет
    assert any("e5-onnx" in n for n in loader.deduper_info()["notes"])
    loader.reset()


def test_tuned_config_in_git_is_used():
    conf = C.load_config()
    m = conf["methods"][C.FALLBACK_METHOD]
    dd = get_deduper()
    assert dd.threshold == m["threshold"] and dd.radius_m == 200
    assert isinstance(dd, Deduper)
