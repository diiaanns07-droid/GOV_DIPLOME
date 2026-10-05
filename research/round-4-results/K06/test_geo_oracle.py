"""Oracle tests (toy and textbook inputs, not city data). Run: python3 -m unittest -v test_geo_oracle"""
import math
import unittest
from geo_oracle import (A_WGS84, classify_length, coord_order, planar_degrees, point_at_fraction,
                        polyline_m, vincenty_m)


def dms(d, m, s, sign=1):
    return sign * (d + m / 60 + s / 3600)


class Oracle(unittest.TestCase):
    def test_1_zero_length(self):
        self.assertEqual(vincenty_m(71.43, 51.17, 71.43, 51.17), 0.0)
        self.assertEqual(polyline_m([[71.43, 51.17]]), 0.0)

    def test_2_equator_longitude_degree(self):
        # 1 deg along the equator = a * pi / 180 = 111 319.491 m
        self.assertAlmostEqual(vincenty_m(0, 0, 1, 0), A_WGS84 * math.pi / 180, delta=0.01)

    def test_3_meridian_degree(self):
        # WGS84 meridian arc from 0 to 1 deg latitude: 110 574.389 m (standard tables)
        self.assertAlmostEqual(vincenty_m(0, 0, 0, 1), 110574.389, delta=0.05)

    def test_4_vincenty_published_example(self):
        # Vincenty (1975) / Geoscience Australia: Flinders Peak -> Buninyong, 54 972.271 m.
        # The published value is on GRS80; GRS80 and WGS84 flattening differ in the 9th digit (<1 mm here).
        d = vincenty_m(dms(144, 25, 29.52440), dms(37, 57, 3.72030, -1),
                       dms(143, 55, 35.38390), dms(37, 39, 10.15610, -1))
        self.assertAlmostEqual(d, 54972.271, delta=0.002)

    def test_5_polyline_additivity_and_split(self):
        a, b, c = [71.42, 51.17], [71.43, 51.17], [71.43, 51.18]
        self.assertAlmostEqual(polyline_m([a, b, c]), vincenty_m(*a, *b) + vincenty_m(*b, *c), places=6)
        mid = point_at_fraction([a, c], 0.5)
        self.assertAlmostEqual(polyline_m([a, mid, c]), polyline_m([a, c]), delta=1e-3 * polyline_m([a, c]))

    def test_6_latlon_swap_detected(self):
        bbox = [71.418372, 51.163033, 71.447, 51.181]  # Astana square, [lon_min, lat_min, lon_max, lat_max]
        good = [[71.4424067, 51.1780043], [71.4414512, 51.1776408]]
        self.assertEqual(coord_order(good, bbox), "lonlat")
        self.assertEqual(coord_order([[p[1], p[0]] for p in good], bbox), "latlon")

    def test_7_unit_errors_classified(self):
        coords = [[71.4424067, 51.1780043], [71.4416664, 51.1777151], [71.4414512, 51.1776408]]
        o = polyline_m(coords)
        self.assertEqual(classify_length(o, coords)[0], "ok")
        self.assertEqual(classify_length(o / 1000, coords)[0], "km_not_m")
        self.assertEqual(classify_length(planar_degrees(coords), coords)[0], "degrees_not_m")
        self.assertEqual(classify_length(o * 1.2, coords)[0], "mismatch")

    def test_8_sphere_within_tolerance_both_axes(self):
        # haversine with mean radius (as K10) must stay inside REL_TOL vs the ellipsoid at 51 deg N
        R = 6371008.8
        def hav(lon1, lat1, lon2, lat2):
            p1, p2 = math.radians(lat1), math.radians(lat2)
            h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
            return 2 * R * math.asin(math.sqrt(h))
        for c in ([[71.42, 51.17], [71.44, 51.17]], [[71.42, 51.17], [71.42, 51.18]]):
            self.assertEqual(classify_length(hav(*c[0], *c[1]), c)[0], "ok")


if __name__ == "__main__":
    unittest.main()
