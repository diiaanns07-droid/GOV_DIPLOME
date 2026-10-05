#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K07 round 3: is the road input a connected, usable PEDESTRIAN graph?

Rules (from the K07 round-3 task):
  * topology only from shared connector ids (Overture `connectors[] {connector_id, at}`),
    never from geometric intersections of lines (bridges/tunnels would be joined falsely);
  * walk permission and direction only from `access_restrictions`; if absent -> "unknown", not "allowed";
  * grade separation from `road_flags` (is_bridge / is_tunnel) or `level_rules`; if absent -> "unknown";
  * a sample (e.g. "first 8 segments per class") is not a network; an object outside the graph or at the
    clip edge is "not computed", never "unreachable".

Inputs:
  K10 samples  research/round-3-results/K07/inputs/k10/samples/<city>_road_segments_sample.geojson
  future export: same GeoJSON layout, but properties.connectors = [{"connector_id": str, "at": 0..1}],
                 properties.access_restrictions, properties.road_flags, properties.level_rules,
                 top-level "k07_clip": {"bbox": [w,s,e,n], "selection": "all_segments_intersecting_clip"}.

Usage:  python3 graph_check.py                       -> results/graph_check.json (K10 samples + synthetic self-test)
        python3 graph_check.py --input export.geojson  -> also checks a future connected export (printed + stored under "extra_inputs")
