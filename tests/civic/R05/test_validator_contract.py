"""R05 validator: contract fixture and the risks the real slice must reject."""

import copy
import json
import os
import subprocess
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TOOLS = os.path.join(REPO, "data", "civic", "astana", "tools")
sys.path.insert(0, TOOLS)

import civic_v1 as cv  # noqa: E402

PACK_SHA = "9c2f5c0dae14b46c0697a9dfc7f854351bfd570d"

# Same content as research/round-11/fixtures/civic_object.json at PACK_SHA (kept inline so the
# test does not depend on a branch checkout; test_contract_fixture_matches_pack compares them).
CONTRACT_FIXTURE = {
    "schema_version": "civic-v1",
    "id": "demo-astana-work-01",
    "city": "astana",
    "kind": "roadworks",
    "title": "Демонстрационный ремонт прохода",
    "description": "Синтетическая запись для проверки интерфейса. Не сведения о реальных работах.",
    "status": "planned",
    "publication": "published",
    "geometry": {"type": "Point", "coordinates": [71.43, 51.17]},
    "geometry_precision": "approximate",
    "schedule": {"planned_start": "2026-10-14", "original_planned_end": "2026-10-20",
                 "current_planned_end": "2026-10-22", "actual_end": None},
    "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
    "responsible": {"organization": None, "public_contact": None},
    "evidence_type": "synthetic",
    "source_refs": [],
    "evidence_notes": "Создано координатором для теста; не публиковать как реальный ремонт.",
    "updated_at": "2026-10-06T12:00:00+06:00",
    "revision": 2,
}

FENCE = cv.load_geofence()
AS_OF = "2026-10-06"


def codes(obj, profile):
    return {i["code"] for i in cv.validate_object(obj, profile=profile, as_of=AS_OF, fence=FENCE)
            if i["severity"] == "error"}


def real_record():
    """A structurally complete record that claims to be real, backed by one fetched source."""
    obj = copy.deepcopy(CONTRACT_FIXTURE)
    obj.update({
        "id": "ast-r05-test-roadworks-1",
        "title": "Тестовая запись",
        "description": "Проверка правил валидатора.",
        "status": "unknown",
        "publication": "draft",
        "evidence_type": "observed",
        "geometry": None,
        "geometry_precision": "unknown",
        "schedule": {"planned_start": None, "original_planned_end": None,
                     "current_planned_end": None, "actual_end": None},
        "evidence_notes": "",
        "revision": 1,
        "source_refs": [{
            "id": "src-test", "url": "https://example.org/news/1", "publisher": "Example",
            "published_on": "2026-09-30", "retrieved_at": "2026-10-06T10:00:00+06:00",
            "access_status": "fetched", "license": None, "fields": ["kind"],
        }],
    })
    return obj


class ContractFixture(unittest.TestCase):
    def test_contract_fixture_matches_pack(self):
        try:
            raw = subprocess.run(["git", "-C", REPO, "show", f"{PACK_SHA}:research/round-11/fixtures/civic_object.json"],
                                 capture_output=True, check=True, timeout=30).stdout
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            self.skipTest("PACK_SHA not available locally (git fetch origin codex/govtech-main-interface)")
        self.assertEqual(json.loads(raw), CONTRACT_FIXTURE)

    def test_fixture_valid_for_contract_and_demo(self):
        self.assertEqual(codes(CONTRACT_FIXTURE, "contract"), set())
        self.assertEqual(codes(CONTRACT_FIXTURE, "demo"), set())

    def test_fixture_rejected_in_real_slice(self):
        self.assertIn("synthetic_in_real", codes(CONTRACT_FIXTURE, "real"))

    def test_minimal_real_record_valid(self):
        self.assertEqual(codes(real_record(), "real"), set())


