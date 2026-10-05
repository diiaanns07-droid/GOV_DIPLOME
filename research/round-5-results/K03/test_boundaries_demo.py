"""K03 round 5 REVIEW: переносимая регрессия границ для демо BUILD (prototypes/city-evidence).

  python3 test_boundaries_demo.py --app-root <извлечённая копия prototypes/city-evidence> [--url http://127.0.0.1:8765/]
                                  [--json out.json] [--skip-build] [--skip-scenarios] [--v2-patch PATH]

--app-root  — каталог, где лежат web/, tools/, inputs/k03_root/ (копия из git, не рабочий каталог сборщика:
              сценарии пишут только во временные копии).
--url       — адрес запущенного serve.py; оттуда берутся data.js и evidence.js (проверки C5/C6/C2-label).
Нужны shapely и pyproj для проверок, вызывающих K03 assign(); без них эти проверки SKIP.

Исходы: PASS; FAIL; XFAIL — ожидаемое падение известного дефекта baseline (K03 v1 D1/D2 или
отсутствие привязки к версии границ в BUILD 0bf27de), не дефект новой версии без её проверки;
XPASS — ожидаемое падение не произошло (дефект, вероятно, исправлен); SKIP.
Код выхода 1 только при FAIL.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
K03_REL = Path('inputs/k03_root/research/round-3-results/K03')
K03_ROOT_REL = Path('inputs/k03_root')
# Файлы, которые читает K03 Layers()/assign() (geo_common.P_* и сам код), относительно inputs/k03_root
K03_CODE = ['research/round-3-results/K03/boundary_validator.py', 'research/round-3-results/K03/geo_common.py']
K03_LAYERS = ['data/astana_districts.geojson', 'data/geo_sources/astana_districts_overpass.json',
              'data/geo_sources/sara_osm.json',
              'research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson',
              'research/round-3-results/K03/inputs/K10/shymkent_districts_overture.geojson']

# 5 ключевых фикстур из research/round-4-results/K03/fixtures.json @ 3660527 (координаты как там, 9 знаков)
FIXTURES = [
    dict(id='R1', src='AST-HOLE-out0.5', lon=71.409286747, lat=50.881525736, expected=('ambiguous', None),
         baseline_v1=('unmatched', None), defect='D1',
         why='0,5 м за контуром города у зоны AST-Z2: принадлежность городу не доказана → ambiguous, не unmatched'),
    dict(id='R2', src='AST-VER-D2', lon=71.460469423, lat=51.129017713, expected=('ambiguous', None),
         baseline_v1=('matched', 'kz.astana.district.saraishyk'), defect='D2',
         why='1,01 м от границы снимка OSM, 0,58 м от границы Overture той же пары районов → ambiguous'),
    dict(id='R3', src='AST-EX-in', lon=71.665106386, lat=51.330255048, expected=('ambiguous', None),
         baseline_v1=('ambiguous', None), defect=None,
         why='эксклав Байконура ∩ Целиноградский район (AST-Z1) → ambiguous, без района'),
    dict(id='R4', src='AST-SB-a0.99', lon=71.400479487, lat=51.083375685, expected=('ambiguous', None),
         baseline_v1=('ambiguous', None), defect=None,
         why='крайний случай допуска: 0,99 м от общей границы Есиль/Нура → ambiguous'),
    dict(id='R5', src='AST-SB-a1.01', lon=71.400479766, lat=51.083375646, expected=('matched', 'kz.astana.district.esil'),
         baseline_v1=('matched', 'kz.astana.district.esil'), defect=None,
         why='крайний случай допуска: 1,01 м → matched Есиль (защита от чрезмерного исправления)'),
]
FINGERPRINT = {'v1': {'R1': ('unmatched', None), 'R2': ('matched', 'kz.astana.district.saraishyk')},
               'v2': {'R1': ('ambiguous', None), 'R2': ('ambiguous', None)}}

RESULTS = []


def rec(cid, outcome, summary, **details):
    RESULTS.append(dict(check=cid, outcome=outcome, summary=summary, details=details))
    print(f'[{outcome:5}] {cid}: {summary}')


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def parse_js(text):
    return json.loads(text[text.index('{'):text.rstrip().rindex(';')])


def load_js(app_root, url, name):
    if url:
        with urllib.request.urlopen(url.rstrip('/') + '/' + name, timeout=20) as r:
            return parse_js(r.read().decode('utf-8')), f'{url.rstrip("/")}/{name}'
    p = app_root / 'web' / name
    return parse_js(p.read_text(encoding='utf-8')), str(p)


def has_geo():
    return importlib.util.find_spec('shapely') is not None and importlib.util.find_spec('pyproj') is not None


def load_k03(app_root):
    d = app_root / K03_REL
    sys.path.insert(0, str(d))
    spec = importlib.util.spec_from_file_location('k03_bv_under_test', d / 'boundary_validator.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, m.Layers()


def behaviour(BV, L):
    got = {}
    for f in FIXTURES:
        if f['id'] in ('R1', 'R2'):
            r = BV.assign(L, f['lon'], f['lat'])
            got[f['id']] = (r['status'], r.get('district'))
    for name, fp in FINGERPRINT.items():
        if got == fp:
            return name, got
    return 'unknown', got


def rule_version(label):
    return label.rsplit('_', 1)[-1] if label and label.startswith('k03_assign_') else 'unknown'


# ---------------- binding (предложение P1: связь place_district с кодом/слоями/версиями) ----------------

def places_digest(data, city):
    rows = sorted([p['id'], round(p['lon'], 7), round(p['lat'], 7)] for p in data['cities'][city]['places'])
    return sha256_bytes(json.dumps(rows, separators=(',', ':')).encode())


def expected_binding(app_root, data):
    k3 = app_root / K03_ROOT_REL
    b = dict(schema='k03-binding-v1',
             code={p: sha256_bytes((k3 / p).read_bytes()) for p in K03_CODE},
             layers={p: sha256_bytes((k3 / p).read_bytes()) for p in K03_LAYERS},
             places={c: places_digest(data, c) for c in data['cities']})
    return b


def binding_digest(b):
    core = {k: b[k] for k in ('schema', 'rule', 'code', 'layers', 'places') if k in b}
    return sha256_bytes(json.dumps(core, sort_keys=True, separators=(',', ':')).encode())


def check_binding(app_root, data, ev, where):
    b = ev.get('boundary_binding')
    if not b:
        rec('C6-binding', 'XFAIL', 'evidence.js не содержит boundary_binding: place_district не связан с кодом/слоями/версией '
            '— устаревшая привязка не обнаруживается без пересборки (известно для BUILD 0bf27de, предложение P1)',
            evidence=where, top_level_keys=sorted(ev))
        return None
    problems = []
    if app_root is None:
        rec('C6-binding', 'SKIP', 'binding есть, но без --app-root его не с чем сверить', evidence=where)
        return b
    exp = expected_binding(app_root, data)
    for part in ('code', 'layers', 'places'):
        for k, v in exp[part].items():
            if b.get(part, {}).get(k) != v:
                problems.append(f'{part}:{k}')
    for city, cd in ev['cities'].items():
        for pid, r in cd['place_district'].items():
            if 'lonlat' not in r:
                problems.append(f'place {city}/{pid}: нет lonlat')
                break
    if b.get('digest') != binding_digest(b):
        problems.append('digest не соответствует содержимому binding')
    rec('C6-binding', 'FAIL' if problems else 'PASS',
        'привязка устарела или неполна: ' + ', '.join(problems[:6]) if problems
        else 'boundary_binding совпадает с текущими кодом K03, слоями и точками data.js', evidence=where,
        problems=problems)
    return b


# ---------------- проверки ----------------

def c1_inputs(app_root):
    man = json.loads((app_root / 'source_manifest.json').read_text(encoding='utf-8'))
    k3 = [f for f in man['files'] if f['copied_to'].startswith('inputs/k03_root/')]
    bad = [f['copied_to'] for f in k3 if sha256_bytes((app_root / f['copied_to']).read_bytes()) != f['sha256']]
    shas = {f['sha'] for f in k3}
    rec('C1-k03-inputs', 'FAIL' if bad else 'PASS',
        f'{len(k3)} файлов K03 из source_manifest.json; несовпадений sha256: {len(bad)}; источник K03 SHA {sorted(shas)}',
        mismatched=bad, k03_source_sha=sorted(shas),
        validator_sha256=sha256_bytes((app_root / K03_REL / 'boundary_validator.py').read_bytes()))


def c2_identity(app_root, BV, L, ev, where):
    beh, got = behaviour(BV, L)
    self_label = BV.assign(L, 71.43, 51.128)['rule']
    ev_label = ev.get('assign_rule')
    obs_labels = sorted({o['method']['id'] for c in ev['cities'].values() for o in c['observations']
                         if o['indicator_id'].startswith('district_status.')})
    versions = {'behaviour': beh, 'assign_result_rule': rule_version(self_label),
                'evidence_assign_rule': rule_version(ev_label), **{f'obs_method:{x}': rule_version(x) for x in obs_labels}}
    ok = len(set(versions.values())) == 1 and beh != 'unknown'
    rec('C2-module-is-what-label-says', 'PASS' if ok else 'FAIL',
        f'поведение={beh}, assign()[rule]={self_label}, evidence.assign_rule={ev_label}, method.id={obs_labels}',
        versions=versions, fingerprint_results={k: list(v) for k, v in got.items()}, evidence=where)
    return beh


def c3_fixtures(BV, L, beh):
    for f in FIXTURES:
        r = BV.assign(L, f['lon'], f['lat'])
        got = (r['status'], r.get('district'))
        if got == f['expected']:
            out = 'XPASS' if f['defect'] and f['baseline_v1'] != f['expected'] and beh == 'v1' else 'PASS'
        elif f['defect'] and got == f['baseline_v1']:
            out = 'XFAIL'
        else:
            out = 'FAIL'
        rec(f"C3-{f['id']}-{f['src']}", out,
            f"{f['why']}; получено {got[0]}/{got[1]}" + (f" (известный дефект {f['defect']} правила v1)" if out == 'XFAIL' else ''),
            point=[f['lon'], f['lat']], expected=list(f['expected']), got=list(got), reason=r.get('reason'),
            baseline_v1=list(f['baseline_v1']), defect=f['defect'], source_fixture=f"round-4 K03 fixtures.json:{f['src']}")


def c4_c5_build(app_root, BV, L, data, ev, skip_build):
    if not skip_build:
        tmp = Path(tempfile.mkdtemp(prefix='k03r5_build_'))
        try:
            app = tmp / 'app'
            shutil.copytree(app_root, app)
            p = subprocess.run([sys.executable, 'tools/build_evidence.py'], cwd=app, capture_output=True, text=True, timeout=600)
            same = p.returncode == 0 and (app / 'web/evidence.js').read_bytes() == (app_root / 'web/evidence.js').read_bytes()
            rec('C4-build-path', 'PASS' if same else 'FAIL',
                'tools/build_evidence.py в копии app-root воспроизводит web/evidence.js побайтно' if same
                else f'пересборка дала другой evidence.js или ошибку (код {p.returncode}) — закоммиченный файл устарел или сборка не детерминирована',
                returncode=p.returncode, stdout=p.stdout[-800:], stderr=p.stderr[-800:])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    problems, n = [], 0
    for city, cd in data['cities'].items():
        pd = ev['cities'][city]['place_district']
        ids = {p['id'] for p in cd['places']}
        extra = sorted(set(pd) - ids)
        if extra:
            problems.append(f'{city}: {len(extra)} записей evidence без места в data.js')
        for p in cd['places']:
            n += 1
            r = pd.get(p['id'])
            if r is None:
                problems.append(f'{city}/{p["id"]}: нет place_district')
                continue
            if r['status'] == 'matched' and (not r['district'] or r['candidates'] != [r['district']]):
                problems.append(f'{city}/{p["id"]}: matched без однозначного района')
            if r['status'] != 'matched' and r.get('district'):
                problems.append(f'{city}/{p["id"]}: {r["status"]} с районом {r["district"]}')
            if BV is not None:
                a = BV.assign(L, p['lon'], p['lat'])
                if (a['status'], a.get('district')) != (r['status'], r.get('district')):
                    problems.append(f'{city}/{p["id"]}: evidence {r["status"]}/{r.get("district")} ≠ assign {a["status"]}/{a.get("district")}')
    rec('C5-place-district-consistent', 'FAIL' if problems else 'PASS',
        f'{n} мест data.js: ' + ('; '.join(problems[:5]) if problems else
                                  'у каждого есть запись, форма статуса верна' + (', совпадает с assign() модуля app-root' if BV else '')),
        problems=problems[:50], places=n, recomputed=BV is not None)


def _unittest_outcome(text):
    tail = text.strip().splitlines()[-1] if text.strip() else ''
    crashed = 'errors=' in tail
    failed = 'failures=' in tail
    return tail, crashed, failed


def _mutate_s1(app):
    """Реальная синхронизация слоёв: геометрия Алматы и Сарайшыка в снимке OSM ← версия Overture из того же пакета."""
    f = app / K03_ROOT_REL / 'data/astana_districts.geojson'
    ov = json.loads((app / K03_ROOT_REL / K03_LAYERS[3]).read_text(encoding='utf-8'))
    by_rel = {}
    for x in ov['features']:
        osm = next((s_['record_id'] for s_ in x['properties']['sources'] if s_['dataset'] == 'OpenStreetMap'), '')
        by_rel[int(osm.lstrip('r').split('@')[0])] = x['geometry']
    g = json.loads(f.read_text(encoding='utf-8'))
    for x in g['features']:
        if x['properties']['osm_id'] in (3482819, 19733918):
            x['geometry'] = by_rel[x['properties']['osm_id']]
    f.write_text(json.dumps(g, ensure_ascii=False), encoding='utf-8')
    return 'снимок OSM ← геометрия Алматы и Сарайшыка из Overture 2026-09-23.1 (реальные данные пакета; так будет, если слои синхронизируются)'


def _mutate_s2(app):
    """Синтетическое обновление K10: одно место Сарыарки переносится к месту Байконура; data.js пересобирается, evidence.js — нет."""
    pf = app / 'inputs/k10/data/astana/places_social.geojson'
    ev = parse_js((app / 'web/evidence.js').read_text(encoding='utf-8'))['cities']['astana']['place_district']
    g = json.loads(pf.read_text(encoding='utf-8'))
    sary = next(x for x in g['features'] if ev.get(x['id'], {}).get('district') == 'kz.astana.district.saryarka')
    baik = next(x for x in g['features'] if ev.get(x['id'], {}).get('district') == 'kz.astana.district.baikonur')
    lon, lat = baik['geometry']['coordinates'][:2]
    sary['geometry']['coordinates'] = [lon + 1e-5, lat + 1e-5]
    raw = json.dumps(g, ensure_ascii=False).encode('utf-8')
    pf.write_bytes(raw)
    mp = app / 'inputs/k10/package_manifest.json'
    m = json.loads(mp.read_text(encoding='utf-8'))
    fm = m['cities']['astana']['files']['places_social']
    fm['sha256'], fm['bytes'] = sha256_bytes(raw), len(raw)
    mp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding='utf-8')
    r = subprocess.run([sys.executable, 'tools/build_data.py'], cwd=app, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError('build_data.py: ' + r.stderr[-300:])
    return f'синтетика: место {sary["id"][:8]}… (Сарыарка) перенесено к месту Байконура; K10-манифест и data.js обновлены, evidence.js не пересобран'


def _mutate_s3(app, v2_patch):
    subprocess.run(['git', 'apply', '--directory=inputs/k03_root', str(Path(v2_patch).resolve())],
                   cwd=app, check=True, capture_output=True)
    return 'к копии применён patch k03_assign_v2 (round-4 K03); evidence.js не пересобран'


def c7_scenarios(app_root, v2_patch):
    """Устаревание на фактическом пути сборки: меняем входы во временной копии app-root, evidence.js не трогаем."""
    if not v2_patch or not Path(v2_patch).exists():
        v2_patch = None
    for sid in ('S1-layer-sync-real', 'S2-k10-place-moved-synthetic', 'S3-rule-update-v2'):
        if sid.startswith('S3') and not v2_patch:
            rec(f'C7-{sid}', 'SKIP', 'patch v2 не найден (--v2-patch)')
            continue
        tmp = Path(tempfile.mkdtemp(prefix='k03r5_scn_'))
        try:
            app = tmp / 'app'
            shutil.copytree(app_root, app)
            desc = {'S1': _mutate_s1, 'S2': _mutate_s2}[sid[:2]](app) if sid[:2] != 'S3' else _mutate_s3(app, v2_patch)
            before = parse_js((app / 'web/evidence.js').read_text(encoding='utf-8'))
            data = parse_js((app / 'web/data.js').read_text(encoding='utf-8'))
            t = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], cwd=app,
                               capture_output=True, text=True, timeout=900)
            tail, crashed, failed = _unittest_outcome(t.stderr or t.stdout)
            b = before.get('boundary_binding')
            fp_detect = None
            if b:
                exp = expected_binding(app, data)
                fp_detect = any(b.get(part, {}).get(k) != v for part in ('code', 'layers', 'places') for k, v in exp[part].items())
            fresh = app / 'tools/check_evidence_fresh.py'
            tool_detect = None
            if fresh.exists():
                tool_detect = subprocess.run([sys.executable, str(fresh)], cwd=app, capture_output=True, text=True).returncode != 0
            detected = failed or bool(fp_detect) or bool(tool_detect)
            p = subprocess.run([sys.executable, 'tools/build_evidence.py'], cwd=app, capture_output=True, text=True, timeout=600)
            crash_build = p.returncode != 0 and 'Traceback' in p.stderr
            changed, label = None, None
            if p.returncode == 0:
                after = parse_js((app / 'web/evidence.js').read_text(encoding='utf-8'))
                changed = sum(1 for c in after['cities'] for pid, r in after['cities'][c]['place_district'].items()
                              if (r['status'], r.get('district')) != (before['cities'][c]['place_district'].get(pid, {}).get('status'),
                                                                      before['cities'][c]['place_district'].get(pid, {}).get('district')))
                label = after.get('assign_rule')
            notes, outcome = [], 'PASS'
            if crash_build or crashed:
                outcome = 'XFAIL'
                notes.append('K03 assign() падает с исключением (дефект D3: пустая зона неоднозначности) — пересборка невозможна')
            if not detected:
                outcome = 'XFAIL'
                notes.append('устаревание evidence.js не обнаруживается до пересборки (нет привязки к версии, предложение P1)')
            if sid.startswith('S3') and label is not None and rule_version(label) != 'v2':
                outcome = 'XFAIL'
                notes.append(f'после пересборки код ведёт себя как v2, но метка в evidence.js {label}: метка берётся из реестра, а не из кода (P1)')
            rec(f'C7-{sid}', outcome,
                f'{desc}. До пересборки: тесты приложения — {tail or "?"}; binding — '
                f'{"нет" if fp_detect is None else ("ловит" if fp_detect else "не ловит")}; check_evidence_fresh — '
                f'{"нет" if tool_detect is None else ("ловит" if tool_detect else "не ловит")}. Пересборка: '
                + (f'код {p.returncode}' + (', исключение' if crash_build else '') if p.returncode else
                   f'ok, place_district изменился у {changed} мест, метка {label}') + ('. ' + '; '.join(notes) if notes else ''),
                app_tests=tail, app_tests_crashed=crashed, app_tests_failed=failed, binding_detects=fp_detect,
                fresh_tool_detects=tool_detect, rebuild_returncode=p.returncode, rebuild_crashed=crash_build,
                rebuild_stderr_tail=p.stderr[-300:], place_district_changed=changed, label_after_rebuild=label,
                known_baseline_issues=notes)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--app-root', type=Path)
    ap.add_argument('--url')
    ap.add_argument('--json', type=Path)
    ap.add_argument('--skip-build', action='store_true')
    ap.add_argument('--skip-scenarios', action='store_true')
    ap.add_argument('--v2-patch', default=str(HERE / 'inputs/k03_assign_v2.patch'))
    a = ap.parse_args()
    if not a.app_root and not a.url:
        ap.error('нужен --app-root и/или --url')
    app_root = a.app_root.resolve() if a.app_root else None
    data, dwhere = load_js(app_root, a.url, 'data.js')
    ev, ewhere = load_js(app_root, a.url, 'evidence.js')
    BV = L = None
    if app_root:
        c1_inputs(app_root)
        if has_geo():
            BV, L = load_k03(app_root)
            beh = c2_identity(app_root, BV, L, ev, ewhere)
            c3_fixtures(BV, L, beh)
        else:
            rec('C2/C3', 'SKIP', 'нет shapely/pyproj — assign() не вызывается')
    else:
        rec('C1-C4,C7', 'SKIP', 'только --url: исходники и модуль K03 недоступны')
        labels = {ev.get('assign_rule')}
        rec('C2-label-only', 'PASS' if len(labels) == 1 else 'FAIL', f'метка правила в отдаваемом evidence.js: {labels}', evidence=ewhere)
    c4_c5_build(app_root, BV, L, data, ev, a.skip_build or not app_root or BV is None) if app_root else c4_c5_build(None, None, None, data, ev, True)
    check_binding(app_root, data, ev, ewhere)
    if app_root and not a.skip_scenarios and BV is not None:
        c7_scenarios(app_root, a.v2_patch)
    summary = {k: sum(1 for r in RESULTS if r['outcome'] == k) for k in ('PASS', 'FAIL', 'XFAIL', 'XPASS', 'SKIP')}
    out = dict(test='research/round-5-results/K03/test_boundaries_demo.py', app_root=str(app_root) if app_root else None,
               url=a.url, data_js=dwhere, evidence_js=ewhere, summary=summary, results=RESULTS,
               python=sys.version.split()[0])
    if a.json:
        a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('SUMMARY', json.dumps(summary))
    return 1 if summary['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
