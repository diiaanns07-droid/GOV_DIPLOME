"""K03 r8: независимые проверки этапов 2–3 поверх сверки fixtures (вызываются из run_tests.py).

Этап 2: геодезия WGS84 против гаверсинуса, симметрия, плотная проверка округления мм, независимость от порядка,
пересчёт QA-групп из координат (без слияния записей), edges_inclusive=false.
"""
import copy
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import geo_v2_ref as R

HERE = Path(__file__).resolve().parent


REC = None  # устанавливает run_tests.main(): общий журнал результатов
JS = None   # путь к проверяемой копии geo_v2.js (--js)


def _rec(check, verdict, summary, **d):
    REC(check, verdict, summary, **d)


def run_node(app, cases, data=None, evidence=None, js=None):
    node = shutil.which('node')
    if not node:
        return None
    req = {'app_root': str(app), 'cases': cases}
    if data is not None:
        req['data'] = data
    if evidence is not None:
        req['evidence'] = evidence
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        json.dump(req, fh, ensure_ascii=False)
        path = fh.name
    r = subprocess.run([node, str(HERE / 'node_runner.cjs'), path, str(js or JS or HERE / 'geo_v2.js')], capture_output=True, text=True, timeout=600)
    Path(path).unlink()
    if r.returncode:
        raise RuntimeError(r.stderr[-400:])
    return {x['id']: x for x in json.loads(r.stdout)}


