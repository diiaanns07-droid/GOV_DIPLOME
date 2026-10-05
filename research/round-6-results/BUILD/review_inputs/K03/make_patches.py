"""K03 round 5: собрать patch-предложения (ничего не применяет к BUILD или round-3).

  python3 research/round-5-results/K03/make_patches.py
Пишет patches/k03_assign_v2_1.patch и patches/build_p1_binding.patch.

P2 (K03 v2.1) = round-4 v2 (inputs/fix_spec_v2.json) + защита от пустых зон (D3), относительно
research/round-3-results/K03/boundary_validator.py @ 44585de. Правило остаётся k03_assign_v2: там, где
v2 не падает, исход не меняется.
P1 (BUILD) = изменённые файлы proposal/p1/ относительно prototypes/city-evidence @ 0bf27de.
"""
import difflib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V1_SHA = '44585de31be01dd131ecb7677c462fc85b4d4cc4'
BUILD_SHA = '0bf27deb8549b325b34a9610402613d745544edb'
V1_REL = 'research/round-3-results/K03/boundary_validator.py'
APP_PREFIX = 'prototypes/city-evidence/'


def git_text(sha, path):
    return subprocess.check_output(['git', 'show', f'{sha}:{path}'], cwd=ROOT, stderr=subprocess.DEVNULL).decode('utf-8')


def apply(src, reps):
    for e in reps:
        n = src.count(e['old'])
        if n != e.get('count', 1):
            raise SystemExit(f"replacement: ожидалось {e.get('count', 1)}, найдено {n}: {e['old'][:70]!r}")
        src = src.replace(e['old'], e['new'])
    return src


def d3_replacements(v2_block):
    lines = v2_block.split('\n')
    head = lines.index('    # v2 регрессия: край города у AST-Z2, 0,5 м снаружи и внутри → ambiguous, а не unmatched')
    body = lines[head:]
    while body and body[-1] == '':
        body.pop()
    old = '\n'.join(body)
    new = '\n'.join(['    if not L.Pzones[\'AST-Z2\'].is_empty:  # v2.1 (D3): зоны может не быть в новой версии слоёв']
                    + ['    ' + x if x else x for x in body])
    return [
        dict(old="""    for z, zg in L.Pzones.items():
        if z.startswith('AST')""",
             new="""    for z, zg in L.Pzones.items():
        if zg.is_empty:
            continue  # v2.1 (D3): зона может исчезнуть в новой версии слоёв (например, AST-Z3 при их синхронизации)
        if z.startswith('AST')"""),
        dict(old="""        ('Baikonur exclave ∩ Tselinograd (AST-A12-F012)', 71.66574, 51.33028, 'ambiguous', None),
        ('uncovered city area (K10 E01)', *L.zones['AST-Z2']['geom'].representative_point().coords[0], 'unmatched', None),
        ('Almaty/Saraishyk version-difference sliver', *L.zones['AST-Z3']['geom'].representative_point().coords[0], 'ambiguous', None),""",
             new="""        # v2.1 (D3): случаи, зависящие от зон, — только если зона есть в текущих слоях
        *([('Baikonur exclave ∩ Tselinograd (AST-A12-F012)', 71.66574, 51.33028, 'ambiguous', None)]
          if not L.zones['AST-Z1']['geom'].is_empty else []),
        *([('uncovered city area (K10 E01)', *L.zones['AST-Z2']['geom'].representative_point().coords[0], 'unmatched', None)]
          if not L.zones['AST-Z2']['geom'].is_empty else []),
        *([('Almaty/Saraishyk version-difference sliver', *L.zones['AST-Z3']['geom'].representative_point().coords[0], 'ambiguous', None)]
          if not L.zones['AST-Z3']['geom'].is_empty else []),"""),
        dict(old=old, new=new),
        dict(old="""                  rep_point=[round(c, 6) for c in v['geom'].representative_point().coords[0]],""",
             new="""                  rep_point=([round(c, 6) for c in v['geom'].representative_point().coords[0]]
                             if not v['geom'].is_empty else None),"""),
    ]


def udiff(a, b, path, new_file=False):
    al = a.splitlines(keepends=True)
    bl = b.splitlines(keepends=True)
    return ''.join(difflib.unified_diff(al, bl, '/dev/null' if new_file else f'a/{path}', f'b/{path}'))


def main():
    (HERE / 'patches').mkdir(exist_ok=True)
    v1 = git_text(V1_SHA, V1_REL)
    spec = json.loads((HERE / 'inputs/fix_spec_v2.json').read_text(encoding='utf-8'))
    v2 = apply(v1, spec['replacements'])
    blk = next(r['new'] for r in spec['replacements'] if 'v2 регрессия' in r['new'])
    v21 = apply(v2, d3_replacements(blk))
    (HERE / 'patches/k03_assign_v2_1.patch').write_text(udiff(v1, v21, V1_REL), encoding='utf-8')
    p1 = []
    for f in sorted((HERE / 'proposal/p1').rglob('*')):
        if f.is_file():
            rel = APP_PREFIX + str(f.relative_to(HERE / 'proposal/p1'))
            try:
                old = git_text(BUILD_SHA, rel)
                new_file = False
            except subprocess.CalledProcessError:
                old, new_file = '', True
            p1.append(udiff(old, f.read_text(encoding='utf-8'), rel, new_file))
    (HERE / 'patches/build_p1_binding.patch').write_text(''.join(p1), encoding='utf-8')
    print('patches written:', [p.name for p in sorted((HERE / 'patches').glob('*.patch'))])


if __name__ == '__main__':
    main()
