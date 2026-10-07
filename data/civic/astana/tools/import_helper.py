"""Import helper for R02: turns the R05 package into a checked, idempotent import plan.

Pure functions, stdlib only, never touches a database and never publishes.
R02's importer (ui/civic_store) owns the transaction; this module tells it *what*
to import and *why not* for everything it refuses.

Package contract (data/civic/astana/):
  objects.json          real current slice   -> source "r05-astana-real"
  historical.json       real historical      -> source "r05-astana-real" (opt-in)
  demo_synthetic.json   synthetic demo slice -> source "r05-astana-demo" (opt-in, flag)

Each import item: {source, external_id, digest, slice_version, demo, historical,
create_body, suggested_publication, schedule}. ``digest`` covers the civic content
without server-owned fields (revision, updated_at, publication), so re-importing an
unchanged package yields ``skip_unchanged``.

CLI (dry run only):
  python3 -I data/civic/astana/tools/import_helper.py [--include-demo] [--include-historical]
         [--existing existing.json]
where existing.json maps external_id -> {"digest", "publication", "edited_after_import": bool}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import civic_v1 as cv  # noqa: E402

SOURCE_REAL = "r05-astana-real"
SOURCE_DEMO = "r05-astana-demo"
SERVER_OWNED = ("revision", "updated_at", "publication")


class PackageError(ValueError):
    pass


def _canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_digest(obj: dict) -> str:
    return hashlib.sha256(_canonical({k: v for k, v in obj.items() if k not in SERVER_OWNED})).hexdigest()


def create_body(obj: dict) -> dict:
    """Body for POST /staff/objects: civic fields without id and server-owned fields."""
    return {k: v for k, v in obj.items() if k not in SERVER_OWNED and k != "id"}


PKG_PREFIX = "data/civic/astana/"


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise PackageError(f"{os.path.basename(path)}: cannot read JSON: {exc}") from None


def _load_slice(path: str, expect_demo: bool) -> dict:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise PackageError(f"{os.path.basename(path)}: not a slice envelope")
    sl = data.get("slice") if isinstance(data.get("slice"), dict) else {}
    if data.get("schema_version") != cv.SCHEMA_VERSION or data.get("city") != cv.CITY:
        raise PackageError(f"{os.path.basename(path)}: not a civic-v1 Astana slice")
    if sl.get("demo") is not expect_demo:
        raise PackageError(f"{os.path.basename(path)}: slice.demo must be {expect_demo}")
    items = data.get("items")
    if not isinstance(items, list) or sl.get("count") != len(items):
        raise PackageError(f"{os.path.basename(path)}: item count does not match slice.count")
    digest = hashlib.sha256(_canonical({"items": items, "inputs": sl.get("inputs")})).hexdigest()
    expected_version = f"r05-astana-{sl.get('name')}-{sl.get('as_of')}-{digest[:12]}"
    if (digest != sl.get("content_sha256") or sl.get("version") != expected_version
            or cv.parse_date(sl.get("as_of")) is None):
        raise PackageError(f"{os.path.basename(path)}: content does not match its slice version (edited by hand?)")
    return data


def _check_inputs(pkg_dir: str, sl: dict, name: str, warnings: list) -> None:
    """Recorded builder inputs must match the files next to the slice, when those files are present."""
    import build_slice as bs  # local import: only needed when sources/intake travel with the package
    recorded = {}
    for inp in sl.get("inputs") or []:
        path = inp.get("path", "") if isinstance(inp, dict) else ""
        local = path[len(PKG_PREFIX):] if path.startswith(PKG_PREFIX) else None
        if local is None:
            raise PackageError(f"{name}: unexpected input path {path!r}")
        recorded[local] = inp.get("sha256")
    for local, sha in sorted(recorded.items()):
        full = os.path.join(pkg_dir, local)
        if not os.path.exists(full):
            warnings.append(f"{name}: input {local} not present; integrity checked by content hash only")
            continue
        try:
            actual = bs.sha256_file(full)
        except bs.IntakeError as exc:
            raise PackageError(f"{name}: {exc}") from None
        if actual != sha:
            raise PackageError(f"{name}: input {local} changed since the slice was built; run build_slice.py")
    if not sl.get("demo") and os.path.isdir(os.path.join(pkg_dir, "intake", "real")):
        on_disk = {f"intake/real/{f}" for f in os.listdir(os.path.join(pkg_dir, "intake", "real")) if f.endswith(".json")}
        listed = {k for k in recorded if k.startswith("intake/real/")}
        if on_disk != listed:
            raise PackageError(f"{name}: intake/real files differ from the slice inputs; run build_slice.py")


def load_package(pkg_dir: str = PKG, *, include_demo: bool = False, include_historical: bool = False) -> dict:
    """Validate the package and return {package, items, rejected}. Raises PackageError on tampering."""
    fence = cv.load_geofence(os.path.join(pkg_dir, "geofence.json"))
    plan_items, rejected, slices, warnings = [], [], {}, []
    wanted = [("objects.json", False, False)]
    if include_historical:
        wanted.append(("historical.json", False, True))
    if include_demo:
        wanted.append(("demo_synthetic.json", True, False))
    seen = {}
    for name, is_demo, is_hist in wanted:
        data = _load_slice(os.path.join(pkg_dir, name), is_demo)
        sl = data["slice"]
        _check_inputs(pkg_dir, sl, name, warnings)
        slices[name] = {"version": sl["version"], "count": sl["count"], "demo": sl["demo"], "as_of": sl["as_of"]}
        profile = "demo" if is_demo else "real"
        max_age = sl.get("status_max_age_days", cv.STATUS_MAX_AGE_DAYS)
        for obj in data["items"]:
            issues = cv.validate_object(obj, profile=profile, as_of=sl["as_of"], fence=fence,
                                        max_status_age_days=max_age)
            errors = [i for i in issues if i["severity"] == "error"]
            oid = obj.get("id") if isinstance(obj, dict) else None
            if errors:
                rejected.append({"file": name, "external_id": oid, "errors": errors})
                continue
            if oid in seen:
                rejected.append({"file": name, "external_id": oid,
                                 "errors": [{"code": "duplicate_id", "message": f"also in {seen[oid]}"}]})
                continue
            seen[oid] = name
            plan_items.append({
                "source": SOURCE_DEMO if is_demo else SOURCE_REAL,
                "external_id": oid,
                "digest": content_digest(obj),
                "slice_version": sl["version"],
                "demo": is_demo,
                "historical": is_hist,
                # Real records always arrive as drafts. A demo record may suggest its designed
                # state so the demo can exercise draft/archived handling; the server decides.
                "suggested_publication": obj["publication"] if is_demo else "draft",
                "schedule": obj["schedule"],
                "create_body": create_body(obj),
            })
    plan_items.sort(key=lambda i: (i["source"], i["external_id"]))
    sources = sorted({SOURCE_DEMO if d else SOURCE_REAL for _, d, _ in wanted})
    # Every real id in the package (current + historical): a record that moved to historical.json
    # is not "missing" just because only objects.json was imported.
    package_ids = set()
    for name in ("objects.json", "historical.json"):
        path = os.path.join(pkg_dir, name)
        if os.path.exists(path):
            items = _read_json(path).get("items") or []
            package_ids |= {(SOURCE_REAL, o.get("id")) for o in items if isinstance(o, dict)}
    package_ids |= {(i["source"], i["external_id"]) for i in plan_items}
    return {"package": {"dir": os.path.abspath(pkg_dir), "slices": slices, "sources": sources,
                        "warnings": warnings, "ids": sorted(package_ids, key=str)},
            "items": plan_items, "rejected": rejected}


SCHEDULE_PUBLIC_FIELDS = ("planned_start", "original_planned_end", "current_planned_end", "actual_end")


def schedule_changes(old: dict | None, new: dict) -> list[dict]:
    old = old or {}
    return [{"field": f"schedule.{k}", "old": old.get(k), "new": new.get(k)}
            for k in SCHEDULE_PUBLIC_FIELDS if old.get(k) != new.get(k)]


def plan(items: list[dict], existing: dict | None = None, sources: list[str] | None = None,
         package_ids: list | None = None) -> list[dict]:
    """Decide per item without side effects. ``existing`` maps external_id -> state in the store.

    Actions: create | skip_unchanged | update_import_draft | editor_review | report_missing.
    Never publish, never archive, never overwrite a published or hand-edited record.
    """
    existing = existing or {}
    actions = []
    for it in items:
        cur = existing.get(it["external_id"])
        if cur is None:
            actions.append({"action": "create", "external_id": it["external_id"], "source": it["source"],
                            "publication_after": "draft", "reason": "new in package"})
        elif cur.get("digest") == it["digest"]:
            actions.append({"action": "skip_unchanged", "external_id": it["external_id"], "source": it["source"]})
        elif cur.get("publication") != "draft" or cur.get("edited_after_import") is not False:
            # Fail closed: unless the store says explicitly "untouched draft", an editor decides.
            actions.append({"action": "editor_review", "external_id": it["external_id"], "source": it["source"],
                            "reason": "package changed but the stored record is published or edited by hand",
                            "schedule_changes": schedule_changes(cur.get("schedule"), it["schedule"]),
                            "note": "original_planned_end of a published record is never replaced by import"})
        else:
            actions.append({"action": "update_import_draft", "external_id": it["external_id"], "source": it["source"],
                            "reason": "untouched import draft; replace with newer package content",
                            "schedule_changes": schedule_changes(cur.get("schedule"), it["schedule"])})
    in_pkg = {(i["source"], i["external_id"]) for i in items} | {tuple(x) for x in (package_ids or [])}
    sources = set(sources) if sources is not None else ({i["source"] for i in items} | {SOURCE_REAL})
    for ext_id, cur in sorted(existing.items()):
        if cur.get("source", SOURCE_REAL) in sources and (cur.get("source", SOURCE_REAL), ext_id) not in in_pkg:
            actions.append({"action": "report_missing", "external_id": ext_id, "source": cur.get("source", SOURCE_REAL),
                            "reason": "absent from this package; do not archive automatically, editor decides"})
    return actions


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="R05 -> R02 import plan (dry run, no database access)")
    ap.add_argument("--package", default=PKG)
    ap.add_argument("--include-demo", action="store_true", help="also import the SYNTHETIC demo slice")
    ap.add_argument("--include-historical", action="store_true")
    ap.add_argument("--existing", help="JSON: external_id -> {digest, publication, edited_after_import, schedule}")
    args = ap.parse_args(argv)
    try:
        pkg = load_package(args.package, include_demo=args.include_demo, include_historical=args.include_historical)
    except PackageError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    existing = None
    if args.existing:
        try:
            existing = _read_json(args.existing)
        except PackageError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 2
    out = {"ok": not pkg["rejected"], "package": pkg["package"], "rejected": pkg["rejected"],
           "actions": plan(pkg["items"], existing, pkg["package"]["sources"], pkg["package"]["ids"]),
           "counts": {"items": len(pkg["items"]), "rejected": len(pkg["rejected"])}}
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
