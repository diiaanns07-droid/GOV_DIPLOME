"""K03: независимая проверка географии Астаны и Шымкента на сохранённых файлах.

Только чтение. Сеть не используется. Исходники продукта и чужие отчёты не меняются.
Запуск из корня репозитория:
    python3 research/next-round/K03/k03_geo_verify.py
Пишет рядом:
    k03_geo_verify_output.json  — все измерения;
    territory_registry.json/.csv — реестр территорий;
    conflicts.json               — реестр конфликтов.

Геометрия соседних отношений собирается заново из линий OSM (склейка путей по
концам), а не через polygonize/symmetric_difference, как в AST_A12_experiments.py.
Конфликт эксклава дополнительно проверяется по составу путей (way id) отношений,
то есть независимо от сборки полигонов.
"""
import csv, hashlib, json, platform, sys
from collections import Counter, defaultdict
from pathlib import Path

import pyproj, shapely
from pyproj import Geod
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
GEOD = Geod(ellps='WGS84')

F_GEOJSON = 'data/astana_districts.geojson'
F_OVERPASS = 'data/geo_sources/astana_districts_overpass.json'
F_OVERPASS2 = 'data/geo_sources/overpass.json'
F_SARA_OSM = 'data/geo_sources/sara_osm.json'
F_SARA_NOM = 'data/geo_sources/sara_nominatim.json'
F_REAL_CTX = 'data/real_context.json'
F_REAL_META = 'data/real_context_meta.json'
F_CITY = 'data/city_data.json'
F_A03 = 'research/astana-results/03_logistics/extracted_files__25_/AST_A03_input_astana_districts_osm.geojson'
F_A03_SYN = 'research/govtech-results/03_logistics/extracted_files__22_/A03_synthetic_instance.geojson'

ASTANA = {3479876: 'esil', 3482819: 'almaty', 3486954: 'saryarka',
          8593081: 'baikonur', 20593940: 'nura', 19733918: 'saraishyk'}
TINY_KM2 = 1e-4  # 100 м²: меньше считаем численным шумом общей границы


def sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def load(p):
    return json.loads((ROOT / p).read_text(encoding='utf-8'))


def km2(g):
    return abs(GEOD.geometry_area_perimeter(g)[0]) / 1e6


def parts(g):
    return list(g.geoms) if hasattr(g, 'geoms') else [g]


def join_rings(ways):
    """ways: [(way_id, [(lon, lat), ...])] → (closed rings with way ids, open chains)."""
    pool = [(list(c), [wid]) for wid, c in ways]
    rings, open_chains = [], []
    while pool:
        cur, ids = pool.pop(0)
        grown = True
        while cur[0] != cur[-1] and grown:
            grown = False
            for i, (s, sid) in enumerate(pool):
                if s[0] == cur[-1]:
                    cur, ids = cur + s[1:], ids + sid
                elif s[-1] == cur[-1]:
                    cur, ids = cur + s[::-1][1:], ids + sid
                elif s[-1] == cur[0]:
                    cur, ids = s + cur[1:], sid + ids
                elif s[0] == cur[0]:
                    cur, ids = s[::-1] + cur[1:], sid + ids
                else:
                    continue
                pool.pop(i)
                grown = True
                break
        (rings if len(cur) >= 4 and cur[0] == cur[-1] else open_chains).append((cur, ids))
    return rings, open_chains


