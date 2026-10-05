"""Извлечь prototypes/city-evidence из коммита BUILD побайтно (для --app-root).

  python3 research/round-5-results/K03/extract_build.py --sha 0bf27deb8549b325b34a9610402613d745544edb --out /tmp/app
Сначала: git fetch origin claude/beautiful-clarke-sbzomj. Пишет только в --out.
Каждый файл: git show <sha>:<path> → Path.write_bytes; git hash-object копии сверяется с blob.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PREFIX = 'prototypes/city-evidence/'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sha', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--prefix', default=PREFIX)
    a = ap.parse_args()
    out = Path(a.out)
    listing = subprocess.check_output(['git', 'ls-tree', '-r', '-z', a.sha, '--', a.prefix], cwd=ROOT)
    files = []
    for entry in listing.split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        _, typ, blob = meta.split()
        if typ != b'blob':
            continue
        p = path.decode()
        data = subprocess.check_output(['git', 'show', f'{a.sha}:{p}'], cwd=ROOT)
        dst = out / p[len(a.prefix):]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        local = subprocess.check_output(['git', 'hash-object', str(dst)], cwd=ROOT, text=True).strip()
        if local != blob.decode():
            raise SystemExit(f'blob mismatch: {p}')
        files.append(dict(path=p, git_blob=blob.decode(), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
    (out / '.extract_manifest.json').write_text(json.dumps(dict(sha=a.sha, prefix=a.prefix, files=files),
                                                           indent=1) + '\n', encoding='utf-8')
    print(f'extracted {len(files)} files from {a.sha[:12]} to {out}')


if __name__ == '__main__':
    main()
