"""K03 round 3, этап 1: реестр различий между источниками границ.

Источники (все локальные, сеть не используется):
  S1 product   — data/astana_districts.geojson; сырой Overpass osm_base 2026-09-22T08:45:51Z
  S2 overture  — K10 @ e91898d: Overture divisions 2026-09-23.1 (OSM relation@version внутри)
  S3 k03_epic  — next-round K03 этой ветки @ a8f1e17
  S4 k03_clever— next-round K03 clever-mccarthy @ c534321
  S5 a10       — коды районов КПСиСУ (импорт b87e5af)
Запуск из корня: python3 research/round-3-results/K03/compare_sources.py
Пишет source_comparison.json и source_comparison.csv рядом со скриптом.
"""
import csv
import json
from collections import defaultdict

from shapely.geometry import Polygon
from shapely.ops import unary_union

from geo_common import (ASTANA_REL, HERE, OVERTURE_RELEASE, P_A10, P_K03_CLEVER, P_K03_CLEVER_GEO,
                        P_K03_OWN, P_K10_E01, P_OV_AST, P_OV_SHY, P_OVERPASS, P_PRODUCT, P_SARA_NOM,
                        P_SARA_OSM, TSELINOGRAD, build_osm_relation, ghash, iou, km2, load,
                        overpass_relations, overture_layer, parts, product_layer, sha256)

DEG_M = 111_320  # м на градус широты; для Хаусдорфа даём порядок величины, не точное расстояние


def vertex_diff(a, b):
    import shapely
    ca = {tuple(c) for c in shapely.get_coordinates(a)}
    cb = {tuple(c) for c in shapely.get_coordinates(b)}
    return len(ca - cb), len(cb - ca)