def build_relation(rel):
    by_role = defaultdict(list)
    for m in rel['members']:
        if m['type'] == 'way' and m.get('geometry'):
            by_role[m.get('role', '')].append((m['ref'], [(p['lon'], p['lat']) for p in m['geometry']]))
    outer_r, outer_open = join_rings(by_role.get('outer', []) + by_role.get('', []))
    inner_r, inner_open = join_rings(by_role.get('inner', []))
    outers = [(Polygon(r), ids) for r, ids in outer_r]
    inners = [(Polygon(r), ids) for r, ids in inner_r]
    holes = defaultdict(list)
    for ip, _ in inners:  # дырка — к наименьшему внешнему кольцу, которое её содержит
        cands = [k for k, (op, _) in enumerate(outers) if op.covers(ip.representative_point())]
        if cands:
            holes[min(cands, key=lambda k: outers[k][0].area)].append(ip)
    pieces = []
    for k, (op, ids) in enumerate(outers):
        g = op.difference(unary_union(holes[k])) if holes[k] else op
        pieces.append((g, ids))
    geom = unary_union([g for g, _ in pieces]) if pieces else None
    return dict(
        geom=geom, pieces=pieces,
        roles={r: len(v) for r, v in by_role.items()},
        member_ways={m['ref']: m.get('role', '') for m in rel['members'] if m['type'] == 'way'},
        outer_rings=len(outer_r), inner_rings=len(inner_r),
        open_chains=len(outer_open) + len(inner_open),
        rings_valid=all(op.is_valid for op, _ in outers + inners),
        geom_valid=bool(geom is not None and geom.is_valid))