class ShapeRules(unittest.TestCase):
    def test_unknown_top_level_field_rejected(self):
        obj = dict(CONTRACT_FIXTURE, internal_notes="служебное")
        self.assertIn("unknown_field", codes(obj, "contract"))

    def test_html_in_text_rejected(self):
        obj = dict(CONTRACT_FIXTURE, description="<b>Демо</b> запись")
        self.assertIn("text_html", codes(obj, "contract"))

    def test_bad_dates_rejected(self):
        obj = copy.deepcopy(CONTRACT_FIXTURE)
        obj["schedule"]["planned_start"] = "14.10.2026"
        self.assertIn("date_format", codes(obj, "contract"))
        obj["schedule"]["planned_start"] = "2026-02-30"
        self.assertIn("date_format", codes(obj, "contract"))

    def test_negative_or_nan_budget_rejected(self):
        for bad in (-1, float("nan"), float("inf"), "100", True):
            obj = copy.deepcopy(CONTRACT_FIXTURE)
            obj["budget"]["amount_kzt"] = bad
            self.assertIn("budget_amount", codes(obj, "contract"), bad)

    def test_revision_must_be_positive_int(self):
        for bad in (0, -1, 1.5, True, "2"):
            self.assertIn("revision", codes(dict(CONTRACT_FIXTURE, revision=bad), "contract"), bad)

    def test_updated_at_needs_offset(self):
        self.assertIn("timestamp_format", codes(dict(CONTRACT_FIXTURE, updated_at="2026-10-06T12:00:00"), "contract"))


class GeometryRules(unittest.TestCase):
    def test_swapped_lon_lat_detected(self):
        obj = dict(CONTRACT_FIXTURE, geometry={"type": "Point", "coordinates": [51.17, 71.43]})
        self.assertIn("geometry_swapped", codes(obj, "contract"))

    def test_other_city_rejected(self):
        obj = dict(CONTRACT_FIXTURE, geometry={"type": "Point", "coordinates": [69.59, 42.32]})  # Shymkent
        self.assertIn("geometry_outside_astana", codes(obj, "contract"))

    def test_open_polygon_rejected(self):
        ring = [[71.43, 51.17], [71.44, 51.17], [71.44, 51.18], [71.43, 51.18]]
        obj = dict(CONTRACT_FIXTURE, geometry={"type": "Polygon", "coordinates": [ring]})
        self.assertIn("geometry_ring_open", codes(obj, "contract"))

    def test_bowtie_polygon_rejected(self):
        ring = [[71.43, 51.17], [71.44, 51.18], [71.44, 51.17], [71.43, 51.18], [71.43, 51.17]]
        obj = dict(CONTRACT_FIXTURE, geometry={"type": "Polygon", "coordinates": [ring]})
        self.assertIn("geometry_self_intersection", codes(obj, "contract"))

    def test_single_point_linestring_rejected(self):
        obj = dict(CONTRACT_FIXTURE, geometry={"type": "LineString", "coordinates": [[71.43, 51.17]]})
        self.assertIn("geometry_linestring", codes(obj, "contract"))

    def test_null_geometry_needs_unknown_precision_in_real(self):
        obj = real_record()
        obj["geometry_precision"] = "source"
        self.assertIn("precision_without_geometry", codes(obj, "real"))


