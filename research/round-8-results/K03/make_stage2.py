"""K03 r8, этап 2: воспроизводимые fixtures — края, lon/lat, одинаковые координаты, ничьи, QA-группы (оба города).

  python3 research/round-8-results/K03/make_stage2.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>
Ожидания заданы по построению (геометрически/по данным сборки), а не запуском модуля: run_tests.py сверяет JS и Python
с ними и между собой; stage_checks.py добавляет независимые проверки (геодезия, симметрия, перестановки, QA).
Контрольные точки и кандидаты — synthetic; исходные записи — Overture из сборки.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from make_fixtures import parse_js  # noqa: E402

R_EARTH = 6371008.8
M_PER_DEG_LAT = math.pi * R_EARTH / 180


def hav_m(a, b):  # только для подбора геометрии fixtures; проверяемые значения считают модули
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin(math.radians(b[1] - a[1]) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(min(1, max(0, h))))


def cp(i, lon, lat, w=1):
    return {'id': i, 'lon': lon, 'lat': lat, 'weight': w}


def cand(i, lon, lat, category, cost=1000):
    return {'id': i, 'lon': lon, 'lat': lat, 'category': category, 'kind': 'hypothetical', 'cost': cost}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    cases = []

    def case(cid, op, city, category, expect, places=None, why=None, **kw):
        cases.append(dict(id=cid, op=op, city=city, category=category, places=places, expect=expect, why=why, **kw))

    for city in ('astana', 'shymkent'):
        P = city[:3].upper()
        W, S, E, N = data['cities'][city]['bbox']
        cx, cy = (W + E) / 2, (S + N) / 2
        places = data['cities'][city]['places']
        for cat in ('school', 'outpatient_clinic'):
            srcs = sorted((p for p in places if p['group'] == cat), key=lambda p: p['id'])
            if not srcs:
                continue
            C = 'S' if cat == 'school' else 'C'
            # края: каждая сторона на 1e-9° снаружи — отказ; середина стороны — принята
            for side, (lon, lat) in {'W': (W, cy), 'E': (E, cy), 'S': (cx, S), 'N': (cx, N)}.items():
                case(f'{P}{C}-edge-{side}', 'validate', city, cat, {'ok': True}, {'control_points': [cp('e', lon, lat)], 'candidates': []},
                     why=f'середина стороны {side} (edges_inclusive)')
                d = {'W': (-1e-9, 0), 'E': (1e-9, 0), 'S': (0, -1e-9), 'N': (0, 1e-9)}[side]
                case(f'{P}{C}-edge-{side}-out', 'validate', city, cat, {'ok': False, 'code': 'outside_bbox', 'path': 'candidates[0]'},
                     {'control_points': [cp('e', cx, cy)], 'candidates': [cand('x', lon + d[0], lat + d[1], cat)]},
                     why=f'на 1e-9° за стороной {side}')
            # перестановка lon/lat у контрольной точки
            case(f'{P}{C}-swap-cp', 'validate', city, cat, {'ok': False, 'code': 'lon_lat_swapped', 'path': 'control_points[0]'},
                 {'control_points': [cp('s', cy, cx)], 'candidates': []})
            # контрольная точка ровно на исходной записи → честный 0; при общих координатах — ничья по ID
            by_xy = {}
            for p in srcs:
                by_xy.setdefault((p['lon'], p['lat']), []).append(p['id'])
            single = next(p for p in srcs if len(by_xy[(p['lon'], p['lat'])]) == 1)
            case(f'{P}{C}-cp-on-source', 'table', city, cat,
                 {'ok': True, 'result': {'baseline[0].mm': 0, 'baseline[0].key': 'source:' + single['id'],
                                         'baseline[0].tied_keys': ['source:' + single['id']]}},
                 {'control_points': [cp('on', single['lon'], single['lat'])], 'candidates': []},
                 why='точка в координатах записи: расстояние 0, а не «нет данных»')
            for xy, ids in sorted(by_xy.items()):
                if len(ids) > 1:
                    ids = sorted(ids)
                    case(f'{P}{C}-cp-on-shared-{len(ids)}', 'table', city, cat,
                         {'ok': True, 'result': {'baseline[0].mm': 0, 'baseline[0].key': 'source:' + ids[0],
                                                 'baseline[0].tied_keys': ['source:' + i for i in ids]}},
                         {'control_points': [cp('on', xy[0], xy[1])], 'candidates': []},
                         why=f'{len(ids)} записей категории в одних координатах: ничья 0 мм, выбирается меньший ID; записи не сливаются')
                    break
            # кандидат ровно в координатах ближайшей записи → ничья, побеждает source
            case(f'{P}{C}-cand-on-source-tie', 'after', city, cat,
                 {'ok': True, 'result': {'[0].key': 'source:' + single['id'], '[0].kind': 'source', '[0].mm': 0}},
                 {'control_points': [cp('on', single['lon'], single['lat'])],
                  'candidates': [cand('h', single['lon'], single['lat'], cat)]}, selected=[0],
                 why='проектный объект поверх существующей записи: улучшения 0, ближайшей остаётся source')
            # два кандидата в одной точке → ничья по ID (b, a → a)
            case(f'{P}{C}-two-cands-same-xy', 'after', city, cat,
                 {'ok': True, 'result': {'[0].key': 'hypothetical:a', '[0].kind': 'hypothetical'}},
                 {'control_points': [cp('p', cx, cy)], 'candidates': [cand('b', cx + 1e-5, cy, cat), cand('a', cx + 1e-5, cy, cat)]},
                 selected=[0, 1])
            # зеркальная ничья source/кандидат: точка на широте записи, кандидат зеркально по долготе
            s0 = single
            dl = 2e-5
            lon_p = s0['lon'] + dl if s0['lon'] + 2 * dl <= E else s0['lon'] - dl
            lon_c = 2 * lon_p - s0['lon']
            case(f'{P}{C}-mirror-tie', 'after', city, cat,
                 {'ok': True, 'result': {'[0].key': 'source:' + s0['id'], '[0].kind': 'source'}},
                 {'control_points': [cp('m', lon_p, s0['lat'])], 'candidates': [cand('mirror', lon_c, s0['lat'], cat)]}, selected=[0],
                 why='source и кандидат на равном расстоянии (симметрия по долготе на одной широте) → побеждает source')
            # почти-ничья < 1 мм: обе дистанции округляются в одно число мм → выбор по ID, а не по долям мм
            d0 = 100 / M_PER_DEG_LAT
            north = (cx, cy + d0)
            eps, pick = 1e-11, None
            while eps < 1e-8:
                south = (cx, cy - d0 - eps)
                mn, ms = hav_m((cx, cy), north), hav_m((cx, cy), south)
                if 5e-5 < ms - mn < 4e-4 and round(mn * 1000) == round(ms * 1000) and abs(mn * 1000 - round(mn * 1000)) < 0.3:
                    pick = south
                    break
                eps *= 1.3
            if pick:
                case(f'{P}{C}-submm-tie', 'after', city, cat,
                     {'ok': True, 'result': {'[0].key': 'hypothetical:a', '[0].mm': round(hav_m((cx, cy), north) * 1000)}},
                     {'control_points': [cp('p', cx, cy)], 'candidates': [cand('b', north[0], north[1], cat), cand('a', pick[0], pick[1], cat)]},
                     selected=[0, 1],
                     why=f'кандидат a дальше b на {round((hav_m((cx, cy), pick) - hav_m((cx, cy), north)) * 1000, 3)} мм, но в мм равны → ничья по ID (haversine-mm-v1)')
    # округление до мм около границ половины миллиметра (решение одно и то же в JS и Python; floor(x+0.5) — тоже)
    vals = []
    for k in (0, 1, 7, 123, 4999, 99999, 1234567):
        m = (k + 0.5) / 1000
        lo, hi = m, m
        for _ in range(3):
            lo, hi = math.nextafter(lo, 0), math.nextafter(hi, 1)
        vals += [lo, m, hi]
    exp = [math.floor(m * 1000 + 0.5) for m in vals]
    case('tomm-half-boundaries', 'tomm', None, None, {'ok': True, 'result': {f'[{i}]': e for i, e in enumerate(exp)}},
         values=vals, why='значения у границ k+0.5 мм ±3 ulp: Math.round(x) и floor(x+0.5) совпадают для x = d·1000')
    doc = dict(schema='k03-geo-v2-fixtures', stage=2,
               description='Этап 2: края bbox по сторонам, перестановка lon/lat, точка в координатах записи, общие координаты '
                           '(QA), ничьи source/кандидат/кандидат, почти-ничья < 1 мм, округление мм. Места — synthetic.',
               target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                           data_js_sha256=hashlib.sha256((app / 'web/data.js').read_bytes()).hexdigest(),
                           evidence_js_sha256=hashlib.sha256((app / 'web/evidence.js').read_bytes()).hexdigest()),
               cases=cases)
    (HERE / 'fixtures/stage2.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'stage2: {len(cases)} cases')


if __name__ == '__main__':
    main()
