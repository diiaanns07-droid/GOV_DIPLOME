"""K11 round 3: conflict audit of the fixed research snapshots (read-only).

Reads research/round-3/snapshots.json from the coordinator branch, diffs every snapshot SHA
against the base, and reports path overlaps, folder intrusions, product-file changes and a
structural comparison of the two K03 territory registries. Uses only git plumbing reads;
never checks out, merges or executes files from other branches.
Writes only research/round-3-results/K11/CONFLICTS.json.

Usage:  git fetch origin codex/research-import-2026-10-05 <assigned branches...>
        python3 research/round-3-results/K11/k11_conflicts.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "CONFLICTS.json"
COORD_REF = "origin/codex/research-import-2026-10-05"
SNAPSHOTS = "research/round-3/snapshots.json"
# K03 is now owned by epic-curie; clever-mccarthy works on K02 only (coordinator, round 3)
OWNER_OVERRIDE = {"K03": "claude/epic-curie-iitc43", "K02": "claude/clever-mccarthy-pywscu"}
COORDINATOR_PATHS = ("research/coordination/", "research/round-3/", "research/README.md", "CLAUDE.md",
                     "research/govtech-results/", "research/astana-results/", "research/govtech-14/",
                     "research/astana-14/")
REGISTRY = "research/next-round/K03/territory_registry"


def git(*args, binary=False):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
    return out if binary else out.decode("utf-8")


def git_ok(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def owner_of(path, slot_branch):
    """Slot that owns a path in the next round, from the folder convention."""
    parts = path.split("/")
    for i, p in enumerate(parts):
        if p in slot_branch and i > 0 and parts[i - 1] in ("next-round", "shared", "round-3-results"):
            return p, OWNER_OVERRIDE.get(p, slot_branch[p])
    return None, None


def registry_versions(shas):
    """Columns, row counts and field agreement of the K03 registry CSVs (no content chosen)."""
    rows = {}
    for slot, sha in shas.items():
        text = git("show", f"{sha}:{REGISTRY}.csv", binary=True).decode("utf-8-sig")
        rows[slot] = list(csv.DictReader(io.StringIO(text)))
    a, b = rows["K02"], rows["K03"]
    id_a = {r["stable_id_proposed"] for r in a if r["stable_id_proposed"]}
    id_b = {r["territory_id"] for r in b if r["territory_id"]}
    by_rel_a = {r["osm_relation"].split("/")[-1]: r for r in a if r["osm_relation"].strip()}
    by_rel_b = {r["osm_relation_id"].split("/")[-1].lstrip("r"): r for r in b if r["osm_relation_id"].strip()}
    pairs = [("stable_id_proposed", "territory_id"), ("legacy_id", "legacy_id"), ("name_ru", "name_ru"),
             ("admin_level", "osm_admin_level"), ("kato", "kato_code"), ("wikidata", "wikidata"),
             ("city", "city"), ("area_km2_geodesic", "area_km2_geodesic")]
    field_diffs = []
    for rel in sorted(set(by_rel_a) & set(by_rel_b)):
        ra, rb = by_rel_a[rel], by_rel_b[rel]
        diffs = {}
        for x, y in pairs:
            va, vb = ra[x].strip(), rb[y].strip()
            if x == "area_km2_geodesic":
                try:
                    if abs(float(va) - float(vb)) < 0.05:
                        continue
                except ValueError:
                    pass
            if va != vb:
                diffs[f"{x}|{y}"] = [va, vb]
        if diffs:
            field_diffs.append({"osm_relation": rel, "name_ru": ra["name_ru"] or rb["name_ru"], "differences": diffs})
    no_rel = {
        "K02": [{k: r[k] for k in ("city", "stable_id_proposed", "unit_type", "name_ru", "kpssu_code")}
                for r in a if not r["osm_relation"].strip()],
        "K03": [{k: r[k] for k in ("city", "territory_id", "id_status", "level", "name_ru")}
                for r in b if not r["osm_relation_id"].strip()],
    }
    return {
        "columns": {s: list(r[0].keys()) for s, r in rows.items()},
        "row_count": {s: len(r) for s, r in rows.items()},
        "rows_by_city": {s: dict(Counter(x["city"] for x in r)) for s, r in rows.items()},
        "assigned_ids": {"K02_only": sorted(id_a - id_b), "K03_only": sorted(id_b - id_a),
                         "common": sorted(id_a & id_b)},
        "osm_relations": {"K02": len(by_rel_a), "K03": len(by_rel_b), "common": len(set(by_rel_a) & set(by_rel_b))},
        "osm_rows_with_field_differences": field_diffs,
        "rows_without_osm_relation": no_rel,
        "note": "Field comparison covers rows matched by OSM relation; area tolerance 0.05 km2. "
                "Rows without OSM relation (Shymkent districts) are listed, not matched: no code-name link exists in either file.",
    }


def main():
    coord_sha = git("rev-parse", COORD_REF).strip()
    snap = json.loads(git("show", f"{coord_sha}:{SNAPSHOTS}"))
    base = snap["base"]
    slot_branch = {a["slot"]: a["branch"] for a in snap["assignments"]}
    branches, by_path = [], defaultdict(list)
    for a in snap["assignments"]:
        sha = a["sha"]
        tip = git("rev-parse", f"origin/{a['branch']}").strip() if git_ok("rev-parse", f"origin/{a['branch']}") else None
        lines = [l.split("\t", 1) for l in git("diff", "--name-status", "--no-renames", base, sha).splitlines()]
        for st, path in lines:
            blob = git("rev-parse", f"{sha}:{path}").strip() if st != "D" else None
            size = int(git("cat-file", "-s", blob)) if blob else None
            by_path[path].append({"slot": a["slot"], "branch": a["branch"], "sha": sha, "status": st,
                                  "blob": blob, "bytes": size})
        branches.append({
            "slot": a["slot"], "branch": a["branch"], "snapshot_sha": sha, "tip_at_check": tip,
            "tip_moved_after_snapshot": bool(tip and tip != sha),
            "base_is_ancestor": git_ok("merge-base", "--is-ancestor", base, sha),
            "changed_files": len(lines), "status_counts": dict(Counter(st for st, _ in lines)),
            "top_dirs": dict(Counter("/".join(p.split("/")[:3]) for _, p in lines)),
            "product_files_changed": sorted(p for _, p in lines if not p.startswith("research/")),
            "coordinator_files_changed": sorted(p for _, p in lines if p.startswith(COORDINATOR_PATHS)),
            "foreign_folders": sorted({"/".join(p.split("/")[:3]) for _, p in lines
                                       if owner_of(p, slot_branch)[0] not in (None, a["slot"])}),
        })
    conflicts = []
    for path, versions in sorted(by_path.items()):
        if len(versions) < 2:
            continue
        slot, owner = owner_of(path, slot_branch)
        conflicts.append({"path": path, "versions": versions,
                          "bytes_identical": len({v["blob"] for v in versions}) == 1,
                          "owner_next_round": {"slot": slot, "branch": owner},
                          "decision": "none: not chosen automatically, no merge performed"})
    intrusions = []
    for path, versions in sorted(by_path.items()):
        slot, owner = owner_of(path, slot_branch)
        for v in versions:
            if slot and v["slot"] != slot:
                intrusions.append({"path": path, "folder_slot": slot, "written_by_slot": v["slot"],
                                   "branch": v["branch"], "sha": v["sha"], "blob": v["blob"], "bytes": v["bytes"],
                                   "also_written_by_owner": any(x["slot"] == slot for x in versions),
                                   "owner_next_round": owner})
    result = {
        "generated_by": "research/round-3-results/K11/k11_conflicts.py",
        "base": base,
        "snapshots_source": f"{COORD_REF}@{coord_sha}:{SNAPSHOTS}",
        "method": "git diff --name-status --no-renames <base> <snapshot sha>; byte identity by git blob id",
        "product_definition": "any path outside research/",
        "branches": branches,
        "path_conflicts": conflicts,
        "folder_intrusions": intrusions,
        "k03_registry_comparison": registry_versions(
            {a["slot"]: a["sha"] for a in snap["assignments"] if a["slot"] in ("K02", "K03")}),
        "summary": {
            "branches_checked": len(branches),
            "path_conflicts": len(conflicts),
            "folder_intrusions": len(intrusions),
            "branches_with_product_changes": [b["slot"] for b in branches if b["product_files_changed"]],
            "branches_with_coordinator_file_changes": [b["slot"] for b in branches if b["coordinator_files_changed"]],
            "non_add_changes": {b["slot"]: b["status_counts"] for b in branches if set(b["status_counts"]) - {"A"}},
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
