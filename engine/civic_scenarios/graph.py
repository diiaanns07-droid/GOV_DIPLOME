"""Проверка и индексация графа civic-scenario (CONTRACT.txt, раздел 5).

graph: {id, city, digest, mode, evidence_type,
        nodes:[{id, lon, lat, boundary?}],
        edges:[{id, from, to, length_m, access, oneway, geometry?, source?}]}

Необязательные поля (совместимое расширение, см. research/round-11-results/R07/contract_delta.txt):
  node.boundary: true  — узел на границе среза: за ним сеть есть, но в граф не включена;
  edge.geometry: [[lon,lat],...] — линия ребра для карты (не участвует в расчёте);
  edge.source: {...} — исходные признаки, переносятся без интерпретации;
  graph.source / graph.label / graph.limitations / graph.license — описание происхождения.

Правила: ID — непустые строки, уникальны; length_m — конечное число >= 0
(отрицательное — ошибка; нулевое допускается и попадает в warnings);
access ∈ allowed|denied|unknown; oneway=true — движение только from -> to.
"""
import math

from .canon import graph_digest, length_mm
from .errors import ScenarioError

MODES = ("walking", "driving")
ACCESS = ("allowed", "denied", "unknown")
EVIDENCE = ("observed", "derived", "hypothesis", "synthetic")
MAX_NODES = 200_000
MAX_EDGES = 400_000
MAX_ID_LEN = 200


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _id(v):
    return isinstance(v, str) and 0 < len(v) <= MAX_ID_LEN


def _bad(msg, **fields):
    raise ScenarioError("invalid_graph", msg, fields or None)


