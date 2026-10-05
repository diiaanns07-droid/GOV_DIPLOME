"""K03 round 8 — независимый Python-оракул геоадаптера city-plan-v2 (не перевод geo_v2.js).

Тот же контракт, что в API.md: контекст среза, проверка мест, таблица расстояний в мм (haversine-mm-v1),
устойчивый ключ ничьей (мм, source < hypothetical, ID). Только stdlib.
"""
import hashlib
import json
import math

SCHEMA = 'city-plan-v2'
METRIC_VERSION = 'haversine-mm-v1'
ADAPTER_VERSION = 'k03-geo-v2.1'
EARTH_R = 6371008.8
CATEGORIES = ('school', 'outpatient_clinic')
POINTS_RANGE, CANDIDATES_RANGE, WEIGHT_RANGE, COST_RANGE, ID_MAX = (1, 25), (0, 16), (1, 100), (1, 1_000_000), 64


class GeoErr(Exception):
    def __init__(self, code, path, detail=''):
        super().__init__(f'{code} @ {path}: {detail}')
        self.code, self.path = code, path


def js_round(x):
    """Math.round из JS: ближайшее целое, половина — вверх. floor(x + 0.5) ошибается при x = 0.49999999999999994."""
    f = math.floor(x)
    return f + 1 if x - f >= 0.5 else f


def to_mm(metres):
    return js_round(metres * 1000)


