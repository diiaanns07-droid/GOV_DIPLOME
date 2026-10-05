"""K10 round-4 REVIEW: small adapter from the K10 round-3 package to the K07 round-3 graph_check input.

What it does (and does not):
  * verifies package files against research/round-3-results/K10/package_manifest.json (sha256);
  * returns the segments FeatureCollection with a top-level ``k07_clip`` header that K07 reads, stating the
    real 2x2 km K10 square and that the 6x6 km frame requested by K07 is NOT satisfied;
  * keeps every property as-is: ``access_restrictions``/``road_flags``/``level_rules`` stay ``None`` when absent;
    no value is ever turned into "allowed";
  * builds edges strictly from connector ids, split by ``at`` with Overture's geodesic linear referencing:
    edge length = (at_b - at_a) * geodesic segment length; node position = actual connector geometry;
  * two graph modes: ``topology`` (all non-denied segments: shows that a link exists in the OSM/Overture graph)
    and ``strict_foot`` (only segments with explicit pedestrian permission). Neither proves real walkability.
Deps: pyproj (same as K07). Usage: see tests/test_k07_compat.py and scripts/run_review.py.
"""
import hashlib
import heapq
import json
from pathlib import Path

from pyproj import Geod

GEOD = Geod(ellps="WGS84")
REPO = Path(__file__).resolve().parents[4]
PKG = REPO / "research/round-3-results/K10"
K10_COMMIT = "ea703f1ddd3a411430a981164a78a7dda64ec909"

# Frames requested by K07 (research/round-3-results/K07/K10_REQUEST.md @ 6778ded), copied verbatim.
K07_REQUEST = {
    "shymkent": {"core_bbox": [69.57896, 42.29927, 69.62748, 42.33528], "clip_bbox": [69.56683, 42.29027, 69.63961, 42.34428]},
    "astana": {"core_bbox": [71.38389, 51.12029, 71.44104, 51.15624], "clip_bbox": [71.36960, 51.11130, 71.45533, 51.16523]},
}


class PackageMismatch(RuntimeError):
    pass


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_package(city, pkg=PKG):
    man = json.loads((pkg / "package_manifest.json").read_text(encoding="utf-8"))
    cm = man["cities"][city]
    out = {"bbox": cm["bbox"], "release": man["release"]}
    for layer in ("segments", "connectors", "places_social"):
        meta = cm["files"][layer]
        path = pkg / meta["path"]
        if _sha(path) != meta["sha256"]:
            raise PackageMismatch(f"{city}/{layer}: sha256 differs from package_manifest.json")
        out[layer] = json.loads(path.read_text(encoding="utf-8"))
        out[layer + "_sha256"] = meta["sha256"]
    return out


def bbox_km(bb):
    w = GEOD.inv(bb[0], (bb[1] + bb[3]) / 2, bb[2], (bb[1] + bb[3]) / 2)[2] / 1000
    h = GEOD.inv((bb[0] + bb[2]) / 2, bb[1], (bb[0] + bb[2]) / 2, bb[3])[2] / 1000
    return round(w, 3), round(h, 3)


