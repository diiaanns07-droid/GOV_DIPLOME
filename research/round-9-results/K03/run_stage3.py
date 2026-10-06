"""K03 r9, этап 3: сценарная фильтрация исходных записей — plan.js любой сборки и web/resilience.js сборки, если он есть.

  python3 research/round-9-results/K03/run_stage3.py --app-root <копия prototypes/city-evidence> --target-sha <SHA> [--json out]

Часть A (plan.js, любая сборка):
  S3-plan-case-baseline   baseline каждого случая через plan.precompute на отфильтрованной копии = оракул (с нуля), source_records = N − k;
  S3-plan-after-manual    after/nearest_after ручного плана в каждом случае = оракул;
  S3-construction         утверждения по построению: соседняя запись в общих координатах остаётся (0 мм), QA-группа/одна запись — ближайшая дальше,
                          все записи исключены → неизвестно (None), а не 0;
  S3-module-view          caseView модуля K03: тот же source_snapshot, исключены ровно указанные ID, контекст не изменён и заморожен;
  S3-other-city           план другого города → other_city, чужой snapshot → foreign_snapshot, ID другого города в случаях отклоняется;
  S3-no-qa-group          Астана: групп COLOCATED нет — случай не создаётся, отсутствие показано статусом;
  S3-integrity            data.js/evidence.js (файл, объект), контекст и source_snapshot не изменились.
Часть B (только если в сборке есть web/resilience.js; иначе NOT_RUN):
  S3-build-envelopes, S3-build-case-baseline, S3-build-optimize, S3-build-invariants, S3-build-other-city,
  S3-build-duplicates-order, S3-build-validate-map (fixtures этапа 2), S3-build-envelope-rules, S3-build-policy (INFO).
Эталон — независимый оракул K03 и fixtures; по ответу сборки ожидания не меняются. Код выхода 1 при FAIL/TEST_INCOMPATIBLE.
"""
import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import OUT, rec, parse_js, sha256_file, run_adapter, plan_snapshot, u16, summary_and_save  # noqa: E402
import resilience_cases_ref as RC  # noqa: E402
import robust_ref as RB  # noqa: E402

# код ошибки модуля K03 → допустимые коды web/resilience.js (различия названий — политика, не дефект)
CODE_MAP = {'too_many_cases': {'bad_cases'}, 'no_cases': {'bad_cases'}, 'bad_shape': {'bad_shape'}, 'reserved_case_id': {'reserved_id'},
            'duplicate_case_id': {'duplicate_id'}, 'bad_case_id': {'bad_id'}, 'bad_label': {'bad_label'}, 'unknown_field': {'bad_shape'},
            'missing_field': {'bad_shape'}, 'empty_exclusion': {'bad_exclusions'}, 'too_many_exclusions': {'bad_exclusions'},
            'duplicate_source_id': {'duplicate_id'}, 'bad_source_id': {'bad_id', 'unknown_source'}, 'unknown_source_id': {'unknown_source'},
            'other_category_source': {'unknown_source'}, 'other_city_source': {'unknown_source'}, 'candidate_not_source': {'candidate_not_source'}}
# расхождения из-за неоднозначности CORE_SPEC (не FAIL продукта; показываются отдельно)
SPEC_AMBIGUOUS = {'label-surrogate': 'одиночный суррогат U+D800 в подписи: K03 отклоняет (не скалярное значение Unicode), '
                                     'сборка принимает (CTRL — только управляющие и U+2028/2029). CORE_SPEC говорит «code points, без управляющих символов».'}


def node_json(script, req, timeout=900):
    node = shutil.which('node')
    if not node:
        return None
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        fh.write(json.dumps(req, ensure_ascii=True))
        p = fh.name
    try:
        r = subprocess.run([node, str(HERE / script), p], capture_output=True, text=True, timeout=timeout)
    finally:
        Path(p).unlink()
    if r.returncode:
        raise RuntimeError(f'{script}: код {r.returncode}: {r.stderr[-400:]}')
    return json.loads(r.stdout)


