"""K06 round 4 REVIEW of K10 round-3 geo-package lengths and distances (stdlib only, reads files, no network).

Input: K10 package directory extracted byte-exactly from commit ea703f1ddd3a411430a981164a78a7dda64ec909
(see extract_k10.py). Output: JSON report. Cities are reported separately; nothing is merged.

Checks per city:
  C1 coordinate order of every segment/connector/place vs the package bbox ([lon, lat] expected)
  C2 k10_length_m vs independent WGS84 oracle; error classification (ok / km / degrees / swap / mismatch)
  C3 connectors per segment, 'at' ordering and range, connector position vs point at 'at' along geometry
  C4 duplicates: segment ids, identical geometries, parallel edges (same connector pair), repeated connectors
  C5 graph edges between adjacent connectors: oracle sub-polyline length vs naive (at_j - at_i) * k10_length_m;
     sum of edges vs segment length; whole-segment length wrongly attributed to every edge
  C6 components via connector ids only, recomputed independently (BFS), vs K10's stated values
  C7 place-to-bbox-edge distance: K10 approximation vs oracle
  C8 injected unit errors on the real slice (one km, one degrees, one swapped) must be detected
  C9 splitting by 'at' as a fraction of PLANAR lon/lat length (shapely substring(..., normalized=True) on
     EPSG:4326 geometry, as in K07 round-3 graph_check.py) vs the geodesic fraction that 'at' actually encodes
Lengths are geometric lengths in metres, not walking times.
"""
import json, os, sys, statistics as st
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo_oracle import (classify_length, coord_order, cumulative_m, planar_degrees, point_at_fraction,
                        polyline_m, vincenty_m)

K10_STATED = {"shymkent": {"components": 7, "largest_share": 0.9813, "nd_components": 7, "nd_largest_share": 0.9811},
              "astana": {"components": 8, "largest_share": 0.9916, "nd_components": 9, "nd_largest_share": 0.9905}}


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))] if v else None


def sub_polyline(coords, f0, f1):
    """Geometry between fractions f0 < f1 of geodesic length."""
    cum = cumulative_m(coords)
    L = cum[-1]
    a, b = f0 * L, f1 * L
    pts = [point_at_fraction(coords, f0)]
    pts += [list(c[:2]) for c, s in zip(coords, cum) if a < s < b]
    pts.append(point_at_fraction(coords, f1))
    return pts


def planar_point(coords, frac):
    """Point at a fraction of the planar (degree-space) length: what shapely interpolate/substring
    with normalized=True do on lon/lat geometry."""
    import math
    d = [math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(coords, coords[1:])]
    target = max(0.0, min(1.0, frac)) * sum(d)
    acc = 0.0
    for (p, q), di in zip(zip(coords, coords[1:]), d):
        if acc + di >= target and di > 0:
            t = (target - acc) / di
            return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]
        acc += di
    return list(coords[-1][:2])


