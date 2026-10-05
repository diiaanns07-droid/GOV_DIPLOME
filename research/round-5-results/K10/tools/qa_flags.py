"""K10 round-5 REVIEW: deterministic QA flags for place coordinates in the city-evidence BUILD.

Flags are for human review only: nothing is deleted, merged, re-geocoded or re-categorised.
Stdlib only.  Two input modes:
  --app-root DIR : extracted prototypes/city-evidence (reads web/data.js and, when present,
                   inputs/k10/data/<city>/places_social.geojson for full-precision coordinates and ID checks)
  --url BASE     : running app (e.g. http://127.0.0.1:8765/); reads BASE + "data.js" only
Output is byte-stable for the same inputs (sorted keys/records, no timestamps, no absolute paths).

Usage: python3 qa_flags.py --app-root <dir> [--out qa_flags.json]
       python3 qa_flags.py --url http://127.0.0.1:8765/ [--out qa_flags.json]
"""
import argparse
import hashlib
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

NEAR_M = 2.0
CITY_ONLY_ADDR = {"шымкент", "shymkent", "астана", "astana", "казахстан", "kazakhstan", "қазақстан"}
RULES = {
    "COORD_EXACT_GROUP": ("review", "2+ records share exactly the same coordinate"),
    "COORD_NEAR_GROUP": ("review", f"records within {NEAR_M} m of each other but not identical (single-linkage cluster)"),
    "GROUP_ADDRESS_DIVERGENT": ("review", "one coordinate carries 2+ different non-empty addresses: possible placeholder geocode"),
    "COORD_LOW_PRECISION": ("info", "both lon and lat have <= 4 decimals (grid of ~8-11 m or coarser)"),
    "ADDRESS_EMAIL_LIKE": ("review", "address field contains an e-mail-like string, not an address (value not reproduced)"),
    "ADDRESS_CITY_OR_COUNTRY_ONLY": ("info", "address is only a city or country name"),
    "OUTSIDE_BBOX": ("error", "point lies outside the city square bbox"),
    "ID_MISSING_IN_UI": ("error", "source place id absent from web/data.js"),
    "ID_EXTRA_IN_UI": ("error", "web/data.js place id absent from the K10 source file"),
    "ID_DUPLICATE": ("error", "place id occurs more than once"),
    "COORD_CHANGED_IN_UI": ("error", "web/data.js coordinate differs from source by more than 1e-6 deg"),
}


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def parse_data_js(raw):
    txt = raw.decode("utf-8")
    start, end = txt.index("{"), txt.rstrip().rindex(";")
    return json.loads(txt[start:end])


def decimals(x):
    s = repr(float(x))
    if "e" in s or "E" in s:
        s = f"{x:.12f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def hav(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = p2 - p1, math.radians(b[0] - a[0])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def norm_addr(a):
    return re.sub(r"\s+", " ", (a or "").strip().lower())


def load(args):
    if args.app_root:
        root = Path(args.app_root)
        raw = (root / "web" / "data.js").read_bytes()
        src = {}
        for city in ("shymkent", "astana"):
            p = root / "inputs" / "k10" / "data" / city / "places_social.geojson"
            if p.exists():
                b = p.read_bytes()
                src[city] = {"path": f"inputs/k10/data/{city}/places_social.geojson", "sha256": sha256(b),
                             "fc": json.loads(b.decode("utf-8"))}
        mode = "app-root"
    else:
        base = args.url if args.url.endswith("/") else args.url + "/"
        with urllib.request.urlopen(base + "data.js", timeout=30) as r:
            raw = r.read()
        src, mode = {}, "url"
    return mode, raw, parse_data_js(raw), src


