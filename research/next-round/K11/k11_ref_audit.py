"""K11: read-only audit of report/evidence completeness and local file references.

Reads only git-tracked files plus research/coordination/INVENTORY.json.
Never executes imported code; writes only research/next-round/K11/k11_ref_audit.json.
Usage (from any directory):  python3 research/next-round/K11/k11_ref_audit.py

Reference extraction is heuristic (regex over text, JSON string values and script literals).
Every `not_found` reference was reviewed by hand at the audited commit; the rule tables below
encode that review so the classification can be re-run and challenged.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CITIES = {"govtech-results": "shymkent", "astana-results": "astana"}
EXPECTED_ROLES = [
    "01_digitalization", "02_utilities", "03_logistics", "04_infrastructure", "05_education",
    "06_transport", "07_tourism", "08_ecology", "09_energy", "10_safety", "11_land",
    "12_data_gis", "13_architecture_ai_thesis", "14_synthesis_product_audit",
]
TEXT_EXT = {".md", ".txt", ".json", ".jsonl", ".py", ".sql"}
REF_EXT = ("json|jsonl|geojson|csv|tsv|py|md|rst|txt|zip|xml|sql|png|jpe?g|svg|pdf|xlsx?|ipynb|html?"
           "|parquet|gpkg|shp|pbf|tiff?|ya?ml|cff|toml|ini|sh|bat|log|db")
# path-like token ending in a known extension; optional leading "/" (absolute sandbox paths);
# allows the "name (1).ext" suffix that browsers add to repeated downloads
REF_RE = re.compile(r"(?<![\w.\-/\\])(/?(?:[\w\-.]+/)*[\w\-.]*\w(?: \(\d+\))?\.(?:%s))(?![\w\-])" % REF_EXT, re.I)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
URL_RE = re.compile(r"(?:[a-z][a-z0-9+.\-]*://|www\.)[^\s)\]>\"'`]+", re.I)

# ---- rule tables from the manual review of not_found references -----------------------------
MISSING_DELIVERABLE = {
    # file the report lists among its own delivered files ("Файлы:"), absent from every branch
    ("research/astana-results/10_safety/AST_A10_report.md", "AST_A10_evidence.json"),
}
CHECKSUM_LISTS = {
    # shipped checksum list whose entries are absent; report L150 says the files were saved
    "research/astana-results/13_architecture_ai_thesis/extracted_files__34_/SHA256SUMS.txt",
}
PARSE_ARTIFACT_RE = re.compile(r"^(?:(?:np|math)\.log|area(?:\.[a-z])?|[\d.,]+)$")
PLACEHOLDER = {"card.json", "h.txt"}  # CLI argument placeholder / curl temp header file
PROPOSED = {
    # files proposed in design sections, explicitly not implemented
    "config/astana.json", "config/shymkent.json", "astana.json", "shymkent.json",
    "land_registry_astana.json", "land_registry_shymkent.json", "data/land_registry.json",
    "registry/sources.jsonl", "registry/observations.csv", "stops.csv", "routes.csv",
    "route_stops.csv", "service.csv", "segment_speed.csv", "facilities.geojson",
    "access_grid.geojson", "change.json", "evidence.json",
    # AST_A12_manifest.json planned_not_executed osmium pipeline
    "astana_union.geojson", "astana.osm.pbf", "astana_roads.osm.pbf",
}
# generic name that matched an unrelated file by basename: docstring example "--out results.json"
FALSE_NAME_MATCH = {"results.json": ("A02_priority_experiment.py",)}
# created by the script itself (netgenerate/netconvert) or shipped with the SUMO install
GENERATED_OR_TOOL = {"grid.net.xml", "river.net.xml", "randomTrips.py"}
CATEGORY_OF_STATUS = {
    "ok_path": "ok", "ok_same_dir": "ok", "ok_combined": "ok",
    "repo_outside_research": "app_repo_file",
    "wrong_path_same_role": "wrong_local_path", "other_dir_same_role": "wrong_local_path",
    "other_city_only": "cross_city_or_role", "other_role_same_city": "cross_city_or_role",
    "local_zip_only": "zip_not_in_git_unpacked",
}


def git_files():
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [p for p in out.decode("utf-8").split("\0") if p]


def git_head():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def role_of(rel):
    parts = PurePosixPath(rel).parts
    if len(parts) >= 3 and parts[0] == "research" and parts[1] in CITIES and re.match(r"\d{2}_", parts[2]):
        return CITIES[parts[1]], parts[2], PurePosixPath(*parts[:3])
    return None, None, None


def kind_of(name):
    low = name.lower()
    if re.search(r"_report(?: \(\d+\))?\.md$", low):
        return "report"
    if re.search(r"_evidence(?: \(\d+\))?\.json$", low):
        return "evidence"
    if low.endswith(".py"):
        return "script"
    if low.startswith("readme") or low == "start_here.txt":
        return "readme"
    return "other"


def strings_in_json(obj, path="$"):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from strings_in_json(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from strings_in_json(v, f"{path}[{i}]")


def extract_refs(rel, text):
    """Yield (location, ref, context) for every file-like token."""
    chunks = None
    if rel.lower().endswith(".json"):
        try:
            chunks = list(strings_in_json(json.loads(text)))
        except ValueError:
            pass
    if chunks is None:
        chunks = [(f"L{i}", line) for i, line in enumerate(text.splitlines(), 1)]
    for loc, chunk in chunks:
        targets = [m.group(1) for m in MD_LINK_RE.finditer(chunk) if not URL_RE.match(m.group(1))]
        cleaned = URL_RE.sub(" ", chunk)
        targets += [m.group(1) for m in REF_RE.finditer(cleaned)]
        seen = set()
        for t in targets:
            t = t.strip().strip("`'\"").split("#")[0].rstrip(".,;:")
            if not t or "*" in t or "<" in t or t in seen or t.startswith("."):
                continue
            seen.add(t)
            yield loc, t, chunk.strip()[:240]


def declared_deliverable(row):
    """Reference sits in a section where the author lists files of this pass."""
    if row["source_kind"] == "evidence":
        return any(".deliverables" in loc for loc in row["locs"])
    if row["source_kind"] == "report":
        return any(loc.startswith("L") and int(loc[1:]) <= 20 for loc in row["locs"])
    return False


def classify(row):
    st = row["status"]
    if PurePosixPath(row["source"]).name in FALSE_NAME_MATCH.get(row["ref"], ()):
        return "placeholder"
    if st in CATEGORY_OF_STATUS:
        return CATEGORY_OF_STATUS[st]
    name = PurePosixPath(row["ref"]).name
    if (row["source"], row["ref"]) in MISSING_DELIVERABLE:
        return "missing_deliverable"
    if row["source"] in CHECKSUM_LISTS:
        return "missing_listed_in_checksums"
    if PARSE_ARTIFACT_RE.match(row["ref"]):
        return "parse_artifact"
    if name in PLACEHOLDER:
        return "placeholder"
    if name in GENERATED_OR_TOOL:
        return "generated_at_runtime_or_tool"
    if row["ref"] in PROPOSED:
        return "proposed_not_implemented"
    if st == "case_mismatch":
        return "external_third_party_file"  # LICENSE.TXT / manifest.json of other projects
    if row["source_kind"] == "script":
        return "script_input_not_shipped"
    return "external_third_party_file"


def write_lists(result):
    """Two flat CSV lists for reviewers: missing files and local links that do not resolve as written."""
    import csv

    missing = []
    for r in result["roles"]:
        if not r["reports"] or not r["evidence"]:
            what = [k for k in ("reports", "evidence") if not r[k]]
            missing.append({"city": r["city"], "role": r["role"], "missing": "+".join(what),
                            "referenced_by": "coordination/STATUS.txt (expected 14 roles)", "where": "",
                            "category": "role_files_absent", "found_path": ""})
    for r in result["references"]:
        if r["category"] in ("missing_deliverable", "missing_listed_in_checksums", "script_input_not_shipped"):
            missing.append({"city": r["city"], "role": r["role"], "missing": r["ref"],
                            "referenced_by": r["source"], "where": ";".join(r["locs"]),
                            "category": r["category"], "found_path": ""})
    wrong = [{"city": r["city"], "role": r["role"], "referenced_by": r["source"], "where": ";".join(r["locs"]),
              "ref_as_written": r["ref"], "category": r["category"], "actual_path": ";".join(r["found"])}
             for r in result["references"]
             if r["category"] in ("wrong_local_path", "cross_city_or_role", "zip_not_in_git_unpacked")]
    for name, rows in (("K11_missing_files.csv", missing), ("K11_wrong_local_links.csv", wrong)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print("lists:", len(missing), "missing rows,", len(wrong), "link rows")


def main():
    tracked = git_files()
    tracked_set = set(tracked)
    by_name = defaultdict(list)
    by_name_cf = defaultdict(list)
    for p in tracked:
        by_name[PurePosixPath(p).name].append(p)
        by_name_cf[PurePosixPath(p).name.casefold()].append(p)

    inventory = json.loads((ROOT / "research/coordination/INVENTORY.json").read_text(encoding="utf-8"))
    inv_files = {f["path"]: f for a in inventory["agents"] for f in a["files"]}
    local_only = sorted(p for p in inv_files if p not in tracked_set)
    local_only_by_name = defaultdict(list)
    for p in local_only:
        local_only_by_name[PurePosixPath(p).name].append(p)

    # 1. completeness per expected role
    roles = []
    for folder, city in CITIES.items():
        for role in EXPECTED_ROLES:
            prefix = f"research/{folder}/{role}/"
            files = [p for p in tracked if p.startswith(prefix)]
            roles.append({
                "city": city, "role": role, "file_count": len(files),
                "reports": [p for p in files if kind_of(PurePosixPath(p).name) == "report"],
                "evidence": [p for p in files if kind_of(PurePosixPath(p).name) == "evidence"],
                "local_only_in_inventory": [p for p in local_only if p.startswith(prefix)],
            })

    # 2. integrity of tracked files vs inventory sha256
    integrity = []
    for p, f in sorted(inv_files.items()):
        if p not in tracked_set:
            continue
        data = (ROOT / p).read_bytes()
        if hashlib.sha256(data).hexdigest() == f["sha256"]:
            continue
        crlf = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        integrity.append({"path": p, "inventory_bytes": f["bytes"], "git_bytes": len(data),
                          "lf_count": data.count(b"\n"),
                          "matches_inventory_after_lf_to_crlf": hashlib.sha256(crlf).hexdigest() == f["sha256"]})
    tracked_role_files = [p for p in tracked if role_of(p)[0]]
    not_in_inventory = sorted(p for p in tracked_role_files if p not in inv_files)

    # 3. byte-identical groups inside role folders (reported, never deleted)
    dup = defaultdict(list)
    for p in tracked_role_files:
        dup[hashlib.sha256((ROOT / p).read_bytes()).hexdigest()].append(p)
    duplicates = [sorted(v) for v in dup.values() if len(v) > 1]

    # 4. references
    uniq = {}
    for src in tracked_role_files:
        if PurePosixPath(src).suffix.lower() not in TEXT_EXT:
            continue
        city, role, role_dir = role_of(src)
        text = (ROOT / src).read_text(encoding="utf-8-sig", errors="replace")
        src_dir = PurePosixPath(src).parent
        for loc, ref, ctx in extract_refs(src, text):
            name = PurePosixPath(ref).name
            if name == PurePosixPath(src).name:
                continue
            key = (src, ref)
            if key in uniq:
                uniq[key]["locs"].append(loc)
                continue
            row = {"source": src, "source_kind": kind_of(PurePosixPath(src).name), "city": city,
                   "role": role, "locs": [loc], "ref": ref, "context": ctx}
            rel = ref.lstrip("/")
            has_dir = "/" in rel
            direct = [str(c) for c in (src_dir / rel, PurePosixPath(rel), role_dir / rel) if str(c) in tracked_set]
            suffix = [p for p in tracked if p.endswith("/" + rel)] if has_dir else []
            parts = rel.split("/")
            combined = has_dir and all(str(src_dir / x) in tracked_set for x in parts)
            hits = suffix or by_name.get(name, [])
            if direct:
                row.update(status="ok_path", found=direct[:1])
            elif combined:
                row.update(status="ok_combined", found=[str(src_dir / x) for x in parts])
            elif hits:
                same_dir = [h for h in hits if PurePosixPath(h).parent == src_dir]
                same_role = [h for h in hits if h.startswith(str(role_dir) + "/")]
                same_city = [h for h in hits if role_of(h)[0] == city]
                other_city = [h for h in hits if role_of(h)[0] and role_of(h)[0] != city]
                if same_dir and not has_dir:
                    row.update(status="ok_same_dir", found=same_dir)
                elif same_role:
                    row.update(status="wrong_path_same_role" if has_dir else "other_dir_same_role", found=same_role)
                elif same_city:
                    row.update(status="other_role_same_city", found=same_city)
                elif other_city:
                    row.update(status="other_city_only", found=other_city)
                else:
                    row.update(status="repo_outside_research", found=hits)
            elif by_name_cf.get(name.casefold()):
                row.update(status="case_mismatch", found=by_name_cf[name.casefold()])
            elif local_only_by_name.get(name):
                row.update(status="local_zip_only", found=local_only_by_name[name])
            else:
                row.update(status="not_found", found=[])
            uniq[key] = row
    refs = sorted(uniq.values(), key=lambda r: (r["city"], r["role"], r["source"], r["ref"]))
    counts, cats = defaultdict(int), defaultdict(int)
    for r in refs:
        r["category"] = classify(r)
        r["declared_deliverable"] = declared_deliverable(r)
        counts[r["status"]] += 1
        cats[r["category"]] += 1

    sandbox = defaultdict(set)
    for p in tracked_role_files:
        if p.endswith(".py"):
            for m in re.finditer(r"[\"'](/home/[^\"']+|/tmp/[^\"']+|/mnt/[^\"']+)[\"']", (ROOT / p).read_text(encoding="utf-8", errors="replace")):
                sandbox[p].add(m.group(1))

    result = {
        "audited_commit": git_head(),
        "scope": "git-tracked files + research/coordination/INVENTORY.json; references extracted heuristically, "
                 "not_found entries reviewed by hand and encoded in the rule tables of k11_ref_audit.py",
        "roles": roles,
        "inventory_local_only": local_only,
        "tracked_role_files_not_in_inventory": not_in_inventory,
        "integrity_mismatches": integrity,
        "duplicate_groups": duplicates,
        "scripts_with_absolute_sandbox_paths": {k: sorted(v) for k, v in sorted(sandbox.items())},
        "reference_status_counts": dict(sorted(counts.items())),
        "reference_category_counts": dict(sorted(cats.items())),
        "references": refs,
    }
    (OUT / "k11_ref_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_lists(result)
    print("commit", result["audited_commit"])
    print("status", json.dumps(result["reference_status_counts"]))
    print("category", json.dumps(result["reference_category_counts"]))
    print("integrity", len(integrity), "duplicates", len(duplicates), "local-only", len(local_only),
          "sandbox-path scripts", len(sandbox))


if __name__ == "__main__":
    main()
