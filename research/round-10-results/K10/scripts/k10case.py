"""K10 round 10: school-access-case-v1 helpers (stdlib only) — strict validator, canonical digest proposal, transfer check.

Follows research/round-10/CONTRACT.txt @ codex/govtech-main-interface 7c6fb75. BUILD owns the authoritative
canonicalisation of case_digest; `case_digest_k10` here is a documented proposal (k10-canon-v1) used by the K10 tests:
it covers the calculation semantics (city, snapshot, bbox, sources, records, coordinates, QA codes, parameters,
assumptions) and is independent of record order. Labels and free-text provenance are not part of it.

    python k10case.py validate <case.json> [--max-school-buffer-m N]
    python k10case.py digest <case.json>
    python k10case.py transfer <from_case.json> <to_case.json>
"""
import hashlib
import json
import math
import re
import sys

SCHEMA = "school-access-case-v1"
CANON = "k10-canon-v1"
CITIES = {"shymkent", "astana"}
KINDS = {"observed", "observed_secondary", "derived", "hypothesis", "synthetic"}
VERIFICATION = {"primary_checked", "secondary_only", "conflict", "not_fetched"}
ELIGIBILITY = {"known_public", "known_restricted", "unknown"}
METHODS = {"geodesic", "pedestrian-v1"}
TOP = {"schema_version", "case_id", "city_id", "title", "bbox", "snapshot_id", "sources", "schools", "origins", "candidates",
       "selected_candidate_ids", "parameters", "model_assumptions"}
