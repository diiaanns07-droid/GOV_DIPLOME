"""K03 r8: тесты геоадаптера city-plan-v2 — JS (node, без DOM) и независимый Python-оракул на одних fixtures.

  python3 research/round-8-results/K03/run_tests.py --app-root <копия prototypes/city-evidence> [--stages 1,2,3] [--js PATH] [--json out]

Для каждого случая: Python и JS сравниваются с ожиданием (ok/code/path) и друг с другом (полный результат).
Если data.js/evidence.js сборки не совпадают с fixtures (sha256) — TEST_INCOMPATIBLE: пересоздать fixtures для этого SHA.
Код выхода 1 при FAIL/TEST_INCOMPATIBLE. Без node — JS-часть SKIP (не PASS).
"""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geo_v2_ref as R  # noqa: E402

OUT = []


def rec(check, verdict, summary, **d):
    OUT.append(dict(check=check, verdict=verdict, summary=summary, details=d))
    print(f'[{verdict}] {check}: {summary}')


def parse_js(p):
    t = Path(p).read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def revive(v):
    if isinstance(v, list):
        return [revive(x) for x in v]
    if isinstance(v, dict):
        if set(v) == {'$num'}:
            return float(v['$num'].replace('Infinity', 'inf'))
        return {k: revive(x) for k, x in v.items()}
    return v


def py_case(c, data, ev, cache):
    if c['op'] == 'tomm':
        return {'ok': True, 'result': [R.to_mm(m) for m in c['values']]}
    if c['op'] == 'dist':
        return {'ok': True, 'result': [R.mm_between({'lon': a[0], 'lat': a[1]}, {'lon': b[0], 'lat': b[1]}) for a, b in c['pairs']]}
    try:
        k = (c['city'], c['category'])
        if k not in cache:
            cache[k] = R.build_context(data, ev, *k)
        ctx = cache[k]

        def one(f):
            try:
                return {'ok': True, 'result': f()}
            except R.GeoErr as e:
                return {'ok': False, 'error': {'code': e.code, 'path': e.path}}
        if c['op'] == 'evidence':
            return {'ok': True, 'result': [one(lambda key=key: R.source_evidence(ctx, key)) for key in c['keys']]}
        if c['op'] == 'bind_table':
            return {'ok': True, 'result': one(lambda: R.bind_nearest_sources(ctx, c['table']))}
        if c['op'] == 'context':
            return {'ok': True, 'result': ctx}
        v = R.validate_places(ctx, revive(c['places']), allow_empty_points=bool(c.get('allow_empty')))
        if c['op'] == 'validate':
            return {'ok': True, 'result': v}
        t = R.distance_table(ctx, v['control_points'], v['candidates'])
        if c['op'] == 'table':
            return {'ok': True, 'result': t}
        if c['op'] == 'bind':
            return {'ok': True, 'result': R.bind_nearest_sources(ctx, t)}
        if c['op'] == 'cand_evidence':
            return {'ok': True, 'result': [R.candidate_evidence(ctx, q) for q in v['candidates']]}
        return {'ok': True, 'result': [R.nearest_after(t, i, c.get('selected') or [], v['candidates'])
                                       for i in range(len(v['control_points']))]}
    except R.GeoErr as e:
        return {'ok': False, 'error': {'code': e.code, 'path': e.path}}


