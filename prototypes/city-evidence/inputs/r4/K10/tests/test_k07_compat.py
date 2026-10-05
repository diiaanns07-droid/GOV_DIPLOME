"""K10 round-4 REVIEW tests: K10 round-3 package vs K07 round-3 graph_check.

Run (Python 3.12, K07 pins networkx 3.6.1, shapely 2.1.2, pyproj 3.8.0):
    python -m unittest discover -s research/round-4-results/K10/tests -v
Real-data tests use the committed K10 package (sha-checked). Fixtures marked SYNTHETIC are tiny
hand-made networks at 0..0.02 deg (or 51 deg N for the `at` test); they test rules, not a city.
"""
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import substring

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "scripts"))
import k10_k07_adapter as A  # noqa: E402

MAN = json.loads((HERE / "inputs/MANIFEST.json").read_text(encoding="utf-8"))
GC_PATH = HERE / "inputs/K07/scripts/graph_check.py"
assert hashlib.sha256(GC_PATH.read_bytes()).hexdigest() == next(
    f["sha256"] for f in MAN["files"] if f["copy"] == "inputs/K07/scripts/graph_check.py"), "K07 input changed"
_spec = importlib.util.spec_from_file_location("k07_graph_check", GC_PATH)
GC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GC)

CITIES = ("shymkent", "astana")
DATA = {c: A.load_package(c) for c in CITIES}


def seg(i, coords, conns, access=None, flags=None, levels=None, status=None, crosses=False):
    """SYNTHETIC segment in K10 package layout (None = field absent)."""
    st = status or "unknown"  # K10 stores its own classification; fixtures default to 'unknown'
    return {"type": "Feature", "id": i, "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"overture_id": i, "connectors": [{"connector_id": c, "at": a} for c, a in conns],
                           "access_restrictions": access, "road_flags": flags, "level_rules": levels,
                           "k10_foot_access": st, "k10_crosses_bbox_edge": crosses}}


class ActualConnectors(unittest.TestCase):
    """Real data: connectors referenced by segments exist and sit where Overture `at` says."""

    def test_referenced_connectors_exist_and_match_geodesic_at(self):
        for city in CITIES:
            d = DATA[city]
            pos = {f["id"]: f["geometry"]["coordinates"] for f in d["connectors"]["features"]}
            worst = 0.0
            for f in d["segments"]["features"]:
                for c in f["properties"]["connectors"]:
                    self.assertIn(c["connector_id"], pos)
                    x, y = A.point_at(f, c["at"])
                    px, py = pos[c["connector_id"]]
                    worst = max(worst, A.GEOD.inv(x, y, px, py)[2])
            with self.subTest(city=city):
                self.assertLess(worst, 0.5, "geodesic linear referencing must reproduce connector geometry")

    def test_k07_planar_interpolation_deviates(self):
        """FINDING: K07 places nodes with shapely interpolate(normalized=True) in degrees -> metres off."""
        for city in CITIES:
            d = DATA[city]
            pos = {f["id"]: f["geometry"]["coordinates"] for f in d["connectors"]["features"]}
            worst = 0.0
            for f in d["segments"]["features"]:
                g = shape(f["geometry"])
                for c in f["properties"]["connectors"]:
                    q = g.interpolate(c["at"], normalized=True)
                    worst = max(worst, A.GEOD.inv(q.x, q.y, *pos[c["connector_id"]])[2])
            with self.subTest(city=city):
                self.assertGreater(worst, 5.0)


class SplitByAt(unittest.TestCase):
    def test_real_segments_sorted_full_span(self):
        for city in CITIES:
            for f in DATA[city]["segments"]["features"]:
                ats = [c["at"] for c in f["properties"]["connectors"]]
                self.assertEqual(ats, sorted(ats))
                self.assertEqual((ats[0], ats[-1]), (0, 1))

    def test_real_split_preserves_segment_length(self):
        for city in CITIES:
            for f in DATA[city]["segments"]["features"][:300]:
                total = A.GEOD.geometry_length(shape(f["geometry"]))
                self.assertAlmostEqual(sum(e[2] for e in A.split_edges(f)), total, delta=0.01)

    def test_synthetic_split_uses_geodesic_fraction(self):
        """SYNTHETIC at 51 deg N: L-shaped line, connector at at=0.5 must be at half the WGS84 length."""
        f = seg("s", [[71.40, 51.10], [71.42, 51.10], [71.42, 51.11]], [("a", 0), ("m", 0.5), ("b", 1)])
        e = A.split_edges(f)
        self.assertEqual([(u, v) for u, v, _ in e], [("a", "m"), ("m", "b")])
        self.assertAlmostEqual(e[0][2], e[1][2], places=6)
        k07_first = A.GEOD.geometry_length(substring(shape(f["geometry"]), 0, 0.5, normalized=True))
        self.assertGreater(abs(k07_first - e[0][2]), 50, "planar-degree split differs by >50 m here")

    def test_malformed_connectors_rejected(self):
        with self.assertRaises(ValueError):
            A.split_edges(seg("bad", [[0, 0], [0.001, 0]], [("b", 1), ("a", 0)]))
        with self.assertRaises(ValueError):
            A.split_edges(seg("one", [[0, 0], [0.001, 0]], [("a", 0)]))


