"""Изолированный каталог пакета R05 раунда 13 для синтетических проверок (реальные файлы не меняются)."""

import importlib.util
import json

import pytest

from r13_helpers import REPO, SYNTH_URL_A, SYNTH_URL_B, PAGE_A, PAGE_B, TOOL


@pytest.fixture(scope="session")
def tool():
    spec = importlib.util.spec_from_file_location("r05_r13_tool_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home(tmp_path, tool, monkeypatch):
    root = tmp_path / "r13home"
    (root / "analysis").mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()
    sources = {"schema": "r05-r12-sources-v1", "city": "astana", "sources": [
        {"id": "src-r12-test-almaty-a", "url": SYNTH_URL_A, "publisher": "Синтетический издатель (тест)",
         "publisher_kind": "state_media", "access_status": "not_fetched"},
        {"id": "src-r12-test-almaty-b", "url": SYNTH_URL_B, "publisher": "Синтетический акимат (тест)",
         "publisher_kind": "official_gov", "access_status": "not_fetched"}]}
    cands = {"schema": "r05-r12-candidates-v1", "city": "astana", "candidates": [
        {"id": "cand-r12-test-almaty", "decision": "to_verify", "freshness": "current_or_upcoming_2026",
         "kind": "roadworks", "title_as_listed": "Синтетический кандидат (тест)",
         "source_ids": ["src-r12-test-almaty-a", "src-r12-test-almaty-b"]},
        {"id": "cand-r12-test-programme", "decision": "to_verify", "freshness": "current_or_upcoming_2026",
         "kind": "construction", "title_as_listed": "Синтетическая программа (тест)", "source_ids": []},
        {"id": "cand-r12-test-rejected", "decision": "rejected", "freshness": "unknown", "kind": "event",
         "title_as_listed": "Отклонённый (тест)", "source_ids": []}]}
    (base / "sources.json").write_text(json.dumps(sources, ensure_ascii=False), encoding="utf-8")
    (base / "candidates.json").write_text(json.dumps(cands, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((REPO / "data/civic/astana/round13-verified/config.json").read_text(encoding="utf-8"))
    cfg.update(base_sources=str(base / "sources.json"), base_candidates=str(base / "candidates.json"))
    (root / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    analysis = {"schema": "r05-r13-queue-analysis-v1", "as_of": "2026-10-07", "method": "synthetic test fixture",
                "clusters": [{"key": "test", "candidate_ids": ["cand-r12-test-almaty", "cand-r12-test-programme"],
                              "candidate_decisions": [
                                  {"candidate_id": "cand-r12-test-almaty", "role": "canonical", "related_to": [], "reason": "тест"},
                                  {"candidate_id": "cand-r12-test-programme", "role": "not_mappable_programme",
                                   "related_to": [], "reason": "тест"}],
                              "contradictions": [], "followup_hints": []}],
                "targets": [
                    {"slug": "test-almaty-closure", "kind": "roadworks", "title_ru": "Закрытие ул. Алматы (тест)",
                     "what_hint": "закрытие участка", "candidate_ids": ["cand-r12-test-almaty"],
                     "source_ids": ["src-r12-test-almaty-a", "src-r12-test-almaty-b"],
                     "location_text": "ул. Алматы, Акмешит — Сауран",
                     "osm_query": {"street": "Алматы", "from": "Акмешит", "to": "Сауран"},
                     "geometry_level": "street_segment", "mappable": True, "priority": 1,
                     "timing": {}, "required_evidence": [], "do_not_infer": [], "provability": {"score": 4, "reason": "тест"}},
                    {"slug": "test-programme", "kind": "construction", "title_ru": "Программа (тест)",
                     "what_hint": "программа", "candidate_ids": ["cand-r12-test-programme"], "source_ids": [],
                     "location_text": "город", "osm_query": None, "geometry_level": "none", "mappable": False,
                     "priority": 9, "timing": {}, "required_evidence": [], "do_not_infer": [],
                     "provability": {"score": 1, "reason": "тест"}}]}
    (root / "analysis" / "queue_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(tool, "HERE", root)
    texts = tmp_path / "saved-pages"            # вне репозитория: tmp_path
    texts.mkdir()
    (texts / "a.html").write_text(PAGE_A, encoding="utf-8")
    (texts / "b.html").write_text(PAGE_B, encoding="utf-8")
    return {"root": root, "texts": texts, "tmp": tmp_path}
