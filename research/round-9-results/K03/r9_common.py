"""K03 r9: общие помощники этапов 1–3 (запись вердиктов, чтение сборки, вызов адаптера plan.js, независимый оракул r8)."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
R8 = HERE.parent.parent / 'round-8-results' / 'K03'
sys.path.insert(0, str(R8))
import geo_v2_ref as R  # noqa: E402,F401  (независимый Python-оракул K03 r8: гаверсинус, мм, ничьи, QA)

OUT = []
WEB_FILES = ('plan.js', 'whatif.js', 'facts.js', 'plan-ui.js', 'app.js', 'index.html', 'data.js', 'evidence.js')


def rec(check, verdict, summary, **d):
    OUT.append(dict(check=check, verdict=verdict, summary=summary, details=d))
    print(f'[{verdict}] {check}: {summary}')


def parse_js(p):
    t = Path(p).read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_hashes(app):
    return {f: sha256_file(app / 'web' / f) for f in WEB_FILES if (app / 'web' / f).exists()}


def u16(s):
    return s.encode('utf-16-be')  # JS сравнивает строки по UTF-16 code units


def run_adapter(app, cases, timeout=600):
    """Запуск plan_adapter.cjs на копии сборки. Возвращает (results_by_id, integrity) или (None, причина)."""
    node = shutil.which('node')
    if not node:
        return None, 'node не установлен'
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as fh:
        json.dump({'app_root': str(app), 'cases': cases}, fh, ensure_ascii=False)
        req = fh.name
    try:
        r = subprocess.run([node, str(HERE / 'plan_adapter.cjs'), req], capture_output=True, text=True, timeout=timeout)
    finally:
        Path(req).unlink()
    if r.returncode:
        return None, f'node код {r.returncode}: {r.stderr[-400:]}'
    doc = json.loads(r.stdout)
    return {x['id']: x for x in doc['results']}, doc['integrity']


def plan_snapshot(data, city):
    """Независимый пересчёт source_snapshot по формуле web/plan.js (city-plan-v2): без bbox, в отличие от geo_v2 r8."""
    c = data['cities'][city]
    pf = ((c.get('files') or {}).get('places_social') or {}).get('sha256')
    rows = sorted(([p['id'], R.round7(p['lon']), R.round7(p['lat'])] for p in c['places']), key=lambda r: u16(r[0]))
    digest = R.sha_hex(R.js_stringify(rows))
    return 'sha256:' + R.sha_hex(R.js_stringify(['city-plan-v2', city, c.get('release'), pf, digest, 'haversine-mm-v1']))


def summary_and_save(path):
    summ = {v: sum(1 for r in OUT if r['verdict'] == v) for v in ('PASS', 'FAIL', 'SKIP', 'NOT_RUN', 'TEST_INCOMPATIBLE', 'INFO')}
    print('SUMMARY', json.dumps(summ))
    if path:
        Path(path).write_text(json.dumps(dict(summary=summ, results=OUT), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 1 if summ['FAIL'] or summ['TEST_INCOMPATIBLE'] else 0
