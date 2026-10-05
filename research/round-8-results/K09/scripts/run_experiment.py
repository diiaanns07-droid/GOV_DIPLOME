#!/usr/bin/env python3
"""Воспроизводимый прогон эксперимента K09 round-8 (только stdlib, сеть не нужна).

  python3 scripts/run_experiment.py                 # v1 (предрегистрация) -> results/
  python3 scripts/run_experiment.py --config config/experiment_config_v2.json   # v2 -> results_v2/
  python3 scripts/run_experiment.py --limit 20 --out /tmp/x   # короткая проверка

Детерминированные файлы: runs.csv, scenarios.csv, summary.json, crosscheck_tasks.json (только v1), DETERMINISTIC_SHA256.txt.
Зависят от машины: timing.csv, timing_summary.json, run_meta.json.
"""
import argparse, csv, hashlib, json, os, platform, sys, time
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09plan import data, suite, experiment as X, exact, METRIC_VERSION  # noqa: E402
from k09plan.metric import Problem  # noqa: E402

DET = ["runs.csv", "scenarios.csv", "summary.json", "crosscheck_tasks.json"]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader(); w.writerows(rows)


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def crosscheck(cfg, ctxs):
    """Фиксированные задачи для будущей сверки сборки: seed 0, n_cand=16, n_pts=25, ratio 0.5, random_1_100, по одной на срез."""
    tasks = []
    for sl in cfg["baselines"]["slices"]:
        ctx = ctxs[sl["id"]]
        sc = suite.make_scenario(ctx, 16, 25, 0.5, "random_1_100", 3, 300, 0, cfg["config_version"])
        pr = Problem(sc["control_points"], ctx["sources"], sc["candidates"], sc["coverage_radius_m"])
        r = exact.optimize(pr, sc["budget"], sc["max_selected"])
        tasks.append({"slice": sl["id"], "kind": "synthetic_points_and_candidates",
                      "context": {k: ctx[k] for k in ("city_id", "category", "bbox", "source_snapshot", "sources", "baseline", "metric_version")},
                      "scenario": sc, "expected": {"problem_digest": exact.problem_digest(ctx, sc), "objectives": r["objectives"],
                                                   "pareto": r["pareto"], "feasible_count": r["feasible_count"],
                                                   "budget_sensitivity": exact.budget_sensitivity(pr, sc["budget"], sc["max_selected"])}})
    return {"note": "Сверка: контекст включает исходные записи среза (real Overture), точки/кандидаты/стоимости synthetic.",
            "metric_version": METRIC_VERSION, "config_version": cfg["config_version"], "tasks": tasks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(K / "config/experiment_config.json"))
    ap.add_argument("--out", default=None, help="по умолчанию results_dir из config (results/ для v1)")
    ap.add_argument("--repeats", type=int, default=3, help="замер времени: минимум из N повторов")
    ap.add_argument("--limit", type=int, default=0, help="только первые N сценариев (проверка)")
    ap.add_argument("--repo", default=str(K.parents[2]))
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    assert cfg["metric_version"] == METRIC_VERSION and cfg["base_sha"] == data.BASE_SHA
    sl_data, digest = data.load_slice(repo=a.repo)
    if digest != data.EXPECTED_DATA_SHA256:
        sys.exit(f"data.js sha256 mismatch: {digest}")
    ctxs = {s["id"]: suite.make_context(sl_data, digest, s["city"], s["category"], s["baseline"]) for s in cfg["baselines"]["slices"]}
    plan = X.scenario_plan(cfg)
    if a.limit:
        plan = plan[:a.limit]
    out = Path(a.out or (K / cfg.get("results_dir", "results"))); out.mkdir(parents=True, exist_ok=True)
    scen, runs, timing = [], [], []
    t0 = time.perf_counter()
    for i, (an, sid, params, ov) in enumerate(plan):
        s, r, t = X.run_one(ctxs[sid], cfg, an, sid, params, ov, a.repeats)
        scen.append(s); runs.extend(r); timing.append(t)
        if (i + 1) % 500 == 0:
            print(f"{i + 1}/{len(plan)} {time.perf_counter() - t0:.1f}s", file=sys.stderr)
    write_csv(out / "runs.csv", runs)
    write_csv(out / "scenarios.csv", scen)
    write_csv(out / "timing.csv", [{k: (f"{v:.9f}" if isinstance(v, float) else v) for k, v in t.items()} for t in timing])
    dump(out / "summary.json", {"config_version": cfg["config_version"], "metric_version": METRIC_VERSION, "base_sha": data.BASE_SHA,
                                "data_sha256": digest, "design": X.design(cfg), "scenarios": len(scen), "runs": len(runs),
                                **X.summarize(runs, scen, cfg)})
    dump(out / "timing_summary.json", X.timing_summary(timing, scen))
    det = list(DET)
    if X.design(cfg) == "v1":
        dump(out / "crosscheck_tasks.json", crosscheck(cfg, ctxs))
    else:
        det.remove("crosscheck_tasks.json")
    dump(out / "run_meta.json", {"python": sys.version.split()[0], "implementation": platform.python_implementation(),
                                 "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
                                 "repeats": a.repeats, "limit": a.limit, "wall_s": round(time.perf_counter() - t0, 3),
                                 "timer": "time.perf_counter, минимум из repeats, один процесс"})
    lines = [f"{hashlib.sha256((out / n).read_bytes()).hexdigest()}  {n}" for n in det]
    (out / "DETERMINISTIC_SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"scenarios={len(scen)} runs={len(runs)} wall={time.perf_counter() - t0:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
