"""K03 round 7: тест point_check (Python и JS) на fixtures.json; опционально сверка с bbox проверяемой сборки.

  python3 research/round-7-results/K03/test_point_check.py [--app-root <копия prototypes/city-evidence>] [--js <путь к point_check.js>] [--json out]

--app-root : bbox/edges_inclusive из web/evidence.js и web/data.js сборки должны совпасть с fixtures.json,
             иначе TEST_INCOMPATIBLE (пересоздать fixtures make_fixtures.py для этого SHA); без него — SKIP сверки.
--js       : проверить другую копию помощника (например, интегрированную сборщиком) на тех же fixtures.
Код выхода 1 при FAIL или TEST_INCOMPATIBLE. Пропуск (нет node) — SKIP, не PASS.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import point_check as P  # noqa: E402

RES = []


def rec(check, verdict, summary, **d):
    RES.append(dict(check=check, verdict=verdict, summary=summary, details=d))
    print(f'[{verdict}] {check}: {summary}')


def parse_js(p):
    t = Path(p).read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def py_results(doc):
    out = []
    for f in doc['fixtures']:
        slice_ = dict(doc['slices'][f['city']], **(f['slice_override'] or {}))
        others = [s for c, s in doc['slices'].items() if c != f['city']]
        point = json.loads(f['raw_json']) if f['raw_json'] is not None else f['point']
        r = P.check_point(slice_, point, others)
        out.append(dict(id=f['id'], ok=r['ok'], code=r['code'], point=r['point'], on_edge=r['on_edge'],
                        other_city_id=r.get('other_city_id')))
    return out


def compare(name, doc, got):
    exp = {f['id']: f for f in doc['fixtures']}
    bad = []
    for g in got:
        f = exp[g['id']]
        e = f['expected']
        if (g['ok'], g['code']) != (e['ok'], e['code']):
            bad.append(f"{g['id']}: ожидалось {e['code']}, получено {g['code']}")
        elif g['ok'] and g['point'] != (f['point'] if f['raw_json'] is None else json.loads(f['raw_json'])):
            bad.append(f"{g['id']}: координаты изменены ({g['point']})")
    missing = sorted(set(exp) - {g['id'] for g in got})
    rec(name, 'FAIL' if bad or missing else 'PASS',
        f'{len(got)} fixtures: несовпадений {len(bad)}' + (f'; нет результата для {missing}' if missing else ''), mismatches=bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixtures', type=Path, default=HERE / 'fixtures.json')
    ap.add_argument('--app-root', type=Path)
    ap.add_argument('--js', type=Path, default=HERE / 'point_check.js')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    doc = json.loads(a.fixtures.read_text(encoding='utf-8'))
    print(f"fixtures: {len(doc['fixtures'])}, построены на {doc['target']['sha']}")
    if a.app_root:
        app = a.app_root.resolve()
        ev, data = parse_js(app / 'web/evidence.js'), parse_js(app / 'web/data.js')
        diff = []
        for c, s in doc['slices'].items():
            su = ev['cities'][c]['spatial_unit']
            if su['bbox'] != s['bbox'] or data['cities'][c]['bbox'] != s['bbox'] or su['edges_inclusive'] != s['edges_inclusive']:
                diff.append(f'{c}: fixtures {s["bbox"]}/{s["edges_inclusive"]} ≠ сборка {su["bbox"]}/{su["edges_inclusive"]}')
        rec('slices-match-app', 'TEST_INCOMPATIBLE' if diff else 'PASS',
            '; '.join(diff) + ' — пересоздайте fixtures make_fixtures.py для этой сборки' if diff
            else 'bbox и edges_inclusive обоих городов в web/evidence.js и web/data.js совпадают с fixtures', diff=diff)
    else:
        rec('slices-match-app', 'SKIP', 'без --app-root соответствие fixtures текущей сборке не проверено')
    py = py_results(doc)
    compare('python-point_check', doc, py)
    node = shutil.which('node')
    if not node:
        rec('js-point_check', 'SKIP', 'node не установлен')
    else:
        r = subprocess.run([node, str(HERE / 'test_point_check.cjs'), str(a.fixtures), str(a.js.resolve())],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            rec('js-point_check', 'FAIL', f'node код {r.returncode}: {r.stderr[-300:]}')
        else:
            js = json.loads(r.stdout)
            compare(f'js-point_check ({a.js.name})', doc, js)
            par = [p['id'] for p, j in zip(py, js) if p != j]
            rec('python-js-parity', 'FAIL' if par else 'PASS',
                f'Python и JS дают одинаковые ok/code/point/on_edge/other_city_id: расхождений {len(par)}', ids=par)
    summ = {v: sum(1 for r in RES if r['verdict'] == v) for v in ('PASS', 'FAIL', 'SKIP', 'TEST_INCOMPATIBLE')}
    print('SUMMARY', json.dumps(summ))
    if a.json:
        a.json.write_text(json.dumps(dict(fixtures_target=doc['target'], summary=summ, results=RES), ensure_ascii=False,
                                     indent=1) + '\n', encoding='utf-8')
    return 1 if summ['FAIL'] or summ['TEST_INCOMPATIBLE'] else 0


if __name__ == '__main__':
    sys.exit(main())
