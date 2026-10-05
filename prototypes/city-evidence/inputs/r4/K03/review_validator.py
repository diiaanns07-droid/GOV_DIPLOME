"""K03 round 4 REVIEW: дополнительные точки для boundary_validator (round 3 @ 44585de).

  python3 research/round-4-results/K03/review_validator.py
Пишет рядом: fixtures.json (точки, ожидания, происхождение), review_results.json (v1/v2/оракул, обход границ).
round-3 файлы не меняются; v2 = round-3 + fix_spec.json, применённый в памяти.

Ожидаемый исход каждой точки задан контрактом правила (порядок шагов в boundary_registry.json →
assignment_rule; v2 добавляет: край города раньше зоны unmatched), а не результатом валидатора.
"""
import json
import math
from collections import Counter

from shapely.geometry import Point

import k03_review_lib as k

TOL = 1.0


def main():
    v1, v2 = k.load_v1(), k.load_v2()
    L = v1.Layers()
    O = k.Oracle(L)
    import geo_common as gc
    _, rels = gc.overpass_relations()
    prod_hash = {u: gc.ghash(g) for u, g in L.ast_prod.items()}
    ov_hash = {u: gc.ghash(g) for u, g in L.ast_ov.items()}
    shy_hash = {u: gc.ghash(g) for u, g in L.shy.items()}
    city_hash = {'astana': gc.ghash(L.ast_city), 'shymkent': gc.ghash(L.shy_city)}
    F = []

    def add(fid, cat, city, pt_utm, exp, exp_d, basis, construction, measured=None):
        lon, lat = k.ll(pt_utm)
        F.append(dict(id=fid, category=cat, city=city, lon=lon, lat=lat, expected_status=exp,
                      expected_district=exp_d, contract_basis=basis, construction=construction,
                      measured=measured or {}))

    def add_ll(fid, cat, city, lon, lat, exp, exp_d, basis, construction):
        F.append(dict(id=fid, category=cat, city=city, lon=lon, lat=lat, expected_status=exp,
                      expected_district=exp_d, contract_basis=basis, construction=construction, measured={}))

    # ---- 1. Общая граница районов (Астана, слой снимка OSM): Есиль | Нура
    def shared_case(prefix, city, layer, hashes, a, b, layer_id):
        A, B = k.utm(layer[a]), k.utm(layer[b])
        line = k.longest_line(A.boundary.intersection(B.boundary))
        s = line.length / 2
        base = line.interpolate(s)
        others = [u for u in layer if u not in (a, b)]
        clear = min(k.utm(layer[u]).boundary.distance(base) for u in others) if others else None
        nA = k.side_normal(line, s, A)
        nB = (-nA[0], -nA[1])
        con = dict(method='середина самого длинного общего участка границы, смещение по нормали',
                   layer=layer_id, unit_a=a, unit_b=b, geom_sha256_a=hashes[a], geom_sha256_b=hashes[b],
                   shared_line_length_m=round(line.length, 1),
                   distance_to_other_districts_m=round(clear, 1) if clear is not None else None)
        add(f'{prefix}-0', 'shared_boundary', city, base, 'ambiguous', None,
            'точка на общей границе: covers ≥2 районов → ambiguous', dict(con, offset_m=0))
        for d, exp, ed, basis in [
                (0.5, 'ambiguous', None, '0,5 м < tol 1 м от границы → ambiguous'),
                (0.99, 'ambiguous', None, 'крайний случай: 0,99 м ≤ tol → ambiguous'),
                (1.01, 'matched', a, 'крайний случай: 1,01 м > tol, один район → matched'),
                (3.0, 'matched', a, '3 м внутрь района → matched')]:
            p = k.offset(base, nA, d)
            add(f'{prefix}-a{d}', 'shared_boundary', city, p, exp, ed, basis, dict(con, offset_m=d, side=a),
                dict(utm_dist_to_shared_m=round(line.distance(p), 4),
                     geodesic_dist_to_shared_m=round(k.geodesic_to_line(p, line), 4)))
        p = k.offset(base, nB, 3.0)
        add(f'{prefix}-b3', 'shared_boundary', city, p, 'matched', b, '3 м внутрь второго района → matched',
            dict(con, offset_m=3.0, side=b))

    shared_case('AST-SB', 'astana', L.ast_prod, prod_hash, 'kz.astana.district.esil', 'kz.astana.district.nura',
                'astana.osm_snapshot')
    shared_case('SHY-SB', 'shymkent', L.shy, shy_hash, 'kz.shymkent.district.abay', 'kz.shymkent.district.karatau',
                'shymkent.overture_2026-09-23.1')

    # Вершины на стыке ≥3 районов Шымкента
    import shapely
    sv = {}
    for u, g in L.shy.items():
        for c in shapely.get_coordinates(g.boundary):
            sv.setdefault(tuple(c), set()).add(u)
    tri = sorted((c, sorted(s)) for c, s in sv.items() if len(s) >= 3)
    for i, (c, s) in enumerate(tri[:2]):
        add_ll(f'SHY-TRI-{i}', 'shared_boundary', 'shymkent', float(c[0]), float(c[1]), 'ambiguous', None,
               'общая вершина ≥3 районов → ambiguous',
               dict(method='вершина, общая для границ ≥3 районов', layer='shymkent.overture_2026-09-23.1', units=s))

    # ---- 2. Эксклав AST-Z1 и эксклавы без конфликта
    z1 = O.z1
    rp = z1.representative_point()
    add('AST-EX-in', 'exclave', 'astana', rp, 'ambiguous', None,
        'AST-Z1: эксклав Байконура ∩ Целиноградский район → ambiguous',
        dict(method='representative_point зоны', zone='AST-Z1', zone_area_km2=round(z1.area / 1e6, 3)))
    ring = z1.exterior if z1.geom_type == 'Polygon' else max(z1.geoms, key=lambda q: q.area).exterior
    s = ring.length / 4
    n_in = k.side_normal(ring, s, z1)
    base = ring.interpolate(s)
    for d, exp, basis in [(-0.5, 'ambiguous', '0,5 м снаружи эксклава (вне города) → край города, ambiguous'),
                          (-5.0, 'outside', '5 м снаружи эксклава, вне контура города → outside')]:
        add(f'AST-EX-out{abs(d)}', 'exclave', 'astana', k.offset(base, n_in, d), exp, None, basis,
            dict(method='точка на границе AST-Z1, смещение наружу', zone='AST-Z1', offset_m=d))
    bk = k.utm(L.ast_prod['kz.astana.district.baikonur'])
    for part in sorted(bk.geoms, key=lambda q: -q.area)[1:]:
        if part.intersection(O.z1).area == 0:
            add(f'AST-EX-ok{round(part.area / 1e6, 3)}', 'exclave', 'astana', part.representative_point(), 'matched',
                'kz.astana.district.baikonur', 'эксклав без конфликта с соседями → matched',
                dict(method='representative_point эксклава', layer='astana.osm_snapshot', area_km2=round(part.area / 1e6, 3)))
    al = k.utm(L.ast_prod['kz.astana.district.almaty'])
    small = min(al.geoms, key=lambda q: q.area)
    add('AST-EX-almaty', 'exclave', 'astana', small.representative_point(), 'matched', 'kz.astana.district.almaty',
        'эксклав Алматы, конфликта нет → matched',
        dict(method='representative_point меньшей части Алматы', layer='astana.osm_snapshot', area_km2=round(small.area / 1e6, 3)))

    # ---- 3. Дыра покрытия AST-Z2
    z2 = O.z2
    add('AST-HOLE-in', 'coverage_hole', 'astana', z2.representative_point(), 'unmatched', None,
        'AST-Z2: внутри контура города, ни одного района, дальше tol от края → unmatched',
        dict(method='representative_point зоны', zone='AST-Z2', zone_area_km2=round(z2.area / 1e6, 3),
             city_outline_sha256=city_hash['astana']))
    ring = z2.exterior if z2.geom_type == 'Polygon' else max(z2.geoms, key=lambda q: q.area).exterior
    s = ring.length / 3
    n_in = k.side_normal(ring, s, z2)
    base = ring.interpolate(s)
    for d, exp, basis in [
            (0.5, 'ambiguous', 'край города (0,5 м внутри): принадлежность городу не доказана → ambiguous (как у прочего края)'),
            (-0.5, 'ambiguous', '0,5 м снаружи контура города: не «внутри города» → ambiguous (край), не unmatched'),
            (5.0, 'unmatched', '5 м внутри зоны → unmatched'),
            (-5.0, 'outside', '5 м снаружи контура города → outside')]:
        add(f'AST-HOLE-{"in" if d > 0 else "out"}{abs(d)}', 'coverage_hole', 'astana', k.offset(base, n_in, d), exp, None,
            basis, dict(method='граница AST-Z2 (= край города), смещение по нормали', zone='AST-Z2', offset_m=d),
            dict(utm_dist_to_city_edge_m=round(O.city['astana'].boundary.distance(k.offset(base, n_in, d)), 4)))

    # ---- 4. Полоса расхождения версий AST-Z3 (путь 903345831)
    z3 = O.z3
    big = max(getattr(z3, 'geoms', [z3]), key=lambda q: q.area)
    add('AST-VER-in', 'version_strip', 'astana', big.representative_point(), 'ambiguous', None,
        'AST-Z3: снимок OSM и Overture относят точку к разным районам → ambiguous',
        dict(method='representative_point крупнейшей части AST-Z3', zone='AST-Z3', part_area_m2=round(big.area, 2),
             way=903345831))
    A, S = k.utm(L.ast_prod['kz.astana.district.almaty']), k.utm(L.ast_prod['kz.astana.district.saraishyk'])
    line = k.longest_line(A.boundary.intersection(S.boundary))
    s0 = line.project(big.representative_point())
    base = line.interpolate(s0)
    nA = k.side_normal(line, s0, A)
    for d, side, exp, ed, basis in [
            (0.0, 'almaty', 'ambiguous', None, 'на границе снимка у изменённого пути → ambiguous'),
            (2.0, 'almaty', 'matched', 'kz.astana.district.almaty', '2 м от границы снимка (≥1,56 м от границы Overture) → matched'),
            (2.0, 'saraishyk', 'matched', 'kz.astana.district.saraishyk', '2 м в Сарайшык → matched')]:
        n = nA if side == 'almaty' else (-nA[0], -nA[1])
        p = k.offset(base, n, d)
        ovline = k.longest_line(k.utm(L.ast_ov['kz.astana.district.almaty']).boundary.intersection(
            k.utm(L.ast_ov['kz.astana.district.saraishyk']).boundary))
        add(f'AST-VER-{side}{d}', 'version_strip', 'astana', p, exp, ed, basis,
            dict(method='общая граница Алматы/Сарайшык в снимке OSM у AST-Z3, смещение по нормали', offset_m=d, side=side,
                 geom_sha256_almaty_snapshot=prod_hash['kz.astana.district.almaty'],
                 geom_sha256_almaty_overture=ov_hash['kz.astana.district.almaty']),
            dict(utm_dist_to_snapshot_border_m=round(line.distance(p), 4), utm_dist_to_overture_border_m=round(ovline.distance(p), 4)))

    # D2: 1,01 м от границы снимка там, где граница Overture ближе 1 м (поиск шагом 0,5 м вдоль общей границы)
    best = None
    t = 0.0
    while t <= line.length:
        b = line.interpolate(t)
        if z3.distance(b) < 30:
            nn = k.side_normal(line, t, A)
            for sgn in (1, -1):
                p = k.offset(b, (nn[0] * sgn, nn[1] * sgn), 1.01)
                dov = ovline.distance(p)
                if line.distance(p) > 1.0 and (best is None or dov < best[0]):
                    best = (dov, p, t, 'almaty' if sgn == 1 else 'saraishyk')
        t += 0.5
    dov, p, t, side = best
    add('AST-VER-D2', 'version_strip', 'astana', p, 'ambiguous', None,
        'D2: дальше 1 м от границы снимка, но ближе 1 м к границе Overture той же пары районов → ambiguous (допуск во всех версиях)',
        dict(method='перебор шагом 0,5 м вдоль общей границы Алматы/Сарайшык снимка у AST-Z3; смещение 1,01 м; выбрана точка с минимальным расстоянием до границы Overture',
             side=side, along_m=t, way=903345831),
        dict(utm_dist_to_snapshot_border_m=round(line.distance(p), 4), utm_dist_to_overture_border_m=round(dov, 4),
             geodesic_dist_to_snapshot_border_m=round(k.geodesic_to_line(p, line), 4),
             geodesic_dist_to_overture_border_m=round(k.geodesic_to_line(p, ovline), 4)))

    # ---- 5. Outside и край города у обычного района
    for rid in (15594335, 3403760):
        g, _ = gc.build_osm_relation(rels[rid])
        q = k.utm(g).difference(O.city['astana'].buffer(50)).representative_point()
        add(f'OUT-{rid}', 'outside', 'astana', q, 'outside', None, 'внутри соседнего отношения, вне контура города → outside',
            dict(method='representative_point(соседнее отношение − буфер города 50 м)', osm_relation=rid,
                 name=rels[rid]['tags'].get('name')))
    for city, cg in (('astana', O.city['astana']), ('shymkent', O.city['shymkent'])):
        main = max(getattr(cg, 'geoms', [cg]), key=lambda q: q.area)
        ring = main.exterior
        s = ring.length * 0.37
        base = ring.interpolate(s)
        n_in = k.side_normal(ring, s, main)
        lay = O.prod if city == 'astana' else O.shy
        owner = next(u for u, g in lay.items() if g.contains(k.offset(base, n_in, 3.0)))
        for d, exp, ed, basis in [(-5.0, 'outside', None, '5 м за краем города → outside'),
                                  (-0.5, 'ambiguous', None, '0,5 м за краем (в пределах tol) → ambiguous'),
                                  (0.5, 'ambiguous', None, '0,5 м внутри у края → ambiguous'),
                                  (3.0, 'matched', owner, '3 м внутри района у края → matched')]:
            add(f'{city[:3].upper()}-EDGE{d}', 'city_edge', city, k.offset(base, n_in, d), exp, ed, basis,
                dict(method='точка на внешнем кольце основной части города, смещение по нормали', offset_m=d,
                     city_outline_sha256=city_hash[city]))
    add_ll('OUT-desert', 'outside', None, 70.0, 45.0, 'outside', None, 'вне обоих городов', dict(method='задано вручную'))

    # ---- 6. Порядок lon/lat и мусорные значения
    for fid, lon, lat, exp, basis in [
            ('SWAP-astana', 51.1, 71.43, 'invalid', 'Астана с перепутанным порядком → invalid (lon_lat_swapped)'),
            ('SWAP-shymkent', 42.3, 69.6, 'invalid', 'Шымкент с перепутанным порядком → invalid (lon_lat_swapped)'),
            ('SWAP-undetectable', 50.0, 50.0, 'outside', 'оба порядка в диапазоне KZ: перестановка неразличима → outside (ограничение правила)'),
            ('BAD-nan', float('nan'), 51.1, 'invalid', 'NaN → invalid'),
            ('BAD-range', 200.0, 51.1, 'invalid', 'долгота вне диапазона → invalid')]:
        add_ll(fid, 'lon_lat_order', None, lon, lat, exp, None, basis, dict(method='задано вручную'))

    # ---- прогон фикстур
    def run(m, f):
        r = m.assign(L, f['lon'], f['lat'])
        return dict(status=r['status'], district=r.get('district'), reason=r.get('reason'))

    rows = []
    for f in F:
        r1, r2 = run(v1, f), run(v2, f)
        o = O.expect(f['lon'], f['lat'])
        ok = lambda r: r['status'] == f['expected_status'] and (f['expected_district'] is None or r['district'] == f['expected_district'])
        rows.append(dict(id=f['id'], expected=[f['expected_status'], f['expected_district']], oracle=list(o),
                         oracle_agrees=o[0] == f['expected_status'] and o[1] == f['expected_district'],
                         v1=r1, v1_pass=ok(r1), v2=r2, v2_pass=ok(r2)))

    # ---- обход границ: точки по всем кольцам районов, городов и зон, смещения по нормали
    offsets = [-3, -1.5, -1.01, -0.99, -0.5, 0, 0.5, 0.99, 1.01, 1.5, 3]
    rings = []
    for name, lay in (('ast_prod', O.prod), ('ast_ov', O.ov), ('shy', O.shy)):
        for u, g in lay.items():
            for part in getattr(g, 'geoms', [g]):
                rings.append((f'{name}:{u}', part, part.exterior))
    for name, g in (('city:astana', O.city['astana']), ('city:shymkent', O.city['shymkent']),
                    ('zone:Z1', O.z1), ('zone:Z2', O.z2)):
        for part in getattr(g, 'geoms', [g]):
            rings.append((name, part, part.exterior))
    sweep = Counter()
    mism = []
    n = 0
    for name, poly, ring in rings:
        steps = 24
        for i in range(steps):
            s = ring.length * (i + 0.5) / steps
            base = ring.interpolate(s)
            nn = k.side_normal(ring, s, poly)
            for d in offsets:
                p = k.offset(base, nn, d)
                lon, lat = k.ll(p)
                o = O.expect(lon, lat)
                a1 = v1.assign(L, lon, lat)
                a2 = v2.assign(L, lon, lat)
                n += 1
                for tag, a in (('v1', a1), ('v2', a2)):
                    good = a['status'] == o[0] and (o[1] is None or a.get('district') == o[1])
                    sweep[(tag, good)] += 1
                    if not good and len(mism) < 400:
                        mism.append(dict(version=tag, ring=name, offset_m=d, lon=lon, lat=lat, oracle=list(o),
                                         got=[a['status'], a.get('district'), a.get('reason')]))
                if a1['status'] == 'matched' and (a1.get('district') is None):
                    sweep[('v1_matched_without_district', True)] += 1
    by_kind = Counter((m['version'], m['ring'].split(':')[0] + ':' + m['ring'].split(':')[1].split('.')[-1]
                       if m['ring'].startswith(('ast', 'shy')) else m['ring'], tuple(m['oracle'][:1]), m['got'][0], m['got'][2])
                      for m in mism)
    res = dict(
        reviewed=dict(path='research/round-3-results/K03/boundary_validator.py', snapshot=k.SNAPSHOT_SHA,
                      git_blob='23b9fe45b0b447f080ee63bb3a7792ffe7d79497'),
        tol_m=TOL, fixtures=len(F),
        fixture_summary=dict(v1_pass=sum(r['v1_pass'] for r in rows), v2_pass=sum(r['v2_pass'] for r in rows),
                             oracle_agrees_with_expected=sum(r['oracle_agrees'] for r in rows)),
        fixture_results=rows,
        sweep=dict(points=n, rings=len(rings), offsets_m=offsets, steps_per_ring=24,
                   v1_agree=sweep[('v1', True)], v1_disagree=sweep[('v1', False)],
                   v2_agree=sweep[('v2', True)], v2_disagree=sweep[('v2', False)],
                   disagreement_kinds=[dict(version=a, ring=b, oracle=c[0], got=d, reason=e, count=cnt)
                                       for (a, b, c, d, e), cnt in sorted(by_kind.items(), key=lambda t: (t[0][0], -t[1]))],
                   examples=mism[:12]))
    (k.HERE / 'fixtures.json').write_text(json.dumps(dict(
        description='Фикстуры K03 round 4: точки с ожидаемым исходом по контракту k03_assign (v2) и происхождением',
        crs='EPSG:4326 lon/lat; построение в EPSG:32642', tol_m=TOL,
        layers={'astana.osm_snapshot': 'data/astana_districts.geojson (osm_base 2026-09-22T08:45:51Z)',
                'astana.overture_2026-09-23.1': 'research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson',
                'shymkent.overture_2026-09-23.1': 'research/round-3-results/K03/inputs/K10/shymkent_districts_overture.geojson'},
        legal_status='not_verified: фикстуры проверяют правило на данных сообщества, не официальные границы',
        fixtures=[dict(f, lon=None if isinstance(f['lon'], float) and math.isnan(f['lon']) else f['lon'],
                       lon_is_nan=isinstance(f['lon'], float) and math.isnan(f['lon'])) for f in F]),
        ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (k.HERE / 'review_results.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(dict(fixtures=len(F), **res['fixture_summary'],
                          sweep={kk: v for kk, v in res['sweep'].items() if kk.startswith(('points', 'v1', 'v2'))}),
                     ensure_ascii=False))
    for r in rows:
        if not (r['v1_pass'] and r['v2_pass'] and r['oracle_agrees']):
            print('  ', r['id'], 'exp', r['expected'], 'oracle', r['oracle'], 'v1', r['v1'], 'v2', r['v2'])


if __name__ == '__main__':
    main()
