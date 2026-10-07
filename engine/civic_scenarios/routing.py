"""Детерминированный кратчайший путь (Дейкстра) в целых миллиметрах.

Порядок кучи — (расстояние мм, ID узла); смежность отсортирована по ID ребра; предшественник
меняется только при строгом улучшении. Поэтому при равных путях выбор стабилен, а признак
equal_cost_alternatives сообщает, что существует другой путь той же длины (счётчик путей, насыщается на 2).
Идея tie-break повторяет web/govtech/k03/routing.js (K03 r10, снимок b2cb2e0) — реализация новая.
Прямая линия никогда не подставляется вместо отсутствующего пути.
"""
import heapq


def dijkstra(adj, source):
    dist = {source: 0}
    pred = {source: None}
    count = {source: 1}
    done = set()
    heap = [(0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if u in done or d > dist[u]:
            continue
        done.add(u)
        for eid, v, mm in adj.get(u, ()):
            if v in done:
                continue
            nd = d + mm
            old = dist.get(v)
            if old is None or nd < old:
                dist[v] = nd
                pred[v] = (u, eid)
                count[v] = count[u]
                heapq.heappush(heap, (nd, v))
            elif nd == old:
                count[v] = min(2, count[v] + count[u])
    return dist, pred, count


def path_to(pred, target):
    nodes, edges = [target], []
    p = pred[target]
    while p is not None:
        u, eid = p
        edges.append(eid)
        nodes.append(u)
        p = pred[u]
    nodes.reverse()
    edges.reverse()
    return nodes, edges


def reachable(adj, source):
    seen = {source}
    stack = [source]
    while stack:
        u = stack.pop()
        for _, v, _ in adj.get(u, ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen
