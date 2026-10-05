"""K03 r8: fixtures для геоадаптера city-plan-v2 из данных конкретной сборки.

  python3 research/round-8-results/K03/make_fixtures.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>
Пишет fixtures/stage1.json (и далее stage2/stage3 — см. make_stage2.py / make_stage3.py).
Синтетические места (kind=synthetic в описании, не данные города) ставятся на сетку внутри bbox среза.
Ожидаемый исход проверок задан по построению; context/table — эталон Python-оракула, сверяемый с JS в run_tests.py.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAN = {'$num': 'NaN'}


def parse_js(p):
    t = Path(p).read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def grid(bbox, n, salt=0):
    """n синтетических точек строго внутри bbox (6 знаков), детерминированно."""
    W, S, E, N = bbox
    k = 1
    while k * k < n:
        k += 1
    out = []
    for i in range(n):
        gx, gy = i % k, i // k
        lon = round(W + (gx + 1 + 0.13 * salt) / (k + 1.5) * (E - W), 6)
        lat = round(S + (gy + 1 + 0.07 * salt) / (k + 1.5) * (N - S), 6)
        out.append((lon, lat))
    return out


def points(bbox, n, prefix='p'):
    return [{'id': f'{prefix}{i + 1:02d}', 'lon': x, 'lat': y, 'weight': 1 + (i * 7) % 100} for i, (x, y) in enumerate(grid(bbox, n))]


def cands(bbox, n, category, prefix='c'):
    return [{'id': f'{prefix}{i + 1:02d}', 'lon': x, 'lat': y, 'category': category, 'kind': 'hypothetical',
             'cost': 1000 * (i + 1)} for i, (x, y) in enumerate(grid(bbox, n, salt=1))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    r7 = json.loads((HERE / 'inputs/r7_point_fixtures.json').read_text(encoding='utf-8'))
    border = {f['id']: f['point'] for f in r7['fixtures'] if f['id'] in ('AST-border-0.0', 'SHY-border-0.0')}
    cases = []

    def case(cid, op, city, category, expect, places=None, **kw):
        cases.append(dict(id=cid, op=op, city=city, category=category, places=places, expect=expect, **kw))

    for city in ('astana', 'shymkent'):
        bb = data['cities'][city]['bbox']
        W, S, E, N = bb
        P = city[:3].upper()
        other = data['cities']['shymkent' if city == 'astana' else 'astana']['bbox']
        for cat in ('school', 'outpatient_clinic'):
            case(f'{P}-ctx-{cat}', 'context', city, cat, {'ok': True})
        cat = 'school'
        base = {'control_points': points(bb, 3), 'candidates': cands(bb, 2, cat)}
        case(f'{P}-max', 'validate', city, cat, {'ok': True}, {'control_points': points(bb, 25), 'candidates': cands(bb, 16, cat)},
             why='25 точек и 16 кандидатов — верхние границы')
        case(f'{P}-max-table', 'table', city, cat, {'ok': True}, {'control_points': points(bb, 25), 'candidates': cands(bb, 16, cat)})
        case(f'{P}-after-sel', 'after', city, cat, {'ok': True}, {'control_points': points(bb, 25), 'candidates': cands(bb, 16, cat)},
             selected=[0, 5, 15])
        case(f'{P}-26-points', 'validate', city, cat, {'ok': False, 'code': 'too_many_points', 'path': 'control_points'},
             {'control_points': points(bb, 26), 'candidates': []})
        case(f'{P}-17-cands', 'validate', city, cat, {'ok': False, 'code': 'too_many_candidates', 'path': 'candidates'},
             {'control_points': points(bb, 1), 'candidates': cands(bb, 17, cat)})
        case(f'{P}-0-points', 'validate', city, cat, {'ok': False, 'code': 'too_many_points', 'path': 'control_points'},
             {'control_points': [], 'candidates': []})
        case(f'{P}-0-points-ui', 'validate', city, cat, {'ok': True}, {'control_points': [], 'candidates': []}, allow_empty=True,
             why='пустое состояние интерфейса допустимо, расчёт и экспорт — нет')
        case(f'{P}-0-cands', 'validate', city, cat, {'ok': True}, {'control_points': points(bb, 2), 'candidates': []})
        corners = [{'id': 'sw', 'lon': W, 'lat': S, 'weight': 1}, {'id': 'ne', 'lon': E, 'lat': N, 'weight': 1}]
        case(f'{P}-edge-corners', 'validate', city, cat, {'ok': True}, {'control_points': corners, 'candidates': []},
             why='углы bbox: edges_inclusive=true')
        case(f'{P}-edge-out-1e-9', 'validate', city, cat, {'ok': False, 'code': 'outside_bbox', 'path': 'control_points[0]'},
             {'control_points': [{'id': 'x', 'lon': W - 1e-9, 'lat': S, 'weight': 1}], 'candidates': []})
        cx, cy = round((W + E) / 2, 6), round((S + N) / 2, 6)
        case(f'{P}-swap', 'validate', city, cat, {'ok': False, 'code': 'lon_lat_swapped', 'path': 'candidates[0]'},
             {'control_points': points(bb, 1), 'candidates': [dict(cands(bb, 1, cat)[0], lon=cy, lat=cx)]})
        case(f'{P}-other-city', 'validate', city, cat, {'ok': False, 'code': 'other_city', 'path': 'control_points[0]'},
             {'control_points': [{'id': 'x', 'lon': (other[0] + other[2]) / 2, 'lat': (other[1] + other[3]) / 2, 'weight': 1}], 'candidates': []})
        case(f'{P}-nan', 'validate', city, cat, {'ok': False, 'code': 'not_finite', 'path': 'control_points[0]'},
             {'control_points': [{'id': 'x', 'lon': NAN, 'lat': cy, 'weight': 1}], 'candidates': []})
        bk = 'AST-border-0.0' if city == 'astana' else 'SHY-border-0.0'
        case(f'{P}-border-candidate', 'validate', city, cat, {'ok': True},
             {'control_points': points(bb, 1), 'candidates': [dict(cands(bb, 1, cat)[0], lon=border[bk][0], lat=border[bk][1])]},
             why=f'кандидат на общей границе районов внутри bbox (K03 r7 {bk}: район ambiguous) — район не требуется')
        src = sorted((p for p in data['cities'][city]['places'] if p['group'] == cat), key=lambda p: p['id'])[0]
        case(f'{P}-cand-same-id-as-source', 'validate', city, cat, {'ok': True},
             {'control_points': points(bb, 1), 'candidates': [dict(cands(bb, 1, cat)[0], id=src['id'])]},
             why='ID кандидата совпадает с ID исходной записи: ключи hypothetical:… и source:… различаются')
        case(f'{P}-cand-on-source', 'validate', city, cat, {'ok': True},
             {'control_points': points(bb, 1), 'candidates': [dict(cands(bb, 1, cat)[0], lon=src['lon'], lat=src['lat'])]},
             why='кандидат в координатах исходной записи: coincides_with_sources, но остаётся hypothetical')
        for cid, mut, code, path in [
                ('dup-point', lambda b: b['control_points'].__setitem__(1, dict(b['control_points'][1], id='p01')), 'duplicate_id', 'control_points[1].id'),
                ('dup-cand', lambda b: b['candidates'].__setitem__(1, dict(b['candidates'][1], id='c01')), 'duplicate_id', 'candidates[1].id'),
                ('id-65', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], id='x' * 65)), 'bad_id', 'control_points[0].id'),
                ('id-ctrl', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], id='a\u0007b')), 'bad_id', 'candidates[0].id'),
                ('id-empty', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], id='')), 'bad_id', 'control_points[0].id'),
                ('id-number', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], id=5)), 'bad_id', 'control_points[0].id'),
                ('weight-0', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], weight=0)), 'bad_weight', 'control_points[0].weight'),
                ('weight-101', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], weight=101)), 'bad_weight', 'control_points[0].weight'),
                ('weight-1.5', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], weight=1.5)), 'bad_weight', 'control_points[0].weight'),
                ('weight-bool', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], weight=True)), 'bad_weight', 'control_points[0].weight'),
                ('cost-0', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], cost=0)), 'bad_cost', 'candidates[0].cost'),
                ('cost-big', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], cost=1000001)), 'bad_cost', 'candidates[0].cost'),
                ('cost-2.5', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], cost=2.5)), 'bad_cost', 'candidates[0].cost'),
                ('kind-observed', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], kind='observed')), 'bad_kind', 'candidates[0].kind'),
                ('cat-mismatch', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], category='outpatient_clinic')), 'bad_category', 'candidates[0].category'),
                ('extra-url', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], url='http://example.org')), 'bad_shape', 'candidates[0]'),
                ('missing-weight', lambda b: b['control_points'].__setitem__(0, {k: v for k, v in b['control_points'][0].items() if k != 'weight'}), 'bad_shape', 'control_points[0]'),
                ('lon-string', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], lon='71.43')), 'not_number', 'control_points[0]'),
                ('lat-range', lambda b: b['control_points'].__setitem__(0, dict(b['control_points'][0], lat=-91)), 'out_of_range', 'control_points[0]'),
                ('far-outside', lambda b: b['candidates'].__setitem__(0, dict(b['candidates'][0], lon=70.0, lat=45.0)), 'outside_bbox', 'candidates[0]')]:
            b = json.loads(json.dumps(base))
            mut(b)
            case(f'{P}-{cid}', 'validate', city, cat, {'ok': False, 'code': code, 'path': path}, b)
    doc = dict(schema='k03-geo-v2-fixtures', stage=1,
               description='Стадия 1: контекст среза, проверка мест (25/16, bbox, ID, вес, стоимость, kind, категория), таблица мм. '
                           'Места на сетке — synthetic, не данные города. Исходные записи — Overture из сборки.',
               target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                           data_js_sha256=hashlib.sha256((app / 'web/data.js').read_bytes()).hexdigest(),
                           evidence_js_sha256=hashlib.sha256((app / 'web/evidence.js').read_bytes()).hexdigest()),
               cases=cases)
    (HERE / 'fixtures').mkdir(exist_ok=True)
    (HERE / 'fixtures/stage1.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'stage1: {len(cases)} cases')


if __name__ == '__main__':
    main()