def case_list(s):
    return [{'id': 'base', 'disabled_source_ids': []}] + s['envelope']['cases']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    app = a.app_root.resolve()
    doc = json.loads((HERE / 'fixtures/stage3.json').read_text(encoding='utf-8'))
    have = {'data_js_sha256': sha256_file(app / 'web/data.js'), 'evidence_js_sha256': sha256_file(app / 'web/evidence.js')}
    diff = [k for k in have if doc['target'].get(k) != have[k]]
    if diff:
        rec('S3-fixtures-match-build', 'TEST_INCOMPATIBLE', f'fixtures этапа 3 построены на {doc["target"]["sha"][:12]}, {diff} другие — make_stage3.py')
        return summary_and_save(a.json)
    rec('S3-fixtures-match-build', 'PASS', f'fixtures этапа 3 (4 среза) построены на данных этой сборки ({a.target_sha[:12]})', target_sha=a.target_sha)
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    data0 = copy.deepcopy(data)
    S = doc['slices']

    # ================= часть A: plan.js =================
    req = []
    for s in S:
        plan, K = s['envelope']['plan'], f'{s["city"]}|{s["category"]}'
        places = {'control_points': plan['control_points'], 'candidates': plan['candidates']}
        for c in case_list(s):
            for op in ('table', 'after'):
                req.append(dict(id=f'{op}|{K}|{c["id"]}', op=op, city=s['city'], category=s['category'], places=places,
                                selected_ids=plan['selected_ids'] if op == 'after' else [], disabled_source_ids=c['disabled_source_ids']))
    shy = next(s for s in S if s['city'] == 'shymkent')['envelope']['plan']
    ast = next(s for s in S if s['city'] == 'astana')['envelope']['plan']
    req += [dict(id='raw|shy-plan-in-astana', op='validate_raw', city='astana', scenario=shy),
            dict(id='raw|astana-with-shy-snapshot', op='validate_raw', city='astana', scenario=dict(ast, source_snapshot=shy['source_snapshot'])),
            dict(id='raw|shy-ok', op='validate_raw', city='shymkent', scenario=shy),
            dict(id='ctx|shymkent', op='context', city='shymkent'), dict(id='ctx|astana', op='context', city='astana')]
    res, integ = run_adapter(app, req)
    if res is None:
        rec('S3-plan-js', 'NOT_RUN', integ)
        return summary_and_save(a.json)
    errs_b, errs_a, errs_c, ties, npts = [], [], [], 0, 0
    for s in S:
        K = f'{s["city"]}|{s["category"]}'
        for c in case_list(s):
            t, af = res[f'table|{K}|{c["id"]}'], res[f'after|{K}|{c["id"]}']
            if not (t['ok'] and af['ok']):
                errs_b.append(f'{K}/{c["id"]}: plan.js отклонил {t.get("error") or t.get("crash")}')
                continue
            if t['result']['source_count'] != s['n_sources'] - len(c['disabled_source_ids']):
                errs_b.append(f'{K}/{c["id"]}: записей в случае {t["result"]["source_count"]} ≠ {s["n_sources"]} − {len(c["disabled_source_ids"])}')
            for e in s['expected_base'][c['id']]:
                npts += 1
                want = {'id': e['base']['id'], 'mm': e['base']['mm']} if e['base'] else None
                if t['result']['base'][e['point']] != want:
                    errs_b.append(f'{K}/{c["id"]}/{e["point"]}: plan {t["result"]["base"][e["point"]]} ≠ оракул {want}')
                ties += bool(e['base'] and len(e['base']['tied_ids']) > 1)
            rows = {r['id']: r for r in af['result']['rows']}
            for e in s['expected_after_manual'][c['id']]:
                r = rows[e['point']]
                if (r['after_mm'], r['nearest_after'], r['before_mm'], r['delta_mm']) != (e['after_mm'], e['after'], e['before_mm'], e['delta_mm']):
                    errs_a.append(f'{K}/{c["id"]}/{e["point"]}: plan after {r["nearest_after"]} {r["after_mm"]} ≠ оракул {e["after"]} {e["after_mm"]}')
        for x in s['asserts']:
            t = res[f'table|{K}|{x["case"]}']['result']['base']
            pts = list(t) if x['point'] == '*' else [x['point']]
            exp = {p: next(e['base'] for e in s['expected_base'][x['case']] if e['point'] == p) for p in pts}
            if not x['ok'] or any(t[p] != ({'id': exp[p]['id'], 'mm': exp[p]['mm']} if exp[p] else None) for p in pts):
                errs_c.append(f'{K}/{x["case"]}/{x["point"]}: {x["rule"]}')
    rec('S3-plan-case-baseline', 'FAIL' if errs_b else 'PASS',
        f'{sum(len(case_list(s)) for s in S)} случаев (с base) × точки = {npts} строк: baseline через plan.precompute на отфильтрованной копии '
        f'= оракулу K03 (с нуля по оставшимся записям), число записей случая = N − k; ничьих {ties}; расхождений {len(errs_b)}', mismatches=errs_b[:20])
    rec('S3-plan-after-manual', 'FAIL' if errs_a else 'PASS',
        f'after/nearest_after/delta ручного плана в каждом случае = оракулу; расхождений {len(errs_a)}', mismatches=errs_a[:20])
    rec('S3-construction', 'FAIL' if errs_c else 'PASS',
        f'{sum(len(s["asserts"]) for s in S)} утверждений по построению на plan.js: исключение одной записи из общих координат оставляет соседнюю '
        '(0 мм, тот же адрес точки); QA-группа и отдельная запись — ближайшая дальше; все записи исключены → до неизвестно (None), не 0; '
        f'нарушений {len(errs_c)}', errors=errs_c)

    # caseView модуля K03 (cases_runner) + проверка случаев с ID другого города
    creq = []
    for s in S:
        for c in case_list(s):
            creq.append(dict(id=f'view|{s["city"]}|{s["category"]}|{c["id"]}', op='view', city=s['city'], category=s['category'], disabled=c['disabled_source_ids']))
        other = next(x for x in S if x['city'] != s['city'] and x['category'] == s['category'])
        foreign = other['envelope']['cases'][0]['disabled_source_ids'][0]
        creq.append(dict(id=f'foreign|{s["city"]}|{s["category"]}', op='validate', city=s['city'], category=s['category'],
                         cases=[dict(s['envelope']['cases'][0], disabled_source_ids=[foreign])]))
        creq.append(dict(id=f'qa|{s["city"]}|{s["category"]}', op='colocated', city=s['city'], category=s['category'], index=0, opts={'id': 'qa'}))
    cr = node_json('cases_runner.cjs', {'app_root': str(app), 'cases': creq})
    cres = {x['id']: x for x in cr['results']}
    errs = []
    for s in S:
        snap = plan_snapshot(data, s['city'])
        all_ids = [p['id'] for p in data['cities'][s['city']]['places'] if p['group'] in ('school', 'outpatient_clinic')]
        for c in case_list(s):
            v = cres[f'view|{s["city"]}|{s["category"]}|{c["id"]}']
            if not v['ok']:
                errs.append(f'{s["city"]}/{c["id"]}: {v.get("error") or v.get("crash")}')
                continue
            r = v['result']
            if r['source_snapshot'] != snap or r['ctx_snapshot'] != snap:
                errs.append(f'{s["city"]}/{c["id"]}: snapshot представления/контекста ≠ базовому')
            if sorted(r['place_ids']) != sorted(i for i in all_ids if i not in c['disabled_source_ids']) or r['ctx_place_count'] != len(all_ids) or not r['frozen']:
                errs.append(f'{s["city"]}/{c["id"]}: состав представления/контекста неверен')
    rec('S3-module-view', 'FAIL' if errs else 'PASS',
        'caseView модуля K03 на контексте plan.js: тот же source_snapshot (= независимый пересчёт), исключены ровно ID случая, контекст '
        f'не изменён, представление заморожено; ошибок {len(errs)}', errors=errs)

    errs = []
    r1, r2, r3 = res['raw|shy-plan-in-astana'], res['raw|astana-with-shy-snapshot'], res['raw|shy-ok']
    if r1['ok'] or r1['error']['code'] != 'other_city':
        errs.append(f'план Шымкента в контексте Астаны: {r1.get("error") or "принят"}')
    if r2['ok'] or r2['error']['code'] != 'foreign_snapshot':
        errs.append(f'план Астаны со snapshot Шымкента: {r2.get("error") or "принят"}')
    if not r3['ok'] or r3['result']['source_snapshot'] != plan_snapshot(data, 'shymkent'):
        errs.append('свой план не принят или snapshot изменён')
    for s in S:
        f = cres[f'foreign|{s["city"]}|{s["category"]}']
        if f['ok'] or f['error']['code'] != 'other_city_source':
            errs.append(f'{s["city"]}/{s["category"]}: ID записи другого города в случае: {f.get("error") or "принят"}')
        try:
            RC.validate_cases(RC.source_catalog(data, ev, s['city'], s['category']),
                              [dict(s['envelope']['cases'][0], disabled_source_ids=[next(x for x in S if x['city'] != s['city'] and x['category'] == s['category'])['envelope']['cases'][0]['disabled_source_ids'][0]])],
                              RC.source_index(data))
            errs.append(f'{s["city"]}: оракул принял ID другого города')
        except RC.CaseErr as e:
            if e.code != 'other_city_source':
                errs.append(f'{s["city"]}: оракул {e.code}')
    rec('S3-other-city', 'FAIL' if errs else 'PASS', 'другой город отклонён: план Шымкента в контексте Астаны → other_city (plan.js), чужой snapshot → '
        'foreign_snapshot, ID записи другого города в случае → other_city_source (модуль K03 JS и оракул); свой план принят с тем же snapshot', errors=errs)

    errs = []
    for s in S:
        q = cres[f'qa|{s["city"]}|{s["category"]}']['result']
        if s['city'] == 'astana':
            if s['colocated_status'] != 'no_qa_group' or q['status'] != 'no_qa_group' or q['case'] is not None \
                    or any(c['id'] == 'qa-colocated' for c in s['envelope']['cases']) or ev['cities']['astana']['qa']['colocated']:
                errs.append(f'astana/{s["category"]}: QA-группа создана или статус не no_qa_group')
        elif s['colocated_status'] != 'ok':
            errs.append(f'shymkent/{s["category"]}: ожидалась QA-группа')
    rec('S3-no-qa-group', 'FAIL' if errs else 'PASS', 'Астана: в evidence.js групп COLOCATED нет — модуль возвращает no_qa_group, случай «qa-colocated» '
        'не создан ни для школ, ни для поликлиник; Шымкент: случай из явно указанной группы создан', errors=errs)

    ok = integ['file_unchanged'] and integ['loaded_data_unchanged'] and cr['integrity']['file_unchanged'] and cr['integrity']['loaded_unchanged'] \
        and all(v['ctx'] == v['recomputed'] == plan_snapshot(data, k) for k, v in integ['snapshots'].items()) and data == data0 \
        and all(res[f'ctx|{c}']['result']['source_snapshot'] == plan_snapshot(data, c) for c in ('shymkent', 'astana'))
    rec('S3-integrity', 'PASS' if ok else 'FAIL', 'после всех случаев (plan.js и модуль K03) data.js/evidence.js — файл и объект — не изменились; '
        'source_snapshot контекста = независимому пересчёту и не зависит от исключений', integrity=integ)

    # ================= часть B: web/resilience.js сборки =================
    breq = []
    for s in S:
        K, env = f'{s["city"]}|{s["category"]}', s['envelope']
        text = (HERE / 'cases' / f'{s["city"]}_{s["category"]}.envelope.json').read_text(encoding='utf-8')
        breq += [dict(id=f'import|{K}', op='import', text=text), dict(id=f'validate|{K}', op='validate', city=s['city'], env=env),
                 dict(id=f'eval0|{K}', op='evaluate', city=s['city'], env=env, selected=[]),
                 dict(id=f'evalm|{K}', op='evaluate', city=s['city'], env=env, selected=env['plan']['selected_ids']),
                 dict(id=f'opt|{K}', op='optimize', city=s['city'], env=env), dict(id=f'export|{K}', op='export', city=s['city'], env=env)]
        nodup = dict(env, cases=[c for c in env['cases'] if c['id'] != 'near-centre-3-again'])
        perm = dict(env, cases=[dict(c, disabled_source_ids=list(reversed(c['disabled_source_ids']))) for c in reversed(env['cases'])])
        breq += [dict(id=f'optnodup|{K}', op='optimize', city=s['city'], env=nodup), dict(id=f'optperm|{K}', op='optimize', city=s['city'], env=perm)]
        other = next(x for x in S if x['city'] != s['city'] and x['category'] == s['category'])
        breq += [dict(id=f'othercity|{K}', op='validate', city=other['city'], env=env),
                 dict(id=f'foreignid|{K}', op='validate', city=s['city'],
                      env=dict(env, cases=[dict(env['cases'][0], disabled_source_ids=[other['envelope']['cases'][0]['disabled_source_ids'][0]])]))]
        # fixtures этапа 2: списки случаев того же среза в этом плане
        for c in json.loads((HERE / 'fixtures/stage2.json').read_text(encoding='utf-8'))['cases']:
            if c['op'] == 'validate' and c['city'] == s['city'] and c['category'] == s['category']:
                breq.append(dict(id=f'map|{K}|{c["id"]}', op='validate', city=s['city'], env=dict(env, cases=c['cases']), _expect=c['expect'],
                                 _case=c['id']))
        for name, label in (('ws', '   '), ('u2028', 'a b'), ('c1', 'a\u0085b'), ('surrogate', 'a\ud800b'), ('rtl', 'א‏ב'), ('html', '<img src=x onerror=alert(1)>')):
            breq.append(dict(id=f'policy|{K}|{name}', op='validate', city=s['city'], env=dict(env, cases=[dict(env['cases'][0], label=label)])))
    s0 = S[0]
    env0, K0 = s0['envelope'], f'{s0["city"]}|{s0["category"]}'
    p13 = copy.deepcopy(env0['plan'])
    p13['candidates'] = p13['candidates'] + [dict(p13['candidates'][0], id=f'x{k}') for k in range(6)] + [dict(p13['candidates'][0], id='bad', lon=0.0)]
    rules = [('derived-per-case', dict(env0, per_case=[]), {'unknown_field'}), ('derived-worst', dict(env0, worst_case_ids=[]), {'unknown_field'}),
             ('derived-verified', dict(env0, verified=True), {'unknown_field'}), ('extra-note', dict(env0, note='x'), {'unknown_field'}),
             ('plan-derived', dict(env0, plan=dict(env0['plan'], derived_results={})), {'derived_not_allowed'}),
             ('missing-cases', {k: v for k, v in env0.items() if k != 'cases'}, {'missing_field'}),
             ('v2-file', dict(env0, schema_version='city-plan-v2'), {'wrong_version'}),
             ('13-candidates-limit-first', dict(env0, plan=p13), {'too_many_candidates'}),
             ('base-in-file', dict(env0, cases=[{'id': 'base', 'label': 'x', 'disabled_source_ids': [env0['cases'][0]['disabled_source_ids'][0]]}]), {'reserved_id'})]
    for name, e, _ in rules:
        breq.append(dict(id=f'rule|{name}', op='validate', city=s0['city'], env=e))
    bt = node_json('resilience_adapter.cjs', {'app_root': str(app), 'cases': [{k: v for k, v in x.items() if not k.startswith('_')} for x in breq]})
    if not bt['available']:
        for chk in ('S3-build-resilience',):
            rec(chk, 'NOT_RUN', f'в сборке {a.target_sha[:12]} нет web/resilience.js — интеграция устойчивости не проверялась (не PASS)')
        return summary_and_save(a.json)
    B = {x['id']: x for x in bt['results']}
    crashes = [k for k, x in B.items() if x.get('crash')]
    if crashes:
        rec('S3-build-adapter', 'FAIL', f'исключения не PlanError в сборке: {len(crashes)}', crashes={k: B[k]['crash'] for k in crashes[:5]})

    errs = []
    for s in S:
        K = f'{s["city"]}|{s["category"]}'
        im, va = B[f'import|{K}'], B[f'validate|{K}']
        mine = RC.validate_cases(RC.source_catalog(data, ev, s['city'], s['category']), s['envelope']['cases'], RC.source_index(data),
                                 [q['id'] for q in s['envelope']['plan']['candidates']])
        if not im['ok'] or not va['ok']:
            errs.append(f'{K}: сборка отклонила файл случаев {im.get("error")} {va.get("error")}')
            continue
        if im['result']['envelope'] != va['result'] or va['result']['cases'] != mine['cases']:
            errs.append(f'{K}: случаи сборки ≠ случаям K03 (канонизация ID/подписей) или импорт ≠ проверке')
        if va['result']['plan']['source_snapshot'] != plan_snapshot(data, s['city']):
            errs.append(f'{K}: snapshot плана изменён')
    rec('S3-build-envelopes', 'FAIL' if errs else 'PASS', 'файлы cases/*.envelope.json K03 (Шымкент и Астана, обе категории) импортируются сборкой '
        '(importResilience); чистые случаи сборки = случаям модуля K03 (отсортированные ID, подписи), snapshot прежний', errors=errs)

    errs, n = [], 0
    for s in S:
        K = f'{s["city"]}|{s["category"]}'
        for tag, exp_after in (('eval0', None), ('evalm', s['expected_after_manual'])):
            r = B[f'{tag}|{K}']
            if not r['ok']:
                errs.append(f'{K}/{tag}: {r.get("error") or r.get("crash")}')
                continue
            pc = {c['case_id']: c for c in r['result']['per_case']}
            if [c['case_id'] for c in r['result']['per_case']] != [c['id'] for c in case_list(s)]:
                errs.append(f'{K}/{tag}: состав/порядок случаев {list(pc)}')
            for c in case_list(s):
                x = pc[c['id']]
                if x['source_records'] != s['n_sources'] - len(c['disabled_source_ids']) or x['disabled_count'] != len(c['disabled_source_ids']):
                    errs.append(f'{K}/{tag}/{c["id"]}: source_records {x["source_records"]}')
                rows = {r_['id']: r_ for r_ in x['rows']}
                for e in s['expected_base'][c['id']]:
                    n += 1
                    rr = rows[e['point']]
                    wb = ({'kind': 'source', 'id': e['base']['id']}, e['base']['mm']) if e['base'] else (None, None)
                    if (rr['nearest_before'], rr['before_mm']) != wb:
                        errs.append(f'{K}/{tag}/{c["id"]}/{e["point"]}: before сборки {rr["nearest_before"]} {rr["before_mm"]} ≠ оракул {wb}')
                if exp_after:
                    for e in exp_after[c['id']]:
                        rr = rows[e['point']]
                        if (rr['nearest_after'], rr['after_mm'], rr['delta_mm']) != (e['after'], e['after_mm'], e['delta_mm']):
                            errs.append(f'{K}/{tag}/{c["id"]}/{e["point"]}: after сборки {rr["nearest_after"]} {rr["after_mm"]} ≠ оракул {e["after"]} {e["after_mm"]}')
            sel = [] if tag == 'eval0' else s['envelope']['plan']['selected_ids']
            rows_or = RB.per_case_rows(data, s['envelope']['plan'], s['envelope']['cases'])
            w = [p['weight'] for p in s['envelope']['plan']['control_points']]
            L = {cid: RB.loss(RB.after_rows(rr_, s['envelope']['plan'], sel), w) for cid, rr_ in rows_or.items()}
            W = max(L.values())
            wv = {'unknown_count': W[0], 'weighted_sum_mm': W[1], 'max_mm': None if W[2] == RB.INF else W[2]}
            wids = sorted((c for c in L if L[c] == W), key=u16)
            if r['result']['worst_vector'] != wv or r['result']['worst_case_ids'] != wids:
                errs.append(f'{K}/{tag}: W сборки {r["result"]["worst_vector"]} {r["result"]["worst_case_ids"]} ≠ оракул {wv} {wids}')
            for cid, l_ in L.items():
                m = pc[cid]['metrics']
                if (m['unknown_count'], m['weighted_sum_mm'], m['max_mm']) != (l_[0], l_[1], None if l_[2] == RB.INF else l_[2]):
                    errs.append(f'{K}/{tag}/{cid}: метрики случая сборки ≠ оракулу')
    rec('S3-build-case-baseline', 'FAIL' if errs else 'PASS',
        f'evaluateResilience сборки: {n} строк before (без выбора и с ручным планом) = baseline оракула по оставшимся записям каждого случая; '
        'after/delta ручного плана, метрики случаев, худший вектор W и список худших случаев = оракулу; source_records = N − k; '
        f'расхождений {len(errs)}', mismatches=errs[:20])

    errs, summ = [], {}
    for s in S:
        K, bf = f'{s["city"]}|{s["category"]}', s['brute_force']
        r = B[f'opt|{K}']
        if not r['ok'] or r['result']['status'] != 'optimal':
            errs.append(f'{K}: {r.get("error") or r["result"]["status"]}')
            continue
        o = r['result']
        for kind in ('nominal', 'robust'):
            x, y = o[kind], bf[kind]
            if x['selected_ids'] != y['selected_ids'] or x['worst_vector'] != y['worst_vector'] or x['worst_case_ids'] != y['worst_case_ids']:
                errs.append(f'{K}/{kind}: сборка {x["selected_ids"]} {x["worst_vector"]} {x["worst_case_ids"]} ≠ перебор {y["selected_ids"]} {y["worst_vector"]} {y["worst_case_ids"]}')
            if (x['base_weighted_mean_mm'] is None) != (y['base_weighted_mean_mm'] is None) or (
                    x['base_weighted_mean_mm'] is not None and abs(x['base_weighted_mean_mm'] - y['base_weighted_mean_mm']) > 1e-9):
                errs.append(f'{K}/{kind}: среднее base')
        pr, pb = o['price_of_robustness_m'], bf['price_of_robustness_m']
        if (pr is None) != (pb is None) or (pr is not None and abs(pr - pb) > 1e-9) or o['same_plan'] != bf['same_plan']:
            errs.append(f'{K}: цена устойчивости {pr} ≠ {pb} или same_plan')
        if o['feasible_count'] != bf['feasible_count'] or o['evaluated'] != 2 ** len(s['envelope']['plan']['candidates']):
            errs.append(f'{K}: feasible {o["feasible_count"]} ≠ {bf["feasible_count"]} или evaluated {o["evaluated"]}')
        summ[K] = {'nominal': o['nominal']['selected_ids'], 'robust': o['robust']['selected_ids'], 'price_m': pr, 'same_plan': o['same_plan'],
                   'robust_worst_case_ids': o['robust']['worst_case_ids']}
    rec('S3-build-optimize', 'FAIL' if errs else 'PASS', 'optimizeResilience сборки = независимому полному перебору K03 на baseline случаев: '
        'обычный и устойчивый план, W, худшие случаи, среднее base, цена устойчивости, same_plan, число допустимых наборов; '
        f'расхождений {len(errs)}', mismatches=errs, plans=summ)

    errs = []
    for s in S:
        K, snap = f'{s["city"]}|{s["category"]}', plan_snapshot(data, s['city'])
        o, ex = B[f'opt|{K}']['result'], B[f'export|{K}']
        if o['source_snapshot'] != snap or o['metric_version'] != 'haversine-mm-v1' or o['objective_version'] != 'worst-lex-v1':
            errs.append(f'{K}: snapshot/версии результата')
        if o['cases'] != [c['id'] for c in case_list(s)]:
            errs.append(f'{K}: список случаев результата')
        if not ex['ok']:
            errs.append(f'{K}: экспорт {ex.get("error")}')
            continue
        e = json.loads(ex['result'])
        if sorted(e) != ['cases', 'plan', 'schema_version'] or 'derived_results' in e['plan'] or e['plan']['source_snapshot'] != snap:
            errs.append(f'{K}: экспорт содержит производные поля или другой snapshot')
        if e != B[f'validate|{K}']['result']:
            errs.append(f'{K}: экспорт ≠ проверенному входу')
    bi = bt['integrity']
    ok = not errs and bi['file_unchanged'] and bi['loaded_unchanged'] and bi['ctx_unchanged'] and all(v['ctx'] == v['recomputed'] for v in bi['snapshots'].values())
    rec('S3-build-invariants', 'PASS' if ok else 'FAIL', 'после validate/evaluate/optimize/export/import сборки: data.js/evidence.js (файл и объект) и '
        'контексты plan.js не изменились; source_snapshot результата = исходному плана (исключения его не подменяют); экспорт — только вход '
        '(schema_version, plan без derived_results, cases)', errors=errs, integrity=bi)

    errs = []
    for s in S:
        K = f'{s["city"]}|{s["category"]}'
        oc, fi = B[f'othercity|{K}'], B[f'foreignid|{K}']
        if oc['ok'] or oc['error']['code'] != 'other_city':
            errs.append(f'{K}: envelope в контексте другого города: {oc.get("error") or "принят"}')
        if fi['ok'] or fi['error']['code'] != 'unknown_source':
            errs.append(f'{K}: ID записи другого города: {fi.get("error") or "принят"}')
    rec('S3-build-other-city', 'FAIL' if errs else 'PASS', 'сборка: envelope в контексте другого города → other_city; ID записи другого города в '
        'disabled_source_ids → unknown_source (оба города, обе категории)', errors=errs)

    errs = []
    for s in S:
        K = f'{s["city"]}|{s["category"]}'
        o, nd, pm = B[f'opt|{K}']['result'], B[f'optnodup|{K}']['result'], B[f'optperm|{K}']['result']
        for kind in ('nominal', 'robust'):
            if o[kind]['selected_ids'] != nd[kind]['selected_ids'] or o[kind]['worst_vector'] != nd[kind]['worst_vector']:
                errs.append(f'{K}/{kind}: повтор набора исключений меняет результат')
            if o[kind]['selected_ids'] != pm[kind]['selected_ids'] or o[kind]['worst_vector'] != pm[kind]['worst_vector'] \
                    or {c['case_id']: c['metrics'] for c in o[kind]['per_case']} != {c['case_id']: c['metrics'] for c in pm[kind]['per_case']}:
                errs.append(f'{K}/{kind}: порядок случаев/ID меняет результат')
        if o['duplicate_case_groups'] != s['identical_sets'] or o['exclusions_digest'] != pm['exclusions_digest'] \
                or o['resilience_problem_digest'] != pm['resilience_problem_digest']:
            errs.append(f'{K}: группы повторов {o["duplicate_case_groups"]} ≠ {s["identical_sets"]} или digest зависит от порядка')
    rec('S3-build-duplicates-order', 'FAIL' if errs else 'PASS', 'повтор набора исключений показан (duplicate_case_groups = identical_sets K03) и не меняет '
        'планы и W; перестановка случаев и ID не меняет результаты по случаям, планы, exclusions_digest и resilience_problem_digest', errors=errs)

    mism, policy, spec, n = [], {}, {}, 0
    for x in breq:
        if not x['id'].startswith('map|'):
            continue
        n += 1
        r, e, cid = B[x['id']], x['_expect'], x['_case'].split('-validate-', 1)[1]
        if r['ok'] != e['ok'] or (not e['ok'] and r['error']['code'] not in CODE_MAP[e['code']]):
            if cid in SPEC_AMBIGUOUS:
                spec.setdefault(cid, []).append(x['id'])
            else:
                mism.append(f'{x["id"]}: сборка {r.get("error") or "принято"}, K03 ожидает {e.get("code") or "принято"}')
        elif not e['ok'] and r['error']['code'] != e['code']:
            policy.setdefault(f'{e["code"]}→{r["error"]["code"]}', set()).add(cid)
    rec('S3-build-validate-map', 'FAIL' if mism else 'PASS',
        f'{n} проверок списков случаев (fixtures этапа 2) в настоящем plan: решение и код сборки = ожиданию K03 по таблице кодов; '
        f'несоответствий {len(mism)}, неоднозначностей спецификации {sum(map(len, spec.values()))}', mismatches=mism[:20],
        code_names={k: sorted(v) for k, v in policy.items()}, spec_ambiguous={k: {'why': SPEC_AMBIGUOUS[k], 'ids': v} for k, v in spec.items()})

    errs = []
    for name, _, want in rules:
        r = B[f'rule|{name}']
        if r['ok'] or r['error']['code'] not in want:
            errs.append(f'{name}: {r.get("error") or "принято"}, ожидалось {sorted(want)}')
    rec('S3-build-envelope-rules', 'FAIL' if errs else 'PASS', 'envelope сборки — только вход: производные поля (per_case, worst_case_ids, verified, '
        'plan.derived_results) и лишние поля отклонены; без cases — missing_field; файл v2 назван; 13 кандидатов → too_many_candidates до проверки '
        'плана (13-й кандидат вне bbox не успевает проверяться); base в файле → reserved_id', errors=errs)

    pol = {}
    for x in breq:
        if x['id'].startswith('policy|'):
            r = B[x['id']]
            lab = x['env']['cases'][0]['label']
            try:
                RC._label(lab, 'label')
                mine = 'принято'
            except RC.CaseErr as e:
                mine = e.code
            pol.setdefault(x['id'].rsplit('|', 1)[1], set()).add((r['error']['code'] if not r['ok'] else 'принято', mine))
    rec('S3-build-policy', 'INFO', 'политика подписей случаев: сборка vs модуль K03 (не PASS/FAIL; для решения координатора)',
        labels={k: sorted(v) for k, v in pol.items()})
    return summary_and_save(a.json)


if __name__ == '__main__':
    sys.exit(main())
