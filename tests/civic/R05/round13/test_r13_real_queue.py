"""Реальная очередь R05 раунда 13: полнота разбора 19 кандидатов и честный ноль подтверждённых."""

import contextlib
import io
import json
from pathlib import Path

import pytest

from r13_helpers import REPO

PKG = REPO / "data/civic/astana/round13-verified"
pytestmark = pytest.mark.skipif(not (PKG / "analysis/queue_analysis.json").exists(),
                                reason="NOT_RUN: разбор очереди (analysis/queue_analysis.json) ещё не сохранён")


@pytest.fixture(scope="module")
def real(tool):
    """Инструмент с HERE = настоящий каталог пакета (только чтение)."""
    saved = tool.HERE
    tool.HERE = PKG
    yield tool
    tool.HERE = saved


def call(tool, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = tool.main(list(argv))
    return code, json.loads(buf.getvalue())


def test_analysis_is_valid_and_covers_every_current_candidate(real):
    issues = real.Issues()
    tgts = real.check_analysis(real.analysis(), issues)
    assert issues.errors == []
    queue = json.loads((PKG / "VERIFY_QUEUE.json").read_text("utf-8"))
    current = queue["current_candidates"]
    assert len(current) == 19 and queue["counts"]["candidates_without_decision"] == 0
    roles = {c["role"] for c in current}
    assert roles <= {"canonical", "duplicate", "overlaps", "separate", "not_mappable_programme"}
    for c in current:                       # кандидат либо ведёт к цели, либо объяснён как дубль/программа
        assert c["targets"] or c["role"] in ("duplicate", "not_mappable_programme", "overlaps"), c
    for slug, t in tgts.items():
        assert t["source_ids"], slug       # что открыть
        assert real.record_id(t) == f"ast-r05-{t['kind']}-{slug}" and len(real.record_id(t)) <= 64


def test_hints_keep_their_origin_and_nothing_is_called_confirmed(real):
    doc = real.analysis()
    blob = json.dumps(doc, ensure_ascii=False).lower()
    for word in ("подтверждено", "confirmed", "verified"):
        assert f'"{word}"' not in blob
    for t in doc["targets"]:
        assert t["timing"].get("origin") in ("url", "search_title", "search_summary", "none", "mixed")
    for c in doc["clusters"]:
        for h in c.get("followup_hints") or []:
            assert h["origin"] in ("search_title", "search_summary")


def test_honest_zero_and_outputs_are_current(real):
    assert not any((PKG / "evidence").glob("*/*.json")) and not any((PKG / "reviews").glob("*.json"))
    code, out = call(real, "check")
    assert code == 0, out
    assert set(out["states"].values()) == {"candidate"}
    summary = json.loads((PKG / "summary.json").read_text("utf-8"))
    assert summary["verified_current"] == 0 and summary["verified_historical"] == 0
    assert summary["fetched_sources"] == 0
    for name in ("package.civic-v1.json", "historical.civic-v1.json"):
        pkg = json.loads((PKG / name).read_text("utf-8"))
        assert pkg["items"] == [] and pkg["slice"]["demo"] is False


def test_queue_geometry_hints_are_labelled_approximate(real):
    queue = json.loads((PKG / "VERIFY_QUEUE.json").read_text("utf-8"))
    for t in queue["targets"]:
        plan = t["geometry_plan"]
        if plan["result"] == "ok":
            assert plan["basis"].startswith("OSM") and "approximate" in plan["precision"]
        assert t["state"] == "candidate"
