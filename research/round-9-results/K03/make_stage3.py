"""K03 r9, этап 3: кейсы Шымкента и Астаны для проверки сценарной фильтрации (обе категории).

  python3 research/round-9-results/K03/make_stage3.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>

Для каждого среза: полный city-plan-v2 (точки и кандидаты synthetic, source_snapshot = формула plan.js) и до 7 явных случаев
на настоящих source ID: одна запись без соседей, одна запись из общих координат (остаются соседи), QA-группа COLOCATED
(у Астаны её нет — статус no_qa_group, случай не создаётся), пользовательская группа, тот же набор в другом порядке, все записи.
Ожидания: baseline каждого случая с нуля (resilience_cases_ref.case_baseline), after ручного плана, полный перебор
nominal/robust (robust_ref.brute_force) и утверждения по построению. Пишет fixtures/stage3.json и cases/<город>_<категория>.*.json.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import R, parse_js, sha256_file, plan_snapshot, u16  # noqa: E402
import resilience_cases_ref as RC  # noqa: E402
import robust_ref as RB  # noqa: E402

COSTS = [30, 40, 50, 20, 60, 35]


def build_slice(data, ev, city, cat, sha):
    c = data['cities'][city]
    W, S, E, N = c['bbox']
    places = c['places']
    srcs = sorted((p for p in places if p['group'] == cat), key=lambda p: u16(p['id']))
    xy = {}
    for p in places:
        xy.setdefault((p['lon'], p['lat']), []).append(p)
    cat_at = lambda p: sorted((o['id'] for o in xy[(p['lon'], p['lat'])] if o['group'] == cat), key=u16)  # noqa: E731
    colid = {i for g in ev['cities'][city]['qa']['colocated'] for i in g['ids']}
    iso = next(p for p in srcs if len(xy[(p['lon'], p['lat'])]) == 1 and p['id'] not in colid)
    # общие координаты внутри категории: пары (и группы) — исключаем меньший ID, остальные остаются в тех же координатах
    shared, seen = [], set()
    for p in srcs:
        ids = cat_at(p)
        if len(ids) > 1 and tuple(ids) not in seen:
            seen.add(tuple(ids))
            shared.append((p['lon'], p['lat'], ids))
    shared.sort(key=lambda t: (len(t[2]), u16(t[2][0])))
    cat_obj = RC.source_catalog(data, ev, city, cat)
    groups = RC.colocated_groups(ev, cat_obj)
    col = next((g for g in groups['groups'] if g['ids_in_category']), None)
    # контрольные точки: в координатах записей случаев + сетка 3×2 + центр (synthetic)
    cps, special = [], {}

    def add_point(pid, lon, lat):
        cps.append({'id': pid, 'lon': lon, 'lat': lat, 'weight': 1 + len(cps) % 5})
    add_point('at-iso', iso['lon'], iso['lat'])
    special['at-iso'] = iso['id']
    for k, (lon, lat, ids) in enumerate(shared[:2]):
        add_point(f'at-shared-{k}', lon, lat)
    if col:
        add_point('at-colocated', col['lon'], col['lat'])
    for i in range(3):
        for j in range(2):
            add_point(f'grid-{i}{j}', round(W + (E - W) * (i + 0.5) / 3, 6), round(S + (N - S) * (j + 0.5) / 2, 6))
    add_point('center', round((W + E) / 2, 6), round((S + N) / 2, 6))
    cands = [{'id': f'cand-{k + 1}', 'lon': round(W + (E - W) * fx, 6), 'lat': round(S + (N - S) * fy, 6), 'category': cat,
              'kind': 'hypothetical', 'cost': COSTS[k]} for k, (fx, fy) in enumerate([(0.2, 0.25), (0.8, 0.25), (0.5, 0.8), (0.2, 0.75), (0.8, 0.75)])]
    cands.append({'id': 'cand-on-iso', 'lon': iso['lon'], 'lat': iso['lat'], 'category': cat, 'kind': 'hypothetical', 'cost': COSTS[5]})
    plan = {'schema_version': 'city-plan-v2', 'city_id': city, 'source_snapshot': plan_snapshot(data, city), 'category': cat,
            'control_points': cps, 'candidates': cands, 'budget': 100, 'max_selected': 2, 'coverage_radius_m': 500,
            'required_ids': [], 'excluded_ids': [], 'selected_ids': ['cand-1', 'cand-on-iso']}
    # случаи — только явный выбор
    cases, notes, centre = [], {}, {'lon': (W + E) / 2, 'lat': (S + N) / 2}
    cases.append(RC.single_case(cat_obj, iso['id'], {'id': 'one-isolated'}))
    for k, (lon, lat, ids) in enumerate(shared[:2]):
        cases.append(RC.single_case(cat_obj, ids[0], {'id': f'one-of-shared-{k}'}))
        notes[f'one-of-shared-{k}'] = {'point': f'at-shared-{k}', 'excluded': ids[0], 'remaining_same_xy': ids[1:]}
    if col:
        r = RC.colocated_case(ev, cat_obj, col['index'], {'id': 'qa-colocated'})
        cases.append(r['case'])
        notes['qa-colocated'] = {'point': 'at-colocated', 'group_index': col['index'], 'excluded': r['case']['disabled_source_ids'],
                                 'other_categories_kept': col['ids_other_categories']}
        colocated_status = 'ok'
    else:
        colocated_status = RC.colocated_case(ev, cat_obj, 0, {'id': 'qa-colocated'})['status']
    near3 = sorted(srcs, key=lambda p: (R.mm_between(centre, p), u16(p['id'])))[:3]
    g = RC.group_case(cat_obj, [p['id'] for p in reversed(near3)], {'id': 'near-centre-3'})
    cases.append(g)
    cases.append({'id': 'near-centre-3-again', 'label': 'Те же три записи (повтор набора, другой порядок)',
                  'disabled_source_ids': list(reversed(g['disabled_source_ids']))})
    cases.append(RC.group_case(cat_obj, [p['id'] for p in srcs], {'id': 'all-records'}))
    assert len(cases) <= 7, len(cases)
    validated = RC.validate_cases(cat_obj, cases, RC.source_index(data), [q['id'] for q in cands])
    # ожидания
    rows = RB.per_case_rows(data, plan, validated['cases'])
    exp = {cid: [{'point': pid, 'base': b} for pid, b in rr] for cid, rr in rows.items()}
    after = {cid: RB.after_rows(rr, plan, plan['selected_ids']) for cid, rr in rows.items()}
    asserts = []
    by_pt = lambda cid, pid: next(b for p, b in rows[cid] if p == pid)  # noqa: E731
    b = by_pt('one-isolated', 'at-iso')
    asserts.append({'case': 'one-isolated', 'point': 'at-iso', 'rule': 'исключена запись в точке: ближайшая — другая запись дальше 0 мм',
                    'ok': b is not None and b['id'] != iso['id'] and b['mm'] > 0})
    for cid, n in notes.items():
        b = by_pt(cid, n['point'])
        if cid.startswith('one-of-shared'):
            asserts.append({'case': cid, 'point': n['point'], 'rule': 'исключена одна запись из общих координат: соседняя запись в тех же координатах, 0 мм',
                            'ok': b is not None and b['mm'] == 0 and b['id'] == n['remaining_same_xy'][0]})
        else:
            asserts.append({'case': cid, 'point': n['point'], 'rule': 'исключены все записи категории QA-группы: ближайшая дальше 0 мм, записи других категорий не участвуют',
                            'ok': b is not None and b['mm'] > 0 and b['id'] not in n['excluded']})
    asserts.append({'case': 'all-records', 'point': '*', 'rule': 'исключены все записи категории: до = неизвестно (None), а не 0',
                    'ok': all(b is None for _, b in rows['all-records'])})
    assert all(x['ok'] for x in asserts), asserts
    env = {'schema_version': 'city-resilience-v1', 'plan': plan, 'cases': cases}
    manifest = RC.exclusion_manifest(cat_obj, validated, {'branch': 'claude/beautiful-clarke-sbzomj', 'sha': sha})
    bf = RB.brute_force(data, plan, validated['cases'])
    return dict(city=city, category=cat, envelope=env, n_sources=len(srcs), colocated_status=colocated_status,
                qa_groups_in_city=len(groups['groups']), shared_in_category=[ids for _, _, ids in shared], notes=notes,
                expected_base=exp, expected_after_manual=after, asserts=asserts, brute_force=bf,
                identical_sets=validated['identical_sets']), manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    slices = []
    (HERE / 'cases').mkdir(exist_ok=True)
    for city in ('shymkent', 'astana'):
        for cat in ('school', 'outpatient_clinic'):
            s, man = build_slice(data, ev, city, cat, a.target_sha)
            slices.append(s)
            stem = HERE / 'cases' / f'{city}_{cat}'
            text = json.dumps(s['envelope'], ensure_ascii=False, indent=1) + '\n'
            assert len(text.encode('utf-8')) <= 256 * 1024
            stem.with_suffix('.envelope.json').write_text(text, encoding='utf-8')
            stem.with_suffix('.manifest.json').write_text(json.dumps(man, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
            print(f'{city}/{cat}: {len(s["envelope"]["cases"])} случаев, colocated={s["colocated_status"]}, '
                  f'nominal={s["brute_force"]["nominal"]["selected_ids"]} robust={s["brute_force"]["robust"]["selected_ids"]} '
                  f'price={s["brute_force"]["price_of_robustness_m"]}')
    doc = dict(schema='k03-r9-stage3-fixtures', stage=3,
               description='Этап 3: сценарная фильтрация исходных записей по случаям на обоих городах и категориях. Точки, веса, кандидаты, '
                           'стоимости и подписи — synthetic; записи и их ID — Overture из сборки. Ожидания — независимый оракул K03.',
               target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                           data_js_sha256=sha256_file(app / 'web/data.js'), evidence_js_sha256=sha256_file(app / 'web/evidence.js')),
               slices=slices)
    (HERE / 'fixtures/stage3.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('stage3 fixtures:', len(slices), 'срезов, sha256', hashlib.sha256((HERE / 'fixtures/stage3.json').read_bytes()).hexdigest()[:16])


if __name__ == '__main__':
    main()
