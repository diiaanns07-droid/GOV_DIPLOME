"""K03 round 3, этап 2: read-only валидатор границ и итоговый boundary_registry.json.

Ничего не меняет во входах и в продукте. Сеть не используется.

  python3 research/round-3-results/K03/boundary_validator.py
      собрать boundary_registry.json, ambiguity_zones.geojson, validator_selftest.json
      (пишет только в свою папку) и выполнить самопроверку; код выхода 1 при провале.
  python3 research/round-3-results/K03/boundary_validator.py --point LON LAT
      привязать одну точку, напечатать JSON, ничего не записывать.

Правило k03_assign_v1 возвращает один из статусов:
  matched    — ровно один район, точка дальше TOL_M от любой его границы, слои не расходятся;
  ambiguous  — общая граница / ближе TOL_M к границе / зона конфликта город–область /
               разные ответы двух версий слоя (Астана);
  unmatched  — внутри полигона города, но ни в одном районе;
  outside    — вне известных полигонов обоих городов;
  invalid    — координаты вне диапазона Казахстана или перепутаны lon/lat.
Произвольный район при конфликте не выбирается.
"""
import argparse
import json
import sys

import shapely
from pyproj import Transformer
from shapely.geometry import Point, mapping
from shapely.ops import transform, unary_union

from geo_common import (ASTANA_REL, HERE, OVERTURE_RELEASE, P_K10_E01, P_OV_AST, P_OV_SHY,
                        P_OVERPASS, P_PRODUCT, P_SARA_OSM, TSELINOGRAD, build_osm_relation,
                        ghash, km2, load, overpass_relations, overture_layer, product_layer, sha256)

TOL_M = 1.0  # > 0,44 м — наибольшее измеренное расхождение версий (Алматы/Сарайшык); параметр, не норматив
KZ_LON, KZ_LAT = (46.5, 87.5), (40.5, 55.5)
UTM = Transformer.from_crs('EPSG:4326', 'EPSG:32642', always_xy=True).transform
SHY_SLUG = {5548210: 'abay', 5550509: 'al-farabi', 5551117: 'enbekshi', 5551119: 'karatau'}


def proj(g):
    return transform(UTM, g)


def polygonal(g):
    """Только площадные части: пересечения и разности могут дать линии/точки на общих границах."""
    polys = [q for q in shapely.get_parts(g) if q.geom_type in ('Polygon', 'MultiPolygon') and q.area > 0]
    return unary_union(polys)


class Layers:
    """Загружает слои один раз; все геометрии дублируются в UTM 42N для метрических допусков."""

    def __init__(self):
        raw, rels = overpass_relations()
        self.snap = raw['osm3s']['timestamp_osm_base']
        self.rels = rels
        _, prod = product_layer()
        _, ov_ast = overture_layer(P_OV_AST)
        _, ov_shy = overture_layer(P_OV_SHY)
        self.sara = next(e for e in load(P_SARA_OSM)['elements'] if e['type'] == 'relation')
        self.ast_prod = {f'kz.astana.district.{s}': prod[r][1] for r, s in ASTANA_REL.items()}
        self.ast_ov = {f'kz.astana.district.{ASTANA_REL[u["osm_relation"]]}': u['geom']
                       for u in ov_ast if u['props']['unit_kind'] == 'district'}
        self.ov_ast_units = {u['osm_relation']: u for u in ov_ast}
        self.ov_shy_units = {u['osm_relation']: u for u in ov_shy}
        self.ast_city = next(u['geom'] for u in ov_ast if u['props']['unit_kind'] == 'city')
        self.shy_city = next(u['geom'] for u in ov_shy if u['props']['unit_kind'] == 'city')
        self.shy = {f'kz.shymkent.district.{SHY_SLUG[u["osm_relation"]]}': u['geom']
                    for u in ov_shy if u['props']['unit_kind'] == 'district'}
        tsel, _ = build_osm_relation(rels[TSELINOGRAD])
        self.zones = {
            'AST-Z1': dict(geom=self.ast_prod['kz.astana.district.baikonur'].intersection(tsel), status='ambiguous',
                           reason='city_vs_region_overlap',
                           candidates=['kz.astana.district.baikonur', f'osm:relation/{TSELINOGRAD} (Целиноградский район, Акмолинская обл.)']),
            'AST-Z2': dict(geom=self.ast_city.difference(unary_union(list(self.ast_ov.values()))), status='unmatched',
                           reason='inside_city_no_district', candidates=[]),
            'AST-Z3': dict(geom=unary_union([self.ast_prod[k].symmetric_difference(self.ast_ov[k])
                                             for k in self.ast_prod]), status='ambiguous',
                           reason='version_disagreement',
                           candidates=['kz.astana.district.almaty', 'kz.astana.district.saraishyk']),
        }
        for z in self.zones.values():
            z['geom'] = polygonal(z['geom'])
        self.P = {k: {u: proj(g) for u, g in d.items()} for k, d in
                  (('ast_prod', self.ast_prod), ('ast_ov', self.ast_ov), ('shy', self.shy))}
        self.Pcity = {'astana': proj(self.ast_city), 'shymkent': proj(self.shy_city)}
        self.Pzones = {z: proj(v['geom']) for z, v in self.zones.items()}


