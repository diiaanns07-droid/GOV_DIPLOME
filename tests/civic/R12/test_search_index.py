"""R12 · эталон A, правило Linear 1: индекс подсказок поиска для R01 (web/civic/map/search_index.json).

Проверяет: файл в репозитории = свежая сборка из снимка OSM R12 (не устарел после правки подписей), у улиц точка на самой
улице и id существующего участка, у объектов — тот же id и та же подпись, что у карточки, одноимённые остановки рядом
склеены с сохранением всех id, без «Парк «Парк …»»."""
import json
from pathlib import Path

import pytest

from engine.civic_geo import target_info
from engine.civic_geo.graph import get_graph
from engine.civic_geo.search_index import OUT, build

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def built():
    return build()


def test_committed_index_is_fresh(built):
    committed = json.loads(OUT.read_text("utf-8"))
    assert committed == json.loads(json.dumps(built, ensure_ascii=False)), "пересоберите: python3 -m engine.civic_geo search-index"


def test_schema_and_counts(built):
    assert built["schema"] == "birge.search_index.v1"
    assert "OpenStreetMap" in built["license"] and built["source"]["evidence_type"].startswith("observed")
    c = built["counts"]
    assert c["streets"] > 1500 and c["bus_stop"] > 300 and c["yard"] > 200 and c["park"] > 20


def test_streets_point_on_street_and_known_segment(built):
    g = get_graph()
    for s in built["streets"][::25]:
        assert s["ru"] and s["kk"]
        w, so, e, n = s["b"]
        assert w - 1e-5 <= s["c"][0] <= e + 1e-5 and so - 1e-5 <= s["c"][1] <= n + 1e-5
        assert s["seg"] in g.by_id and g.by_id[s["seg"]].name == s["ru"]
    turan = [s for s in built["streets"] if s["ru"] == "проспект Туран"]
    assert turan and turan[0]["kk"] == "Тұран даңғылы"


def test_objects_match_card_labels(built):
    for o in built["objects"][::20]:
        info = target_info(o["id"])
        assert info["target"]["label_ru"] == o["ru"] and info["target"]["label_kk"] == o["kk"]
    assert not [o for o in built["objects"] if o["ru"].startswith("Парк «Парк") or o["kk"].endswith("саябағы» саябағы")]


def test_same_stop_both_sides_kept_as_also(built):
    khan = [o for o in built["objects"] if o["ru"] == "Остановка «Хан Шатыр»"]
    assert len(khan) == 1 and "osm-node-4109037549" in [khan[0]["id"]] + khan[0].get("also", [])
    assert khan[0].get("d") == "nura"