def planar_sub(coords, f0, f1):
    import math
    d = [0.0]
    for p, q in zip(coords, coords[1:]):
        d.append(d[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    a, b = f0 * d[-1], f1 * d[-1]
    return [planar_point(coords, f0)] + [list(c[:2]) for c, s in zip(coords, d) if a < s < b] + [planar_point(coords, f1)]


def components(segs, select):
    adj = defaultdict(set)
    seg_node = {}
    for f in segs:
        p = f["properties"]
        if not select(p):
            continue
        cids = [c["connector_id"] for c in sorted(p["connectors"] or [], key=lambda c: c["at"])]
        if not cids:
            continue
        seg_node[f["id"]] = cids[0]
        for c in cids:
            adj[c]
        for a, b in zip(cids, cids[1:]):
            adj[a].add(b); adj[b].add(a)
    comp, k = {}, 0
    for n in adj:
        if n in comp:
            continue
        k += 1; stack = [n]; comp[n] = k
        while stack:
            for m in adj[stack.pop()]:
                if m not in comp:
                    comp[m] = k; stack.append(m)
    length = Counter()
    for f in segs:
        if f["id"] in seg_node:
            length[comp[seg_node[f["id"]]]] += polyline_m(f["geometry"]["coordinates"])
    tot = sum(length.values())
    return {"components": len(length), "largest_share": round(max(length.values()) / tot, 4)}


def review_city(pkg, city, cm):
    load = lambda name: json.load(open(os.path.join(pkg, cm["files"][name]["path"]), encoding="utf-8"))["features"]
    sg, cn, pl = load("segments"), load("connectors"), load("places_social")
    bb = cm["bbox"]
    rep = {"bbox": bb, "segments": len(sg), "connectors": len(cn), "places": len(pl)}

    # C1
    rep["C1_coord_order"] = {
        "segments": dict(Counter(coord_order(f["geometry"]["coordinates"], bb) for f in sg)),
        "connectors": dict(Counter(coord_order([f["geometry"]["coordinates"]], bb) for f in cn)),
        "places": dict(Counter(coord_order([f["geometry"]["coordinates"]], bb) for f in pl)),
        "bbox_order_ok": bb[0] < bb[2] and bb[1] < bb[3] and abs(bb[0]) > abs(bb[1])}

    # C2
    labels, ratios, absdiff = Counter(), [], []
    for f in sg:
        lab, o = classify_length(f["properties"]["k10_length_m"], f["geometry"]["coordinates"])
        labels[lab] += 1
        if o > 0:
            ratios.append(f["properties"]["k10_length_m"] / o - 1); absdiff.append(abs(f["properties"]["k10_length_m"] - o))
    rep["C2_length_vs_oracle"] = {"labels": dict(labels), "rel_diff_min": round(min(ratios), 5),
                                  "rel_diff_median": round(st.median(ratios), 5), "rel_diff_max": round(max(ratios), 5),
                                  "abs_diff_m_max": round(max(absdiff), 3),
                                  "total_k10_km": round(sum(f["properties"]["k10_length_m"] for f in sg) / 1000, 3),
                                  "total_oracle_km": round(sum(polyline_m(f["geometry"]["coordinates"]) for f in sg) / 1000, 3)}

    # C3
    cpos = {f["id"]: f["geometry"]["coordinates"] for f in cn}
    per_seg, at_unsorted, at_out, ends_missing, off = Counter(), 0, 0, 0, []
    for f in sg:
        cs = f["properties"]["connectors"] or []
        per_seg[len(cs)] += 1
        ats = [c["at"] for c in cs]
        at_unsorted += ats != sorted(ats)
        at_out += any(not 0 <= a <= 1 for a in ats)
        ends_missing += not (ats and min(ats) == 0 and max(ats) == 1)
        for c in cs:
            p = point_at_fraction(f["geometry"]["coordinates"], c["at"])
            x = cpos[c["connector_id"]]
            off.append(vincenty_m(p[0], p[1], x[0], x[1]))
    rep["C3_connectors"] = {"connectors_per_segment": dict(sorted(per_seg.items())),
                            "segments_with_3plus_connectors": sum(n for k, n in per_seg.items() if k >= 3),
                            "at_not_sorted": at_unsorted, "at_outside_0_1": at_out, "segments_without_both_ends": ends_missing,
                            "connector_vs_at_point_m": {"p50": round(q(off, .5), 3), "p99": round(q(off, .99), 3),
                                                        "max": round(max(off), 3), "gt_1m": sum(o > 1 for o in off)}}

    # C4
    geom = Counter(json.dumps([[round(c[0], 7), round(c[1], 7)] for c in f["geometry"]["coordinates"]]) for f in sg)
    geom_rev = Counter()
    for f in sg:
        cc = [[round(c[0], 7), round(c[1], 7)] for c in f["geometry"]["coordinates"]]
        geom_rev[json.dumps(min(cc, cc[::-1]))] += 1
    pair = Counter()
    rep_conn = 0
    for f in sg:
        cids = [c["connector_id"] for c in sorted(f["properties"]["connectors"] or [], key=lambda c: c["at"])]
        rep_conn += len(cids) != len(set(cids))
        for a, b in zip(cids, cids[1:]):
            pair[tuple(sorted((a, b)))] += 1
    rep["C4_duplicates"] = {"duplicate_segment_ids": sum(n - 1 for n in Counter(f["id"] for f in sg).values() if n > 1),
                            "identical_geometry_repeats": sum(n - 1 for n in geom.values() if n > 1),
                            "identical_geometry_repeats_either_direction": sum(n - 1 for n in geom_rev.values() if n > 1),
                            "parallel_edges_same_connector_pair": sum(n - 1 for n in pair.values() if n > 1),
                            "segments_repeating_a_connector": rep_conn}

    # C5
    naive_err, edges, sum_err, whole_overcount = [], 0, [], 0.0
    for f in sg:
        coords, p = f["geometry"]["coordinates"], f["properties"]
        cs = sorted(p["connectors"] or [], key=lambda c: c["at"])
        if len(cs) < 2:
            continue
        L = polyline_m(coords)
        tot = 0.0
        for a, b in zip(cs, cs[1:]):
            e = polyline_m(sub_polyline(coords, a["at"], b["at"]))
            tot += e; edges += 1
            naive_err.append(abs((b["at"] - a["at"]) * p["k10_length_m"] - e))
        sum_err.append(abs(tot - L))
        whole_overcount += (len(cs) - 2) * L  # if every edge got the whole segment length
    rep["C5_edges"] = {"edges": edges,
                       "naive_at_times_length_vs_oracle_m": {"p50": round(q(naive_err, .5), 3), "p99": round(q(naive_err, .99), 3),
                                                              "max": round(max(naive_err), 3)},
                       "sum_of_edges_vs_segment_m_max": round(max(sum_err), 4),
                       "overcount_km_if_whole_segment_length_per_edge": round(whole_overcount / 1000, 3)}

    # C6
    st_ = K10_STATED[city]
    allr = components(sg, lambda p: p["subtype"] == "road")
    nd = components(sg, lambda p: p["subtype"] == "road" and p["k10_foot_access"] != "denied")
    rep["C6_components"] = {"all_roads": allr, "foot_not_denied": nd, "k10_stated": st_,
                            "match": allr["components"] == st_["components"] and nd["components"] == st_["nd_components"]
                            and abs(allr["largest_share"] - st_["largest_share"]) <= 0.002
                            and abs(nd["largest_share"] - st_["nd_largest_share"]) <= 0.002}

    # C7
    def k10_edge(x, y):
        import math
        dx = min(x - bb[0], bb[2] - x) * 111320.0 * math.cos(math.radians(y))
        return min(dx, min(y - bb[1], bb[3] - y) * 111320.0)
    def oracle_edge(x, y):
        return min(vincenty_m(x, y, bb[0], y), vincenty_m(x, y, bb[2], y), vincenty_m(x, y, x, bb[1]), vincenty_m(x, y, x, bb[3]))
    d = [k10_edge(*f["geometry"]["coordinates"][:2]) - oracle_edge(*f["geometry"]["coordinates"][:2]) for f in pl]
    near_k10 = sum(k10_edge(*f["geometry"]["coordinates"][:2]) < 100 for f in pl)
    near_or = sum(oracle_edge(*f["geometry"]["coordinates"][:2]) < 100 for f in pl)
    rep["C7_place_to_bbox_edge"] = {"k10_minus_oracle_m_min": round(min(d), 2), "max": round(max(d), 2),
                                    "within_100m_k10": near_k10, "within_100m_oracle": near_or}

    # C8 injected errors on real geometry
    bad = {}
    picks = sorted(sg, key=lambda f: -f["properties"]["k10_length_m"])[:3]
    inj = [("km_not_m", picks[0], picks[0]["properties"]["k10_length_m"] / 1000),
           ("degrees_not_m", picks[1], planar_degrees(picks[1]["geometry"]["coordinates"])),
           ("latlon_swapped", picks[2], polyline_m([[c[1], c[0]] for c in picks[2]["geometry"]["coordinates"]]))]
    for want, f, val in inj:
        got = classify_length(val, f["geometry"]["coordinates"])[0]
        bad[want] = {"segment": f["id"], "injected_value": round(val, 6), "detected_as": got, "ok": got == want}
    rep["C8_injected_unit_errors"] = bad

    # C9
    errs, rel, node_off, worst = [], [], [], None
    for f in sg:
        coords = f["geometry"]["coordinates"]
        cs = sorted(f["properties"]["connectors"] or [], key=lambda c: c["at"])
        for a, b in zip(cs, cs[1:]):
            good = polyline_m(sub_polyline(coords, a["at"], b["at"]))
            planar = polyline_m(planar_sub(coords, a["at"], b["at"]))
            e = planar - good
            errs.append(abs(e))
            if good > 1:
                rel.append(abs(e) / good)
            if worst is None or abs(e) > abs(worst["diff_m"]):
                worst = {"segment": f["id"], "edge": [a["connector_id"], b["connector_id"]],
                         "geodesic_m": round(good, 2), "planar_split_m": round(planar, 2), "diff_m": round(e, 2)}
        for c in cs:
            pp = planar_point(coords, c["at"])
            x = cpos[c["connector_id"]]
            node_off.append(vincenty_m(pp[0], pp[1], x[0], x[1]))
    rep["C9_planar_at_split_vs_geodesic"] = {
        "edges": len(errs), "abs_diff_m": {"p50": round(q(errs, .5), 3), "p90": round(q(errs, .9), 3),
                                          "p99": round(q(errs, .99), 3), "max": round(max(errs), 2)},
        "edges_diff_gt_1m": sum(e > 1 for e in errs), "edges_diff_gt_5m": sum(e > 5 for e in errs),
        "edges_rel_diff_gt_1pct_of_ge1m": sum(r > .01 for r in rel),
        "node_position_vs_connector_m": {"p99": round(q(node_off, .99), 2), "max": round(max(node_off), 2),
                                         "gt_1m": sum(o > 1 for o in node_off)},
        "worst_edge": worst,
        "note": "segment totals are unaffected; only the split between edges of one segment shifts"}
    return rep


def main(pkg, out):
    man = json.load(open(os.path.join(pkg, "package_manifest.json"), encoding="utf-8"))
    rep = {"input": "K10 round 3 package, commit ea703f1ddd3a411430a981164a78a7dda64ec909, release " + man["release"],
           "data_kind": "observed_secondary (Overture/OSM), 2x2 km slice per city, not a city registry",
           "note": "lengths are geometric metres along OSM geometry, not walking time", "cities": {}}
    for city, cm in man["cities"].items():
        rep["cities"][city] = review_city(pkg, city, cm)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