SOURCE_KEYS = {"id", "url", "publisher", "title", "published_at", "data_period", "retrieved_at", "verification_status", "license", "content_sha256"}
REC = {"id", "label", "lon", "lat", "kind", "source_ids", "field_provenance", "qa"}
SCHOOL = REC | {"category", "access_eligibility", "capacity", "capacity_source_ids"}
ORIGIN = REC | {"weight", "parent_source_id", "method"}
CANDIDATE = REC | {"cost", "land_status"}
PARAMS = {"distance_method", "routing_policy_id", "threshold_m", "max_new_objects"}
COST = {"value", "currency", "period", "kind", "source_ids"}
DERIVED_RESULT_KEYS = {"plans", "rows", "facts", "metrics", "case_digest", "before_mm", "after_mm", "delta_mm", "distance_mm", "result"}
LIMITS = {"origins": 25, "candidates": 16, "schools": 400, "sources": 100, "bytes": 2_000_000, "label": 200}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
CTRL = re.compile(r"[\u0000-\u001f\u007f-\u009f]")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CaseError(ValueError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def dist_to_bbox_m(lon, lat, bbox):
    w, s, e, n = bbox
    return haversine_m(lon, lat, min(max(lon, w), e), min(max(lat, s), n))


def _fail(code, detail):
    raise CaseError(code, detail)


def _text(v, where, maxlen=LIMITS["label"], allow_none=False):
    if v is None and allow_none:
        return
    if not isinstance(v, str) or not v.strip() or len(v) > maxlen or CTRL.search(v):
        _fail("bad_text", f"{where}: non-empty text up to {maxlen} chars without control characters")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _no_results(obj, path="case"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in DERIVED_RESULT_KEYS:
                _fail("derived_field", f"{path}.{k}: a case holds inputs only; results are recomputed")
            _no_results(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _no_results(v, f"{path}[{i}]")


def _record(r, keys, where, source_ids, bbox):
    if not isinstance(r, dict):
        _fail("bad_shape", f"{where}: object expected")
    extra, missing = set(r) - keys, keys - set(r)
    if extra:
        _fail("unknown_field", f"{where}: {sorted(extra)}")
    if missing:
        _fail("missing_field", f"{where}: {sorted(missing)}")
    if not isinstance(r["id"], str) or not ID_RE.match(r["id"]):
        _fail("bad_id", f"{where}: id {r['id']!r}")
    _text(r["label"], f"{where}.label")
    if not (_num(r["lon"]) and _num(r["lat"]) and -180 <= r["lon"] <= 180 and -90 <= r["lat"] <= 90):
        _fail("bad_coordinates", f"{where}: lon/lat")
    if r["kind"] not in KINDS:
        _fail("bad_kind", f"{where}: {r['kind']!r}")
    if not isinstance(r["source_ids"], list) or not all(isinstance(x, str) for x in r["source_ids"]) or len(set(r["source_ids"])) != len(r["source_ids"]):
        _fail("bad_source_ids", where)
    unknown = [x for x in r["source_ids"] if x not in source_ids]
    if unknown:
        _fail("unknown_source", f"{where}: {unknown}")
    if not isinstance(r["field_provenance"], dict):
        _fail("bad_provenance", where)
    if not isinstance(r["qa"], list):
        _fail("bad_qa", where)
    for q in r["qa"]:
        if not (isinstance(q, dict) and set(q) == {"code", "text"} and isinstance(q["code"], str) and ID_RE.match(q["code"])):
            _fail("bad_qa", f"{where}: qa items are {{code, text}}")
        _text(q["text"], f"{where}.qa", 600)


def validate_case(case, raw_bytes=None, max_school_buffer_m=None):
    """Strict check of one school-access-case-v1 object; returns a summary or raises CaseError (atomic refusal)."""
    if raw_bytes is not None and len(raw_bytes) > LIMITS["bytes"]:
        _fail("too_large", f"{len(raw_bytes)} bytes > {LIMITS['bytes']}")
    if not isinstance(case, dict):
        _fail("bad_shape", "top level must be an object")
    extra, missing = set(case) - TOP, TOP - set(case)
    if extra:
        _fail("unknown_field", sorted(extra))
    if missing:
        _fail("missing_field", sorted(missing))
    if case["schema_version"] != SCHEMA:
        _fail("bad_schema", case["schema_version"])
    _no_results(case)
    if not isinstance(case["case_id"], str) or not ID_RE.match(case["case_id"]):
        _fail("bad_id", "case_id")
    if case["city_id"] not in CITIES:
        _fail("bad_city", case["city_id"])
    _text(case["title"], "title", 300)
    _text(case["snapshot_id"], "snapshot_id", 200)
    b = case["bbox"]
    if not (isinstance(b, list) and len(b) == 4 and all(_num(x) for x in b) and -180 <= b[0] < b[2] <= 180 and -90 <= b[1] < b[3] <= 90):
        _fail("bad_bbox", b)
    src = case["sources"]
    if not isinstance(src, list) or not src or len(src) > LIMITS["sources"]:
        _fail("bad_sources", "1..100 sources")
    sids = set()
    for i, s in enumerate(src):
        if not isinstance(s, dict) or set(s) != SOURCE_KEYS:
            _fail("bad_source", f"sources[{i}]: keys must be exactly {sorted(SOURCE_KEYS)}")
        if not isinstance(s["id"], str) or not ID_RE.match(s["id"]) or s["id"] in sids:
            _fail("bad_source", f"sources[{i}].id")
        sids.add(s["id"])
        if s["verification_status"] not in VERIFICATION:
            _fail("bad_source", f"{s['id']}: verification_status")
        if s["content_sha256"] is not None and not (isinstance(s["content_sha256"], str) and HEX64.match(s["content_sha256"])):
            _fail("bad_source", f"{s['id']}: content_sha256")
        if s["content_sha256"] is not None and s["verification_status"] == "not_fetched":
            _fail("bad_source", f"{s['id']}: not_fetched source cannot carry a content hash")
        if s["verification_status"] == "not_fetched" and s["retrieved_at"] is not None:
            _fail("bad_source", f"{s['id']}: not_fetched source has no retrieved_at")
        for k in ("url", "publisher", "title", "license"):
            _text(s[k], f"{s['id']}.{k}", 500)
    ids = set()

    def uniq(rid):
        if rid in ids:
            _fail("duplicate_id", rid)
        ids.add(rid)

    sch = case["schools"]
    if not isinstance(sch, list) or len(sch) > LIMITS["schools"]:
        _fail("bad_schools", "list up to 400")
    for i, r in enumerate(sch):
        _record(r, SCHOOL, f"schools[{i}]", sids, b)
        uniq(r["id"])
        if r["kind"] not in {"observed", "observed_secondary", "synthetic"}:
            _fail("bad_kind", f"schools[{i}]: existing schools are observed/observed_secondary (synthetic only in a demo)")
        _text(r["category"], f"schools[{i}].category", 80)
        if r["access_eligibility"] not in ELIGIBILITY:
            _fail("bad_eligibility", f"schools[{i}]")
        cap = r["capacity"]
        if cap is not None and not (isinstance(cap, int) and not isinstance(cap, bool) and cap >= 0):
            _fail("bad_capacity", f"schools[{i}]")
        if not isinstance(r["capacity_source_ids"], list) or any(x not in sids for x in r["capacity_source_ids"]):
            _fail("bad_capacity", f"schools[{i}].capacity_source_ids")
        if cap is not None and not r["capacity_source_ids"]:
            _fail("bad_capacity", f"schools[{i}]: a capacity needs its source")
        if max_school_buffer_m is not None and dist_to_bbox_m(r["lon"], r["lat"], b) > max_school_buffer_m + 1:
            _fail("outside_buffer", f"schools[{i}] {r['id']}: farther than {max_school_buffer_m} m from bbox")
    org = case["origins"]
    if not isinstance(org, list) or len(org) > LIMITS["origins"]:
        _fail("bad_origins", f"list up to {LIMITS['origins']} (UI must show the truncated rest, not hide it)")
    weights = set()
    for i, r in enumerate(org):
        _record(r, ORIGIN, f"origins[{i}]", sids, b)
        uniq(r["id"])
        if not (b[0] <= r["lon"] <= b[2] and b[1] <= r["lat"] <= b[3]):
            _fail("outside_bbox", f"origins[{i}] {r['id']}: main-case points stay in bbox")
        if not _num(r["weight"]) or r["weight"] <= 0:
            _fail("bad_weight", f"origins[{i}]")
        weights.add(r["weight"])
        if r["kind"] == "derived" and not (isinstance(r["parent_source_id"], str) and r["parent_source_id"] in sids):
            _fail("bad_origin", f"origins[{i}]: derived origin needs parent_source_id from sources")
        _text(r["method"], f"origins[{i}].method", 400)
    if len(weights) > 1:
        _fail("bad_weight", "first scenario uses equal origin weights")
    cand = case["candidates"]
    if not isinstance(cand, list) or len(cand) > LIMITS["candidates"]:
        _fail("bad_candidates", f"list up to {LIMITS['candidates']}")
    for i, r in enumerate(cand):
        _record(r, CANDIDATE, f"candidates[{i}]", sids, b)
        uniq(r["id"])
        if r["kind"] not in {"hypothesis", "synthetic"}:
            _fail("bad_kind", f"candidates[{i}]: hypothesis|synthetic")
        if not (b[0] <= r["lon"] <= b[2] and b[1] <= r["lat"] <= b[3]):
            _fail("outside_bbox", f"candidates[{i}]")
        c = r["cost"]
        if c is not None:
            if not (isinstance(c, dict) and set(c) == COST and _num(c["value"]) and c["value"] >= 0 and all(x in sids for x in c["source_ids"])):
                _fail("bad_cost", f"candidates[{i}]: null or {sorted(COST)} with real sources")
        if r["land_status"] != "unknown" and not r["source_ids"]:
            _fail("bad_land_status", f"candidates[{i}]: a confirmed land status needs a source")
        _text(r["land_status"], f"candidates[{i}].land_status", 80)
    sel = case["selected_candidate_ids"]
    p = case["parameters"]
    if not isinstance(p, dict) or set(p) != PARAMS:
        _fail("bad_parameters", f"keys must be exactly {sorted(PARAMS)}")
    if p["distance_method"] not in METHODS:
        _fail("bad_parameters", "distance_method")
    if p["distance_method"] == "geodesic" and p["routing_policy_id"] is not None:
        _fail("bad_parameters", "geodesic has routing_policy_id null")
    if p["distance_method"] == "pedestrian-v1" and not isinstance(p["routing_policy_id"], str):
        _fail("bad_parameters", "pedestrian-v1 needs routing_policy_id")
    if not (isinstance(p["threshold_m"], int) and not isinstance(p["threshold_m"], bool) and 0 < p["threshold_m"] <= 100000):
        _fail("bad_parameters", "threshold_m: positive integer metres (user parameter, not a norm)")
    if p["max_new_objects"] != 1:
        _fail("bad_parameters", "max_new_objects = 1 on the main path")
    cids = {r["id"] for r in cand}
    if not isinstance(sel, list) or len(set(sel)) != len(sel) or any(x not in cids for x in sel) or len(sel) > p["max_new_objects"]:
        _fail("bad_selection", sel)
    ma = case["model_assumptions"]
    if not isinstance(ma, list) or not ma:
        _fail("bad_assumptions", "non-empty list")
    aids = set()
    for i, a in enumerate(ma):
        if not (isinstance(a, dict) and set(a) == {"id", "text"} and isinstance(a["id"], str) and ID_RE.match(a["id"]) and a["id"] not in aids):
            _fail("bad_assumptions", f"model_assumptions[{i}]: {{id, text}} with unique id")
        aids.add(a["id"])
        _text(a["text"], f"model_assumptions[{i}]", 1200)
    return {"city_id": case["city_id"], "schools": len(sch), "origins": len(org), "candidates": len(cand), "sources": len(src),
            "eligibility": {k: sum(1 for r in sch if r["access_eligibility"] == k) for k in sorted(ELIGIBILITY)}}


def _qa_codes(r):
    return sorted(q["code"] for q in r["qa"])


def canonical(case):
    """Order-independent calculation semantics of a case (k10-canon-v1)."""
    def rec(r, extra):
        d = {"id": r["id"], "lon": round(r["lon"], 7), "lat": round(r["lat"], 7), "kind": r["kind"], "source_ids": sorted(r["source_ids"]), "qa": _qa_codes(r)}
        d.update({k: r[k] for k in extra})
        return d
    return {
        "canon": CANON, "schema_version": case["schema_version"], "city_id": case["city_id"], "snapshot_id": case["snapshot_id"],
        "bbox": [round(x, 7) for x in case["bbox"]],
        "sources": sorted(({k: s[k] for k in ("id", "url", "verification_status", "content_sha256", "license", "data_period", "published_at")} for s in case["sources"]), key=lambda s: s["id"]),
        "schools": sorted((rec(r, ("category", "access_eligibility", "capacity")) | {"capacity_source_ids": sorted(r["capacity_source_ids"])} for r in case["schools"]), key=lambda r: r["id"]),
        "origins": sorted((rec(r, ("weight", "parent_source_id")) for r in case["origins"]), key=lambda r: r["id"]),
        "candidates": sorted((rec(r, ("cost", "land_status")) for r in case["candidates"]), key=lambda r: r["id"]),
        "selected_candidate_ids": sorted(case["selected_candidate_ids"]),
        "parameters": case["parameters"],
        "model_assumption_ids": sorted(a["id"] for a in case["model_assumptions"]),
    }


def case_digest_k10(case):
    blob = json.dumps(canonical(case), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def transfer_check(a, b):
    """What must change when the user switches from case a to case b (different cities). Returns a list of findings;
    an empty list means nothing of city a survives in b."""
    out = []
    if a["city_id"] == b["city_id"]:
        out.append({"code": "same_city", "detail": a["city_id"]})
    if a["snapshot_id"] == b["snapshot_id"]:
        out.append({"code": "same_snapshot", "detail": a["snapshot_id"]})
    if a["bbox"] == b["bbox"]:
        out.append({"code": "same_bbox", "detail": a["bbox"]})
    if case_digest_k10(a) == case_digest_k10(b):
        out.append({"code": "same_digest", "detail": "k10-canon-v1"})
    rid = lambda c: {r["id"] for k in ("schools", "origins", "candidates") for r in c[k]}
    shared = sorted(rid(a) & rid(b))
    if shared:
        out.append({"code": "shared_record_ids", "detail": shared[:20]})
    pts = lambda c: {(round(r["lon"], 6), round(r["lat"], 6)) for k in ("schools", "origins", "candidates") for r in c[k]}
    same_pts = sorted(pts(a) & pts(b))
    if same_pts:
        out.append({"code": "shared_coordinates", "detail": same_pts[:10]})
    shared_src = sorted({s["id"] for s in a["sources"]} & {s["id"] for s in b["sources"]})
    if shared_src:
        out.append({"code": "shared_source_ids", "detail": shared_src})
    shared_urls = sorted({s["url"] for s in a["sources"]} & {s["url"] for s in b["sources"]})
    if shared_urls:
        out.append({"code": "shared_source_urls_info", "detail": shared_urls})
    labels = lambda c: {r["label"] for k in ("schools", "origins", "candidates") for r in c[k]}
    shared_labels = sorted(labels(a) & labels(b))
    if shared_labels:
        out.append({"code": "shared_labels_info", "detail": shared_labels[:10]})
    for k in ("schools", "origins", "candidates"):
        bb = b["bbox"]
        stray = [r["id"] for r in b[k] if dist_to_bbox_m(r["lon"], r["lat"], bb) > 5000]
        if stray:
            out.append({"code": "far_from_bbox", "detail": {k: stray[:10]}})
    return out


def main(a):
    if a[0] == "validate":
        raw = open(a[1], "rb").read()
        buf = float(a[a.index("--max-school-buffer-m") + 1]) if "--max-school-buffer-m" in a else None
        try:
            print(json.dumps(validate_case(json.loads(raw), raw, buf), ensure_ascii=False))
        except CaseError as e:
            print(json.dumps({"refused": e.code, "detail": str(e.detail)}, ensure_ascii=False))
            sys.exit(1)
    elif a[0] == "digest":
        print(case_digest_k10(json.load(open(a[1], encoding="utf-8"))))
    elif a[0] == "transfer":
        f = transfer_check(json.load(open(a[1], encoding="utf-8")), json.load(open(a[2], encoding="utf-8")))
        print(json.dumps(f, ensure_ascii=False, indent=1))
        sys.exit(1 if any(not x["code"].endswith("_info") for x in f) else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
