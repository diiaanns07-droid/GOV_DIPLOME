"""K03 r9, этап 1: fixtures сканирования настоящих source ID и seeded synthetic сценариев для plan.js.

  python3 research/round-9-results/K03/make_stage1_scan.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>

real-sources: контрольная точка в координатах КАЖДОЙ записи категории (оба города, обе категории). Ожидание по построению:
  до = 0 мм, ближайшая — запись с меньшим ID среди записей категории в тех же координатах (ничья раскрыта списком tied_ids);
  кандидаты поставлены поверх записей: после = 0 мм и ближайшей остаётся source (ничья source < hypothetical).
random: 8 сценариев на срез, 25 точек и 16 кандидатов внутри bbox (seed фиксирован), 3 кандидата поверх записей; выбор 0..5.
  Ожидание вычисляет независимый оракул K03 r8 во время прогона. Точки, веса и кандидаты — synthetic, не данные города.
"""
import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import parse_js, sha256_file, u16  # noqa: E402

SEED = 20261006


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data = parse_js(app / 'web/data.js')
    rnd = random.Random(SEED)
    cases = []
    for city in ('astana', 'shymkent'):
        c = data['cities'][city]
        W, S, E, N = c['bbox']
        for cat in ('school', 'outpatient_clinic'):
            P = f'{city[:3].upper()}{"S" if cat == "school" else "C"}'
            srcs = sorted((p for p in c['places'] if p['group'] == cat), key=lambda p: u16(p['id']))
            at = {}
            for p in srcs:
                at.setdefault((p['lon'], p['lat']), []).append(p['id'])
            for b in range(0, len(srcs), 25):
                chunk = srcs[b:b + 25]
                cps = [{'id': f'at{b + k:02d}', 'lon': p['lon'], 'lat': p['lat'], 'weight': 1} for k, p in enumerate(chunk)]
                cands = [{'id': f'on{k:02d}', 'lon': p['lon'], 'lat': p['lat'], 'category': cat, 'kind': 'hypothetical', 'cost': 1}
                         for k, p in enumerate(chunk[:16])]
                expect = {cp['id']: {'base_mm': 0, 'base_id': min(at[(p['lon'], p['lat'])], key=u16),
                                     'tied_ids': sorted(at[(p['lon'], p['lat'])], key=u16), 'record': p['id'],
                                     'after_kind': 'source', 'after_mm': 0}
                          for cp, p in zip(cps, chunk)}
                cases.append(dict(id=f'{P}-real-sources-{b // 25}', kind='real_sources', city=city, category=cat,
                                  places={'control_points': cps, 'candidates': cands}, selected_ids=[q['id'] for q in cands[:5]],
                                  expect=expect))
            for k in range(8):
                cps = [{'id': f'p{i:02d}', 'lon': round(rnd.uniform(W, E), 7), 'lat': round(rnd.uniform(S, N), 7),
                        'weight': rnd.randint(1, 100)} for i in range(25)]
                cands = [{'id': f'c{i:02d}', 'lon': round(rnd.uniform(W, E), 7), 'lat': round(rnd.uniform(S, N), 7),
                          'category': cat, 'kind': 'hypothetical', 'cost': rnd.randint(1, 1000)} for i in range(13)]
                for i, p in enumerate(rnd.sample(srcs, 3)):
                    cands.append({'id': f'c{13 + i:02d}', 'lon': p['lon'], 'lat': p['lat'], 'category': cat, 'kind': 'hypothetical',
                                  'cost': rnd.randint(1, 1000)})
                rnd.shuffle(cands)
                sel = sorted(q['id'] for q in rnd.sample(cands, rnd.randint(0, 5)))
                cases.append(dict(id=f'{P}-random-{k}', kind='random', city=city, category=cat,
                                  places={'control_points': cps, 'candidates': cands}, selected_ids=sel))
    doc = dict(schema='k03-r9-stage1-scan', seed=SEED,
               description='Сканирование nearest/ties на настоящих source ID и seeded synthetic сценариях. Контрольные точки, веса, '
                           'стоимости и кандидаты — synthetic; координаты real_sources — копии координат записей data.js.',
               target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                           data_js_sha256=sha256_file(app / 'web/data.js'), evidence_js_sha256=sha256_file(app / 'web/evidence.js')),
               cases=cases)
    (HERE / 'fixtures').mkdir(exist_ok=True)
    (HERE / 'fixtures/stage1_scan.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'stage1_scan: {len(cases)} cases')


if __name__ == '__main__':
    main()
