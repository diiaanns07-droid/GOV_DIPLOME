"""K03 r10: маленькие ручные графы (synthetic) в формате Overture и запросы с ожиданиями по построению.

  python3 research/round-10-results/K03/make_hand_graphs.py   → fixtures/hand_graphs.json

Каждый граф — сегменты/соединители в схеме K10 (connectors[{connector_id, at}], access_restrictions, road_flags, level_rules),
собранные тем же build_graph.build. Координаты — метры от (69.60, 42.31), переведённые в градусы (synthetic, не город).
Ожидание: статус и причина; для ok — точная длина как сумма кусков (каждый округлён до мм) по ЗАРАНЕЕ известному пути
(без маршрутизатора), ожидаемые/запрещённые рёбра и допущения.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k03net as K  # noqa: E402
import build_graph as BG  # noqa: E402

LON0, LAT0 = 69.60, 42.31
MY = K.R_EARTH * math.pi / 180  # метров в градусе широты на сфере haversine-mm-v1
MX = MY * math.cos(math.radians(LAT0))


def P(x, y):
    return [round(LON0 + x / MX, 9), round(LAT0 + y / MY, 9)]


def mm(m):
    return K.js_round(m * 1000)


class Mini:
    def __init__(self, name, bbox_m, note):
        self.name, self.note = name, note
        (x0, y0), (x1, y1) = bbox_m
        self.bbox = P(x0, y0) + P(x1, y1)
        self.segs, self.cons = [], {}

    def seg(self, sid, pts, cls='footway', access=None, flags=None, levels=None, con_at=None):
        coords = [P(*p) for p in pts]
        cum = [0.0]
        for i in range(1, len(coords)):
            cum.append(cum[-1] + K.haversine_m(coords[i - 1], coords[i]))
        idx = con_at if con_at is not None else [0, len(pts) - 1]
        cons = []
        for j in idx:
            cid = 'n' + str(pts[j][0]) + '_' + str(pts[j][1])
            self.cons[cid] = coords[j]
            cons.append({'connector_id': cid, 'at': round(cum[j] / cum[-1], 9)})
        self.segs.append({'type': 'Feature', 'id': sid, 'geometry': {'type': 'LineString', 'coordinates': coords},
                          'properties': {'class': cls, 'subclass': None, 'connectors': cons, 'access_restrictions': access,
                                         'road_flags': flags, 'level_rules': levels, 'sources': [{'record_id': 'synthetic:' + sid}]}})
        return self

    def graph(self):
        seg = {'type': 'FeatureCollection', 'features': self.segs}
        con = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'id': k, 'geometry': {'type': 'Point', 'coordinates': v}, 'properties': {}}
                                                         for k, v in sorted(self.cons.items())]}
        return seg, con, BG.build(seg, con, 'synthetic-' + self.name, self.bbox, 'synthetic', {'note': 'synthetic hand graph'})


def seglen(g, sid):
    return sum(e['len_mm'] for e in g['edges'] if e['seg'] == sid)


def edge_ids(g, sid):
    return [e['id'] for e in g['edges'] if e['seg'] == sid]


DENY_FOOT = [{'access_type': 'denied', 'when': {'mode': ['foot']}}]
ONEWAY_FOOT = [{'access_type': 'denied', 'when': {'heading': 'backward', 'mode': ['foot']}}]
ONEWAY_NOMODE = [{'access_type': 'denied', 'when': {'heading': 'backward'}}]
DURING_FOOT = [{'access_type': 'denied', 'when': {'mode': ['foot'], 'during': 'Mo-Fr 07:00-19:00'}}]
BETWEEN_FOOT = [{'access_type': 'denied', 'when': {'mode': ['foot']}, 'between': [0.6, 0.9]}]


def q(qid, o, t, strict, exploratory, why):
    return {'id': qid, 'origin': {'id': 'o', 'lon': P(*o)[0], 'lat': P(*o)[1]}, 'target': {'id': 't', 'lon': P(*t)[0], 'lat': P(*t)[1]},
            'expect': {'pedestrian-v1-strict': strict, 'pedestrian-v1-exploratory': exploratory}, 'why': why}


def ok(dist, include=(), exclude=(), assume=None, label_incomplete=None):
    e = {'status': 'ok', 'distance_mm': dist, 'include_edges': list(include), 'exclude_edges': list(exclude)}
    if assume is not None:
        e['assumptions_superset'] = assume
    return e


def st(status, reason):
    return {'status': status, 'reason': reason}


def main():
    out = []

    # H1 мост: линии пересекаются без общего соединителя → путь в обход
    for kind, flag, lvl in (('bridge', 'is_bridge', 1), ('tunnel', 'is_tunnel', -1)):
        m = Mini(f'h1-{kind}', ((-50, -150), (250, 150)), f'{kind}: CD пересекает AB в (100,0) без соединителя (уровень {lvl})')
        m.seg('ab', [(0, 0), (200, 0)]).seg('cd', [(100, -100), (100, 100)], flags=[{'values': [flag], 'between': None}],
                                            levels=[{'value': lvl, 'between': None}]).seg('bd', [(200, 0), (100, 100)])
        s, c, g = m.graph()
        d = seglen(g, 'ab') + seglen(g, 'bd') + seglen(g, 'cd')
        qs = [q('A-to-C', (0, 0), (100, -100), ok(d, edge_ids(g, 'ab') + edge_ids(g, 'bd') + edge_ids(g, 'cd')),
                ok(d, edge_ids(g, 'ab') + edge_ids(g, 'bd') + edge_ids(g, 'cd')), 'пересечение не узел: путь A→B→D→C, а не 200 м через точку пересечения')]
        out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': qs})

    # H2 барьер: явный запрет foot на B–C; обход через E; без обхода — disconnected
    m = Mini('h2-barrier', ((-50, -50), (350, 150)), 'BC запрещён для foot; обход B–E–C')
    m.seg('ab', [(0, 0), (100, 0)]).seg('bc', [(100, 0), (200, 0)], access=DENY_FOOT).seg('be', [(100, 0), (150, 80)]).seg('ec', [(150, 80), (200, 0)])
    s, c, g = m.graph()
    d = seglen(g, 'ab') + seglen(g, 'be') + seglen(g, 'ec')
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-C', (0, 0), (200, 0), ok(d, edge_ids(g, 'be'), edge_ids(g, 'bc')), ok(d, edge_ids(g, 'be'), edge_ids(g, 'bc')), 'барьер: обход через E')]})
    m = Mini('h2-barrier-no-detour', ((-50, -50), (350, 150)), 'BC запрещён, обхода нет; C–F отдельная компонента внутри квадрата')
    m.seg('ab', [(0, 0), (100, 0)]).seg('bc', [(100, 0), (200, 0)], access=DENY_FOOT).seg('cf', [(200, 0), (300, 0)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-F', (0, 0), (300, 0), st('disconnected', 'no_path_in_closed_component'), st('disconnected', 'no_path_in_closed_component'),
          'пути нет, обе компоненты внутри квадрата → disconnected (ограничение модельной сети)')]})

    # H3 одностороннее пешеходное ограничение (foot, heading backward) + обход B–C–A
    m = Mini('h3-oneway-foot', ((-50, -50), (150, 120)), 'AB: foot только вперёд; обход B–C–A')
    m.seg('ab', [(0, 0), (100, 0)], access=ONEWAY_FOOT).seg('bc', [(100, 0), (50, 60)]).seg('ca', [(50, 60), (0, 0)])
    s, c, g = m.graph()
    qs = [q('A-to-B', (0, 0), (100, 0), ok(seglen(g, 'ab'), edge_ids(g, 'ab')), ok(seglen(g, 'ab'), edge_ids(g, 'ab')), 'по разрешённому направлению'),
          q('B-to-A', (100, 0), (0, 0), ok(seglen(g, 'bc') + seglen(g, 'ca'), edge_ids(g, 'bc') + edge_ids(g, 'ca'), edge_ids(g, 'ab')),
            ok(seglen(g, 'bc') + seglen(g, 'ca'), edge_ids(g, 'bc') + edge_ids(g, 'ca'), edge_ids(g, 'ab')), 'против запрета: только обход')]
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': qs})
    m = Mini('h3-oneway-footway-nomode', ((-50, -50), (150, 50)), 'footway с heading-запретом без mode — относится к пешеходу; обхода нет')
    m.seg('ab', [(0, 0), (100, 0)], access=ONEWAY_NOMODE)
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-B', (0, 0), (100, 0), ok(seglen(g, 'ab')), ok(seglen(g, 'ab')), 'вперёд можно'),
        q('B-to-A', (100, 0), (0, 0), st('disconnected', 'no_path_in_closed_component'), st('disconnected', 'no_path_in_closed_component'),
          'назад нельзя в обеих политиках')]})
    m = Mini('h3-oneway-road-nomode', ((-50, -50), (150, 50)), 'residential с heading-запретом без mode — автомобильный oneway OSM')
    m.seg('ab', [(0, 0), (100, 0)], cls='residential', access=ONEWAY_NOMODE)
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('B-to-A', (100, 0), (0, 0), st('access_unknown', 'no_verified_edge_within_snap'),
          ok(seglen(g, 'ab'), edge_ids(g, 'ab'), assume=['foot_access_unknown', 'vehicle_oneway_not_applied_to_foot']),
          'strict: доступ не подтверждён; exploratory: пройдено с допущением «oneway автомобильный»')]})

    # H4 неподключённая вершина
    m = Mini('h4-disconnected', ((-50, -50), (350, 100)), 'AB и DE не связаны, обе внутри квадрата')
    m.seg('ab', [(0, 0), (100, 0)]).seg('de', [(200, 50), (300, 50)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-D', (0, 0), (200, 50), st('disconnected', 'no_path_in_closed_component'), st('disconnected', 'no_path_in_closed_component'),
          'изолированная компонента → disconnected, прямая не подставляется')]})

    # H5 длинная привязка
    m = Mini('h5-long-snap', ((-50, -150), (250, 150)), 'AB; точки в 99 м и 101 м от линии')
    m.seg('ab', [(0, 0), (200, 0)])
    s, c, g = m.graph()
    p99, p101, B = P(100, 99), P(100, 101), P(200, 0)
    Q = [p99[0], P(0, 0)[1]]
    d99 = mm(K.haversine_m(p99, Q)) + mm(K.haversine_m(Q, B))
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('P99-to-B', (100, 99), (200, 0), ok(d99, edge_ids(g, 'ab'), assume=['snap_model_connection']), ok(d99, edge_ids(g, 'ab'), assume=['snap_model_connection']),
          'привязка 99 м ≤ 100 м: отрезок привязки — модельное соединение, входит в длину'),
        q('P101-to-B', (100, 101), (200, 0), st('unsnappable', 'no_edge_within_max_snap'), st('unsnappable', 'no_edge_within_max_snap'),
          '101 м > 100 м: unsnappable, а не прямая')]})

    # H6 неизвестный доступ
    m = Mini('h6-unknown', ((-50, -50), (250, 50)), 'только residential без правил foot')
    m.seg('ab', [(0, 0), (200, 0)], cls='residential')
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-B', (0, 0), (200, 0), st('access_unknown', 'no_verified_edge_within_snap'), ok(seglen(g, 'ab'), assume=['foot_access_unknown']),
          'strict: access_unknown; exploratory: маршрут по неполным данным')]})
    m = Mini('h6-unknown-middle', ((-50, -50), (350, 50)), 'footway – residential – footway')
    m.seg('ab', [(0, 0), (100, 0)]).seg('bc', [(100, 0), (200, 0)], cls='residential').seg('cd', [(200, 0), (300, 0)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-D', (0, 0), (300, 0), st('access_unknown', 'path_only_via_unverified_edges'),
          ok(seglen(g, 'ab') + seglen(g, 'bc') + seglen(g, 'cd'), edge_ids(g, 'bc'), assume=['foot_access_unknown']),
          'путь есть только через ребро с неизвестным доступом')]})

    # H7 граница среза
    m = Mini('h7-boundary-open', ((0, 0), (300, 300)), 'A–X и T–Y уходят за край, внутри не связаны')
    m.seg('ax', [(50, 50), (-50, 50)]).seg('ty', [(250, 50), (350, 50)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-T', (50, 50), (250, 50), st('outside_coverage', 'path_may_exist_outside_slice'), st('outside_coverage', 'path_may_exist_outside_slice'),
          'обе стороны достигают открытых узлов: путь через внешнюю сеть не проверен')]})
    m = Mini('h7-boundary-shortcut', ((0, 0), (300, 300)), 'внутренний путь A–M–T длиннее нижней границы через X…Y снаружи')
    m.seg('am', [(50, 50), (150, 290)]).seg('mt', [(150, 290), (250, 50)]).seg('ax', [(50, 50), (50, -50)]).seg('ty', [(250, 50), (250, -50)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-T', (50, 50), (250, 50), ok(seglen(g, 'am') + seglen(g, 'mt'), edge_ids(g, 'am') + edge_ids(g, 'mt'), assume=['boundary_unverified']),
          ok(seglen(g, 'am') + seglen(g, 'mt'), edge_ids(g, 'am') + edge_ids(g, 'mt'), assume=['boundary_unverified']),
          'путь найден, но более короткий путь вне среза не исключён (нижняя граница ≈ 400 м < 520 м)')]})

    # H8 точка вне квадрата
    m = Mini('h8-outside', ((0, -50), (300, 50)), 'точка вне bbox')
    m.seg('ab', [(0, 0), (300, 0)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('out-to-B', (-100, 0), (300, 0), st('outside_coverage', 'point_outside_slice'), st('outside_coverage', 'point_outside_slice'), 'вне среза')]})

    # H9 одно ребро: прямо по ребру; против одностороннего — обход
    m = Mini('h9-same-edge', ((-50, -150), (350, 50)), 'обе точки на AB; AB foot только вперёд; обход B–C–A')
    m.seg('ab', [(0, 0), (150, 0), (300, 0)], access=ONEWAY_FOOT).seg('bc', [(300, 0), (150, -80)]).seg('ca', [(150, -80), (0, 0)])
    s, c, g = m.graph()
    o1, t1, A, Bp = P(50, 10), P(250, 10), P(0, 0), P(300, 0)
    q1, q2 = [o1[0], A[1]], [t1[0], A[1]]
    mid = P(150, 0)
    d_fwd = mm(K.haversine_m(o1, q1)) + mm(K.haversine_m(q1, mid) + K.haversine_m(mid, q2)) + mm(K.haversine_m(q2, t1))
    d_back = mm(K.haversine_m(t1, q2)) + mm(K.haversine_m(q2, Bp)) + seglen(g, 'bc') + seglen(g, 'ca') + mm(K.haversine_m(A, q1)) + mm(K.haversine_m(q1, o1))
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('along', (50, 10), (250, 10), ok(d_fwd, edge_ids(g, 'ab'), edge_ids(g, 'bc')), ok(d_fwd, edge_ids(g, 'ab'), edge_ids(g, 'bc')), 'прямо по ребру'),
        q('against', (250, 10), (50, 10), ok(d_back, edge_ids(g, 'bc') + edge_ids(g, 'ca')), ok(d_back, edge_ids(g, 'bc') + edge_ids(g, 'ca')),
          'против направления: до B, обход, от A')]})

    # H10 условное правило
    m = Mini('h10-conditional', ((-50, -50), (350, 50)), 'BC: запрет foot по времени (during); A–B и C–D — footway')
    m.seg('ab', [(0, 0), (100, 0)]).seg('bc', [(100, 0), (200, 0)], access=DURING_FOOT).seg('cd', [(200, 0), (300, 0)])
    s, c, g = m.graph()
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g, 'queries': [
        q('A-to-D', (0, 0), (300, 0), st('access_unknown', 'path_only_via_unverified_edges'),
          ok(seglen(g, 'ab') + seglen(g, 'bc') + seglen(g, 'cd'), edge_ids(g, 'bc'), assume=['conditional_foot_rule']),
          'strict не использует условное ребро; exploratory — с допущением')]})

    # H11 запрет на части сегмента (between)
    m = Mini('h11-between', ((-50, -60), (250, 60)), 'сегмент A–M–B с запретом foot на [0.6, 0.9]: AM доступно, MB запрещено')
    m.seg('amb', [(0, 0), (100, 0), (200, 0)], access=BETWEEN_FOOT, con_at=[0, 1, 2])
    s, c, g = m.graph()
    e0, e1 = edge_ids(g, 'amb')
    p150 = P(150, 0)
    d = mm(K.haversine_m(p150, P(100, 0))) + seglen(g, 'amb') - next(e['len_mm'] for e in g['edges'] if e['id'] == e1)
    out.append({'name': m.name, 'note': m.note, 'segments': s, 'connectors': c, 'graph': g,
                'edge_expect': {e0: {'s': ['ok', 'ok'], 'x': ['ok', 'ok']}, e1: {'s': ['no', 'no'], 'x': ['no', 'no']}}, 'queries': [
        q('A-to-M', (0, 0), (100, 0), ok(next(e['len_mm'] for e in g['edges'] if e['id'] == e0), [e0], [e1]),
          ok(next(e['len_mm'] for e in g['edges'] if e['id'] == e0), [e0], [e1]), 'доступная часть'),
        q('A-to-P150', (0, 0), (150, 0), ok(d, [e0], [e1], assume=['snap_model_connection']), ok(d, [e0], [e1], assume=['snap_model_connection']),
          'точка на запрещённом ребре привязывается к доступному в 50 м: модельное соединение не проверяет физический проход (ограничение)')]})

    doc = {'schema': 'k03-r10-hand-graphs', 'kind': 'synthetic',
           'description': 'Ручные графы в формате Overture (synthetic, не город); ожидания по построению, без маршрутизатора.',
           'policy_sha256': BG.policy()[1], 'graphs': out}
    K.dump(HERE / 'fixtures/hand_graphs.json', doc)
    print('hand graphs:', len(out), 'queries:', sum(len(x['queries']) for x in out))


if __name__ == '__main__':
    main()
