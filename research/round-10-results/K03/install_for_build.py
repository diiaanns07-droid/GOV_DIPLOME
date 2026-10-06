"""K03 r10: установка модуля маршрутов в КОПИЮ/рабочее дерево BUILD (запускает BUILD; общий код K03 из своей ветки не меняет).

  python3 research/round-10-results/K03/install_for_build.py --target <корень дерева BUILD>

Копирует в <target>/web/govtech/k03/: routing.js, school-access-routing.js, shymkent.graph.json, astana.graph.json и пишет
K03_MANIFEST.json (sha256 каждого файла, graph_sha256, policy_sha256, ODbL, коммит-источник). Затем BUILD применяет
patches/build_d2ff344_k03_routing_assets.patch (белый список ui/web_server.py, теги <script> в web/index.html, тест хэшей).
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {'routing.js': HERE / 'routing.js', 'school-access-routing.js': HERE / 'school-access-routing.js',
         'shymkent.graph.json': HERE / 'graph/shymkent.graph.json', 'astana.graph.json': HERE / 'graph/astana.graph.json'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--target', type=Path, required=True)
    a = ap.parse_args()
    dst = a.target / 'web/govtech/k03'
    dst.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(['git', '-C', str(HERE), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip() or None
    files = []
    for name, src in FILES.items():
        shutil.copyfile(src, dst / name)
        files.append({'file': name, 'sha256': hashlib.sha256((dst / name).read_bytes()).hexdigest(),
                      'source': 'research/round-10-results/K03/' + str(src.relative_to(HERE))})
    graphs = {c: json.loads((dst / f'{c}.graph.json').read_text(encoding='utf-8')) for c in ('shymkent', 'astana')}
    man = {'source_branch': 'claude/epic-curie-iitc43', 'source_commit_at_install': head, 'files': files,
           'graphs': {c: {'graph_sha256': g['graph_sha256'], 'policy_sha256': g['policy_sha256'], 'release': g['release'], 'license': g['license']['id']}
                      for c, g in graphs.items()},
           'note': 'Модуль K03 pedestrian-v1. Граф — производная база OSM (ODbL-1.0, © OpenStreetMap contributors, Overture Maps Foundation).'}
    (dst / 'K03_MANIFEST.json').write_text(json.dumps(man, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('installed', [f['file'] for f in files], '→', dst)


if __name__ == '__main__':
    main()
