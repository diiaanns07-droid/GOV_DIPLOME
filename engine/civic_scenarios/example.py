"""Воспроизводимый пример для RUN.txt: места на карте -> узлы сети -> база / A / B на снимке OSM.

    python -m engine.civic_scenarios.example            # напечатать значения
    python -m engine.civic_scenarios.example --check    # сверить с ожиданиями в кейсе (код выхода 1 при расхождении)

Ожидания записаны в cases/astana-baiterek-khanshatyr-v1.case.json ("expected") и получены этим же
движком (engine 1.1.0) на графе osm-astana-walking-20260506 — это проверка воспроизводимости, а не
независимое измерение на местности. Перекрытия вымышленные (гипотеза), длина — пешая, не время.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

from .compare import ENGINE, compare
from .registry import load_graph
from .snap import snap_point

CASE = Path(__file__).resolve().parent / "cases" / "astana-baiterek-khanshatyr-v1.case.json"
LATE = "2026-10-10T21:00:00+05:00"   # A уже закончилось (до 20:00), B ещё действует (до 08:00 следующего дня)


def run(case=None):
    case = case or json.loads(CASE.read_text("utf-8"))
    payload = case["payload"]
    pg = load_graph(payload["graph_id"])
    snaps = {k: snap_point(pg, *v["input"]) for k, v in case["places"].items()}
    result = compare(payload, pg)
    late = compare(dict(copy.deepcopy(payload), analysis_at=LATE), pg)
    base = result["baseline"]["routes"][0]
    plans = {p["id"]: p for p in result["plans"]}
    late_plans = {p["id"]: p for p in late["plans"]}
    return {
        "engine_version": ENGINE["version"], "graph_id": pg.id, "graph_digest": pg.digest,
        "snap": {k: {"node_id": s["node_id"], "distance_m": s["distance_m"], "status": s["status"]} for k, s in snaps.items()},
        "baseline_length_m": base["length_m"],
        "plan_length_m": {k: p["routes"][0]["length_m"] for k, p in plans.items()},
        "delta_vs_baseline_m": {k: p["vs_baseline"]["pairs"][0]["delta_m"] for k, p in plans.items()},
        "b_minus_a_m": result["a_vs_b"]["pairs"][0]["delta_m"],
        "late": {"analysis_at": LATE, "active": {k: bool(p["active_closed_edge_ids"]) for k, p in late_plans.items()},
                 "plan_length_m": {k: p["routes"][0]["length_m"] for k, p in late_plans.items()}},
        "result_digest": result["result_digest"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    case = json.loads(CASE.read_text("utf-8"))
    got = run(case)
    print(json.dumps(got, ensure_ascii=False, indent=1))
    if args.check:
        want = case["expected"]
        bad = sorted(k for k in want if want[k] != got.get(k))
        print("CHECK", "PASS" if not bad else "FAIL " + ", ".join(bad))
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
