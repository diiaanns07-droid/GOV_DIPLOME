"""R04 раунд 15: route() — службы для обращения (CONTRACT §7 POST /route, §5.1 route_hint). Без сети.

conftest.py в папке R04 нет нарочно (см. tests/civic/R04/round14/r04_helpers.py).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ui.civic_ml_api import route, route_hint
from ui.civic_ml_api import routing as R
from ui.civic_ml_api.route_eval import evaluate, load_cases

CASES = Path(__file__).with_name("route_cases.json")


@pytest.fixture(autouse=True)
def fresh_names():
    R._names_cache.update(at=0.0, names=None)
    yield
    R._names_cache.update(at=0.0, names=None)


def services(result):
    return [s["service"] for s in result["services"]]


# ---------------------------------------------------------------- сцена 8 и главные случаи
@pytest.mark.parametrize("kwargs", [
    {"text": "Яма после раскопок водоканала"},
    {"text": "Яма после раскопок водоканала", "category": "roads", "subtopic": "pothole"},
    {"body": {"text": "Яма после раскопок водоканала", "category": "roads"}},
])
def test_scene8_two_services(kwargs):
    res = route(**kwargs)
    assert services(res) == ["water", "road"]
    assert res["joint"] is True
    assert [s["role"] for s in res["services"]] == ["lead", "partner"]
    assert res["summary_ru"] == "Нужны 2 службы: Водоканал и Дорожная служба"
    assert res["summary_kk"] == "Екі қызмет керек: Сумен жабдықтау қызметі және Жол қызметі"
    assert res["why_ru"] and res["why_kk"] and "\n" not in res["why_ru"]
    assert res["model_version"].startswith(R.VERSION)


def test_route_hint_shape_for_r09():
    hint = route_hint(route(text="Яма после раскопок водоканала"))
    assert hint == {"services": ["water", "road"], "joint": True, "source": "rules",
                    "model_version": hint["model_version"]}
    assert hint["model_version"].startswith("r04-route-")


def test_single_service_from_table_with_explanation():
    res = route(category="utilities", subtopic="no_heating")
    assert services(res) == ["heating"] and res["joint"] is False
    assert res["rule"] == "table.subtopic"
    assert "Теплосеть" in res["why_ru"] and "Жылу желісі" in res["why_kk"]
    assert res["summary_ru"] == "Служба: Теплосеть"


@pytest.mark.parametrize("text, expect", [
    ("После ремонта дороги снова появилась яма", ["road"]),          # «после ремонта» без сетей — одна служба
    ("Водоканал отключил воду без предупреждения", ["water"]),        # водоканал без раскопа
    ("Не горит фонарь, столб наклонился", ["lighting"]),              # столб не упал
    ("Нет горячей воды и отопления", ["heating"]),                    # обе — теплосеть
    ("Упало дерево и перегородило дорогу", ["greenery"]),             # дерево без проводов
    ("Люк без крышки рядом с парком, уже кто-то провалился", ["water"]),  # провалился человек, не асфальт
    ("Асфальт провалился, получилась настоящая траншея", ["road"]),   # «траншея» без сетей и засыпки
    ("Контейнеры переполнены, собаки растаскивают мусор", ["waste"]),  # собаки — подробность, не вторая проблема
    ("Свалка рядом с детской площадкой", ["waste"]),                   # площадка — место
    ("Сәлеметсіз бе! Жөндеуден кейін жолға асфальт төселмеді. Рақмет", ["water", "road"]),  # «Рақмет» — вежливость
])
def test_negatives_and_near_misses(text, expect):
    assert services(route(text=text)) == expect


def test_resident_category_is_respected_without_joint():
    res = route(text="Прорвало трубу, вода течёт на дорогу", category="utilities", subtopic="no_water")
    assert services(res) == ["water"] and res["category_source"] == "given"


def test_three_outages():
    res = route(text="Нет воды, света и газа")
    assert services(res) == ["water", "power", "gas"]
    assert res["summary_ru"] == "Нужны 3 службы: Водоканал, Электросети и Газовая служба"


def test_thanks_goes_to_akimat_but_polite_complaint_does_not():
    assert services(route(text="Спасибо за ремонт двора")) == ["akimat"]
    assert services(route(text="Жаңа алаң үшін рақмет, тез бітірдіңіздер!")) == ["akimat"]
    assert services(route(text="Аулада шам жанбайды. Рақмет.")) == ["lighting"]


def test_kazakh_and_latin_text():
    assert services(route(text="Су құбырын жөндегеннен кейін жолда үлкен шұңқыр қалды")) == ["water", "road"]
    assert services(route(text="Raskopali dorogu i ne zakopali")) == ["water", "road"]
    assert services(route(text="Su joq")) == ["water"]


# ---------------------------------------------------------------- набор фраз (числа для DELIVERY)
def test_route_cases_file_is_valid():
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert len(cases) >= 150
    assert {c["lang"] for c in cases} >= {"ru", "kk", "mixed"}
    assert sum(c["joint"] for c in cases) >= 50
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert set(c["expect"]) <= set(R.SERVICE_IDS), c["id"]
        assert c["split"] in ("dev", "test")


@pytest.mark.parametrize("split", ["dev", "test"])
def test_route_cases_quality(split):
    res = evaluate(load_cases(), split)
    bad = [(e["id"], e["text"], e["expect"], e["got"]) for e in res["errors"]]
    assert res["set_acc"] >= 0.97, bad
    assert res["joint"]["precision"] >= 0.95 and res["joint"]["recall"] >= 0.95, bad


# ---------------------------------------------------------------- таблица R08: правки акимата и её отсутствие
def test_akimat_edits_of_r08_table_are_used(tmp_path, monkeypatch):
    from ui.civic_akim import routing as r08
    path = tmp_path / "routing.json"
    path.write_text(json.dumps({"rules": {"roads/pothole": "landscaping"},
                                "services": {"water": {"ru": "Городской водоканал", "kk": "Қалалық су қызметі"}}},
                               ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(r08, "OVERRIDE_PATH", path)
    assert services(route(category="roads", subtopic="pothole")) == ["landscaping"]
    res = route(text="Яма после раскопок водоканала")
    assert res["summary_ru"] == "Нужны 2 службы: Городской водоканал и Дорожная служба"


def test_without_r08_module_uses_fallback(monkeypatch):
    monkeypatch.setattr(R, "_r08", lambda: None)
    res = route(text="Яма после раскопок водоканала")
    assert services(res) == ["water", "road"]
    assert res["summary_ru"] == "Нужны 2 службы: Водоканал и Дорожная служба"
    assert services(route(category="lighting", subtopic="wire_down")) == ["power"]


# ---------------------------------------------------------------- ввод
@pytest.mark.parametrize("kwargs", [
    {},
    {"text": "  "},
    {"text": "??"},
    {"category": "nope"},
    {"text": 15},
    {"text": "Яма", "point": [10, 10]},
    {"text": "Яма", "point": "71.4,51.1"},
])
def test_bad_input_is_value_error(kwargs):
    with pytest.raises(ValueError):
        route(**kwargs)


def test_unknown_subtopic_is_ignored_and_point_checked():
    res = route(text="Яма на дороге", category="roads", subtopic="no_such", point=[71.43, 51.13])
    assert services(res) == ["road"] and res["subtopic"] == "pothole"


def test_speed_route_under_30ms():
    texts = [c["text"] or "яма" for c in load_cases()]
    route(text="прогрев")
    times = []
    for text in texts * 2:
        t0 = time.perf_counter()
        route(text=text)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    assert times[int(0.95 * (len(times) - 1))] < 30, times[-5:]


# ---------------------------------------------------------------- календарь работ R06: кто копал рядом
def test_nearby_dig_work_names_the_network(monkeypatch):
    from datetime import date, timedelta as td
    today = date.today()
    works = [{"id": "w-1", "service": "heating", "kind": "dig", "starts_on": (today - td(days=40)).isoformat(),
              "ends_on": (today - td(days=20)).isoformat(), "distance_m": 60, "source": "demo"},
             {"id": "w-2", "service": "road", "kind": "surface", "starts_on": today.isoformat(), "distance_m": 10},
             {"id": "w-3", "service": "water", "kind": "dig", "starts_on": (today + td(days=200)).isoformat(),
              "distance_m": 5}]                                   # плановая раскопка далеко в будущем — не она
    R.set_works_source(lambda point, radius: works)
    try:
        res = route(text="Раскопали дорогу и так и бросили", point=[71.43, 51.12])
        assert services(res) == ["heating", "road"]
        assert res["evidence"]["work"]["id"] == "w-1" and res["why_ru"].startswith("Рядом шли раскопки: Теплосеть")
        assert res["why_kk"].startswith("Жақын жерде қазба жұмыстары жүрді: Жылу желісі")
        # Служба названа в тексте — чужая раскопка рядом её не меняет.
        res = route(text="Водоканал раскопал дорогу", point=[71.43, 51.12])
        assert services(res) == ["water", "road"] and res["evidence"] is None
        # Без точки — как раньше.
        assert route(text="Раскопали дорогу и так и бросили")["evidence"] is None
    finally:
        R.set_works_source(None)


def test_works_source_failure_is_harmless():
    def broken(point, radius):
        raise RuntimeError("нет базы")

    R.set_works_source(broken)
    try:
        assert services(route(text="Раскопали дорогу и так и бросили", point=[71.43, 51.12])) == ["water", "road"]
    finally:
        R.set_works_source(None)