def records(city, ui, src):
    """One row per source record (full precision) or per UI record when no source file is available."""
    if city in src:
        out = []
        for f in src[city]["fc"]["features"]:
            p = f["properties"]
            addrs = [a.get("freeform") for a in (p.get("addresses") or []) if a.get("freeform")]
            out.append({"id": f["id"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
                        "address": "; ".join(addrs) or None})
        return out, {"file": src[city]["path"], "sha256": src[city]["sha256"], "coord_field": "geometry.coordinates"}
    return ([{"id": p["id"], "lon": p["lon"], "lat": p["lat"], "address": p.get("address")} for p in ui["places"]],
            {"file": "web/data.js", "sha256": None, "coord_field": "places[].lon/lat (rounded to 1e-6 by build_data.py)"})


def city_flags(city, ui, src, data_js_sha):
    recs, source = records(city, ui, src)
    if source["sha256"] is None:
        source["sha256"] = data_js_sha
    bb = ui["bbox"]
    flags, groups = [], []

    def add(rid, rule, reason, **extra):
        flags.append({"city": city, "id": rid, "rule": rule, "severity": RULES[rule][0], "reason": reason,
                      "source": {"file": source["file"], "sha256": source["sha256"],
                                 "field": "addresses[].freeform" if rule.startswith("ADDRESS") else source["coord_field"]},
                      **extra})

    # exact groups
    by_xy = {}
    for r in recs:
        by_xy.setdefault((r["lon"], r["lat"]), []).append(r)
    for (lon, lat), members in sorted(by_xy.items()):
        if len(members) < 2:
            continue
        gid = f"{city}:exact:{lon:.7f},{lat:.7f}"
        ids = sorted(m["id"] for m in members)
        addrs = sorted({norm_addr(m["address"]) for m in members if norm_addr(m["address"])})
        inside = bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]
        groups.append({"group_id": gid, "kind": "exact", "city": city, "lon": lon, "lat": lat, "size": len(ids),
                       "ids": ids, "inside_bbox": inside, "distinct_nonempty_addresses": len(addrs)})
        for m in members:
            add(m["id"], "COORD_EXACT_GROUP", f"{len(ids)} records share coordinate ({lon}, {lat})", group_id=gid)
            if len(addrs) >= 2:
                add(m["id"], "GROUP_ADDRESS_DIVERGENT", f"{len(addrs)} different addresses at one coordinate", group_id=gid)

    # near clusters (single linkage) over distinct coordinates
    pts = sorted(by_xy)
    parent = list(range(len(pts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if hav(pts[i], pts[j]) <= NEAR_M:
                parent[find(i)] = find(j)
    clusters = {}
    for i, xy in enumerate(pts):
        clusters.setdefault(find(i), []).append(xy)
    for xys in clusters.values():
        if len(xys) < 2:
            continue
        xys.sort()
        members = sorted(r["id"] for xy in xys for r in by_xy[xy])
        span = max(hav(a, b) for a in xys for b in xys)
        gid = f"{city}:near:{xys[0][0]:.7f},{xys[0][1]:.7f}"
        groups.append({"group_id": gid, "kind": "near", "city": city, "coordinates": [list(x) for x in xys],
                       "size": len(members), "ids": members, "max_span_m": round(span, 2),
                       "inside_bbox": all(bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3] for x, y in xys)})
        for rid in members:
            add(rid, "COORD_NEAR_GROUP", f"{len(members)} records at {len(xys)} coordinates within {round(span, 2)} m", group_id=gid)

    for r in recs:
        if max(decimals(r["lon"]), decimals(r["lat"])) <= 4:
            add(r["id"], "COORD_LOW_PRECISION", f"coordinate ({r['lon']}, {r['lat']}) has <= 4 decimals")
        a = r["address"] or ""
        if re.search(r"[^\s@]+@[^\s@]+\.[^\s@]+", a):
            add(r["id"], "ADDRESS_EMAIL_LIKE", RULES["ADDRESS_EMAIL_LIKE"][1])
        elif norm_addr(a) in CITY_ONLY_ADDR:
            add(r["id"], "ADDRESS_CITY_OR_COUNTRY_ONLY", "address is only a city/country name")
        if not (bb[0] <= r["lon"] <= bb[2] and bb[1] <= r["lat"] <= bb[3]):
            add(r["id"], "OUTSIDE_BBOX", f"({r['lon']}, {r['lat']}) outside {bb}")

    # id integrity UI vs source
    ui_ids = [p["id"] for p in ui["places"]]
    integrity = {"ui_places": len(ui_ids), "source_places": len(recs) if city in src else None}
    for rid in sorted({i for i in ui_ids if ui_ids.count(i) > 1}):
        add(rid, "ID_DUPLICATE", "id occurs more than once in web/data.js")
    if city in src:
        s_ids = {r["id"] for r in recs}
        for rid in sorted(s_ids - set(ui_ids)):
            add(rid, "ID_MISSING_IN_UI", RULES["ID_MISSING_IN_UI"][1])
        for rid in sorted(set(ui_ids) - s_ids):
            add(rid, "ID_EXTRA_IN_UI", RULES["ID_EXTRA_IN_UI"][1])
        uxy = {p["id"]: (p["lon"], p["lat"]) for p in ui["places"]}
        for r in recs:
            if r["id"] in uxy and (abs(uxy[r["id"]][0] - r["lon"]) > 1e-6 or abs(uxy[r["id"]][1] - r["lat"]) > 1e-6):
                add(r["id"], "COORD_CHANGED_IN_UI", f"source ({r['lon']}, {r['lat']}) vs UI {uxy[r['id']]}")
        integrity["all_source_ids_in_ui"] = s_ids <= set(ui_ids)
        integrity["no_extra_ids_in_ui"] = set(ui_ids) <= s_ids
    return flags, groups, integrity


def build(args):
    mode, raw, data, src = load(args)
    js_sha = sha256(raw)
    out = {"schema": "k10-qa-flags-v1", "generator": "research/round-5-results/K10/tools/qa_flags.py",
           "policy": "flags are for review; no record is removed, merged, moved or re-categorised",
           "input": {"mode": mode, "data_js_sha256": js_sha,
                     "source_files": {c: {"path": s["path"], "sha256": s["sha256"]} for c, s in sorted(src.items())}},
           "rules": {k: {"severity": v[0], "description": v[1]} for k, v in RULES.items()},
           "near_threshold_m": NEAR_M, "cities": {}, "groups": [], "flags": []}
    for city in sorted(data["cities"]):
        flags, groups, integ = city_flags(city, data["cities"][city], src, js_sha)
        out["flags"] += flags
        out["groups"] += groups
        summ = {}
        for f in flags:
            summ[f["rule"]] = summ.get(f["rule"], 0) + 1
        out["cities"][city] = {"bbox": data["cities"][city]["bbox"], "flag_counts": dict(sorted(summ.items())),
                               "records_flagged": len({f["id"] for f in flags}), "id_integrity": integ}
    out["flags"].sort(key=lambda f: (f["city"], f["rule"], f["id"], f.get("group_id", "")))
    out["groups"].sort(key=lambda g: (g["city"], g["kind"], g["group_id"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-root")
    g.add_argument("--url")
    ap.add_argument("--out")
    a = ap.parse_args()
    txt = json.dumps(build(a), ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
    sys.stdout.write(txt if not a.out else json.dumps({"written": a.out, "sha256": sha256(txt.encode("utf-8"))}) + "\n")


if __name__ == "__main__":
    main()
