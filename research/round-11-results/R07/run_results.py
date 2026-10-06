"""Воспроизводимые результаты R07: входы, выходы, дайджесты, замер времени, карточка A/B.

    python3 research/round-11-results/R07/run_results.py
Пишет results/*.json, AB_CARD.md, bench.json в этом каталоге. Время — справочно (зависит от машины).
"""
import json
import platform
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from engine.civic_scenarios import compare, timeline  # noqa: E402
from engine.civic_scenarios.registry import CASES, load_graph, load_graph_dict  # noqa: E402
from engine.civic_scenarios.routing import reachable  # noqa: E402

OUT = HERE / "results"
OUT.mkdir(exist_ok=True)
WINDOWS = {"synthetic-tiny-v1-demo": ("2026-10-07T00:00:00+05:00", "2026-10-09T00:00:00+05:00"),
           "k03-astana-demo-v1": ("2026-10-10T00:00:00+05:00", "2026-10-12T00:00:00+05:00")}


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", "utf-8")


def card(case, r, tl):
    L = [f"# Карточка A/B — {case['title']}", "",
         f"- Статус данных: **{case['evidence_type']}**; граф `{r['input']['graph_id']}` ({r['input']['graph_evidence_type']}), режим **{r['input']['mode']}**",
         f"- Момент анализа: {r['input']['analysis_at']} (UTC {r['input']['analysis_at_utc']}); правило `{r['input']['interval_rule']}`",
         f"- graph_digest `{r['input']['graph_digest'][:16]}…`, scenario_digest `{r['input']['scenario_digest'][:16]}…`, result_digest `{r['result_digest'][:16]}…`",
         f"- {case['note']}", "",
         "| | База | План A | План B |", "|---|---|---|---|"]
    plans = {p["id"]: p for p in r["plans"]}
    bs = r["baseline"]["status_summary"]["by_status"]
    L.append("| пар ok / unknown / unreachable | " + " | ".join(
        f"{x['ok']} / {x['unknown']} / {x['unreachable']}" for x in [bs] + [plans[k]["status_summary"]["by_status"] for k in "AB"]) + " |")
    L.append("| рёбер закрыто в момент анализа | 0 | " + " | ".join(str(len(plans[k]["active_closed_edge_ids"])) for k in "AB") + " |")
    for key, lab in (("comparable_pairs", "сопоставимых пар с базой"), ("mean_delta_m_comparable", "средний прирост длины, м"),
                     ("max_delta_m_comparable", "макс. прирост длины, м")):
        L.append(f"| {lab} | — | " + " | ".join(str(plans[k]["vs_baseline"]["summary"][key]) for k in "AB") + " |")
    for key, lab in (("longer", "пар удлинилось"), ("lost_within_model", "пар потеряли путь (в модели)"), ("became_uncertain", "пар стали unknown")):
        L.append(f"| {lab} | — | " + " | ".join(str(plans[k]["vs_baseline"]["summary"]["changes"][key]) for k in "AB") + " |")
    tp = {p["id"]: p["totals"] for p in tl["plans"]}
    L.append(f"| за окно {tl['input']['window_start_utc']}…{tl['input']['window_end_utc']}: добавочная длина, м·ч | — | "
             + " | ".join(str(tp[k]["extra_length_m_h"]) for k in "AB") + " |")
    L.append("| за окно: потеря пути, пара·ч | — | " + " | ".join(str(tp[k]["pair_hours_lost_within_model"]) for k in "AB") + " |")
    if r["a_vs_b"]:
        s = r["a_vs_b"]["summary"]
        L += ["", f"**B относительно A:** сопоставимых {s['comparable_pairs']}, средняя разница {s['mean_delta_m_comparable']} м, "
                  f"B длиннее в {s['changes']['longer']}, короче в {s['changes']['shorter']}, потеря пути {s['changes']['lost_within_model']}."]
    L += ["", "Ограничения:"] + [f"- {x}" for x in r["limitations"]] + ["", "Предупреждения:"] + [f"- {w['message']}" for w in r["warnings"]] + [""]
    return "\n".join(L)


def bench():
    g = load_graph_dict("k03-astana-pedestrian-r10")
    t0 = time.perf_counter()
    from engine.civic_scenarios.graph import prepare_graph
    pg = prepare_graph(g)
    prep = time.perf_counter() - t0
    adj = pg.adjacency(("allowed",), frozenset())
    comp = sorted(max((reachable(adj, n) for n in sorted(adj)[::100]), key=len))
    allowed = sorted(e["id"] for e in g["edges"] if e["access"] == "allowed")
    p = {"schema_version": "civic-scenario-v1", "city": "astana", "graph_id": g["id"], "graph_digest": g["digest"], "mode": "walking",
         "analysis_at": "2026-10-10T12:00:00+05:00", "origin_node_ids": comp[:25], "destination_node_ids": comp[-40:],
         "plans": [{"id": "A", "closures": [{"edge_ids": allowed[:200], "start_at": "2026-10-10T08:00:00+05:00", "end_at": "2026-10-10T20:00:00+05:00"}]},
                   {"id": "B", "closures": [{"edge_ids": allowed[200:400], "start_at": "2026-10-10T08:00:00+05:00", "end_at": "2026-10-10T20:00:00+05:00"}]}]}
    runs = []
    for _ in range(5):
        pg._adj_cache.clear()
        t = time.perf_counter()
        compare(p, pg)
        runs.append(time.perf_counter() - t)
    return {"graph": g["id"], "nodes": len(g["nodes"]), "edges": len(g["edges"]), "pairs": 25 * 40, "closed_edges_per_plan": 200,
            "prepare_graph_s_incl_digest": round(prep, 3), "compare_s_runs": [round(x, 3) for x in runs],
            "compare_s_median": round(statistics.median(runs), 3), "python": platform.python_version(), "machine": platform.machine(),
            "note": "1000 пар = максимальный лимит payload (25 стартов × 40 целей); 3 набора маршрутов (база, A, B)."}


def main():
    index = []
    for path in sorted(CASES.glob("*.case.json")):
        case = json.loads(path.read_text("utf-8"))
        payload = case["payload"]
        pg = load_graph(payload["graph_id"])
        r = compare(payload, pg)
        ws, we = WINDOWS[case["case_id"]]
        tl = timeline(payload, pg, ws, we)
        assert compare(json.loads(json.dumps(payload)), pg)["result_digest"] == r["result_digest"]  # повтор = тот же digest
        dump(f"{case['case_id']}.input.json", payload)
        dump(f"{case['case_id']}.result.json", r)
        dump(f"{case['case_id']}.timeline.json", tl)
        (HERE / f"AB_CARD_{case['case_id']}.md").write_text(card(case, r, tl), "utf-8")
        index.append({"case_id": case["case_id"], "evidence_type": case["evidence_type"], "graph_id": payload["graph_id"],
                      "graph_digest": payload["graph_digest"], "payload_digest": r["input"]["payload_digest"],
                      "scenario_digest": r["input"]["scenario_digest"], "result_digest": r["result_digest"],
                      "timeline_window": [ws, we], "timeline_digest": tl["result_digest"]})
    dump("INDEX.json", {"engine": "engine.civic_scenarios 1.0.0", "cases": index})
    b = bench()
    (HERE / "bench.json").write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=1))
    print(json.dumps(b, ensure_ascii=False))


if __name__ == "__main__":
    main()
