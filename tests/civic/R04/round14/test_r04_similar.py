"""ui.civic_ml_api.similar: источник жалоб, контракт ответа, проверка ввода, приватность, хранилище R09."""

import json
from datetime import timedelta

import pytest

import ui.civic_ml_api as api
from ml.civic_dedup.fixtures import offset
from ui.civic_ml_api.errors import MLServiceUnavailable

from r04_helpers import NOW, STOP, clean_api, record  # noqa: F401 — clean_api: autouse-фикстура

SNOW = "Не убран снег на остановке, люди падают"
OTHER_TEXTS = ["Во дворе не горят фонари", "Мусорные баки переполнены", "Яма на дороге у школы"]


def connect(recs):
    api.set_complaint_source(api.records_source(recs, clock=lambda: NOW))


def test_not_connected_is_503_with_code():
    with pytest.raises(MLServiceUnavailable) as err:
        api.similar(SNOW, point=list(STOP))
    assert err.value.status == 503 and err.value.code == "source_not_connected" and err.value.message


def test_contract_and_people_count():
    connect([record("c-snow0001", "Аялдамада қар тазаланбаған", metoo=6),
             record("c-light001", "Во дворе не горят фонари", category="lighting")])
    res = api.similar(SNOW, point=list(STOP), days=14)
    assert set(res) >= {"matches", "people_total", "method", "model_version", "threshold", "days", "radius_m"}
    assert [m["complaint_id"] for m in res["matches"]] == ["c-snow0001"]
    m = res["matches"][0]
    assert set(m) >= {"complaint_id", "score", "target", "metoo"} and m["metoo"] == 6 and m["people"] == 7
    assert res["people_total"] == 7 and res["days"] == 14 and res["radius_m"] == 200


def test_response_never_contains_complaint_text():
    secret = "Не убран снег на остановке, звоните Айгерим [телефон]"
    connect([record("c-snow0002", secret)])
    res = api.similar(SNOW, point=list(STOP))
    assert res["matches"]
    dumped = json.dumps(res, ensure_ascii=False)
    assert "Айгерим" not in dumped and '"text"' not in dumped


def test_target_param_and_far_points():
    seg = {"kind": "segment", "id": "osm-w555-2"}
    connect([record("c-seg00001", SNOW, point=offset(STOP, 1500, 0), target=seg)])
    assert api.similar(SNOW, point=list(STOP))["matches"] == []
    assert api.similar(SNOW, point=list(STOP), target=seg)["matches"]
    assert api.similar(SNOW, target="osm-w555-2")["matches"]


def test_days_param():
    connect([record("c-old00002", SNOW, days_ago=10)])
    assert api.similar(SNOW, point=list(STOP), days=7)["matches"] == []
    assert api.similar(SNOW, point=list(STOP), days=30)["matches"]


def test_no_location_returns_empty_with_note():
    connect([record("c-snow0003", SNOW)])
    res = api.similar(SNOW)
    assert res["matches"] == [] and res["note"] == "no_location"


@pytest.mark.parametrize("kwargs", [{"point": "71.4,51.1"}, {"point": [71.4]}, {"point": [float("nan"), 51.1]},
                                    {"days": "7"}, {"target": 5}, {"limit": "много"}])
def test_bad_input_is_value_error(kwargs):
    connect([])
    with pytest.raises(ValueError):
        api.similar(SNOW, **{"point": list(STOP), **kwargs})


def test_bad_text_type():
    connect([])
    with pytest.raises(ValueError):
        api.similar(None, point=list(STOP))


def test_empty_and_long_text():
    connect([record("c-snow0004", SNOW)])
    assert api.similar("", point=list(STOP))["matches"] == []
    assert api.similar("...", point=list(STOP))["matches"] == []
    long = SNOW + " " + "очень длинное описание " * 5000
    assert api.similar(long, point=list(STOP))["matches"]


def test_source_failure_propagates_as_error():
    def broken(**_kw):
        raise OSError("база недоступна")
    api.set_complaint_source(broken)
    with pytest.raises(OSError):
        api.similar(SNOW, point=list(STOP))


def test_limit():
    connect([record(f"c-lim{i:05d}", SNOW, point=offset(STOP, 5 * i, 0)) for i in range(10)])
    assert len(api.similar(SNOW, point=list(STOP))["matches"]) == 5
    assert len(api.similar(SNOW, point=list(STOP), limit=2)["matches"]) == 2


# ---------------------------------------------------------------- хранилище R09
r09 = pytest.importorskip("ui.civic_feedback.v2", reason="нет ui/civic_feedback/v2 (R09) в сборке")


