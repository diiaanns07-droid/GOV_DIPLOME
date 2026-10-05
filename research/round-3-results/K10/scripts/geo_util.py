"""Stdlib-only geometry helpers shared by download.py and offline_check.py."""
import math

R_EARTH_M = 6371008.8


def haversine_m(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_M * math.asin(math.sqrt(a))


def line_length_m(coords):
    return sum(haversine_m(*a[:2], *b[:2]) for a, b in zip(coords, coords[1:]))


def point_in_bbox(x, y, bb):
    return bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]


def dist_to_bbox_edge_m(x, y, bb):
    """Distance from a point inside bb to the nearest bbox edge (metres, local approximation)."""
    dx = min(x - bb[0], bb[2] - x) * 111320.0 * math.cos(math.radians(y))
    dy = min(y - bb[1], bb[3] - y) * 111320.0
    return min(dx, dy)
