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


# ---------------- этап 3 ----------------

FORBIDDEN = ('confirmed', 'verified', 'подтвержд')
ALLOWED_STATUS = {'source_reported_unverified', 'not_confirmed', 'hypothetical'}  # отрицания, а не подтверждения


def _walk_strings(x, path=''):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk_strings(v, f'{path}.{k}')
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk_strings(v, f'{path}[{i}]')
    elif isinstance(x, str):
        yield path, x


def provenance_qa_independent(doc, py, jsr, data, ev, app):
    """Каждое поле provenance/QA ответа сверяется с data.js/evidence.js напрямую (не через контекст модуля)."""
    bad, n = [], 0
    for c in doc['cases']:
        if c['op'] != 'evidence':
            continue
        city, cat = c['city'], c['category']
        rec = {p['id']: p for p in data['cities'][city]['places']}
        q = ev['cities'][city]['qa']
        coloc = {i: len(g['ids']) for g in q['colocated'] for i in g['ids']}
        dups = {}
        for d in q['possible_duplicates']:
            dups.setdefault(d['a'], set()).add(('source:' + d['b'], d['rule']))
            dups.setdefault(d['b'], set()).add(('source:' + d['a'], d['rule']))
        for impl, res in (('py', py[c['id']]), ('js', jsr.get(c['id']) if jsr else None)):
            if res is None:
                continue
            for k, r in zip(c['keys'], res['result']):
                if not r['ok']:
                    continue
                n += 1
                e = r['result']
                p = rec.get(e['id'])
                if p is None or p['group'] != cat or (p['lon'], p['lat']) != (e['lon'], e['lat']):
                    bad.append(f'{impl} {k}: запись не найдена в data.js этой категории или координаты другие')
                    continue
                want_recs = [{x: s.get(x) for x in ('dataset', 'record_id', 'license', 'update_time')} for s in p.get('sources') or []]
                if e['provenance']['records'] != want_recs or e['provenance']['overture_version'] != p.get('overture_version'):
                    bad.append(f'{impl} {k}: provenance ≠ data.js')
                codes = {f['code'] for f in e['flags']}
                if ('colocated' in codes) != (p['id'] in coloc):
                    bad.append(f'{impl} {k}: флаг colocated ≠ evidence.qa')
                got_d = {(f['other'], f['rule']) for f in e['flags'] if f['code'] == 'possible_duplicate'}
                if got_d != dups.get(p['id'], set()):
                    bad.append(f'{impl} {k}: possible_duplicate ≠ evidence.qa')
                if ('category_doubt' in codes) != (p['id'] in q['category_doubt']):
                    bad.append(f'{impl} {k}: category_doubt ≠ evidence.qa')
                shared = sum(1 for x in data['cities'][city]['places'] if (x['lon'], x['lat']) == (p['lon'], p['lat'])) - 1
                if ('shared_coordinates' in codes) != (shared > 0):
                    bad.append(f'{impl} {k}: shared_coordinates ≠ данные ({shared})')
                if e['position_status'] != 'source_reported_unverified' or e['confirmation'] != 'not_confirmed':
                    bad.append(f'{impl} {k}: статус положения {e["position_status"]}/{e["confirmation"]}')
                for path, s in _walk_strings({kk: vv for kk, vv in e.items() if kk not in ('name', 'provenance')}):
                    if any(w in s.lower() for w in FORBIDDEN) and s not in ALLOWED_STATUS:
                        bad.append(f'{impl} {k}{path}: «{s}» похоже на подтверждение')
    _rec('S3-provenance-qa-vs-sources', 'FAIL' if bad else 'PASS',
         f'{n} ответов sourceEvidence (JS и Python, оба города, обе категории): provenance = data.js, флаги QA = evidence.qa и '
         f'точные совпадения координат, статус всегда source_reported_unverified/not_confirmed; несоответствий {len(bad)}',
         problems=bad[:20])