def great_circle_m(a_lon, a_lat, b_lon, b_lat):
    phi1, phi2 = math.radians(a_lat), math.radians(b_lat)
    h = (math.sin(math.radians(b_lat - a_lat) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(b_lon - a_lon) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def mm_between(a, b):
    return to_mm(great_circle_m(a['lon'], a['lat'], b['lon'], b['lat']))


def _js_compatible(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 53:
        return int(v)
    if isinstance(v, (list, tuple)):
        return [_js_compatible(x) for x in v]
    return v


def js_stringify(v):
    """JSON.stringify для массивов чисел/строк/bool/null: без пробелов, целые float как целые, без \\u-экранирования."""
    return json.dumps(_js_compatible(v), separators=(',', ':'), ensure_ascii=False)


def sha_hex(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def round7(x):
    return js_round(x * 1e7) / 1e7


def _box_ok(b):
    return (isinstance(b, list) and len(b) == 4
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in b)
            and -180 <= b[0] < b[2] <= 180 and -90 <= b[1] < b[3] <= 90)


def _inside(b, lon, lat, inclusive):
    if inclusive:
        return b[0] <= lon <= b[2] and b[1] <= lat <= b[3]
    return b[0] < lon < b[2] and b[1] < lat < b[3]


def build_context(data, evidence, city, category):
    cities = (data or {}).get('cities', {})
    if city not in cities:
        raise GeoErr('bad_city', 'city', str(city)[:40])
    if category not in CATEGORIES:
        raise GeoErr('bad_category', 'category', str(category)[:40])
    c = cities[city]
    ev_city = ((evidence or {}).get('cities') or {}).get(city) or {}
    su = ev_city.get('spatial_unit')
    bbox = su['bbox'] if su and su.get('bbox') else c['bbox']
    if not _box_ok(bbox) or (su and su.get('bbox') != c['bbox']):
        raise GeoErr('bad_slice', 'bbox', 'bbox некорректен или различается')
    inclusive = (su.get('edges_inclusive') is True) if su else True
    pf = ((c.get('files') or {}).get('places_social') or {}).get('sha256')
    rows = sorted(([p['id'], round7(p['lon']), round7(p['lat'])] for p in c['places']), key=lambda r: r[0])
    digest_all = sha_hex(js_stringify(rows))
    snapshot = 'sha256:' + sha_hex(js_stringify([SCHEMA, city, c.get('release'), pf, digest_all, bbox, inclusive,
                                                 METRIC_VERSION]))
    qa = ev_city.get('qa')
    group_of = {}
    partners = {}
    if qa:
        for g in qa.get('colocated') or []:
            for i in g['ids']:
                group_of[i] = {'size': len(g['ids']), 'lon': g['lon'], 'lat': g['lat']}
        for d in qa.get('possible_duplicates') or []:
            partners.setdefault(d['a'], []).append({'other': d['b'], 'rule': d['rule'], 'distance_m': d['distance_m']})
            partners.setdefault(d['b'], []).append({'other': d['a'], 'rule': d['rule'], 'distance_m': d['distance_m']})
    same_xy = {}
    for p in c['places']:
        same_xy[(p['lon'], p['lat'])] = same_xy.get((p['lon'], p['lat']), 0) + 1
    srcs = []
    for p in sorted((p for p in c['places'] if p['group'] == category), key=lambda p: p['id']):
        srcs.append({
            'key': 'source:' + p['id'], 'kind': 'source', 'id': p['id'], 'lon': p['lon'], 'lat': p['lat'], 'group': p['group'],
            'name': p.get('name'),
            'provenance': {'overture_id': p['id'], 'overture_version': p.get('overture_version'), 'confidence': p.get('confidence'),
                           'records': [{'dataset': s.get('dataset'), 'record_id': s.get('record_id'), 'license': s.get('license'),
                                        'update_time': s.get('update_time')} for s in (p.get('sources') or [])]},
            'qa': {'available': bool(qa), 'colocated_group': group_of.get(p['id']),
                   'possible_duplicates': sorted(partners.get(p['id'], []), key=lambda x: x['other']),
                   'category_doubt': ((qa or {}).get('category_doubt') or {}).get(p['id']),
                   'same_exact_coordinates': same_xy[(p['lon'], p['lat'])] - 1}})
    sources_digest = 'sha256:' + sha_hex(js_stringify([snapshot, category, [[s['id'], s['lon'], s['lat']] for s in srcs]]))
    others = []
    for x in cities:
        if x != city:
            ou = ((evidence or {}).get('cities') or {}).get(x, {}).get('spatial_unit')
            others.append({'city_id': x, 'bbox': cities[x]['bbox'], 'edges_inclusive': (ou.get('edges_inclusive') is True) if ou else True})
    return {'schema': SCHEMA, 'adapter_version': ADAPTER_VERSION, 'metric_version': METRIC_VERSION, 'city_id': city, 'category': category, 'bbox': list(bbox),
            'edges_inclusive': inclusive, 'release': c.get('release'), 'places_file_sha256': pf, 'source_snapshot': snapshot,
            'sources_digest': sources_digest, 'sources': srcs, 'other_slices': others}


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v):
    return math.isfinite(v) if isinstance(v, float) else abs(v) <= 1.7976931348623157e308


def _integer(v):
    if isinstance(v, bool) or not _number(v):
        return False
    return isinstance(v, int) or (math.isfinite(v) and v.is_integer())


def check_coord(ctx, lon, lat, path):
    if not (_number(lon) and _number(lat)):
        raise GeoErr('not_number', path)
    if not (_finite(lon) and _finite(lat)):
        raise GeoErr('not_finite', path)
    if abs(lon) > 180 or abs(lat) > 90:
        raise GeoErr('out_of_range', path)
    if _inside(ctx['bbox'], lon, lat, ctx['edges_inclusive']):
        return
    if _inside(ctx['bbox'], lat, lon, ctx['edges_inclusive']):
        raise GeoErr('lon_lat_swapped', path)
    for o in ctx.get('other_slices') or []:
        if _box_ok(o['bbox']) and _inside(o['bbox'], lon, lat, o['edges_inclusive']):
            raise GeoErr('other_city', path, o['city_id'])
    raise GeoErr('outside_bbox', path)


def _shape(obj, keys, path):
    if not isinstance(obj, dict):
        raise GeoErr('bad_shape', path)
    if sorted(obj) != sorted(keys):
        raise GeoErr('bad_shape', path, ','.join(sorted(obj))[:80])
    i = obj['id']
    if not isinstance(i, str) or not (1 <= len(i) <= ID_MAX) or any(ord(ch) < 32 or ord(ch) == 127 for ch in i):
        raise GeoErr('bad_id', path + '.id')


def validate_places(ctx, places, allow_empty_points=False):
    if not isinstance(places, dict):
        raise GeoErr('bad_shape', '$')
    cps, cands = places.get('control_points'), places.get('candidates')
    if not isinstance(cps, list):
        raise GeoErr('bad_shape', 'control_points')
    if not isinstance(cands, list):
        raise GeoErr('bad_shape', 'candidates')
    if len(cps) > POINTS_RANGE[1] or (len(cps) < POINTS_RANGE[0] and not allow_empty_points):
        raise GeoErr('too_many_points', 'control_points')
    if not (CANDIDATES_RANGE[0] <= len(cands) <= CANDIDATES_RANGE[1]):
        raise GeoErr('too_many_candidates', 'candidates')
    seen, out_p = set(), []
    for i, p in enumerate(cps):
        path = f'control_points[{i}]'
        _shape(p, ('id', 'lon', 'lat', 'weight'), path)
        if p['id'] in seen:
            raise GeoErr('duplicate_id', path + '.id')
        seen.add(p['id'])
        if not _integer(p['weight']) or not (WEIGHT_RANGE[0] <= p['weight'] <= WEIGHT_RANGE[1]):
            raise GeoErr('bad_weight', path + '.weight')
        check_coord(ctx, p['lon'], p['lat'], path)
        out_p.append({'key': 'control:' + p['id'], 'kind': 'control', 'id': p['id'], 'lon': p['lon'], 'lat': p['lat'],
                      'weight': p['weight']})
    seen, out_c = set(), []
    for i, q in enumerate(cands):
        path = f'candidates[{i}]'
        _shape(q, ('id', 'lon', 'lat', 'category', 'kind', 'cost'), path)
        if q['id'] in seen:
            raise GeoErr('duplicate_id', path + '.id')
        seen.add(q['id'])
        if q['kind'] != 'hypothetical':
            raise GeoErr('bad_kind', path + '.kind')
        if q['category'] != ctx['category']:
            raise GeoErr('bad_category', path + '.category')
        if not _integer(q['cost']) or not (COST_RANGE[0] <= q['cost'] <= COST_RANGE[1]):
            raise GeoErr('bad_cost', path + '.cost')
        check_coord(ctx, q['lon'], q['lat'], path)
        out_c.append({'key': 'hypothetical:' + q['id'], 'kind': 'hypothetical', 'id': q['id'], 'lon': q['lon'], 'lat': q['lat'],
                      'category': q['category'], 'cost': q['cost'],
                      'coincides_with_sources': [s['key'] for s in ctx['sources'] if s['lon'] == q['lon'] and s['lat'] == q['lat']]})
    return {'control_points': out_p, 'candidates': out_c}


def _order(item):
    mm, kind, ident = item
    return (mm, 0 if kind == 'source' else 1, ident.encode('utf-16-be'))  # JS сравнивает строки по UTF-16 code units


def distance_table(ctx, cps, cands):
    base = []
    for p in cps:
        options = [(mm_between(p, s), 'source', s['id']) for s in ctx['sources']]
        if not options:
            base.append(None)
            continue
        best = min(options, key=_order)
        tied = sorted(('source:' + i for mm, _, i in options if mm == best[0]), key=lambda k: k.encode('utf-16-be'))
        base.append({'key': 'source:' + best[2], 'id': best[2], 'mm': best[0], 'tied_keys': tied})
    return {'metric_version': METRIC_VERSION, 'source_snapshot': ctx['source_snapshot'], 'point_keys': [p['key'] for p in cps],
            'candidate_keys': [q['key'] for q in cands], 'baseline': base,
            'to_candidates': [[mm_between(p, q) for q in cands] for p in cps]}


def nearest_after(table, i, selected, cands):
    pool = []
    if table['baseline'][i]:
        b = table['baseline'][i]
        pool.append((b['mm'], 'source', b['id']))
    pool += [(table['to_candidates'][i][j], 'hypothetical', cands[j]['id']) for j in selected]
    if not pool:
        return None
    mm, kind, ident = min(pool, key=_order)
    return {'key': f'{kind}:{ident}', 'kind': kind, 'mm': mm}
