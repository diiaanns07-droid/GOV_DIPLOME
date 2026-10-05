"""K03 r8, этап 3: fixtures привязки ближайшей записи к provenance/QA (оба города, обе категории).

  python3 research/round-8-results/K03/make_stage3.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>
Ожидания — по данным сборки (data.js/evidence.js) и построению; stage_checks.py сверяет каждое поле provenance/QA
с исходными файлами независимо от модуля.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_fixtures import parse_js  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    cases = []

    def case(cid, op, city, category, expect, why=None, **kw):
        cases.append(dict(id=cid, op=op, city=city, category=category, expect=expect, why=why, **kw))

    for city in ('astana', 'shymkent'):
        P = city[:3].upper()
        places = data['cities'][city]['places']
        W, S, E, N = data['cities'][city]['bbox']
        coloc = {i: len(g['ids']) for g in ev['cities'][city]['qa']['colocated'] for i in g['ids']}
        for cat in ('school', 'outpatient_clinic'):
            C = 'S' if cat == 'school' else 'C'
            srcs = sorted((p for p in places if p['group'] == cat), key=lambda p: p['id'])
            keys = ['source:' + p['id'] for p in srcs]
            exp = {f'[{i}].ok': True for i in range(len(keys))}
            exp.update({f'[{i}].result.position_status': 'source_reported_unverified' for i in range(len(keys))})
            exp.update({f'[{i}].result.confirmation': 'not_confirmed' for i in range(len(keys))})
            n = len(keys)
            exp.update({f'[{n}].ok': False, f'[{n}].error.code': 'unknown_source',
                        f'[{n + 1}].ok': False, f'[{n + 1}].error.code': 'unknown_source',
                        f'[{n + 2}].ok': False, f'[{n + 2}].error.code': 'unknown_source'})
            other = next(p for p in places if p['group'] != cat)
            case(f'{P}{C}-evidence-all', 'evidence', city, cat, {'ok': True, 'result': exp},
                 keys=keys + ['source:does-not-exist', 'hypothetical:' + srcs[0]['id'], 'source:' + other['id']],
                 why='все записи категории разрешаются; неизвестный ключ, hypothetical и запись другой категории — unknown_source')
            by_xy = {}
            for p in srcs:
                by_xy.setdefault((p['lon'], p['lat']), []).append(p['id'])
            single = next(p for p in srcs if len(by_xy[(p['lon'], p['lat'])]) == 1 and p['id'] not in coloc)
            case(f'{P}{C}-bind-single', 'bind', city, cat,
                 {'ok': True, 'result': {'[0].status': 'ok', '[0].nearest.key': 'source:' + single['id'], '[0].tied_count': 1,
                                         '[0].tie': None, '[0].nearest.position_status': 'source_reported_unverified',
                                         '[0].nearest.confirmation': 'not_confirmed'}},
                 places={'control_points': [{'id': 'p', 'lon': single['lon'], 'lat': single['lat'], 'weight': 1}], 'candidates': []},
                 why='запись без общих координат: ничьи нет, но и «подтверждено» нет')
            for xy, ids in sorted(by_xy.items()):
                if len(ids) > 1:
                    ids = sorted(ids)
                    size = coloc.get(ids[0])
                    shared = sum(1 for p in places if (p['lon'], p['lat']) == xy) - 1
                    e = {'[0].nearest.key': 'source:' + ids[0], '[0].tied_count': len(ids), '[0].tie.code': 'tie_shared_coordinates',
                         '[0].tie.keys': ['source:' + i for i in ids], '[0].nearest.confirmation': 'not_confirmed'}
                    case(f'{P}{C}-bind-shared-{len(ids)}', 'bind', city, cat, {'ok': True, 'result': e},
                         places={'control_points': [{'id': 'p', 'lon': xy[0], 'lat': xy[1], 'weight': 1}], 'candidates': []},
                         why=f'{len(ids)} записей категории в одних координатах (COLOCATED: {size or "нет"}, всего в точке {shared + 1}): '
                             'ничья раскрыта, выбранная запись не становится подтверждённым местом')
                    break
            s0 = srcs[0]
            cx, cy = (W + E) / 2, (S + N) / 2
            same0 = ['source:' + i for i in sorted(by_xy[(s0['lon'], s0['lat'])])]
            case(f'{P}{C}-cand-evidence', 'cand_evidence', city, cat,
                 {'ok': True, 'result': {'[0].kind': 'hypothetical', '[0].position_status': 'hypothetical',
                                         '[0].confirmation': 'not_confirmed', '[0].flags[0].code': 'coincides_with_source',
                                         '[0].flags[0].sources': same0, '[1].flags': []}},
                 places={'control_points': [{'id': 'p', 'lon': cx, 'lat': cy, 'weight': 1}],
                         'candidates': [{'id': 'on', 'lon': s0['lon'], 'lat': s0['lat'], 'category': cat, 'kind': 'hypothetical', 'cost': 1},
                                        {'id': 'off', 'lon': cx, 'lat': cy, 'category': cat, 'kind': 'hypothetical', 'cost': 1}]},
                 why='кандидат поверх записи помечен coincides_with_source и остаётся hypothetical; кандидат в другом месте — без флагов')
    doc = dict(schema='k03-geo-v2-fixtures', stage=3,
               description='Этап 3: provenance/QA ближайшей записи, ничьи в общих координатах, кандидат поверх записи. '
                           'Контрольные точки и кандидаты — synthetic; записи — Overture из сборки.',
               target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                           data_js_sha256=hashlib.sha256((app / 'web/data.js').read_bytes()).hexdigest(),
                           evidence_js_sha256=hashlib.sha256((app / 'web/evidence.js').read_bytes()).hexdigest()),
               cases=cases)
    (HERE / 'fixtures/stage3.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'stage3: {len(cases)} cases')


if __name__ == '__main__':
    main()