def stale_and_synthetic(doc, py, jsr, data, ev, app):
    """stale_table; ничья на равном расстоянии и запись без provenance — на явной синтетике; срез без QA."""
    import run_tests
    out, bad = [], []
    city, cat = 'astana', 'school'
    W, S, E, N = data['cities'][city]['bbox']
    places = {'control_points': [{'id': 'p', 'lon': (W + E) / 2, 'lat': (S + N) / 2, 'weight': 1}], 'candidates': []}
    # 1) таблица, построенная на изменённом срезе (одна школа сдвинута), не привязывается к текущему контексту
    d2 = json.loads(json.dumps(data))
    sch = next(p for p in d2['cities'][city]['places'] if p['group'] == cat)
    sch['lon'] = round(sch['lon'] + 0.001, 6) if sch['lon'] + 0.001 < E else round(sch['lon'] - 0.001, 6)
    t_py = run_tests.py_case(dict(id='t', op='table', city=city, category=cat, places=places), d2, ev, {})['result']
    r_py = run_tests.py_case(dict(id='b', op='bind_table', city=city, category=cat, table=t_py), data, ev, {})['result']
    js_t = run_node(app, [dict(id='t', op='table', city=city, category=cat, places=places)], data=d2)
    r_js = run_node(app, [dict(id='b', op='bind_table', city=city, category=cat, table=js_t['t']['result'])]) if js_t else None
    t_bad = dict(t_py, metric_version='haversine-m-v0')
    r_py2 = run_tests.py_case(dict(id='b', op='bind_table', city=city, category=cat, table=json.loads(json.dumps(t_bad))), d2, ev, {})['result']
    got = [r_py.get('error', {}).get('code'), r_js and r_js['b']['result'].get('error', {}).get('code'), r_py2.get('error', {}).get('code')]
    out.append(('stale_table', got))
    if any(g not in ('stale_table', None) for g in got) or got[0] != 'stale_table' or got[2] != 'stale_table' or (r_js and got[1] != 'stale_table'):
        bad.append(f'stale_table: {got}')
    # 2) синтетика: две школы симметрично относительно точки (разные координаты) и без sources[]
    d3 = json.loads(json.dumps(data))
    cx, cy = (W + E) / 2, (S + N) / 2
    d3['cities'][city]['places'] = [p for p in d3['cities'][city]['places'] if p['group'] != cat] + [
        dict(id='syn-b', lon=cx + 2e-4, lat=cy, group=cat, name='SYNTHETIC B', sources=[], overture_version=None, confidence=None),
        dict(id='syn-a', lon=cx - 2e-4, lat=cy, group=cat, name='SYNTHETIC A',
             sources=[{'dataset': 'meta', 'license': 'x', 'record_id': None, 'update_time': None}], overture_version=None, confidence=None)]
    case = dict(id='s', op='bind', city=city, category=cat, places=places)
    rp = run_tests.py_case(case, d3, ev, {})['result'][0]
    rj = run_node(app, [case], data=d3)
    rj = rj['s']['result'][0] if rj else None
    for impl, r in (('py', rp), ('js', rj)):
        if r is None:
            continue
        codes = [f['code'] for f in r['nearest']['flags']]
        out.append((impl, r['nearest']['key'], r['tie'] and r['tie']['code'], codes))
        if r['nearest']['key'] != 'source:syn-a' or not r['tie'] or r['tie']['code'] != 'tie_equal_distance' or 'record_id_missing' not in codes:
            bad.append(f'{impl} synthetic tie/provenance: {r["nearest"]["key"]}, {r["tie"]}, {codes}')
    ev_b = run_tests.py_case(dict(id='e', op='evidence', city=city, category=cat, keys=['source:syn-b']), d3, ev, {})['result'][0]
    if [f['code'] for f in ev_b['result']['flags']] != ['no_provenance_records']:
        bad.append(f'py syn-b flags {ev_b["result"]["flags"]}')
    # 3) срез без QA: «замечаний нет» не выдаётся, есть qa_unavailable
    ev4 = json.loads(json.dumps(ev))
    del ev4['cities'][city]['qa']
    k0 = 'source:' + sorted(p['id'] for p in data['cities'][city]['places'] if p['group'] == cat)[0]
    e4 = run_tests.py_case(dict(id='q', op='evidence', city=city, category=cat, keys=[k0]), data, ev4, {})['result'][0]['result']
    j4 = run_node(app, [dict(id='q', op='evidence', city=city, category=cat, keys=[k0])], evidence=ev4)
    j4 = j4['q']['result'][0]['result'] if j4 else None
    for impl, e in (('py', e4), ('js', j4)):
        if e is not None and 'qa_unavailable' not in [f['code'] for f in e['flags']]:
            bad.append(f'{impl}: срез без QA не помечен qa_unavailable')
    out.append(('qa_unavailable', [f['code'] for f in e4['flags']]))
    _rec('S3-stale-and-synthetic', 'FAIL' if bad else 'PASS',
         'таблица чужого среза/версии → stale_table (JS, Python); синтетическая ничья на равном расстоянии → tie_equal_distance, '
         'меньший ID; запись без record_id/sources[] помечена; срез без QA → qa_unavailable' if not bad else '; '.join(bad),
         observations=[str(o) for o in out])


