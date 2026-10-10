"""R05 · 3D-превью: данные модуля из настоящего OSM и допуски точности CONTRACT §8.

Запуск из корня репозитория:  python -m unittest discover -s tests/civic/R05/build3d -p "test_*.py"
"""

import importlib.util
import json
import math
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DATA = os.path.join(REPO, "web", "civic", "build3d", "data")
GRAPH = os.path.join(REPO, "engine", "civic_scenarios", "graphs", "osm-astana-walking-20260506.graph.json")
GEOFENCE = os.path.join(REPO, "data", "civic", "astana", "geofence.json")

spec = importlib.util.spec_from_file_location("make_fixtures", os.path.join(HERE, "make_fixtures.py"))
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def inside(x, y, ring):
    c = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def dist_to_line_m(p, line):
    """Расстояние от точки до ломаной (lon/lat) в метрах — локальные метры вокруг точки."""
    best = float("inf")
    pts = [mf.to_local(p, q) for q in line]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, (-ax * dx - ay * dy) / L2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = load(GRAPH)
        cls.by_id = {e["id"]: e for e in cls.graph["edges"]}
        cls.geofence = load(GEOFENCE)
        cls.streets = load(os.path.join(DATA, "nura-streets.json"))
        cls.districts = load(os.path.join(DATA, "astana-districts.json"))
        cls.proposals = load(os.path.join(DATA, "proposals.fixture.json"))

    def in_astana(self, lon, lat):
        return any(inside(lon, lat, ring) for poly in self.geofence["polygons"] for ring in poly["rings"])

    def test_regeneration_is_byte_identical(self):
        tmp = tempfile.mkdtemp(prefix="r05b3d-")
        try:
            mf.main(tmp)
            for name in ("nura-streets.json", "astana-districts.json", "demo-basemap.json", "proposals.fixture.json",
                         "astana-existing.json"):
                with open(os.path.join(tmp, name), "rb") as a, open(os.path.join(DATA, name), "rb") as b:
                    self.assertEqual(a.read(), b.read(), name + " отличается от генератора")
        finally:
            shutil.rmtree(tmp)

    def test_streets_are_real_graph_edges(self):
        names = self.streets["names"]
        self.assertGreater(len(self.streets["edges"]), 500)
        for eid, ni, _f, _t, length, geom in self.streets["edges"]:
            src = self.by_id[eid]  # id как у R12 /targets: osm-w<way>-<n>
            self.assertEqual(names[ni], src["name"])
            self.assertEqual(len(geom), len(src["geometry"]))
            for (x, y), (sx, sy) in zip(geom, src["geometry"]):
                self.assertLess(abs(x - sx), 1.1e-6)
                self.assertLess(abs(y - sy), 1.1e-6)
            self.assertAlmostEqual(length, src["length_m"], delta=0.01)

    def test_street_coordinates_inside_astana(self):
        for _eid, _ni, _f, _t, _l, geom in self.streets["edges"]:
            for lon, lat in (geom[0], geom[-1]):
                self.assertTrue(self.in_astana(lon, lat), (lon, lat))

    def test_simplified_districts_keep_original_vertices(self):
        original = {}  # у одного района может быть несколько полигонов (Алматы, Байконур)
        for p in self.geofence["polygons"]:
            bucket = original.setdefault(p["district_id"], set())
            bucket.update(tuple(round(v, 6) for v in pt) for ring in p["rings"] for pt in ring)
        for d in self.districts["districts"]:
            for ring in d["rings"]:
                self.assertGreaterEqual(len(ring), 4)
                for pt in ring:
                    self.assertIn(tuple(pt), original[d["id"]])

    def test_lighting_follows_street_within_5m(self):
        light = [p for p in self.proposals["proposals"] if p["kind"] == "lighting"]
        self.assertTrue(light)
        for p in light:
            edges = [self.by_id[i]["geometry"] for i in p["target"]["ids"]]
            self.assertEqual(p["target"]["kind"], "segment")
            coords = p["geometry"]["coordinates"]
            # Вершины и точки через ~5 м между ними — не дальше 5 м от формы рёбер (CONTRACT §8.3).
            for a, b in zip(coords, coords[1:]):
                n = max(1, int(math.hypot(*mf.to_local(a, b)) // 5))
                for k in range(n + 1):
                    q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                    d = min(dist_to_line_m(q, g) for g in edges)
                    self.assertLess(d, 5.0, (p["id"], q, d))
                    self.assertTrue(self.in_astana(*q))

    def test_stop_within_60m_of_street(self):
        for p in self.proposals["proposals"]:
            if p["kind"] != "stop":
                continue
            c = p["geometry"]["coordinates"]
            d = min(dist_to_line_m(c, e["geometry"]) for e in self.graph["edges"]
                    if e.get("name") and abs(e["geometry"][0][0] - c[0]) < 0.01 and abs(e["geometry"][0][1] - c[1]) < 0.01)
            self.assertLess(d, 60.0)
            self.assertGreater(d, 3.0, "остановка не стоит на оси дороги")
            self.assertTrue(self.in_astana(*c))

    def test_yard_examples_fit_inside_real_yards(self):
        """Примеры сквера и площадки стоят ЦЕЛИКОМ внутри настоящих дворов OSM (UX_REVIEW R11, день 3 #20)."""
        ex = load(os.path.join(DATA, "astana-existing.json"))
        yards = {y[0]: y[4] for y in ex["yards"]}
        sizes = {"square": (40, 30), "playground": (24, 18), "sports": (32, 20), "stop": (12, 4.5)}
        found = 0
        for p in self.proposals["proposals"]:
            t = p.get("target") or {}
            if t.get("kind") != "area":
                continue
            found += 1
            ring = yards[t["id"]]
            w, d = sizes[p["kind"]]
            c = p["geometry"]["coordinates"]
            a = math.radians(-p["rotation_deg"])
            local_ring = [mf.to_local(c, q) for q in ring]
            for sx in (-1, 1):
                for sy in (-1, 1):
                    x, y = sx * w / 2, sy * d / 2
                    xr, yr = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
                    self.assertTrue(mf.point_in_ring_xy(xr, yr, local_ring), (p["id"], sx, sy))
        self.assertGreaterEqual(found, 2)

    def test_proposals_contract_shape(self):
        for p in self.proposals["proposals"]:
            for key in ("id", "kind", "geometry", "status", "votes_up", "votes_down"):
                self.assertIn(key, p)
            self.assertEqual(p["status"], "proposal")
            self.assertIs(p["demo"], True, "примеры помечены demo")
            self.assertIn(p["kind"], ("square", "playground", "sports", "stop", "lighting"))

    def test_existing_objects_are_real_osm(self):
        ex = load(os.path.join(DATA, "astana-existing.json"))
        self.assertEqual(ex["evidence_type"], "real (OSM)")
        city = mf.city_polygons()

        def inside(el):
            x, y = mf.center(el)
            return mf.in_city((mf.r(x), mf.r(y)), city)

        # Остановки = остановки ∪ платформы без повторов по (type, id), как требует README LOCAL-1,
        # без ж/д и трамвайных платформ (R10 B-007) и без объектов вне районов Астаны (R10 B-008).
        stops, rail = {}, set()
        for name in ("bus_stops", "platforms"):
            for e in mf.osm_elements(name):
                stops[(e["type"], e["id"])] = e
                if mf.is_rail(e):
                    rail.add("osm-%s-%d" % (e["type"], e["id"]))
        self.assertGreater(len(rail), 0, "в выгрузке LOCAL-1 есть ж/д платформы — фильтр проверяется на деле")
        expected = [e for e in stops.values() if not mf.is_rail(e) and inside(e)]
        self.assertEqual(len(ex["points"]["stop"]), len(expected))
        self.assertFalse(rail & {row[2] for row in ex["points"]["stop"]}, "ж/д платформа записана как остановка")
        for kind, name in (("playground", "playgrounds"), ("sports", "pitches"), ("lamp", "street_lamps")):
            self.assertEqual(len(ex["points"][kind]), len([e for e in mf.osm_elements(name) if inside(e)]), kind)
        # Все координаты файла — внутри Астаны (CONTRACT §8.3; так же проверяет R10 accuracy.py).
        outside = [row[:3] for rows in ex["points"].values() for row in rows if not mf.in_city(row[:2], city)]
        outside += [y[0] for y in ex["yards"] for p in y[4] if not mf.in_city(p, city)]
        self.assertEqual(outside, [], "объекты вне границы Астаны")
        lo, la, hi_lo, hi_la = 71.2079 - 0.05, 50.9206 - 0.05, 71.7953 + 0.05, 51.3612 + 0.05
        for kind, rows in ex["points"].items():
            for row in rows:
                self.assertRegex(row[2], r"^osm-(node|way|relation)-\d+$")
                self.assertTrue(lo <= row[0] <= hi_lo and la <= row[1] <= hi_la, (kind, row[:3]))
        for y in ex["yards"]:
            self.assertRegex(y[0], r"^yard-\d+$")
            self.assertGreaterEqual(len(y[4]), 4)
            self.assertEqual(y[4][0], y[4][-1], "кольцо двора замкнуто")

    def test_street_names_kk_only_from_osm(self):
        # Казахские названия улиц — только name:kk из OSM (без машинного перевода), параллельно names.
        names, kk = self.streets["names"], self.streets["names_kk"]
        self.assertEqual(len(kk), len(names))
        self.assertEqual(kk[names.index("улица Сыганак")], "Сығанақ көшесі")
        self.assertEqual(kk[names.index("проспект Туран")], "Тұран даңғылы")
        import gzip
        with gzip.open(mf.OSM_WALKING, "rt", encoding="utf-8") as fh:
            osm_kk = {(el.get("tags") or {}).get("name:kk") for el in json.load(fh)["elements"] if el.get("type") == "way"}
        for name in kk:
            if name is not None:
                self.assertIn(name, osm_kk, "название не из OSM")
        self.assertEqual(self.streets["names_kk_source"]["found"], sum(1 for x in kk if x))

    def test_license_and_attribution(self):
        for data in (self.streets, self.proposals):
            self.assertEqual(data["source"]["license"], "ODbL-1.0")
            self.assertIn("OpenStreetMap", data["source"]["attribution"])


if __name__ == "__main__":
    unittest.main()