class BridgeWithoutSharedConnector(unittest.TestCase):
    def test_synthetic_bridge_not_joined(self):
        """SYNTHETIC: bridge crosses a street at (0.001,0) with no shared connector -> no link."""
        fc = {"features": [
            seg("street", [[0, 0], [0.002, 0]], [("c1", 0), ("c2", 1)]),
            seg("bridge", [[0.001, -0.001], [0.001, 0.001]], [("c3", 0), ("c4", 1)],
                flags=[{"values": ["is_bridge"]}], levels=[{"value": 1}])]}
        adj = A.build_graph(fc, "topology")
        self.assertIsNone(A.shortest(adj, "c1", "c3")[0])
        self.assertTrue(shape(fc["features"][0]["geometry"]).crosses(shape(fc["features"][1]["geometry"])))

    def test_real_crossings_without_shared_connector_are_not_edges(self):
        for city in CITIES:
            res, (G, _edge, _proj) = GC.check(A.to_k07(city, DATA[city]), city)
            feats = DATA[city]["segments"]["features"]
            lines = [shape(f["geometry"]) for f in feats]
            conn = [{c["connector_id"] for c in f["properties"]["connectors"]} for f in feats]
            pairs = [(i, j) for i in range(len(lines)) for j in range(i + 1, len(lines))
                     if not (conn[i] & conn[j]) and lines[i].crosses(lines[j])]
            by_id = {f["id"]: conn[k] for k, f in enumerate(feats)}
            with self.subTest(city=city):
                self.assertEqual(len(pairs), res["crossings_without_shared_connector_not_joined"])
                # every K07 edge joins two connectors of its own segment -> no join by geometric crossing
                self.assertFalse([(u, v) for u, v, d in G.edges(data=True) if not {u, v} <= by_id[d["seg"]]])
                for i, j in pairs:  # crossing pairs are never joined by an edge of either crossing segment
                    self.assertFalse([1 for a in conn[i] for b in conn[j] if G.has_edge(a, b)
                                      and G.get_edge_data(a, b)[0]["seg"] in (feats[i]["id"], feats[j]["id"])])


class ConditionalAndUnknown(unittest.TestCase):
    def test_adapter_never_promotes(self):
        for city in CITIES:
            fc = A.to_k07(city, DATA[city])
            for f0, f1 in zip(DATA[city]["segments"]["features"], fc["features"]):
                self.assertIs(f0, f1)  # properties untouched (None stays None)
            sts = [A.strict_foot(f["properties"]) for f in fc["features"]]
            explicit = sum(1 for f in fc["features"] if f["properties"]["k10_foot_access"] == "allowed")
            self.assertEqual(sts.count("allowed"), explicit)

    def test_k07_foot_rule_promotes_conditional_to_allowed(self):
        """FINDING: K07 foot_rule -> 'allowed' for vehicle-oneway rules, mode-specific vehicle denials and []."""
        oneway = [{"access_type": "denied", "when": {"heading": "backward"}}]
        motor_only = [{"access_type": "denied", "when": {"mode": ["motor_vehicle"]}}]
        self.assertEqual(GC.foot_rule(oneway)[0], "allowed")
        self.assertEqual(GC.foot_rule(motor_only)[0], "allowed")
        self.assertEqual(GC.foot_rule([])[0], "allowed")
        self.assertEqual(GC.foot_rule(None)[0], "unknown")
        counts = {}
        for city in CITIES:
            counts[city] = sum(1 for f in DATA[city]["segments"]["features"]
                               if f["properties"]["k10_foot_access"] == "conditional"
                               and GC.foot_rule(f["properties"]["access_restrictions"])[0] == "allowed")
        self.assertEqual(counts, {"shymkent": 114, "astana": 166})

    def test_strict_mode_does_not_establish_walkability(self):
        for city in CITIES:
            strict = A.build_graph(DATA[city]["segments"], "strict_foot")
            n_allowed = sum(1 for f in DATA[city]["segments"]["features"] if f["properties"]["k10_foot_access"] == "allowed")
            with self.subTest(city=city):
                self.assertEqual(len({sid for u in strict for (_d, sid, _s) in strict[u].values()}), n_allowed)


