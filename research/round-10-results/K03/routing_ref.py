"""K03 r10: независимый Python-оракул маршрутизации pedestrian-v1 (те же правила, что routing.js; отдельная реализация).

Используется только для проверки JS: привязка, Дейкстра (расстояние мм, ID узла; предшественник — при строгом улучшении),
статусы, геометрия, допущения, граница среза. Только stdlib.
"""
import heapq
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import k03net as K  # noqa: E402

METHOD, ROUTE_SCHEMA = 'pedestrian-v1', 'k03-route-v1'
KEY = {'pedestrian-v1-strict': 's', 'pedestrian-v1-exploratory': 'x'}
LABEL = {'pedestrian-v1-strict': 'маршрут по пешеходным рёбрам OSM/Overture (не проверено на месте)',
         'pedestrian-v1-exploratory': 'маршрут по неполным данным (не гарантированно доступный пешеходный путь)'}
VERIFIED_IN_X = 'маршрут только по рёбрам с подтверждённым доступом (найден в exploratory)'


def mm(m):
    return K.js_round(m * 1000)


def line_m(cs):
    return sum(K.haversine_m(cs[i - 1], cs[i]) for i in range(1, len(cs)))


class Graph:
    def __init__(self, g):
        self.g = g
        self.E = g['edges']
        self.N = {n['id']: n for n in g['nodes']}
        self.idx = {e['id']: i for i, e in enumerate(self.E)}
        self.adj = {}
        for k in 'sx':
            fw, bw = {n: [] for n in self.N}, {n: [] for n in self.N}
            for i, e in enumerate(self.E):
                if e[k][0] == 'ok':
                    fw[e['from']].append((e['id'], 0, i, e['to']))
                    bw[e['to']].append((e['id'], 0, i, e['from']))
                if e[k][1] == 'ok':
                    fw[e['to']].append((e['id'], 1, i, e['from']))
                    bw[e['from']].append((e['id'], 1, i, e['to']))
            for d in (fw, bw):
                for v in d.values():
                    v.sort(key=lambda a: (K.u16(a[0]), a[1]))
            self.adj[k] = (fw, bw)


def snap(G, pt, k):
    kx = math.cos(pt[1] * math.pi / 180)
    best = None
    for ei, e in enumerate(G.E):
        if 'ok' not in e[k]:
            continue
        cs = e['coords']
        for i in range(len(cs) - 1):
            A, B = cs[i], cs[i + 1]
            ax, ay = (A[0] - pt[0]) * kx, A[1] - pt[1]
            bx, by = (B[0] - pt[0]) * kx, B[1] - pt[1]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            t = -(ax * dx + ay * dy) / L2 if L2 > 0 else 0.0
            t = min(1.0, max(0.0, t))
            q = [A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1])]
            cand = (mm(K.haversine_m(pt, q)), K.u16(e['id']), i)
            if best is None or cand < best[0]:
                best = (cand, ei, i, t, q)
    if best is None:
        return None
    (d, _, _), ei, i, t, q = best
    cs = G.E[ei]['coords']
    return {'e': ei, 'i': i, 't': t, 'q': q, 'd': d, 'a': mm(line_m(cs[:i + 1] + [q])), 'b': mm(line_m([q] + cs[i + 1:]))}


def dijkstra(G, k, starts, reverse=False):
    adj = G.adj[k][1 if reverse else 0]
    dist, pred = {}, {}
    for node, cost in starts:
        if node not in dist or cost < dist[node]:
            dist[node], pred[node] = cost, None
    pq = [(c, K.u16(n), n) for n, c in dist.items()]
    heapq.heapify(pq)
    done = set()
    while pq:
        c, _, u = heapq.heappop(pq)
        if u in done or c > dist[u]:
            continue
        done.add(u)
        for eid, d, i, v in adj[u]:
            nd = c + G.E[i]['len_mm']
            if v not in done and (v not in dist or nd < dist[v]):
                dist[v], pred[v] = nd, (u, i, d)
                heapq.heappush(pq, (nd, K.u16(v), v))
    return dist, pred


def starts_out(e, s, k):
    out = []
    if e[k][1] == 'ok' or s['a'] == 0:  # кусок 0 мм от направления не зависит
        out.append((e['from'], s['a']))
    if e[k][0] == 'ok' or s['b'] == 0:
        out.append((e['to'], s['b']))
    return out


