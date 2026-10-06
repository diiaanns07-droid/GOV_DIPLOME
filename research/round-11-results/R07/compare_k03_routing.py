"""Сверка engine.civic_scenarios с существующей K03 routing.js (снимок b2cb2e0) на совпадающих условиях.

Условия совпадения: точки = узлы графа внутри bbox, инцидентные ребру нужной политики (привязка 0 мм),
без перекрытий. strict(K03) <-> allowed-only(R07); exploratory(K03) <-> allowed+unknown(R07).
routing.js и исходный граф читаются из git-объектов во временный каталог; ничего не переписывается.

    python3 research/round-11-results/R07/compare_k03_routing.py [--pairs 400] [--seed 11]
"""
import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from engine.civic_scenarios.compare import EXPLORATORY, STRICT  # noqa: E402
from engine.civic_scenarios.registry import load_graph, load_graph_dict  # noqa: E402
from engine.civic_scenarios.routing import dijkstra  # noqa: E402

SRC = "b2cb2e02c602c166ba6d47c02d8e902e5478c791"
RUNNER = r"""
const fs = require("fs"), crypto = require("crypto");
const R = require(process.argv[2]);
const g = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const G = R.prepare(g, { sha256hex: (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex") });
const jobs = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const out = jobs.map(([pol, o, t]) => { const r = R.route(G, o, t, pol); return [r.status, r.distance_mm, r.reason]; });
process.stdout.write(JSON.stringify(out));
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=400)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    civic = load_graph_dict("k03-astana-pedestrian-r10")
    pg = load_graph("k03-astana-pedestrian-r10")
    W, S, E, N = civic["bbox"]
    pos = {n["id"]: (n["lon"], n["lat"]) for n in civic["nodes"]}
    inside = {i for i, (x, y) in pos.items() if W <= x <= E and S <= y <= N}
    inc = {"strict": set(), "exploratory": set()}
    for e in civic["edges"]:
        for k, acc in (("strict", STRICT), ("exploratory", EXPLORATORY)):
            if e["access"] in acc:
                inc[k].update((e["from"], e["to"]))
    rnd = random.Random(a.seed)
    jobs, mine = [], []
    for pol, acc in (("strict", STRICT), ("exploratory", EXPLORATORY)):
        cand = sorted(inc[pol] & inside)
        adj = pg.adjacency(acc, frozenset())
        origins = rnd.sample(cand, 20)
        for o in origins:
            dist = dijkstra(adj, o)[0]
            for t in rnd.sample(cand, a.pairs // 40):
                jobs.append(["pedestrian-v1-" + pol, {"id": o, "lon": pos[o][0], "lat": pos[o][1]},
                             {"id": t, "lon": pos[t][0], "lat": pos[t][1]}])
                mine.append(dist.get(t))
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for name, path in (("routing.js", "web/govtech/k03/routing.js"), ("g.json", "web/govtech/k03/astana.graph.json")):
            (td / name).write_bytes(subprocess.run(["git", "show", f"{SRC}:{path}"], cwd=ROOT, check=True,
                                                   capture_output=True).stdout)
        (td / "jobs.json").write_text(json.dumps(jobs))
        (td / "run.cjs").write_text(RUNNER)
        res = json.loads(subprocess.run(["node", str(td / "run.cjs"), str(td / "routing.js"), str(td / "g.json"),
                                         str(td / "jobs.json")], check=True, capture_output=True, text=True).stdout)
    stats = {"strict": {"pairs": 0, "both_ok_equal": 0, "both_ok_diff": 0, "status_mismatch": 0, "both_no_path": 0},
             "exploratory": {"pairs": 0, "both_ok_equal": 0, "both_ok_diff": 0, "status_mismatch": 0, "both_no_path": 0}}
    mismatches = []
    for (pol, o, t), m, (st, dmm, reason) in zip(jobs, mine, res):
        k = pol.split("-")[-1]
        s = stats[k]
        s["pairs"] += 1
        if st == "ok" and m is not None:
            if dmm == m:
                s["both_ok_equal"] += 1
            else:
                s["both_ok_diff"] += 1
                mismatches.append([pol, o["id"], t["id"], dmm, m])
        elif st != "ok" and m is None:
            s["both_no_path"] += 1
        else:
            s["status_mismatch"] += 1
            mismatches.append([pol, o["id"], t["id"], st, reason, m])
    out = {"source_commit": SRC, "graph_id": civic["id"], "graph_digest": civic["digest"], "seed": a.seed,
           "conditions": "node-to-node inside bbox, no closures; K03 snap distance 0",
           "stats": stats, "mismatches": mismatches[:50],
           "verdict": "PASS" if not mismatches else "FAIL"}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
