"""Build the R05 Astana civic-v1 slices from curated intake records.

Inputs (all inside data/civic/astana/):
  slice_config.json          as_of date, historical cutoff
  sources.json               source registry (r05-sources-v1)
  intake/real/*.json         one r05-intake-v1 record per real object (claims -> sources)
  intake/demo/*.json         lists of synthetic demo records (partial civic-v1)

Outputs:
  objects.json               real, current slice (publication=draft; editor publishes)
  historical.json            real records that are explicitly historical
  demo_synthetic.json        synthetic demo slice, slice.demo=true, separate from real data
  evidence_index.json        claim -> source -> short quote/locator, for editors (not public DTO)
  validation.json            QA report of everything above

Determinism: no wall-clock values; sorted keys/items; the slice version is a hash
of the canonical items and input digests. Same inputs -> byte-identical outputs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(PKG, "..", "..", ".."))
sys.path.insert(0, HERE)

import civic_v1 as cv  # noqa: E402

BUILDER = "data/civic/astana/tools/build_slice.py"
INTAKE_VERSION = "r05-intake-v1"
CLAIM_TYPES = ("stated", "expected", "reported_actual")
CLAIMABLE = tuple(sorted(cv.FIELD_PATHS - {"title", "description", "geometry_precision"}))
# Registry roles that describe terms of use or software, not city works: they cannot back a civic fact.
NON_FACT_ROLES = frozenset({"license_text", "license_terms", "service_terms", "documentation", "basemap_service",
                            "data_api"})


class IntakeError(ValueError):
    pass


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def slice_digest(items: list, inputs: list, name: str, as_of: str, demo: bool, max_age: int) -> str:
    """Integrity hash of a slice: items, builder inputs and every parameter that changes validation."""
    return sha256_bytes(canonical({"items": items, "inputs": inputs, "params": {
        "name": name, "as_of": as_of, "demo": demo, "status_max_age_days": max_age}}))


def sha256_file(path: str) -> str:
    """Hash of the parsed JSON in canonical form: stable across CRLF/LF checkouts."""
    return sha256_bytes(canonical(load_json(path)))


def rel(path: str) -> str:
    return os.path.relpath(path, REPO).replace(os.sep, "/")


def load_json(path: str):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except ValueError as exc:
        raise IntakeError(f"{rel(path)}: invalid JSON: {exc}") from None


def write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------- normalisation

def _empty_object(oid: str) -> dict:
    return {
        "schema_version": cv.SCHEMA_VERSION,
        "id": oid,
        "city": cv.CITY,
        "kind": None,
        "title": "",
        "description": "",
        "status": "unknown",
        "publication": "draft",
        "geometry": None,
        "geometry_precision": "unknown",
        "schedule": {k: None for k in cv.SCHEDULE_KEYS},
        "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
        "responsible": {"organization": None, "public_contact": None},
        "evidence_type": "observed",
        "source_refs": [],
        "evidence_notes": "",
        "updated_at": None,
        "revision": 1,
    }


def normalise_intake(rec: dict, registry: dict, path: str = "<intake>") -> tuple[dict, list]:
    """Turn one intake record into (civic-v1 object, evidence rows). Raises IntakeError."""
    def fail(msg):
        raise IntakeError(f"{path}: {msg}")

    if rec.get("intake_version") != INTAKE_VERSION:
        fail(f"intake_version must be {INTAKE_VERSION!r}")
    oid = rec.get("id")
    if not isinstance(oid, str) or not oid.startswith("ast-r05-") or not cv.ID_RE.match(oid):
        fail("id must look like 'ast-r05-<latin-slug>'")
    obj = _empty_object(oid)
    if rec.get("kind") not in cv.KINDS:
        fail(f"kind must be one of {cv.KINDS}")
    obj["kind"] = rec["kind"]
    for key in ("title", "description", "evidence_notes"):
        val = rec.get(key)
        if val is not None and not isinstance(val, str):
            fail(f"{key} must be text")
        obj[key] = (val or "").strip()
    reviewed = rec.get("reviewed_at")
    if cv.parse_ts(reviewed) is None:
        fail("reviewed_at must be an ISO8601 timestamp with offset (becomes updated_at)")
    obj["updated_at"] = reviewed
    et = rec.get("evidence_type", "observed")
    if et not in ("observed", "derived", "hypothesis"):
        fail("real intake evidence_type must be observed, derived or hypothesis")
    obj["evidence_type"] = et
    if rec.get("geometry") is not None:
        obj["geometry"] = rec["geometry"]
        obj["geometry_precision"] = rec.get("geometry_precision", "unknown")
        if obj["geometry_precision"] not in cv.PRECISIONS:
            fail("geometry_precision invalid")
        basis = rec.get("geometry_basis")
        basis = basis.strip() if isinstance(basis, str) else ""
        if obj["geometry_precision"] == "approximate" and not basis:
            fail("approximate geometry needs geometry_basis (how the point/line was placed)")
        if basis:  # keep the explanation in the published record, not only in the intake file
            obj["evidence_notes"] = (obj["evidence_notes"] + "\n" if obj["evidence_notes"] else "") + "Геометрия: " + basis

    evidence = []
    fields_by_source: dict[str, set] = {}
    seen_fields: dict[str, str] = {}
    for i, claim in enumerate(rec.get("claims") or []):
        cpath = f"claims[{i}]"
        field, sid, ctype = claim.get("field"), claim.get("source_id"), claim.get("claim_type")
        if field not in CLAIMABLE:
            fail(f"{cpath}.field {field!r} is not claimable")
        if ctype not in CLAIM_TYPES:
            fail(f"{cpath}.claim_type must be one of {CLAIM_TYPES}")
        src = registry.get(sid)
        if src is None:
            fail(f"{cpath}.source_id {sid!r} is not in sources.json")
        if src.get("access_status") != "fetched":
            fail(f"{cpath}: source {sid!r} was not fetched; it cannot support a value")
        if src.get("role") in NON_FACT_ROLES:
            fail(f"{cpath}: source {sid!r} is a {src.get('role')} entry, not a publication about city works")
        quote = claim.get("quote")
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 300:
            fail(f"{cpath}.quote must be a short (<=300 chars) verbatim excerpt")
        if field == "schedule.actual_end" and ctype != "reported_actual":
            fail(f"{cpath}: actual_end needs a reported_actual claim; an expected date stays in current_planned_end")
        if field == "status" and claim.get("value") == "completed" and ctype != "reported_actual":
            fail(f"{cpath}: status=completed needs a reported_actual claim")
        if field == "status" and claim.get("value") in ("in_progress", "cancelled") and ctype == "expected":
            fail(f"{cpath}: status={claim.get('value')} is an actual state; an expected claim supports only "
                 "'planned' (otherwise leave status unknown)")
        if field in seen_fields and seen_fields[field] != repr(claim.get("value")):
            fail(f"{cpath}: conflicting values for {field}; resolve before import")
        seen_fields[field] = repr(claim.get("value"))
        value = claim.get("value")
        if field == "geometry":
            if obj["geometry"] is None:
                fail(f"{cpath}: geometry claim without geometry")
            if rec.get("geometry_precision") == "approximate":
                fail(f"{cpath}: geometry claim contradicts geometry_precision=approximate")
            obj["geometry_precision"] = "source"
        elif field.startswith("schedule."):
            obj["schedule"][field.split(".", 1)[1]] = value
        elif field == "budget.amount_kzt":
            obj["budget"]["amount_kzt"] = value
            obj["budget"]["source_id"] = sid
        elif field == "budget.basis":
            obj["budget"]["basis"] = value
        elif field.startswith("responsible."):
            obj["responsible"][field.split(".", 1)[1]] = value
        elif field == "status":
            obj["status"] = value
        elif field == "kind":
            if value != obj["kind"]:
                fail(f"{cpath}: kind claim {value!r} differs from record kind {obj['kind']!r}")
        fields_by_source.setdefault(sid, set()).add(field)
        evidence.append({
            "object_id": oid, "field": field, "value": value, "claim_type": ctype,
            "source_id": sid, "quote": quote.strip(), "locator": claim.get("locator"),
        })
    claimed = {e["field"] for e in evidence}
    if "budget.amount_kzt" in claimed and "budget.basis" not in claimed:
        fail("budget.amount_kzt needs a budget.basis claim (planned/contract/spent) from the source")
    for sid in rec.get("related_sources") or []:
        if sid not in registry:
            fail(f"related source {sid!r} is not in sources.json")
        fields_by_source.setdefault(sid, set())

    for sid in sorted(fields_by_source):
        src = registry[sid]
        obj["source_refs"].append({
            "id": sid,
            "url": src["url"],
            "publisher": src.get("publisher"),
            "published_on": src.get("published_on"),
            "retrieved_at": src.get("retrieved_at"),
            "access_status": src.get("access_status"),
            "license": src.get("license"),
            "fields": sorted(fields_by_source[sid]),
        })
    evidence.sort(key=lambda e: (e["object_id"], e["field"], e["source_id"]))
    return obj, evidence


def is_historical(obj: dict, rec: dict, as_of: dt.date, cutoff_days: int) -> bool:
    if rec.get("historical") is True:
        return True
    if obj["status"] not in ("completed", "cancelled"):
        return False
    end = cv.parse_date(obj["schedule"]["actual_end"]) or cv.parse_date(obj["schedule"]["current_planned_end"])
    return bool(end and (as_of - end).days > cutoff_days)


def normalise_demo(rec: dict, as_of: str, path: str) -> dict:
    oid = rec.get("id")
    if not isinstance(oid, str) or not oid.startswith("demo-astana-"):
        raise IntakeError(f"{path}: demo ids must start with 'demo-astana-'")
    obj = _empty_object(oid)
    obj["evidence_type"] = "synthetic"
    obj["publication"] = rec.get("publication", "published")
    obj["updated_at"] = f"{as_of}T00:00:00Z"
    for key in ("kind", "title", "description", "status", "geometry", "geometry_precision", "evidence_notes"):
        if key in rec:
            obj[key] = rec[key]
    for key in ("schedule",):
        if key in rec:
            obj[key].update(rec[key])
    obj["revision"] = rec.get("revision", 1)
    unknown = set(rec) - {"id", "kind", "title", "description", "status", "geometry", "geometry_precision",
                          "evidence_notes", "schedule", "publication", "revision", "_case"}
    if unknown:
        raise IntakeError(f"{path}: {oid}: demo records may not set {sorted(unknown)}")
    return obj


# ---------------------------------------------------------------- QA

def qa_summary(items: list[dict]) -> dict:
    def count(key):
        out: dict[str, int] = {}
        for o in items:
            out[str(o.get(key))] = out.get(str(o.get(key)), 0) + 1
        return dict(sorted(out.items()))
    unknown = {
        "status_unknown": sum(o["status"] == "unknown" for o in items),
        "geometry_null": sum(o["geometry"] is None for o in items),
        "budget_amount_null": sum(o["budget"]["amount_kzt"] is None for o in items),
        "organization_null": sum(o["responsible"]["organization"] is None for o in items),
    }
    for k in cv.SCHEDULE_KEYS:
        unknown[f"schedule_{k}_null"] = sum(o["schedule"][k] is None for o in items)
    return {
        "count": len(items),
        "by_kind": count("kind"),
        "by_status": count("status"),
        "by_evidence_type": count("evidence_type"),
        "by_geometry_precision": count("geometry_precision"),
        "by_publication": count("publication"),
        "unknown_fields": unknown,
        "geometry_types": dict(sorted(
            {t: sum(1 for o in items if (o["geometry"] or {}).get("type") == t)
             for t in ("Point", "LineString", "Polygon")}.items())),
    }


def public_readiness(obj: dict, registry: dict, as_of: dt.date, max_age: int = cv.STATUS_MAX_AGE_DAYS) -> dict:
    """Advisory: can the record be shown publicly once an editor publishes it?"""
    reasons = []
    if obj["evidence_type"] == "synthetic":
        reasons.append("synthetic: show only with a visible DEMO label")
    if obj["evidence_type"] == "hypothesis":
        reasons.append("hypothesis: not for public display")
    for ref in obj["source_refs"]:
        src = registry.get(ref["id"], {})
        if ref["fields"] and src.get("license_status") in (None, "unknown"):
            reasons.append(f"{ref['id']}: reuse terms of the source are unknown; cite facts with a link, do not copy text/images")
        pub = cv.parse_date(ref.get("published_on"))
        if ref["fields"] and pub and (as_of - pub).days > max_age:
            reasons.append(f"{ref['id']}: source older than {max_age} days; re-check before showing as current")
        if ref["fields"] and pub is None:
            reasons.append(f"{ref['id']}: source has no publication date; re-check before showing as current")
    if obj["status"] == "unknown":
        reasons.append("current state unknown: card must say 'статус не подтверждён'")
    blocking = any(r.startswith(("hypothesis", "synthetic")) for r in reasons)
    return {"object_id": obj["id"], "public_ok_after_editor_review": not blocking, "notes": reasons}


def registry_checks(reg: dict) -> list[dict]:
    issues = []
    ids = set()
    for s in reg["sources"]:
        sid = s.get("id")
        if sid in ids:
            issues.append({"code": "duplicate_source_id", "severity": "error", "path": sid, "message": "duplicate id"})
        ids.add(sid)
        if not (isinstance(sid, str) and cv.R02_REF_ID_RE.match(sid)):
            issues.append({"code": "source_id_format", "severity": "error", "path": str(sid),
                           "message": "source id: Latin letters/digits/._- up to 64 chars (R02 format)"})
        if s.get("access_status") not in cv.ACCESS_STATUSES:
            issues.append({"code": "source_access_status", "severity": "error", "path": sid, "message": "bad access_status"})
        if s.get("access_status") == "fetched" and not (
                cv.parse_ts(s.get("retrieved_at")) and re.fullmatch(r"[0-9a-f]{64}", str(s.get("sha256")))
                and any(isinstance(a, dict) and a.get("outcome") == "fetched" for a in s.get("access_attempts") or [])):
            issues.append({"code": "fetched_without_proof", "severity": "error", "path": sid,
                           "message": "fetched source needs retrieved_at, a sha256 and a successful attempt"})
        if s.get("access_status") != "fetched" and s.get("supports"):
            issues.append({"code": "unfetched_supports", "severity": "error", "path": sid,
                           "message": "a source that was not fetched cannot support anything"})
        if not s.get("access_attempts") and not s.get("local_copy"):
            issues.append({"code": "no_access_record", "severity": "warning", "path": sid,
                           "message": "no recorded access attempt or local copy"})
    return issues


# ---------------------------------------------------------------- build

def build(pkg: str = PKG) -> dict:
    """Return {filename: data} for all outputs (nothing is written)."""
    config = load_json(os.path.join(pkg, "slice_config.json"))
    as_of = config["as_of"]
    as_of_d = cv.parse_date(as_of)
    if as_of_d is None:
        raise IntakeError("slice_config.as_of must be YYYY-MM-DD")
    cutoff = int(config.get("historical_cutoff_days", 365))
    max_age = int(config.get("status_max_age_days", cv.STATUS_MAX_AGE_DAYS))
    sources_path = os.path.join(pkg, "sources.json")
    reg = load_json(sources_path)
    registry = {s["id"]: s for s in reg["sources"]}
    try:
        fence = cv.load_geofence(os.path.join(pkg, "geofence.json"))
    except (OSError, ValueError) as exc:
        raise IntakeError(f"geofence.json: {exc}") from None

    inputs = [{"path": rel(sources_path), "sha256": sha256_file(sources_path)},
                {"path": rel(os.path.join(pkg, "slice_config.json")),
               "sha256": sha256_file(os.path.join(pkg, "slice_config.json"))}]
    current, historical, evidence, demo = [], [], [], []
    for path in sorted(glob.glob(os.path.join(pkg, "intake", "real", "*.json"))):
        rec = load_json(path)
        inputs.append({"path": rel(path), "sha256": sha256_file(path)})
        obj, ev = normalise_intake(rec, registry, rel(path))
        (historical if is_historical(obj, rec, as_of_d, cutoff) else current).append(obj)
        evidence.extend(ev)
    demo_inputs = []
    for path in sorted(glob.glob(os.path.join(pkg, "intake", "demo", "*.json"))):
        data = load_json(path)
        demo_inputs.append({"path": rel(path), "sha256": sha256_file(path)})
        for rec in data.get("records", []):
            demo.append(normalise_demo(rec, as_of, rel(path)))

    for lst in (current, historical, demo):
        lst.sort(key=lambda o: o["id"])
    evidence.sort(key=lambda e: (e["object_id"], e["field"], e["source_id"]))

    def envelope(items, name, is_demo, ins):
        digest = slice_digest(items, ins, name, as_of, is_demo, max_age)
        return {
            "schema_version": cv.SCHEMA_VERSION,
            "city": cv.CITY,
            "slice": {
                "name": name,
                "version": f"r05-astana-{name}-{as_of}-{digest[:12]}",
                "as_of": as_of,
                "demo": is_demo,
                "count": len(items),
                "status_max_age_days": max_age,
                "builder": BUILDER,
                "inputs": ins,
                "content_sha256": digest,
                "notice": (
                    "СИНТЕТИЧЕСКИЕ ДАННЫЕ ДЛЯ ДЕМОНСТРАЦИИ. Не сведения о реальных работах в Астане."
                    if is_demo else
                    "Реальные записи только с подтверждением полученным источником; publication=draft до проверки редактором."
                ),
            },
            "items": items,
        }

    out = {
        "objects.json": envelope(current, "current", False, inputs),
        "historical.json": envelope(historical, "historical", False, inputs),
        "demo_synthetic.json": envelope(demo, "demo", True, demo_inputs),
        "evidence_index.json": {
            "schema": "r05-evidence-index-v1", "city": cv.CITY, "as_of": as_of,
            "notice": "Для редактора: связь значения поля с источником и короткая выдержка. Не входит в публичный DTO.",
            "rows": evidence,
        },
    }
    kw = {"as_of": as_of, "fence": fence, "max_status_age_days": max_age}
    reports = {
        "objects.json": cv.validate_collection(current, profile="real", **kw),
        "historical.json": cv.validate_collection(historical, profile="real", **kw),
        "demo_synthetic.json": cv.validate_collection(demo, profile="demo", **kw),
    }
    contract_reports = {name: cv.validate_collection(out[name]["items"], profile="contract", **kw)
                        for name in reports}
    cross_ids = sorted({o["id"] for o in current + historical} & {o["id"] for o in demo})
    reg_issues = registry_checks(reg)
    valid = (all(r["valid"] for r in reports.values()) and all(r["valid"] for r in contract_reports.values())
             and not cross_ids and not any(i["severity"] == "error" for i in reg_issues))
    out["validation.json"] = {
        "schema": "r05-validation-v1",
        "city": cv.CITY,
        "as_of": as_of,
        "valid": valid,
        "validator": "data/civic/astana/tools/civic_v1.py",
        "slices": {
            name: {
                "version": out[name]["slice"]["version"],
                "profile": reports[name]["profile"],
                "valid": reports[name]["valid"] and contract_reports[name]["valid"],
                "errors": reports[name]["errors"],
                "warnings": reports[name]["warnings"],
                "contract_profile_errors": contract_reports[name]["errors"],
                "issues": {k: v for k, v in reports[name]["by_object"].items() if v},
                "collection_issues": reports[name]["collection_issues"],
                "qa": qa_summary(out[name]["items"]),
            } for name in reports
        },
        "ids_shared_between_real_and_demo": cross_ids,
        "sources": {
            "total": len(reg["sources"]),
            "fetched": sum(s.get("access_status") == "fetched" for s in reg["sources"]),
            "not_fetched": sum(s.get("access_status") == "not_fetched" for s in reg["sources"]),
            "unavailable": sum(s.get("access_status") == "unavailable" for s in reg["sources"]),
            "used_by_objects": sorted({r["id"] for o in current + historical for r in o["source_refs"]}),
            "registry_issues": reg_issues,
        },
        "public_readiness": [public_readiness(o, registry, as_of_d, max_age) for o in current + historical],
        "evidence_rows": len(evidence),
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build R05 Astana civic-v1 slices")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if outputs on disk differ")
    args = ap.parse_args(argv)
    try:
        out = build()
    except IntakeError as exc:
        print(f"intake error: {exc}", file=sys.stderr)
        return 2
    changed = []
    for name, data in sorted(out.items()):
        path = os.path.join(PKG, name)
        new = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        try:
            same = load_json(path) == data  # compare content, not bytes (CRLF checkouts)
        except (OSError, ValueError):
            same = False
        if not same:
            changed.append(name)
            if not args.check:
                with open(path, "wb") as fh:
                    fh.write(new)
    v = out["validation.json"]
    print(json.dumps({"valid": v["valid"], "changed": changed,
                      "versions": {k: s["version"] for k, s in v["slices"].items()},
                      "counts": {k: s["qa"]["count"] for k, s in v["slices"].items()}}, ensure_ascii=False))
    if args.check and changed:
        return 1
    return 0 if v["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
