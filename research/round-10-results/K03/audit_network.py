"""K03 r10, этап 1: хватает ли сети segments/connectors для пешеходного графа школьного кейса (оба города).

  python3 research/round-10-results/K03/audit_network.py

Входы — только закреплённые коммиты (k03net.load_inputs): web/govtech/core/data.js базы d2ff344 и сырой K10-пакет донора d18847f
(prototypes/city-evidence/inputs/k10/data/<city>/{segments,connectors}.geojson; sha256 сверяется с data.js.cities[c].files).
Выход: audit/<city>.json, inputs/INPUT_MANIFEST.json. Ничего не скачивает; сети не требуется.
"""
import collections
import json
import statistics
import sys
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k03net as K  # noqa: E402

PED_CLASSES = ('footway', 'pedestrian', 'steps', 'path', 'living_street')


def foot_rules(p):
    """Независимая классификация правил доступа, относящихся к пешеходу (не копия K10)."""
    out = collections.Counter()
    for r in p.get('access_restrictions') or []:
        w = r.get('when') or {}
        modes = w.get('mode')
        if modes is not None and 'foot' not in modes:
            out['other_mode_only'] += 1
            continue
        cond = [k for k in ('during', 'using', 'recognized', 'vehicle') if w.get(k)]
        if r.get('between'):
            cond.append('between')
        if w.get('heading'):
            cond.append('heading')
        explicit = bool(modes)
        t = r.get('access_type')
        if t == 'denied' and not modes and cond == ['heading']:
            out['no_mode_heading_denied (oneway OSM)'] += 1
        elif t == 'denied':
            out['foot_denied' + ('' if explicit else '_all_modes') + (('_cond:' + '+'.join(cond)) if cond else '')] += 1
        else:
            out[f'{t}_foot' + ('' if explicit else '_all_modes') + (('_cond:' + '+'.join(cond)) if cond else '')] += 1
    return out


