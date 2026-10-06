"""K03 r10, этап 2: пешеходный граф pedestrian-v1 из сегментов/соединителей Overture (K10-пакет).

  python3 research/round-10-results/K03/build_graph.py            # оба города из закреплённых входов → graph/<city>.graph.json
  python3 research/round-10-results/K03/build_graph.py --check    # пересобрать в памяти и сверить с файлами (детерминизм, hash)

Узлы — соединители (connector_id); рёбра — куски сегмента между соседними соединителями (по индексу вершины).
Для каждого ребра и направления [вперёд, назад] по policy/pedestrian-v1.json:
  s  — strict:      ok | unk (доступ не подтверждён) | no (запрет);
  x  — exploratory: ok | no;
  xa — допущения exploratory для направления (пусто = подтверждено данными).
Длина ребра len_mm — гаверсинус по вершинам ребра, округлён один раз. graph_sha256 покрывает входы, политику, узлы и рёбра.
Без сети и платных API; только stdlib.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k03net as K  # noqa: E402

SCHEMA = 'k03-pedestrian-graph-v1'
POLICY_PATH = HERE / 'policy/pedestrian-v1.json'
PED = ('footway', 'pedestrian', 'steps', 'path', 'living_street')
PED_ONEWAY_APPLIES = ('footway', 'pedestrian', 'steps', 'path')  # на этих классах heading-запрет без mode относится к пешеходу
COND_KEYS = ('during', 'using', 'recognized', 'vehicle')
LICENSE = {'id': 'ODbL-1.0', 'attribution': ['© OpenStreetMap contributors (ODbL-1.0)', 'Overture Maps Foundation, release 2026-09-23.1'],
           'note': 'Граф — производная база данных OSM (через Overture): распространяется под ODbL с атрибуцией; юридическая проверка не проводилась.'}


def policy():
    p = json.loads(POLICY_PATH.read_text(encoding='utf-8'))
    return p, K.sha256_canon(p)


def _rules(props):
    out = []
    for r in props.get('access_restrictions') or []:
        w = r.get('when') or {}
        modes = w.get('mode') or None
        if modes is not None and 'foot' not in modes:
            continue
        out.append({'type': r.get('access_type'), 'foot': bool(modes), 'heading': w.get('heading'),
                    'cond': [k for k in COND_KEYS if w.get(k)], 'between': r.get('between')})
    return out


def _overlaps(btw, a, b):
    if not btw:
        return True
    x, y = btw
    return max(a, x) < min(b, y) or (a == b and x <= a <= y)


def _covers(btw, a, b):
    return not btw or (btw[0] <= a and b <= btw[1])


def edge_access(props, a, b):
    """Допуск ребра [at a, at b] по направлениям для strict/exploratory + допущения + вид доказательства."""
    cls = props.get('class')
    flags = {v for f in props.get('road_flags') or [] if _overlaps(f.get('between'), a, b) for v in f.get('values') or []}
    rules = _rules(props)
    s, x, xa = [], [], []
    evid = set()
    for d in ('forward', 'backward'):
        hard_deny = cond = oneway_nomode = allow_foot = allow_all = False
        for r in rules:
            if r['heading'] and r['heading'] != d:
                continue
            if r['type'] == 'denied':
                if not _overlaps(r['between'], a, b):
                    continue
                if r['cond']:
                    cond = True
                elif r['heading'] and not r['foot']:
                    oneway_nomode = True
                else:
                    hard_deny = True
            elif r['type'] in ('allowed', 'designated'):
                if r['cond']:
                    cond = cond or _overlaps(r['between'], a, b)
                elif _covers(r['between'], a, b):
                    allow_foot = allow_foot or r['foot']
                    allow_all = allow_all or not r['foot']
        excluded = cls == 'motorway' or bool(flags & {'is_under_construction', 'is_abandoned'})
        explicit = allow_foot or allow_all
        class_sem = cls in PED
        assume = []
        if excluded or hard_deny or (oneway_nomode and cls in PED_ONEWAY_APPLIES and not allow_foot):
            s.append('no'), x.append('no'), xa.append([])
            evid.add('denied')
            continue
        if oneway_nomode and not allow_foot:
            st = 'no'  # буквально: запрет всех режимов в этом направлении
            assume.append('vehicle_oneway_not_applied_to_foot')
        elif cond:
            st = 'unk'
        elif explicit or class_sem:
            st = 'ok'
        else:
            st = 'unk'
        if cond:
            assume.append('conditional_foot_rule')
        if not (explicit or class_sem):
            assume.append('cycleway_foot_unknown' if cls == 'cycleway' else 'foot_access_unknown')
        evid.add('explicit_rule' if explicit else 'class_semantics' if class_sem else 'unknown')
        s.append(st), x.append('ok'), xa.append(sorted(assume))
    order = ('explicit_rule', 'class_semantics', 'unknown', 'denied')
    return s, x, xa, next(e for e in order if e in evid), sorted(flags)


def build(segments_fc, connectors_fc, city, bbox, release, inputs_meta):
    pol, pol_sha = policy()
    W, S, E, N = bbox
    inside = lambda pt: W <= pt[0] <= E and S <= pt[1] <= N  # noqa: E731
    cons = {f['id']: f['geometry']['coordinates'] for f in connectors_fc['features']}
    nodes = {}
    edges = []
    for f in sorted(segments_fc['features'], key=lambda f: K.u16(f['id'])):
        p, co = f['properties'], f['geometry']['coordinates']
        idx = []
        for c in p['connectors']:
            pt = cons[c['connector_id']]
            j = min(range(len(co)), key=lambda k: (K.haversine_m(pt, co[k]), k))
            if K.haversine_m(pt, co[j]) > 0.01 or (idx and j <= idx[-1][1]):
                raise ValueError(f'{f["id"]}: соединитель {c["connector_id"]} не на вершине по порядку')
            idx.append((c['connector_id'], j, c['at']))
        levels = [{'value': r.get('value'), 'between': r.get('between')} for r in p.get('level_rules') or []]
        osm = [s.get('record_id') for s in p.get('sources') or [] if s.get('record_id')]
        for k in range(len(idx) - 1):
            (ca, ia, aa), (cb, ib, ab) = idx[k], idx[k + 1]
            piece = [list(v) for v in co[ia:ib + 1]]
            s, x, xa, ev, flags = edge_access(p, aa, ab)
            edges.append({'id': f'{f["id"]}#{k}', 'seg': f['id'], 'from': ca, 'to': cb, 'at': [aa, ab], 'coords': piece,
                          'len_mm': K.js_round(K.polyline_m(piece) * 1000), 'cls': p.get('class'), 'sub': p.get('subclass'),
                          'flags': flags, 'levels': [lv for lv in levels if _overlaps(lv['between'], aa, ab)], 'osm': osm,
                          'out': any(not inside(v) for v in piece), 's': s, 'x': x, 'xa': xa, 'ev': ev})
            for cid in (ca, cb):
                nodes[cid] = {'id': cid, 'lon': cons[cid][0], 'lat': cons[cid][1], 'open': not inside(cons[cid])}
    nodes = [nodes[k] for k in sorted(nodes, key=K.u16)]
    edges.sort(key=lambda e: K.u16(e['id']))
    body = {'schema': SCHEMA, 'city': city, 'bbox': list(bbox), 'release': release, 'policy_family': pol['family'], 'policy_sha256': pol_sha,
            'max_snap_m': pol['max_snap_m'], 'inputs': inputs_meta, 'nodes': nodes, 'edges': edges}
    g = dict(body, graph_sha256=K.sha256_canon(body), license=LICENSE,
             build={'script': 'research/round-10-results/K03/build_graph.py',
                    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
             stats=stats(nodes, edges))
    return g


def stats(nodes, edges):
    km = lambda es: round(sum(e['len_mm'] for e in es) / 1e6, 3)  # noqa: E731
    both = lambda e, key: e[key][0] == 'ok' or e[key][1] == 'ok'  # noqa: E731
    return {'nodes': len(nodes), 'open_nodes': sum(n['open'] for n in nodes), 'edges': len(edges), 'km_all': km(edges),
            'km_strict_ok_any_direction': km([e for e in edges if both(e, 's')]),
            'km_exploratory_ok_any_direction': km([e for e in edges if both(e, 'x')]),
            'km_denied_both': km([e for e in edges if e['x'] == ['no', 'no']]),
            'edges_by_evidence': {k: sum(e['ev'] == k for e in edges) for k in ('explicit_rule', 'class_semantics', 'unknown', 'denied')},
            'edges_one_direction_strict': sum(sorted(e['s']) == ['no', 'ok'] for e in edges),
            'edges_with_assumptions': sum(bool(e['xa'][0] or e['xa'][1]) for e in edges)}


def build_city(I, city):
    dc = I['data_js']['cities'][city]
    man = I['manifest']['cities'][city]
    inputs = {k: {f: man[k][f] for f in ('commit', 'path', 'git_blob', 'sha256')} for k in ('segments', 'connectors')}
    inputs['data_js'] = {f: I['manifest']['data_js'][f] for f in ('commit', 'path', 'git_blob', 'sha256')}
    return build(I[(city, 'segments')], I[(city, 'connectors')], city, dc['bbox'], dc['release'], inputs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    I = K.load_inputs()
    bad = []
    for c in K.CITIES:
        g = build_city(I, c)
        path = HERE / f'graph/{c}.graph.json'
        text = json.dumps(g, ensure_ascii=False, separators=(',', ':')) + '\n'
        if a.check:
            old = json.loads(path.read_text(encoding='utf-8'))
            same = old['graph_sha256'] == g['graph_sha256'] and old == json.loads(text)
            bad += [] if same else [c]
            print(c, 'graph_sha256', g['graph_sha256'], 'совпадает с файлом' if same else 'НЕ совпадает')
        else:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text, encoding='utf-8')
            print(c, g['graph_sha256'], json.dumps(g['stats'], ensure_ascii=False), f'{len(text.encode()) / 1e6:.2f} МБ')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
