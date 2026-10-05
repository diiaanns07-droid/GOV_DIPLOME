"""K03 round 5: проверить предложения P1 + P2 во ВРЕМЕННОЙ копии BUILD (BUILD не меняется, FIXED не заявляется).

  python3 research/round-5-results/K03/verify_proposal.py --app-root <извлечённая копия 0bf27de> [--json out.json]
Шаги в tmp-копии: git apply P2 (K03 v2.1) в inputs/k03_root, git apply -p3 P1 (BUILD) → source_manifest
обновляется, как сделал бы copy_inputs.py из нового коммита K03 → путь сборки build_data → build_evidence →
explain_ref → тесты приложения (unittest, node conformance) → check_evidence_fresh → test_boundaries_demo.py.
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
BUILD_SHA = '0bf27deb8549b325b34a9610402613d745544edb'
P1 = HERE / 'patches/build_p1_binding.patch'
P2 = HERE / 'patches/k03_assign_v2_1.patch'


def run(cmd, cwd, timeout=900):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return dict(cmd=' '.join(map(str, cmd)), returncode=r.returncode, tail=(r.stdout + r.stderr).strip()[-700:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix='k03r5_prop_'))
    steps = {}
    try:
        # раскладка как в репозитории: tools/explain_ref.py импортирует agent/ из корня (APP.parents[1])
        app = tmp / 'prototypes' / 'city-evidence'
        shutil.copytree(a.app_root.resolve(), app)
        try:
            ls = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BUILD_SHA, '--', 'agent/'], cwd=ROOT, text=True)
            for rel in ls.split():
                dst = tmp / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(subprocess.check_output(['git', 'show', f'{BUILD_SHA}:{rel}'], cwd=ROOT))
            steps['agent_from_build_sha'] = dict(cmd=f'git show {BUILD_SHA[:12]}:agent/*', returncode=0, tail=f'{len(ls.split())} files')
        except subprocess.CalledProcessError as e:
            steps['agent_from_build_sha'] = dict(cmd='git ls-tree agent/', returncode=1, tail=str(e))
        expl_before = (app / 'tests/expected_explanations.json').read_bytes()
        steps['apply_p2'] = run(['git', 'apply', '--directory=inputs/k03_root', str(P2)], app)
        steps['apply_p1'] = run(['git', 'apply', '-p3', str(P1)], app)
        mp = app / 'source_manifest.json'
        m = json.loads(mp.read_text(encoding='utf-8'))
        rel = 'inputs/k03_root/research/round-3-results/K03/boundary_validator.py'
        for f in m['files']:
            if f['copied_to'] == rel:
                b = (app / rel).read_bytes()
                f.update(sha256=hashlib.sha256(b).hexdigest(), bytes=len(b), sha='proposal: patches/k03_assign_v2_1.patch')
        mp.write_text(json.dumps(m, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        for name, cmd in [('build_data', [sys.executable, 'tools/build_data.py']),
                          ('build_evidence', [sys.executable, 'tools/build_evidence.py']),
                          ('explain_ref', [sys.executable, 'tools/explain_ref.py']),
                          ('app_unittest', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests']),
                          ('app_conformance_node', ['node', 'tests/conformance.cjs']),
                          ('check_evidence_fresh', [sys.executable, 'tools/check_evidence_fresh.py'])]:
            steps[name] = run(cmd, app)
        steps['expected_explanations_unchanged'] = dict(
            cmd='cmp tests/expected_explanations.json (до/после explain_ref)',
            returncode=0 if (app / 'tests/expected_explanations.json').read_bytes() == expl_before else 1, tail='')
        out_json = tmp / 'k03r5_patched.json'
        steps['k03_test'] = run([sys.executable, str(HERE / 'test_boundaries_demo.py'), '--app-root', str(app),
                                 '--json', str(out_json)], HERE)
        test = json.loads(out_json.read_text(encoding='utf-8')) if out_json.exists() else None
        if test:
            test['app_root'] = '<tmp copy of 0bf27de + P2 (k03_assign_v2_1.patch) + P1 (build_p1_binding.patch), rebuilt>'
            txt = json.dumps(test, ensure_ascii=False).replace(str(app), '<app-root>')
            test = json.loads(txt)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res = dict(note='Проверка предложения во временной копии. BUILD 0bf27de не изменён; статус FIXED не заявляется.',
               build_under_test='claude/beautiful-clarke-sbzomj@0bf27deb8549b325b34a9610402613d745544edb',
               patches={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (P1, P2)},
               steps={k: dict(v, tail=v['tail'].replace(str(tmp), '<tmp>')) for k, v in steps.items()},
               k03_test_summary=test and test['summary'], k03_test=test)
    for k, v in steps.items():
        print(f"{k:22} rc={v['returncode']}  {v['tail'].splitlines()[-1] if v['tail'] else ''}")
    print('k03 test summary:', test and test['summary'])
    if a.json:
        txt = re.sub(r'/tmp/k03r5_[a-z]+_[A-Za-z0-9_]+', '<tmp>', json.dumps(res, ensure_ascii=False, indent=1))
        a.json.write_text(txt + '\n', encoding='utf-8')
    ok = all(v['returncode'] == 0 for v in steps.values())
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
