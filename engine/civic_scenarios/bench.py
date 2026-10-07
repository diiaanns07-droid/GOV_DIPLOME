"""Замер производительности R07 на текущем графе (справочно: зависит от машины; не обещание real-time).

    python -m engine.civic_scenarios.bench [--repeat 5] [--out FILE]

Холодно = в новом процессе: чтение файла + проверка sha256/digest + индекс (prepare_graph).
Тепло = повтор в том же процессе (граф и смежность уже в кэше). Пример — кейс RUN (1 пара, A/B).
"""
import argparse
import copy
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

GRAPH_ID = "osm-astana-walking-20260506"


def measure(repeat):
    from .compare import compare
    from .example import CASE
    from .registry import load_graph, load_graph_dict, manifest
    from .snap import snap_index, snap_point
    out = {}
    t = time.perf_counter(); g = load_graph_dict(GRAPH_ID); out["load_graph_dict_s"] = round(time.perf_counter() - t, 3)
    t = time.perf_counter(); pg = load_graph(GRAPH_ID); out["prepare_graph_cold_s"] = round(time.perf_counter() - t, 3)
    t = time.perf_counter(); snap_index(pg); out["snap_index_build_s"] = round(time.perf_counter() - t, 3)
    case = json.loads(CASE.read_text("utf-8"))
    t = time.perf_counter(); [snap_point(pg, *p["input"]) for p in case["places"].values()]; out["snap_2_points_ms"] = round((time.perf_counter() - t) * 1000, 2)
    runs = []
    for i in range(repeat):
        p = copy.deepcopy(case["payload"])
        if i == 0:
            pg._adj_cache.clear()
        t = time.perf_counter(); compare(p, pg); runs.append(time.perf_counter() - t)
    out["compare_first_s"] = round(runs[0], 3)
    out["compare_warm_median_s"] = round(statistics.median(runs[1:]), 3) if len(runs) > 1 else None
    # Худший случай: цель во фрагменте сети (нет пути) — полный обход сети и проверка границы выгрузки.
    station = snap_point(pg, 71.5330, 51.1105)["node_id"]
    worst = []
    for _ in range(max(2, repeat)):
        p = copy.deepcopy(case["payload"]); p["destination_node_ids"] = p["destination_node_ids"] + [station]
        t = time.perf_counter(); compare(p, pg); worst.append(time.perf_counter() - t)
    out["compare_unreachable_target_median_s"] = round(statistics.median(worst), 3)
    # граф целиком в браузер: сериализация ответа GET /scenarios/graphs/{id}
    t = time.perf_counter(); body = json.dumps({"ok": True, "data": {"graph": g}}, ensure_ascii=False).encode("utf-8"); out["graph_response_serialize_s"] = round(time.perf_counter() - t, 3)
    out["graph_response_bytes"] = len(body)
    entry = next(x for x in manifest()["graphs"] if x["id"] == GRAPH_ID)
    out.update(graph_id=GRAPH_ID, nodes=entry["nodes"], edges=entry["edges"], digest=entry["digest"], pairs=1, plans=2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--out")
    ap.add_argument("--child", action="store_true")
    a = ap.parse_args(argv)
    if a.child:
        print(json.dumps(measure(a.repeat)))
        return 0
    cold = [json.loads(subprocess.run([sys.executable, "-m", "engine.civic_scenarios.bench", "--child", "--repeat", str(a.repeat)],
                                      check=True, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2]).stdout) for _ in range(3)]
    keys = [k for k, v in cold[0].items() if isinstance(v, float)]
    res = {"runs_new_process": 3, "repeat_compare_per_process": a.repeat,
           "median": {k: statistics.median(c[k] for c in cold) for k in keys},
           "graph": {k: cold[0][k] for k in ("graph_id", "nodes", "edges", "digest", "graph_response_bytes", "pairs", "plans")},
           "env": {"python": platform.python_version(), "machine": platform.machine(), "cpus": os.cpu_count(), "system": platform.system()},
           "note": "Справочный замер в облачном контейнере; браузерная загрузка графа и отрисовка — отдельно (browser_r07_r13.json)."}
    text = json.dumps(res, ensure_ascii=False, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