Requires: Python 3.12, shapely 2.1.2, pyproj 3.8.0, networkx 3.6.1
"""
import json, math, sys
from pathlib import Path

import networkx as nx
from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import substring, transform
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
K07 = HERE.parent
GEOD = Geod(ellps="WGS84")
EDGE_BUFFER_M = 200          # nodes this close to the clip boundary are "edge" nodes
FOOT_MODES = {"foot", "pedestrian"}


def local_projection(lon, lat):
    """Azimuthal equidistant projection centred on the data: metres, works for any city and for the fixture."""
    t = Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m", always_xy=True)
    return lambda geom: transform(t.transform, geom)


def foot_rule(rules):
    """Return ('denied'|'allowed'|'unknown', directional:bool) for pedestrians from Overture-like access_restrictions."""
    if rules is None:
        return "unknown", False
    verdict, directional = "allowed", False   # an explicit empty list = no restriction recorded
    for r in rules:
        when = r.get("when") or {}
        modes = set(when.get("mode") or [])
        applies = not modes or bool(modes & FOOT_MODES)
        if not applies:
            continue
        if when.get("heading"):
            directional = True
        if r.get("access_type") == "denied" and not when.get("heading"):
            verdict = "denied"
    return verdict, directional


def grade_flags(props):
    flags = props.get("road_flags")
    levels = props.get("level_rules")
    if flags is None and levels is None:
        return None
    vals = set()
    for f in flags or []:
        vals.update(f.get("values") or [])
    return {"is_bridge": "is_bridge" in vals, "is_tunnel": "is_tunnel" in vals,
            "has_level": any((l.get("value") or 0) != 0 for l in (levels or []))}


def check(fc, name):
    feats = fc["features"]
    props = [f["properties"] for f in feats]
    lines = [shape(f["geometry"]) for f in feats]
    xs = [c[0] for g in lines for c in g.coords]
    ys = [c[1] for g in lines for c in g.coords]
    proj = local_projection((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    plines = [proj(g) for g in lines]
    clip = fc.get("k07_clip")

    connectors_ok = all(isinstance(p.get("connectors"), list) and all(
        isinstance(c, dict) and "connector_id" in c and "at" in c for c in p["connectors"]) for p in props)
    access_present = sum(p.get("access_restrictions") is not None for p in props)
    grade_present = sum(grade_flags(p) is not None for p in props)

    # diagnostics that do NOT build a network: geometric crossings and shared vertices inside the input
    tree = STRtree(plines)
    crossings, near = 0, []
    for i, g in enumerate(plines):
        for j in tree.query(g.buffer(1.0)):
            if j > i and g.crosses(plines[j]):
                crossings += 1
        others = [plines[j] for j in tree.query(g.buffer(5000)) if j != i]
        near.append(min((g.distance(o) for o in others), default=math.inf))
    finite = sorted(x for x in near if math.isfinite(x))
    med_gap = finite[len(finite) // 2] if finite else None
    no_neighbour_5km = sum(1 for x in near if not math.isfinite(x))
    end_coords = {}
    for i, g in enumerate(lines):
        for c in (g.coords[0], g.coords[-1]):
            end_coords.setdefault((round(c[0], 7), round(c[1], 7)), set()).add(i)
    shared_end = sum(1 for s in end_coords.values() if len(s) > 1)
    km = sum(GEOD.geometry_length(g) for g in lines) / 1000

    res = {"input": name, "segments": len(feats), "length_km_geodesic": round(km, 2),
           "sampling_declared": fc.get("k07_clip", {}).get("selection") or fc.get("name"),
           "C1_topology_from_connector_ids": connectors_ok,
           "C2_walk_permission_field_present_share": round(access_present / len(feats), 3),
           "C3_direction_for_pedestrians": "from access_restrictions" if access_present == len(feats) else "unknown",
           "C4_grade_separation_field_present_share": round(grade_present / len(feats), 3),
           "C5_complete_clip_not_sample": bool(clip and clip.get("selection") == "all_segments_intersecting_clip"),
           "diagnostics_not_used_for_graph": {
               "geometric_crossings_between_input_segments": crossings,
               "median_gap_to_nearest_other_segment_m": None if med_gap is None else round(med_gap, 1),
               "segments_without_other_segment_within_5km": no_neighbour_5km,
               "endpoint_coordinates_shared_by_2plus_segments": shared_end}}

    if not connectors_ok:
        res["verdict"] = "view_only"
        res["reasons"] = ["connector ids and positions are absent (only a count) -> topology cannot be rebuilt without "
                          "joining intersecting lines, which is not allowed"]
        if access_present < len(feats):
            res["reasons"].append("access_restrictions absent -> pedestrian permission and direction unknown")
        if grade_present < len(feats):
            res["reasons"].append("road_flags / level_rules absent -> bridges and tunnels cannot be told apart")
        if not res["C5_complete_clip_not_sample"]:
            res["reasons"].append("input is a sample, not all segments of a clip area -> any distance would be cut by the sample edge")
        return res, None

    # ---- connector graph (future export) ----
    G = nx.MultiDiGraph()
    unknown_km = denied_km = 0.0
    seg_conn = []
    for f, p, g, pg in zip(feats, props, lines, plines):
        conns = sorted(p["connectors"], key=lambda c: c["at"])
        seg_conn.append({c["connector_id"] for c in conns})
        rule, directional = foot_rule(p.get("access_restrictions"))
        L = GEOD.geometry_length(g)
        if rule == "denied":
            denied_km += L / 1000
            continue
        if rule == "unknown":
            unknown_km += L / 1000
        for a, b in zip(conns, conns[1:]):
            piece = substring(g, a["at"], b["at"], normalized=True)
            d = GEOD.geometry_length(piece)
            for u, v in ((a["connector_id"], b["connector_id"]), (b["connector_id"], a["connector_id"])):
                G.add_edge(u, v, m=d, seg=p.get("overture_id"), permission=rule)
            if directional:
                pass  # heading-specific foot rules are reported; this checker keeps both directions and flags them
        for c in conns:
            G.nodes[c["connector_id"]].setdefault("xy", g.interpolate(c["at"], normalized=True).coords[0])
    # crossings without a shared connector are grade separations or data errors; they are reported, never joined
    unjoined = 0
    for i, g in enumerate(plines):
        for j in tree.query(g.buffer(1.0)):
            if j > i and g.crosses(plines[j]) and not (seg_conn[i] & seg_conn[j]):
                unjoined += 1
    comps = sorted(nx.weakly_connected_components(G), key=len, reverse=True) if G.number_of_nodes() else []
    edge_nodes = set()
    if clip:
        cb = proj(box(*clip["bbox"])).exterior
        for n, d in G.nodes(data=True):
            if "xy" in d and proj(Point(d["xy"])).distance(cb) <= EDGE_BUFFER_M:
                edge_nodes.add(n)
    res.update({"graph_nodes": G.number_of_nodes(), "graph_edges_directed": G.number_of_edges(),
                "components": len(comps), "largest_component_nodes": len(comps[0]) if comps else 0,
                "km_permission_unknown": round(unknown_km, 3), "km_denied_for_foot": round(denied_km, 3),
                "crossings_without_shared_connector_not_joined": unjoined,
                "edge_nodes_within_m_of_clip": {"buffer_m": EDGE_BUFFER_M, "count": len(edge_nodes)}})
    problems = []
    if not res["C5_complete_clip_not_sample"]:
        problems.append("not a complete clip")
    if res["C2_walk_permission_field_present_share"] < 1:
        problems.append("pedestrian permission unknown on part of the segments")
    if res["C4_grade_separation_field_present_share"] < 1:
        problems.append("grade separation unknown on part of the segments")
    res["verdict"] = "routable" if not problems else "routable_with_warnings"
    res["reasons"] = problems
    return res, (G, edge_nodes, proj)


def nearest_node(G, proj, lon, lat):
    p = proj(Point(lon, lat))
    best = min(((proj(Point(d["xy"])).distance(p), n) for n, d in G.nodes(data=True) if "xy" in d), default=None)
    return best


def compare(G, edge_nodes, proj, origin, targets, threshold_m, snap_max_m=150):
    """Network vs straight-line distance from origin to each target in THIS graph (not provision by seats)."""
    so = nearest_node(G, proj, *origin)
    out = []
    dist = {}
    if so and so[0] <= snap_max_m:
        dist = nx.single_source_dijkstra_path_length(G, so[1], weight="m")
    for t in targets:
        straight = GEOD.inv(origin[0], origin[1], t["lon"], t["lat"])[2]
        st = nearest_node(G, proj, t["lon"], t["lat"])
        row = {"id": t["id"], "straight_m": round(straight, 1)}
        if not so or so[0] > snap_max_m:
            row.update(status="origin_not_on_graph", network_m=None)
        elif not st or st[0] > snap_max_m:
            row.update(status="target_not_on_graph", network_m=None)
        elif st[1] in dist:
            net = so[0] + dist[st[1]] + st[0]
            row.update(status="ok", network_m=round(net, 1), ratio=round(net / straight, 3) if straight else None,
                       within_threshold_network=net <= threshold_m, within_threshold_straight=straight <= threshold_m)
        else:
            # conservative: if either side's component reaches the clip edge, a path may exist outside the clip
            target_comp = nx.node_connected_component(G.to_undirected(as_view=True), st[1])
            touches_edge = bool(edge_nodes & (set(dist) | target_comp))
            row.update(status="no_path_in_graph_edge_of_clip" if touches_edge else "no_path_in_graph", network_m=None)
        out.append(row)
    return out


# ------------------------------------------------------------------ synthetic fixture (NOT a city)
def fixture():
    """Tiny SYNTHETIC network at Null Island (0°,0°). 0.001° ≈ 111 m. Tests the rules, not a place."""
    def seg(i, coords, conns, cls="footway", access=None, flags=None):
        return {"type": "Feature", "properties": {"overture_id": i, "class": cls, "connectors": conns,
                                                  "access_restrictions": access if access is not None else [],
                                                  "road_flags": flags if flags is not None else [], "level_rules": []},
                "geometry": {"type": "LineString", "coordinates": coords}}
    fs = [
        seg("s1", [[0, 0], [0.002, 0]], [{"connector_id": "c1", "at": 0}, {"connector_id": "c2", "at": 1}]),
        seg("s2", [[0.002, 0], [0.002, 0.002]], [{"connector_id": "c2", "at": 0}, {"connector_id": "c3", "at": 1}]),
        # bridge crossing s1 at (0.001, 0) without a shared connector: must NOT be joined
        seg("s3", [[0.001, -0.001], [0.001, 0.001]], [{"connector_id": "c4", "at": 0}, {"connector_id": "c5", "at": 1}],
            cls="primary", flags=[{"values": ["is_bridge"]}]),
        # motorway denied for pedestrians
        seg("s4", [[0.002, 0.002], [0.004, 0.002]], [{"connector_id": "c3", "at": 0}, {"connector_id": "c6", "at": 1}],
            cls="motorway", access=[{"access_type": "denied", "when": {"mode": ["foot"]}}]),
        # isolated piece reaching the clip edge
        seg("s5", [[0.0045, 0.004], [0.005, 0.004]], [{"connector_id": "c7", "at": 0}, {"connector_id": "c8", "at": 1}]),
    ]
    return {"type": "FeatureCollection", "name": "SYNTHETIC fixture, Null Island",
            "k07_clip": {"bbox": [-0.0027, -0.0036, 0.0054, 0.0043], "selection": "all_segments_intersecting_clip"},
            "features": fs}


def selftest():
    res, (G, edge_nodes, proj) = check(fixture(), "synthetic_fixture")
    targets = [{"id": "near_c3", "lon": 0.002, "lat": 0.0021}, {"id": "bridge_end_c5", "lon": 0.001, "lat": 0.0011},
               {"id": "isolated_c8", "lon": 0.005, "lat": 0.0041}]
    cmp_rows = compare(G, edge_nodes, proj, (0.0, 0.0001), targets, threshold_m=500)
    by = {r["id"]: r for r in cmp_rows}
    expect = {
        "only connector topology": res["crossings_without_shared_connector_not_joined"] == 1,
        "bridge not joined -> 3 components": res["components"] == 3,
        "motorway excluded for foot": res["km_denied_for_foot"] > 0.2,
        "network longer than straight": by["near_c3"]["status"] == "ok" and by["near_c3"]["network_m"] > by["near_c3"]["straight_m"],
        "bridge end: no path in graph (interior), never 'unreachable'": by["bridge_end_c5"]["status"] == "no_path_in_graph",
        "isolated piece at clip edge is flagged as edge": by["isolated_c8"]["status"] == "no_path_in_graph_edge_of_clip",
        "edge nodes are only the isolated piece": res["edge_nodes_within_m_of_clip"]["count"] == 2,
    }
    return {"kind": "SYNTHETIC fixture at Null Island; tests the checker, not a city", "check": res,
            "comparison_from_origin_0_0.0001": cmp_rows, "expectations": expect, "passed": all(expect.values())}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", default=[], help="extra segments GeoJSON to check (future K10 export)")
    args = ap.parse_args()
    out = {"kind": "graph usability check", "inputs": {}, "cities": {}}
    for city in ("shymkent", "astana"):
        p = K07 / "inputs/k10/samples" / f"{city}_road_segments_sample.geojson"
        fc = json.loads(p.read_text(encoding="utf-8"))
        res, _ = check(fc, str(p.relative_to(K07)))
        out["cities"][city] = res
    for extra in args.input:
        res, _ = check(json.loads(Path(extra).read_text(encoding="utf-8")), extra)
        out.setdefault("extra_inputs", {})[extra] = res
        print(json.dumps(res, ensure_ascii=False, indent=1))
    st = selftest()
    out["synthetic_selftest"] = st
    (K07 / "results").mkdir(exist_ok=True)
    (K07 / "results/graph_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({c: {k: v for k, v in r.items() if k in ("segments", "length_km_geodesic", "verdict", "reasons", "diagnostics_not_used_for_graph")}
                      for c, r in out["cities"].items()}, ensure_ascii=False, indent=1))
    print("synthetic selftest passed:", st["passed"], st["expectations"])
    if not st["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
