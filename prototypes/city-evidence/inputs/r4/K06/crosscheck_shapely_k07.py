"""K06 round 4: cross-check (optional, needs shapely 2.1.2 + pyproj) that
  (a) the stdlib oracle agrees with pyproj Geod(WGS84) (Karney) on every K10 segment, and
  (b) review_k10.planar_sub reproduces shapely substring(..., normalized=True) used in K07 graph_check.py,
  (c) the K07 expression for one edge and node on the worst edges.
Usage: python crosscheck_shapely_k07.py <k10_pkg_dir> <out.json>"""
import json, os, sys
from pyproj import Geod
from shapely.geometry import LineString
from shapely.ops import substring
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_oracle import polyline_m, vincenty_m
from review_k10 import planar_sub, planar_point, sub_polyline

GEOD = Geod(ellps="WGS84")
pkg, out = sys.argv[1], sys.argv[2]
man = json.load(open(os.path.join(pkg, "package_manifest.json"), encoding="utf-8"))
res = {"versions": {"shapely": __import__("shapely").__version__, "pyproj": __import__("pyproj").__version__}, "cities": {}}
for city, cm in man["cities"].items():
    sg = json.load(open(os.path.join(pkg, cm["files"]["segments"]["path"]), encoding="utf-8"))["features"]
    rel_oracle, emu_err, k07 = [], [], []
    for f in sg:
        coords = f["geometry"]["coordinates"]
        g = LineString(coords)
        L = GEOD.geometry_length(g)
        rel_oracle.append(abs(polyline_m(coords) - L) / L)
        cs = sorted(f["properties"]["connectors"], key=lambda c: c["at"])
        for a, b in zip(cs, cs[1:]):
            piece = substring(g, a["at"], b["at"], normalized=True)          # K07 graph_check.py line 150
            d_k07 = GEOD.geometry_length(piece)                                 # K07 line 151
            d_emu = polyline_m(planar_sub(coords, a["at"], b["at"]))
            d_good = polyline_m(sub_polyline(coords, a["at"], b["at"]))
            emu_err.append(abs(d_k07 - d_emu))
            k07.append((abs(d_k07 - d_good), f["id"], round(d_k07, 2), round(d_good, 2)))
    k07.sort(reverse=True)
    res["cities"][city] = {"oracle_vs_pyproj_rel_max": max(rel_oracle),
                           "planar_emulation_vs_shapely_m_max": round(max(emu_err), 4),
                           "k07_edge_vs_geodesic_split_top3": [{"segment": s, "k07_m": a, "geodesic_split_m": b, "abs_diff_m": round(d, 2)}
                                                               for d, s, a, b in k07[:3]],
                           "k07_edges_diff_gt_5m": sum(1 for d, *_ in k07 if d > 5), "edges": len(k07)}
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