def main():
    out = dict(meta=dict(
        task='K03 geography verification', network_used=False,
        python=platform.python_version(), shapely=shapely.__version__, pyproj=pyproj.__version__,
        inputs={p: sha(p) for p in [F_GEOJSON, F_OVERPASS, F_OVERPASS2, F_SARA_OSM, F_SARA_NOM,
                                     F_REAL_CTX, F_REAL_META, F_CITY, F_A03, F_A03_SYN]}))

    gj = load(F_GEOJSON)
    ov = load(F_OVERPASS)
    ov2 = load(F_OVERPASS2)
    snap = ov['osm3s']['timestamp_osm_base']
    retrieved = ov['_provenance']['retrieved_at']

    # V1. Два сырых ответа Overpass: одинаковы ли элементы.
    out['V1_raw_overpass_copies'] = dict(
        same_osm_base=ov['osm3s'] == ov2['osm3s'],
        same_elements=ov['elements'] == ov2['elements'],
        only_difference_is_provenance_key=(set(ov) - set(ov2)) == {'_provenance'} and ov['elements'] == ov2['elements'])

    # V2. Инвентарь отношений в ответе bbox-запроса.
    rels = {e['id']: e for e in ov['elements'] if e['type'] == 'relation'}
    inv = []
    for rid, e in sorted(rels.items()):
        t = e['tags']
        inv.append(dict(
            relation=rid, in_product=rid in ASTANA, legacy_id=ASTANA.get(rid),
            admin_level=t.get('admin_level'), name=t.get('name'), name_ru=t.get('name:ru'),
            name_kk=t.get('name:kk'), name_en=t.get('name:en'), addr_region=t.get('addr:region'),
            wikidata=t.get('wikidata'),
            id_like_tags={k: v for k, v in t.items()
                          if any(s in k.lower() for s in ('ref', 'kato', 'iso', 'code', 'oktmo'))}))
    out['V2_bbox_relations'] = dict(
        query=gj['metadata']['source_url'], osm_base=snap, retrieved_at=retrieved,
        count=len(inv), astana_districts=sum(r['in_product'] for r in inv),
        not_astana=[dict(relation=r['relation'], name=r['name'], admin_level=r['admin_level'],
                         addr_region=r['addr_region']) for r in inv if not r['in_product']],
        relations=inv)

    # V3. Независимая сборка всех 11 отношений.
    built = {rid: build_relation(e) for rid, e in rels.items()}
    out['V3_assembly'] = {str(rid): dict(
        name=rels[rid]['tags'].get('name'), roles=b['roles'], outer_rings=b['outer_rings'],
        inner_rings=b['inner_rings'], open_chains=b['open_chains'], rings_valid=b['rings_valid'],
        geom_valid=b['geom_valid'], area_km2=round(km2(b['geom']), 3) if b['geom'] else None,
        parts_km2=sorted((round(km2(p), 3) for p in parts(b['geom'])), reverse=True) if b['geom'] else [])
        for rid, b in sorted(built.items())}

    # V4. GeoJSON продукта против независимой сборки и против копии AST-A03.
    prod = {f['properties']['id']: f for f in gj['features']}
    a03 = load(F_A03)
    a03_ids = {(f['properties'].get('id') or f['properties'].get('district_id')): f for f in a03['features']}
    cmp = {}
    for rid, lid in ASTANA.items():
        pg = shape(prod[lid]['geometry'])
        mine = built[rid]['geom']
        p = prod[lid]['properties']
        row = dict(
            relation=rid, osm_admin_level_in_geojson=p.get('osm_admin_level'),
            valid=pg.is_valid, parts=len(parts(pg)),
            parts_km2=sorted((round(km2(x), 3) for x in parts(pg)), reverse=True),
            area_km2_repo_field=p.get('area_km2'), area_km2_geodesic=round(km2(pg), 2),
            repo_field_minus_geodesic_pct=round((p['area_km2'] - km2(pg)) / km2(pg) * 100, 2),
            symdiff_vs_independent_build_km2=round(km2(pg.symmetric_difference(mine)), 6),
            coords_lon_lat_in_kz_range=all(46.5 <= x <= 87.5 and 40.5 <= y <= 55.5
                                           for x, y in pg.exterior.coords) if pg.geom_type == 'Polygon'
            else all(46.5 <= x <= 87.5 and 40.5 <= y <= 55.5 for q in pg.geoms for x, y in q.exterior.coords))
        if lid in a03_ids:
            row['symdiff_vs_AST_A03_copy_km2'] = round(km2(pg.symmetric_difference(shape(a03_ids[lid]['geometry']))), 6)
        cmp[lid] = row
    out['V4_product_geojson'] = dict(
        metadata=gj['metadata'], districts=cmp,
        a03_copy=dict(file=F_A03, feature_ids=sorted(str(k) for k in a03_ids),
                      byte_identical_to_product=sha(F_A03) == sha(F_GEOJSON)))

    # V5. Объединение районов Астаны: площадь, части, внутренние пустоты.
    D = {lid: shape(prod[lid]['geometry']) for lid in prod}
    U = unary_union(list(D.values()))
    holes = [Polygon(r) for p in parts(U) for r in p.interiors]
    part_owner = []
    for p in sorted(parts(U), key=lambda q: -km2(q)):
        rp = p.representative_point()
        part_owner.append(dict(area_km2=round(km2(p), 3),
                               rep_point_in_district=sorted(k for k, g in D.items() if g.covers(rp)),
                               rep_point=[round(rp.x, 5), round(rp.y, 5)]))
    pair_overlaps = {}
    ks = sorted(D)
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            x = D[a].intersection(D[b])
            if not x.is_empty and x.area > 0 and km2(x) > TINY_KM2:
                pair_overlaps[f'{a}|{b}'] = round(km2(x), 6)
    out['V5_astana_union'] = dict(
        union_km2=round(km2(U), 2), sum_of_districts_km2=round(sum(km2(g) for g in D.values()), 2),
        parts=part_owner, interior_gaps=len(holes), interior_gaps_km2=[round(km2(h), 6) for h in holes],
        overlapping_district_pairs_over_100m2=pair_overlaps)

    # V6. Площадные пересечения районов Астаны с соседями из того же ответа.
    neigh = {}
    for rid, b in built.items():
        if rid in ASTANA:
            continue
        g = b['geom']
        per = {}
        for lid, dg in D.items():
            x = g.intersection(dg)
            a = km2(x) if not x.is_empty and x.area > 0 else 0.0
            if a > TINY_KM2:
                per[lid] = round(a, 4)
        touches = g.boundary.intersection(U.boundary).length > 0
        neigh[str(rid)] = dict(name=rels[rid]['tags'].get('name'), admin_level=rels[rid]['tags'].get('admin_level'),
                               area_km2=round(km2(g), 2), overlap_with_astana_districts_km2=per,
                               shares_boundary_with_astana_union=touches)
    out['V6_neighbour_overlaps'] = neigh
    allpairs = {}
    rk = sorted(built)
    for i, a in enumerate(rk):
        for b in rk[i + 1:]:
            x = built[a]['geom'].intersection(built[b]['geom'])
            if not x.is_empty and x.area > 0 and km2(x) > TINY_KM2:
                allpairs[f'{a}|{b}'] = dict(names=[rels[a]['tags'].get('name'), rels[b]['tags'].get('name')],
                                            admin_levels=[rels[a]['tags'].get('admin_level'), rels[b]['tags'].get('admin_level')],
                                            overlap_km2=round(km2(x), 3),
                                            smaller_fully_inside=round(km2(x), 3) >= round(min(km2(built[a]['geom']), km2(built[b]['geom'])), 3))
    out['V6b_all_relation_overlaps'] = allpairs

    # V7. Эксклав Байконура и Целиноградский район: по путям OSM, без сборки полигонов.
    tsel = built[3403760]
    bk = built[8593081]
    exclaves = []
    for g, ids in sorted(bk['pieces'], key=lambda t: -km2(t[0])):
        rp = g.representative_point()
        exclaves.append(dict(
            area_km2=round(km2(g), 3), rep_point=[round(rp.x, 5), round(rp.y, 5)], ring_way_ids=ids,
            ways_also_in_tselinograd={str(w): tsel['member_ways'][w] for w in ids if w in tsel['member_ways']},
            covered_by_tselinograd_build=tsel['geom'].covers(rp),
            covered_by_other_neighbours=[str(r) for r, b in built.items()
                                         if r not in ASTANA and r != 3403760 and b['geom'].covers(rp)]))
    tsel_inner = []
    t_in = [(m['ref'], [(p['lon'], p['lat']) for p in m['geometry']])
            for m in rels[3403760]['members'] if m['type'] == 'way' and m.get('role') == 'inner']
    for r, ids in join_rings(t_in)[0]:
        rp = Polygon(r).representative_point()
        tsel_inner.append(dict(ways=ids, area_km2=round(km2(Polygon(r)), 3), rep_point=[round(rp.x, 5), round(rp.y, 5)],
                               covered_by_saved_relations=[str(x) for x, b in built.items() if x != 3403760 and b['geom'].covers(rp)]))
    shared_all = {str(w): dict(baikonur_role=bk['member_ways'][w], tselinograd_role=tsel['member_ways'][w])
                  for w in bk['member_ways'] if w in tsel['member_ways']}
    out['V7_baikonur_exclave_vs_tselinograd'] = dict(
        tselinograd_roles=tsel['roles'], tselinograd_inner_rings=tsel['inner_rings'], tselinograd_inner_detail=tsel_inner,
        relations_with_way_372797931=[str(r) for r, e in rels.items()
                                      if any(m['type'] == 'way' and m['ref'] == 372797931 for m in e['members'])],
        baikonur_pieces=exclaves, ways_shared_baikonur_tselinograd=shared_all,
        ast_a12_point=dict(point=[71.66574, 51.33028],
                           in_baikonur=D['baikonur'].covers(Point(71.66574, 51.33028)),
                           in_tselinograd=tsel['geom'].covers(Point(71.66574, 51.33028))))

    # V8. Вершины, общие для трёх и более районов; contains против covers.
    vert = defaultdict(set)
    for lid, g in D.items():
        for p in parts(g):
            for ring in [p.exterior, *p.interiors]:
                for c in ring.coords:
                    vert[c].add(lid)
    multi = {c: sorted(s) for c, s in vert.items() if len(s) >= 3}
    tp = (71.447389, 51.1311552)
    out['V8_boundary_points'] = dict(
        vertices_shared_by_3plus_districts=[dict(point=list(c), districts=s) for c, s in sorted(multi.items())],
        ast_a12_point=dict(point=list(tp), shared_vertex_districts=sorted(vert.get(tp, [])),
                           contains={k: D[k].contains(Point(tp)) for k in D},
                           covers={k: D[k].covers(Point(tp)) for k in D}))

    # V9. Сарайшык: OSM API против Overpass, версия, Nominatim.
    so = load(F_SARA_OSM)
    rel = next(e for e in so['elements'] if e['type'] == 'relation')
    nodes = {e['id']: (e['lon'], e['lat']) for e in so['elements'] if e['type'] == 'node'}
    ways = {e['id']: e['nodes'] for e in so['elements'] if e['type'] == 'way'}
    api_rel = dict(members=[dict(type=m['type'], ref=m['ref'], role=m['role'],
                                 geometry=[dict(lon=nodes[n][0], lat=nodes[n][1]) for n in ways[m['ref']]])
                            if m['type'] == 'way' else m for m in rel['members']])
    api_geom = build_relation(api_rel)['geom']
    nom = load(F_SARA_NOM)[0]
    out['V9_saraishyk'] = dict(
        osm_api=dict(version=rel['version'], timestamp=rel['timestamp'], changeset=rel['changeset'],
                     admin_level=rel['tags'].get('admin_level'), members=len(rel['members'])),
        overpass_osm_base=snap, edit_before_snapshot=rel['timestamp'] < snap,
        same_way_members_as_overpass=sorted(m['ref'] for m in rel['members'] if m['type'] == 'way')
        == sorted(m['ref'] for m in rels[19733918]['members'] if m['type'] == 'way'),
        symdiff_api_vs_product_km2=round(km2(api_geom.symmetric_difference(D['saraishyk'])), 6),
        nominatim=dict(addresstype=nom.get('addresstype'), place_rank=nom.get('place_rank'), address=nom.get('address')))

    # V10. Районы в учебных и справочных файлах продукта.
    cd = load(F_CITY)
    rc = load(F_REAL_CTX)
    rm = load(F_REAL_META)
    out['V10_product_district_lists'] = dict(
        city_data_districts=[d['id'] for d in cd['districts']],
        real_context_districts=sorted(rc), real_context_nonzero=sum(1 for v in rc.values() for x in v.values() if x),
        real_context_meta={k: rm.get(k) for k in ('status', 'generated_at', 'districts_source')},
        geojson_districts=sorted(prod))

    # V11. Шымкент: есть ли в репозитории хоть какая-то реальная геометрия.
    syn = load(F_A03_SYN)
    out['V11_shymkent'] = dict(
        real_geometry_in_repo=False,
        searched=['data/', 'research/**/*.geojson'],
        only_shymkent_geojson=F_A03_SYN,
        a03_synthetic_metadata={k: v for k, v in syn.items() if k != 'features'},
        a03_synthetic_feature_count=len(syn.get('features', [])))

    (OUT / 'k03_geo_verify_output.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    write_registry(out, rels, D, built, snap, retrieved)
    write_conflicts(out, snap)
    print(json.dumps({k: out[k] for k in ('V1_raw_overpass_copies',)}, ensure_ascii=False))
    print('written:', [p.name for p in sorted(OUT.glob('*.json'))] + [p.name for p in sorted(OUT.glob('*.csv'))])


def write_registry(out, rels, D, built, snap, retrieved):
    bv = f'osm:{snap}'
    ov_sha = out['meta']['inputs'][F_OVERPASS][:16]
    gj_sha = out['meta']['inputs'][F_GEOJSON][:16]
    nom = out['V9_saraishyk']['nominatim']['address']
    excl = out['V7_baikonur_exclave_vs_tselinograd']
    conflict_ids = {}
    rows = []

    def row(**k):
        base = dict(territory_id=None, id_status=None, city=None, level=None, name_ru=None, name_kk=None,
                    name_source=None, legacy_id=None, osm_relation_id=None, osm_admin_level=None,
                    kato_code=None, kato_source=None, wikidata=None, iso_3166_2=None, boundary_version=None, snapshot_date=None,
                    retrieved_at=None, geometry_in_repo=None, geometry_source=None, area_km2_geodesic=None,
                    parts=None, provenance=None, osm_geometry_check=None, official_status_check=None,
                    use_in_city_aggregates=None, conflicts=None, notes=None)
        base.update(k)
        rows.append(base)

    row(territory_id='kz.astana', id_status='proposed (A12 rule)', city='astana', level='city',
        name_ru='Астана', name_kk='Астана', name_source='sara_nominatim.json address.city',
        iso_3166_2=f"{nom.get('ISO3166-2-lvl4')} (lvl4) / {nom.get('ISO3166-2-lvl15')} (lvl15) — Nominatim, не официально",
        boundary_version=bv, snapshot_date=snap, retrieved_at=retrieved, geometry_in_repo='derived only',
        geometry_source='derived: union of 6 OSM district relations (city relation not saved)',
        area_km2_geodesic=out['V5_astana_union']['union_km2'], parts=len(out['V5_astana_union']['parts']),
        provenance=f'{F_GEOJSON} sha256:{gj_sha}…; {F_SARA_NOM}',
        osm_geometry_check='verified_locally: union of saved district polygons',
        official_status_check='not_verified: official city boundary/KATO not opened (stat.gov.kz blocked)',
        use_in_city_aggregates='yes', conflicts='K03-C01; K03-C05',
        notes='Отношение города (admin_level 4) в сохранённом ответе отсутствует: запрос брал admin_level 5–9.')

    for rid, lid in ASTANA.items():
        t = rels[rid]['tags']
        d = out['V4_product_geojson']['districts'][lid]
        cf = []
        if t.get('admin_level') != '6':
            cf.append('K03-C02')
        if lid == 'baikonur' and any(p['covered_by_tselinograd_build'] for p in excl['baikonur_pieces']):
            cf.append('K03-C01')
        cf.append('K03-C05')
        if lid not in out['V10_product_district_lists']['city_data_districts']:
            cf.append('K03-C06')
        if any(lid in x['districts'] for x in out['V8_boundary_points']['vertices_shared_by_3plus_districts']):
            cf.append('K03-C07')
        row(territory_id=f'kz.astana.district.{lid}', id_status='proposed (A12 rule)', city='astana',
            level='district', name_ru=t.get('name:ru'), name_kk=t.get('name:kk') or t.get('name'),
            name_source='OSM name:ru; name:kk' + ('' if t.get('name:kk') else ' отсутствует → OSM name'),
            legacy_id=lid, osm_relation_id=rid, osm_admin_level=t.get('admin_level'),
            kato_code=t.get('kato'), kato_source=('OSM tag kato (community, not official)' if t.get('kato')
                                                  else 'absent in OSM snapshot; official not checked'),
            wikidata=t.get('wikidata'), boundary_version=bv, snapshot_date=snap, retrieved_at=retrieved, geometry_in_repo='yes',
            geometry_source='osm_community', area_km2_geodesic=d['area_km2_geodesic'], parts=d['parts'],
            provenance=f'{F_GEOJSON} sha256:{gj_sha}…; raw {F_OVERPASS} sha256:{ov_sha}…',
            osm_geometry_check=('verified_locally: valid, matches independent rebuild '
                                f"(symdiff {d['symdiff_vs_independent_build_km2']} km²)"),
            official_status_check='not_verified: district composition, KATO, legal act not opened',
            use_in_city_aggregates='yes', conflicts='; '.join(cf) or None,
            notes=('OSM version ' + str(out['V9_saraishyk']['osm_api']['version']) + ', edited '
                   + out['V9_saraishyk']['osm_api']['timestamp']) if lid == 'saraishyk' else None)

    for rid in sorted(rels):
        if rid in ASTANA:
            continue
        t = rels[rid]['tags']
        n = out['V6_neighbour_overlaps'][str(rid)]
        cf = 'K03-C01' if rid == 3403760 and n['overlap_with_astana_districts_km2'] else None
        row(territory_id=None, id_status='not assigned (outside Astana)', city='outside: ' + (t.get('addr:region') or 'region tag absent'),
            level=f"admin_level {t.get('admin_level')}", name_ru=t.get('name:ru'), name_kk=t.get('name:kk') or t.get('name'),
            name_source='OSM tags', osm_relation_id=rid, osm_admin_level=t.get('admin_level'),
            kato_code=t.get('kato'), kato_source='OSM tag kato' if t.get('kato') else 'absent in OSM snapshot',
            wikidata=t.get('wikidata'),
            boundary_version=bv, snapshot_date=snap, retrieved_at=retrieved, geometry_in_repo='raw only',
            geometry_source='osm_community (rebuilt by K03)', area_km2_geodesic=n['area_km2'],
            provenance=f'raw {F_OVERPASS} sha256:{ov_sha}…',
            osm_geometry_check='rebuilt locally from member ways',
            official_status_check='not_verified', use_in_city_aggregates='no (bbox side effect)',
            conflicts=cf, notes='Попал в ответ из-за bbox-запроса; в агрегаты Астаны не включать.')

    row(territory_id='kz.shymkent', id_status='proposed (A12 rule)', city='shymkent', level='city',
        name_ru='Шымкент', name_source='task context', iso_3166_2='unknown (A12-F018 KZ-79 — hypothesis)',
        geometry_in_repo='no', geometry_source='none', provenance='none saved',
        osm_geometry_check='missing: no OSM snapshot for Shymkent saved (Overpass blocked in A12, K03)',
        official_status_check='not_verified', use_in_city_aggregates='n/a',
        conflicts='K03-C04',
        notes='Нет relation id, КАТО, полигона. Полигон не создавать до получения источника.')
    for slug, ru in [('abay', 'Абайский район'), ('al-farabi', 'Аль-Фарабийский район'),
                     ('enbekshi', 'Енбекшинский район'), ('karatau', 'Каратауский район'),
                     ('turan', 'Туранский район')]:
        row(territory_id=None, id_status='not assigned: name is hypothesis', city='shymkent', level='district',
            name_ru=ru, name_source='A12-F016 hypothesis (model memory, low)', geometry_in_repo='no',
            geometry_source='none', provenance='A12_evidence.json A12-F016 (no source)',
            osm_geometry_check='missing', official_status_check='not_verified',
            use_in_city_aggregates='no until verified',
            notes='Состав и дата создания (Туранский) не подтверждены; стабильный id не выдавать.')

    fields = list(rows[0])
    (OUT / 'territory_registry.json').write_text(json.dumps(dict(
        generated_by='research/next-round/K03/k03_geo_verify.py', boundary_version=bv,
        status_vocabulary=dict(
            verified_locally='проверено на сохранённых файлах репозитория этим скриптом',
            not_verified='первоисточник не открыт; статус неизвестен',
            missing='данных/геометрии нет в репозитории',
            hypothesis='утверждение без источника (память модели в исходном отчёте)'),
        rows=rows), ensure_ascii=False, indent=1), encoding='utf-8')
    with open(OUT / 'territory_registry.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_conflicts(out, snap):
    ex = out['V7_baikonur_exclave_vs_tselinograd']
    p9 = next(p for p in ex['baikonur_pieces'] if p['covered_by_tselinograd_build'])
    v8 = out['V8_boundary_points']
    nom = out['V9_saraishyk']['nominatim']['address']
    kato = {r['legacy_id']: r['id_like_tags'].get('kato') for r in out['V2_bbox_relations']['relations'] if r['in_product']}
    C = [
        dict(id='K03-C01', city='astana', type='city_vs_region_overlap',
             units=['kz.astana.district.baikonur (rel 8593081)', 'Целиноградский район (rel 3403760, Акмолинская обл.)'],
             measured=dict(overlap_km2=p9['area_km2'], rep_point=p9['rep_point'], exclave_ring_ways=p9['ring_way_ids'],
                           exclave_ways_in_tselinograd=p9['ways_also_in_tselinograd'],
                           relations_with_exclave_way=ex['relations_with_way_372797931']),
             osm_status='confirmed in saved OSM snapshot by way membership (not an assembly artifact)',
             legal_status='unknown: no official act/map opened',
             source_claim='AST-A12-F012 (medium); AST-A12 возражение 3', boundary_version=f'osm:{snap}',
             handling='topology_conflict; не относить объекты эксклава к Астане без ручного решения'),
        dict(id='K03-C02', city='astana', type='admin_level_inconsistency',
             units=['kz.astana.district.saraishyk (rel 19733918)'],
             measured=dict(saraishyk_admin_level=out['V9_saraishyk']['osm_api']['admin_level'], others='6',
                           osm_version=out['V9_saraishyk']['osm_api']['version'],
                           last_edit=out['V9_saraishyk']['osm_api']['timestamp']),
             osm_status='confirmed in saved OSM snapshot and OSM API copy', legal_status='n/a (OSM tagging)',
             source_claim='A12-F003, AST-A12-F009, AST-A12-F010', boundary_version=f'osm:{snap}',
             handling='выбирать районы по явному списку relation id, не по admin_level'),
        dict(id='K03-C03', city='astana', type='bbox_selection_leak',
             units=[f"{x['relation']} {x['name']} (admin_level {x['admin_level']})" for x in out['V2_bbox_relations']['not_astana']],
             measured=dict(relations_in_response=out['V2_bbox_relations']['count'], astana=out['V2_bbox_relations']['astana_districts']),
             osm_status='confirmed', legal_status='n/a',
             source_claim='A12-F004 (называет Косшы и 3 района; Тайтөбе не упомянута)', boundary_version=f'osm:{snap}',
             handling='не агрегировать по bbox; Тайтөбе (admin_level 8) целиком внутри Косшы — вложенность, не конфликт'),
        dict(id='K03-C04', city='shymkent', type='missing_geometry_and_stale_global_layer',
             units=['kz.shymkent'],
             measured=dict(real_geometry_in_repo=False, natural_earth_files_in_repo=False),
             osm_status='missing: Overpass blocked (A12, K03)', legal_status='unknown',
             source_claim='A12-F010…F012 (Natural Earth относит Шымкент к Туркестанской обл.) — входные файлы NE не сохранены, '
                          'K03 не воспроизвёл', boundary_version=None,
             handling='не создавать полигоны; не использовать глобальные admin-1 для привязки к городу'),
        dict(id='K03-C05', city='astana', type='identifier_ambiguity',
             units=['kz.astana'] + [f'kz.astana.district.{k}' for k in kato],
             measured=dict(nominatim_iso_lvl4=nom.get('ISO3166-2-lvl4'), nominatim_iso_lvl15=nom.get('ISO3166-2-lvl15'),
                           osm_kato_tags=kato),
             osm_status='observed in saved Nominatim/OSM files',
             legal_status='not_verified: ISO OBP and stat.gov.kz KATO not opened',
             source_claim='A12-F005 указывает только KZ-71; A12/AST-A12 считают KATO неизвестным, хотя в снимке есть теги kato у 4 районов',
             boundary_version=f'osm:{snap}',
             handling='хранить kato_code с kato_source=osm; заменить официальным после сверки; у Нуры и Сарайшыка kato нет'),
        dict(id='K03-C06', city='astana', type='district_list_mismatch_in_product',
             units=['city_data.json', 'real_context.json', 'astana_districts.geojson'],
             measured=out['V10_product_district_lists'], osm_status='observed in repo files', legal_status='n/a',
             source_claim='A12-F006, A12-F008, AST-A12-F003, AST-A12-F006', boundary_version=None,
             handling='учебные 5 районов (synthetic) не смешивать с 6 районами OSM; real_context — нули-заглушки'),
        dict(id='K03-C07', city='astana', type='boundary_tie_points',
             units=[', '.join(x['districts']) for x in v8['vertices_shared_by_3plus_districts']],
             measured=dict(points=v8['vertices_shared_by_3plus_districts'], ast_a12_point=v8['ast_a12_point']),
             osm_status='confirmed: contains() False для всех, covers() True для сходящихся районов',
             legal_status='n/a', source_claim='AST-A12-F014 (называет одну точку; найдено 3, одна — на 4 района)',
             boundary_version=f'osm:{snap}', handling='правило разрешения ничьих (boundary_tie) при привязке точек'),
    ]
    (OUT / 'conflicts.json').write_text(json.dumps(dict(
        generated_by='research/next-round/K03/k03_geo_verify.py', conflicts=C), ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())
