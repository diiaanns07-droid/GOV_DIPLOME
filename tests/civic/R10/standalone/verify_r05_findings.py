"""R10 skeptical re-verification of the R05 defect candidates D1-D4 (round 11).

    python3 -I -B verify_r05_findings.py <R05_ROOT>        (cwd = R05_ROOT)

Independent of r05_driver.py: own fixtures, own temp copies (tempfile under $TMPDIR, removed at the end).
Product code read before use (stdlib only, no network, no shell). build_slice.main() is never called.
Prints one JSON object.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1])
os.chdir(ROOT)
PKG = os.path.join(ROOT, "data", "civic", "astana")
TOOLS = os.path.join(PKG, "tools")
sys.path.insert(0, TOOLS)


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cv = _load("civic_v1")
bs = _load("build_slice")
ih = _load("import_helper")
TMP = tempfile.mkdtemp(prefix="r10-verify-r05-")
OUT = {"modules": {m.__name__: m.__file__ for m in (cv, bs, ih)}}
AS_OF = "2026-10-06"


def canonical(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def codes(issues, sev="error"):
    return sorted({i["code"] for i in issues if i["severity"] == sev})


def source(sid, published_on):
    return {"id": sid, "url": f"https://example.org/verify/{sid}", "role": "r10_verify", "publisher": "R10 verify",
            "publisher_basis": "r10", "title": "R10 verify", "published_on": published_on,
            "retrieved_at": "2026-10-06T10:00:00Z", "access_status": "fetched",
            "access_attempts": [{"at": "2026-10-06T10:00:00Z", "outcome": "fetched"}],
            "sha256": "1" * 64, "license": None, "license_status": "unknown", "supports": [], "notes": "R10 verify"}


def intake(oid, claims, **kw):
    rec = {"intake_version": "r05-intake-v1", "id": oid, "kind": "roadworks", "title": "Проверочная запись R10",
           "description": "", "historical": False, "geometry": None, "geometry_precision": "unknown",
           "claims": claims, "evidence_notes": "R10 verify", "reviewed_at": "2026-10-06T10:00:00Z"}
    rec.update(kw)
    return rec


def claim(field, value, sid, ctype, quote):
    return {"field": field, "value": value, "source_id": sid, "claim_type": ctype, "quote": quote, "locator": "p1"}


def pkg_copy(tag, sources=(), intakes=(), drop_geofence=False):
    d = os.path.join(TMP, tag)
    shutil.copytree(PKG, d, ignore=shutil.ignore_patterns("__pycache__"))
    if drop_geofence:
        os.remove(os.path.join(d, "geofence.json"))
    reg = json.load(open(os.path.join(d, "sources.json"), encoding="utf-8"))
    reg["sources"].extend(sources)
    json.dump(reg, open(os.path.join(d, "sources.json"), "w", encoding="utf-8"), ensure_ascii=False)
    for i, rec in enumerate(intakes):
        json.dump(rec, open(os.path.join(d, "intake", "real", f"verify-{i}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
    return d


def build_and_import(d):
    try:
        out = bs.build(d)
    except bs.IntakeError as exc:
        return {"intake_error": str(exc)}
    for name, data in out.items():
        json.dump(data, open(os.path.join(d, name), "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True)
    v = out["validation.json"]
    res = {"valid": v["valid"],
           "current": [{"id": o["id"], "status": o["status"], "schedule": o["schedule"],
                        "geometry": o["geometry"]} for o in out["objects.json"]["items"]],
           "objects_issues": {k: [(i["code"], i["severity"]) for i in lst]
                              for k, lst in v["slices"]["objects.json"]["issues"].items()},
           "public_readiness": v["public_readiness"]}
    try:
        p = ih.load_package(d)
        res["import_items"] = [i["external_id"] for i in p["items"]]
        res["import_rejected"] = [[r["external_id"], sorted({e["code"] for e in r["errors"]})] for r in p["rejected"]]
    except ih.PackageError as exc:
        res["package_error"] = str(exc)
    return res


# ---------------------------------------------------------------- D1
d1 = {}
S = [source("src-v-future", "2026-10-01")]
Q = "работы начнутся 1 ноября"
d1["expected_claim_in_progress"] = build_and_import(pkg_copy("d1a", S, [intake("ast-r05-roadworks-verify-a", [
    claim("status", "in_progress", "src-v-future", "expected", Q),
    claim("schedule.planned_start", "2026-11-01", "src-v-future", "expected", Q)])]))
# control 1: same announcement curated correctly -> status planned
d1["control_planned"] = build_and_import(pkg_copy("d1b", S, [intake("ast-r05-roadworks-verify-b", [
    claim("status", "planned", "src-v-future", "stated", Q),
    claim("schedule.planned_start", "2026-11-01", "src-v-future", "expected", Q)])]))
# control 2: the guard that does exist (completed needs reported_actual)
d1["expected_claim_completed"] = build_and_import(pkg_copy("d1c", S, [intake("ast-r05-roadworks-verify-c", [
    claim("status", "completed", "src-v-future", "expected", Q)])]))
# variant: claim_type=expected for status=planned (legit?) and in_progress without any planned_start
d1["expected_claim_in_progress_no_dates"] = build_and_import(pkg_copy("d1d", S, [intake("ast-r05-roadworks-verify-d", [
    claim("status", "in_progress", "src-v-future", "expected", Q)])]))


def real_obj(status, schedule):
    o = {"schema_version": "civic-v1", "id": "ast-r05-roadworks-verify", "city": "astana", "kind": "roadworks",
         "title": "Проверка", "description": "", "status": status, "publication": "draft", "geometry": None,
         "geometry_precision": "unknown",
         "schedule": dict({"planned_start": None, "original_planned_end": None, "current_planned_end": None,
                           "actual_end": None}, **schedule),
         "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
         "responsible": {"organization": None, "public_contact": None}, "evidence_type": "observed",
         "source_refs": [{"id": "src-v", "url": "https://example.org/v", "publisher": "x", "published_on": "2026-10-01",
                          "retrieved_at": "2026-10-06T10:00:00Z", "access_status": "fetched", "license": None,
                          "fields": ["status"] + ["schedule." + k for k in schedule]}],
         "evidence_notes": "", "updated_at": "2026-10-06T10:00:00Z", "revision": 1}
    return o


fence = cv.load_geofence(os.path.join(PKG, "geofence.json"))
d1["validator_in_progress_future_start"] = cv.validate_object(
    real_obj("in_progress", {"planned_start": "2026-11-01"}), profile="real", as_of=AS_OF, fence=fence)
d1["validator_completed_future_start"] = cv.validate_object(
    real_obj("completed", {"planned_start": "2026-12-01"}), profile="real", as_of=AS_OF, fence=fence)
OUT["D1"] = d1

# ---------------------------------------------------------------- D2
d2 = {}
SWAP = {"type": "Point", "coordinates": [51.17, 71.43]}
S2 = [source("src-v-geo", "2026-10-01")]
rec_geo = intake("ast-r05-roadworks-verify-geo", [
    claim("schedule.current_planned_end", "2026-11-15", "src-v-geo", "expected", "завершим к 15 ноября")],
    geometry=SWAP, geometry_precision="approximate", geometry_basis="точка по названию улицы")
d2["build_with_geofence"] = build_and_import(pkg_copy("d2a", S2, [rec_geo]))
d2["build_without_geofence"] = build_and_import(pkg_copy("d2b", S2, [rec_geo], drop_geofence=True))
d2["contract_profile_no_fence_accepts_swapped"] = codes(cv.validate_object(
    dict(real_obj("unknown", {}), geometry=SWAP, geometry_precision="approximate"), profile="real", as_of=AS_OF,
    fence=None))
# Does --check / any package-level check notice a missing geofence.json?
def _val_summary(out):
    v = out["validation.json"]
    return {"valid": v["valid"], "slices": {k: [s["errors"], s["warnings"], s["issues"]] for k, s in v["slices"].items()},
            "registry_issues": v["sources"]["registry_issues"]}


with_fence, without_fence = pkg_copy("d2c"), pkg_copy("d2d", drop_geofence=True)
d2["committed_package_validation_identical_with_and_without_geofence"] = (
    _val_summary(bs.build(with_fence)) == _val_summary(bs.build(without_fence)))
d2["committed_package_without_geofence_validation_valid"] = bs.build(without_fence)["validation.json"]["valid"]
d2["load_geofence_missing_returns"] = repr(cv.load_geofence(os.path.join(without_fence, "geofence.json")))
OUT["D2"] = d2

# ---------------------------------------------------------------- D4
import subprocess  # noqa: E402  (git show of the PACK fixture; read-only)
pack = json.loads(subprocess.run(["git", "-C", ROOT, "show",
                                  "9c2f5c0dae14b46c0697a9dfc7f854351bfd570d:research/round-11/fixtures/civic_object.json"],
                                 capture_output=True, check=True, timeout=60).stdout)
OUT["D4_pack_fixture_loaded"] = pack is not None
OUT["D4"] = {}
if pack is not None:
    o = copy.deepcopy(pack)
    o["evidence_type"] = "observed"
    o["source_refs"] = []
    OUT["D4"]["contract"] = [(i["code"], i["severity"]) for i in cv.validate_object(o, profile="contract", as_of=AS_OF, fence=fence)]
    OUT["D4"]["real"] = codes(cv.validate_object(o, profile="real", as_of=AS_OF, fence=fence))
    OUT["D4"]["pack_source_refs"] = pack.get("source_refs")
    OUT["D4"]["pack_evidence_type"] = pack.get("evidence_type")

# ---------------------------------------------------------------- non-vacuity of checks 09/10/11 for REAL records
# (the committed package has 0 real records, so the driver exercised the plan only with demo items)
nv = {}
S3 = [source("src-v-fresh", "2026-10-01")]
real_rec = intake("ast-r05-roadworks-verify-real", [
    claim("status", "planned", "src-v-fresh", "stated", "ремонт начнётся 20 октября"),
    claim("schedule.planned_start", "2026-10-20", "src-v-fresh", "expected", "ремонт начнётся 20 октября"),
    claim("schedule.original_planned_end", "2026-11-15", "src-v-fresh", "expected", "завершим к 15 ноября"),
    claim("schedule.current_planned_end", "2026-11-15", "src-v-fresh", "expected", "завершим к 15 ноября")])
dr = pkg_copy("nv", S3, [real_rec])
br = build_and_import(dr)
nv["build_valid"] = br["valid"]
p1, p2 = ih.load_package(dr), ih.load_package(dr)
real_items = [i for i in p1["items"] if not i["demo"]]
nv["real_items"] = [i["external_id"] for i in real_items]
nv["real_suggested_publication"] = sorted({i["suggested_publication"] for i in real_items})
nv["real_create_body_server_owned"] = sorted({k for i in real_items for k in i["create_body"]
                                              if k in ("id", "revision", "updated_at", "publication")})
nv["real_digest_stable"] = [i["digest"] for i in p1["items"]] == [i["digest"] for i in p2["items"]]
first = ih.plan(real_items, None, p1["package"]["sources"])
nv["real_first_actions"] = sorted({(a["action"], a.get("publication_after")) for a in first})
same = {i["external_id"]: {"digest": i["digest"], "publication": "draft", "edited_after_import": False,
                           "source": i["source"], "schedule": i["schedule"]} for i in real_items}
nv["real_reimport_actions"] = sorted({a["action"] for a in ih.plan(real_items, same, p1["package"]["sources"])})
pub = {k: dict(v, digest="stale", publication="published") for k, v in same.items()}
nv["real_changed_published_actions"] = sorted({a["action"] for a in ih.plan(real_items, pub, p1["package"]["sources"])})
OUT["non_vacuity_real_path"] = nv

shutil.rmtree(TMP, ignore_errors=True)
OUT["tmp_removed"] = not os.path.exists(TMP)
print(json.dumps(OUT, ensure_ascii=False, sort_keys=True, indent=1))
