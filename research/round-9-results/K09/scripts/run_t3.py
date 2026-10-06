#!/usr/bin/env python3
"""Прогон протокола T3 оракулом (детерминированные выходы отдельно от времени).

  python3 scripts/run_t3.py                       # полный прогон -> results/stage3/
  python3 scripts/run_t3.py --limit 12 --out /tmp/x   # проверка формата
  python3 scripts/run_t3.py --emit-envelopes /tmp/env.jsonl   # только входы (для адаптера BUILD r9)
"""
import argparse, csv, hashlib, json, os, platform, sys, time
from pathlib import Path

K = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(K))
from k09res import t3 as T, resilience as RS  # noqa: E402
from k09plan import data, suite  # noqa: E402

REPO = K.parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(K / "config/t3_config.json"))
    ap.add_argument("--out", default=str(K / "results/stage3"))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--emit-envelopes", default=None)
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    attr = json.loads((K / "config/t3_attribute_sets.json").read_text(encoding="utf-8"))["slices"]
    d, sha = data.load_slice(repo=str(REPO), sha=cfg["data_build_sha"])
    assert sha == data.EXPECTED_DATA_SHA256
    ctxs = {s["id"]: suite.make_context(d, sha, s["city"], s["category"], "real_slice_records") for s in cfg["slices"]}
    for s in cfg["slices"]:
        assert len(ctxs[s["id"]]["sources"]) == s["n_sources"]
    plan = T.task_plan(cfg, attr)
    assert len(plan) == cfg["task_counts"]["total"], len(plan)
    if a.limit:
        plan = plan[:a.limit]
    if a.emit_envelopes:
        with open(a.emit_envelopes, "w", encoding="utf-8") as f:
            for spec in plan:
                an, sid, size, fam, k, br, ms, seed = spec
                cases = T.exclusion_cases(ctxs[sid], cfg, fam, k, seed, attr[sid]["cases"])
                env = T.make_env(ctxs[sid], cfg, size, br, ms, seed, cases)
                f.write(json.dumps({"task_key": f"{an}|{sid}|{size}|{fam}|k{k}|br{br}|ms{ms}|s{seed}", "slice": sid,
                                    "city": ctxs[sid]["city_id"], "category": ctxs[sid]["category"], "envelope": env}, ensure_ascii=False) + "\n")
        print(f"{len(plan)} envelopes -> {a.emit_envelopes}")
        return
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows, timing = [], {}
    t0 = time.perf_counter()
    for i, spec in enumerate(plan):
        row, t = T.run_one(ctxs[spec[1]], cfg, attr, spec, a.repeats)
        rows.append(row); timing[row["task_key"]] = t
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(plan)} {time.perf_counter() - t0:.0f}s", file=sys.stderr)
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(out / "t3_runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", restval="")
        w.writeheader(); w.writerows(rows)
    (out / "t3_summary.json").write_text(json.dumps(T.summarize(rows, cfg), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "t3_timing.json").write_text(json.dumps({"by_group": T.timing_summary(timing, rows),
                                                    "per_task_ms": {k: round(v * 1e3, 4) for k, v in timing.items()}}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    meta = {"python": sys.version.split()[0], "implementation": platform.python_implementation(), "platform": platform.platform(),
            "machine": platform.machine(), "cpu_count": os.cpu_count(), "repeats": a.repeats, "limit": a.limit,
            "wall_s": round(time.perf_counter() - t0, 2), "timer": "time.perf_counter, минимум из repeats; оракул Python, один процесс"}
    (out / "t3_run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [f"{hashlib.sha256((out / n).read_bytes()).hexdigest()}  {n}" for n in ("t3_runs.csv", "t3_summary.json")]
    (out / "DETERMINISTIC_SHA256.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines)); print(f"tasks={len(rows)} wall={meta['wall_s']}s", file=sys.stderr)


if __name__ == "__main__":
    main()