def _district_hits(pp, layer):
    hits, near = [], []
    for uid, g in layer.items():
        d = g.boundary.distance(pp)
        if g.covers(pp):
            hits.append(uid)
        if d <= TOL_M:
            near.append((uid, round(d, 3)))
    return sorted(hits), sorted(near)


def assign(L, lon, lat):
    res = dict(rule='k03_assign_v1', tol_m=TOL_M, point=[lon, lat])
    if not (KZ_LON[0] <= lon <= KZ_LON[1] and KZ_LAT[0] <= lat <= KZ_LAT[1]):
        swapped = KZ_LON[0] <= lat <= KZ_LON[1] and KZ_LAT[0] <= lon <= KZ_LAT[1]
        return dict(res, status='invalid', reason='lon_lat_swapped' if swapped else 'outside_kazakhstan_range')
    pp = proj(Point(lon, lat))
    city = next((c for c, g in L.Pcity.items() if g.covers(pp) or g.boundary.distance(pp) <= TOL_M), None)
    if city is None:
        return dict(res, status='outside', reason='outside_known_city_polygons', city=None)
    res['city'] = city
    if L.Pcity[city].boundary.distance(pp) <= TOL_M:
        res['city_edge'] = True
    for z, zg in L.Pzones.items():
        if z.startswith('AST') and city == 'astana' and (zg.covers(pp) or zg.boundary.distance(pp) <= TOL_M):
            meta = L.zones[z]
            if meta['reason'] == 'version_disagreement' and not zg.covers(pp):
                continue  # близость к этой зоне проверяется ниже обычным допуском к границам
            return dict(res, status=meta['status'], reason=meta['reason'], zone=z, district=None,
                        candidates=meta['candidates'])
    layers = {'astana': [('osm_snapshot', L.P['ast_prod']), ('overture', L.P['ast_ov'])],
              'shymkent': [('overture', L.P['shy'])]}[city]
    per = {}
    for name, lay in layers:
        hits, near = _district_hits(pp, lay)
        per[name] = dict(covers=hits, within_tol=near)
    res['layers'] = per
    first = per[layers[0][0]]
    if len({tuple(v['covers']) for v in per.values()}) > 1:
        return dict(res, status='ambiguous', reason='version_disagreement', district=None,
                    candidates=sorted({u for v in per.values() for u in v['covers']}))
    if not first['covers']:
        return dict(res, status='ambiguous' if first['within_tol'] else 'unmatched',
                    reason='near_district_boundary' if first['within_tol'] else 'inside_city_no_district',
                    district=None, candidates=[u for u, _ in first['within_tol']])
    if len(first['covers']) > 1 or first['within_tol'] or res.get('city_edge'):
        return dict(res, status='ambiguous',
                    reason='boundary_tie' if len(first['covers']) > 1 else 'near_district_boundary',
                    district=None, candidates=sorted(set(first['covers']) | {u for u, _ in first['within_tol']}))
    return dict(res, status='matched', reason='single_district_interior', district=first['covers'][0],
                candidates=first['covers'])