def overlap_share(a, b):
    """Share of bbox a's degree-area covered by bbox b."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return round(ix * iy / ((a[2] - a[0]) * (a[3] - a[1])), 4)


def to_k07(city, pkg_data):
    """Segments FeatureCollection in the K07 input layout; properties are not altered."""
    bb = pkg_data["bbox"]
    req = K07_REQUEST[city]
    fc = dict(pkg_data["segments"])
    fc["k07_clip"] = {
        "bbox": bb,
        "core_bbox": None,
        "selection": "all_segments_intersecting_clip",
        "source": f"K10 round-3 package @ {K10_COMMIT}, data/{city}/segments.geojson",
        "frame_km_w_h": bbox_km(bb),
        "k07_requested_clip_6x6km_satisfied": False,
        "k07_requested_clip_bbox": req["clip_bbox"],
        "share_of_k07_requested_clip_covered": overlap_share(req["clip_bbox"], bb),
        "share_of_k07_requested_core_covered": overlap_share(req["core_bbox"], bb),
        "note": "2x2 km K10 square is complete for its own query only; it is not the 6x6 km frame K07 asked for.",
    }
    return fc


# --------------------------------------------------------------------------- permissions (never promotes)
def strict_foot(props):
    """K10 status as stored (allowed/denied/conditional/unknown); only 'allowed' is traversable in strict mode."""
    return props.get("k10_foot_access", "unknown")


# --------------------------------------------------------------------------- exact split by `at`
def split_edges(feature):
    """Edges (u, v, length_m) between consecutive connectors by `at`; raises on malformed connector lists."""
    p = feature["properties"]
    conns = p.get("connectors")
    if not isinstance(conns, list) or len(conns) < 2:
        raise ValueError(f"{feature.get('id')}: needs >=2 connectors with ids")
    ats = [c["at"] for c in conns]
    if ats != sorted(ats) or ats[0] < 0 or ats[-1] > 1:
        raise ValueError(f"{feature.get('id')}: connectors not sorted by at or at outside [0,1]")
    coords = feature["geometry"]["coordinates"]
    total = sum(GEOD.inv(a[0], a[1], b[0], b[1])[2] for a, b in zip(coords, coords[1:]))
    return [(a["connector_id"], b["connector_id"], (b["at"] - a["at"]) * total) for a, b in zip(conns, conns[1:])]


def point_at(feature, at):
    """Geodesic linear referencing (Overture semantics): position at fraction `at` of the WGS84 length."""
    coords = feature["geometry"]["coordinates"]
    cum = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum.append(cum[-1] + GEOD.inv(a[0], a[1], b[0], b[1])[2])
    t = at * cum[-1]
    for i in range(len(coords) - 1):
        if t <= cum[i + 1] or i == len(coords) - 2:
            span = cum[i + 1] - cum[i]
            f = 0.0 if span == 0 else min(max((t - cum[i]) / span, 0.0), 1.0)
            a, b = coords[i], coords[i + 1]
            return [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])]
    return list(coords[-1])


# --------------------------------------------------------------------------- graph and edge semantics
def build_graph(segments_fc, mode):
    """Undirected weighted adjacency {node: {nbr: (length_m, segment_id, foot_status)}}.

    mode='topology'   : every segment except explicit 'denied' (shows a link exists in the data graph)
    mode='strict_foot': only segments with explicit pedestrian permission ('allowed')
    """
    if mode not in ("topology", "strict_foot"):
        raise ValueError(mode)
    adj = {}
    for f in segments_fc["features"]:
        st = strict_foot(f["properties"])
        if st == "denied" or (mode == "strict_foot" and st != "allowed"):
            continue
        for u, v, d in split_edges(f):
            for a, b in ((u, v), (v, u)):
                cur = adj.setdefault(a, {}).get(b)
                if cur is None or d < cur[0]:
                    adj[a][b] = (d, f["id"], st)
    return adj


def shortest(adj, src, dst):
    """Dijkstra; returns (length_m, [segment ids]) or (None, [])."""
    if src not in adj or dst not in adj:
        return None, []
    dist, prev, pq = {src: 0.0}, {}, [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist[u]:
            continue
        for v, (w, sid, _st) in adj[u].items():
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v], prev[v] = nd, (u, sid)
                heapq.heappush(pq, (nd, v))
    if dst not in dist:
        return None, []
    path, n = [], dst
    while n != src:
        n, sid = prev[n]
        path.append(sid)
    return dist[dst], path[::-1]


def component_of(adj, start):
    seen, stack = {start}, [start]
    while stack:
        u = stack.pop()
        for v in adj.get(u, {}):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def edge_nodes(pkg_data):
    """Graph-cut nodes by data, not by distance: connectors outside the square and connectors of
    segments that cross the square boundary."""
    out = {f["id"] for f in pkg_data["connectors"]["features"] if not f["properties"]["k10_inside_bbox"]}
    for f in pkg_data["segments"]["features"]:
        if f["properties"]["k10_crosses_bbox_edge"]:
            out.update(c["connector_id"] for c in f["properties"]["connectors"])
    return out


def reach(adj, edge, src, dst, statuses_by_seg=None):
    """Status in THIS graph: ok / no_path_in_graph_edge_of_clip / no_path_in_graph (never 'unreachable')."""
    d, path = shortest(adj, src, dst)
    if d is not None:
        res = {"status": "ok", "network_m": round(d, 1), "segments_on_path": len(path)}
        if statuses_by_seg is not None:
            sts = [statuses_by_seg[s] for s in path]
            res["foot_status_on_path"] = {s: sts.count(s) for s in sorted(set(sts))}
            res["pedestrian_permission"] = "established" if set(sts) == {"allowed"} else "not_established"
        return res
    touches = bool(edge & (component_of(adj, src) | component_of(adj, dst)))
    return {"status": "no_path_in_graph_edge_of_clip" if touches else "no_path_in_graph", "network_m": None}
