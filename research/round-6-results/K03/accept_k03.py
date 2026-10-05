"""K03 round 6: приёмка K03 в сборке BUILD (адаптер к раскладке inputs/k03v2_root).

  python3 research/round-6-results/K03/accept_k03.py --app-root <копия prototypes/city-evidence> [--repo-sha SHA] [--json out.json]

Отличия от research/round-5-results/K03/test_boundaries_demo.py (TEST_INCOMPATIBLE с 064ed25, см. STATUS.md):
  * корень K03 берётся из K03_DIR в tools/build_evidence.py, а не жёстко inputs/k03_root;
  * наблюдения статусов ищутся по полю source.path/derivation, а не по префиксу indicator_id;
  * нет списка XFAIL: каждый инвариант — PASS или FAIL (SKIP только если проверка не выполнялась);
  * устаревание проверяется собственной командой сборки tools/check_all.py, а не наличием поля boundary_binding.
Сценарии меняют только временные копии (раскладка как в репозитории: <tmp>/prototypes/city-evidence + <tmp>/agent).
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R5 = ROOT / 'research/round-5-results/K03/test_boundaries_demo.py'
OUT = []

# 5 ключевых фикстур (из round-4 K03 fixtures.json @ 3660527; те же, что в round-5 тесте). Ожидание — контракт v2.
FIXTURES = [
    ('R1', 'AST-HOLE-out0.5', 71.409286747, 50.881525736, 'ambiguous', None),
    ('R2', 'AST-VER-D2', 71.460469423, 51.129017713, 'ambiguous', None),
    ('R3', 'AST-EX-in', 71.665106386, 51.330255048, 'ambiguous', None),
    ('R4', 'AST-SB-a0.99', 71.400479487, 51.083375685, 'ambiguous', None),
    ('R5', 'AST-SB-a1.01', 71.400479766, 51.083375646, 'matched', 'kz.astana.district.esil'),
]
V1_FINGERPRINT = {'R1': ['unmatched', None], 'R2': ['matched', 'kz.astana.district.saraishyk']}


def rec(inv, check, verdict, summary, **d):
    OUT.append(dict(invariant=inv, check=check, verdict=verdict, summary=summary, details=d))
    print(f'[{verdict:4}] {inv}/{check}: {summary}')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def parse_js(p):
    t = Path(p).read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def k03_root_name(app):
    src = (app / 'tools/build_evidence.py').read_text(encoding='utf-8')
    m = re.search(r'K03_DIR\s*=\s*APP\s*/\s*"inputs"\s*/\s*"([^"]+)"', src)
    return m.group(1) if m else 'k03_root'


def k03_dir(app, root):
    return app / 'inputs' / root / 'research/round-3-results/K03'


def py_k03(app, root, body, timeout=600):
    """Выполнить код с K03 из app в отдельном процессе; возвращает (rc, stdout JSON|None, stderr)."""
    code = ('import sys, json; sys.path.insert(0, sys.argv[1]); import boundary_validator as BV; L = BV.Layers()\n' + body)
    r = subprocess.run([sys.executable, '-c', code, str(k03_dir(app, root))], capture_output=True, text=True, timeout=timeout)
    out = None
    if r.returncode == 0 and r.stdout.strip():
        out = json.loads(r.stdout.strip().splitlines()[-1])
    return r.returncode, out, r.stderr


def layout(app_root, repo_sha):
    tmp = Path(tempfile.mkdtemp(prefix='k03r6_'))
    app = tmp / 'prototypes' / 'city-evidence'
    shutil.copytree(app_root, app, ignore=shutil.ignore_patterns('__pycache__'))
    if repo_sha:
        ls = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', repo_sha, '--', 'agent/'], cwd=ROOT, text=True)
        for rel in ls.split():
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(subprocess.check_output(['git', 'show', f'{repo_sha}:{rel}'], cwd=ROOT))
    return tmp, app


def check_all(app):
    log = app.parent.parent / 'check_all_log.json'
    r = subprocess.run([sys.executable, 'tools/check_all.py', '--log', str(log)], cwd=app, capture_output=True, text=True, timeout=900)
    res = json.loads(log.read_text(encoding='utf-8')) if log.exists() else None
    failed = [f"{x['step']}: {x['check']}" for x in (res or {}).get('results', []) if x['status'] == 'FAIL']
    return r.returncode, failed, res and dict(passed=res['passed'], skipped=res['skipped'], failed=res['failed'])


def run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    return r.returncode, (r.stdout + r.stderr)[-500:]


# ---------------- I0: исходная сборка без изменений ----------------

def i0(app_root, repo_sha, root):
    tmp, app = layout(app_root, repo_sha)
    try:
        rc, failed, summ = check_all(app)
        rec('I0', 'check_all-clean', 'PASS' if rc == 0 else 'FAIL',
            f'tools/check_all.py на неизменённой копии: {summ}', returncode=rc, failed=failed)
        ev = parse_js(app / 'web/evidence.js')
        data = parse_js(app / 'web/data.js')
        pts = {c: [[p['id'], p['lon'], p['lat']] for p in data['cities'][c]['places']] for c in data['cities']}
        body = ('pts = json.loads(sys.stdin.read())\n'
                'print(json.dumps({c: {i: [BV.assign(L, x, y)["status"], BV.assign(L, x, y).get("district")] '
                'for i, x, y in v} for c, v in pts.items()}))')
        r = subprocess.run([sys.executable, '-c', 'import sys, json; sys.path.insert(0, sys.argv[1]); '
                            'import boundary_validator as BV; L = BV.Layers()\n' + body, str(k03_dir(app, root))],
                           input=json.dumps(pts), capture_output=True, text=True, timeout=600)
        got = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {}
        bad = [f'{c}/{i}' for c, v in got.items() for i, sd in v.items()
               if [ev['cities'][c]['place_district'][i]['status'], ev['cities'][c]['place_district'][i].get('district')] != sd]
        n = sum(len(v) for v in pts.values())
        rec('I0', 'place_district-vs-used-module', 'PASS' if r.returncode == 0 and not bad and len(got) == len(pts) else 'FAIL',
            f'{n} мест data.js пересчитаны модулем inputs/{root}: расхождений {len(bad)}', mismatches=bad[:10])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- I3: правило в коде = правило в метаданных ----------------

def i3(app_root, repo_sha, root):
    app = app_root
    body = ('print(json.dumps({"rule": BV.assign(L, 71.43, 51.128)["rule"], "fx": {k: [BV.assign(L, x, y)["status"], '
            'BV.assign(L, x, y).get("district")] for k, x, y in ' + repr([(f[0], f[2], f[3]) for f in FIXTURES]) + '}}))')
    rc, out, err = py_k03(app, root, body)
    if rc != 0:
        rec('I3', 'behaviour', 'FAIL', f'модуль inputs/{root} не выполняется: {err[-200:]}')
        return
    fails = [f[0] for f in FIXTURES if out['fx'][f[0]] != [f[4], f[5]]]
    behaviour = 'v1' if all(out['fx'][k] == v for k, v in V1_FINGERPRINT.items()) else ('v2' if not fails else 'unknown')
    rec('I3', 'fixtures-v2-contract', 'PASS' if not fails else 'FAIL',
        f'5 ключевых фикстур модулем inputs/{root}: несоответствий {len(fails)} {fails}; поведение {behaviour}',
        results=out['fx'])
    ev = parse_js(app / 'web/evidence.js')
    k03_obs = [o for c in ev['cities'].values() for o in c['observations']
               if 'k03' in ((o.get('source') or {}).get('path') or '') and 'boundary_validator' in o['source']['path']]
    labels = {
        'assign()["rule"] (код)': out['rule'],
        'evidence.assign_rule': ev.get('assign_rule'),
        **{f'obs.method.id ({len(k03_obs)} набл.)': sorted({o['method']['id'] for o in k03_obs})},
        **{'obs.source.source_id': sorted({o['source']['source_id'] for o in k03_obs})},
    }
    want = out['rule']
    ui_ok = (ev.get('assign_rule') == want and labels[f'obs.method.id ({len(k03_obs)} набл.)'] == [want]
             and all(want in s for s in labels['obs.source.source_id']) and behaviour == want.rsplit('_', 1)[-1] and k03_obs)
    src_sha = sorted({o['source']['sha256'] for o in k03_obs})
    real_sha = sha((k03_dir(app, root) / 'boundary_validator.py').read_bytes())
    rec('I3', 'code-vs-evidence-and-ui', 'PASS' if ui_ok and src_sha == [real_sha] else 'FAIL',
        f'поведение={behaviour}; ' + '; '.join(f'{k}={v}' for k, v in labels.items())
        + f'; source.sha256 наблюдений = sha256 модуля: {src_sha == [real_sha]}', labels=labels)
    kd = k03_dir(app, root)
    meta = {}
    mf = app / 'inputs' / root / 'MANIFEST_K03V2.json'
    if mf.exists():
        meta[f'inputs/{root}/MANIFEST_K03V2.json:rule'] = json.loads(mf.read_text(encoding='utf-8')).get('rule')
    meta[f'inputs/{root}/…/boundary_registry.json:assignment_rule.id'] = json.loads(
        (kd / 'boundary_registry.json').read_text(encoding='utf-8'))['assignment_rule']['id']
    st = json.loads((kd / 'validator_selftest.json').read_text(encoding='utf-8'))
    meta[f'inputs/{root}/…/validator_selftest.json:rule'] = st.get('rule')
    bad = {k: v for k, v in meta.items() if v != want}
    rc_st, st_now, _ = py_k03(app, root, 'ok, c = BV.selftest(L); print(json.dumps({"ok": ok, "n": len(c)}))')
    rec('I3', 'code-vs-k03-metadata-files', 'PASS' if not bad else 'FAIL',
        (f'метаданные копии противоречат коду ({want}): {bad}' if bad else f'все метаданные копии = {want}')
        + f'; selftest кода сейчас: {st_now}, в validator_selftest.json: {len(st["cases"])} случаев',
        metadata=meta, selftest_now=st_now, selftest_json_cases=len(st['cases']),
        used_by_build='boundary_registry.json читается build_evidence.district_names() (только названия)')
    # Защита метки: код подменён на исходный v1 — check_all должен упасть до публикации устаревшей метки
    if root != 'k03_root' and (app / 'inputs/k03_root').exists():
        tmp, cp = layout(app_root, repo_sha)
        try:
            shutil.copy2(k03_dir(cp, 'k03_root') / 'boundary_validator.py', k03_dir(cp, root) / 'boundary_validator.py')
            rc2, failed2, summ2 = check_all(cp)
            rec('I3', 'label-guard-code-swap', 'PASS' if rc2 != 0 and any('K03' in f for f in failed2) else 'FAIL',
                f'код в inputs/{root} подменён исходным v1: check_all код {rc2}, упали {failed2}', check_all=summ2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------- I1: пустая зона AST-Z3 после синхронизации слоёв ----------------

def sync_layers(app, root):
    """Реальная синхронизация: в снимке OSM геометрия Алматы и Сарайшыка ← версия Overture из того же корня K03."""
    base = app / 'inputs' / root
    ov = json.loads((base / 'research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson').read_text(encoding='utf-8'))
    by = {}
    for x in ov['features']:
        rid = next((s['record_id'] for s in x['properties']['sources'] if s['dataset'] == 'OpenStreetMap'), '')
        by[int(rid.lstrip('r').split('@')[0])] = x['geometry']
    f = base / 'data/astana_districts.geojson'
    g = json.loads(f.read_text(encoding='utf-8'))
    for x in g['features']:
        if x['properties']['osm_id'] in (3482819, 19733918):
            x['geometry'] = by[x['properties']['osm_id']]
    f.write_text(json.dumps(g, ensure_ascii=False), encoding='utf-8')


def i1(app_root, repo_sha, root):
    tmp, app = layout(app_root, repo_sha)
    try:
        sync_layers(app, root)
        rc, out, err = py_k03(app, root, 'print(json.dumps({"zones_empty": {z: v["geom"].is_empty for z, v in L.zones.items()}, '
                                         '"assign": [BV.assign(L, 71.43, 51.128)["status"], BV.assign(L, 69.59, 42.32)["status"]]}))')
        tb = [l for l in err.splitlines() if 'boundary_validator.py' in l or 'Error' in l][-3:]
        rc_b, tail_b = run([sys.executable, 'tools/build_evidence.py'], app)
        crashed = rc != 0
        rec('I1', 'empty-AST-Z3-after-layer-sync', 'FAIL' if crashed or rc_b != 0 else 'PASS',
            (f'после синхронизации слоёв K03 assign() падает: {tb}' if crashed else
             f'зоны пусты: {out["zones_empty"]}; assign: {out["assign"]}') + f'; build_evidence код {rc_b}',
            traceback_tail=tb, build_evidence_returncode=rc_b, build_tail=tail_b[-300:],
            repro=('python3 research/round-6-results/K03/repro_d3.py --app-root <копия>' if crashed else None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- I2: устаревший place_district после изменения точки / слоя ----------------

def propagate_sha(app, changed, skip=('web/data.js', 'web/evidence.js', '.extract_manifest.json')):
    """Как сделала бы корректная выгрузка: заменить старые sha256 изменённых файлов во всех текстовых файлах копии
    (длина sha неизменна, поэтому размеры файлов-ссылок не меняются); повторять до неподвижной точки."""
    todo = dict(changed)
    touched = set()
    while todo:
        old, new = todo.popitem()
        for p in app.rglob('*'):
            rel = p.relative_to(app).as_posix()
            if not p.is_file() or rel in skip or p.suffix not in ('.json', '.md', '.geojson', '.js', '.py', '.txt'):
                continue
            b = p.read_bytes()
            if old.encode() in b:
                before = sha(b)
                p.write_bytes(b.replace(old.encode(), new.encode()))
                todo[before] = sha(p.read_bytes())
                touched.add(rel)
    return sorted(touched)


def move_place(app):
    """Синтетика: одно место Сарыарки получает координаты места Байконура (+1e-5°); длина записи сохраняется."""
    pf = app / 'inputs/k10/data/astana/places_social.geojson'
    ev = parse_js(app / 'web/evidence.js')['cities']['astana']['place_district']
    raw = pf.read_text(encoding='utf-8')
    g = json.loads(raw)
    sary = next(x for x in g['features'] if ev.get(x['id'], {}).get('district') == 'kz.astana.district.saryarka')
    baik = next(x for x in g['features'] if ev.get(x['id'], {}).get('district') == 'kz.astana.district.baikonur')
    old = json.dumps(sary['geometry'], ensure_ascii=False)
    if old not in raw:
        old = json.dumps(sary['geometry'], ensure_ascii=False, separators=(',', ':'))
    lon0, lat0 = sary['geometry']['coordinates'][:2]
    lon1, lat1 = baik['geometry']['coordinates'][:2]
    new = old.replace(repr(lon0), f'{lon1 + 1e-5:.{len(repr(lon0).split(".")[1])}f}', 1).replace(
        repr(lat0), f'{lat1 + 1e-5:.{len(repr(lat0).split(".")[1])}f}', 1)
    assert raw.count(old) == 1 and len(new) == len(old), 'координаты не найдены однозначно или длина изменилась'
    before = sha(pf.read_bytes())
    pf.write_text(raw.replace(old, new), encoding='utf-8')
    return sary['id'], before, sha(pf.read_bytes())


def shift_layer(app, root, dlat=0.003):
    """Синтетика: в снимке OSM копии K03 полигон Сарыарки сдвинут на dlat градусов к северу (~330 м)."""
    f = app / 'inputs' / root / 'data/astana_districts.geojson'
    g = json.loads(f.read_text(encoding='utf-8'))

    def mv(c):
        return [mv(x) for x in c] if isinstance(c[0], list) else [c[0], c[1] + dlat]
    for x in g['features']:
        if x['properties']['id'] == 'saryarka':
            x['geometry']['coordinates'] = mv(x['geometry']['coordinates'])
    f.write_text(json.dumps(g, ensure_ascii=False), encoding='utf-8')


def changed_places(before, after):
    return {f'{c}/{i}': [before['cities'][c]['place_district'][i]['district'] or before['cities'][c]['place_district'][i]['status'],
                         r['district'] or r['status']]
            for c in after['cities'] for i, r in after['cities'][c]['place_district'].items()
            if [r['status'], r.get('district')] != [before['cities'][c]['place_district'][i]['status'],
                                                   before['cities'][c]['place_district'][i].get('district')]}


def i2(app_root, repo_sha, root):
    for sid in ('point-moved', 'layer-changed', 'layer-touched-no-effect'):
        tmp, app = layout(app_root, repo_sha)
        try:
            before = parse_js(app / 'web/evidence.js')
            note = ''
            if sid == 'point-moved':
                pid, s0, s1 = move_place(app)
                touched = propagate_sha(app, {s0: s1})
                rc_d, tail_d = run([sys.executable, 'tools/build_data.py'], app)
                note = f'место {pid[:8]}… перенесено; sha обновлён в {len(touched)} файлах; build_data код {rc_d}'
            elif sid == 'layer-changed':
                shift_layer(app, root)
                note = f'полигон Сарыарки в inputs/{root}/data/astana_districts.geojson сдвинут на 0,003° (синтетика)'
            else:
                f = app / 'inputs' / root / 'data/astana_districts.geojson'
                f.write_bytes(f.read_bytes() + b'\n')
                note = f'в inputs/{root}/data/astana_districts.geojson добавлен перевод строки (данные не изменены)'
            rc, failed, summ = check_all(app)
            rc_b, tail_b = run([sys.executable, 'tools/build_evidence.py'], app)
            after = parse_js(app / 'web/evidence.js') if rc_b == 0 else None
            ch = changed_places(before, after) if after else None
            rc2, failed2, summ2 = check_all(app) if rc_b == 0 else (None, None, None)
            stale = bool(ch)
            detected = rc != 0 and any('evidence.js == rebuild' in f for f in failed)
            if sid == 'layer-touched-no-effect':
                inputs_flag = any(f.startswith('inputs') for f in failed)
                verdict = 'INFO'
                summary = (f'{note}: check_all до пересборки код {rc} {failed or ""}; изменение файла K03 v2 '
                           f'{"обнаружено" if inputs_flag else "НЕ обнаружено проверкой inputs (файлы корня, кроме boundary_validator.py, не сверяются с манифестом)"}; '
                           f'привязки не изменились ({len(ch or {})})')
            else:
                ev_ok_after = rc_b == 0 and not any('evidence.js == rebuild' in f for f in (failed2 or []))
                verdict = 'PASS' if (stale and detected and ev_ok_after) else 'FAIL'
                other_after = [f for f in (failed2 or []) if 'evidence.js == rebuild' not in f]
                summary = (f'{note}; до пересборки check_all код {rc}, упали {failed}; пересборка: изменились привязки '
                           f'{len(ch or {})}: {ch}; после пересборки evidence.js == rebuild '
                           f'{"проходит" if ev_ok_after else "НЕ проходит"}'
                           + (f'; ожидаемо зависимые проверки: {other_after} (эталон объяснений нужно пересоздать)' if other_after else ''))
            rec('I2', sid, verdict, summary, check_all_before=summ, failed_before=failed, rebuild_returncode=rc_b,
                changed=ch, check_all_after=summ2, failed_after=failed2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--repo-sha', help='SHA, из которого взять agent/ для раскладки (explain_ref.py импортирует agent)')
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    app = a.app_root.resolve()
    root = k03_root_name(app)
    print(f'K03 root used by build: inputs/{root}')
    i0(app, a.repo_sha, root)
    i3(app, a.repo_sha, root)
    i1(app, a.repo_sha, root)
    i2(app, a.repo_sha, root)
    summ = {v: sum(1 for r in OUT if r['verdict'] == v) for v in ('PASS', 'FAIL', 'SKIP', 'INFO')}
    print('SUMMARY', json.dumps(summ))
    if a.json:
        txt = json.dumps(dict(k03_root=f'inputs/{root}', summary=summ, results=OUT), ensure_ascii=False, indent=1)
        a.json.write_text(re.sub(r'/tmp/k03r6_[A-Za-z0-9_]+', '<tmp>', txt) + '\n', encoding='utf-8')
    return 1 if summ['FAIL'] else 0


if __name__ == '__main__':
    sys.exit(main())
