"""K03 r9: отрицательный контроль — намеренно испорченные КОПИИ сборки должны давать FAIL в нужных проверках.

  python3 research/round-9-results/K03/negative_controls.py --app-root <копия сборки> --work <временный каталог> --stage 1 [--log out.json]

Копия сборки создаётся в --work, исходная копия и prototypes/city-evidence не меняются. Каждая порча — одна текстовая замена;
если замена не нашлась (код сборки изменился), контроль = NOT_RUN, а не PASS.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

MUTANTS = {
    1: [
        ('tie-larger-id', 'web/plan.js', '(mm === best.mm && s.id < best.id)', '(mm === best.mm && s.id > best.id)',
         'в ничьей исходных записей выбирается больший ID', ['S1-real-sources', 'S1-nearest-fixtures']),
        ('dedup-same-coords', 'web/plan.js',
         'const places = c.places.filter((p) => CATEGORIES[p.group])',
         'const places = c.places.filter((p, i, a) => CATEGORIES[p.group] && a.findIndex((q) => q.group === p.group && q.lon === p.lon && q.lat === p.lat) === i)',
         'записи категории в одних координатах сливаются в одну («совпадение = дубликат»)', ['S1-context', 'S1-coincident-not-duplicate']),
        ('hypothetical-wins-tie', 'web/plan.js',
         '(d.mm === best.mm && best.kind === "hypothetical" && c.id < best.id)', '(d.mm === best.mm && (best.kind === "source" || c.id < best.id))',
         'кандидат поверх записи вытесняет исходную запись в ничьей', ['S1-real-sources', 'S1-nearest-fixtures']),
        ('colocated-text-duplicate', 'web/facts.js', 'точное место не проверено', 'вероятно дубликат',
         'текст QA называет совпадение координат дубликатом', ['S1-coincident-not-duplicate']),
        ('bbox-exclusive', 'web/whatif.js', 'bb[0] <= lon && lon <= bb[2]', 'bb[0] < lon && lon < bb[2]',
         'границы bbox исключены', ['S1-validate']),
    ],
    # этап 2: порча КОПИИ модуля resilience_cases.js (прогон с --js), сборка не меняется
    2: [
        ('ids-unsorted', 'module:resilience_cases.js', 'return ids.slice().sort(cmpStr);', 'return ids.slice();',
         'ID исключений не канонизируются (зависят от порядка ввода)', ['S2-js', 'S2-js-python-parity']),
        ('dedupe-silently', 'module:resilience_cases.js', 'if (seen.has(id)) fail("duplicate_source_id", `${path}[${k}]`, id);', '',
         'повтор ID молча принимается', ['S2-js']),
        ('candidate-accepted', 'module:resilience_cases.js',
         'if (candidateIds && candidateIds.has(id)) fail("candidate_not_source", path, `${id}: ID кандидата, а не исходной записи`);',
         'if (candidateIds && candidateIds.has(id)) return id;', 'ID кандидата принимается вместо исходной записи', ['S2-js']),
        ('colocated-all-categories', 'module:resilience_cases.js', 'make(cat, grp.ids_in_category, "colocated"',
         'make(cat, grp.ids_in_category.concat(grp.ids_other_categories), "colocated"',
         'QA-группа исключает записи других категорий', ['S2-js']),
        ('label-utf16-length', 'module:resilience_cases.js', 'if ([...v].length > LIMITS.label)', 'if (v.length > LIMITS.label)',
         'длина подписи в UTF-16, а не в code points', ['S2-js']),
        ('auto-first-group', 'module:resilience_cases.js',
         'if (!Number.isInteger(groupIndex) || groupIndex < 0',
         'if (groupIndex === undefined || groupIndex === null) groupIndex = 0;\n    if (!Number.isInteger(groupIndex) || groupIndex < 0',
         'без явного индекса берётся первая QA-группа (автоисключение)', ['S2-js', 'S2-no-auto-exclusion']),
        ('digest-order', 'module:resilience_cases.js', '.sort((a, b) => cmpStr(a[0], b[0]));\n    return "sha256:"',
         ';\n    return "sha256:"', 'digest зависит от порядка случаев', ['S2-digest-invariance']),
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--work', type=Path, required=True)
    ap.add_argument('--stage', type=int, default=1)
    ap.add_argument('--target-sha', default='d865dd4a124291e10dd0b7bb1d9eada20d34c268')
    ap.add_argument('--log', type=Path)
    a = ap.parse_args()
    runner = HERE / f'run_stage{a.stage}.py'
    out, bad = [], 0
    for name, rel, old, new, why, must_fail in MUTANTS[a.stage]:
        dst = a.work / f'neg_{name}'
        if dst.exists():
            shutil.rmtree(dst)
        module = rel.startswith('module:')
        if module:
            dst.mkdir(parents=True)
            f = dst / rel.split(':', 1)[1]
            shutil.copy(HERE / f.name, f)
        else:
            shutil.copytree(a.app_root, dst)
            f = dst / rel
        t = f.read_text(encoding='utf-8')
        if t.count(old) != 1:
            out.append(dict(mutant=name, verdict='NOT_RUN', why=f'замена не найдена однозначно в {rel} ({t.count(old)})'))
            print(f'[NOT_RUN] {name}')
            continue
        f.write_text(t.replace(old, new), encoding='utf-8')
        js = dst / 'r.json'
        cmd = [sys.executable, str(runner), '--app-root', str(a.app_root if module else dst), '--json', str(js),
               '--target-sha', a.target_sha if module else a.target_sha + '+' + name] + (['--js', str(f)] if module else [])
        subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        res = json.loads(js.read_text(encoding='utf-8'))
        failed = sorted(r['check'] for r in res['results'] if r['verdict'] == 'FAIL')
        caught = all(any(f == m or f.startswith(m) for f in failed) for m in must_fail)
        bad += not caught
        out.append(dict(mutant=name, file=rel, why=why, expected_fail=must_fail, failed=failed, summary=res['summary'],
                        verdict='PASS' if caught else 'FAIL'))
        print(f'[{"PASS" if caught else "FAIL"}] {name}: FAIL в {failed} (ожидались {must_fail})')
        shutil.rmtree(dst)
    if a.log:
        a.log.write_text(json.dumps(dict(stage=a.stage, base=a.target_sha, controls=out), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
