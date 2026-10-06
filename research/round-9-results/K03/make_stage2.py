"""K03 r9, этап 2: fixtures построителя случаев исключения (оба города, обе категории).

  python3 research/round-9-results/K03/make_stage2.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>

Ожидания — по построению из data.js/evidence.js сборки (не из JS-модуля и не из оракула):
одна запись, пользовательская группа, QA-группа COLOCATED (у Астаны её нет — статус no_qa_group, группа не создаётся),
список случаев, envelope без производных полей, manifest исключаемых записей с provenance на базовом срезе.
Ключ ожидания с префиксом "js:" проверяется только у JS (заморозка объектов). Подписи случаев и ID кандидатов — synthetic.
"""
import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import parse_js, sha256_file, plan_snapshot, u16  # noqa: E402


def clip(s, n=120):
    s = ''.join(' ' if unicodedata.category(ch) in ('Cc', 'Cs') else ch for ch in s)
    return s if len(s) <= n else s[:n - 1] + '…'


def raw_sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    cases = []

    def case(cid, op, expect, why=None, **kw):
        cases.append(dict(id=cid, op=op, expect=expect, why=why, **kw))

    def ok(**res):
        return {'ok': True, 'result': res}

    def err(code, path):
        return {'ok': False, 'code': code, 'path': path}

    for city in ('astana', 'shymkent'):
        other_city = 'shymkent' if city == 'astana' else 'astana'
        places = data['cities'][city]['places']
        q = ev['cities'][city]['qa']
        for cat in ('school', 'outpatient_clinic'):
            P = f'{city[:3].upper()}{"S" if cat == "school" else "C"}'
            K = dict(city=city, category=cat)
            srcs = sorted((p for p in places if p['group'] == cat), key=lambda p: u16(p['id']))
            ids = [p['id'] for p in srcs]
            N = len(srcs)
            xy = {}
            for p in places:
                xy.setdefault((p['lon'], p['lat']), []).append(p)
            col_of = {i: g for g in q['colocated'] for i in g['ids']}
            other_cat = next(p['id'] for p in sorted(places, key=lambda p: u16(p['id'])) if p['group'] != cat)
            foreign = sorted(p['id'] for p in data['cities'][other_city]['places'] if p['group'] == cat)[0]

            # ---- каталог: копии записей data.js с provenance и QA ----
            exp = {'catalog.city_id': city, 'catalog.category': cat, 'catalog.source_snapshot': plan_snapshot(data, city),
                   'catalog.release': data['cities'][city]['release'], 'catalog.qa_available': True,
                   'js:frozen': True, 'js:mutation_blocked': True}
            for k, p in enumerate(srcs):
                r = f'catalog.records[{k}]'
                same = [o for o in xy[(p['lon'], p['lat'])] if o['id'] != p['id']]
                exp.update({f'{r}.id': p['id'], f'{r}.category': cat, f'{r}.lon': p['lon'], f'{r}.lat': p['lat'], f'{r}.name': p.get('name'),
                            f'{r}.address': p.get('address'), f'{r}.provenance.overture_version': p.get('overture_version'),
                            f'{r}.provenance.confidence': p.get('confidence'), f'{r}.provenance.overture_category': p.get('category'),
                            f'{r}.provenance.sources': [{'dataset': s.get('dataset'), 'record_id': s.get('record_id'), 'license': s.get('license'),
                                                         'update_time': s.get('update_time')} for s in p.get('sources') or []],
                            f'{r}.record_sha256': raw_sha(p), f'{r}.position_status': 'source_reported_unverified',
                            f'{r}.qa.colocated.size' if p['id'] in col_of else f'{r}.qa.colocated': len(col_of[p['id']]['ids']) if p['id'] in col_of else None,
                            f'{r}.same_coordinates.in_category': sorted((o['id'] for o in same if o['group'] == cat), key=u16),
                            f'{r}.same_coordinates.other_categories': sorted((o['id'] for o in same if o['group'] != cat), key=u16)})
            exp[f'catalog.records[{N}]'] = '<missing>'
            case(f'{P}-catalog', 'catalog', ok(**exp), 'каталог: все записи категории, копии полей data.js, provenance, QA; ничего не исключено', **K)

            # ---- QA-группы: показываются, но ничего не создают ----
            gexp = {'qa_available': True, 'groups': [{'index': i, 'lon': g['lon'], 'lat': g['lat'], 'size': len(g['ids']),
                                                      'ids_in_category': sorted((x for x in g['ids'] if x in ids), key=u16),
                                                      'ids_other_categories': sorted((x for x in g['ids'] if x not in ids), key=u16)}
                                                     for i, g in enumerate(q['colocated'])]}
            case(f'{P}-groups', 'groups', ok(**gexp), 'группы COLOCATED среза; у Астаны их нет — пустой список, группа не придумывается', **K)

            # ---- одна запись ----
            iso = next(p for p in srcs if len(xy[(p['lon'], p['lat'])]) == 1)
            case(f'{P}-single-isolated', 'single', ok(**{'id': 'one', 'label': clip(f'Условно без записи: {iso.get("name") or "без названия"}'),
                                                         'disabled_source_ids': [iso['id']]}),
                 'одна запись без общих координат; подпись по умолчанию — «условно», без «закрытия»', source_id=iso['id'], opts={'id': 'one'}, **K)
            shared = [p for p in srcs if sum(1 for o in xy[(p['lon'], p['lat'])] if o['group'] == cat) > 1]
            if shared:
                p = shared[0]
                case(f'{P}-single-shared', 'single', ok(**{'disabled_source_ids': [p['id']]}),
                     'запись из общих координат: исключается только она, соседи по координатам остаются', source_id=p['id'], opts={'id': 'one'}, **K)
            case(f'{P}-single-label', 'single', ok(**{'label': 'Мой случай ✓ 🙂 <b>текст</b>'}), 'подпись пользователя — только текст',
                 source_id=ids[0], opts={'id': 'one', 'label': 'Мой случай ✓ 🙂 <b>текст</b>'}, **K)
            case(f'{P}-single-kazakh-id', 'single', ok(**{'id': 'жағдай-1'}), 'ID случая по правилам BUILD (Unicode NFC)',
                 source_id=ids[0], opts={'id': 'жағдай-1'}, **K)
            for name, sid, e in [('other-cat', other_cat, err('other_category_source', 'disabled_source_ids[0]')),
                                 ('other-city', foreign, err('other_city_source', 'disabled_source_ids[0]')),
                                 ('unknown', 'no-such-record', err('unknown_source_id', 'disabled_source_ids[0]')),
                                 ('prefixed', 'source:' + ids[0], err('bad_source_id', 'disabled_source_ids[0]')),
                                 ('number', 12345, err('bad_source_id', 'disabled_source_ids[0]'))]:
                case(f'{P}-single-{name}', 'single', e, None, source_id=sid, opts={'id': 'one'}, **K)
            case(f'{P}-single-candidate', 'single', err('candidate_not_source', 'disabled_source_ids[0]'),
                 'ID кандидата не принимается вместо ID исходной записи', source_id='cand-1', opts={'id': 'one'}, candidate_ids=['cand-1'], **K)
            case(f'{P}-single-candidate-same-id', 'single', ok(**{'disabled_source_ids': [ids[0]]}),
                 'кандидат с ID исходной записи: disabled_source_ids — пространство source, исключается запись', source_id=ids[0],
                 opts={'id': 'one'}, candidate_ids=[ids[0]], **K)
            case(f'{P}-single-no-id', 'single', err('bad_case_id', 'id'), None, source_id=ids[0], opts={}, **K)
            case(f'{P}-single-base', 'single', err('reserved_case_id', 'id'), None, source_id=ids[0], opts={'id': 'base'}, **K)

            # ---- пользовательская группа ----
            g3 = ids[:3]
            nm = [next(p for p in srcs if p['id'] == i).get('name') or 'без названия' for i in g3]
            case(f'{P}-group-3', 'group', ok(**{'id': 'g', 'disabled_source_ids': g3, 'label': clip(f'Условно без выбранных записей (3): {", ".join(nm)}')}),
                 'порядок ввода не важен: ID отсортированы', source_ids=list(reversed(g3)), opts={'id': 'g'}, **K)
            case(f'{P}-group-all', 'group', ok(**{'disabled_source_ids': ids}), f'все {N} записей категории — допустимо (до = неизвестно)',
                 source_ids=ids, opts={'id': 'g'}, **K)
            for name, lst, e in [('dup', [ids[0], ids[1], ids[0]], err('duplicate_source_id', 'disabled_source_ids[2]')),
                                 ('empty', [], err('empty_exclusion', 'disabled_source_ids')),
                                 ('too-many', ids + [ids[0]], err('too_many_exclusions', 'disabled_source_ids')),
                                 ('other-cat', [ids[0], other_cat], err('other_category_source', 'disabled_source_ids[1]')),
                                 ('other-city', [ids[0], foreign], err('other_city_source', 'disabled_source_ids[1]')),
                                 ('not-array', ids[0], err('bad_shape', 'disabled_source_ids'))]:
                case(f'{P}-group-{name}', 'group', e, None, source_ids=lst, opts={'id': 'g'}, **K)

            # ---- QA-группа COLOCATED (явно указанная пользователем) ----
            if not q['colocated']:
                case(f'{P}-colocated-none', 'colocated', ok(status='no_qa_group', case=None, group=None),
                     'в срезе нет групп COLOCATED: случай не создаётся, отсутствие показано', index=0, opts={'id': 'qa'}, **K)
            for gi, g in enumerate(q['colocated']):
                inc = sorted((x for x in g['ids'] if x in ids), key=u16)
                if inc:
                    lab = clip(f'Условно без записей QA-группы COLOCATED ({g["lon"]}, {g["lat"]}): {len(inc)} из {len(g["ids"])}')
                    case(f'{P}-colocated-{gi}', 'colocated', ok(**{'status': 'ok', 'case.disabled_source_ids': inc, 'case.label': lab,
                                                                   'group.ids_other_categories': sorted((x for x in g['ids'] if x not in ids), key=u16)}),
                         f'группа {gi}: исключаются только {len(inc)} записей категории из {len(g["ids"])}; другие категории и соседи вне группы не добавляются',
                         index=gi, opts={'id': 'qa'}, **K)
                else:
                    case(f'{P}-colocated-{gi}', 'colocated', ok(status='no_records_in_category', case=None),
                         f'группа {gi} без записей категории: случай не создаётся', index=gi, opts={'id': 'qa'}, **K)
            if q['colocated']:
                case(f'{P}-colocated-no-index', 'colocated', err('unknown_qa_group', 'group'),
                     'без явно указанной группы случай не создаётся (нет «исключить все QA»)', index=None, opts={'id': 'qa'}, **K)
                case(f'{P}-colocated-bad-index', 'colocated', err('unknown_qa_group', 'group'), None, index=len(q['colocated']), opts={'id': 'qa'}, **K)
                case(f'{P}-colocated-str-index', 'colocated', err('unknown_qa_group', 'group'), None, index='0', opts={'id': 'qa'}, **K)

            # ---- список случаев (как в envelope) ----
            one = {'id': 'one', 'label': 'Без первой записи', 'disabled_source_ids': [ids[0]]}
            grp = {'id': 'grp', 'label': 'Без трёх записей', 'disabled_source_ids': [ids[2], ids[1], ids[0]]}
            twin = {'id': 'twin', 'label': 'Те же три в другом порядке', 'disabled_source_ids': [ids[1], ids[0], ids[2]]}
            allc = {'id': 'all', 'label': 'Без всех записей категории', 'disabled_source_ids': list(reversed(ids))}
            base_cases = [one, grp, twin, allc]
            case(f'{P}-validate-mixed', 'validate', ok(**{'cases[1].disabled_source_ids': sorted(grp['disabled_source_ids'], key=u16),
                                                          'with_base[0]': {'id': 'base', 'label': 'Исходные данные', 'disabled_source_ids': []},
                                                          'with_base[4].id': 'all', 'identical_sets': [['grp', 'twin']],
                                                          'cases[3].disabled_source_ids': ids}),
                 'base добавлен автоматически; совпадающие наборы разрешены и показаны', cases=base_cases, **K)
            seven = [dict(one, id=f'c{i}') for i in range(7)]
            case(f'{P}-validate-7', 'validate', ok(**{'cases[6].id': 'c6', 'identical_sets': [[f'c{i}' for i in range(7)]]}), '7 пользовательских случаев + base = 8',
                 cases=seven, **K)
            neg = [('8', seven + [dict(one, id='c7')], err('too_many_cases', 'cases')),
                   ('0', [], err('no_cases', 'cases')),
                   ('not-array', one, err('bad_shape', 'cases')),
                   ('not-object', [one, 'x'], err('bad_shape', 'cases[1]')),
                   ('base', [dict(one, id='base')], err('reserved_case_id', 'cases[0].id')),
                   ('dup-case', [one, dict(grp, id='one')], err('duplicate_case_id', 'cases[1].id')),
                   ('id-space', [dict(one, id='a b')], err('bad_case_id', 'cases[0].id')),
                   ('id-empty', [dict(one, id='')], err('bad_case_id', 'cases[0].id')),
                   ('id-65', [dict(one, id='x' * 65)], err('bad_case_id', 'cases[0].id')),
                   ('id-nfd', [dict(one, id=unicodedata.normalize('NFD', 'й'))], err('bad_case_id', 'cases[0].id')),
                   ('label-empty', [dict(one, label='')], err('bad_label', 'cases[0].label')),
                   ('label-121', [dict(one, label='я' * 121)], err('bad_label', 'cases[0].label')),
                   ('label-bel', [dict(one, label='a\u0007b')], err('bad_label', 'cases[0].label')),
                   ('label-surrogate', [dict(one, label='a\ud800b')], err('bad_label', 'cases[0].label')),
                   ('label-number', [dict(one, label=5)], err('bad_label', 'cases[0].label')),
                   ('unknown-field', [dict(one, derived={'mean': 1})], err('unknown_field', 'cases[0].derived')),
                   ('missing-label', [{'id': 'one', 'disabled_source_ids': [ids[0]]}], err('missing_field', 'cases[0].label')),
                   ('disabled-null', [dict(one, disabled_source_ids=None)], err('bad_shape', 'cases[0].disabled_source_ids')),
                   ('candidate', [dict(one, disabled_source_ids=['cand-1'])], err('candidate_not_source', 'cases[0].disabled_source_ids[0]')),
                   ('other-city', [one, dict(grp, disabled_source_ids=[foreign])], err('other_city_source', 'cases[1].disabled_source_ids[0]'))]
            for name, lst, e in neg:
                case(f'{P}-validate-{name}', 'validate', e, None, cases=lst, candidate_ids=['cand-1'], **K)
            case(f'{P}-validate-label-120-astral', 'validate', ok(**{'cases[0].label': '🙂' * 120}),
                 '120 code points (240 UTF-16 единиц) — допустимо', cases=[dict(one, label='🙂' * 120)], **K)
            case(f'{P}-validate-Base', 'validate', ok(**{'cases[0].id': 'Base'}), 'зарезервирован только "base"', cases=[dict(one, id='Base')], **K)

            # ---- manifest исключаемых записей на базовом срезе ----
            used = sorted({x for c in base_cases for x in c['disabled_source_ids']}, key=u16)
            mexp = {'manifest.schema': 'k03-exclusion-manifest-v1', 'manifest.city_id': city, 'manifest.category': cat,
                    'manifest.base_source_snapshot': plan_snapshot(data, city), 'manifest.release': data['cities'][city]['release'],
                    'manifest.cases[1].identical_to': ['twin'], 'manifest.cases[0].identical_to': [],
                    'manifest.build': {'branch': 'claude/beautiful-clarke-sbzomj', 'sha': a.target_sha},
                    'js:frozen': True, 'js:mutation_blocked': True}
            for x in used:
                p = next(s for s in srcs if s['id'] == x)
                mexp.update({f'manifest.records.{x}.category': cat, f'manifest.records.{x}.lon': p['lon'], f'manifest.records.{x}.lat': p['lat'],
                             f'manifest.records.{x}.record_sha256': raw_sha(p), f'manifest.records.{x}.position_status': 'source_reported_unverified',
                             f'manifest.records.{x}.provenance.sources': [{'dataset': s.get('dataset'), 'record_id': s.get('record_id'),
                                                                           'license': s.get('license'), 'update_time': s.get('update_time')}
                                                                          for s in p.get('sources') or []]})
            case(f'{P}-manifest', 'manifest', ok(**mexp), 'исходники, категория и provenance каждого исключаемого ID на базовом срезе; '
                 'manifest не входит в envelope', cases=base_cases, build={'branch': 'claude/beautiful-clarke-sbzomj', 'sha': a.target_sha}, **K)

    # ---- envelope: только вход, производные поля не принимаются ----
    one = {'id': 'one', 'label': 'x', 'disabled_source_ids': ['a']}
    for name, env, e in [('ok', {'schema_version': 'city-resilience-v1', 'plan': {'schema_version': 'city-plan-v2'}, 'cases': [one]}, {'ok': True}),
                         ('per-case', {'schema_version': 'city-resilience-v1', 'plan': {}, 'cases': [], 'per_case': []}, err('derived_not_accepted', 'per_case')),
                         ('worst', {'schema_version': 'city-resilience-v1', 'plan': {}, 'cases': [], 'worst_case_ids': []}, err('derived_not_accepted', 'worst_case_ids')),
                         ('verified', {'schema_version': 'city-resilience-v1', 'plan': {}, 'cases': [], 'verified': True}, err('derived_not_accepted', 'verified')),
                         ('extra', {'schema_version': 'city-resilience-v1', 'plan': {}, 'cases': [], 'note': ''}, err('unknown_field', 'note')),
                         ('missing-cases', {'schema_version': 'city-resilience-v1', 'plan': {}}, err('missing_field', 'cases')),
                         ('version', {'schema_version': 'city-plan-v2', 'plan': {}, 'cases': []}, err('bad_version', 'schema_version')),
                         ('plan-derived', {'schema_version': 'city-resilience-v1', 'plan': {'derived_results': {}}, 'cases': []},
                          err('derived_not_accepted', 'plan.derived_results')),
                         ('plan-array', {'schema_version': 'city-resilience-v1', 'plan': [], 'cases': []}, err('bad_shape', 'plan'))]:
        case(f'ENV-{name}', 'envelope', e, None, envelope=env)
    doc = dict(schema='k03-r9-stage2-fixtures', stage=2,
               description='Этап 2: явные случаи исключения исходных записей (одна, группа, QA COLOCATED), список случаев, envelope, '
                           'manifest provenance. Подписи, ID случаев и кандидатов — synthetic; записи — Overture из сборки.',
               target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                           data_js_sha256=sha256_file(app / 'web/data.js'), evidence_js_sha256=sha256_file(app / 'web/evidence.js')),
               cases=cases)
    text = json.dumps(doc, ensure_ascii=False, indent=1).replace('\ud800', '\\ud800')  # одиночный суррогат — экранированием JSON
    (HERE / 'fixtures/stage2.json').write_text(text + '\n', encoding='utf-8')
    print(f'stage2: {len(cases)} cases')


if __name__ == '__main__':
    main()
