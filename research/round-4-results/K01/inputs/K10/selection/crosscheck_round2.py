"""K10 round 3: independent cross-check of the package against round-2 raw extracts.

Round-2 raw extracts (same Overture release 2026-09-23.1, separate download on 2026-10-05,
sha256 listed in research/next-round/K10/provenance/raw_extracts.sha256) are filtered
with the same query and compared by id with the committed package.
The raw files are NOT committed (3-47 MB each); this check needs them locally.

Usage: python selection/crosscheck_round2.py <raw_dir>   (run from the package dir)
"""
import hashlib
import json
import os
import sys

import shapely
from shapely.geometry import box

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PKG, "scripts"))
from k10_rules import social_group  # noqa: E402
from geo_util import point_in_bbox  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(raw):
    man = json.load(open(os.path.join(PKG, "package_manifest.json"), encoding="utf-8"))
    out = {"check": "package ids vs round-2 raw extracts, same query", "cities": {}}
    for city, cm in man["cities"].items():
        bb = cm["bbox"]
        sq = box(*bb)
        pk = {}
        for layer in ("places_social", "segments"):
            fc = json.load(open(os.path.join(PKG, cm["files"][layer]["path"]), encoding="utf-8"))
            pk[layer] = {f["id"]: f["properties"].get("overture_version") for f in fc["features"]}
        rp = os.path.join(raw, f"{city}_places.jsonl")
        rs = os.path.join(raw, f"{city}_segment.jsonl")
        r_pl, r_sg = {}, {}
        for line in open(rp, encoding="utf-8"):
            p = json.loads(line)
            g = shapely.from_wkt(p["geometry"])
            if point_in_bbox(g.x, g.y, bb) and social_group(p.get("taxonomy"), p.get("basic_category")):
                r_pl[p["id"]] = p.get("version")
        for line in open(rs, encoding="utf-8"):
            s = json.loads(line)
            if shapely.from_wkt(s["geometry"]).intersects(sq):
                r_sg[s["id"]] = s.get("version")
        res = {}
        for layer, r in (("places_social", r_pl), ("segments", r_sg)):
            a, b = set(pk[layer]), set(r)
            res[layer] = {"package": len(a), "round2_raw": len(b), "only_package": sorted(a - b)[:20],
                          "only_round2": sorted(b - a)[:20], "n_only_package": len(a - b), "n_only_round2": len(b - a),
                          "version_mismatch": sum(1 for i in a & b if pk[layer][i] != r[i])}
        res["raw_inputs"] = {os.path.basename(rp): sha(rp), os.path.basename(rs): sha(rs)}
        out["cities"][city] = res
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1]), ensure_ascii=False, indent=1))
