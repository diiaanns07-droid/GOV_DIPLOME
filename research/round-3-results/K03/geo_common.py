"""K03 round 3: общие функции чтения слоёв. Только чтение, без сети."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import shapely
from pyproj import Geod
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INP = HERE / 'inputs'
GEOD = Geod(ellps='WGS84')

P_PRODUCT = 'data/astana_districts.geojson'
P_OVERPASS = 'data/geo_sources/astana_districts_overpass.json'
P_SARA_OSM = 'data/geo_sources/sara_osm.json'
P_SARA_NOM = 'data/geo_sources/sara_nominatim.json'
P_A10 = 'research/govtech-results/10_safety/A10_sample_kpssu_shymkent_aggregates.json'
P_K03_OWN = 'research/next-round/K03/territory_registry.json'
P_OV_AST = 'research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson'
P_OV_SHY = 'research/round-3-results/K03/inputs/K10/shymkent_districts_overture.geojson'
P_K10_E01 = 'research/round-3-results/K03/inputs/K10/E01_district_coverage.json'
P_K03_CLEVER = 'research/round-3-results/K03/inputs/K03_clever/territory_registry.json'
P_K03_CLEVER_GEO = 'research/round-3-results/K03/inputs/K03_clever/geometry_result.json'

OVERTURE_RELEASE = '2026-09-23.1'
ASTANA_REL = {3479876: 'esil', 3482819: 'almaty', 3486954: 'saryarka',
              8593081: 'baikonur', 20593940: 'nura', 19733918: 'saraishyk'}
TSELINOGRAD = 3403760


def load(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8'))


def sha256(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def km2(g):
    return abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6


def ghash(g):
    """sha256 нормализованного WKB: не зависит от начальной точки колец и порядка частей."""
    return hashlib.sha256(shapely.normalize(g).wkb).hexdigest()


def parts(g):
    return list(g.geoms) if hasattr(g, 'geoms') else [g]


def iou(a, b):
    u = km2(a.union(b))
    return km2(a.intersection(b)) / u if u else None


def _join(ways):
    pool = [list(c) for c in ways]
    rings = []
    while pool:
        cur = pool.pop(0)
        grown = True
        while cur[0] != cur[-1] and grown:
            grown = False
            for i, s in enumerate(pool):
                if s[0] == cur[-1]:
                    cur = cur + s[1:]
                elif s[-1] == cur[-1]:
                    cur = cur + s[::-1][1:]
                elif s[-1] == cur[0]:
                    cur = s + cur[1:]
                elif s[0] == cur[0]:
                    cur = s[::-1] + cur[1:]
                else:
                    continue
                pool.pop(i)
                grown = True
                break
        if len(cur) >= 4 and cur[0] == cur[-1]:
            rings.append(Polygon(cur))
    return rings


def build_osm_relation(rel):
    """Сборка мультиполигона из путей Overpass `out geom` (как в next-round K03)."""
    role = defaultdict(list)
    for m in rel['members']:
        if m['type'] == 'way' and m.get('geometry'):
            role[m.get('role') or 'outer'].append([(p['lon'], p['lat']) for p in m['geometry']])
    outers, inners = _join(role['outer']), _join(role['inner'])
    holes = defaultdict(list)
    for ip in inners:
        c = [k for k, op in enumerate(outers) if op.covers(ip.representative_point())]
        if c:
            holes[min(c, key=lambda k: outers[k].area)].append(ip)
    pieces = [op.difference(unary_union(holes[k])) if holes[k] else op for k, op in enumerate(outers)]
    return unary_union(pieces), inners


def overpass_relations():
    raw = load(P_OVERPASS)
    return raw, {e['id']: e for e in raw['elements'] if e['type'] == 'relation'}


def product_layer():
    gj = load(P_PRODUCT)
    return gj, {f['properties']['osm_id']: (f['properties'], shape(f['geometry'])) for f in gj['features']}


def overture_layer(path):
    gj = load(path)
    units = []
    for f in gj['features']:
        p = f['properties']
        osm = next((s for s in p['sources'] if s['dataset'] == 'OpenStreetMap'), {})
        rec = osm.get('record_id') or ''
        rid, _, ver = rec.lstrip('r').partition('@')
        units.append(dict(props=p, geom=shape(f['geometry']), osm_relation=int(rid) if rid else None,
                          osm_relation_version=int(ver) if ver else None,
                          osm_source_update_time=osm.get('update_time')))
    return gj, units