def norm(x):
    """Сравнение без различия 1 и 1.0 (в JS одно число)."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, list):
        return [norm(i) for i in x]
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    return x


def check_expect(name, c, r):
    e = c['expect']
    if r.get('crash'):
        return f'{name}: исключение {r["crash"][:200]}'
    if r['ok'] != e['ok']:
        return f'{name}: ok={r["ok"]} ({r.get("error")}), ожидалось {e}'
    if not e['ok'] and (r['error']['code'], r['error']['path']) != (e['code'], e['path']):
        return f'{name}: {r["error"]} ≠ ожидаемого {e["code"]} @ {e["path"]}'
    for path, want in (e.get('result') or {}).items():
        got = get_path(r.get('result'), path)
        if norm(got) != norm(want):
            return f'{name}: {path} = {json.dumps(got, ensure_ascii=False)[:120]}, ожидалось {json.dumps(want, ensure_ascii=False)[:120]}'
    return None


def get_path(obj, path):
    """'a.b[2].c' → obj['a']['b'][2]['c']; отсутствие → '<missing>'."""
    import re
    cur = obj
    for tok in re.findall(r'[^.\[\]]+|\[\d+\]', path):
        try:
            cur = cur[int(tok[1:-1])] if tok.startswith('[') else cur[tok]
        except (KeyError, IndexError, TypeError):
            return '<missing>'
    return cur


def run_stage(fx_path, app, js, data, ev, extra_checks):
    doc = json.loads(fx_path.read_text(encoding='utf-8'))
    st = doc['stage']
    tgt = doc['target']
    have = {'data_js_sha256': hashlib.sha256((app / 'web/data.js').read_bytes()).hexdigest(),
            'evidence_js_sha256': hashlib.sha256((app / 'web/evidence.js').read_bytes()).hexdigest()}
    diff = [k for k in have if tgt.get(k) != have[k]]
    if diff:
        rec(f'S{st}-fixtures-match-build', 'TEST_INCOMPATIBLE',
            f'fixtures построены на {tgt["sha"][:12]}, а {diff} сборки другие — пересоздать make_fixtures для этого SHA', diff=diff)
        return
    rec(f'S{st}-fixtures-match-build', 'PASS', f'fixtures stage {st} построены на данных этой сборки ({tgt["sha"][:12]})')
    cache = {}
    py = {c['id']: py_case(c, data, ev, cache) for c in doc['cases']}
    bad_py = [m for c in doc['cases'] if (m := check_expect('py ' + c['id'], c, py[c['id']]))]
    rec(f'S{st}-python-oracle', 'FAIL' if bad_py else 'PASS', f'{len(doc["cases"])} случаев: несоответствий {len(bad_py)}', mismatches=bad_py[:20])
    node = shutil.which('node')
    if not node:
        rec(f'S{st}-js', 'SKIP', 'node не установлен')
        return
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        json.dump({'app_root': str(app), 'cases': doc['cases']}, fh, ensure_ascii=False)
        req = fh.name
    r = subprocess.run([node, str(HERE / 'node_runner.cjs'), req, str(js)], capture_output=True, text=True, timeout=600)
    Path(req).unlink()
    if r.returncode:
        rec(f'S{st}-js', 'FAIL', f'node код {r.returncode}: {r.stderr[-300:]}')
        return
    jsr = {x['id']: x for x in json.loads(r.stdout)}
    bad_js = [m for c in doc['cases'] if (m := check_expect('js ' + c['id'], c, jsr[c['id']]))]
    rec(f'S{st}-js ({Path(js).name})', 'FAIL' if bad_js else 'PASS', f'{len(doc["cases"])} случаев: несоответствий {len(bad_js)}', mismatches=bad_js[:20])
    par = [c['id'] for c in doc['cases'] if norm({k: v for k, v in jsr[c['id']].items() if k != 'id'}) != norm(py[c['id']])]
    rec(f'S{st}-js-python-parity', 'FAIL' if par else 'PASS',
        f'полное совпадение результатов JS и Python (контекст, места, мм, ничьи): расхождений {len(par)}', ids=par[:20])
    for fn in extra_checks.get(str(st), []):
        fn(doc, py, jsr, data, ev, app)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--stages', default='1')
    ap.add_argument('--js', type=Path, default=HERE / 'geo_v2.js')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    extra = {}
    try:
        import stage_checks  # noqa: E402  (этапы 2 и 3)
        stage_checks.REC = rec
        stage_checks.JS = a.js.resolve()
        extra = stage_checks.EXTRA
    except ImportError:
        pass
    for st in a.stages.split(','):
        run_stage(HERE / f'fixtures/stage{st}.json', app, a.js.resolve(), data, ev, extra)
    summ = {v: sum(1 for r in OUT if r['verdict'] == v) for v in ('PASS', 'FAIL', 'SKIP', 'TEST_INCOMPATIBLE')}
    print('SUMMARY', json.dumps(summ))
    if a.json:
        a.json.write_text(json.dumps(dict(summary=summ, results=OUT), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 1 if summ['FAIL'] or summ['TEST_INCOMPATIBLE'] else 0


if __name__ == '__main__':
    sys.exit(main())
