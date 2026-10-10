"""R02 раунд 13: настоящая поставка R05 (ca0f06f) и отдельный synthetic-сценарий.

Реальные подтверждённые записи: 0 (пакеты R05 пусты). Непустой сценарий ниже — synthetic fixture
(demo-срез), он проверяет механику импорта, а не городской реестр.
"""

import copy
import json
from pathlib import Path

import pytest

from ui.civic_store.importer import ImportRejected, import_package, load_package
from r02_helpers import call
from test_r02_import_cli import package, real_item

R05 = Path(__file__).parent / "fixtures" / "r05_ca0f06f"


def table_counts(service):
    with service.db.read() as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("civic_objects", "civic_history", "civic_public_objects", "civic_imports",
                          "civic_import_candidates")}


@pytest.mark.parametrize("name,source", [("package.civic-v1.json", "r05-astana-r12-verified"),
                                         ("historical.civic-v1.json", "r05-astana-r12-verified-historical")])
def test_real_r05_package_is_empty_and_reported_as_empty(service, name, source):
    pkg = load_package(R05 / name)
    dry = import_package(service.objects, pkg, dry_run=True)
    assert dry["status"] == "dry_run" and dry["source"] == source and dry["demo"] is False
    assert dry["items"] == [] and dry["missing"] == []
    assert dry["summary"]["items_in_package"] == 0 and dry["summary"]["new_drafts"] == 0
    assert "Пакет пуст" in dry["summary"]["note"]
    assert table_counts(service)["civic_imports"] == 0
    first = import_package(service.objects, copy.deepcopy(pkg))
    again = import_package(service.objects, copy.deepcopy(pkg))
    for report in (first, again):
        assert report["status"] == "applied" and report["counts"] == {"report_missing": 0}
        assert report["summary"]["published_by_import"] == 0
    counts = table_counts(service)
    assert counts["civic_objects"] == 0 and counts["civic_public_objects"] == 0
    assert counts["civic_imports"] == 2  # сам факт запуска записан, объектов нет


def test_r05_candidates_file_is_not_importable(service):
    with pytest.raises(ImportRejected, match="schema_version"):
        import_package(service.objects, load_package(R05 / "candidates.json"))
    assert table_counts(service)["civic_objects"] == 0


def synthetic_package(items):
    return {"schema_version": "civic-v1", "city": "astana",
            "slice": {"name": "r02-synthetic-fixture", "version": "s1", "demo": True,
                      "source": "r02-synthetic-fixture"}, "items": items}


def synthetic_item(object_id, **overrides):
    item = real_item(object_id, evidence_type="synthetic", source_refs=[],
                     title=f"СИНТЕТИКА {object_id}", **overrides)
    return item


def test_synthetic_fixture_creates_drafts_only_and_stays_synthetic(service):
    pkg = synthetic_package([synthetic_item("syn-r13-a"),
                             synthetic_item("syn-r13-b", schedule={"planned_start": "2026-09-01",
                                                                   "original_planned_end": None,
                                                                   "current_planned_end": "2026-09-30",
                                                                   "actual_end": None})])
    report = import_package(service.objects, pkg)
    assert report["summary"]["new_drafts"] == 2
    assert report["summary"]["evidence_types"] == {"synthetic": 2}
    warn = {i["external_id"]: [w["code"] for w in i.get("warnings", [])] for i in report["items"]}
    assert warn == {"syn-r13-a": [], "syn-r13-b": ["end_date_passed"]}
    with service.db.read() as conn:
        rows = conn.execute("SELECT publication, data_json FROM civic_objects").fetchall()
    assert {r["publication"] for r in rows} == {"draft"}
    assert {json.loads(r["data_json"])["evidence_type"] for r in rows} == {"synthetic"}
    assert call(service, "GET", "/objects")["body"]["data"]["items"] == []
    # Synthetic нельзя «переименовать» в observed реальным пакетом с тем же id.
    relabel = import_package(service.objects, package([real_item("syn-r13-a")]))
    assert relabel["items"][0]["action"] == "id_conflict"
