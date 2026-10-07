import json, random, sys, time
sys.path.insert(0, sys.argv[1])
from engine.civic_scenarios import compare
from engine.civic_scenarios.registry import list_cases, load_graph
out = {}
t = time.perf_counter()
for c in list_cases():
    out[c["case_id"]] = compare(c["payload"], load_graph(c["payload"]["graph_id"]))["result_digest"]
pg = load_graph("osm-astana-walking-20260506")
case = next(c for c in list_cases() if c["case_id"] == "astana-baiterek-khanshatyr-v1")
rnd = random.Random(7)
base_route = compare(case["payload"], pg)["baseline"]["routes"][0]["edge_ids"]
allowed = sorted(e for e, v in pg.edges.items() if v[3] == "allowed")
for i in range(6):
    p = json.loads(json.dumps(case["payload"]))
    p["destination_node_ids"] = p["destination_node_ids"] + ["osm-n12828087928", "osm-n8111070301"]   # Ак Орда, вокзал (фрагмент)
    p["plans"][0]["closures"][0]["edge_ids"] = sorted(set(rnd.sample(base_route, 3) + rnd.sample(allowed, 50)))
    p["plans"][1]["closures"][0]["edge_ids"] = sorted(set(rnd.sample(base_route, 6)))
    out["random%d" % i] = compare(p, pg)["result_digest"]
print(json.dumps({"digests": out, "seconds": round(time.perf_counter() - t, 1)}))
