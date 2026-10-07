"""R05 раунд 12: инварианты закоммиченных данных пакета и геокодирования по OSM-снимку.

Проверяют не «число записей», а то, что неизвестное не выдаётся за подтверждённое:
непрочитанный источник не помечен fetched, кандидаты не попадают в пакет импорта,
даты публикации берутся только из URL или страницы, геометрия — только из открытых данных.
"""

import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[4]
PKG = REPO / "data/civic/astana/round12-verified"
TOOL = PKG / "tools/r12.py"
OSM = REPO / "data/civic/astana/osm-walking/overpass.json.gz"
MIRRORS = ("web.archive.org", "archive.ph", "r.jina.ai", "webcache", "translate.goog")


def load(name):
    path = PKG / name
    if not path.exists():
        pytest.skip(f"NOT_RUN: нет {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def tool(*args):
    return subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True, cwd=str(REPO),
                          timeout=180)


def test_check_command_passes_on_committed_data():
    result = tool("check")
    report = json.loads(result.stdout)
    errors = [i for i in report["issues"] if i["severity"] == "error"]
    assert not errors and not report["civic_issues"] and not report["stale_packages"], report


def test_unread_sources_are_never_marked_fetched():
    sources = load("sources.json")["sources"]
    verified_ids = set()
    for path in (PKG / "verified").glob("*.json"):
        rec = json.loads(path.read_text(encoding="utf-8"))
        verified_ids |= set(rec["verification"]["sources"])
    for src in sources:
        if src["access_status"] == "fetched":
            assert src["id"] in verified_ids, f"{src['id']} fetched без проверенной записи"
            assert re.fullmatch(r"[0-9a-f]{64}", src["content_sha256"] or "")
        assert not any(m in src["url"] for m in MIRRORS), src["url"]
        assert src["url"].startswith("https://")
        if src["published_on"] is not None:
            assert src["published_on_basis"] in ("url", "page")
            if src["published_on_basis"] == "url":
                assert src["published_on"] in src["url"], "дата из URL должна буквально быть в URL"


def test_candidates_are_not_in_import_package():
    cands = load("candidates.json")["candidates"]
    package = load("package.civic-v1.json")
    historical = load("historical.civic-v1.json")
    verified = {p.stem for p in (PKG / "verified").glob("*.json")}
    items = {i["id"] for i in package["items"] + historical["items"]}
    assert items == verified, "в пакете только записи из verified/"
    assert not items & {c["id"] for c in cands}
    for item in package["items"] + historical["items"]:
        assert item["publication"] == "draft" and item["evidence_type"] in ("observed", "derived")
        assert all(ref["access_status"] == "fetched" for ref in item["source_refs"])


def test_candidate_hints_keep_their_origin_and_decisions_have_reasons():
    cands = load("candidates.json")["candidates"]
    assert cands, "кандидаты должны быть сохранены (журнал поиска)"
    sources = {s["id"]: s for s in load("sources.json")["sources"]}
    for cand in cands:
        assert cand["decision"] in ("to_verify", "rejected", "duplicate") and cand["reason"]
        assert cand["source_ids"] and all(sid in sources for sid in cand["source_ids"])
        for hint in cand["hints"]:
            assert hint["origin"] in ("url", "search_title", "search_summary")
        if cand["decision"] == "duplicate":
            assert cand["duplicate_of"] in {c["id"] for c in cands}
        geo = cand.get("geocode")
        if geo and geo.get("geometry"):
            assert geo["geometry_precision"] == "approximate" and "OSM" in geo["geometry_basis"]


def test_summary_counts_match_files():
    summary = load("summary.json")
    cands = load("candidates.json")["candidates"]
    assert summary["unverified_candidates"] == sum(1 for c in cands if c["decision"] == "to_verify")
    assert summary["rejected_candidates"] == sum(1 for c in cands if c["decision"] == "rejected")
    assert summary["confirmed_current"] == len(load("package.civic-v1.json")["items"])


def test_network_audit_records_denials_without_circumvention():
    audit = load("network_audit.json")
    assert audit["attempts"] and all(a["outcome"] == "egress_denied" for a in audit["attempts"])
    assert "Not attempted" in audit["circumvention"]


# ---------------------------------------------------------------- geocoding on the open OSM snapshot
needs_osm = pytest.mark.skipif(not OSM.exists(), reason="NOT_RUN: нет OSM-снимка (дерево не от 56538a3)")


def geocode(*args):
    result = tool("geocode", *args)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@needs_osm
def test_intersection_point_from_osm_without_shared_node():
    res = geocode("--street", "Бейсековой", "--cross", "Тлендиева")
    assert res["geometry"]["type"] == "Point" and res["geometry_precision"] == "approximate"
    lon, lat = res["geometry"]["coordinates"]
    assert 71.2 < lon < 71.8 and 51.0 < lat < 51.35
    assert "OSM" in res["geometry_basis"] and "2026-05-06" in res["geometry_basis"]
    # «Бейсекбаева» — другая улица, не должна совпасть с «Бейсековой»
    assert not any("Бейсекбаев" in n for n in res["matched_names"])


@needs_osm
def test_unknown_street_gives_null_not_district_centre():
    res = geocode("--street", "Несуществующая Улица Ромашковая")
    assert res["geometry"] is None and res["geometry_precision"] == "unknown"


@needs_osm
def test_disconnected_same_name_street_is_not_merged():
    res = geocode("--street", "Кайсенова")
    assert res["geometry"] is None and res["ambiguous"] is True
