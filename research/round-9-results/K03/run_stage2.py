"""K03 r9, этап 2: построитель случаев исключения — JS (resilience_cases.js на контексте настоящего plan.js) и Python-оракул.

  python3 research/round-9-results/K03/run_stage2.py --app-root <копия prototypes/city-evidence> --target-sha <SHA> [--js PATH] [--json out]

S2-fixtures-match-build  данные сборки = данным fixtures (иначе TEST_INCOMPATIBLE);
S2-python-oracle / S2-js  ожидания fixtures (по построению из data.js/evidence.js);
S2-js-python-parity      полное совпадение результатов (кроме заморозки, она есть только в JS);
S2-digest-invariance     digest исключений не зависит от порядка случаев и ID, меняется от подписи/набора; JS = Python;
S2-no-auto-exclusion     ни одна функция не создаёт случай без явного выбора; QA только показывается;
S2-wording               подписи по умолчанию «условно…», без «закрытия/кризиса/риска/дубликата»; примечание CORE_SPEC;
S2-integrity             data.js/evidence.js (файл и объект) не изменились; source_snapshot = пересчёту.
"""
import argparse
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from r9_common import OUT, rec, parse_js, sha256_file, plan_snapshot, summary_and_save  # noqa: E402
import resilience_cases_ref as RC  # noqa: E402
from run_tests import get_path, norm  # noqa: E402  (r8: путь 'a.b[2].c', 1 == 1.0)

JS_ONLY = ('frozen', 'mutation_blocked')
FORBIDDEN = re.compile(r'закрыт|кризис|риск|вероятн|дубликат|прогноз', re.I)


def py_run(c, data, ev, idx, cats):
    try:
        cat = None
        if c.get('category'):
            k = (c['city'], c['category'])
            if k not in cats:
                cats[k] = RC.source_catalog(data, ev, *k)
            cat = cats[k]
        opts = dict(c.get('opts') or {}, index=idx)
        if c.get('candidate_ids'):
            opts['candidate_ids'] = c['candidate_ids']
        op = c['op']
        if op == 'catalog':
            r = {'catalog': cat}
        elif op == 'groups':
            r = RC.colocated_groups(ev, cat)
        elif op == 'single':
            r = RC.single_case(cat, c['source_id'], opts)
        elif op == 'group':
            r = RC.group_case(cat, c['source_ids'], opts)
        elif op == 'colocated':
            r = RC.colocated_case(ev, cat, c['index'], opts)
        elif op == 'validate':
            r = RC.validate_cases(cat, c['cases'], idx, c.get('candidate_ids'))
        elif op == 'envelope':
            r = RC.check_envelope_shape(c['envelope']) and 'ok'
        elif op == 'digest':
            r = RC.exclusion_digest(cat, RC.validate_cases(cat, c['cases'], idx)['cases'])
        elif op == 'manifest':
            r = {'manifest': RC.exclusion_manifest(cat, RC.validate_cases(cat, c['cases'], idx, c.get('candidate_ids')), c.get('build'))}
        else:
            raise ValueError(op)
        return {'ok': True, 'result': copy.deepcopy(r)}
    except RC.CaseErr as e:
        return {'ok': False, 'error': {'code': e.code, 'path': e.path}}


def js_run(app, js, cases):
    node = shutil.which('node')
    if not node:
        return None, 'node не установлен'
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        fh.write(json.dumps({'app_root': str(app), 'cases': cases}, ensure_ascii=True))
        req = fh.name
    try:
        r = subprocess.run([node, str(HERE / 'cases_runner.cjs'), req, str(js)], capture_output=True, text=True, timeout=600)
    finally:
        Path(req).unlink()
    if r.returncode:
        return None, f'node код {r.returncode}: {r.stderr[-400:]}'
    doc = json.loads(r.stdout)
    return {x['id']: x for x in doc['results']}, doc['integrity']


def check(name, c, r, js):
    e = c['expect']
    if r.get('crash'):
        return f'{name}: исключение {r["crash"][:200]}'
    if r['ok'] != e['ok']:
        return f'{name}: ok={r["ok"]} {r.get("error")}, ожидалось {e}'
    if not e['ok']:
        if (r['error']['code'], r['error']['path']) != (e['code'], e['path']):
            return f'{name}: {r["error"]} ≠ {e["code"]} @ {e["path"]}'
        return None
    for path, want in (e.get('result') or {}).items():
        if path.startswith('js:'):
            if not js:
                continue
            path = path[3:]
        got = get_path(r.get('result'), path) if not ('.' in path and path.split('.')[0] == 'manifest' and '.records.' in path) \
            else rec_path(r.get('result'), path)
        if norm(got) != norm(want):
            return f'{name}: {path} = {json.dumps(got, ensure_ascii=False)[:120]}, ожидалось {json.dumps(want, ensure_ascii=False)[:120]}'
    return None


