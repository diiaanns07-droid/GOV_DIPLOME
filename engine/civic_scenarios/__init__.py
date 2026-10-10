"""R07 — воспроизводимый симулятор последствий перекрытий (civic-scenario-v1, CONTRACT.txt раздел 5).

    compare(payload, graph)        -> civic-scenario-result-v1 (baseline, планы A/B, сравнение)
    timeline(payload, graph, window_start, window_end) -> расписание по всем границам интервалов (stretch)
    prepare_graph(graph)           -> проверенный индекс графа (ScenarioError при ошибке)
    load_graph(graph_id)           -> граф из реестра разрешённых graph_id (без путей от клиента)
    handle(method, path, query, body) -> HTTP-адаптер /api/civic/v1/scenarios/* для R01

Только стандартная библиотека. Подробности: engine/civic_scenarios/README.md.
"""
from .canon import canonical_json, graph_digest, sha256_hex
from .compare import compare
from .snap import SNAP_MAX_M, snap_point
from .timeline import timeline
from .errors import ScenarioError
from .graph import prepare_graph

__all__ = ["compare", "timeline", "snap_point", "SNAP_MAX_M", "prepare_graph", "ScenarioError", "canonical_json", "graph_digest", "sha256_hex"]