@pytest.fixture
def store():
    s = r09.ComplaintStore(":memory:", clock=lambda: NOW)
    yield s
    s.close()


def create(store, text, point, device, target=None, category="snow_ice"):
    payload = {"text": text, "category": category, "point": list(point)}
    if target:
        payload["target"] = target
    rec, _ = store.create(payload, device)
    return rec


def test_r09_store_end_to_end(store):
    stop = {"kind": "object", "id": "osm-node-1001", "label_ru": "Остановка «Нура»"}
    first = create(store, "Аялдамада қар тазаланбаған, адамдар құлап жатыр", STOP, "dev-aaaaaaaaaaaaaaaa", stop)
    create(store, "Во дворе не горят фонари", offset(STOP, 50, 0), "dev-bbbbbbbbbbbbbbbb", category="lighting")
    create(store, "Не убран снег у школы", offset(STOP, 3000, 0), "dev-cccccccccccccccc")
    store.metoo(first["id"], "dev-dddddddddddddddd")
    api.connect_store(store)
    res = api.similar(SNOW, point=list(offset(STOP, 30, 30)), days=14)
    assert [m["complaint_id"] for m in res["matches"]] == [first["id"]]
    assert res["matches"][0]["metoo"] == 1 and res["people_total"] == 2
    assert res["matches"][0]["target"]["id"] == "osm-node-1001"


def test_r09_fixed_and_duplicates_excluded(store):
    a = create(store, SNOW, STOP, "dev-aaaaaaaaaaaaaaaa")
    b = create(store, "На остановке не чистят снег", STOP, "dev-bbbbbbbbbbbbbbbb")
    store.set_status(a["id"], "fixed", actor="test")
    store.mark_duplicate(b["id"], a["id"], actor="test")
    api.connect_store(store)
    assert api.similar(SNOW, point=list(STOP))["matches"] == []


def test_r09_service_object_is_accepted(store):
    create(store, SNOW, STOP, "dev-aaaaaaaaaaaaaaaa")
    api.connect_store(r09.ComplaintsV2Service(store))
    assert api.similar(SNOW, point=list(STOP))["matches"]


def test_r09_old_complaints_outside_window(store):
    from ui.civic_ml_api.similar_search import StoreSource
    create(store, SNOW, STOP, "dev-aaaaaaaaaaaaaaaa")
    src = StoreSource(store)
    src.now = lambda: NOW + timedelta(days=20)   # «сейчас» через 20 дней: жалоба старше окна 14 дней
    api.set_complaint_source(src)
    assert api.similar(SNOW, point=list(STOP), days=14)["matches"] == []
    assert api.similar(SNOW, point=list(STOP), days=30)["matches"]


def test_r09_cache_warming_on_connect_and_on_create(store):
    from ml.civic_dedup import get_deduper
    from ui.civic_ml_api.similar_search import WARMER
    create(store, SNOW, STOP, "dev-aaaaaaaaaaaaaaaa")
    api.connect_store(store)                      # прогрев открытых жалоб за 30 дней
    assert WARMER.join(10)
    assert len(get_deduper().cache) == 1
    create(store, "Во дворе не горят фонари", STOP, "dev-bbbbbbbbbbbbbbbb", category="lighting")  # событие created
    assert WARMER.join(10)
    assert len(get_deduper().cache) == 2
    api.set_complaint_source(None)                # отписка: новые жалобы больше не греются
    create(store, "Мусор не вывозят", STOP, "dev-cccccccccccccccc", category="waste")
    assert WARMER.join(10) and len(get_deduper().cache) == 2


def test_warm_cache_without_source_is_noop():
    assert api.warm_cache() == 0


def test_long_record_text_warm_cache_key_matches_search(store):
    """Прогрев и поиск обрезают текст одинаково: длинная жалоба после прогрева не считается заново."""
    from ml.civic_dedup import get_deduper
    from ui.civic_ml_api.similar_search import WARMER
    long = SNOW + " " + "подробности " * 400            # > 2000 символов (у R09 предел 2000 — через import_record)
    rec = record("c-long0001", long)
    store.import_record(dict(rec, due_at=rec["created_at"], schema="civic-complaint-v2", target={"kind": "object", "id": "osm-node-1001"}))
    api.connect_store(store)
    assert WARMER.join(10) and len(get_deduper().cache) == 1
    assert api.similar(SNOW, point=list(STOP))["matches"]
    assert len(get_deduper().cache) == 1                 # тот же ключ — запись не пересчитана
