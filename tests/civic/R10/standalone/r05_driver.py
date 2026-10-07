"""R10 standalone driver for R05 (Astana data package, validator, licences). Round 11.

    python3 -I -B r05_driver.py <R05_ROOT> [<licfetch_manifest.json>]      (cwd = R05_ROOT)

Prints ONE JSON object of raw observations; standalone_r05.py asserts on it.
Product code (data/civic/astana/tools/{civic_v1,build_slice,import_helper,build_geofence,schedule_diff}.py)
was read before use: stdlib only, no network, no shell; build_slice.build()/import_helper.load_package()
only read files, build_slice.main() (writes into the package) is NOT called. probe_sources.py (network)
is never imported. Every write here goes to a fresh tempfile.mkdtemp() that is removed at the end.
R10's own checker (tests/civic/R10/r10lib/contract.py) and BAD_VARIANTS come from this repository, not
from the product.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
R10_DIR = os.path.dirname(HERE)
AS_OF = "2026-10-06"
PACK_SHA = "9c2f5c0dae14b46c0697a9dfc7f854351bfd570d"
PACK_FIXTURE_SHA256 = "e2ba1de7d263f69629d12c01dea35c774f0be321a1fb9f7685787c33caad88f2"


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return repr(v)


def _canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ------------------------------------------------------------------ R10 side (own code)
_saved_path = list(sys.path)
TFC = _load("r10_test_fixture_contract", os.path.join(R10_DIR, "test_fixture_contract.py"))
R10C = TFC.contract
BAD_VARIANTS = TFC.BAD_VARIANTS
sys.path[:] = _saved_path  # undo the R10 test module's sys.path insert

# ------------------------------------------------------------------ product side
ROOT = os.path.abspath(sys.argv[1])
LICFETCH = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
os.chdir(ROOT)
sys.path.insert(0, ROOT)
SYS_PATH0_BEFORE_PRODUCT = sys.path[0]
PKG = os.path.join(ROOT, "data", "civic", "astana")
TOOLS = os.path.join(PKG, "tools")
cv = _load("civic_v1", os.path.join(TOOLS, "civic_v1.py"))
bs = _load("build_slice", os.path.join(TOOLS, "build_slice.py"))
ih = _load("import_helper", os.path.join(TOOLS, "import_helper.py"))
bg = _load("build_geofence", os.path.join(TOOLS, "build_geofence.py"))
sd = _load("schedule_diff", os.path.join(TOOLS, "schedule_diff.py"))
FENCE = cv.load_geofence(os.path.join(PKG, "geofence.json"))
TMP = tempfile.mkdtemp(prefix="r10-r05-")

OUT: dict = {"meta": {}}


def git(*args) -> bytes:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, check=True, timeout=60).stdout


OUT["meta"] = {
    "root": ROOT,
    "head": git("rev-parse", "HEAD").decode().strip(),
    "python": sys.version.split()[0],
    "sys_path0_before_product_import": SYS_PATH0_BEFORE_PRODUCT,
    "modules": {m.__name__: m.__file__ for m in (cv, bs, ih, bg, sd)},
    "r10_contract_file": R10C.__file__,
    "tmp": TMP,
}


def r05_verdict(obj, profile="contract", fence=FENCE, as_of=AS_OF):
    issues = cv.validate_object(obj, profile=profile, as_of=as_of, fence=fence)
    errs = sorted({i["code"] for i in issues if i["severity"] == "error"})
    warns = sorted({i["code"] for i in issues if i["severity"] == "warning"})
    return {"accept": not errs, "errors": errs, "warnings": warns}


def r10_verdict(obj):
    probs = R10C.check_object(obj)
    return {"accept": not probs, "problems": probs}


# ------------------------------------------------------------------ 1. PACK fixture
pack_bytes = git("show", f"{PACK_SHA}:research/round-11/fixtures/civic_object.json")
pack = json.loads(pack_bytes)
OUT["pack_fixture"] = {
    "sha256": hashlib.sha256(pack_bytes).hexdigest(),
    "same_as_r10_copy": pack == TFC.load_fixture(),
    "r05_contract": r05_verdict(pack, "contract"),
    "r05_demo": r05_verdict(pack, "demo"),
    "r05_real": r05_verdict(pack, "real"),
    "r10": r10_verdict(pack),
}

# ------------------------------------------------------------------ 2. R10 BAD_VARIANTS
rows = []
for desc, path, value, needle in BAD_VARIANTS:
    obj = TFC.mutate(path, value)
    rows.append({
        "desc": desc, "path": path, "value": _jsonable(value),
        "r05_contract": r05_verdict(obj, "contract"),
        "r05_contract_nofence": r05_verdict(obj, "contract", fence=None),
        "r05_real": r05_verdict(obj, "real"),
        "r10": r10_verdict(obj),
    })
OUT["bad_variants"] = rows


# ------------------------------------------------------------------ 3. extra variants (R10, from CONTRACT)
def fx():
    return copy.deepcopy(pack)


def ref(**kw):
    base = {"id": "src-r10-test", "url": "https://example.org/r10/news-1", "publisher": "R10 test publisher",
            "published_on": "2026-10-01", "retrieved_at": "2026-10-06T10:00:00Z", "access_status": "fetched",
            "license": None, "fields": []}
    base.update(kw)
    return base


extra = {}


def add_extra(key, obj):
    extra[key] = {"r05_contract": r05_verdict(obj, "contract"), "r05_real": r05_verdict(obj, "real"),
                  "r10": r10_verdict(obj)}


o = fx(); o["title"] = "<b>Ремонт</b> прохода"; add_extra("html_in_title", o)
o = fx(); o["description"] = "Вопросы по телефону +7 701 123 45 67"; add_extra("phone_in_description", o)
o = fx(); o["geometry"] = {"type": "Point", "coordinates": [71.43, 51.17, 350.0]}; add_extra("position_3d", o)
o = fx(); o["geometry"] = None; o["geometry_precision"] = "source"; add_extra("precision_source_without_geometry", o)
o = fx(); o["evidence_type"] = "observed"; add_extra("observed_without_any_source", o)
o = fx(); o["evidence_type"] = "observed"
o["source_refs"] = [ref(access_status="not_fetched", retrieved_at=None, fields=["status", "schedule.current_planned_end"])]
add_extra("observed_supported_only_by_unfetched_source", o)
o = fx(); o["source_refs"] = [ref(retrieved_at=None)]; add_extra("fetched_source_without_retrieved_at", o)
o = fx(); r = ref(); del r["license"]; o["source_refs"] = [r]; add_extra("source_ref_missing_license_key", o)
o = fx(); o["budget"] = {"amount_kzt": 0, "basis": "unknown", "source_id": None}; add_extra("budget_zero_amount", o)
OUT["extra_variants"] = extra


# ------------------------------------------------------------------ 4. real-profile semantics (false facts)
def real_obj(**kw):
    o = {
        "schema_version": "civic-v1", "id": "ast-r05-roadworks-r10-test", "city": "astana", "kind": "roadworks",
        "title": "Ремонт тротуара (тестовая запись R10)", "description": "", "status": "unknown",
        "publication": "draft", "geometry": None, "geometry_precision": "unknown",
        "schedule": {"planned_start": None, "original_planned_end": None, "current_planned_end": None,
                     "actual_end": None},
        "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
        "responsible": {"organization": None, "public_contact": None},
        "evidence_type": "observed", "source_refs": [ref(fields=["schedule.current_planned_end"])],
        "evidence_notes": "R10 test", "updated_at": "2026-10-06T10:00:00Z", "revision": 1,
    }
    o["schedule"]["current_planned_end"] = "2026-11-15"
    for k, v in kw.items():
        if k == "schedule":
            o["schedule"].update(v)
        else:
            o[k] = v
    return o


sem = {}
sem["baseline_expected_end_status_unknown"] = r05_verdict(real_obj(), "real")
sem["expected_end_recorded_as_actual_end"] = r05_verdict(real_obj(
    status="completed", schedule={"actual_end": "2026-06-30", "current_planned_end": "2026-06-30"},
    source_refs=[ref(published_on="2026-05-01", fields=["status", "schedule.actual_end", "schedule.current_planned_end"])]),
    "real")
sem["actual_end_after_as_of"] = r05_verdict(real_obj(
    status="completed", schedule={"actual_end": "2026-10-20", "current_planned_end": "2026-10-20"},
    source_refs=[ref(published_on="2026-10-01", fields=["status", "schedule.actual_end", "schedule.current_planned_end"])]),
    "real")
sem["old_announcement_status_in_progress"] = r05_verdict(real_obj(
    status="in_progress", source_refs=[ref(published_on="2025-03-01", fields=["status", "schedule.current_planned_end"])]),
    "real")
sem["future_announcement_status_in_progress"] = r05_verdict(real_obj(
    status="in_progress", schedule={"planned_start": "2026-11-01"},
    source_refs=[ref(published_on="2026-10-01", fields=["status", "schedule.planned_start", "schedule.current_planned_end"])]),
    "real")
sem["future_start_status_completed"] = r05_verdict(real_obj(
    status="completed", schedule={"planned_start": "2026-12-01", "current_planned_end": "2027-03-01"},
    source_refs=[ref(published_on="2026-10-01", fields=["status", "schedule.planned_start", "schedule.current_planned_end"])]),
    "real")
sem["observed_only_unfetched_source"] = r05_verdict(real_obj(
    status="planned", source_refs=[ref(access_status="not_fetched", retrieved_at=None,
                                       fields=["status", "schedule.current_planned_end"])]), "real")
sem["observed_without_any_source"] = r05_verdict(real_obj(source_refs=[], schedule={"current_planned_end": None}), "real")
sem["budget_from_unfetched_source"] = r05_verdict(real_obj(
    budget={"amount_kzt": 250000000, "basis": "planned", "source_id": "src-r10-nf"},
    source_refs=[ref(fields=["schedule.current_planned_end"]),
                 ref(id="src-r10-nf", access_status="not_fetched", retrieved_at=None,
                     fields=["budget.amount_kzt", "budget.basis"])]), "real")
sem["budget_zero_as_unknown"] = r05_verdict(real_obj(
    budget={"amount_kzt": 0, "basis": "planned", "source_id": "src-r10-test"},
    source_refs=[ref(fields=["schedule.current_planned_end", "budget.amount_kzt", "budget.basis"])]), "real")
sem["geometry_copied_from_2gis"] = r05_verdict(real_obj(
    geometry={"type": "Point", "coordinates": [71.43, 51.17]}, geometry_precision="source",
    source_refs=[ref(fields=["schedule.current_planned_end"]),
                 ref(id="src-r10-2gis", url="https://2gis.kz/astana/geo/123", fields=["geometry"])]), "real")
sem["synthetic_in_real"] = r05_verdict(pack, "real")
OUT["real_semantics"] = sem


# ------------------------------------------------------------------ 5. build pipeline on a temp copy
def temp_pkg(tag: str, extra_sources: list, intakes: list) -> str:
    d = os.path.join(TMP, tag)
    shutil.copytree(PKG, d, ignore=shutil.ignore_patterns("__pycache__"))
    with open(os.path.join(d, "sources.json"), encoding="utf-8") as fh:
        reg = json.load(fh)
    reg["sources"].extend(extra_sources)
    with open(os.path.join(d, "sources.json"), "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False)
    for i, rec in enumerate(intakes):
        with open(os.path.join(d, "intake", "real", f"r10-{i}.json"), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False)
    return d


def src(sid, published_on):
    return {"id": sid, "url": f"https://example.org/r10/{sid}", "role": "r10_test", "publisher": "R10 test",
            "publisher_basis": "r10", "title": "R10 test", "published_on": published_on,
            "retrieved_at": "2026-10-06T10:00:00Z", "access_status": "fetched",
            "access_attempts": [{"at": "2026-10-06T10:00:00Z", "outcome": "fetched"}],
            "sha256": "0" * 64, "license": None, "license_status": "unknown", "supports": [], "notes": "R10 test"}


def intake(oid, claims, title="Тестовая запись R10"):
    return {"intake_version": "r05-intake-v1", "id": oid, "kind": "roadworks", "title": title,
            "description": "", "historical": False, "geometry": None, "geometry_precision": "unknown",
            "claims": claims, "evidence_notes": "R10 test", "reviewed_at": "2026-10-06T10:00:00Z"}


def claim(field, value, sid, ctype, quote="тестовая выдержка R10"):
    return {"field": field, "value": value, "source_id": sid, "claim_type": ctype, "quote": quote, "locator": "p1"}


def write_outputs(d, out):
    for name, data in out.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)


def run_build(tag, extra_sources, intakes):
    d = temp_pkg(tag, extra_sources, intakes)
    res = {}
    try:
        out = bs.build(d)
    except bs.IntakeError as exc:
        return {"intake_error": str(exc)}
    write_outputs(d, out)
    v = out["validation.json"]
    res["validation_valid"] = v["valid"]
    res["current"] = [{"id": o["id"], "status": o["status"], "publication": o["publication"],
                       "schedule": o["schedule"]} for o in out["objects.json"]["items"]]
    res["historical"] = [{"id": o["id"], "status": o["status"]} for o in out["historical.json"]["items"]]
    res["issue_codes"] = sorted({i["code"] for s in v["slices"].values() for lst in s["issues"].values()
                                 for i in lst if i["severity"] == "error"})
    try:
        pkg = ih.load_package(d, include_historical=True)
        res["import_items"] = [i["external_id"] for i in pkg["items"]]
        res["import_rejected"] = [{"id": r["external_id"], "codes": sorted({e["code"] for e in r["errors"]})}
                                  for r in pkg["rejected"]]
    except ih.PackageError as exc:
        res["import_package_error"] = str(exc)
    return res


pipe = {}
pipe["old_planned_announcement"] = run_build("old-planned", [src("src-r10-old", "2025-04-01")], [intake(
    "ast-r05-roadworks-r10-old", [claim("status", "planned", "src-r10-old", "stated"),
                                  claim("schedule.original_planned_end", "2025-09-30", "src-r10-old", "expected"),
                                  claim("schedule.current_planned_end", "2025-09-30", "src-r10-old", "expected")])])
pipe["old_completed_report"] = run_build("old-completed", [src("src-r10-done", "2025-05-02")], [intake(
    "ast-r05-roadworks-r10-done", [claim("status", "completed", "src-r10-done", "reported_actual"),
                                   claim("schedule.actual_end", "2025-05-01", "src-r10-done", "reported_actual")])])
pipe["future_announcement_in_progress"] = run_build("future", [src("src-r10-future", "2026-10-01")], [intake(
    "ast-r05-roadworks-r10-future", [claim("status", "in_progress", "src-r10-future", "expected",
                                           "работы начнутся 1 ноября"),
                                     claim("schedule.planned_start", "2026-11-01", "src-r10-future", "expected",
                                           "работы начнутся 1 ноября")])])
pipe["claim_from_unfetched_source"] = run_build("unfetched", [], [intake(
    "ast-r05-roadworks-r10-unf", [claim("schedule.current_planned_end", "2026-11-15", "src-astana-gov-kz", "stated")])])
pipe["expected_date_as_actual_end"] = run_build("expected-actual", [src("src-r10-exp", "2026-05-01")], [intake(
    "ast-r05-roadworks-r10-exp", [claim("status", "completed", "src-r10-exp", "reported_actual"),
                                  claim("schedule.actual_end", "2026-06-30", "src-r10-exp", "expected",
                                        "завершим в июне")])])
pipe["fresh_planned_announcement"] = run_build("fresh", [src("src-r10-fresh", "2026-10-01")], [intake(
    "ast-r05-roadworks-r10-fresh", [claim("status", "planned", "src-r10-fresh", "stated"),
                                    claim("schedule.planned_start", "2026-10-20", "src-r10-fresh", "expected"),
                                    claim("schedule.current_planned_end", "2026-11-15", "src-r10-fresh", "expected"),
                                    claim("schedule.original_planned_end", "2026-11-15", "src-r10-fresh", "expected")])])
OUT["pipeline"] = pipe

# ------------------------------------------------------------------ 6. import plan on the real package
imp = {}
b1, b2 = bs.build(), bs.build()
committed = {}
for name in b1:
    with open(os.path.join(PKG, name), encoding="utf-8") as fh:
        committed[name] = json.load(fh) == b1[name]
imp["build_deterministic"] = _canonical(b1) == _canonical(b2)
imp["committed_equals_build"] = committed
pkg1 = ih.load_package(PKG, include_demo=True, include_historical=True)
pkg2 = ih.load_package(PKG, include_demo=True, include_historical=True)
items = pkg1["items"]
imp["counts"] = {"items": len(items), "rejected": len(pkg1["rejected"]),
                 "real_items": sum(1 for i in items if not i["demo"]), "demo_items": sum(1 for i in items if i["demo"])}
first = ih.plan(items, None, pkg1["package"]["sources"])
imp["first_actions"] = sorted({a["action"] for a in first})
imp["first_publication_after"] = sorted({str(a.get("publication_after")) for a in first})
imp["create_body_server_owned_keys"] = sorted({k for i in items for k in i["create_body"]
                                               if k in ("id", "revision", "updated_at", "publication")})
imp["real_suggested_publication"] = sorted({i["suggested_publication"] for i in items if not i["demo"]})
imp["demo_suggested_publication"] = sorted({i["suggested_publication"] for i in items if i["demo"]})
imp["digests_stable_across_loads"] = [i["digest"] for i in items] == [i["digest"] for i in pkg2["items"]]
existing_same = {i["external_id"]: {"digest": i["digest"], "publication": "draft", "edited_after_import": False,
                                    "source": i["source"], "schedule": i["schedule"]} for i in items}
imp["reimport_actions"] = sorted({a["action"] for a in ih.plan(items, existing_same, pkg1["package"]["sources"])})
existing_pub = {k: dict(v, digest="stale", publication="published") for k, v in existing_same.items()}
pub_actions = ih.plan(items, existing_pub, pkg1["package"]["sources"])
imp["changed_published_actions"] = sorted({a["action"] for a in pub_actions})
existing_edit = {k: dict(v, digest="stale", edited_after_import=True) for k, v in existing_same.items()}
imp["changed_hand_edited_actions"] = sorted({a["action"] for a in ih.plan(items, existing_edit, pkg1["package"]["sources"])})
existing_missing = dict(existing_same)
existing_missing["demo-astana-r10-removed"] = {"digest": "x", "publication": "published", "source": "r05-astana-demo",
                                               "edited_after_import": False, "schedule": {}}
miss = [a for a in ih.plan(items, existing_missing, pkg1["package"]["sources"])
        if a["external_id"] == "demo-astana-r10-removed"]
imp["missing_record_actions"] = sorted({a["action"] for a in miss})
all_action_names = set()
for plan_ in (first, pub_actions, miss):
    all_action_names |= {a["action"] for a in plan_}
imp["any_publish_or_archive_action"] = sorted(a for a in all_action_names if "publish" in a or "archiv" in a)


# smuggling: a slice whose hash is recomputed (README formula) but which carries forbidden records
def smuggle(tag, objs, geofence=True):
    d = os.path.join(TMP, "smuggle-" + tag)
    shutil.copytree(PKG, d, ignore=shutil.ignore_patterns("__pycache__"))
    if not geofence:
        os.remove(os.path.join(d, "geofence.json"))
    path = os.path.join(d, "objects.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["items"] = objs
    sl = data["slice"]
    digest = hashlib.sha256(_canonical({"items": objs, "inputs": sl["inputs"]})).hexdigest()
    sl["count"] = len(objs)
    sl["content_sha256"] = digest
    sl["version"] = f"r05-astana-current-{sl['as_of']}-{digest[:12]}"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    try:
        p = ih.load_package(d)
    except ih.PackageError as exc:
        return {"package_error": str(exc)}
    return {"items": [i["external_id"] for i in p["items"]],
            "rejected": [{"id": r["external_id"], "codes": sorted({e["code"] for e in r["errors"]})} for r in p["rejected"]]}


syn = fx(); syn["id"] = "ast-r05-roadworks-r10-syn"
swapped = real_obj(geometry={"type": "Point", "coordinates": [51.17, 71.43]}, geometry_precision="approximate")
imp["smuggle_synthetic_into_real"] = smuggle("synthetic", [syn])
imp["smuggle_observed_without_source"] = smuggle("nosource", [real_obj(source_refs=[], schedule={"current_planned_end": None})])
imp["smuggle_swapped_coords_with_geofence"] = smuggle("swapped-fence", [swapped])
imp["smuggle_swapped_coords_without_geofence"] = smuggle("swapped-nofence", [swapped], geofence=False)
OUT["import"] = imp

# ------------------------------------------------------------------ 7. geofence
geo = {}
with open(os.path.join(PKG, "geofence.json"), "rb") as fh:
    geo_raw = fh.read()
fence = json.loads(geo_raw)
lons = [p[0] for poly in fence["polygons"] for ring in poly["rings"] for p in ring]
lats = [p[1] for poly in fence["polygons"] for ring in poly["rings"] for p in ring]
geo["computed_bbox"] = [min(lons), min(lats), max(lons), max(lats)]
geo["declared_city_bbox"] = fence.get("city_bbox")
geo["outer_bbox"] = fence.get("outer_bbox")
geo["margin_deg"] = fence.get("margin_deg")
geo["polygons"] = len(fence["polygons"])
geo["districts"] = sorted({str(p.get("district_id")) for p in fence["polygons"]})
rings = [ring for poly in fence["polygons"] for ring in poly["rings"]]
geo["rings"] = len(rings)
geo["open_rings"] = sum(1 for r in rings if r[0] != r[-1])
geo["short_rings"] = sum(1 for r in rings if len(r) < 4)
geo["positions_not_2d"] = sum(1 for r in rings for p in r if len(p) != 2)
geo["positions_lon_gt_lat"] = all(p[0] > p[1] for r in rings for p in r)
geo["license"] = fence.get("license")
geo["input"] = fence.get("input")
geo_in = os.path.join(ROOT, (fence.get("input") or {}).get("path") or "data/astana_districts.geojson")
with open(geo_in, "rb") as fh:
    geo["input_sha256_actual"] = hashlib.sha256(fh.read()).hexdigest()
geo["rebuild_equals_committed"] = bg.build(geo_in) == fence


def r10_pip(lon, lat, ring):  # independent ray casting
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        (xi, yi), (xj, yj) = ring[i][:2], ring[j][:2]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def r10_in_city(lon, lat):
    for poly in fence["polygons"]:
        rs = poly["rings"]
        if r10_pip(lon, lat, rs[0]) and not any(r10_pip(lon, lat, h) for h in rs[1:]):
            return True
    return False


POINTS = {  # approximate public coordinates, R10 general knowledge, [lon, lat]
    "baiterek": (71.4305, 51.1283), "khan_shatyr": (71.4040, 51.1322), "ak_orda": (71.4460, 51.1258),
    "almaty_city": (76.9286, 43.2567), "karaganda": (73.0870, 49.8060), "kokshetau": (69.3890, 53.2830),
    "baiterek_swapped": (51.1283, 71.4305),
}
geo["points"] = {k: {"r05": cv.fence_position(lon, lat, FENCE), "r10_inside_district": r10_in_city(lon, lat)}
                 for k, (lon, lat) in POINTS.items()}
OUT["geofence"] = geo

# ------------------------------------------------------------------ 8. sources / audits / licences
s = {}
with open(os.path.join(PKG, "sources.json"), encoding="utf-8") as fh:
    reg = json.load(fh)
audits = []
for f in (reg.get("network_audit") or {}).get("audit_files") or []:
    with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
        audits.extend(json.load(fh))
by_url: dict = {}
for row in audits:
    by_url.setdefault(row["url"], []).extend(row["attempts"])
REQUIRED = ("id", "url", "publisher", "retrieved_at", "access_status", "license")
s["count"] = len(reg["sources"])
s["missing_required_keys"] = {x.get("id"): [k for k in REQUIRED if k not in x] for x in reg["sources"]
                              if any(k not in x for k in REQUIRED)}
s["null_publisher"] = sorted(x["id"] for x in reg["sources"] if x.get("publisher") is None)
s["null_license"] = sorted(x["id"] for x in reg["sources"] if x.get("license") is None)
s["by_status"] = {}
for x in reg["sources"]:
    s["by_status"][x.get("access_status")] = s["by_status"].get(x.get("access_status"), 0) + 1
mism = []
for x in reg["sources"]:
    att = by_url.get(x["url"], [])
    fetched_att = [a for a in att if a.get("outcome") == "fetched" and a.get("http_status") == 200]
    st = x.get("access_status")
    if st not in ("fetched", "not_fetched", "unavailable"):
        mism.append([x["id"], "bad access_status"])
    if st == "fetched":
        if not fetched_att:
            mism.append([x["id"], "fetched but no fetched audit attempt"])
        elif x.get("sha256") not in {a.get("sha256") for a in fetched_att}:
            mism.append([x["id"], "sha256 differs from audit"])
        elif x.get("retrieved_at") not in {a.get("at") for a in fetched_att}:
            mism.append([x["id"], "retrieved_at is not an audit fetch time"])
    else:
        if fetched_att:
            mism.append([x["id"], "audit shows a successful fetch but status is " + str(st)])
        if x.get("retrieved_at") is not None or x.get("sha256") is not None:
            mism.append([x["id"], "not fetched but has retrieved_at/sha256"])
        if x.get("supports"):
            mism.append([x["id"], "not fetched but supports something"])
        if not att:
            mism.append([x["id"], "no audit attempt for this URL"])
    for a in x.get("access_attempts") or []:
        if a.get("outcome") == "egress_denied" and st == "fetched" and len(x["access_attempts"]) == 1:
            mism.append([x["id"], "only attempt denied but status fetched"])
s["audit_mismatches"] = mism
s["audit_urls_not_in_registry"] = sorted(set(by_url) - {x["url"] for x in reg["sources"]})
s["denied_hosts_marked_fetched"] = sorted(x["id"] for x in reg["sources"] if x.get("access_status") == "fetched"
                                          and all(a.get("outcome") == "egress_denied" for a in by_url.get(x["url"], [{}])))
s["license_claimed_without_fetch"] = sorted([x["id"], x.get("license"), x.get("license_status")]
                                            for x in reg["sources"] if x.get("access_status") != "fetched" and x.get("license"))
reg_by_id = {x["id"]: x for x in reg["sources"]}

objs = {}
for name in ("objects.json", "historical.json", "demo_synthetic.json"):
    with open(os.path.join(PKG, name), encoding="utf-8") as fh:
        objs[name] = json.load(fh)
bad_real = []
for name in ("objects.json", "historical.json"):
    for o in objs[name]["items"]:
        fetched = [r for r in o.get("source_refs") or [] if r.get("access_status") == "fetched" and r.get("fields")]
        if o.get("evidence_type") in ("observed", "derived") and not fetched:
            bad_real.append(o.get("id"))
        if o.get("evidence_type") == "synthetic" or o.get("publication") != "draft":
            bad_real.append(o.get("id"))
        for r in o.get("source_refs") or []:
            if reg_by_id.get(r.get("id"), {}).get("access_status") != r.get("access_status"):
                bad_real.append(o.get("id"))
s["real_counts"] = {n: len(objs[n]["items"]) for n in ("objects.json", "historical.json")}
s["real_records_violating_provenance"] = bad_real
demo = objs["demo_synthetic.json"]
s["demo_flag"] = demo["slice"].get("demo")
s["demo_bad"] = sorted(o["id"] for o in demo["items"] if o["evidence_type"] != "synthetic" or o["source_refs"]
                       or o["budget"]["amount_kzt"] is not None or not o["id"].startswith("demo-")
                       or not any(w in (o["title"] + " " + o["description"]).lower() for w in ("демо", "синтет")))
s["demo_publications"] = sorted({o["publication"] for o in demo["items"]})
with open(os.path.join(PKG, "validation.json"), encoding="utf-8") as fh:
    val = json.load(fh)
s["validation_sources"] = {k: val["sources"][k] for k in ("total", "fetched", "not_fetched", "unavailable")}
with open(os.path.join(PKG, "LICENSE_REGISTER.json"), encoding="utf-8") as fh:
    lr = json.load(fh)
lic_rows, lic_bad = [], []
for e in lr["entries"]:
    cited = [ev for ev in e.get("terms_evidence", []) if ev.get("source_id")]
    for ev in cited:
        rs = reg_by_id.get(ev["source_id"])
        if rs is None:
            lic_bad.append([e["id"], ev["source_id"], "cited source not in registry"])
        elif rs.get("access_status") != ev.get("access_status"):
            lic_bad.append([e["id"], ev["source_id"], "access_status differs from registry"])
        elif ev.get("sha256") and ev["sha256"] != rs.get("sha256"):
            lic_bad.append([e["id"], ev["source_id"], "sha256 differs from registry"])
    if e.get("verification") == "fetched_official_text" and not any(
            reg_by_id.get(ev["source_id"], {}).get("access_status") == "fetched" for ev in cited):
        lic_bad.append([e["id"], None, "fetched_official_text without a fetched cited source"])
    lic_rows.append({"id": e["id"], "license": e.get("license"), "verification": e.get("verification"),
                     "public_display": e.get("public_display"), "required_notice": e.get("required_notice"),
                     "cited": [[ev["source_id"], ev.get("access_status")] for ev in cited],
                     "local_copies": [ev.get("local_copy") for ev in e.get("terms_evidence", []) if ev.get("local_copy")]})
s["license_register"] = lic_rows
s["license_register_inconsistencies"] = lic_bad
with open(os.path.join(PKG, "ATTRIBUTION.txt"), encoding="utf-8") as fh:
    attr = fh.read()
s["attribution_has"] = {k: (k in attr) for k in ("OpenStreetMap", "openstreetmap.org/copyright", "OpenMapTiles",
                                                  "OpenFreeMap", "ODbL", "Overture Maps Foundation")}
with open(os.path.join(ROOT, "research", "round-11-results", "R05", "DELIVERY.json"), encoding="utf-8") as fh:
    dlv = json.load(fh)
s["delivery"] = {"status": dlv.get("status"), "code_commit": dlv.get("code_commit"),
                 "integration_notes": dlv.get("integration_notes"), "checks": [c.get("name") for c in dlv.get("checks", [])],
                 "r10_check_delivery": R10C.check_delivery(dlv, role="R05", pack_sha=PACK_SHA)}
if LICFETCH:
    with open(LICFETCH, encoding="utf-8") as fh:
        man = json.load(fh)
    base = os.path.dirname(os.path.abspath(LICFETCH))
    rf = {}
    for url, rel_ in man["files"].items():
        with open(os.path.join(base, rel_), "rb") as fh:
            h = hashlib.sha256(fh.read()).hexdigest()
        reg_row = next((x for x in reg["sources"] if x["url"] == url), None)
        rf[url] = {"r10_sha256": h, "r05_sha256": (reg_row or {}).get("sha256"),
                   "r05_status": (reg_row or {}).get("access_status")}
    s["licfetch"] = {"fetched_at": man.get("fetched_at"), "files": rf, "denied": man.get("denied")}
else:
    s["licfetch"] = None
OUT["sources"] = s

# ------------------------------------------------------------------ 9. schedule_diff (expected never becomes actual)
v1 = sd.make_snapshot("Ремонт тротуара на тестовой улице планируется завершить до 30 октября 2026 года.",
                      source_id="src-r10-sd", url="https://example.org/r10/sd", retrieved_at="2026-10-01T10:00:00Z",
                      published_on="2026-10-01")
v2 = sd.make_snapshot("Срок ремонта тротуара на тестовой улице перенесён: работы завершат до 15 ноября 2026 года. "
                      "Первый участок завершён 20 октября 2026 года.",
                      source_id="src-r10-sd", url="https://example.org/r10/sd", retrieved_at="2026-10-06T10:00:00Z",
                      published_on="2026-10-05")
rec = real_obj(schedule={"original_planned_end": "2026-10-30", "current_planned_end": "2026-10-30"})
dd = sd.diff(v1, v2, rec)
OUT["schedule_diff"] = {
    "auto_applied": dd["auto_applied"],
    "all_require_editor": all(f["requires_editor_confirmation"] for f in dd["findings"]),
    "findings": [{"kind": f["kind"], "field": f["field"], "old": f["old"], "new": f["new"]} for f in dd["findings"]],
}

shutil.rmtree(TMP, ignore_errors=True)
OUT["meta"]["tmp_removed"] = not os.path.exists(TMP)
print(json.dumps(OUT, ensure_ascii=False, sort_keys=True))
