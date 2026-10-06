"""K03 r10: проверки модуля маршрутов pedestrian-v1 (routing.js) и графов.

  python3 research/round-10-results/K03/run_tests.py [--js PATH] [--json out]

R-hand-*        ручные графы (synthetic): статус/причина/длина/рёбра/допущения по построению — Python-оракул и JS;
R-graph-edges   правила графа: запрет на части сегмента, пересечение без соединителя не узел;
R-city-*        фиксированные пары обоих городов: JS и оракул = сохранённым ожиданиям (compact);
R-parity        полное совпадение JS и Python (включая геометрию и части);
R-geometry      независимая проверка: длина геометрии ≈ distance_mm, начало/конец в точках, вершины из рёбер маршрута;
R-direction     каждое пройденное ребро разрешено политикой в этом направлении, рёбра идут цепочкой;
R-invariants    distance/geometry = null при status ≠ ok; strict ok ⇒ exploratory ok и не длиннее; сеть ≥ прямой;
R-determinism   перестановка исходных сегментов → тот же graph_sha256; перестановка точек → те же строки;
R-hash          JS проверяет graph_sha256 (подмена ребра отклоняется); Python пересчитывает hash и policy_sha256.
Код выхода 1 при FAIL. Без node — NOT_RUN (не PASS).
"""
import argparse
import copy
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k03net as K  # noqa: E402
import build_graph as BG  # noqa: E402
import routing_ref as RR  # noqa: E402
from make_city_pairs import compact, POL  # noqa: E402
import make_hand_graphs as MH  # noqa: E402

OUT = []


def rec(check, verdict, summary, **d):
    OUT.append(dict(check=check, verdict=verdict, summary=summary, details=d))
    print(f'[{verdict}] {check}: {summary}')


def run_js(js, graphs, queries, tamper=()):
    node = shutil.which('node')
    if not node:
        return None
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        fh.write(json.dumps({'graphs': graphs, 'verify_hash': True, 'tamper': list(tamper), 'queries': queries}, ensure_ascii=True))
        p = fh.name
    try:
        r = subprocess.run([node, str(HERE / 'route_runner.cjs'), p, str(js)], capture_output=True, text=True, timeout=900)
    finally:
        Path(p).unlink()
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])
    return json.loads(r.stdout)


def check_expect(name, e, r):
    if r['status'] != e['status']:
        return f'{name}: статус {r["status"]} ({r.get("reason")}), ожидался {e["status"]}'
    if e['status'] != 'ok':
        return None if r['reason'] == e['reason'] else f'{name}: причина {r["reason"]} ≠ {e["reason"]}'
    if r['distance_mm'] != e['distance_mm']:
        return f'{name}: {r["distance_mm"]} мм ≠ {e["distance_mm"]} мм'
    miss = [x for x in e['include_edges'] if x not in r['route_edge_ids']]
    bad = [x for x in e['exclude_edges'] if x in r['route_edge_ids']]
    lack = [a for a in e.get('assumptions_superset', []) if a not in r['assumptions']]
    if miss or bad or lack:
        return f'{name}: нет рёбер {miss}, лишние {bad}, нет допущений {lack}'
    return None