def selftest(L):
    cases = []
    for uid, g in list(L.ast_prod.items()) + list(L.shy.items()):
        rp = g.representative_point()
        cases.append((f'interior {uid}', rp.x, rp.y, 'matched', uid))
    cases += [
        ('AST-A12 tri-point Almaty/Esil/Saraishyk', 71.447389, 51.1311552, 'ambiguous', None),
        ('4-district vertex Baikonur/Esil/Nura/Saryarka', 71.428229, 51.1518972, 'ambiguous', None),
        ('Baikonur exclave ∩ Tselinograd (AST-A12-F012)', 71.66574, 51.33028, 'ambiguous', None),
        ('uncovered city area (K10 E01)', *L.zones['AST-Z2']['geom'].representative_point().coords[0], 'unmatched', None),
        ('Almaty/Saraishyk version-difference sliver', *L.zones['AST-Z3']['geom'].representative_point().coords[0], 'ambiguous', None),
        ('outside both cities', 70.0, 45.0, 'outside', None),
        ('swapped lon/lat', 51.1311552, 71.447389, 'invalid', None),
    ]
    # Шымкент: общая вершина двух районов и точка в 5 м от неё внутри района
    a, b = 'kz.shymkent.district.abay', 'kz.shymkent.district.al-farabi'
    shared = L.shy[a].boundary.intersection(L.shy[b].boundary)
    v = shapely.get_coordinates(shared)[0]
    cases.append(('Shymkent shared vertex Abay/Al-Farabi', float(v[0]), float(v[1]), 'ambiguous', None))
    pv = proj(Point(*v))
    inner = L.P['shy'][a]
    toward = inner.representative_point()
    dx, dy = toward.x - pv.x, toward.y - pv.y
    n = (dx * dx + dy * dy) ** 0.5
    for step in (5, 10, 20, 40):
        cand = Point(pv.x + dx / n * step, pv.y + dy / n * step)
        if inner.contains(cand) and inner.boundary.distance(cand) > TOL_M:
            inv = Transformer.from_crs('EPSG:32642', 'EPSG:4326', always_xy=True).transform(cand.x, cand.y)
            cases.append((f'Shymkent {step} m inside Abay from shared vertex', inv[0], inv[1], 'matched', a))
            break
    out, ok = [], True
    for name, lon, lat, exp, exp_d in cases:
        r = assign(L, lon, lat)
        passed = r['status'] == exp and (exp_d is None or r.get('district') == exp_d)
        ok &= passed
        out.append(dict(case=name, point=[round(lon, 7), round(lat, 7)], expected=exp, expected_district=exp_d,
                        got=r['status'], district=r.get('district'), reason=r.get('reason'),
                        candidates=r.get('candidates'), passed=passed))
    return ok, out


