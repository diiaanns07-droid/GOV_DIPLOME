"""K03 r9: manifest проверенной сборки и входов (git blob + sha256), без копирования данных в Git.

  python3 research/round-9-results/K03/make_manifest.py --app-root <копия> --sha <SHA сборки>
Копия делается research/round-5-results/K03/extract_build.py (сверка blob при извлечении). Здесь — повторная сверка
git hash-object копии с blob коммита для использованных файлов, и blob входов K03 r8 на HEAD этой ветки.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
USED = ['web/plan.js', 'web/whatif.js', 'web/facts.js', 'web/plan-ui.js', 'web/app.js', 'web/index.html', 'web/data.js', 'web/evidence.js',
        'tests/plan.cjs', 'tools/plan_oracle.py', 'tools/build_evidence.py']
CODE = '3e1302aa583594b0bf674090ac9c2d49ac424dae'  # snapshots.json r9: build.code_candidate
R8 = ['geo_v2.js', 'geo_v2_ref.py', 'run_tests.py', 'node_runner.cjs', 'stage_checks.py',
      'fixtures/stage1.json', 'fixtures/stage2.json', 'fixtures/stage3.json']


def git(*a):
    return subprocess.run(['git', '-C', str(ROOT), *a], capture_output=True, text=True, check=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--sha', required=True)
    a = ap.parse_args()
    files, bad = {}, []
    present = set(git('ls-tree', '-r', '--name-only', a.sha, 'prototypes/city-evidence/').splitlines())
    for rel in USED + [r for r in ('web/resilience.js', 'web/resilience-ui.js', 'tests/resilience.cjs', 'tools/resilience_oracle.py')
                       if f'prototypes/city-evidence/{r}' in present]:
        p = a.app_root / rel
        blob = git('rev-parse', f'{a.sha}:prototypes/city-evidence/{rel}')
        have = git('hash-object', str(p))
        files[rel] = {'git_blob': blob, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
        if blob != have:
            bad.append(rel)
    r8 = {}
    for rel in R8:
        p = ROOT / 'research/round-8-results/K03' / rel
        r8[rel] = {'git_blob': git('hash-object', str(p)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
    doc = {'build': {'branch': 'claude/beautiful-clarke-sbzomj', 'sha': a.sha, 'prototype_tree': git('rev-parse', f'{a.sha}:prototypes/city-evidence'),
                     'code_candidate': CODE, 'same_tree_as_code_candidate': git('rev-parse', f'{a.sha}:prototypes/city-evidence') == git('rev-parse', f'{CODE}:prototypes/city-evidence'),
                     'path': 'prototypes/city-evidence/', 'files': files, 'blob_mismatch': bad},
           'k03_r8_inputs': {'branch': 'claude/epic-curie-iitc43', 'pinned_commit': '9b39f0f34f6086a20d8a6359352a9dfe30300d80',
                             'path': 'research/round-8-results/K03/', 'files': r8},
           'note': 'data.js/evidence.js в Git этой ветки не копируются: берутся из коммита сборки по blob; копия — временная.'}
    (HERE / 'inputs').mkdir(exist_ok=True)
    (HERE / f'inputs/BUILD_MANIFEST_{a.sha[:7]}.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('blob mismatch:', bad or 'нет')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