def starts_in(e, s, k):
    out = []
    if e[k][0] == 'ok' or s['a'] == 0:
        out.append((e['from'], s['a']))
    if e[k][1] == 'ok' or s['b'] == 0:
        out.append((e['to'], s['b']))
    return out


def arrival(G, k, so, st, dist):
    eT = G.E[st['e']]
    cands = []
    if so['e'] == st['e']:
        fwd = (so['i'], so['t']) <= (st['i'], st['t'])
        same = (so['i'], so['t']) == (st['i'], st['t'])
        if same or (fwd and eT[k][0] == 'ok') or (not fwd and eT[k][1] == 'ok'):
            mid = eT['coords'][so['i'] + 1:st['i'] + 1] if fwd else list(reversed(eT['coords'][st['i'] + 1:so['i'] + 1]))
            cs = [so['q']] + mid + [st['q']]
            cands.append((mm(line_m(cs)), 0, 'direct', 0 if fwd else 1, cs))
    if (eT[k][0] == 'ok' or st['a'] == 0) and eT['from'] in dist:
        cands.append((dist[eT['from']] + st['a'], 1, 'from', 0, None))
    if (eT[k][1] == 'ok' or st['b'] == 0) and eT['to'] in dist:
        cands.append((dist[eT['to']] + st['b'], 2, 'to', 1, None))
    return min(cands, key=lambda c: (c[0], c[1])) if cands else None


def build_path(G, so, st, pred, arr):
    E, eO, eT = G.E, G.E[so['e']], G.E[st['e']]
    cost, _, via, d_end, cs_direct = arr
    if via == 'direct':
        return ([], cs_direct, []) if cost == 0 else ([(eT['id'], d_end, True)], cs_direct, list(eT['xa'][d_end]))
    node = eT['from'] if via == 'from' else eT['to']
    steps = []
    while pred[node] is not None:
        u, i, d = pred[node]
        steps.append((i, d))
        node = u
    steps.reverse()
    first = node
    d0 = 1 if first == eO['from'] else 0
    cs = [so['q']] + (list(reversed(eO['coords'][:so['i'] + 1])) if d0 == 1 else eO['coords'][so['i'] + 1:])
    edges, assume = [], []
    if (so['a'] if d0 == 1 else so['b']) > 0:
        edges, assume = [(eO['id'], d0, True)], list(eO['xa'][d0])
    for i, d in steps:
        c = E[i]['coords'] if d == 0 else list(reversed(E[i]['coords']))
        cs += c[1:]
        edges.append((E[i]['id'], d, False))
        assume += E[i]['xa'][d]
    tail = eT['coords'][1:st['i'] + 1] if d_end == 0 else list(reversed(eT['coords'][st['i'] + 1:-1]))
    cs += tail + [st['q']]
    if (st['a'] if d_end == 0 else st['b']) > 0:
        edges.append((eT['id'], d_end, True))
        assume += eT['xa'][d_end]
    return edges, cs, assume