def main():
    I = K.load_inputs()
    data = I['data_js']
    K.dump(HERE / 'inputs/INPUT_MANIFEST.json', dict(I['manifest'], note='Входы читаются git show из закреплённых коммитов; blob сверен, '
                                                      'sha256 сегментов/соединителей = data.js.cities[c].files[*].sha256.'))
    summary = {}
    for c in K.CITIES:
        segs = I[(c, 'segments')]['features']
        cons = {f['id']: f for f in I[(c, 'connectors')]['features']}
        meta = {k: v for k, v in I[(c, 'segments')].items() if k != 'features'}
        dc = data['cities'][c]
        W, S, E, N = dc['bbox']
        inside = lambda pt: W <= pt[0] <= E and S <= pt[1] <= N  # noqa: E731
        rep = {'city': c, 'source': meta, 'bbox': dc['bbox']}

        # 1. data.js против сырого источника
        djs = {s['id']: s for s in dc['segments']}
        raw = {f['id']: f for f in segs}
        coord_bad = [i for i, s in djs.items() if i in raw and s['coords'] != [[round(x, 6), round(y, 6)] for x, y in raw[i]['geometry']['coordinates']]]
        rep['data_js_vs_raw'] = {
            'segments_data_js': len(djs), 'segments_raw': len(raw), 'same_id_set': set(djs) == set(raw),
            'coords_equal_raw_rounded_6dp': not coord_bad, 'coord_mismatch_examples': coord_bad[:3],
            'foot_access_equal_k10': all(djs[i]['foot_access'] == raw[i]['properties']['k10_foot_access'] for i in djs),
            'data_js_segment_fields': sorted(next(iter(djs.values())).keys()),
            'data_js_has_connector_ids': any(isinstance(s.get('connectors'), list) for s in djs.values()),
            'verdict': 'data.js недостаточно для графа: у сегмента только число соединителей, без их ID и позиций; связность по '
                       'пересечению линий запрещена. Граф строится из сырого K10-пакета донора (тот же sha256, что в data.js.files).'}

        # 2. соответствие соединителей геометрии на фактических строках
        missing, off_vertex, order_bad, ends_bad, dup, at_dev = 0, [], 0, 0, 0, []
        for f in segs:
            co = f['geometry']['coordinates']
            cum = [0.0]
            for i in range(1, len(co)):
                cum.append(cum[-1] + K.haversine_m(co[i - 1], co[i]))
            cs = f['properties']['connectors']
            ids = [x['connector_id'] for x in cs]
            dup += len(set(ids)) != len(ids)
            ends_bad += not (cs[0]['at'] == 0 and cs[-1]['at'] == 1)
            last = -1
            for x in cs:
                if x['connector_id'] not in cons:
                    missing += 1
                    continue
                pt = cons[x['connector_id']]['geometry']['coordinates']
                d = [K.haversine_m(pt, v) for v in co]
                j = min(range(len(co)), key=lambda k: (d[k], k))
                if d[j] > 0.01:
                    off_vertex.append([f['id'], x['connector_id'], round(d[j], 3)])
                order_bad += j < last
                last = j
                at_dev.append(abs((cum[j] / cum[-1] if cum[-1] else 0) - x['at']))
        used = {x['connector_id'] for f in segs for x in f['properties']['connectors']}
        rep['geometry_checks'] = {'connectors_missing': missing, 'connector_not_on_vertex_gt_1cm': len(off_vertex), 'examples': off_vertex[:3],
                                  'connector_order_not_monotonic': order_bad, 'first_last_not_0_1': ends_bad, 'duplicate_connector_in_segment': dup,
                                  'at_vs_haversine_fraction_max': max(at_dev), 'at_vs_haversine_fraction_p99': sorted(at_dev)[int(len(at_dev) * .99)],
                                  'connectors_total': len(cons), 'connectors_unused': len(set(cons) - used),
                                  'connectors_outside_bbox': sum(1 for v in cons.values() if not inside(v['geometry']['coordinates'])),
                                  'k10_inside_flag_matches_bbox': all(v['properties']['k10_inside_bbox'] == inside(v['geometry']['coordinates']) for v in cons.values())}

        # 3. классы, длины, доступ, мосты/тоннели/уровни
        km = collections.Counter()
        for f in segs:
            km[f['properties']['class']] += K.polyline_m(f['geometry']['coordinates']) / 1000
        rules = collections.Counter()
        for f in segs:
            rules.update(foot_rules(f['properties']))
        k10 = collections.Counter(f['properties']['k10_foot_access'] for f in segs)
        km_access = collections.Counter()
        for f in segs:
            km_access[f['properties']['k10_foot_access']] += K.polyline_m(f['geometry']['coordinates']) / 1000
        special = []
        for f in segs:
            p = f['properties']
            fl = [{'values': r.get('values'), 'between': r.get('between')} for r in p.get('road_flags') or []]
            lv = [{'value': r.get('value'), 'between': r.get('between')} for r in p.get('level_rules') or []]
            if fl and any(set(x['values'] or []) - {'is_link'} for x in fl) or lv:
                special.append({'id': f['id'], 'class': p['class'], 'subclass': p['subclass'], 'road_flags': fl, 'level_rules': lv,
                                'osm': [s.get('record_id') for s in p.get('sources') or []], 'foot': p['k10_foot_access'],
                                'connectors': len(p['connectors'])})
        rep['classes_km'] = {k: round(v, 3) for k, v in km.most_common()}
        rep['subclass_counts'] = dict(collections.Counter(f['properties']['subclass'] for f in segs).most_common())
        rep['foot_access_k10'] = {'segments': dict(k10), 'km': {k: round(v, 3) for k, v in km_access.items()}}
        rep['foot_relevant_rules_independent'] = dict(rules.most_common())
        rep['pedestrian_class_km'] = round(sum(v for k, v in km.items() if k in PED_CLASSES), 3)
        rep['bridges_tunnels_levels'] = special

        # 4. пересечения линий без общего соединителя (не узлы) и касания вершин без соединителя
        lines = [LineString(f['geometry']['coordinates']) for f in segs]
        tree = STRtree(lines)
        conset = [set(x['connector_id'] for x in f['properties']['connectors']) for f in segs]
        conpts = {k: Point(v['geometry']['coordinates']) for k, v in cons.items()}
        crossings = []
        for i, j in zip(*tree.query(lines, predicate='intersects')):
            if i >= j:
                continue
            inter = lines[i].intersection(lines[j])
            pts = [g for g in getattr(inter, 'geoms', [inter]) if g.geom_type == 'Point'] + \
                  [Point(g.coords[0]) for g in getattr(inter, 'geoms', [inter]) if g.geom_type == 'LineString']
            shared = conset[i] & conset[j]
            for pt in pts:
                if any(conpts[s].distance(pt) < 1e-7 for s in shared):
                    continue
                pi, pj = segs[i]['properties'], segs[j]['properties']
                crossings.append({'a': segs[i]['id'], 'b': segs[j]['id'], 'lon': round(pt.x, 7), 'lat': round(pt.y, 7),
                                  'a_class': pi['class'], 'b_class': pj['class'],
                                  'a_flags': sorted({v for r in pi.get('road_flags') or [] for v in r.get('values') or []}),
                                  'b_flags': sorted({v for r in pj.get('road_flags') or [] for v in r.get('values') or []}),
                                  'a_levels': sorted({r.get('value') for r in pi.get('level_rules') or []}),
                                  'b_levels': sorted({r.get('value') for r in pj.get('level_rules') or []}),
                                  'a_osm': [s.get('record_id') for s in pi.get('sources') or []][:1],
                                  'b_osm': [s.get('record_id') for s in pj.get('sources') or []][:1]})
        expl = lambda x: bool(x['a_flags'] or x['b_flags'] or x['a_levels'] or x['b_levels'])  # noqa: E731
        rep['crossings_without_shared_connector'] = {
            'count': len(crossings), 'with_bridge_tunnel_or_level': sum(map(expl, crossings)),
            'without_any_level_or_flag': sum(not expl(x) for x in crossings),
            'rule': 'не узел: связность только по общему connector_id; в граф не добавляются', 'examples_with_flags': [x for x in crossings if expl(x)][:6],
            'examples_without_flags': [x for x in crossings if not expl(x)][:6]}

        # 5. связность (неориентированная, все сегменты) и граница среза
        adj = collections.defaultdict(set)
        for f in segs:
            ids = [x['connector_id'] for x in f['properties']['connectors']]
            for a, b in zip(ids, ids[1:]):
                adj[a].add(b)
                adj[b].add(a)

        def components(nodes, nbr):
            seen, comps = set(), []
            for n in sorted(nodes):
                if n in seen:
                    continue
                st, comp = [n], []
                seen.add(n)
                while st:
                    x = st.pop()
                    comp.append(x)
                    for y in nbr(x):
                        if y not in seen:
                            seen.add(y)
                            st.append(y)
                comps.append(comp)
            return sorted(comps, key=len, reverse=True)
        comps = components(set(adj), lambda x: adj[x])
        open_ = {k for k, v in cons.items() if not inside(v['geometry']['coordinates'])}
        rep['connectivity_all_segments'] = {'components': len(comps), 'largest_nodes': len(comps[0]), 'nodes': len(adj),
                                            'largest_share': round(len(comps[0]) / len(adj), 4),
                                            'closed_components_inside_bbox': sum(1 for cp in comps if not set(cp) & open_),
                                            'components_touching_boundary': sum(1 for cp in comps if set(cp) & open_)}
        padj = collections.defaultdict(set)
        for f in segs:
            if f['properties']['class'] not in PED_CLASSES or f['properties']['k10_foot_access'] == 'denied':
                continue
            ids = [x['connector_id'] for x in f['properties']['connectors']]
            for a, b in zip(ids, ids[1:]):
                padj[a].add(b)
                padj[b].add(a)
        pc = components(set(padj), lambda x: padj[x])
        rep['connectivity_pedestrian_classes_only'] = {'classes': list(PED_CLASSES), 'components': len(pc), 'nodes': len(padj),
                                                       'largest_nodes': len(pc[0]) if pc else 0,
                                                       'largest_share': round(len(pc[0]) / len(padj), 4) if pc else None,
                                                       'sizes_top10': [len(x) for x in pc[:10]]}
        cross = [f for f in segs if f['properties']['k10_crosses_bbox_edge']]
        out_km = 0.0
        for f in segs:
            co = f['geometry']['coordinates']
            out_km += sum(K.haversine_m(co[i - 1], co[i]) for i in range(1, len(co)) if not (inside(co[i - 1]) and inside(co[i]))) / 1000
        rep['boundary'] = {'segments_crossing_bbox_edge': len(cross), 'connectors_outside_bbox_open': len(open_),
                           'km_of_pieces_touching_outside': round(out_km, 3), 'buffer_in_data_m': 0,
                           'note': 'Выгрузка K10 — сегменты, пересекающие квадрат, целиком; соседние сегменты вне квадрата отсутствуют. '
                                   'Узел внутри bbox полон (все его сегменты в данных), узел вне bbox «открыт».'}

        # 6. школы: расстояние до сети (все классы / пешеходные классы) и до края среза
        sch = [p for p in dc['places'] if p['group'] == 'school']
        ped_lines = [ln for ln, f in zip(lines, segs) if f['properties']['class'] in PED_CLASSES and f['properties']['k10_foot_access'] != 'denied']
        any_lines = [ln for ln, f in zip(lines, segs) if f['properties']['k10_foot_access'] != 'denied']

        def near_m(pt, lns):
            best = None
            for ln in lns:
                q = ln.interpolate(ln.project(Point(pt)))
                d = K.haversine_m(pt, (q.x, q.y))
                best = d if best is None or d < best else best
            return best
        rows = []
        for p in sorted(sch, key=lambda p: p['id']):
            pt = (p['lon'], p['lat'])
            edge = min(K.haversine_m(pt, (W, p['lat'])), K.haversine_m(pt, (E, p['lat'])), K.haversine_m(pt, (p['lon'], S)), K.haversine_m(pt, (p['lon'], N)))
            rows.append({'id': p['id'], 'name': p['name'], 'to_any_road_m': round(near_m(pt, any_lines), 1),
                         'to_pedestrian_class_m': round(near_m(pt, ped_lines), 1), 'to_bbox_edge_m': round(edge, 1)})
        q = lambda xs: {'min': min(xs), 'median': statistics.median(xs), 'max': max(xs)}  # noqa: E731
        rep['schools_snap'] = {'count': len(rows), 'to_any_road_m': q([r['to_any_road_m'] for r in rows]),
                               'to_pedestrian_class_m': q([r['to_pedestrian_class_m'] for r in rows]),
                               'within_100m_of_bbox_edge': sum(r['to_bbox_edge_m'] < 100 for r in rows), 'rows': rows,
                               'note': 'Расстояние в плоской проекции lon/lat до ближайшей точки линии, затем гаверсинус; для выбора допуска привязки.'}
        K.dump(HERE / f'audit/{c}.json', rep)
        summary[c] = {'segments': len(segs), 'connectors': len(cons), 'data_js_sufficient': False,
                      'connector_on_vertex_violations': len(off_vertex), 'crossings_without_connector': len(crossings),
                      'pedestrian_km': rep['pedestrian_class_km'], 'all_km': round(sum(km.values()), 3),
                      'ped_components': len(pc), 'ped_largest_share': rep['connectivity_pedestrian_classes_only']['largest_share'],
                      'schools_to_any_road_median_m': rep['schools_snap']['to_any_road_m']['median'],
                      'schools_to_ped_median_m': rep['schools_snap']['to_pedestrian_class_m']['median'],
                      'schools_to_ped_max_m': rep['schools_snap']['to_pedestrian_class_m']['max']}
        print(c, json.dumps(summary[c], ensure_ascii=False))
    K.dump(HERE / 'audit/summary.json', summary)


if __name__ == '__main__':
    main()
