"""compare(payload, graph) -> JSON-результат civic-scenario-result-v1.

Модель — длина пути по графу (метры), не время в пути. Политика доступа «strict»:
маршрут строится только по рёбрам access=allowed. Рёбра unknown используются лишь для
диагностики: если путь есть только через них, статус маршрута unknown (а не ok и не unreachable).
Перекрытие блокирует ребро в обоих направлениях на интервале [start_at, end_at).

Статусы пары (origin, destination):
  ok           — путь по allowed-рёбрам найден; length_m — его длина;
  unknown      — пути по allowed нет, но он есть через рёбра с неизвестным доступом
                 (reason=path_only_via_unknown_access) или может проходить вне среза
                 (reason=path_may_exist_outside_graph);
  unreachable  — пути нет внутри известной модели (reason=no_path_within_model). Это свойство
                 модели, а не доказанная физическая недоступность.
Отсутствие пути никогда не равно нулю и не подменяется прямой.
"""
from .canon import sha256_hex
from .graph import PreparedGraph, prepare_graph
from .payload import SCHEMA, active_closed, utc_iso, validate_payload
from .routing import dijkstra, path_to, reachable

RESULT_SCHEMA = "civic-scenario-result-v1"
ENGINE = {"name": "engine.civic_scenarios", "version": "1.1.0", "policy": "strict-allowed-only"}
STRICT = ("allowed",)
EXPLORATORY = ("allowed", "unknown")

ASSUMPTIONS = [
    "metric_is_network_length_m_not_travel_time",
    "closure_blocks_edge_in_both_directions",
    "unknown_access_not_used_for_ok_routes",
    "no_congestion_no_signals_no_turn_costs",
    "scenario_is_hypothesis_not_official_closure",
]
LIMITATIONS = [
    "Нет модели пробок, времени в пути, CO2, аварийности или экономического эффекта.",
    "Сценарий перекрытия — гипотеза пользователя; он не равен официальному решению о перекрытии.",
    "«unreachable» означает отсутствие пути в данной модели графа, а не доказанную потерю доступа на местности.",
    "Средние изменения считаются только по парам, где путь найден и в базовом, и в сравниваемом состоянии.",
]


def _route_set(pg, origins, dests, closed):
    """Маршруты для всех пар при заданном множестве закрытых рёбер."""
    strict = pg.adjacency(STRICT, closed)
    explo = pg.adjacency(EXPLORATORY, closed)
    explo_rev = pg.adjacency(EXPLORATORY, closed, reverse=True) if pg.boundary else None
    rows = []
    back_cache = {}
    for o in origins:
        dist, pred, count = dijkstra(strict, o)
        edist = None
        fwd_boundary = None
        for d in dests:
            row = {"origin_node_id": o, "destination_node_id": d}
            if d in dist:
                nodes, edges = path_to(pred, d)
                row.update(status="ok", length_m=dist[d] / 1000, edge_ids=edges, node_ids=nodes,
                           equal_cost_alternatives=count[d] > 1, reason=None)
            else:
                if edist is None:
                    edist = dijkstra(explo, o)[0]
                row.update(status=None, length_m=None, edge_ids=[], node_ids=[], equal_cost_alternatives=False)
                if d in edist:
                    row.update(status="unknown", reason="path_only_via_unknown_access",
                               length_if_unknown_allowed_m=edist[d] / 1000)
                else:
                    may_outside = False
                    if pg.boundary:
                        if fwd_boundary is None:
                            fwd_boundary = bool(reachable(explo, o) & pg.boundary)
                        if fwd_boundary:
                            if d not in back_cache:
                                back_cache[d] = bool(reachable(explo_rev, d) & pg.boundary)
                            may_outside = back_cache[d]
                    if may_outside:
                        row.update(status="unknown", reason="path_may_exist_outside_graph")
                    else:
                        row.update(status="unreachable", reason="no_path_within_model")
            rows.append(row)
    return rows


def _status_counts(rows):
    c = {"ok": 0, "unknown": 0, "unreachable": 0}
    for r in rows:
        c[r["status"]] += 1
    total = len(rows)
    return {"pairs": total, "by_status": c, "ok_share": round(c["ok"] / total, 4) if total else None}


def _diff(base_rows, rows, closed=frozenset()):
    """Попарное сравнение двух наборов маршрутов (одинаковый порядок пар)."""
    pairs, deltas = [], []
    counts = {"unchanged": 0, "longer": 0, "shorter": 0, "lost_within_model": 0, "became_uncertain": 0,
              "gained": 0, "not_comparable": 0}
    for b, r in zip(base_rows, rows):
        item = {"origin_node_id": b["origin_node_id"], "destination_node_id": b["destination_node_id"],
                "from_status": b["status"], "to_status": r["status"], "delta_m": None}
        if b["status"] == "ok" and r["status"] == "ok":
            delta_mm = round(r["length_m"] * 1000) - round(b["length_m"] * 1000)
            item["delta_m"] = delta_mm / 1000
            item["change"] = "unchanged" if delta_mm == 0 else ("longer" if delta_mm > 0 else "shorter")
            item["route_changed"] = r["edge_ids"] != b["edge_ids"]
            deltas.append(delta_mm)
        elif b["status"] == "ok" and r["status"] == "unreachable":
            item["change"] = "lost_within_model"
        elif b["status"] == "ok" and r["status"] == "unknown":
            item["change"] = "became_uncertain"
        elif b["status"] != "ok" and r["status"] == "ok":
            item["change"] = "gained"
        else:
            item["change"] = "not_comparable"
        if closed and b["status"] == "ok":
            item["baseline_route_uses_closed_edge"] = any(e in closed for e in b["edge_ids"])
        counts[item["change"]] += 1
        pairs.append(item)
    summary = {
        "pairs": len(pairs),
        "comparable_pairs": len(deltas),
        "changes": counts,
        "mean_delta_m_comparable": round(sum(deltas) / len(deltas) / 1000, 3) if deltas else None,
        "max_delta_m_comparable": max(deltas) / 1000 if deltas else None,
        "sum_delta_m_comparable": sum(deltas) / 1000 if deltas else None,
        "note": "средние/суммы только по парам со статусом ok в обоих состояниях; пары без пути не считаются нулём",
    }
    return pairs, summary