def build_registry(L, tests_ok, tests):
    sc = load('research/round-3-results/K03/source_comparison.json')
    man = load('research/round-3-results/K03/inputs/MANIFEST.json')
    rows = {r['unit']: r for r in sc['astana_districts']}
    units = []
    for rid, slug in ASTANA_REL.items():
        r = rows[slug]
        ou = L.ov_ast_units[rid]
        units.append(dict(
            unit_id=f'kz.astana.district.{slug}', id_status='proposed (A12 rule)', city='kz.astana', level='district',
            legacy_id=slug, osm_relation=rid,
            names=dict(ru=dict(value=r['s1_name_ru'], source='OSM name:ru'),
                       kk=dict(value=r['s1_name_kk'] or r['s1_name'],
                               source='OSM name:kk' if r['s1_name_kk'] else 'OSM name (name:kk нет)'),
                       product=dict(value=r['s1_product_name'], source=P_PRODUCT)),
            kato=dict(value=r['s1_kato_tag'], source='OSM tag kato (community)' if r['s1_kato_tag'] else None,
                      official='not_verified'),
            wikidata=r['s1_wikidata'],
            level_by_source=dict(osm_admin_level=r['s1_osm_admin_level'],
                                 overture=f"{r['s2_overture_subtype']}/{r['s2_overture_admin_level']}"),
            versions=[
                dict(layer_id='astana.osm_snapshot', osm_relation_version=r['s1_relation_version'],
                     version_note=r['s1_relation_version_note'], object_time=r['s1_relation_timestamp'],
                     dataset_time=L.snap, dataset_time_kind='overpass osm_base',
                     geom_sha256=r['s1_geom_sha256'], area_km2=r['s1_area_km2']),
                dict(layer_id='astana.overture_2026-09-23.1', osm_relation_version=r['s2_osm_relation_version'],
                     object_time=r['s2_osm_source_update_time'], object_time_kind='overture sources[].update_time',
                     dataset_time=OVERTURE_RELEASE, dataset_time_kind='overture release',
                     overture_division_id=ou['props']['overture_division_id'],
                     overture_version=ou['props']['overture_version'],
                     geom_sha256=r['s2_geom_sha256'], area_km2=r['s2_area_km2'])],
            cross_source=dict(geom_identical=r['geom_identical'], iou=r['iou'], symdiff_m2=r['symdiff_m2'],
                              hausdorff_m_approx=r['hausdorff_m_approx']),
            research_view=dict(layer_id='astana.osm_snapshot', include_in_city_aggregates=True),
            legal_status='not_verified'))
    for rid, slug in SHY_SLUG.items():
        u = L.ov_shy_units[rid]
        p = u['props']
        units.append(dict(
            unit_id=f'kz.shymkent.district.{slug}', id_status='proposed (A12 rule)', city='kz.shymkent', level='district',
            legacy_id=None, osm_relation=rid,
            names=dict(ru=dict(value=(p.get('names_common') or {}).get('ru'), source='Overture names.common.ru'),
                       kk=dict(value=p['name_primary'], source='Overture names.primary')),
            kato=dict(value=None, source=None, official='not_verified'), wikidata=None,
            level_by_source=dict(overture=f"{p['overture_subtype']}/{p['admin_level']}", osm_admin_level=None),
            versions=[dict(layer_id='shymkent.overture_2026-09-23.1', osm_relation_version=u['osm_relation_version'],
                           object_time=u['osm_source_update_time'], object_time_kind='overture sources[].update_time',
                           dataset_time=OVERTURE_RELEASE, dataset_time_kind='overture release',
                           overture_division_id=p['overture_division_id'], overture_version=p['overture_version'],
                           geom_sha256=ghash(u['geom']), area_km2=round(km2(u['geom']), 3))],
            cross_source=dict(geom_identical=None, note='второго источника геометрии нет'),
            research_view=dict(layer_id='shymkent.overture_2026-09-23.1', include_in_city_aggregates=True),
            legal_status='not_verified'))
    ac, sh = sc['astana_city'], sc['shymkent']
    cities = [
        dict(city_id='kz.astana', iso_3166_2='KZ-71',
             iso_source='pycountry 26.2.16 / Debian iso-codes (вторичная копия ISO); Nominatim также даёт KZ-AST на lvl15',
             outline=dict(layer_id='astana.overture_2026-09-23.1', osm=ac['overture_city']['osm'],
                          object_time=ac['overture_city']['update_time'], area_km2=ac['overture_city']['area_km2'],
                          parts=ac['overture_city']['parts'], geom_sha256=ac['overture_city']['geom_sha256']),
             districts_union_km2=ac['districts_union_km2'], uncovered_km2=ac['uncovered']['area_km2'],
             mixed_versions='контур города r3087155@64 (2026-06-01) старше границ районов в снимке 2026-09-22',
             legal_status='not_verified'),
        dict(city_id='kz.shymkent', iso_3166_2='KZ-79', iso_source='pycountry 26.2.16 / Debian iso-codes (вторичная копия ISO)',
             outline=dict(layer_id='shymkent.overture_2026-09-23.1', osm=sh['overture_city']['osm'],
                          object_time=sh['overture_city']['update_time'], area_km2=sh['overture_city']['area_km2'],
                          geom_sha256=sh['overture_city']['geom_sha256']),
             districts_union_km2=sh['districts_union_km2'], uncovered_km2=sh['city_not_covered_km2'],
             district_polygons=sh['district_polygon_count'], legal_status='not_verified')]
    zones = [dict(zone_id=z, city='kz.astana', type=v['reason'], assign_status=v['status'],
                  area_km2=round(km2(v['geom']), 3) if v['reason'] != 'version_disagreement' else None,
                  area_m2=round(km2(v['geom']) * 1e6, 2) if v['reason'] == 'version_disagreement' else None,
                  rep_point=[round(c, 6) for c in v['geom'].representative_point().coords[0]],
                  geom_sha256=ghash(v['geom']), candidates=v['candidates'], kind='derived', legal_status='not_verified')
             for z, v in L.zones.items()]
    unresolved = [
        dict(id='U1', city='kz.shymkent', question='Существует ли официально пятый (Туранский) район и где его граница?',
             evidence=['4 полигона county покрывают 100% города (Overture 2026-09-23.1)',
                       'A12-F016: 5 районов (гипотеза, память модели)',
                       'K10 STATUS: «Тұран только macrohood» — записи в сохранённых файлах нет',
                       'A10: 5 кодов КПСиСУ, 197914 только с 2023'],
             needed='акт о районах Шымкента (adilet.zan.kz) и КАТО (stat.gov.kz); свежий OSM/Overture с macrohood',
             rule='в реестре нет единицы и ID для Туранского района; полигон не рисуется'),
        dict(id='U2', city='kz.shymkent', question='Соответствие кодов КПСиСУ 197910–197914 районам',
             evidence=[sh['kpssu_codes']], needed='справочник кодов КПСиСУ или КАТО', rule='код→район не присваивается'),
        dict(id='U3', city='kz.astana', question='Юридическая принадлежность эксклава Байконура 9,021 км²',
             evidence=['OSM: путь 372797931 только в rel 8593081; в rel 3403760 его нет', 'Overture: целиком в полигоне города'],
             needed='акт/карта границ города', rule='AST-Z1 → ambiguous'),
        dict(id='U4', city='kz.astana', question='Чья территория 11,034 км² внутри контура города вне районов',
             evidence=['= внутреннее кольцо Целиноградского района (IoU 1,0)'], needed='акт о районах Астаны',
             rule='AST-Z2 → unmatched'),
        dict(id='U5', city='both', question='Официальный состав районов, названия, КАТО',
             evidence=['теги OSM kato у 4 районов Астаны; у Шымкента нет'], needed='stat.gov.kz, adilet.zan.kz',
             rule='kato.official = not_verified'),
        dict(id='U6', city='kz.astana', question='Что изменила правка Сарайшыка v16→v17 кроме пути 903345831',
             evidence=['changeset 189349743, 2026-09-21; версии путей в sara_osm.json'], needed='история OSM (api.openstreetmap.org)',
             rule='хранить обе версии с hash'),
    ]
    rules = [
        dict(id='L1', rule='Единицы выбирать только по явному списку (источник, relation id). Не по bbox, admin_level или подтипу Overture.',
             why='bbox даёт 5 чужих отношений; у Сарайшыка admin_level 8 / locality'),
        dict(id='L2', rule='Астана, районы: исследовательский просмотр — снимок OSM продукта (osm_base 2026-09-22T08:45:51Z). Overture 2026-09-23.1 — контрольный слой.',
             why='снимок новее по общей границе Алматы/Сарайшык (путь 903345831 v12); 4/6 районов побайтно совпадают'),
        dict(id='L3', rule='Астана, контур города — только Overture r3087155@64; использовать лишь для различия unmatched/outside. Отмечать mixed_versions.',
             why='в снимке продукта нет отношения города'),
        dict(id='L4', rule='Шымкент — только Overture 2026-09-23.1: город + 4 района county. Подпись: «OSM через Overture, не официально; Туранский район и код 197914 не разрешены».',
             why='единственная сохранённая геометрия Шымкента'),
        dict(id='L5', rule='Natural Earth, geoBoundaries (2017) и другие глобальные admin-слои не использовать для привязки к городу/району; только как отрицательный контроль.',
             why='A12-F010…F012, K10-D03'),
        dict(id='L6', rule='Учебные районы city_data.json (5, synthetic) не соединять с реальными геометриями и метриками без явной метки synthetic.',
             why='Сарайшыка нет в учебной модели'),
        dict(id='L7', rule='Каждое наблюдение хранит layer_id, версию relation/выпуск и geom_sha256; при смене hash — новая версия, а не перезапись.',
             why='одинаковый номер версии relation не гарантирует одинаковую геометрию (Алматы @46)'),
        dict(id='L8', rule='Точки привязывать правилом k03_assign_v1; ambiguous/unmatched не превращать в район и не отбрасывать молча — показывать отдельной строкой.',
             why='конфликтные зоны AST-Z1…Z3 и общие границы'),
        dict(id='L9', rule='Все юридические статусы not_verified, пока акты/КАТО не открыты. Недостающие официальные границы не рисуются.',
             why='официальные источники заблокированы политикой сети'),
    ]
    reg = dict(
        registry_id='K03-round3-boundary-registry', registry_version=1,
        generated_by='research/round-3-results/K03/boundary_validator.py',
        inputs=dict(local={p: sha256(p) for p in (P_PRODUCT, P_OVERPASS, P_SARA_OSM, P_OV_AST, P_OV_SHY, P_K10_E01)},
                    copied_from_other_branches=[dict(local_path=f['local_path'], source_commit=f['source_commit'],
                                                     source_path=f['source_path'], git_blob=f['git_blob'])
                                                for f in man['files']]),
        vocabulary=dict(
            legal_status={'not_verified': 'официальный акт/классификатор не открыт'},
            kind={'observed_community': 'OSM/Overture — наблюдение данных сообщества', 'derived': 'вычислено K03 из имеющихся геометрий'},
            time={'dataset_time': 'время выпуска/снимка набора', 'object_time': 'время версии исходного объекта OSM'},
            assign_status=['matched', 'ambiguous', 'unmatched', 'outside', 'invalid']),
        layers=[
            dict(layer_id='astana.osm_snapshot', city='kz.astana', role='research_view_districts', file=P_PRODUCT,
                 raw=P_OVERPASS, dataset_time=L.snap, retrieved_at='2026-09-23T11:28:06+00:00',
                 license='ODbL-1.0 (© OpenStreetMap contributors)', units=6, has_city_outline=False),
            dict(layer_id='astana.overture_2026-09-23.1', city='kz.astana', role='cross_check_districts + city_outline',
                 file='research/round-3-results/K03/inputs/K10/astana_districts_overture.geojson',
                 origin='K10 @ e91898d', dataset_time=OVERTURE_RELEASE,
                 release_published_note='S3 LastModified 2026-09-25 по K10 datasets.json; K03 не перепроверял',
                 license='ODbL-1.0 (OSM via Overture)', units=6,
                 has_city_outline=True),
            dict(layer_id='shymkent.overture_2026-09-23.1', city='kz.shymkent', role='research_view_districts + city_outline',
                 file='research/round-3-results/K03/inputs/K10/shymkent_districts_overture.geojson',
                 origin='K10 @ e91898d', dataset_time=OVERTURE_RELEASE,
                 release_published_note='S3 LastModified 2026-09-25 по K10 datasets.json; K03 не перепроверял',
                 license='ODbL-1.0 (OSM via Overture)', units=4,
                 has_city_outline=True)],
        cities=cities, units=units, zones=zones, unresolved=unresolved, layer_selection_rules=rules,
        assignment_rule=dict(id='k03_assign_v1', tol_m=TOL_M, metric_crs='EPSG:32642',
                             order=['invalid: вне диапазона KZ или lon/lat перепутаны',
                                    'outside: вне контуров обоих городов (с допуском tol_m)',
                                    'zone AST-Z1/Z2/Z3 → ambiguous/unmatched/ambiguous',
                                    'Астана: разные ответы снимка OSM и Overture → ambiguous (version_disagreement)',
                                    'нет района: ближе tol_m к границе → ambiguous, иначе unmatched',
                                    '≥2 района или ближе tol_m к границе или край города → ambiguous',
                                    'иначе matched'],
                             tol_note='tol_m=1 м > 0,44 м наибольшего измеренного расхождения версий; это параметр исследования, не норматив'),
        selftest=dict(passed=tests_ok, cases=len(tests), failed=[t['case'] for t in tests if not t['passed']]))
    return reg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--point', nargs=2, type=float, metavar=('LON', 'LAT'))
    a = ap.parse_args()
    L = Layers()
    if a.point:
        print(json.dumps(assign(L, *a.point), ensure_ascii=False, indent=1))
        return 0
    ok, tests = selftest(L)
    (HERE / 'validator_selftest.json').write_text(json.dumps(dict(rule='k03_assign_v1', passed=ok, cases=tests),
                                                             ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    reg = build_registry(L, ok, tests)
    (HERE / 'boundary_registry.json').write_text(json.dumps(reg, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    feats = [dict(type='Feature', properties=dict(zone_id=z['zone_id'], type=z['type'], assign_status=z['assign_status'],
                                                  kind='derived', legal_status='not_verified', candidates=z['candidates']),
                  geometry=mapping(L.zones[z['zone_id']]['geom'])) for z in reg['zones']]
    (HERE / 'ambiguity_zones.geojson').write_text(json.dumps(dict(
        type='FeatureCollection', name='K03 derived ambiguity zones (not official boundaries)',
        license_note='derived from OpenStreetMap data (ODbL-1.0)', features=feats), ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(selftest_passed=ok, cases=len(tests), failed=reg['selftest']['failed'],
                          units=len(reg['units']), zones=[(z['zone_id'], z['area_km2'] or z['area_m2']) for z in reg['zones']]),
                     ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