def v1_cross_check(doc, py, jsr, data, ev, app):
    """Сверка с действующим модулем сборки web/whatif.js (v1): nearest_before по тем же точкам."""
    node = shutil.which('node')
    if not node or not (app / 'web/whatif.js').exists():
        _rec('S3-v1-whatif-consistency', 'SKIP', 'нет node или web/whatif.js в сборке')
        return
    st1 = json.loads((HERE / 'fixtures/stage1.json').read_text(encoding='utf-8'))
    req = []
    for c in st1['cases']:
        if c['id'].endswith('-max-table'):
            for cat in ('school', 'outpatient_clinic'):
                req.append(dict(id=f'{c["city"]}-{cat}', city=c['city'], category=cat, points=c['places']['control_points']))
    code = r'''
const fs = require("fs"), path = require("path");
const [app, reqf, geo] = process.argv.slice(1);
const W = require(path.join(app, "web/whatif.js")), G = require(geo);
const load = (f) => { const t = fs.readFileSync(path.join(app, "web", f), "utf8"); return JSON.parse(t.slice(t.indexOf("{"), t.trimEnd().lastIndexOf(";"))); };
const data = load("data.js"), ev = load("evidence.js");
const out = [];
for (const r of JSON.parse(fs.readFileSync(reqf, "utf8"))) {
  const v1 = W.compute(data.cities[r.city].places, r.category, r.points.map((p) => ({ id: p.id, lon: p.lon, lat: p.lat })), null);
  const ctx = G.buildGeoContext(data, ev, r.city, r.category);
  const v = G.validatePlaces(ctx, { control_points: r.points, candidates: [] });
  const t = G.distanceTable(ctx, v.control_points, []);
  out.push({ id: r.id, v1: v1.rows.map((x) => x.nearest_before), v2: t.baseline.map((b) => b && b.id),
    v1_m: v1.rows.map((x) => x.before), v2_mm: t.baseline.map((b) => b && b.mm) });
}
process.stdout.write(JSON.stringify(out));
'''
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        json.dump(req, fh)
        path = fh.name
    r = subprocess.run([node, '-e', code, str(app), path, str(JS or HERE / 'geo_v2.js')], capture_output=True, text=True, timeout=300)
    Path(path).unlink()
    if r.returncode:
        _rec('S3-v1-whatif-consistency', 'FAIL', f'node: {r.stderr[-300:]}')
        return
    res = json.loads(r.stdout)
    diff = [(x['id'], i) for x in res for i, (a, b) in enumerate(zip(x['v1'], x['v2'])) if a != b]
    mm = [(x['id'], i) for x in res for i, (m, q) in enumerate(zip(x['v1_m'], x['v2_mm'])) if (m is None) != (q is None) or (m is not None and round(m * 1000) != q)]
    n = sum(len(x['v1']) for x in res)
    _rec('S3-v1-whatif-consistency', 'FAIL' if diff or mm else 'PASS',
         f'{n} точек (25 × 2 города × 2 категории): ближайшая исходная запись geo_v2 = nearest_before web/whatif.js (v1) сборки — '
         f'расхождений {len(diff)}; мм = round(before·1000) — расхождений {len(mm)}', diff=diff[:10], mm=mm[:10])


EXTRA['3'] = [provenance_qa_independent, stale_and_synthetic, v1_cross_check]