def normalized_scenario(norm, payload):
    """Канонический вид сценария: порядок перекрытий и edge_ids не влияет на дайджест."""
    return {
        "schema_version": SCHEMA, "city": payload["city"], "graph_id": payload["graph_id"],
        "graph_digest": payload["graph_digest"], "mode": payload["mode"], "analysis_at_utc": utc_iso(norm["at"]),
        "origin_node_ids": sorted(norm["origins"]), "destination_node_ids": sorted(norm["destinations"]),
        "plans": [{"id": p["id"], "closures": sorted(
            ({"edge_ids": c["edge_ids"], "start_utc": utc_iso(c["start"]), "end_utc": utc_iso(c["end"])}
             for c in p["closures"]), key=lambda c: (c["start_utc"], c["end_utc"], c["edge_ids"]))}
            for p in norm["plans"]],
    }


def _closure_warnings(pg, closed):
    w = []
    non_allowed = sorted(e for e in closed if pg.edges[e][3] != "allowed")
    if non_allowed:
        w.append({"code": "closure_on_non_allowed_edge",
                  "message": "перекрыты рёбра, которые и так не используются в strict-маршрутах (access denied/unknown)",
                  "edge_ids": non_allowed[:50]})
    return w


def compare(payload, graph):
    """Сравнить baseline и планы A/B в момент analysis_at. graph — dict или PreparedGraph."""
    pg = graph if isinstance(graph, PreparedGraph) else prepare_graph(graph)
    norm = validate_payload(payload, pg)
    origins, dests, at = norm["origins"], norm["destinations"], norm["at"]

    base_rows = _route_set(pg, origins, dests, frozenset())
    result_plans, plan_rows = [], {}
    warnings = list(pg.warnings)
    for p in norm["plans"]:
        closed, inactive = active_closed(p, at)
        closed = frozenset(closed)
        rows = base_rows if not closed else _route_set(pg, origins, dests, closed)
        plan_rows[p["id"]] = rows
        pairs, summary = _diff(base_rows, rows, closed)
        pw = _closure_warnings(pg, closed)
        base_used = {e for r in base_rows if r["status"] == "ok" for e in r["edge_ids"]}
        on_base = sorted(closed & base_used)
        if not closed:
            pw.append({"code": "no_active_closures", "message": "в момент analysis_at ни одно перекрытие плана не действует"})
        elif not on_base:
            pw.append({"code": "closure_not_on_baseline_routes",
                       "message": "закрытые участки не лежат на базовых путях выбранных пар — длины не меняются"})
        result_plans.append({
            "id": p["id"],
            "active_closed_edge_ids": sorted(closed),
            "closed_on_baseline_routes": on_base,
            "inactive_closures": sorted(inactive, key=lambda c: (c["start_at"], c["end_at"], c["edge_ids"])),
            "routes": rows,
            "status_summary": _status_counts(rows),
            "vs_baseline": {"pairs": pairs, "summary": summary},
            "warnings": pw,
        })
    a_vs_b = None
    if "A" in plan_rows and "B" in plan_rows:
        pairs, summary = _diff(plan_rows["A"], plan_rows["B"])
        closed_sets = {p["id"]: set(p["active_closed_edge_ids"]) for p in result_plans}
        identical = closed_sets["A"] == closed_sets["B"]
        a_vs_b = {"from_plan": "A", "to_plan": "B", "pairs": pairs, "summary": summary,
                  "identical_active_closures": identical}
        if identical:
            warnings.append({"code": "plans_identical_at_analysis_at",
                             "message": "в момент analysis_at у планов A и B закрыты одни и те же участки — результаты совпадают"})

    unknown_pairs = sum(1 for r in base_rows if r["status"] == "unknown")
    if unknown_pairs:
        warnings.append({"code": "baseline_has_unknown_pairs",
                         "message": f"в базовом состоянии {unknown_pairs} пар без подтверждённого пути (unknown)",
                         "count": unknown_pairs})
    scenario = normalized_scenario(norm, payload)
    result = {
        "schema_version": RESULT_SCHEMA,
        "engine": ENGINE,
        "input": {
            "payload_schema_version": SCHEMA,
            "payload_digest": sha256_hex(payload),
            "scenario_digest": sha256_hex(scenario),
            "city": payload["city"], "graph_id": pg.id, "graph_digest": pg.digest,
            "graph_evidence_type": pg.evidence_type, "mode": pg.mode,
            "analysis_at": payload["analysis_at"], "analysis_at_utc": utc_iso(at),
            "origin_node_ids": origins, "destination_node_ids": dests,
            "interval_rule": "start_at <= analysis_at < end_at",
            "units": {"length": "m", "internal": "integer mm", "delta": "m"},
        },
        "graph_coverage": pg.coverage,
        "baseline": {"routes": base_rows, "status_summary": _status_counts(base_rows)},
        "plans": result_plans,
        "a_vs_b": a_vs_b,
        "warnings": warnings,
        "assumptions": ASSUMPTIONS,
        "limitations": LIMITATIONS,
    }
    result["result_digest"] = sha256_hex({k: v for k, v in result.items() if k != "result_digest"})
    return result
