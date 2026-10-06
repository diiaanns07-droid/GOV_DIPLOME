"""Детерминированно собрать демонстрационный кейс на срезе K03 (гипотетические перекрытия).

Старты — 3 узла allowed-сети у западного края bbox, цели — 6 узлов у восточного края (внутри bbox,
наибольшая компонента allowed). План A перекрывает 2 средних ребра базового пути первой пары,
план B — 6 рёбер вокруг середины того же пути на другом интервале. Это гипотеза для демонстрации,
не официальное перекрытие и не реальное событие.

    python3 research/round-11-results/R07/make_k03_case.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from engine.civic_scenarios.registry import CASES, load_graph, load_graph_dict  # noqa: E402
from engine.civic_scenarios.routing import dijkstra, path_to, reachable  # noqa: E402

g = load_graph_dict("k03-astana-pedestrian-r10")
pg = load_graph("k03-astana-pedestrian-r10")
W, S, E, N = g["bbox"]
pos = {n["id"]: (n["lon"], n["lat"]) for n in g["nodes"]}
adj = pg.adjacency(("allowed",), frozenset())
inside = [n for n in sorted(adj) if W <= pos[n][0] <= E and S <= pos[n][1] <= N]
comp = max((reachable(adj, n) for n in inside[::50]), key=len)
cand = [n for n in inside if n in comp]
origins = sorted(cand, key=lambda n: (pos[n][0], n))[:400:130][:3]
dests = sorted(cand, key=lambda n: (-pos[n][0], n))[:600:100][:6]
dist, pred, _ = dijkstra(adj, origins[0])
_, path_edges = path_to(pred, dests[0])
mid = len(path_edges) // 2
plan_a = path_edges[mid - 1:mid + 1]
plan_b = path_edges[max(0, mid - 6):mid - 3] + path_edges[mid + 3:mid + 6]
case = {
    "case_id": "k03-astana-demo-v1",
    "title": "Центр Астаны (срез K03, пешеход): гипотетические перекрытия A и B",
    "evidence_type": "hypothesis",
    "note": "Перекрытия выбраны алгоритмом на кратчайшем пути для демонстрации метода; это не официальное "
            "и не реальное перекрытие. Граф — производная OSM/Overture (ODbL), пешеходный режим.",
    "generator": "research/round-11-results/R07/make_k03_case.py",
    "payload": {
        "schema_version": "civic-scenario-v1", "city": "astana", "graph_id": g["id"], "graph_digest": g["digest"],
        "mode": "walking", "analysis_at": "2026-10-10T12:00:00+05:00",
        "origin_node_ids": origins, "destination_node_ids": dests,
        "plans": [
            {"id": "A", "closures": [{"edge_ids": plan_a, "start_at": "2026-10-10T08:00:00+05:00", "end_at": "2026-10-10T20:00:00+05:00"}]},
            {"id": "B", "closures": [{"edge_ids": plan_b, "start_at": "2026-10-10T10:00:00+05:00", "end_at": "2026-10-11T10:00:00+05:00"}]},
        ],
    },
}
(CASES / "k03-astana-demo-v1.case.json").write_text(json.dumps(case, ensure_ascii=False, indent=1) + "\n", "utf-8")
print(origins, dests, len(path_edges), plan_a, len(plan_b))
