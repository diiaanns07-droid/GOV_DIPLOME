"""K03 round 7: собрать fixtures.json для point_check (контрольные точки и проектный объект city-whatif-v1).

  python3 research/round-7-results/K03/make_fixtures.py --app-root <копия prototypes/city-evidence> --target-sha <SHA>

bbox и edges_inclusive берутся из web/evidence.js (cities.<city>.spatial_unit) и сверяются с web/data.js.
Ожидаемый исход каждой точки задан правилом point_check (по построению), а не результатом его запуска.
K03 assign() используемой сборкой копии (K03_ROOT в tools/build_evidence.py) даёт только справку k03_info:
район не условие приёма точки и не официальная принадлежность. Нужны shapely и pyproj для k03_info.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPECIAL = {'NaN': float('nan'), 'Infinity': float('inf'), '-Infinity': float('-inf')}


def parse_js(p):
    t = Path(p).read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rstrip().rindex(';')])


def k03_root(app):
    src = (app / 'tools/build_evidence.py').read_text(encoding='utf-8')
    m = re.search(r'K03_ROOT\s*=\s*APP\s*/\s*"inputs"\s*/\s*"([^"]+)"', src) or \
        re.search(r'K03_DIR\s*=\s*APP\s*/\s*"inputs"\s*/\s*"([^"]+)"', src)
    return m.group(1)


def slices(app):
    ev, data = parse_js(app / 'web/evidence.js'), parse_js(app / 'web/data.js')
    out = {}
    for c, cd in ev['cities'].items():
        su = cd['spatial_unit']
        if su['bbox'] != data['cities'][c]['bbox']:
            raise SystemExit(f'{c}: bbox evidence.js {su["bbox"]} != data.js {data["cities"][c]["bbox"]}')
        out[c] = dict(city_id=c, bbox=su['bbox'], edges_inclusive=su['edges_inclusive'], type=su['type'],
                      geometry_sha256=su.get('geometry_sha256'))
    return out


def k03_points(app, root, pts):
    """K03 assign() в отдельном процессе; также точки на общей границе районов внутри bbox."""
    code = r'''
import sys, json
sys.path.insert(0, sys.argv[1])
import boundary_validator as BV, geo_common as gc
from shapely.geometry import box, Point
from pyproj import Transformer
L = BV.Layers()
req = json.loads(sys.stdin.read())
out = {"assign": {}, "borders": {}}
for k, (lon, lat) in req["points"].items():
    r = BV.assign(L, lon, lat)
    out["assign"][k] = {"status": r["status"], "district": r.get("district"), "reason": r.get("reason"),
                        "candidates": r.get("candidates"), "rule": r.get("rule")}
to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32642", always_xy=True).transform
to_ll = Transformer.from_crs("EPSG:32642", "EPSG:4326", always_xy=True).transform
from shapely.ops import transform, linemerge
for city, (a, b, bb) in req["borders"].items():
    lay = L.ast_prod if city == "astana" else L.shy
    A, B = transform(to_utm, lay[a]), transform(to_utm, lay[b])
    line = A.boundary.intersection(B.boundary).intersection(transform(to_utm, box(*bb)))
    line = linemerge(line) if line.geom_type == "MultiLineString" else line
    seg = max(getattr(line, "geoms", [line]), key=lambda q: q.length)
    s = seg.length / 2
    p, q1, q2 = seg.interpolate(s), seg.interpolate(s - 0.5), seg.interpolate(s + 0.5)
    nx, ny = -(q2.y - q1.y), q2.x - q1.x
    n = (nx * nx + ny * ny) ** 0.5
    nx, ny = nx / n, ny / n
    if not A.contains(Point(p.x + nx * 2, p.y + ny * 2)):
        nx, ny = -nx, -ny
    pts = {}
    for d in (0.0, 0.5, 5.0):
        pts[str(d)] = list(to_ll(p.x + nx * d, p.y + ny * d))
    out["borders"][city] = {"a": a, "b": b, "points": pts, "shared_in_bbox_m": round(seg.length, 1)}
print(json.dumps(out))
'''
    r = subprocess.run([sys.executable, '-c', code, str(app / 'inputs' / root / 'research/round-3-results/K03')],
                       input=json.dumps(pts), capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise SystemExit('K03: ' + r.stderr[-800:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-root', type=Path, required=True)
    ap.add_argument('--target-sha', required=True)
    ap.add_argument('--out', type=Path, default=HERE / 'fixtures.json')
    a = ap.parse_args()
    app = a.app_root.resolve()
    S = slices(app)
    root = k03_root(app)
    A, Sh = S['astana'], S['shymkent']
    F = []

    def add(fid, city, kind, point, code, why, raw=None, slice_override=None, k03=None):
        F.append(dict(id=fid, city=city, kind=kind, point=point, raw_json=raw, slice_override=slice_override,
                      expected=dict(ok=code in ('inside', 'on_edge'), code=code), why=why, k03_ref=k03))

    for c, s in S.items():
        W, So, E, N = s['bbox']
        cx, cy = (W + E) / 2, (So + N) / 2
        other = Sh if c == 'astana' else A
        ox, oy = (other['bbox'][0] + other['bbox'][2]) / 2, (other['bbox'][1] + other['bbox'][3]) / 2
        p = c[:3].upper()
        add(f'{p}-center', c, 'control', [cx, cy], 'inside', 'центр квадрата', k03='center')
        add(f'{p}-corner-SW', c, 'control', [W, So], 'on_edge', 'угол квадрата W,S: границы включены (edges_inclusive=true)')
        add(f'{p}-corner-NE', c, 'proposed', [E, N], 'on_edge', 'угол квадрата E,N, проектный объект')
        add(f'{p}-edge-W', c, 'control', [W, cy], 'on_edge', 'середина западной стороны')
        add(f'{p}-just-out-W', c, 'control', [W - 1e-9, cy], 'outside_bbox', 'на 1e-9° западнее (~0,1 мм): допуска нет, точка вне')
        add(f'{p}-just-in-W', c, 'control', [W + 1e-9, cy], 'inside', 'на 1e-9° восточнее западной стороны')
        add(f'{p}-swap', c, 'control', [cy, cx], 'lon_lat_swapped', 'центр квадрата с порядком [широта, долгота]')
        add(f'{p}-other-city', c, 'control', [ox, oy], 'other_city', 'центр квадрата другого города: не переносится')
        add(f'{p}-far', c, 'proposed', [70.0, 45.0], 'outside_bbox', 'точка в Казахстане вне обоих квадратов')
        add(f'{p}-edges-exclusive', c, 'control', [W, cy], 'outside_bbox', 'та же точка на стороне, но срез с edges_inclusive=false',
            slice_override=dict(edges_inclusive=False))
    W, So, E, N = A['bbox']
    cx, cy = (W + E) / 2, (So + N) / 2
    for fid, raw, code, why in [
            ('AST-nan-lon', '{"lon": NaN, "lat": 51.17}', 'not_finite', 'NaN (в строгом JSON недопустим; здесь — если пришёл из кода)'),
            ('AST-inf-lat', '[71.43, Infinity]', 'not_finite', 'Infinity'),
            ('AST-1e999', '[1e999, 51.17]', 'not_finite', '1e999 — парсеры дают бесконечность'),
            ('AST-bigint', '[' + '1' * 400 + ', 51.17]', 'not_finite', 'целое из 400 цифр: в JS Infinity, в Python — переполнение'),
            ('AST-null', '[null, 51.17]', 'not_number', 'null вместо числа'),
            ('AST-string', '["71.43", "51.17"]', 'not_number', 'строки не приводятся к числам'),
            ('AST-bool', '[true, 51.17]', 'not_number', 'bool не число'),
            ('AST-short', '[71.43]', 'bad_shape', 'одна координата'),
            ('AST-extra-key', '{"lon": 71.43, "lat": 51.17, "url": "http://example.org"}', 'bad_shape', 'лишнее поле (внешний URL) не принимается'),
            ('AST-lon-range', '[200.0, 51.17]', 'out_of_range', 'долгота > 180'),
            ('AST-lat-range', '[71.43, -91.0]', 'out_of_range', 'широта < -90')]:
        add(fid, 'astana', 'control', None, code, why, raw=raw)
    add('AST-bad-slice', 'astana', 'control', [cx, cy], 'bad_slice', 'срез с нулевой шириной bbox',
        slice_override=dict(bbox=[W, So, W, N]))
    # Спорные зоны K03 (round 3) — вне квадратов среза: отклоняются по bbox, а не по району
    for fid, pt, why in [('AST-Z1-exclave', [71.66574, 51.33028], 'эксклав Байконура ∩ Целиноградский район (AST-Z1)'),
                         ('AST-Z2-hole', [71.4046433, 50.8719883], 'часть контура города без района (AST-Z2)'),
                         ('AST-Z3-sliver', [71.4622857, 51.1287367], 'полоса расхождения версий Алматы/Сарайшык (AST-Z3)')]:
        add(fid, 'astana', 'proposed', pt, 'outside_bbox', why + ' — вне квадрата среза', k03=fid)
    borders = {'astana': ['kz.astana.district.baikonur', 'kz.astana.district.saryarka', A['bbox']],
               'shymkent': ['kz.shymkent.district.al-farabi', 'kz.shymkent.district.enbekshi', Sh['bbox']]}
    pts = {f['id']: f['point'] for f in F if f['point'] and f['k03_ref']}
    k3 = k03_points(app, root, dict(points=pts, borders=borders))
    for c, bd in k3['borders'].items():
        p = c[:3].upper()
        for d, why in (('0.0', 'на общей границе районов'), ('0.5', '0,5 м от общей границы'), ('5.0', '5 м от общей границы')):
            add(f'{p}-border-{d}', c, 'proposed', bd['points'][d], 'inside',
                f'гипотетический объект {why} {bd["a"].split(".")[-1]}/{bd["b"].split(".")[-1]} внутри квадрата', k03=f'{p}-border-{d}')
    pts2 = {f['id']: f['point'] for f in F if f['k03_ref'] and f['k03_ref'].startswith(('AST-border', 'SHY-border'))}
    k3b = k03_points(app, root, dict(points=pts2, borders={}))
    info = dict(k3['assign'], **k3b['assign'])
    for f in F:
        if f['k03_ref']:
            f['k03_info'] = dict(info[f['id']], informational_only=True, legal_status='not_verified')
        del f['k03_ref']
    k03_file = app / 'inputs' / root / 'research/round-3-results/K03/boundary_validator.py'
    doc = dict(
        schema='k03-point-fixtures-v1',
        description=('Координаты контрольных точек и проектного объекта city-whatif-v1: проверка по bbox текущего среза. '
                     'Ожидаемый исход — правило point_check; k03_info — справка K03 (район не условие приёма, не официальная принадлежность).'),
        target=dict(branch='claude/beautiful-clarke-sbzomj', sha=a.target_sha, path='prototypes/city-evidence/',
                    web_data_js_sha256=hashlib.sha256((app / 'web/data.js').read_bytes()).hexdigest(),
                    web_evidence_js_sha256=hashlib.sha256((app / 'web/evidence.js').read_bytes()).hexdigest(),
                    k03_root=f'inputs/{root}', k03_validator_sha256=hashlib.sha256(k03_file.read_bytes()).hexdigest()),
        slices=S, special_values='raw_json разбирается парсером реализации (Python json / JS: NaN и Infinity подставляются вручную)',
        fixtures=F)
    a.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(F)} fixtures → {a.out}')
    for f in F:
        if 'k03_info' in f:
            print(f"  {f['id']:18} expected {f['expected']['code']:13} K03: {f['k03_info']['status']} {f['k03_info']['district'] or ''} {f['k03_info']['reason']}")


if __name__ == '__main__':
    main()