class ProvenanceRules(unittest.TestCase):
    def test_unknown_budget_is_not_zero(self):
        obj = real_record()
        obj["budget"] = {"amount_kzt": 0, "basis": "unknown", "source_id": None}
        self.assertIn("budget_zero", codes(obj, "real"))

    def test_budget_must_link_to_stating_source(self):
        obj = real_record()
        obj["budget"] = {"amount_kzt": 125000000, "basis": "planned", "source_id": "src-test"}
        found = codes(obj, "real")
        self.assertIn("budget_unlinked", found)          # src-test does not list budget.amount_kzt
        self.assertIn("unsupported_claim", found)
        obj["source_refs"][0]["fields"] += ["budget.amount_kzt", "budget.basis"]
        self.assertEqual(codes(obj, "real"), set())

    def test_status_without_source_rejected(self):
        obj = real_record()
        obj["status"] = "in_progress"
        self.assertIn("unsupported_claim", codes(obj, "real"))

    def test_old_announcement_is_not_current_state(self):
        obj = real_record()
        obj["status"] = "in_progress"
        obj["source_refs"][0]["fields"].append("status")
        obj["source_refs"][0]["published_on"] = "2026-05-01"
        self.assertIn("stale_status", codes(obj, "real"))
        obj["source_refs"][0]["published_on"] = "2026-09-30"
        self.assertNotIn("stale_status", codes(obj, "real"))

    def test_expected_end_is_not_actual_end(self):
        # Source of 2026-05-20 says "завершим в июне": it cannot support actual_end in June.
        obj = real_record()
        obj["status"] = "completed"
        obj["schedule"]["actual_end"] = "2026-06-30"
        obj["source_refs"][0]["published_on"] = "2026-05-20"
        obj["source_refs"][0]["fields"] += ["status", "schedule.actual_end"]
        self.assertIn("actual_end_after_publication", codes(obj, "real"))

    def test_actual_end_requires_completed_status(self):
        obj = real_record()
        obj["schedule"]["actual_end"] = "2026-09-01"
        self.assertIn("actual_end_without_completion", codes(obj, "contract"))

    def test_actual_end_in_future_rejected(self):
        obj = real_record()
        obj["status"] = "completed"
        obj["schedule"]["actual_end"] = "2026-12-01"
        self.assertIn("actual_end_in_future", codes(obj, "contract"))

    def test_unfetched_source_cannot_support_fields(self):
        obj = real_record()
        obj["source_refs"][0].update(access_status="not_fetched", retrieved_at=None)
        found = codes(obj, "real")
        self.assertIn("unfetched_support", found)
        self.assertIn("no_fetched_source", found)

    def test_fetched_needs_retrieved_at(self):
        obj = real_record()
        obj["source_refs"][0]["retrieved_at"] = None
        self.assertIn("fetched_without_time", codes(obj, "contract"))

    def test_organization_needs_source(self):
        obj = real_record()
        obj["responsible"]["organization"] = "ГУ «Управление»"
        self.assertIn("unsupported_claim", codes(obj, "real"))

    def test_geometry_from_proprietary_map_rejected(self):
        obj = real_record()
        obj["geometry"] = {"type": "Point", "coordinates": [71.43, 51.17]}
        obj["geometry_precision"] = "source"
        obj["source_refs"].append({
            "id": "src-map", "url": "https://2gis.kz/astana/geo/1", "publisher": "2GIS", "published_on": None,
            "retrieved_at": "2026-10-06T10:00:00+06:00", "access_status": "fetched", "license": None,
            "fields": ["geometry"]})
        self.assertIn("proprietary_geometry", codes(obj, "real"))

    def test_phone_number_in_text_flagged(self):
        obj = real_record()
        obj["description"] = "Звонить жителю +7 701 123 45 67"
        self.assertIn("pii_suspected", codes(obj, "real"))

    def test_hypothesis_cannot_be_published(self):
        obj = real_record()
        obj["evidence_type"] = "hypothesis"
        obj["publication"] = "published"
        self.assertIn("hypothesis_published", codes(obj, "real"))


class DemoRules(unittest.TestCase):
    def test_demo_needs_visible_marker_and_prefix(self):
        obj = dict(CONTRACT_FIXTURE, id="astana-work-01", title="Ремонт прохода", description="Работы")
        found = codes(obj, "demo")
        self.assertIn("demo_id_prefix", found)
        self.assertIn("demo_unmarked", found)

    def test_demo_carries_no_money_or_sources(self):
        obj = copy.deepcopy(CONTRACT_FIXTURE)
        obj["budget"] = {"amount_kzt": 5000000, "basis": "planned", "source_id": None}
        obj["source_refs"] = [{"id": "s", "url": "https://www.gov.kz/x", "publisher": None, "published_on": None,
                               "retrieved_at": None, "access_status": "not_fetched", "license": None, "fields": []}]
        found = codes(obj, "demo")
        self.assertIn("demo_budget", found)
        self.assertIn("demo_with_sources", found)


class CollectionRules(unittest.TestCase):
    def test_duplicate_ids_rejected(self):
        report = cv.validate_collection([CONTRACT_FIXTURE, CONTRACT_FIXTURE], profile="contract", as_of=AS_OF, fence=FENCE)
        self.assertFalse(report["valid"])
        self.assertIn("duplicate_id", {i["code"] for i in report["collection_issues"]})


if __name__ == "__main__":
    unittest.main()