def rec_path(obj, path):
    """manifest.records.<ID>.a.b — ID содержит '-' и цифры, поэтому разбирается отдельно."""
    head, rest = path.split('.records.', 1)
    rid, _, tail = rest.partition('.')
    base = get_path(obj, head + '.records')
    if not isinstance(base, dict) or rid not in base:
        return '<missing>'
    return get_path(base[rid], tail) if tail else base[rid]


def strip_js(v):
    return {k: x for k, x in v.items() if k not in JS_ONLY} if isinstance(v, dict) else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    ap.add_argument('--js', type=Path, default=HERE / 'resilience_cases.js')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    app = a.app_root.resolve()
    doc = json.loads((HERE / 'fixtures/stage2.json').read_text(encoding='utf-8'))
    have = {'data_js_sha256': sha256_file(app / 'web/data.js'), 'evidence_js_sha256': sha256_file(app / 'web/evidence.js')}
    diff = [k for k in have if doc['target'].get(k) != have[k]]
    if diff:
        rec('S2-fixtures-match-build', 'TEST_INCOMPATIBLE', f'fixtures построены на {doc["target"]["sha"][:12]}, {diff} сборки другие — make_stage2.py', diff=diff)
        return summary_and_save(a.json)
    rec('S2-fixtures-match-build', 'PASS', f'fixtures этапа 2 построены на данных этой сборки ({a.target_sha[:12]})')
    data, ev = parse_js(app / 'web/data.js'), parse_js(app / 'web/evidence.js')
    data0, ev0 = copy.deepcopy(data), copy.deepcopy(ev)
    idx, cats = RC.source_index(data), {}
    py = {c['id']: py_run(c, data, ev, idx, cats) for c in doc['cases']}
    bad = [m for c in doc['cases'] if (m := check('py ' + c['id'], c, py[c['id']], False))]
    rec('S2-python-oracle', 'FAIL' if bad else 'PASS', f'{len(doc["cases"])} случаев: несоответствий {len(bad)}', mismatches=bad[:20])

    # дополнительные запросы для свойств: перестановки, другая подпись/набор
    extra = []
    for city in ('astana', 'shymkent'):
        for cat in ('school', 'outpatient_clinic'):
            base = next(c for c in doc['cases'] if c['op'] == 'validate' and c['id'].endswith('-validate-mixed') and c['city'] == city and c['category'] == cat)
            cs = base['cases']
            perm = [dict(x, disabled_source_ids=list(reversed(x['disabled_source_ids']))) for x in reversed(cs)]
            relabel = [dict(cs[0], label=cs[0]['label'] + '!')] + cs[1:]
            reset = [dict(cs[0], disabled_source_ids=cs[1]['disabled_source_ids'][:2])] + cs[1:]
            for tag, lst in (('orig', cs), ('perm', perm), ('relabel', relabel), ('reset', reset)):
                extra.append(dict(id=f'D:{city}:{cat}:{tag}', op='digest', city=city, category=cat, cases=lst))
            extra.append(dict(id=f'P:{city}:{cat}', op='probe', city=city, category=cat))
    pyx = {c['id']: py_run(c, data, ev, idx, cats) for c in extra if c['op'] != 'probe'}

    jsr, integ = js_run(app, a.js.resolve(), doc['cases'] + extra)
    if jsr is None:
        rec('S2-js', 'NOT_RUN', integ)
        return summary_and_save(a.json)
    badj = [m for c in doc['cases'] if (m := check('js ' + c['id'], c, jsr[c['id']], True))]
    rec(f'S2-js ({a.js.name})', 'FAIL' if badj else 'PASS', f'{len(doc["cases"])} случаев: несоответствий {len(badj)}', mismatches=badj[:20])
    par = []
    for c in doc['cases']:
        j, p = jsr[c['id']], py[c['id']]
        jj = {k: (strip_js(v) if k == 'result' else v) for k, v in j.items() if k != 'id'}
        if norm(jj) != norm(p):
            par.append(c['id'])
    rec('S2-js-python-parity', 'FAIL' if par else 'PASS', f'полное совпадение результатов JS и Python (каталог, случаи, ошибки, manifest): расхождений {len(par)}',
        ids=par[:20])

    errs = []
    for city in ('astana', 'shymkent'):
        for cat in ('school', 'outpatient_clinic'):
            d = {t: (jsr[f'D:{city}:{cat}:{t}']['result'], pyx[f'D:{city}:{cat}:{t}']['result']) for t in ('orig', 'perm', 'relabel', 'reset')}
            if any(j != p for j, p in d.values()):
                errs.append(f'{city}/{cat}: digest JS ≠ Python')
            if d['orig'][0] != d['perm'][0] or d['orig'][1] != d['perm'][1]:
                errs.append(f'{city}/{cat}: digest зависит от порядка случаев/ID')
            if d['orig'][0] in (d['relabel'][0], d['reset'][0]):
                errs.append(f'{city}/{cat}: digest не меняется от подписи или набора')
            m = py[f'{city[:3].upper()}{"S" if cat == "school" else "C"}-manifest']['result']['manifest']
            if m['exclusion_digest'] != d['orig'][1]:
                errs.append(f'{city}/{cat}: digest manifest ≠ digest случаев')
    rec('S2-digest-invariance', 'FAIL' if errs else 'PASS',
        'digest исключений: перестановка случаев и ID не меняет его, другая подпись или набор меняют; JS = Python; manifest хранит тот же digest '
        f'вместе с base_source_snapshot; ошибок {len(errs)}', errors=errs)

    errs = []
    for c in doc['cases']:
        if c['op'] == 'catalog':
            for name, r in (('js', jsr[c['id']]), ('py', py[c['id']])):
                if 'cases' in r['result'] or 'cases' in r['result']['catalog'] or 'disabled_source_ids' in json.dumps(r['result']):
                    errs.append(f'{name} {c["id"]}: каталог содержит случаи')
        if c['op'] == 'groups':
            for name, r in (('js', jsr[c['id']]), ('py', py[c['id']])):
                if any(k not in ('index', 'lon', 'lat', 'size', 'ids_in_category', 'ids_other_categories') for g in r['result']['groups'] for k in g):
                    errs.append(f'{name} {c["id"]}: список групп создаёт что-то кроме описания')
    src = (a.js.resolve()).read_text(encoding='utf-8')
    probes = {k: v['result'] for k, v in jsr.items() if k.startswith('P:')}
    builders = {'singleCase', 'groupCase', 'colocatedCase', 'validateCases', 'colocatedGroups', 'sourceCatalog'}
    for k, r in probes.items():
        for fn, o in r.items():
            if fn != 'exported' and o['created']:
                errs.append(f'JS {k}: {fn} без явного выбора создал случай')
        unknown = [f for f in r['exported'] if f not in builders | {'isId', 'canon', 'sourceIndex', 'nextCaseId', 'defaultLabel', 'checkEnvelopeShape',
                                                                   'makeEnvelope', 'caseView', 'exclusionDigest', 'exclusionManifest', 'CaseError'}]
        if unknown:
            errs.append(f'JS: новые экспортируемые функции без проверки на автоисключение: {unknown}')
    for city in ('astana', 'shymkent'):
        for cat in ('school', 'outpatient_clinic'):
            c = cats[(city, cat)]
            for f in (lambda: RC.single_case(c, None, {'id': 'p', 'index': idx}), lambda: RC.group_case(c, None, {'id': 'p', 'index': idx}),
                      lambda: RC.colocated_case(ev, c, None, {'id': 'p', 'index': idx}), lambda: RC.validate_cases(c, None, idx)):
                try:
                    r = f()
                    if r.get('case') or r.get('disabled_source_ids'):
                        errs.append(f'py {city}/{cat}: случай без явного выбора')
                except RC.CaseErr:
                    pass
    no_idx = [c['id'] for c in doc['cases'] if c['id'].endswith('-colocated-no-index')]
    rec('S2-no-auto-exclusion', 'FAIL' if errs or not no_idx else 'PASS',
        f'каталог и список QA-групп ничего не исключают; каждая экспортируемая функция без явного выбора не создаёт случай '
        f'(поведенческая проба JS и Python на 4 срезах); случай из QA-группы — только по явно указанному индексу '
        f'({len(no_idx)} случаев без индекса → unknown_qa_group); у Астаны групп нет → no_qa_group, группа не придумывается; ошибок {len(errs)}',
        errors=errs)

    labels = [r['result']['label'] for c in doc['cases'] for r in (jsr[c['id']],) if r['ok'] and c['op'] in ('single', 'group') and 'label' not in (c.get('opts') or {})]
    labels += [r['result']['case']['label'] for c in doc['cases'] for r in (jsr[c['id']],) if r['ok'] and c['op'] == 'colocated' and r['result']['case']]
    bad = [x for x in labels if not x.startswith('Условно') or FORBIDDEN.search(x)]
    js_note = re.search(r'NOTE_RU = "([^"]+)"', src)
    note_ok = js_note and js_note.group(1) == RC.NOTE_RU and RC.NOTE_RU.startswith('Условно исключаем из расчёта; это не подтверждение закрытия')
    rec('S2-wording', 'FAIL' if bad or not note_ok else 'PASS',
        f'{len(labels)} подписей по умолчанию начинаются с «Условно» и не содержат «закрытие/кризис/риск/дубликат/прогноз»; '
        'примечание = формулировке CORE_SPEC («Условно исключаем из расчёта; это не подтверждение закрытия»)', bad=bad[:10], examples=labels[:4])

    snaps_ok = all(v['ctx'] == v['recomputed'] == plan_snapshot(data, k) for k, v in integ['snapshots'].items())
    ok = integ['file_unchanged'] and integ['loaded_unchanged'] and snaps_ok and data == data0 and ev == ev0
    rec('S2-integrity', 'PASS' if ok else 'FAIL', 'после всех построений data.js/evidence.js (файл, объект JS, объект Python) не изменились; '
        'source_snapshot plan.js = независимому пересчёту', integrity=integ)
    return summary_and_save(a.json)


if __name__ == '__main__':
    sys.exit(main())
