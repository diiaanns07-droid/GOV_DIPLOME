"""Минимальный repro D3 на сборке: пустая зона AST-Z3 → K03 assign() падает.

  python3 research/round-6-results/K03/repro_d3.py --app-root <копия prototypes/city-evidence>
Копирует только inputs/<K03 root> во временный каталог, синхронизирует слои (снимок OSM ← геометрия Алматы и
Сарайшыка из Overture того же корня — реальные данные пакета) и вызывает assign() для одной точки Астаны.
Код выхода 1 и трассировка = дефект воспроизведён; 0 = не воспроизводится.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    a = ap.parse_args()
    app = a.app_root.resolve()
    m = re.search(r'K03_DIR\s*=\s*APP\s*/\s*"inputs"\s*/\s*"([^"]+)"', (app / 'tools/build_evidence.py').read_text(encoding='utf-8'))
    root = m.group(1) if m else 'k03_root'
    tmp = Path(tempfile.mkdtemp(prefix='k03r6_d3_'))
    try:
        base = tmp / root
        shutil.copytree(app / 'inputs' / root, base, ignore=shutil.ignore_patterns('__pycache__'))
        ov = json.loads((base / 'research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson').read_text(encoding='utf-8'))
        geo = {int(next(s['record_id'] for s in x['properties']['sources'] if s['dataset'] == 'OpenStreetMap')
                   .lstrip('r').split('@')[0]): x['geometry'] for x in ov['features']}
        f = base / 'data/astana_districts.geojson'
        g = json.loads(f.read_text(encoding='utf-8'))
        for x in g['features']:
            if x['properties']['osm_id'] in (3482819, 19733918):  # Алматы, Сарайшык
                x['geometry'] = geo[x['properties']['osm_id']]
        f.write_text(json.dumps(g, ensure_ascii=False), encoding='utf-8')
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import boundary_validator as BV; L = BV.Layers(); '
                'print("AST-Z3 empty:", L.zones["AST-Z3"]["geom"].is_empty); print(BV.assign(L, 71.43, 51.128)["status"])')
        r = subprocess.run([sys.executable, '-c', code, str(base / 'research/round-3-results/K03')],
                           capture_output=True, text=True)
        print(f'K03 root: inputs/{root}')
        print(r.stdout.strip())
        print(r.stderr.strip()[-700:].replace(str(tmp), '<tmp>'))
        return 1 if r.returncode else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
