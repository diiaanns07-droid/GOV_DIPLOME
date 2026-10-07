"""Конвертер результатов поиска R05: детерминированность и честное происхождение подсказок."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT = REPO / "research/round-12-results/R05/import_search_results.py"

# Скрипт — исследовательский материал раунда 12 (research/round-12-results/R05/, закреплён в ca0f06f).
# На ветке без этой папки проверка не выполняется и честно помечается NOT_RUN, а не PASS.
pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(),
    reason="NOT_RUN: research/round-12-results/R05/import_search_results.py нет на этой ветке (см. ca0f06f)")


def load_module():
    spec = importlib.util.spec_from_file_location("r05_r12_import_search_results", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_norm_url_keeps_gov_kz_language_and_drops_amp_and_tracking():
    m = load_module()
    assert m.norm_url("http://www.gov.kz/memleket/entities/astana/press/news/details/1193903?lang=ru") == \
        "https://www.gov.kz/memleket/entities/astana/press/news/details/1193903?lang=ru"
    assert m.norm_url("https://bes.media/amp/kakie-ulitsi/?utm_source=x") == "https://bes.media/kakie-ulitsi"
    assert m.source_id("https://www.gov.kz/x?lang=ru") != m.source_id("https://www.gov.kz/x?lang=kk")


def test_publisher_mapping_is_by_domain_not_by_agent_label():
    m = load_module()
    assert m.publisher_for("www.inform.kz") == ("МИА «Казинформ»", "state_media")
    assert m.publisher_for("unknown-blog.example") == (None, "other")
    # gov.kz — портал разных органов: не всё на нём — акимат Астаны
    assert m.publisher_for("www.gov.kz", "/memleket/entities/astana/press/news/details/1")[0] == "Акимат города Астаны"
    assert m.publisher_for("www.gov.kz", "/memleket/entities/tsm/press/news/details/1")[0] == "Министерство туризма и спорта РК"
    assert "entities/astana-uvp" in m.publisher_for("www.gov.kz", "/memleket/entities/astana-uvp/press/1")[0]


def run(m, tmp_path, monkeypatch, result):
    pkg = tmp_path / "pkg"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(m, "PKG", pkg)
    src = tmp_path / "result.json"
    src.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    assert m.main([str(src)]) == 0
    return (json.loads((pkg / "sources.json").read_text(encoding="utf-8")),
            json.loads((pkg / "candidates.json").read_text(encoding="utf-8")),
            (pkg / "sources.json").read_bytes() + (pkg / "candidates.json").read_bytes())


RESULT = {"queries": ["q1"], "candidates": [
    {"url": "https://digitalbusiness.kz/2026-06-05/v-astane-perekroyut-dorogi/", "title_as_listed": "В Астане перекроют дороги",
     "domain": "digitalbusiness.kz", "source_kind": "official_gov", "kind": "event", "topic": "t", "location_text": "",
     "date_hint": "2026-06-05", "date_hint_origin": "url", "is_astana": "yes", "notes": "", "sweep": "events",
     "claims": [{"field": "event_date", "value_text": "7 июня", "origin": "search_summary"}],
     "verdict": {"decision": "keep", "reason": "ok", "duplicate_of_url": "", "freshness": "past_2026",
                 "best_date_hint": "2026-06-05", "best_date_origin": "url", "corroborating_urls": [],
                 "contradictions": "", "city_check": "astana_confirmed_in_title_or_url"}},
    {"url": "https://www.gov.kz/memleket/entities/astana/press/news/details/1?lang=ru", "title_as_listed": "Официально",
     "domain": "gov.kz", "source_kind": "news", "kind": "roadworks", "topic": "t", "location_text": "ул. А",
     "date_hint": "", "date_hint_origin": "none", "is_astana": "yes", "notes": "", "sweep": "official", "claims": [],
     "verdict": None},
]}


def test_import_is_deterministic_and_nothing_is_fetched(tmp_path, monkeypatch):
    m = load_module()
    sources, cands, first = run(m, tmp_path / "a", monkeypatch, RESULT)
    _, _, second = run(m, tmp_path / "b", monkeypatch, RESULT)
    assert first == second
    assert all(s["access_status"] == "not_fetched" and s["content_sha256"] is None for s in sources["sources"])
    by_url = {s["url"]: s for s in sources["sources"]}
    dated = by_url["https://digitalbusiness.kz/2026-06-05/v-astane-perekroyut-dorogi"]
    assert dated["published_on"] == "2026-06-05" and dated["published_on_basis"] == "url"
    # издатель по домену, а не по метке агента («official_gov» у новостного сайта не принимается)
    assert dated["publisher_kind"] == "news"
    gov = by_url["https://www.gov.kz/memleket/entities/astana/press/news/details/1?lang=ru"]
    assert gov["publisher_kind"] == "official_gov" and gov["published_on"] is None
    hint = next(c for c in cands["candidates"] if c["kind"] == "event")["hints"][0]
    assert hint["origin"] == "search_summary"
    unjudged = next(c for c in cands["candidates"] if c["kind"] == "roadworks")
    assert unjudged["decision"] == "to_verify" and "не проверено скептиком" in unjudged["reason"]
