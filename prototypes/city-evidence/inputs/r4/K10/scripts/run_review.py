"""K10 round-4 REVIEW: measurements behind REVIEW.md (K10 round-3 package vs K07 round-3 graph_check).

Calls K07 graph_check.check() on the package as-is and through the adapter. K07 main() is NOT called
(it would overwrite inputs/K07/results/graph_check.json next to the copied script).
Usage (repo root, Python 3.12 with K07 pins):
    python research/round-4-results/K10/scripts/run_review.py > research/round-4-results/K10/results/review_measurements.json
"""
import collections
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import substring

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "scripts"))
import k10_k07_adapter as A  # noqa: E402

GC_PATH = HERE / "inputs/K07/scripts/graph_check.py"
spec = importlib.util.spec_from_file_location("k07_graph_check", GC_PATH)
GC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GC)
KEYS = ("verdict", "reasons", "C1_topology_from_connector_ids", "C2_walk_permission_field_present_share",
        "C4_grade_separation_field_present_share", "C5_complete_clip_not_sample", "graph_nodes", "components",
        "largest_component_nodes", "km_permission_unknown", "km_denied_for_foot",
        "crossings_without_shared_connector_not_joined", "edge_nodes_within_m_of_clip")


def q(v, p):
    v = sorted(v)
    return round(v[min(len(v) - 1, int(p * len(v)))], 3)


def city_review(city):
    d = A.load_package(city)
    feats = d["segments"]["features"]
    pos = {f["id"]: f["geometry"]["coordinates"] for f in d["connectors"]["features"]}
    out = {"package_files_sha256": {k: d[k + "_sha256"] for k in ("segments", "connectors", "places_social")}}

    as_is, _ = GC.check(d["segments"], f"{city} as-is")
    adapted_fc = A.to_k07(city, d)
    adapted, (G, k07_edge, _proj) = GC.check(adapted_fc, f"{city} adapted")
    out["k07_check_as_is"] = {k: as_is.get(k) for k in KEYS}
    out["k07_check_adapted"] = {k: adapted.get(k) for k in KEYS}
    out["k07_clip_written_by_adapter"] = adapted_fc["k07_clip"]

    out["foot_status_k10_vs_k07"] = {f"{a} -> {b}": n for (a, b), n in sorted(collections.Counter(
        (f["properties"]["k10_foot_access"], GC.foot_rule(f["properties"]["access_restrictions"])[0]) for f in feats).items())}

    planar, edge_abs, edge_rel = [], [], []
    for f in feats:
        g = shape(f["geometry"])
        L = A.GEOD.geometry_length(g)
        cs = f["properties"]["connectors"]
        for c in cs:
            p = g.interpolate(c["at"], normalized=True)
            planar.append(A.GEOD.inv(p.x, p.y, *pos[c["connector_id"]])[2])
        for a, b in zip(cs, cs[1:]):
            k07 = A.GEOD.geometry_length(substring(g, a["at"], b["at"], normalized=True))
            true = (b["at"] - a["at"]) * L
            edge_abs.append(abs(k07 - true))
            if true > 1:
                edge_rel.append(abs(k07 - true) / true)
    out["k07_planar_at_node_error_m"] = {"n": len(planar), "p50": q(planar, .5), "p99": q(planar, .99), "max": round(max(planar), 3)}
    out["k07_planar_at_edge_length_error"] = {"edges": len(edge_abs), "abs_m_p99": q(edge_abs, .99), "abs_m_max": round(max(edge_abs), 2),
                                             "rel_p99": q(edge_rel, .99), "rel_max": round(max(edge_rel), 3)}

    lines = [shape(f["geometry"]) for f in feats]
    conn = [{c["connector_id"] for c in f["properties"]["connectors"]} for f in feats]
    crossings = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if not (conn[i] & conn[j]) and lines[i].crosses(lines[j]):
                pi, pj = feats[i]["properties"], feats[j]["properties"]
                graded = bool(pi["k10_flags"] or pi["k10_levels"] or pj["k10_flags"] or pj["k10_levels"])
                crossings.append({"a": [pi["overture_id"], pi["class"], pi["k10_flags"], pi["k10_levels"]],
                                  "b": [pj["overture_id"], pj["class"], pj["k10_flags"], pj["k10_levels"]],
                                  "grade_separation_flagged": graded})
    out["crossings_without_shared_connector"] = {"count": len(crossings),
                                                 "without_any_bridge_tunnel_level_flag": sum(1 for c in crossings if not c["grade_separation_flagged"]),
                                                 "pairs": crossings}

    data_edge = A.edge_nodes(d)
    topo = A.build_graph(d["segments"], "topology")
    strict = A.build_graph(d["segments"], "strict_foot")
    comps, seen = [], set()
    for n in topo:
        if n not in seen:
            c = A.component_of(topo, n)
            seen |= c
            comps.append(c)
    comps.sort(key=len, reverse=True)
    minor = comps[1:]
    out["edge_nodes"] = {"k07_rule_within_200m_of_clip": len(k07_edge), "k10_data_flags": len(data_edge),
                         "graph_nodes_topology_mode": len(topo),
                         "minor_components": len(minor),
                         "minor_components_touching_edge_by_k10_flags": sum(1 for c in minor if c & data_edge),
                         "minor_components_touching_edge_by_k07_200m": sum(1 for c in minor if c & k07_edge)}
    seg_strict = {sid for u in strict for (_d, sid, _s) in strict[u].values()}
    out["graph_modes"] = {"topology": {"nodes": len(topo), "components": len(comps), "largest_component_nodes": len(comps[0])},
                          "strict_foot": {"nodes": len(strict), "segments": len(seg_strict)}}

    st = {f["id"]: A.strict_foot(f["properties"]) for f in feats}
    nodes = [(f["id"], f["geometry"]["coordinates"]) for f in d["connectors"]["features"] if f["id"] in topo]
    places = sorted(d["places_social"]["features"], key=lambda f: f["id"])

    def snap(p):
        x, y = p["geometry"]["coordinates"]
        n = min(nodes, key=lambda n: A.GEOD.inv(x, y, *n[1])[2])
        return n[0], round(A.GEOD.inv(x, y, *n[1])[2], 1)

    o, o_d = snap(places[0])
    rows = []
    for p in places[1:6]:
        t, t_d = snap(p)
        r = A.reach(topo, data_edge, o, t, st)
        r.update({"target": p["id"], "snap_m": t_d,
                  "straight_m": round(A.GEOD.inv(*places[0]["geometry"]["coordinates"], *p["geometry"]["coordinates"])[2], 1)})
        rows.append(r)
    out["topology_mode_example"] = {"mode": "topology_only (link exists in Overture/OSM graph; NOT pedestrian permission)",
                                    "origin_place": places[0]["id"], "origin_snap_m": o_d, "rows": rows}
    return out


def main():
    res = {"review": "K10 round 4: K10 round-3 package (ea703f1) vs K07 round-3 graph_check (6778ded)",
           "k07_graph_check_sha256": hashlib.sha256(GC_PATH.read_bytes()).hexdigest(),
           "k07_synthetic_selftest_passed": GC.selftest()["passed"],
           "cities": {c: city_review(c) for c in ("shymkent", "astana")}}
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