def _grid(bbox, n=25):
    W, S, E, N = bbox
    k = int(math.ceil(math.sqrt(n)))
    return [(W + (i % k + 0.5) / k * (E - W), S + (i // k + 0.5) / k * (N - S)) for i in range(n)]


def geodesic(doc, py, jsr, data, ev, app):
    try:
        from pyproj import Geod
    except ImportError:
        _rec('S2-geodesic-vs-haversine', 'SKIP', 'pyproj не установлен')
        return
    g = Geod(ellps='WGS84')
    worst, n, order_diff, pts = 0.0, 0, 0, 0
    for city in ('astana', 'shymkent'):
        srcs = [p for p in data['cities'][city]['places'] if p['group'] in ('school', 'outpatient_clinic')]
        for (x, y) in _grid(data['cities'][city]['bbox']):
            hv = [(R.great_circle_m(x, y, s['lon'], s['lat']), s['id']) for s in srcs]
            gd = [(abs(g.inv(x, y, s['lon'], s['lat'])[2]), s['id']) for s in srcs]
            for (h, _), (d, _) in zip(hv, gd):
                if d > 1:
                    worst = max(worst, abs(h - d) / d)
                    n += 1
            pts += 1
            order_diff += min(hv)[1] != min(gd)[1]
    ok = worst < 0.005
    _rec('S2-geodesic-vs-haversine', 'PASS' if ok else 'FAIL',
         f'{n} пар (25 точек × записи школ/поликлиник, оба города): макс. относительное отличие гаверсинуса R=6371008.8 от '
         f'WGS84 {worst * 100:.3f}% (< 0,5% — порог, при котором ошибка порядка lon/lat или единиц была бы видна); '
         f'ближайшая запись по сфере и эллипсоиду различается у {order_diff} из {pts} точек (свойство метрики, не ошибка)',
         max_rel_diff=worst, pairs=n, nearest_differs=order_diff, points=pts)


def symmetry(doc, py, jsr, data, ev, app):
    pairs = []
    for city in ('astana', 'shymkent'):
        srcs = [p for p in data['cities'][city]['places']]
        for (x, y) in _grid(data['cities'][city]['bbox'], 9):
            pairs += [[[x, y], [s['lon'], s['lat']]] for s in srcs]
    rev = [[b, a] for a, b in pairs]
    pyf = [R.mm_between({'lon': a[0], 'lat': a[1]}, {'lon': b[0], 'lat': b[1]}) for a, b in pairs]
    pyr = [R.mm_between({'lon': a[0], 'lat': a[1]}, {'lon': b[0], 'lat': b[1]}) for a, b in rev]
    js = run_node(app, [{'id': 'f', 'op': 'dist', 'pairs': pairs}, {'id': 'r', 'op': 'dist', 'pairs': rev}])
    bad_py = sum(a != b for a, b in zip(pyf, pyr))
    if js is None:
        _rec('S2-symmetry', 'FAIL' if bad_py else 'PASS', f'Python: {len(pairs)} пар, d(a,b)≠d(b,a): {bad_py}; JS SKIP (нет node)')
        return
    jf, jr = js['f']['result'], js['r']['result']
    bad_js = sum(a != b for a, b in zip(jf, jr))
    cross = sum(a != b for a, b in zip(pyf, jf))
    _rec('S2-symmetry-and-mm-parity', 'FAIL' if bad_py or bad_js or cross else 'PASS',
         f'{len(pairs)} пар (9 точек × все записи, оба города): d(a,b)≠d(b,a) — Python {bad_py}, JS {bad_js}; мм JS≠Python {cross}')


def rounding_dense(doc, py, jsr, data, ev, app):
    vals = []
    for k in range(0, 5_000_000, 977):
        m = (k + 0.5) / 1000
        lo, hi = m, m
        for _ in range(2):
            lo, hi = math.nextafter(lo, 0), math.nextafter(hi, 1)
            vals += [lo, hi]
        vals.append(m)
    naive = [math.floor(v * 1000 + 0.5) for v in vals]
    mine = [R.to_mm(v) for v in vals]
    bad_py = sum(a != b for a, b in zip(naive, mine))
    js = run_node(app, [{'id': 't', 'op': 'tomm', 'values': vals}])
    bad_js = sum(a != b for a, b in zip(naive, js['t']['result'])) if js else None
    _rec('S2-mm-rounding-dense', 'FAIL' if bad_py or bad_js else 'PASS',
         f'{len(vals)} значений у границ k+0,5 мм (±2 ulp, до 5 км): floor(x+0.5) ≠ js_round — {bad_py}; ≠ JS Math.round — '
         f'{bad_js if bad_js is not None else "SKIP"}. Единственное расходящееся x=0.49999999999999994 не получается из d·1000')


def permutation(doc, py, jsr, data, ev, app):
    """Обратный порядок мест в data.js и входных массивов не меняет ближайшие ключи и ничьи."""
    st1 = json.loads((HERE / 'fixtures/stage1.json').read_text(encoding='utf-8'))
    base = [c for c in st1['cases'] if c['op'] == 'table' and c['id'].endswith('-max-table')]
    base += [c for c in doc['cases'] if c['op'] in ('table', 'after')]
    dperm = copy.deepcopy(data)
    for c in dperm['cities'].values():
        c['places'] = list(reversed(c['places']))
    cases_rev = []
    for c in base:
        c2 = copy.deepcopy(c)
        pl = c2['places']
        n = len(pl['candidates'])
        pl['control_points'] = list(reversed(pl['control_points']))
        pl['candidates'] = list(reversed(pl['candidates']))
        if 'selected' in c2:
            c2['selected'] = [n - 1 - j for j in c2['selected']]
        cases_rev.append(c2)

    def keyed(c, res):
        if c['op'] == 'table':
            return {pk: (b and (b['key'], b['mm'], tuple(b['tied_keys']))) for pk, b in zip(res['point_keys'], res['baseline'])}
        ids = [p['id'] for p in c['places']['control_points']]
        return {i: (r and (r['key'], r['mm'])) for i, r in zip(ids, res)}

    import run_tests
    bad = []
    for c, c2 in zip(base, cases_rev):
        a1 = run_tests.py_case(c, data, ev, {})
        a2 = run_tests.py_case(c2, dperm, ev, {})
        if keyed(c, a1['result']) != keyed(c2, a2['result']):
            bad.append('py ' + c['id'])
    js1 = run_node(app, base)
    js2 = run_node(app, cases_rev, data=dperm)
    if js1:
        for c, c2 in zip(base, cases_rev):
            if keyed(c, js1[c['id']]['result']) != keyed(c2, js2[c2['id']]['result']):
                bad.append('js ' + c['id'])
    _rec('S2-order-independence', 'FAIL' if bad else 'PASS',
         f'{len(base)} сценариев: обратный порядок мест в data.js, контрольных точек и кандидатов → те же ближайшие ключи, мм и ничьи '
         f'(Python{" и JS" if js1 else ""}); расхождений {len(bad)}', mismatches=bad)


def qa_groups(doc, py, jsr, data, ev, app):
    bad, info = [], []
    for city in ('astana', 'shymkent'):
        places = data['cities'][city]['places']
        by_xy = {}
        for p in places:
            by_xy.setdefault((p['lon'], p['lat']), []).append(p['id'])
        mine = sorted(sorted(v) for v in by_xy.values() if len(v) >= 3)
        theirs = sorted(sorted(g['ids']) for g in ev['cities'][city]['qa']['colocated'])
        if mine != theirs:
            bad.append(f'{city}: группы COLOCATED по точным координатам {mine} ≠ evidence {theirs}')
        members = {i: len(g['ids']) for g in ev['cities'][city]['qa']['colocated'] for i in g['ids']}
        group_of = {p['id']: p['group'] for p in places}
        for g in ev['cities'][city]['qa']['colocated']:
            comp = {}
            for i in g['ids']:
                comp[group_of[i]] = comp.get(group_of[i], 0) + 1
            info.append(f'{city}: группа ({g["lon"]}, {g["lat"]}) из {len(g["ids"])} записей разных категорий {comp}')
        for cat in ('school', 'outpatient_clinic'):
            ctx = R.build_context(data, ev, city, cat)
            n_data = sum(1 for p in places if p['group'] == cat)
            if len(ctx['sources']) != n_data:
                bad.append(f'{city}/{cat}: записей в контексте {len(ctx["sources"])} ≠ {n_data} в data.js (слияние?)')
            for s in ctx['sources']:
                g = s['qa']['colocated_group']
                if (g is not None) != (s['id'] in members) or (g and g['size'] != members[s['id']]):
                    bad.append(f'{city}/{cat}/{s["id"]}: colocated_group {g} не соответствует evidence по ID')
        # физическое скопление, разрезанное правилом «точное совпадение»: записи ближе 1,5 м с разными координатами
        grp_ids = set(members)
        for p in places:
            for q in places:
                if p['id'] < q['id'] and (p['lon'], p['lat']) != (q['lon'], q['lat']) and \
                        R.great_circle_m(p['lon'], p['lat'], q['lon'], q['lat']) < 1.5 and ((p['id'] in grp_ids) != (q['id'] in grp_ids)):
                    info.append(f'{city}: {p["id"][:8]}… и {q["id"][:8]}… в {R.great_circle_m(p["lon"], p["lat"], q["lon"], q["lat"]):.2f} м, '
                                f'но только одна в группе COLOCATED (правило — точное совпадение 5 знаков)')
    _rec('S2-qa-groups-not-merged', 'FAIL' if bad else 'PASS',
         'группы COLOCATED пересчитаны из точных координат data.js и совпадают с evidence; флаг привязан по ID; '
         'записи не сливаются (число записей категории = data.js)' if not bad else '; '.join(bad[:4]), problems=bad, info=info)
    for i in info:
        print('   INFO', i)


def edges_exclusive(doc, py, jsr, data, ev, app):
    ev2 = copy.deepcopy(ev)
    for c in ev2['cities'].values():
        c['spatial_unit']['edges_inclusive'] = False
    res = []
    for city in ('astana', 'shymkent'):
        W, S, E, N = data['cities'][city]['bbox']
        places = {'control_points': [{'id': 'c', 'lon': W, 'lat': S, 'weight': 1}], 'candidates': []}
        try:
            R.validate_places(R.build_context(data, ev2, city, 'school'), places)
            res.append(('py', city, 'ok'))
        except R.GeoErr as e:
            res.append(('py', city, e.code))
        js = run_node(app, [{'id': 'x', 'op': 'validate', 'city': city, 'category': 'school', 'places': places}], evidence=ev2)
        if js:
            res.append(('js', city, js['x']['result'] and 'ok' if js['x']['ok'] else js['x']['error']['code']))
    ok = all(r[2] == 'outside_bbox' for r in res)
    _rec('S2-edges-exclusive-variant', 'PASS' if ok else 'FAIL',
         f'копия среза с edges_inclusive=false: угол bbox отклоняется — {res}')


EXTRA = {'2': [geodesic, symmetry, rounding_dense, permutation, qa_groups, edges_exclusive]}
