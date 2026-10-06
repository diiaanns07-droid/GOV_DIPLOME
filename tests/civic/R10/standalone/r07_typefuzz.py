"""R10 type-fuzz of R07 POST /scenarios/compare handler (C06: malformed input -> 4xx JSON, never an exception/500).

Run in an isolated interpreter against a pinned checkout:
  cd <root> && python3 -I -B tests/civic/R10/standalone/r07_typefuzz.py <root>
Prints how many of ~210 malformed payloads escaped as exceptions or 5xx.
"""
import json, sys, copy
root = sys.argv[1]
sys.path.insert(0, root)
from engine.civic_scenarios import http as h
from engine.civic_scenarios.registry import list_cases
case = [c for c in list_cases() if "synthetic" in json.dumps(c)][0]
base = case.get("payload") or case
assert isinstance(base, dict), list(case)[:10]
ok = h.handle("POST", "/api/civic/v1/scenarios/compare", None, copy.deepcopy(base))
print("baseline:", ok["status"], list(ok["body"].get("data", {}))[:12])
weird = [None, 1, 1.5, True, "x", "", [], {}, [1], [None], {"a": 1}, float("nan"), "2026-13-45T99:99", -1, 10**30]
fields = ["schema_version","city","graph_id","graph_digest","mode","analysis_at","origin_node_ids","destination_node_ids","plans"]
escaped = []
for f in fields:
    for w in weird:
        p = copy.deepcopy(base); p[f] = w
        try:
            r = h.handle("POST", "/api/civic/v1/scenarios/compare", None, p)
            if r["status"] >= 500: escaped.append((f, repr(w), r["status"]))
        except Exception as e:
            escaped.append((f, repr(w), type(e).__name__ + ": " + str(e)[:80]))
# nested: plans/closures shapes
nested = []
for w in weird:
    p = copy.deepcopy(base); p["plans"] = [w]; nested.append(("plans[0]", p))
    p = copy.deepcopy(base); p["plans"] = [{"id": "A", "closures": [w]}]; nested.append(("plans[0].closures[0]", p))
    p = copy.deepcopy(base); p["plans"] = [{"id": "A", "closures": [{"edge_ids": w, "start_at": "2026-10-15T08:00:00+05:00", "end_at": "2026-10-15T10:00:00+05:00"}]}]; nested.append(("closures.edge_ids", p))
    p = copy.deepcopy(base); p["plans"] = [{"id": "A", "closures": [{"edge_ids": [], "start_at": w, "end_at": w}]}]; nested.append(("closures.start/end", p))
    p = copy.deepcopy(base); p["origin_node_ids"] = [w]; nested.append(("origin_node_ids[0]", p))
for name, p in nested:
    try:
        r = h.handle("POST", "/api/civic/v1/scenarios/compare", None, p)
        if r["status"] >= 500: escaped.append((name, "", r["status"]))
    except Exception as e:
        escaped.append((name, json.dumps(p.get("plans"), default=str)[:90] if "plan" in name or "closure" in name else str(p.get("origin_node_ids"))[:60], type(e).__name__ + ": " + str(e)[:80]))
print("total probes:", len(fields)*len(weird) + len(nested), "escaped:", len(escaped))
for e in escaped[:40]: print("  ", e)
