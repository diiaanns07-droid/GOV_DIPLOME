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


def _load_slice(path: str, expect_demo: bool) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    sl = data.get("slice") or {}
    if data.get("schema_version") != cv.SCHEMA_VERSION or data.get("city") != cv.CITY:
        raise PackageError(f"{os.path.basename(path)}: not a civic-v1 Astana slice")
    if sl.get("demo") is not expect_demo:
        raise PackageError(f"{os.path.basename(path)}: slice.demo must be {expect_demo}")
    items = data.get("items")
    if not isinstance(items, list) or sl.get("count") != len(items):
        raise PackageError(f"{os.path.basename(path)}: item count does not match slice.count")
    digest = hashlib.sha256(_canonical({"items": items, "inputs": sl.get("inputs")})).hexdigest()
    if digest != sl.get("content_sha256") or not str(sl.get("version", "")).endswith(digest[:12]):
        raise PackageError(f"{os.path.basename(path)}: content does not match its slice version (edited by hand?)")
    return data


def load_package(pkg_dir: str = PKG, *, include_demo: bool = False, include_historical: bool = False) -> dict:
    """Validate the package and return {package, items, rejected}. Raises PackageError on tampering."""
    fence = cv.load_geofence(os.path.join(pkg_dir, "geofence.json"))
    plan_items, rejected, slices = [], [], {}
    wanted = [("objects.json", False, False)]
    if include_historical:
        wanted.append(("historical.json", False, True))
    if include_demo:
        wanted.append(("demo_synthetic.json", True, False))
    seen = {}
    for name, is_demo, is_hist in wanted:
        data = _load_slice(os.path.join(pkg_dir, name), is_demo)
        sl = data["slice"]
        slices[name] = {"version": sl["version"], "count": sl["count"], "demo": sl["demo"], "as_of": sl["as_of"]}
        profile = "demo" if is_demo else "real"
        for obj in data["items"]:
            issues = cv.validate_object(obj, profile=profile, as_of=sl["as_of"], fence=fence)
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
    return {"package": {"dir": os.path.abspath(pkg_dir), "slices": slices, "sources": sources},
            "items": plan_items, "rejected": rejected}


SCHEDULE_PUBLIC_FIELDS = ("planned_start", "original_planned_end", "current_planned_end", "actual_end")


def schedule_changes(old: dict | None, new: dict) -> list[dict]:
    old = old or {}
    return [{"field": f"schedule.{k}", "old": old.get(k), "new": new.get(k)}
            for k in SCHEDULE_PUBLIC_FIELDS if old.get(k) != new.get(k)]


def plan(items: list[dict], existing: dict | None = None, sources: list[str] | None = None) -> list[dict]:
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
        elif cur.get("publication") in ("published", "archived") or cur.get("edited_after_import"):
            actions.append({"action": "editor_review", "external_id": it["external_id"], "source": it["source"],
                            "reason": "package changed but the stored record is published or edited by hand",
                            "schedule_changes": schedule_changes(cur.get("schedule"), it["schedule"]),
                            "note": "original_planned_end of a published record is never replaced by import"})
        else:
            actions.append({"action": "update_import_draft", "external_id": it["external_id"], "source": it["source"],
                            "reason": "untouched import draft; replace with newer package content",
                            "schedule_changes": schedule_changes(cur.get("schedule"), it["schedule"])})
    in_pkg = {(i["source"], i["external_id"]) for i in items}
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
        with open(args.existing, encoding="utf-8") as fh:
            existing = json.load(fh)
    out = {"ok": not pkg["rejected"], "package": pkg["package"], "rejected": pkg["rejected"],
           "actions": plan(pkg["items"], existing, pkg["package"]["sources"]),
           "counts": {"items": len(pkg["items"]), "rejected": len(pkg["rejected"])}}
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
