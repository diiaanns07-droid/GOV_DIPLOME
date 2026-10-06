"""K03 r10: фиксированный набор пар обоих городов → fixtures/city_pairs.json (+ сводка покрытия).

  python3 research/round-10-results/K03/make_city_pairs.py

Точки анализа (origins) — сетка 3×3 внутри квадрата, kind=synthetic (не жители и не здания). Кандидаты — 2 synthetic точки.
Цели — все школы data.js (observed_secondary, Overture/OSM) + кандидаты. Для каждой пары: strict, exploratory, geodesic.
Ожидания записывает независимый Python-оракул (routing_ref); JS сверяется с ними в run_tests.py.
"""
import collections
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k03net as K  # noqa: E402
import routing_ref as RR  # noqa: E402

POL = ('pedestrian-v1-strict', 'pedestrian-v1-exploratory')


def compact(r):
    """Строка для хранения: геометрия — sha256 канонического JSON и число точек (полное сравнение JS/Python — в run_tests.py)."""
    c = {k: r[k] for k in ('status', 'distance_mm', 'reason', 'route_edge_ids', 'assumptions', 'label', 'method', 'policy_id')}
    c['geometry_sha256'] = K.sha256_canon(r['geometry']) if r['geometry'] else None
    c['geometry_points'] = len(r['geometry']['coordinates']) if r['geometry'] else 0
    c['parts_mm'] = [x['length_mm'] for x in r['parts']]
    return c


def points(city, bbox, data):
    W, S, E, N = bbox
    origins = [{'id': f'grid-{i}{j}', 'lon': round(W + (E - W) * fx, 7), 'lat': round(S + (N - S) * fy, 7), 'kind': 'synthetic'}
               for i, fx in enumerate((0.2, 0.5, 0.8)) for j, fy in enumerate((0.2, 0.5, 0.8))]
    cands = [{'id': 'cand-A', 'lon': round(W + (E - W) * 0.35, 7), 'lat': round(S + (N - S) * 0.65, 7), 'kind': 'synthetic'},
             {'id': 'cand-B', 'lon': round(W + (E - W) * 0.65, 7), 'lat': round(S + (N - S) * 0.35, 7), 'kind': 'synthetic'}]
    schools = [{'id': p['id'], 'lon': p['lon'], 'lat': p['lat'], 'kind': 'observed_secondary', 'name': p['name']}
               for p in sorted(data['cities'][city]['places'], key=lambda p: K.u16(p['id'])) if p['group'] == 'school']
    return origins, schools + cands


def main():
    data = K.load_inputs()['data_js']
    out, summary = {}, {}
    for city in K.CITIES:
        g = json.loads((HERE / f'graph/{city}.graph.json').read_text(encoding='utf-8'))
        R = RR.Router(g)
        origins, targets = points(city, g['bbox'], data)
        rows = []
        for o in origins:
            for t in targets:
                rows.append({'origin_id': o['id'], 'target_id': t['id'],
                             **{p: compact(R.route(o, t, p)) for p in POL}, 'geodesic': compact(R.geodesic(o, t))})
        out[city] = {'graph_sha256': g['graph_sha256'], 'origins': origins, 'targets': targets, 'rows': rows}
        st = {p: dict(collections.Counter(r[p]['status'] for r in rows)) for p in POL}
        reasons = {p: dict(collections.Counter(r[p]['reason'] for r in rows if r[p]['status'] != 'ok')) for p in POL}
        ratio = {p: [r[p]['distance_mm'] / r['geodesic']['distance_mm'] for r in rows if r[p]['status'] == 'ok' and r['geodesic']['distance_mm'] > 0] for p in POL}
        assum = {p: dict(collections.Counter(a for r in rows if r[p]['status'] == 'ok' for a in r[p]['assumptions'])) for p in POL}
        summary[city] = {'pairs': len(rows), 'origins_synthetic': len(origins), 'targets': len(targets),
                         'schools_observed_secondary': sum(t['kind'] == 'observed_secondary' for t in targets),
                         'status': st, 'non_ok_reasons': reasons, 'assumptions_in_ok_routes': assum,
                         'network_to_geodesic_ratio': {p: ({'min': round(min(v), 3), 'median': round(statistics.median(v), 3), 'max': round(max(v), 3)} if v else None)
                                                       for p, v in ratio.items()}}
        print(city, json.dumps(summary[city]['status'], ensure_ascii=False), json.dumps(summary[city]['network_to_geodesic_ratio']))
    K.dump(HERE / 'fixtures/city_pairs.json', {'schema': 'k03-r10-city-pairs', 'description': 'origins и кандидаты synthetic; школы — Overture/OSM '
                                               'observed_secondary из data.js d2ff344; ожидания — Python-оракул routing_ref.', 'cities': out})
    K.dump(HERE / 'fixtures/city_pairs_summary.json', summary)


if __name__ == '__main__':
    main()