class PathBeyondEdge(unittest.TestCase):
    def _fixture(self):
        """SYNTHETIC: clip [0,0,0.01,0.01] (~1.1 km). Two dead-end branches leave the clip; their outer
        connectors are ~390 m outside and no node lies within 200 m of the boundary."""
        fc = {"type": "FeatureCollection", "name": "SYNTHETIC edge fixture",
              "k07_clip": {"bbox": [0, 0, 0.01, 0.01], "selection": "all_segments_intersecting_clip"},
              "features": [
                  seg("a", [[0.004, 0.005], [0.004, 0.0135]], [("a_in", 0), ("a_out", 1)], crosses=True),
                  seg("b", [[0.006, 0.005], [0.006, 0.0135]], [("b_in", 0), ("b_out", 1)], crosses=True)]}
        conns = {"features": [{"id": n, "properties": {"k10_inside_bbox": n.endswith("_in")}} for n in
                              ("a_in", "a_out", "b_in", "b_out")]}
        return fc, {"segments": fc, "connectors": conns}

    def test_k07_misses_edge_when_no_node_within_200m(self):
        """FINDING: K07 edge rule (node within 200 m of clip) labels this interior 'no_path_in_graph'."""
        fc, _ = self._fixture()
        _res, (G, edge, proj) = GC.check(fc, "synthetic_edge")
        rows = GC.compare(G, edge, proj, (0.004, 0.0051), [{"id": "b", "lon": 0.006, "lat": 0.0051}], threshold_m=500)
        self.assertEqual(len(edge), 0)
        self.assertEqual(rows[0]["status"], "no_path_in_graph")

    def test_adapter_marks_edge_from_data_flags(self):
        fc, pkg = self._fixture()
        adj = A.build_graph(fc, "topology")
        r = A.reach(adj, A.edge_nodes(pkg), "a_in", "b_in")
        self.assertEqual(r["status"], "no_path_in_graph_edge_of_clip")

    def test_real_edge_nodes_from_data_flags(self):
        """Real data: the square cuts the graph; cut nodes come from K10 flags (outside connectors, edge segments)."""
        for city in CITIES:
            adj = A.build_graph(DATA[city]["segments"], "topology")
            edge = A.edge_nodes(DATA[city])
            comps, seen = [], set()
            for n in adj:
                if n not in seen:
                    c = A.component_of(adj, n)
                    seen |= c
                    comps.append(c)
            comps.sort(key=len, reverse=True)
            with self.subTest(city=city):
                self.assertTrue(edge & comps[0])
                self.assertGreater(len(edge), 0)


class TopologyModeOnRealData(unittest.TestCase):
    def test_link_exists_but_permission_not_established(self):
        """Real data: two social places snapped to nearest connector are linked in topology mode;
        permission along the path is not established (unknown/conditional segments on it)."""
        for city in CITIES:
            d = DATA[city]
            adj = A.build_graph(d["segments"], "topology")
            st = {f["id"]: A.strict_foot(f["properties"]) for f in d["segments"]["features"]}
            nodes = [(f["id"], f["geometry"]["coordinates"]) for f in d["connectors"]["features"] if f["id"] in adj]
            places = sorted(d["places_social"]["features"], key=lambda f: f["id"])[:2]

            def snap(p):
                x, y = p["geometry"]["coordinates"]
                return min(nodes, key=lambda n: A.GEOD.inv(x, y, *n[1])[2])[0]

            r = A.reach(adj, A.edge_nodes(d), snap(places[0]), snap(places[1]), st)
            with self.subTest(city=city):
                self.assertEqual(r["status"], "ok")
                self.assertEqual(r["pedestrian_permission"], "not_established")


class FrameCompatibility(unittest.TestCase):
    def test_package_is_not_the_requested_6x6_frame(self):
        for city in CITIES:
            clip = A.to_k07(city, DATA[city])["k07_clip"]
            w, h = clip["frame_km_w_h"]
            with self.subTest(city=city):
                self.assertLess(max(w, h), 2.1)
                self.assertFalse(clip["k07_requested_clip_6x6km_satisfied"])
                self.assertLess(clip["share_of_k07_requested_clip_covered"], 0.2)
        self.assertEqual(A.to_k07("astana", DATA["astana"])["k07_clip"]["share_of_k07_requested_core_covered"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
