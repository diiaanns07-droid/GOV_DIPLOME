"""STRETCH: оба расписания по всем моментам изменения ограничений в окне [window_start, window_end).

Окно режется на отрезки по всем start_at/end_at перекрытий; внутри отрезка набор закрытых рёбер
постоянен, поэтому маршруты считаются один раз на отрезок (с кэшем по набору рёбер).
Для каждой пары и плана (относительно baseline):
  hours_lost_within_model  — часы, когда в baseline путь есть (ok), а в плане unreachable;
  hours_became_uncertain   — часы, когда baseline ok, а в плане unknown;
  hours_comparable         — часы, когда ok в обоих;
  extra_length_m_h         — ∫ (длина плана − длина baseline) dt по сравнимым часам, единица м·ч;
  max_extra_length_m       — максимум добавочной длины по сравнимым отрезкам, м.
Метры и часы не складываются в общий «балл». Это длина пути, а не задержка во времени.
"""
from .canon import sha256_hex
from .compare import RESULT_SCHEMA, _diff, _route_set
from .graph import PreparedGraph, prepare_graph
from .payload import active_closed, parse_ts, utc_iso, validate_payload
from .errors import ScenarioError

MAX_WINDOW_H = 24 * 366


def timeline(payload, graph, window_start, window_end):
    pg = graph if isinstance(graph, PreparedGraph) else prepare_graph(graph)
    norm = validate_payload(payload, pg)
    ws, we = parse_ts(window_start, "window_start"), parse_ts(window_end, "window_end")
    if ws >= we:
        raise ScenarioError("invalid_payload", "window_start должен быть раньше window_end")
    if (we - ws).total_seconds() / 3600 > MAX_WINDOW_H:
        raise ScenarioError("too_large", "окно больше 366 суток")
    origins, dests = norm["origins"], norm["destinations"]
    base_rows = _route_set(pg, origins, dests, frozenset())
    cache = {frozenset(): base_rows}

    plans_out = []
    for p in norm["plans"]:
        cuts = {ws, we}
        for c in p["closures"]:
            for t in (c["start"], c["end"]):
                if ws < t < we:
                    cuts.add(t)
        cuts = sorted(cuts)
        per_pair = {(r["origin_node_id"], r["destination_node_id"]): {
            "origin_node_id": r["origin_node_id"], "destination_node_id": r["destination_node_id"],
            "baseline_status": r["status"], "hours_lost_within_model": 0.0, "hours_became_uncertain": 0.0,
            "hours_comparable": 0.0, "extra_length_m_h": 0.0, "max_extra_length_m": None} for r in base_rows}
        segments = []
        for t0, t1 in zip(cuts, cuts[1:]):
            closed, _ = active_closed(p, t0)
            closed = frozenset(closed)
            if closed not in cache:
                cache[closed] = _route_set(pg, origins, dests, closed)
            pairs, summary = _diff(base_rows, cache[closed])
            h = (t1 - t0).total_seconds() / 3600
            for it in pairs:
                acc = per_pair[(it["origin_node_id"], it["destination_node_id"])]
                if it["change"] == "lost_within_model":
                    acc["hours_lost_within_model"] += h
                elif it["change"] == "became_uncertain":
                    acc["hours_became_uncertain"] += h
                elif it["delta_m"] is not None:
                    acc["hours_comparable"] += h
                    acc["extra_length_m_h"] += it["delta_m"] * h
                    if acc["max_extra_length_m"] is None or it["delta_m"] > acc["max_extra_length_m"]:
                        acc["max_extra_length_m"] = it["delta_m"]
            segments.append({"start_utc": utc_iso(t0), "end_utc": utc_iso(t1), "duration_h": round(h, 6),
                             "active_closed_edge_ids": sorted(closed), "changes": summary["changes"]})
        rows = list(per_pair.values())
        for r in rows:
            for k in ("hours_lost_within_model", "hours_became_uncertain", "hours_comparable", "extra_length_m_h"):
                r[k] = round(r[k], 6)
        plans_out.append({
            "id": p["id"], "segments": segments, "pairs": rows,
            "totals": {
                "pair_hours_lost_within_model": round(sum(r["hours_lost_within_model"] for r in rows), 6),
                "pair_hours_became_uncertain": round(sum(r["hours_became_uncertain"] for r in rows), 6),
                "extra_length_m_h": round(sum(r["extra_length_m_h"] for r in rows), 6),
                "pairs_with_any_loss": sum(1 for r in rows if r["hours_lost_within_model"] > 0),
                "units": {"pair_hours": "пара·ч", "extra_length_m_h": "м·ч"},
            },
        })
    result = {
        "schema_version": RESULT_SCHEMA + "+timeline",
        "input": {"payload_digest": sha256_hex(payload), "graph_id": pg.id, "graph_digest": pg.digest, "mode": pg.mode,
                  "window_start_utc": utc_iso(ws), "window_end_utc": utc_iso(we),
                  "interval_rule": "start_at <= t < end_at"},
        "baseline_status": {f"{r['origin_node_id']}>{r['destination_node_id']}": r["status"] for r in base_rows},
        "plans": plans_out,
        "note": "м·ч и пара·ч — разные величины; общий балл не вычисляется. Длина пути, не время в пути.",
    }
    result["result_digest"] = sha256_hex({k: v for k, v in result.items() if k != "result_digest"})
    return result