class Router:
    def __init__(self, g):
        self.G = Graph(g)
        self.cache = {}

    def _c(self, key, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]

    def snap(self, k, pt):
        return self._c(('s', k, tuple(pt)), lambda: snap(self.G, pt, k))

    def fwd(self, k, pt, s):
        return self._c(('f', k, tuple(pt)), lambda: dijkstra(self.G, k, starts_out(self.G.E[s['e']], s, k)))

    def bwd(self, k, pt, s):
        return self._c(('b', k, tuple(pt)), lambda: dijkstra(self.G, k, starts_in(self.G.E[s['e']], s, k), reverse=True))

    def base(self, o, t, policy):
        g = self.G.g
        return {'schema_version': ROUTE_SCHEMA, 'origin_id': o['id'], 'target_id': t['id'], 'distance_mm': None, 'status': None,
                'method': METHOD, 'policy_id': policy, 'policy_sha256': g['policy_sha256'], 'graph_sha256': g['graph_sha256'],
                'city': g['city'], 'route_edge_ids': [], 'geometry': None, 'parts': [], 'assumptions': [], 'reason': None, 'label': None}

    def route(self, o, t, policy, max_snap_m=None):
        G, g = self.G, self.G.g
        k = KEY[policy]
        lim = round((max_snap_m or g['max_snap_m']) * 1000)
        r = self.base(o, t, policy)
        po, pt = [o['lon'], o['lat']], [t['lon'], t['lat']]
        W, S, E_, N = g['bbox']
        if not all(W <= p[0] <= E_ and S <= p[1] <= N for p in (po, pt)):
            return dict(r, status='outside_coverage', reason='point_outside_slice')
        so, st = self.snap(k, po), self.snap(k, pt)
        ok = lambda s: s is not None and s['d'] <= lim  # noqa: E731
        if not (ok(so) and ok(st)):
            if k == 's' and ok(self.snap('x', po)) and ok(self.snap('x', pt)):
                return dict(r, status='access_unknown', reason='no_verified_edge_within_snap')
            return dict(r, status='unsnappable', reason='no_edge_within_max_snap', assumptions=[f'max_snap_m={K.js_num(lim / 1000)}'])
        dist, pred = self.fwd(k, po, so)
        arr = arrival(G, k, so, st, dist)
        if arr is None:
            sx, tx = self.snap('x', po), self.snap('x', pt)
            if k == 's' and ok(sx) and ok(tx) and arrival(G, 'x', sx, tx, self.fwd('x', po, sx)[0]) is not None:
                return dict(r, status='access_unknown', reason='path_only_via_unverified_edges')
            opn = ok(sx) and ok(tx) and any(G.N[n]['open'] for n in self.fwd('x', po, sx)[0]) and any(G.N[n]['open'] for n in self.bwd('x', pt, tx)[0])
            return dict(r, status='outside_coverage', reason='path_may_exist_outside_slice') if opn else \
                dict(r, status='disconnected', reason='no_path_in_closed_component')
        edges, cs, assume = build_path(G, so, st, pred, arr)
        net = arr[0]
        A = set(assume)
        if so['d'] > 0 or st['d'] > 0:
            A.add('snap_model_connection')
        if any(G.E[G.idx[e]]['out'] for e, _, _ in edges):
            A.add('route_partly_outside_slice')
        bdist = self.bwd(k, pt, st)[0]
        # нижняя граница через внешнюю сеть: пары открытых узлов с c < net (полный перебор; JS считает то же решение через f(b'))
        o_open = [(n, c) for n, c in dist.items() if G.N[n]['open'] and c < net]
        t_open = [(n, c) for n, c in bdist.items() if G.N[n]['open'] and c < net]
        lb = None
        for n2, c2 in t_open:
            p2 = (G.N[n2]['lon'], G.N[n2]['lat'])
            for n1, c1 in o_open:
                v = c1 + c2 + mm(K.haversine_m((G.N[n1]['lon'], G.N[n1]['lat']), p2))
                if lb is None or v < lb:
                    lb = v
        if lb is not None and lb < net:
            A.add('boundary_unverified')
        coords = []
        for c in [po] + cs + [pt]:
            if not coords or c[0] != coords[-1][0] or c[1] != coords[-1][1]:
                coords.append(list(c))
        label = LABEL[policy] if (k == 's' or assume) else VERIFIED_IN_X
        return dict(r, status='ok', distance_mm=so['d'] + net + st['d'], route_edge_ids=[e for e, _, _ in edges],
                    geometry={'type': 'LineString', 'coordinates': coords},
                    parts=[{'kind': 'snap', 'role': 'origin', 'length_mm': so['d'], 'model_connection': True, 'edge_id': G.E[so['e']]['id']},
                           {'kind': 'network', 'length_mm': net, 'edges': [{'id': e, 'd': d, 'partial': pa} for e, d, pa in edges]},
                           {'kind': 'snap', 'role': 'target', 'length_mm': st['d'], 'model_connection': True, 'edge_id': G.E[st['e']]['id']}],
                    assumptions=sorted(A, key=K.u16), label=label)

    def geodesic(self, o, t):
        g = self.G.g
        r = dict(self.base(o, t, None), method='geodesic', policy_sha256=None)
        po, pt = [o['lon'], o['lat']], [t['lon'], t['lat']]
        W, S, E_, N = g['bbox']
        if not all(W <= p[0] <= E_ and S <= p[1] <= N for p in (po, pt)):
            return dict(r, status='outside_coverage', reason='point_outside_slice')
        return dict(r, status='ok', distance_mm=mm(K.haversine_m(po, pt)), geometry={'type': 'LineString', 'coordinates': [po, pt]},
                    assumptions=['straight_line_not_route'], label='прямая, не маршрут')