class PreparedGraph:
    """Неизменяемый индекс графа. Исходный dict не модифицируется."""

    def __init__(self, graph, node_ids, edges, warnings, coverage):
        self.id = graph["id"]
        self.city = graph["city"]
        self.digest = graph["digest"]
        self.mode = graph["mode"]
        self.evidence_type = graph["evidence_type"]
        self.node_ids = node_ids          # set
        self.boundary = frozenset(n["id"] for n in graph["nodes"] if n.get("boundary") is True)
        self.edges = edges                # dict id -> (from, to, mm, access, oneway)
        self.warnings = warnings
        self.coverage = coverage
        # Координаты узлов — для привязки точки пользователя к сети (snap.py), не для расчёта длины.
        self.coords = {n["id"]: (float(n["lon"]), float(n["lat"])) for n in graph["nodes"]}
        self.bbox = graph.get("bbox") if isinstance(graph.get("bbox"), list) and len(graph.get("bbox")) == 4 else None
        self._adj_cache = {}
        self._snap_cache = None

    def adjacency(self, accesses, closed, reverse=False):
        """Список смежности: node -> [(edge_id, neighbor, mm)], отсортированный по edge_id.

        accesses — допустимые значения access; closed — множество закрытых edge_id (обе стороны).
        """
        key = (tuple(sorted(accesses)), frozenset(closed), reverse)
        adj = self._adj_cache.get(key)
        if adj is not None:
            return adj
        adj = {}
        for eid in sorted(self.edges):
            frm, to, mm, access, oneway = self.edges[eid]
            if access not in accesses or eid in closed:
                continue
            pairs = [(frm, to)] if oneway else [(frm, to), (to, frm)]
            for a, b in pairs:
                if reverse:
                    a, b = b, a
                adj.setdefault(a, []).append((eid, b, mm))
        # A city graph has ~100k edges: retaining 65 alternate closure indexes
        # can exhaust memory. Bound the cache by graph size, not just requests.
        cache_limit = max(2, min(64, 200_000 // max(1, len(self.edges))))
        if len(self._adj_cache) >= cache_limit:
            self._adj_cache.clear()
        self._adj_cache[key] = adj
        return adj


def prepare_graph(graph, check_digest=True):
    if not isinstance(graph, dict):
        _bad("граф должен быть объектом")
    for k in ("id", "city", "digest", "mode", "evidence_type", "nodes", "edges"):
        if k not in graph:
            _bad(f"нет поля {k}", field=k)
    if not _id(graph["id"]):
        _bad("id графа — непустая строка")
    if not isinstance(graph["city"], str) or not graph["city"]:
        _bad("city — непустая строка")
    if graph["mode"] not in MODES:
        _bad("mode — walking|driving", field="mode")
    if graph["evidence_type"] not in EVIDENCE:
        _bad("evidence_type — observed|derived|hypothesis|synthetic", field="evidence_type")
    nodes, edges = graph["nodes"], graph["edges"]
    if not isinstance(nodes, list) or not isinstance(edges, list):
        _bad("nodes/edges — массивы")
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise ScenarioError("too_large", f"граф больше лимита {MAX_NODES} узлов / {MAX_EDGES} рёбер")
    if not isinstance(graph["digest"], str):
        _bad("digest — строка")

    node_ids = set()
    for i, n in enumerate(nodes):
        if not isinstance(n, dict) or not _id(n.get("id")):
            _bad(f"узел #{i}: нужен строковый id", index=i)
        if n["id"] in node_ids:
            _bad(f"повтор ID узла {n['id'][:80]}", node_id=n["id"])
        if not _num(n.get("lon")) or not _num(n.get("lat")) or abs(n["lon"]) > 180 or abs(n["lat"]) > 90:
            _bad(f"узел {n['id'][:80]}: lon/lat — конечные WGS84", node_id=n["id"])
        if "boundary" in n and not isinstance(n["boundary"], bool):
            _bad(f"узел {n['id'][:80]}: boundary — boolean", node_id=n["id"])
        node_ids.add(n["id"])

    out = {}
    zero = 0
    total = {"allowed": 0, "denied": 0, "unknown": 0}
    for i, e in enumerate(edges):
        if not isinstance(e, dict) or not _id(e.get("id")):
            _bad(f"ребро #{i}: нужен строковый id", index=i)
        eid = e["id"]
        if eid in out:
            _bad(f"повтор ID ребра {eid[:80]}", edge_id=eid)
        if e.get("from") not in node_ids or e.get("to") not in node_ids:
            _bad(f"ребро {eid[:80]}: from/to ссылаются на неизвестный узел", edge_id=eid)
        L = e.get("length_m")
        if not _num(L):
            _bad(f"ребро {eid[:80]}: length_m — конечное число", edge_id=eid)
        if L < 0:
            _bad(f"ребро {eid[:80]}: отрицательная длина", edge_id=eid)
        if e.get("access") not in ACCESS:
            _bad(f"ребро {eid[:80]}: access — allowed|denied|unknown", edge_id=eid)
        if not isinstance(e.get("oneway"), bool):
            _bad(f"ребро {eid[:80]}: oneway — boolean", edge_id=eid)
        mm = length_mm(L)
        if mm == 0:
            zero += 1
        total[e["access"]] += mm
        out[eid] = (e["from"], e["to"], mm, e["access"], e["oneway"])

    if check_digest:  # после структурной проверки: NaN/inf уже отклонены как invalid_graph
        try:
            actual = graph_digest(graph)
        except (TypeError, ValueError) as exc:
            _bad(f"граф не сериализуется в канонический JSON: {exc}")
        if actual != graph["digest"]:
            raise ScenarioError("graph_digest_mismatch", "содержимое графа не совпадает с digest",
                                {"expected": graph["digest"], "actual": actual})

    warnings = []
    if zero:
        warnings.append({"code": "zero_length_edges", "message": f"рёбер нулевой длины: {zero}", "count": zero})
    if any(n.get("boundary") is True for n in nodes):
        warnings.append({"code": "graph_is_slice",
                         "message": "граф — срез: за граничными узлами сеть есть, но не моделируется; "
                                    "маршрут через внешнюю сеть может быть короче, а «нет пути» — не доказано"})
    all_mm = sum(total.values())
    coverage = {
        "edges": len(out),
        "nodes": len(node_ids),
        "length_m_by_access": {k: v / 1000 for k, v in total.items()},
        "known_access_share_by_length": None if all_mm == 0 else round((total["allowed"] + total["denied"]) / all_mm, 4),
    }
    return PreparedGraph(graph, node_ids, out, warnings, coverage)
