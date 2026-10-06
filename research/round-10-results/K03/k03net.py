"""K03 r10: общие помощники (stdlib): закреплённые входы из Git с проверкой blob, гаверсинус, канонический JSON, sha256.

Входы читаются только из коммитов (git show), не из рабочего дерева: донор d18847f (сырой K10-пакет Overture/OSM) и база
d2ff344 (web/govtech/core/data.js). Рабочее дерево этой ветки не содержит новых путей — это ожидаемо.
"""
import hashlib
import json
import math
import subprocess
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DONOR = 'd18847f9e7c18fcfae3349c0b223b023d359a838'
BASE = 'd2ff344c5ec9b9a729ea59df50ec81f981e619de'
CITIES = ('shymkent', 'astana')
R_EARTH = 6371008.8  # как haversine-mm-v1 в plan.js


def git(*a, binary=False):
    r = subprocess.run(['git', '-C', str(ROOT), *a], capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode('utf-8').strip()


def pinned(sha, path):
    """Байты файла из коммита + git blob + sha256 (blob проверяется повторным hash-object по байтам)."""
    blob = git('rev-parse', f'{sha}:{path}')
    data = git('show', f'{sha}:{path}', binary=True)
    check = hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()
    if check != blob:
        raise RuntimeError(f'blob mismatch {sha}:{path}')
    return data, {'commit': sha, 'path': path, 'git_blob': blob, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def parse_js(data):
    t = data.decode('utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def load_inputs():
    """Сырые сегменты/соединители донора и data.js базы; сверка sha256 файлов с data.js.cities[c].files."""
    djs, djs_meta = pinned(BASE, 'web/govtech/core/data.js')
    data = parse_js(djs)
    out = {'data_js': data, 'manifest': {'data_js': djs_meta, 'cities': {}}}
    for c in CITIES:
        man = {}
        for layer in ('segments', 'connectors'):
            raw, meta = pinned(DONOR, f'prototypes/city-evidence/inputs/k10/data/{c}/{layer}.geojson')
            want = data['cities'][c]['files'][layer]['sha256']
            meta['sha256_equals_data_js_files'] = meta['sha256'] == want
            if not meta['sha256_equals_data_js_files']:
                raise RuntimeError(f'{c}/{layer}: sha256 ≠ data.js files ({want})')
            out[(c, layer)] = json.loads(raw)
            man[layer] = meta
        out['manifest']['cities'][c] = man
    return out


def haversine_m(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = p2 - p1, math.radians(b[0] - a[0])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def js_round(x):
    """Math.round для x ≥ 0 (как в JS; floor(x+0.5) расходится только на 0.49999999999999994)."""
    f = math.floor(x)
    return int(f + 1 if x - f >= 0.5 else f)


def polyline_m(coords):
    return sum(haversine_m(coords[i - 1], coords[i]) for i in range(1, len(coords)))


# ---------- канонический JSON (как JSON.stringify с сортировкой ключей по UTF-16) ----------
def js_num(x):
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, int):
        return str(x)
    if x != x or x in (float('inf'), float('-inf')):
        return 'null'
    if x == 0:
        return '0'
    _, digits, exp = Decimal(repr(abs(x))).as_tuple()
    ds = ''.join(map(str, digits)).rstrip('0') or '0'
    exp += len(digits) - len(ds)
    k, n = len(ds), exp + len(ds)
    neg = '-' if x < 0 else ''
    if k <= n <= 21:
        return neg + ds + '0' * (n - k)
    if 0 < n <= 21:
        return neg + ds[:n] + '.' + ds[n:]
    if -6 < n <= 0:
        return neg + '0.' + '0' * (-n) + ds
    e = n - 1
    return neg + ds[0] + ('.' + ds[1:] if k > 1 else '') + 'e' + ('+' if e > 0 else '-') + str(abs(e))


def js_str(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == '\\':
            out.append('\\\\')
        elif ch in '\b\f\n\r\t':
            out.append({'\b': '\\b', '\f': '\\f', '\n': '\\n', '\r': '\\r', '\t': '\\t'}[ch])
        elif o < 0x20 or 0xD800 <= o <= 0xDFFF:
            out.append('\\u%04x' % o)
        else:
            out.append(ch)
    return ''.join(out) + '"'


def u16(s):
    return s.encode('utf-16-be')


def canon(v):
    if v is None:
        return 'null'
    if isinstance(v, (bool, int, float)):
        return js_num(v)
    if isinstance(v, str):
        return js_str(v)
    if isinstance(v, (list, tuple)):
        return '[' + ','.join(canon(x) for x in v) + ']'
    return '{' + ','.join(js_str(k) + ':' + canon(v[k]) for k in sorted(v, key=u16)) + '}'


def sha256_canon(v):
    return hashlib.sha256(canon(v).encode('utf-8')).hexdigest()


def dump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
