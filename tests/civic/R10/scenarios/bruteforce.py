"""R10 brute-force reference for civic-scenario-v1 (CONTRACT section 5). Deliberately NOT Dijkstra.

Enumerates EVERY simple path (exhaustive DFS) from origin to destination over the edges that are
open at analysis_at, then takes the minimum of exact Decimal sums. Status rule (strict policy):
  ok          - some path uses only access=allowed edges; length_m = min over those paths;
  unknown     - no allowed-only path, but a path exists when access=unknown edges are also used;
  unreachable - no path even with unknown edges (denied edges are never traversable).
A closure blocks its edges in both directions while start_at <= analysis_at < end_at (absolute
instants, explicit offsets). Only for tiny graphs: the path count is exponential.
`variant` switches on one deliberate bug so the suite can prove its cases would catch it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json

VARIANTS = ("unknown_as_allowed", "ignore_oneway", "ignore_closures", "string_time_compare",
            "end_inclusive", "denied_as_allowed")


def canonical_digest(graph: dict) -> str:
    body = {k: v for k, v in graph.items() if k != "digest"}
    try:
        text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except ValueError:  # NaN/Infinity: only in deliberately broken error-case graphs
        text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def instant(text: str) -> datetime:
    value = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    if value.utcoffset() is None:
        raise ValueError(f"timestamp without offset: {text}")
    return value


def closed_edges(plan: dict, analysis_at: str, variant: str | None = None) -> set:
    at, closed = instant(analysis_at), set()
    for c in plan["closures"]:
        if variant == "ignore_closures":
            continue
        if variant == "string_time_compare":
            active = c["start_at"] <= analysis_at < c["end_at"]
        elif variant == "end_inclusive":
            active = instant(c["start_at"]) <= at <= instant(c["end_at"])
        else:
            active = instant(c["start_at"]) <= at < instant(c["end_at"])
        if active:
            closed.update(c["edge_ids"])
    return closed


def all_simple_paths(graph: dict, origin: str, dest: str, closed: set, accesses: set, variant=None):
    """Yield (edge_id list, Decimal length) for every simple path; exhaustive DFS, no pruning."""
    out = {}
    for e in graph["edges"]:
        if e["id"] in closed or e["access"] not in accesses:
            continue
        both = variant == "ignore_oneway" or not e["oneway"]
        steps = [(e["from"], e["to"])] + ([(e["to"], e["from"])] if both else [])
        for a, b in steps:
            out.setdefault(a, []).append((e["id"], b, Decimal(repr(e["length_m"]))))
    stack = [(origin, [origin], [], Decimal(0))]
    while stack:
        node, seen, edges, total = stack.pop()
        if node == dest:
            yield edges, total
            continue
        for eid, nxt, length in out.get(node, ()):
            if nxt not in seen:
                stack.append((nxt, seen + [nxt], edges + [eid], total + length))


def route(graph, origin, dest, closed, variant=None) -> dict:
    strict = {"allowed", "unknown"} if variant == "unknown_as_allowed" else {"allowed"}
    if variant == "denied_as_allowed":
        strict = {"allowed", "denied"}
    paths = list(all_simple_paths(graph, origin, dest, closed, strict, variant))
    if paths:
        best = min(total for _, total in paths)
        minimal = sorted(edges for edges, total in paths if total == best)
        return {"status": "ok", "length": best, "minimal_paths": minimal}
    if any(True for _ in all_simple_paths(graph, origin, dest, closed, strict | {"unknown"}, variant)):
        return {"status": "unknown", "length": None, "minimal_paths": []}
    return {"status": "unreachable", "length": None, "minimal_paths": []}


def evaluate(graph: dict, payload: dict, variant: str | None = None) -> dict:
    """{'baseline'|plan_id: {'o>d': route}} for every origin x destination pair."""
    states = {"baseline": set()}
    for plan in payload["plans"]:
        states[plan["id"]] = closed_edges(plan, payload["analysis_at"], variant)
    return {name: {f"{o}>{d}": route(graph, o, d, closed, variant)
                   for o in payload["origin_node_ids"] for d in payload["destination_node_ids"]}
            for name, closed in states.items()}
