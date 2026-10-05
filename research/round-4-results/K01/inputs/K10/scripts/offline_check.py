"""K10 round 3 OFFLINE check of the committed geo-package (Python stdlib only, no network).

* blocks all socket connections for the duration of the check;
* audits every file opened: only package files listed in package_manifest.json
  (plus the manifest and this package's scripts) may be read;
* verifies sha256/bytes/feature counts against package_manifest.json;
* recomputes: id uniqueness, bbox membership, edge flags, lengths, foot-access class,
  segment->connector referential integrity, graph connectivity (via connector ids only,
  never via geometric intersection), objects near the bbox edge.

Usage (from anywhere): python scripts/offline_check.py [--json report.json]
Exit code 0 = all integrity checks passed.
"""
import builtins
import hashlib
import json
import os
import socket
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from geo_util import dist_to_bbox_edge_m, line_length_m, point_in_bbox  # noqa: E402
from k10_rules import SOCIAL_GROUPS, foot_access  # noqa: E402

EDGE_M = 100.0
OPENED = []


class NetworkBlocked(RuntimeError):
    pass


def _no_net(*a, **k):
    raise NetworkBlocked("network access attempted during offline check")


def install_guards():
    socket.socket.connect = _no_net
    socket.socket.connect_ex = _no_net
    socket.create_connection = _no_net
    real_open = builtins.open

    def audited_open(file, *a, **k):
        if isinstance(file, (str, bytes, os.PathLike)):
            OPENED.append(os.path.abspath(os.fsdecode(file)))
        return real_open(file, *a, **k)

    builtins.open = audited_open
    return real_open


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def seg_intersects_bbox(coords, bb):
    """Liang-Barsky clip of each line piece against bb (stdlib)."""
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        dx, dy = x1 - x0, y1 - y0
        t0, t1, ok = 0.0, 1.0, True
        for p, q in ((-dx, x0 - bb[0]), (dx, bb[2] - x0), (-dy, y0 - bb[1]), (dy, bb[3] - y0)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
            else:
                t = q / p
                if p < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
                if t0 > t1:
                    ok = False
                    break
        if ok:
            return True
    return len(coords) == 1 and point_in_bbox(*coords[0][:2], bb)


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def components(segs, select):
    uf = UF()
    seg_root = {}
    for f in segs:
        p = f["properties"]
        if not select(p):
            continue
        cids = [c["connector_id"] for c in p["connectors"] or []]
        if not cids:
            continue
        for a, b in zip(cids, cids[1:]):
            uf.union(a, b)
        seg_root[f["id"]] = cids[0]
    length = Counter()
    count = Counter()
    for f in segs:
        if f["id"] in seg_root:
            r = uf.find(seg_root[f["id"]])
            length[r] += f["properties"]["k10_length_m"]
            count[r] += 1
    total = sum(length.values())
    top = length.most_common(1)
    return {"segments": len(seg_root), "components": len(length),
            "largest_component_share_of_length": round(top[0][1] / total, 4) if total else None,
            "largest_component_segments": count[top[0][0]] if top else 0,
            "singleton_components": sum(1 for r in count if count[r] == 1)}


def check_city(city, cm, errors):
    bb = cm["bbox"]
    layers = {}
    for name, fmeta in cm["files"].items():
        path = os.path.join(PKG, fmeta["path"])
        if sha256_file(path) != fmeta["sha256"]:
            errors.append(f"{city}/{name}: sha256 mismatch")
        if os.path.getsize(path) != fmeta["bytes"]:
            errors.append(f"{city}/{name}: size mismatch")
        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        if len(fc["features"]) != fmeta["features"]:
            errors.append(f"{city}/{name}: feature count {len(fc['features'])} != manifest {fmeta['features']}")
        if fc.get("release") != MANIFEST["release"] or fc.get("city") != city or fc.get("bbox") != bb:
            errors.append(f"{city}/{name}: header release/city/bbox mismatch")
        ids = [f["id"] for f in fc["features"]]
        dup = [i for i, n in Counter(ids).items() if n > 1]
        if dup:
            errors.append(f"{city}/{name}: {len(dup)} duplicate ids")
        if any(f["id"] != f["properties"]["overture_id"] for f in fc["features"]):
            errors.append(f"{city}/{name}: id != overture_id")
        layers[name] = fc["features"]

    rep = {"bbox": bb}
    # places
    pl = layers["places_social"]
    out_box = [f["id"] for f in pl if not point_in_bbox(*f["geometry"]["coordinates"][:2], bb)]
    bad_grp = [f["id"] for f in pl if f["properties"]["k10_group"] not in SOCIAL_GROUPS]
    if out_box:
        errors.append(f"{city}: {len(out_box)} places outside bbox")
    if bad_grp:
        errors.append(f"{city}: {len(bad_grp)} places with unknown k10_group")
    near = [f for f in pl if dist_to_bbox_edge_m(*f["geometry"]["coordinates"][:2], bb) < EDGE_M]
    name_pos = Counter((f["properties"]["name_primary"], tuple(round(c, 4) for c in f["geometry"]["coordinates"][:2]))
                       for f in pl)
    rep["places"] = {"count": len(pl), "by_group": dict(sorted(Counter(f["properties"]["k10_group"] for f in pl).items())),
                     "within_100m_of_bbox_edge": len(near),
                     "same_name_same_point_repeats": sum(n - 1 for n in name_pos.values() if n > 1),
                     "confidence_lt_0_5": sum(1 for f in pl if (f["properties"]["confidence"] or 0) < 0.5)}

    # segments
    sg = layers["segments"]
    not_inter = [f["id"] for f in sg if not seg_intersects_bbox(f["geometry"]["coordinates"], bb)]
    if not_inter:
        errors.append(f"{city}: {len(not_inter)} segments do not intersect bbox")
    edge_flag_bad, len_bad, fa_bad = 0, 0, 0
    for f in sg:
        p, coords = f["properties"], f["geometry"]["coordinates"]
        crosses = not all(point_in_bbox(x, y, bb) for x, y in (c[:2] for c in coords))
        edge_flag_bad += crosses != p["k10_crosses_bbox_edge"]
        len_bad += abs(line_length_m(coords) - p["k10_length_m"]) > 0.02
        fa_bad += foot_access(p["access_restrictions"])[0] != p["k10_foot_access"]
    for n, v in (("k10_crosses_bbox_edge", edge_flag_bad), ("k10_length_m", len_bad), ("k10_foot_access", fa_bad)):
        if v:
            errors.append(f"{city}: {v} segments with wrong {n}")
    roads = [f for f in sg if f["properties"]["subtype"] == "road"]

    def oneway_only(p):
        # foot-relevant rules are only "denied, heading=backward, no mode list" (OSM oneway encoding)
        rel = [r for r in p["access_restrictions"] or []
               if (r.get("when") or {}).get("mode") is None or "foot" in (r.get("when") or {}).get("mode")]
        return bool(rel) and all(r.get("access_type") == "denied" and set(k for k, v in (r.get("when") or {}).items() if v) == {"heading"}
                                 and not r.get("between") for r in rel)

    cond = [f["properties"] for f in roads if f["properties"]["k10_foot_access"] == "conditional"]
    rep["segments"] = {
        "conditional_breakdown": {"oneway_heading_only_no_mode": sum(1 for p in cond if oneway_only(p)),
                                  "other_conditions": sum(1 for p in cond if not oneway_only(p))},
        "count": len(sg), "by_subtype": dict(Counter(f["properties"]["subtype"] for f in sg)),
        "road_by_class": dict(Counter(f["properties"]["class"] for f in roads).most_common()),
        "crossing_bbox_edge": sum(1 for f in sg if f["properties"]["k10_crosses_bbox_edge"]),
        "road_length_km_full_geometry": round(sum(f["properties"]["k10_length_m"] for f in roads) / 1000, 3),
        "foot_access": dict(Counter(f["properties"]["k10_foot_access"] for f in roads)),
        "with_access_restrictions": sum(1 for f in roads if f["properties"]["access_restrictions"]),
        "flags": dict(Counter(x for f in roads for x in f["properties"]["k10_flags"])),
        "nonzero_level": sum(1 for f in roads if any(v != 0 for v in f["properties"]["k10_levels"])),
        "subclass": dict(Counter(f["properties"]["subclass"] for f in roads if f["properties"]["subclass"])),
        "with_road_surface": sum(1 for f in roads if f["properties"]["road_surface"]),
        "with_width": sum(1 for f in roads if f["properties"]["width_rules"]),
    }

    # connectors and referential integrity
    cn = layers["connectors"]
    cids = {f["id"] for f in cn}
    ref = Counter(c["connector_id"] for f in sg for c in f["properties"]["connectors"] or [])
    missing = [c for c in ref if c not in cids]
    unref = [c for c in cids if c not in ref]
    if missing:
        errors.append(f"{city}: {len(missing)} referenced connectors missing")
    if unref:
        errors.append(f"{city}: {len(unref)} connectors not referenced by any segment")
    inside_bad = sum(1 for f in cn if point_in_bbox(*f["geometry"]["coordinates"][:2], bb) != f["properties"]["k10_inside_bbox"])
    if inside_bad:
        errors.append(f"{city}: {inside_bad} connectors with wrong k10_inside_bbox")
    rep["connectors"] = {"count": len(cn), "outside_bbox": sum(1 for f in cn if not f["properties"]["k10_inside_bbox"]),
                         "shared_by_2plus_segments": sum(1 for c, n in ref.items() if n >= 2),
                         "missing_referenced": len(missing)}

    # connectivity strictly through connector ids
    rep["graph_all_roads"] = components(sg, lambda p: p["subtype"] == "road")
    rep["graph_roads_foot_not_denied"] = components(
        sg, lambda p: p["subtype"] == "road" and p["k10_foot_access"] != "denied")
    return rep


def run():
    global MANIFEST
    del OPENED[:]
    real_open = install_guards()
    try:
        errors = []
        mpath = os.path.join(PKG, "package_manifest.json")
        with open(mpath, encoding="utf-8") as fh:
            MANIFEST = json.load(fh)
        report = {"package": MANIFEST["package"], "release": MANIFEST["release"], "cities": {}}
        for city, cm in MANIFEST["cities"].items():
            report["cities"][city] = check_city(city, cm, errors)
        allowed = {os.path.abspath(mpath)} | {
            os.path.abspath(os.path.join(PKG, f["path"])) for cm in MANIFEST["cities"].values() for f in cm["files"].values()}
        foreign = sorted({p for p in OPENED if p not in allowed and not p.startswith(HERE + os.sep)})
        if foreign:
            errors.append(f"files outside the package manifest were opened: {foreign}")
        report["files_opened"] = sorted({os.path.relpath(p, PKG) for p in OPENED})
        report["network"] = "socket connect blocked during check"
        report["errors"] = errors
        report["ok"] = not errors
        return report
    finally:
        builtins.open = real_open


MANIFEST = None

if __name__ == "__main__":
    rep = run()
    txt = json.dumps(rep, ensure_ascii=False, indent=1)
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    print(txt)
    sys.exit(0 if rep["ok"] else 1)