def main():
    raw, rels = overpass_relations()
    snap = raw['osm3s']['timestamp_osm_base']
    retrieved = raw['_provenance']['retrieved_at']
    _, prod = product_layer()
    _, ov_ast = overture_layer(P_OV_AST)
    _, ov_shy = overture_layer(P_OV_SHY)
    sara = load(P_SARA_OSM)
    sara_rel = next(e for e in sara['elements'] if e['type'] == 'relation')
    sara_ways = {e['id']: e for e in sara['elements'] if e['type'] == 'way'}
    nom = load(P_SARA_NOM)[0]
    own = {r['osm_relation_id']: r for r in load(P_K03_OWN)['rows'] if r.get('osm_relation_id')}
    clever_rows = load(P_K03_CLEVER)['rows']
    clever = {r['osm_relation']: r for r in clever_rows if r.get('osm_relation')}
    e01 = load(P_K10_E01)

    out = dict(meta=dict(
        overture_release=OVERTURE_RELEASE, product_osm_base=snap, product_retrieved_at=retrieved,
        note=('Дата выпуска Overture (2026-09-23.1) — дата сборки выпуска; версии OSM внутри неё '
              'старше. osm_base продукта — состояние базы Overpass. update_time — время исходной записи OSM.'),
        inputs={p: sha256(p) for p in (P_PRODUCT, P_OVERPASS, P_SARA_OSM, P_SARA_NOM, P_A10, P_K03_OWN,
                                        P_OV_AST, P_OV_SHY, P_K10_E01, P_K03_CLEVER, P_K03_CLEVER_GEO)}))

    # --- Астана: районы
    ov_by_rel = {u['osm_relation']: u for u in ov_ast if u['props']['unit_kind'] == 'district'}
    rows = []
    for rid, slug in ASTANA_REL.items():
        pp, pg = prod[rid]
        t = rels[rid]['tags']
        o = ov_by_rel[rid]
        og = o['geom']
        same = ghash(pg) == ghash(og)
        only_p, only_o = vertex_diff(pg, og)
        row = dict(
            city='astana', unit=slug, osm_relation=rid,
            # S1 product / сырой OSM
            s1_osm_base=snap,
            s1_relation_version=(sara_rel['version'] if rid == 19733918 else None),
            s1_relation_version_note=('OSM API sara_osm.json' if rid == 19733918
                                      else 'не записана: Overpass out geom без meta'),
            s1_relation_timestamp=(sara_rel['timestamp'] if rid == 19733918 else None),
            s1_osm_admin_level=t.get('admin_level'),
            s1_name_ru=t.get('name:ru'), s1_name=t.get('name'), s1_name_kk=t.get('name:kk'),
            s1_product_name=pp['name'], s1_kato_tag=t.get('kato'), s1_wikidata=t.get('wikidata'),
            s1_geom_sha256=ghash(pg), s1_area_km2=round(km2(pg), 3), s1_parts=len(parts(pg)),
            # S2 Overture
            s2_release=OVERTURE_RELEASE,
            s2_osm_relation_version=o['osm_relation_version'],
            s2_osm_source_update_time=o['osm_source_update_time'],
            s2_overture_subtype=o['props']['overture_subtype'],
            s2_overture_admin_level=o['props']['admin_level'],
            s2_overture_version=o['props']['overture_version'],
            s2_division_id=o['props']['overture_division_id'],
            s2_name_primary=o['props']['name_primary'],
            s2_name_common_ru=(o['props'].get('names_common') or {}).get('ru'),
            s2_geom_sha256=ghash(og), s2_area_km2=round(km2(og), 3),
            # Сравнение S1/S2
            geom_identical=same, iou=round(iou(pg, og), 7),
            symdiff_m2=round(km2(pg.symmetric_difference(og)) * 1e6, 2),
            hausdorff_m_approx=round(pg.hausdorff_distance(og) * DEG_M, 2),
            vertices_only_s1=only_p, vertices_only_s2=only_o,
            # S3 / S4
            s3_k03_epic_area_km2=own[rid]['area_km2_geodesic'], s3_kato=own[rid].get('kato_code'),
            s4_k03_clever_area_km2=clever[rid]['area_km2_geodesic'], s4_kato=clever[rid].get('kato'),
            official_status='not_verified')
        rows.append(row)
    out['astana_districts'] = rows

    # Причина расхождения Алматы/Сарайшык: путь общей границы в changeset 189349743
    diff_ways = []
    for rid in (3482819, 19733918):
        pg, og = prod[rid][1], ov_by_rel[rid]['geom']
        if ghash(pg) != ghash(og):
            import shapely
            extra = {tuple(c) for c in shapely.get_coordinates(pg)} - {tuple(c) for c in shapely.get_coordinates(og)}
            ways = sorted({m['ref'] for e in rels.values() for m in e['members'] if m['type'] == 'way'
                           and any((q['lon'], q['lat']) in extra for q in m.get('geometry', []))})
            diff_ways.append(dict(relation=rid, vertices_only_in_product=len(extra), ways=ways,
                                  ways_meta=[dict(way=w, version=sara_ways[w]['version'],
                                                  timestamp=sara_ways[w]['timestamp'],
                                                  changeset=sara_ways[w]['changeset'])
                                             for w in ways if w in sara_ways]))
    out['astana_geometry_difference_cause'] = diff_ways

    # --- Сарайшык: уровни в разных источниках
    sar = next(r for r in rows if r['unit'] == 'saraishyk')
    out['saraishyk_levels'] = dict(
        osm_admin_level_overpass=sar['s1_osm_admin_level'],
        osm_admin_level_api_v17=sara_rel['tags'].get('admin_level'),
        other_astana_districts_osm_admin_level=sorted({r['s1_osm_admin_level'] for r in rows if r['unit'] != 'saraishyk'}),
        overture_subtype=sar['s2_overture_subtype'], overture_admin_level=sar['s2_overture_admin_level'],
        other_astana_districts_overture=sorted({(r['s2_overture_subtype'], r['s2_overture_admin_level'])
                                                for r in rows if r['unit'] != 'saraishyk'}),
        nominatim=dict(addresstype=nom.get('addresstype'), place_rank=nom.get('place_rank')),
        product_city_data='отсутствует (5 учебных районов)',
        versions=dict(product=f"r19733918@{sara_rel['version']} ({sara_rel['timestamp']})",
                      overture=f"r19733918@{sar['s2_osm_relation_version']} ({sar['s2_osm_source_update_time']})"),
        conclusion='три разных представления уровня; выбирать по явному списку relation id, не по уровню/подтипу')

    # --- Астана: город, непокрытая площадь, эксклав
    city = next(u for u in ov_ast if u['props']['unit_kind'] == 'city')
    ov_union = unary_union([u['geom'] for u in ov_by_rel.values()])
    uncovered = city['geom'].difference(ov_union)
    tsel, tsel_inners = build_osm_relation(rels[TSELINOGRAD])
    inner = max(tsel_inners, key=lambda p: p.area)
    exclave = prod[8593081][1].intersection(tsel)
    out['astana_city'] = dict(
        overture_city=dict(osm=f"r{city['osm_relation']}@{city['osm_relation_version']}",
                           update_time=city['osm_source_update_time'], area_km2=round(km2(city['geom']), 3),
                           geom_sha256=ghash(city['geom']), parts=len(parts(city['geom']))),
        product_city_relation='нет: запрос Overpass брал admin_level 5–9',
        districts_union_km2=round(km2(ov_union), 3),
        districts_outside_city_km2=round(km2(ov_union.difference(city['geom'])), 6),
        uncovered=dict(area_km2=round(km2(uncovered), 3), parts=[round(km2(p), 3) for p in parts(uncovered)],
                       rep_point=[round(c, 5) for c in uncovered.representative_point().coords[0]],
                       geom_sha256=ghash(uncovered),
                       vs_tselinograd_inner_ring_from_product_snapshot=dict(
                           inner_ring_km2=round(km2(inner), 3), iou=round(iou(uncovered, inner), 6),
                           note='дыра Целиноградского района (Overpass 2026-09-22) и непокрытая часть города (Overture r3087155@64) — одна территория')),
        exclave_overlap=dict(area_km2=round(km2(exclave), 3), geom_sha256=ghash(exclave),
                             inside_overture_city_polygon=round(km2(exclave.intersection(city['geom'])) / km2(exclave), 6),
                             note='эксклав Байконура входит в полигон города (Overture) и в Целиноградский район (Overpass); версии разные'))

    # --- Шымкент
    shy_city = next(u for u in ov_shy if u['props']['unit_kind'] == 'city')
    shy_d = [u for u in ov_shy if u['props']['unit_kind'] == 'district']
    su = unary_union([u['geom'] for u in shy_d])
    ov_pairs = {}
    for i, a in enumerate(shy_d):
        for b in shy_d[i + 1:]:
            x = a['geom'].intersection(b['geom'])
            if not x.is_empty and x.area > 0:
                ov_pairs[f"{a['props']['name_primary']}|{b['props']['name_primary']}"] = round(km2(x) * 1e6, 3)
    a10 = load(P_A10)
    years = defaultdict(list)
    for code, yr, _ in a10['queries']['shymkent_by_district_year']['rows']:
        years[str(code)].append(yr)
    a12_hyp = ['Абайский район', 'Аль-Фарабийский район', 'Енбекшинский район', 'Каратауский район', 'Туранский район']
    ru_common = {(u['props'].get('names_common') or {}).get('ru'): u for u in shy_d}
    out['shymkent'] = dict(
        overture_city=dict(osm=f"r{shy_city['osm_relation']}@{shy_city['osm_relation_version']}",
                           update_time=shy_city['osm_source_update_time'], area_km2=round(km2(shy_city['geom']), 3),
                           geom_sha256=ghash(shy_city['geom'])),
        overture_districts=[dict(osm=f"r{u['osm_relation']}@{u['osm_relation_version']}",
                                 update_time=u['osm_source_update_time'], name_primary=u['props']['name_primary'],
                                 name_common_ru=(u['props'].get('names_common') or {}).get('ru'),
                                 subtype=u['props']['overture_subtype'], area_km2=round(km2(u['geom']), 3),
                                 geom_sha256=ghash(u['geom']), valid=u['geom'].is_valid) for u in shy_d],
        district_polygon_count=len(shy_d),
        districts_union_km2=round(km2(su), 3),
        city_not_covered_km2=round(km2(shy_city['geom'].difference(su)), 6),
        districts_outside_city_km2=round(km2(su.difference(shy_city['geom'])), 6),
        pairwise_overlaps_m2=ov_pairs,
        a12_hypothesis_names_vs_overture=[dict(a12_name=n, overture_match=(f"r{ru_common[n]['osm_relation']}"
                                                                           if n in ru_common else None)) for n in a12_hyp],
        turan=dict(k10_claim='в STATUS K10: «Тұран есть только как macrohood»',
                   saved_record=False,
                   check='в samples/results K10 @ e91898d нет записи или геометрии Тұран; утверждение не проверяемо по репозиторию'),
        kpssu_codes=dict(source=P_A10, codes={c: [min(y), max(y)] for c, y in sorted(years.items())},
                         note='5 кодов при 4 полигонах; справочника кодов нет; код→район не сопоставлен'),
        k03_epic='5 названий районов как гипотеза A12-F016, без геометрии',
        k03_clever='город (код 1979) + 5 кодов КПСиСУ, без геометрии и названий',
        k10_e01=dict(coverage=e01['shymkent']['city_area_covered_by_districts_share'],
                     not_covered_km2=e01['shymkent']['city_area_not_covered_km2']))

    # --- Сверка двух next-round K03 между собой
    agree = []
    for rid in ASTANA_REL:
        agree.append(dict(osm_relation=rid, area_epic=own[rid]['area_km2_geodesic'],
                          area_clever=clever[rid]['area_km2_geodesic'],
                          area_equal_0_01=abs(own[rid]['area_km2_geodesic'] - clever[rid]['area_km2_geodesic']) < 0.01,
                          kato_equal=(own[rid].get('kato_code') or None) == (clever[rid].get('kato') or None)))
    out['k03_versions_agreement'] = dict(
        astana_districts=agree,
        only_in_epic=['ISO KZ-AST (lvl15) рядом с KZ-71 в Nominatim', 'проверка эксклава по составу путей',
                      '3 вершины на стыке ≥3 районов', 'дыра Целиноградского района 11,034 км²'],
        only_in_clever=['коды КПСиСУ 1979 / 197910–197914 из A10', 'IoU продукт/сырой OSM'],
        shymkent_rows=dict(epic='город + 5 гипотетических названий', clever='город + 5 кодов'),
        iso_from_k10='pycountry 26.2.16: KZ-71 Astana, KZ-79 Shymkent (вторичная копия ISO; KZ-AST там нет)')

    (HERE / 'source_comparison.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    cols = ['city', 'unit', 'osm_relation', 's1_relation_version', 's1_osm_admin_level', 's1_kato_tag',
            's2_osm_relation_version', 's2_osm_source_update_time', 's2_overture_subtype', 's2_overture_admin_level',
            's1_geom_sha256', 's2_geom_sha256', 'geom_identical', 'iou', 'symdiff_m2', 'hausdorff_m_approx',
            's1_area_km2', 's2_area_km2', 's3_k03_epic_area_km2', 's4_k03_clever_area_km2',
            's1_name_ru', 's2_name_primary', 'official_status']
    flat = [{c: r[c] for c in cols} for r in rows]
    for u in out['shymkent']['overture_districts']:
        flat.append(dict({c: None for c in cols}, city='shymkent', unit=u['name_common_ru'],
                         osm_relation=u['osm'].split('@')[0][1:], s2_osm_relation_version=u['osm'].split('@')[1],
                         s2_osm_source_update_time=u['update_time'], s2_overture_subtype=u['subtype'],
                         s2_geom_sha256=u['geom_sha256'], s2_area_km2=u['area_km2'], s2_name_primary=u['name_primary'],
                         official_status='not_verified'))
    with open(HERE / 'source_comparison.csv', 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(flat)
    print(json.dumps(dict(astana_identical={r['unit']: r['geom_identical'] for r in rows},
                          uncovered_km2=out['astana_city']['uncovered']['area_km2'],
                          uncovered_vs_tsel_inner_iou=out['astana_city']['uncovered']['vs_tselinograd_inner_ring_from_product_snapshot']['iou'],
                          exclave_in_city=out['astana_city']['exclave_overlap']['inside_overture_city_polygon'],
                          shymkent_polygons=out['shymkent']['district_polygon_count'],
                          shymkent_not_covered_km2=out['shymkent']['city_not_covered_km2']), ensure_ascii=False))


if __name__ == '__main__':
    main()
