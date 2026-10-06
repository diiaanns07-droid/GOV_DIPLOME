"""K03 r10: отрицательный контроль — намеренно испорченные КОПИИ routing.js должны давать FAIL в нужных проверках run_tests.py.

  python3 research/round-10-results/K03/negative_controls.py --work <временный каталог> [--log runs/negative_controls.json]

Каждая порча — одна текстовая замена; если замена не найдена однозначно, контроль NOT_RUN, а не PASS. Исходный routing.js не меняется.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUTANTS = [
    ('ignore-direction', 'if (e[k][1] === "ok") { out[k].get(e.to)', 'if (e[k][1] === "ok" || e[k][0] === "ok") { out[k].get(e.to)',
     'одностороннее ограничение игнорируется', ['R-hand-js', 'R-direction']),
    ('silent-geodesic', 'return open2 ? { ...r, status: "outside_coverage", reason: "path_may_exist_outside_slice" } : { ...r, status: "disconnected", reason: "no_path_in_closed_component" };',
     'return { ...r, status: "ok", distance_mm: mm(haversine(po, pt)), geometry: { type: "LineString", coordinates: [po, pt] } };',
     'при отсутствии пути молча подставляется прямая', ['R-hand-js']),
    ('no-max-snap', 'const okSnap = (s) => s && s.d <= maxSnap;', 'const okSnap = (s) => !!s;', 'допуск привязки 100 м не проверяется', ['R-hand-js']),
    ('strict-uses-exploratory', '"pedestrian-v1-strict": "s"', '"pedestrian-v1-strict": "x"', 'strict использует рёбра с неизвестным доступом',
     ['R-hand-js', 'R-city-js']),
    ('no-boundary-check', 'if (lb !== null && lb < net) assumptions.add("boundary_unverified");', '',
     'не отмечается, что более короткий путь вне среза не исключён', ['R-hand-js', 'R-city-js']),
    ('unknown-as-disconnected', 'return { ...r, status: "access_unknown", reason: "path_only_via_unverified_edges" }',
     'return { ...r, status: "disconnected", reason: "no_path_in_closed_component" }', 'неизвестный доступ выдаётся за отсутствие пути',
     ['R-hand-js', 'R-city-js']),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--log', type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    src = (HERE / 'routing.js').read_text(encoding='utf-8')
    out, bad = [], 0
    for name, old, new, why, must in MUTANTS:
        if src.count(old) != 1:
            out.append(dict(mutant=name, verdict='NOT_RUN', why=f'замена найдена {src.count(old)} раз'))
            print(f'[NOT_RUN] {name}')
            continue
        f = a.work / f'routing_{name}.js'
        f.write_text(src.replace(old, new), encoding='utf-8')
        js = a.work / f'{name}.json'
        subprocess.run([sys.executable, str(HERE / 'run_tests.py'), '--js', str(f), '--json', str(js)], capture_output=True, text=True, timeout=1800)
        res = json.loads(js.read_text(encoding='utf-8'))
        failed = sorted(r['check'] for r in res['results'] if r['verdict'] == 'FAIL')
        caught = all(m in failed for m in must)
        bad += not caught
        out.append(dict(mutant=name, why=why, expected_fail=must, failed=failed, verdict='PASS' if caught else 'FAIL'))
        print(f'[{"PASS" if caught else "FAIL"}] {name}: FAIL в {failed} (ожидались {must})')
    if a.log:
        a.log.write_text(json.dumps({'controls': out}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
