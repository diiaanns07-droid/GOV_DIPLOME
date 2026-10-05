"""K03 round 4 REVIEW: общие функции проверки boundary_validator (round 3, @44585de).

Только чтение. round-3 файлы не меняются: исправление (v2) применяется в памяти из fix_spec.json.
"""
import difflib
import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R3 = ROOT / 'research/round-3-results/K03'
SNAPSHOT_SHA = '44585de31be01dd131ecb7677c462fc85b4d4cc4'
V1_PATH = R3 / 'boundary_validator.py'
FIX_SPEC = HERE / 'fix_spec.json'
PATCH = HERE / 'patches/k03_assign_v2.patch'

if str(R3) not in sys.path:
    sys.path.insert(0, str(R3))

from pyproj import Geod, Transformer  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402
from shapely.ops import linemerge, unary_union  # noqa: E402

TO_UTM = Transformer.from_crs('EPSG:4326', 'EPSG:32642', always_xy=True).transform
TO_LL = Transformer.from_crs('EPSG:32642', 'EPSG:4326', always_xy=True).transform
GEOD = Geod(ellps='WGS84')


def load_v1():
    spec = importlib.util.spec_from_file_location('k03_bv_v1', V1_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def patched_source():
    src = V1_PATH.read_text(encoding='utf-8')
    for e in json.loads(FIX_SPEC.read_text(encoding='utf-8'))['replacements']:
        n = src.count(e['old'])
        if n != e.get('count', 1):
            raise RuntimeError(f"fix_spec: ожидалось {e.get('count', 1)} вхождений, найдено {n}: {e['old'][:60]!r}")
        src = src.replace(e['old'], e['new'])
    return src


def load_v2():
    m = type(sys)('k03_bv_v2')
    m.__file__ = str(V1_PATH)  # те же входы; main() не вызывается
    exec(compile(patched_source(), 'boundary_validator.py (v2, in-memory)', 'exec'), m.__dict__)
    return m


def unified_patch():
    rel = 'research/round-3-results/K03/boundary_validator.py'
    a = V1_PATH.read_text(encoding='utf-8').splitlines(keepends=True)
    b = patched_source().splitlines(keepends=True)
    return ''.join(difflib.unified_diff(a, b, f'a/{rel}', f'b/{rel}'))


# ---------- геометрические помощники (UTM 42N, метры) ----------

def utm(g):
    from shapely.ops import transform
    return transform(TO_UTM, g)


def ll(pt):
    x, y = TO_LL(pt.x, pt.y)
    return [round(x, 9), round(y, 9)]


def longest_line(g):
    g = linemerge(g) if g.geom_type in ('MultiLineString', 'GeometryCollection') else g
    lines = [q for q in getattr(g, 'geoms', [g]) if q.geom_type == 'LineString']
    return max(lines, key=lambda q: q.length)


def normal_at(line, s):
    a, b = line.interpolate(max(s - 0.5, 0)), line.interpolate(min(s + 0.5, line.length))
    tx, ty = b.x - a.x, b.y - a.y
    n = math.hypot(tx, ty)
    return -ty / n, tx / n


def offset(base, normal, d):
    return Point(base.x + normal[0] * d, base.y + normal[1] * d)


def side_normal(line, s, inside_poly):
    """Нормаль в точке s линии, направленная внутрь inside_poly."""
    p = line.interpolate(s)
    n = normal_at(line, s)
    return n if inside_poly.contains(offset(p, n, 2.0)) else (-n[0], -n[1])


def geodesic_to_line(pt_utm, line_utm):
    """Геодезическое расстояние от точки до ближайшей точки линии (ближайшая ищется в UTM)."""
    q = line_utm.interpolate(line_utm.project(pt_utm))
    (lon1, lat1), (lon2, lat2) = TO_LL(pt_utm.x, pt_utm.y), TO_LL(q.x, q.y)
    return abs(GEOD.inv(lon1, lat1, lon2, lat2)[2])


class Oracle:
    """Независимая реализация контракта k03_assign (v2: край города проверяется раньше зоны unmatched).

    Зоны вычисляются заново из слоёв, а не берутся из валидатора.
    """
    TOL = 1.0
    KZ_LON, KZ_LAT = (46.5, 87.5), (40.5, 55.5)

    def __init__(self, L):
        import geo_common as gc
        raw, rels = gc.overpass_relations()
        tsel, _ = gc.build_osm_relation(rels[gc.TSELINOGRAD])
        self.city = {'astana': utm(L.ast_city), 'shymkent': utm(L.shy_city)}
        self.prod = {k: utm(g) for k, g in L.ast_prod.items()}
        self.ov = {k: utm(g) for k, g in L.ast_ov.items()}
        self.shy = {k: utm(g) for k, g in L.shy.items()}
        poly = lambda g: unary_union([q for q in getattr(g, 'geoms', [g]) if q.geom_type in ('Polygon', 'MultiPolygon')
                                      and q.area > 0])
        self.z1 = poly(utm(L.ast_prod['kz.astana.district.baikonur']).intersection(utm(tsel)))
        self.z2 = poly(self.city['astana'].difference(unary_union(list(self.ov.values()))))
        self.z3 = poly(unary_union([self.prod[k].symmetric_difference(self.ov[k]) for k in self.prod]))

    def expect(self, lon, lat):
        if not all(math.isfinite(v) for v in (lon, lat)):
            return 'invalid', None
        if not (self.KZ_LON[0] <= lon <= self.KZ_LON[1] and self.KZ_LAT[0] <= lat <= self.KZ_LAT[1]):
            return 'invalid', None
        p = Point(TO_UTM(lon, lat))
        city = next((c for c, g in self.city.items() if g.covers(p) or g.boundary.distance(p) <= self.TOL), None)
        if city is None:
            return 'outside', None
        T = self.TOL
        if city == 'astana' and (self.z1.covers(p) or self.z1.boundary.distance(p) <= T):
            return 'ambiguous', None
        if self.city[city].boundary.distance(p) <= T:
            return 'ambiguous', None
        if city == 'astana' and self.z3.area > 0 and self.z3.buffer(1e-9).covers(p):
            return 'ambiguous', None
        layers = [self.prod, self.ov] if city == 'astana' else [self.shy]
        covers = [sorted(k for k, g in lay.items() if g.covers(p)) for lay in layers]
        if any(c != covers[0] for c in covers):
            return 'ambiguous', None
        near = any(g.boundary.distance(p) <= T for lay in layers for g in lay.values())
        if not covers[0]:
            return ('ambiguous', None) if near else ('unmatched', None)
        if len(covers[0]) > 1 or near:
            return 'ambiguous', None
        return 'matched', covers[0][0]