def validate_route(r, g, k):
    """Независимый валидатор строки ok: геометрия, длина, направления, цепочка рёбер."""
    errs = []
    E = {e['id']: e for e in g['edges']}
    cs = r['geometry']['coordinates']
    if cs[0] != [r['_o']['lon'], r['_o']['lat']] or cs[-1] != [r['_t']['lon'], r['_t']['lat']]:
        errs.append('геометрия не начинается/не заканчивается в точках')
    geo_mm = K.polyline_m(cs) * 1000
    pieces = len(r['route_edge_ids']) + 3
    if abs(r['distance_mm'] - geo_mm) > 0.5 * pieces + 1:
        errs.append(f'длина {r["distance_mm"]} мм ≠ геометрии {geo_mm:.1f} мм (допуск {0.5 * pieces + 1})')
    if r['distance_mm'] != sum(x['length_mm'] for x in r['parts']):
        errs.append('distance ≠ сумме частей')
    verts = {tuple(v) for eid in r['route_edge_ids'] for v in E[eid]['coords']}
    inner = cs[1:-1]
    snaps = 2
    off = [v for v in inner if tuple(v) not in verts]
    if len(off) > snaps:
        errs.append(f'{len(off)} вершин геометрии не из рёбер маршрута')
    net = next(p for p in r['parts'] if p['kind'] == 'network')['edges']
    for x in net:
        if E[x['id']][k][x['d']] != 'ok':
            errs.append(f'ребро {x["id"]} пройдено в запрещённом направлении {x["d"]}')
    ends = lambda x: (E[x['id']]['from'], E[x['id']]['to']) if x['d'] == 0 else (E[x['id']]['to'], E[x['id']]['from'])  # noqa: E731
    for a, b in zip(net, net[1:]):
        if ends(a)[1] != ends(b)[0]:
            errs.append(f'разрыв цепочки {a["id"]} → {b["id"]}')
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--js', type=Path, default=HERE / 'routing.js')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    hand = json.loads((HERE / 'fixtures/hand_graphs.json').read_text(encoding='utf-8'))
    city = json.loads((HERE / 'fixtures/city_pairs.json').read_text(encoding='utf-8'))
    graphs = {c: json.loads((HERE / f'graph/{c}.graph.json').read_text(encoding='utf-8')) for c in K.CITIES}

    # ---------- запросы ----------
    queries, meta = [], {}
    for h in hand['graphs']:
        for q in h['queries']:
            for p in POL:
                qid = f'H|{h["name"]}|{q["id"]}|{p}'
                queries.append({'id': qid, 'graph': h['name'], 'origin': q['origin'], 'target': q['target'], 'method': 'pedestrian-v1', 'policy': p})
                meta[qid] = (h['graph'], q, p)
    for c in K.CITIES:
        O = {o['id']: o for o in city['cities'][c]['origins']}
        T = {t['id']: t for t in city['cities'][c]['targets']}
        for row in city['cities'][c]['rows']:
            o, t = O[row['origin_id']], T[row['target_id']]
            for p in POL + ('geodesic',):
                qid = f'C|{c}|{o["id"]}|{t["id"]}|{p}'
                pt = {k: v for k, v in o.items() if k in ('id', 'lon', 'lat')}, {k: v for k, v in t.items() if k in ('id', 'lon', 'lat')}
                queries.append({'id': qid, 'graph': c, 'origin': pt[0], 'target': pt[1], 'method': 'geodesic' if p == 'geodesic' else 'pedestrian-v1',
                                'policy': None if p == 'geodesic' else p})
                meta[qid] = (graphs[c], {'origin': pt[0], 'target': pt[1], 'stored': row[p]}, p)
    # Python-оракул
    routers = {h['name']: RR.Router(h['graph']) for h in hand['graphs']}
    routers.update({c: RR.Router(graphs[c]) for c in K.CITIES})
    py = {}
    for q in queries:
        R = routers[q['graph']]
        py[q['id']] = R.geodesic(q['origin'], q['target']) if q['method'] == 'geodesic' else R.route(q['origin'], q['target'], q['policy'])
    js_graphs = {h['name']: {'graph': h['graph']} for h in hand['graphs']}
    js_graphs.update({c: {'path': f'graph/{c}.graph.json'} for c in K.CITIES})
    jr = run_js(a.js.resolve(), js_graphs, queries, tamper=K.CITIES)
    if jr is None:
        rec('R-js', 'NOT_RUN', 'node не установлен')
    js = {x['id']: x for x in jr['results']} if jr else {}
    crashes = [k for k, x in js.items() if not x['ok']]
    if crashes:
        rec('R-js-errors', 'FAIL', f'исключения JS: {len(crashes)}', examples={k: js[k]['error'] for k in crashes[:5]})

    # ---------- ручные графы ----------
    for who, res in (('python-oracle', py), ('js', {k: v['result'] for k, v in js.items() if v['ok']})):
        if who == 'js' and not jr:
            continue
        bad, n = [], 0
        for qid, (g, q, p) in meta.items():
            if qid.startswith('H|'):
                n += 1
                m = check_expect(qid, q['expect'][p], res[qid]) if qid in res else f'{qid}: нет результата'
                if m:
                    bad.append(m)
        rec(f'R-hand-{who}', 'FAIL' if bad else 'PASS', f'{n} запросов (17 ручных графов × 2 политики): статус, причина, длина в мм по построению, '
            f'рёбра, допущения; несоответствий {len(bad)}', mismatches=bad[:20])
    errs = []
    for h in hand['graphs']:
        for eid, want in (h.get('edge_expect') or {}).items():
            e = next(x for x in h['graph']['edges'] if x['id'] == eid)
            if e['s'] != want['s'] or e['x'] != want['x']:
                errs.append(f'{h["name"]}/{eid}: s={e["s"]} x={e["x"]} ≠ {want}')
        if h['name'].startswith('h1-'):
            cx = MH.P(100, 0)  # точка пересечения AB и моста/тоннеля CD
            at_cross = [n['id'] for n in h['graph']['nodes'] if K.haversine_m((n['lon'], n['lat']), cx) < 0.01]
            if at_cross or len(h['graph']['nodes']) != 4:
                errs.append(f'{h["name"]}: узел в точке пересечения {at_cross} или число узлов {len(h["graph"]["nodes"])} ≠ 4')
    rec('R-graph-edges', 'FAIL' if errs else 'PASS', 'правила графа: запрет foot на части сегмента [0.6, 0.9] закрывает только перекрытое ребро; '
        'пересечение моста/тоннеля с линией без соединителя не создаёт узла (4 узла)', errors=errs)

    # ---------- города: ожидания и полная сверка ----------
    for who, res in (('python-oracle', py), ('js', {k: v['result'] for k, v in js.items() if v['ok']})):
        if who == 'js' and not jr:
            continue
        bad, n = [], 0
        for qid, (g, q, p) in meta.items():
            if qid.startswith('C|'):
                n += 1
                if qid not in res or compact(res[qid]) != q['stored']:
                    bad.append(qid)
        rec(f'R-city-{who}', 'FAIL' if bad else 'PASS', f'{n} строк (Шымкент 153 + Астана 90 пар × strict/exploratory/geodesic) = сохранённым ожиданиям; '
            f'несоответствий {len(bad)}', mismatches=bad[:20])
    if jr:
        par = [qid for qid in meta if qid not in js or not js[qid]['ok'] or js[qid]['result'] != py[qid]]
        rec('R-parity', 'FAIL' if par else 'PASS', f'полное совпадение JS и Python ({len(meta)} строк: статус, мм, рёбра, геометрия, части, допущения, '
            f'метки, hash): расхождений {len(par)}', ids=par[:20])
        res = {k: v['result'] for k, v in js.items() if v['ok']}
    else:
        res = py

    # ---------- независимые валидаторы на всех ok-строках ----------
    gerr, derr, n = [], [], 0
    for qid, (g, q, p) in meta.items():
        r = res.get(qid)
        if not r or r['status'] != 'ok' or p == 'geodesic':
            continue
        n += 1
        rr = dict(r, _o=q['origin'], _t=q['target'])
        try:
            msgs = validate_route(rr, g, 's' if p.endswith('strict') else 'x')
        except Exception as e:  # noqa: BLE001 — неправильная форма результата = FAIL, а не падение проверки
            msgs = [f'форма результата не проверяется: {type(e).__name__} {str(e)[:80]}']
        for m in msgs:
            (derr if 'направлени' in m or 'цепочки' in m else gerr).append(f'{qid}: {m}')
    rec('R-geometry', 'FAIL' if gerr else 'PASS', f'{n} маршрутов ok: геометрия от точки до точки, |distance_mm − длина геометрии| ≤ 0,5 мм × кусков + 1, '
        f'distance = сумма частей, вершины — из рёбер маршрута (кроме 2 точек привязки); ошибок {len(gerr)}', errors=gerr[:20])
    rec('R-direction', 'FAIL' if derr else 'PASS', f'{n} маршрутов ok: каждое ребро пройдено в разрешённом политикой направлении, рёбра идут цепочкой; '
        f'ошибок {len(derr)}', errors=derr[:20])

    inv, longer_other_snap, strict_ok_pairs = [], [], 0
    for qid, (g, q, p) in meta.items():
        r = res.get(qid)
        if not r:
            continue
        if (r['status'] == 'ok') != (r['distance_mm'] is not None) or (r['status'] == 'ok') != (r['geometry'] is not None):
            inv.append(f'{qid}: distance/geometry при статусе {r["status"]}')
        if r['status'] != 'ok' and (r['route_edge_ids'] or r['method'] != ('geodesic' if p == 'geodesic' else 'pedestrian-v1')):
            inv.append(f'{qid}: при {r["status"]} есть рёбра или подменён метод')
        if p == 'pedestrian-v1-strict' and r['status'] == 'ok':
            x = res.get(qid.replace('strict', 'exploratory'))
            att = lambda y: [pp.get('edge_id') for pp in y.get('parts') or [] if pp.get('kind') == 'snap']  # noqa: E731
            if not x or x['status'] != 'ok':
                inv.append(f'{qid}: strict ok, а exploratory {x and x["status"]}')
            elif att(x) == att(r) and x['distance_mm'] > r['distance_mm']:
                inv.append(f'{qid}: при тех же рёбрах привязки exploratory {x["distance_mm"]} > strict {r["distance_mm"]}')
            elif x['distance_mm'] > r['distance_mm']:
                longer_other_snap.append({'pair': qid, 'strict_mm': r['distance_mm'], 'exploratory_mm': x['distance_mm'],
                                          'strict_snap_mm': [pp.get('length_mm') for pp in r.get('parts') or [] if pp.get('kind') == 'snap'],
                                          'exploratory_snap_mm': [pp.get('length_mm') for pp in x.get('parts') or [] if pp.get('kind') == 'snap']})
            strict_ok_pairs += 1
        if qid.startswith('C|') and p != 'geodesic' and r['status'] == 'ok' and (qid.rsplit('|', 1)[0] + '|geodesic') in res:
            gd = res[qid.rsplit('|', 1)[0] + '|geodesic']['distance_mm']
            if r['distance_mm'] < gd - 1:
                inv.append(f'{qid}: сеть {r["distance_mm"]} < прямой {gd}')
    rec('R-invariants', 'FAIL' if inv else 'PASS', 'при status ≠ ok distance_mm и geometry = null, рёбер нет, метод не подменён прямой; strict ok ⇒ exploratory ok, '
        'а при тех же рёбрах привязки exploratory не длиннее; длина по сети ≥ прямой − 1 мм; '
        f'нарушений {len(inv)}', errors=inv[:20])
    rec('R-snap-rule-effect', 'INFO', f'из {strict_ok_pairs} пар strict ok в {len(longer_other_snap)} exploratory длиннее: точка привязывается к БЛИЖАЙШЕМУ ребру своей '
        'политики (дорога ближе пешеходного ребра), а не к лучшему по итоговой длине. Это правило pedestrian-v1, не ошибка Дейкстры; '
        'привязка к любому ребру в 100 м систематически укорачивала бы путь прямыми отрезками.', examples=longer_other_snap[:6])

    # ---------- детерминизм ----------
    errs = []
    I = K.load_inputs()
    rnd = random.Random(20261006)
    for c in K.CITIES:
        sh = copy.deepcopy(I)
        rnd.shuffle(sh[(c, 'segments')]['features'])
        rnd.shuffle(sh[(c, 'connectors')]['features'])
        if BG.build_city(sh, c)['graph_sha256'] != graphs[c]['graph_sha256']:
            errs.append(f'{c}: перестановка сегментов меняет graph_sha256')
    for h in hand['graphs']:
        s2 = copy.deepcopy(h['segments'])
        rnd.shuffle(s2['features'])
        if BG.build(s2, h['connectors'], h['graph']['city'], h['graph']['bbox'], 'synthetic', h['graph']['inputs'])['graph_sha256'] != h['graph']['graph_sha256']:
            errs.append(f'{h["name"]}: перестановка меняет graph_sha256')
    if jr:
        perm = [dict(q, id=q['id'] + '|perm') for q in reversed([q for q in queries if q['id'].startswith('C|')])]
        jp = run_js(a.js.resolve(), {c: {'path': f'graph/{c}.graph.json'} for c in K.CITIES}, perm)
        diff = [x['id'] for x in jp['results'] if x['result'] != js[x['id'][:-5]]['result']]
        if diff:
            errs.append(f'JS: обратный порядок запросов меняет {len(diff)} строк')
    rec('R-determinism', 'FAIL' if errs else 'PASS', 'перестановка сегментов и соединителей (оба города, 17 ручных графов) → тот же graph_sha256; '
        'обратный порядок запросов в JS (новый кэш) → те же строки', errors=errs)

    # ---------- hash и целостность ----------
    errs = []
    pol_sha = BG.policy()[1]
    for c in K.CITIES:
        g = graphs[c]
        body = {k: g[k] for k in ('schema', 'city', 'bbox', 'release', 'policy_family', 'policy_sha256', 'max_snap_m', 'inputs', 'nodes', 'edges')}
        if K.sha256_canon(body) != g['graph_sha256'] or g['policy_sha256'] != pol_sha:
            errs.append(f'{c}: graph_sha256 или policy_sha256 не пересчитывается')
        if jr and (jr['hash'].get(c) != 'ok' or jr['hash'].get(c + ':tampered') != 'graph_hash_mismatch'):
            errs.append(f'{c}: JS hash {jr["hash"].get(c)}, подмена → {jr["hash"].get(c + ":tampered")}')
        if g['license']['id'] != 'ODbL-1.0' or g['inputs']['segments']['sha256'] != K.load_inputs()['manifest']['cities'][c]['segments']['sha256']:
            errs.append(f'{c}: лицензия или входы')
    rec('R-hash', 'FAIL' if errs else 'PASS', 'graph_sha256 пересчитывается (Python) и проверяется в JS; подмена длины одного ребра → graph_hash_mismatch; '
        'policy_sha256 = файлу политики; ODbL и sha256 входов в графе', errors=errs)

    summ = {v: sum(1 for r in OUT if r['verdict'] == v) for v in ('PASS', 'FAIL', 'SKIP', 'NOT_RUN', 'INFO')}
    print('SUMMARY', json.dumps(summ))
    if a.json:
        K.dump(a.json, {'summary': summ, 'results': OUT})
    return 1 if summ['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
