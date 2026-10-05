"""K06 round 4 REVIEW: small independent oracle for straight-line distance and polyline length.

Independent of K10's geo_util (sphere, haversine): uses Vincenty's inverse formula on the WGS84 ellipsoid.
Coordinates follow GeoJSON / EPSG:4326 order [lon, lat] unless stated otherwise. Standard library only.

Tolerance rationale: a mean-radius sphere differs from the ellipsoid by up to about -0.32 % east-west and
-0.05 % north-south at 42-51 deg N, so a sphere-based length is accepted when |rel diff| <= 0.5 % (+0.05 m
for rounding to centimetres). Anything far outside is classified against explicit error hypotheses.

A length here is a geometric (topological) length in metres along OSM/Overture geometry. It is NOT walking
time: no speed, crossings, waiting, slopes, winter or access rights are modelled.
"""
import math

A_WGS84 = 6378137.0
F_WGS84 = 1 / 298.257223563
B_WGS84 = A_WGS84 * (1 - F_WGS84)
REL_TOL = 0.005
ABS_TOL_M = 0.05


def vincenty_m(lon1, lat1, lon2, lat2, max_iter=200, eps=1e-12):
    """Geodesic distance in metres on WGS84 (Vincenty 1975 inverse). Raises on non-convergence."""
    if lon1 == lon2 and lat1 == lat2:
        return 0.0
    a, b, f = A_WGS84, B_WGS84, F_WGS84
    L = math.radians(lon2 - lon1)
    U1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    U2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    sU1, cU1, sU2, cU2 = math.sin(U1), math.cos(U1), math.sin(U2), math.cos(U2)
    lam = L
    for _ in range(max_iter):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.hypot(cU2 * sl, cU1 * sU2 - sU1 * cU2 * cl)
        if ss == 0:
            return 0.0
        cs = sU1 * sU2 + cU1 * cU2 * cl
        sig = math.atan2(ss, cs)
        sa = cU1 * cU2 * sl / ss
        c2a = 1 - sa * sa
        c2sm = cs - 2 * sU1 * sU2 / c2a if c2a else 0.0
        C = f / 16 * c2a * (4 + f * (4 - 3 * c2a))
        lam_prev = lam
        lam = L + (1 - C) * f * sa * (sig + C * ss * (c2sm + C * cs * (-1 + 2 * c2sm * c2sm)))
        if abs(lam - lam_prev) < eps:
            break
    else:
        raise ValueError("Vincenty did not converge (near-antipodal points)")
    u2 = c2a * (a * a - b * b) / (b * b)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    ds = B * ss * (c2sm + B / 4 * (cs * (-1 + 2 * c2sm * c2sm) - B / 6 * c2sm * (-3 + 4 * ss * ss) * (-3 + 4 * c2sm * c2sm)))
    return b * A * (sig - ds)


def polyline_m(coords):
    """Length in metres of a [lon, lat] polyline (extra z/m ordinates ignored)."""
    return sum(vincenty_m(p[0], p[1], q[0], q[1]) for p, q in zip(coords, coords[1:]))


def cumulative_m(coords):
    out = [0.0]
    for p, q in zip(coords, coords[1:]):
        out.append(out[-1] + vincenty_m(p[0], p[1], q[0], q[1]))
    return out


def point_at_fraction(coords, frac):
    """Point at a fraction 0..1 of the geodesic polyline length (linear interpolation inside a vertex pair)."""
    cum = cumulative_m(coords)
    target = max(0.0, min(1.0, frac)) * cum[-1]
    for i in range(1, len(cum)):
        if cum[i] >= target or i == len(cum) - 1:
            seg = cum[i] - cum[i - 1]
            t = (target - cum[i - 1]) / seg if seg else 0.0
            p, q = coords[i - 1], coords[i]
            return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]
    return list(coords[0][:2])


def planar_degrees(coords):
    """Euclidean length on raw lon/lat numbers (a classic unit error: degrees, not metres)."""
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(coords, coords[1:]))


def within_tol(claimed, oracle, rel_tol=REL_TOL, abs_tol=ABS_TOL_M):
    return abs(claimed - oracle) <= max(rel_tol * oracle, abs_tol)


def classify_length(claimed, coords, rel_tol=REL_TOL):
    """Compare a claimed length in metres with the oracle and name the most likely error.

    Returns (label, oracle_m). Labels: ok, km_not_m, degrees_not_m, latlon_swapped, mismatch.
    Hypotheses are tested explicitly; a value matching none is 'mismatch' (never silently accepted).
    """
    o = polyline_m(coords)
    if within_tol(claimed, o, rel_tol):
        return "ok", o
    if o > 0 and within_tol(claimed * 1000, o, rel_tol):
        return "km_not_m", o
    pdeg = planar_degrees(coords)
    if pdeg > 0 and abs(claimed - pdeg) <= rel_tol * pdeg + 1e-9:
        return "degrees_not_m", o
    try:
        sw = polyline_m([[p[1], p[0]] for p in coords])
        if within_tol(claimed, sw, rel_tol) and not within_tol(sw, o, rel_tol):
            return "latlon_swapped", o
    except ValueError:
        pass
    return "mismatch", o


def coord_order(coords, bbox):
    """'lonlat' if points fall in bbox [lon_min, lat_min, lon_max, lat_max] as given, 'latlon' if only
    after swapping, otherwise 'outside'. A wide margin (0.5 deg) keeps segments crossing the edge."""
    m = 0.5
    def inside(x, y):
        return bbox[0] - m <= x <= bbox[2] + m and bbox[1] - m <= y <= bbox[3] + m
    if all(inside(p[0], p[1]) for p in coords):
        return "lonlat"
    if all(inside(p[1], p[0]) for p in coords):
        return "latlon"
    return "outside"
