"""Замер скорости classify и similar на CPU (prompts/R04.txt п. 3: classify ≤ 50 мс, similar ≤ 150 мс на 5 000).

    python -m ml.civic_dedup.bench                 # отчёт в ml/civic_dedup/results/bench.json
    python -m ml.civic_dedup.bench --n 5000 --queries 300

Сценарии similar (5 000 синтетических обращений, demo):
  city      — точки по всему городу (обычная плотность: в круге 200 м единицы записей);
  hotspot   — все 5 000 в круге 150 м (худший случай: каждый запрос сравнивает тысячи текстов);
  r09_store — то же «city», но через настоящее хранилище R09 (SQLite в памяти), если модуль есть.
«first_query» — самый первый запрос (загрузка оценщика + пустой кэш); «cold» — первый проход по запросам
(кэш признаков заполняется по ходу), «warm» — повторный проход.
Время — по часам процесса (time.perf_counter), в миллисекундах; p50/p95/max.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ml.civic_dedup import config as C
from ml.civic_dedup import fixtures as F
from ml.civic_dedup import get_deduper, reset
from ml.civic_dedup.search import ASTANA_TZ


def stats(ms: list[float]) -> dict:
    ms = sorted(ms)
    p95 = ms[min(len(ms) - 1, int(round(0.95 * (len(ms) - 1))))]
    return {"n": len(ms), "p50_ms": round(statistics.median(ms), 2), "p95_ms": round(p95, 2), "max_ms": round(ms[-1], 2),
            "mean_ms": round(statistics.fmean(ms), 2)}


def cpu_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def timed(fn, *args, **kwargs) -> tuple[float, object]:
    t0 = time.perf_counter()
    res = fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000, res


# Тексты без слов словаря: решает модель (v1 или v2), а не словарь — так замер честнее.
NO_KEYWORD_TEXTS = ["Лифт не работает вторую неделю", "Помогите, пожалуйста, никто не отвечает",
                    "Үйдің лифті істемейді", "Когда закончат ремонт подъезда?", "Почтовые ящики сломаны"]


def corpus_texts(limit: int = 400) -> list[str]:
    """Тексты синтетики R02 (если ветка R02 в сборке) — разной длины и стиля; иначе пусто."""
    path = C.REPO_ROOT / "ml" / "datasets" / "synth_v3" / "data" / "corpus_v3.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line)["text"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:: max(1, len(rows) // limit)][:limit]


def bench_classify(texts: list[str], repeats: int) -> dict:
    from ui.civic_ml_api import classify, reset as reset_api, status
    reset_api()
    first_ms, _ = timed(classify, "Во дворе не горят фонари")  # загрузка моделей + первый ответ
    ms, sources = [], {}
    for i in range(repeats):
        dt, res = timed(classify, texts[i % len(texts)])
        ms.append(dt)
        sources[res["source"]] = sources.get(res["source"], 0) + 1
    return {"chain": status()["classify"], "first_call_ms": round(first_ms, 2), "sources": sources, **stats(ms)}


def bench_similar(records: list[dict], queries: list[tuple[str, list[float], dict]], source) -> dict:
    from ui.civic_ml_api import set_complaint_source, similar
    reset()  # новый Deduper -> пустой кэш признаков
    set_complaint_source(source)
    cold, warm, found = [], [], []
    first_ms, _ = timed(similar, queries[0][0], point=queries[0][1], days=14, target=queries[0][2])
    reset()  # первый запрос считаем отдельно и снова с пустым кэшем
    set_complaint_source(source)
    for text, point, target in queries:
        dt, res = timed(similar, text, point=point, days=14, target=target)
        cold.append(dt)
        found.append(len(res["matches"]))
    for text, point, target in queries:
        dt, _ = timed(similar, text, point=point, days=14, target=target)
        warm.append(dt)
    set_complaint_source(None)
    return {"first_query_ms": round(first_ms, 2), "cold": stats(cold), "warm": stats(warm),
            "mean_matches": round(statistics.fmean(found), 2),
            "method": get_deduper().version}


def make_queries(records, n: int, seed: int) -> list:
    rng = random.Random(seed)
    phrases = [t for ts in F.PHRASES.values() for t in ts]
    out = []
    for _ in range(n):
        base = rng.choice(records)
        point = F.offset(tuple(base["point"]), rng.uniform(-100, 100), rng.uniform(-100, 100))
        out.append((rng.choice(phrases), point, base["target"] if rng.random() < 0.5 else None))
    return out


def run(n: int, queries: int, seed: int) -> dict:
    from ui.civic_ml_api import records_source
    now = datetime.now(ASTANA_TZ)
    clock = lambda: now  # noqa: E731 — одно «сейчас» для всего замера
    phrases = [t for ts in F.PHRASES.values() for t in ts]
    report = {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
              "env": {"cpu": cpu_name(), "cpus": os.cpu_count(), "python": platform.python_version(),
                      "platform": platform.platform()},
              "data": f"{n} synthetic demo complaints (ml/civic_dedup/fixtures.py), seed {seed}"}
    report["classify"] = bench_classify(phrases + NO_KEYWORD_TEXTS * 4 + corpus_texts(), max(500, queries))
    city = F.make_records(n, seed=seed, now=now)
    report["similar_city"] = bench_similar(city, make_queries(city, queries, seed), records_source(city, clock))
    hot = F.make_records(n, seed=seed, now=now, hotspot=F.NURA_CENTER, n_targets=50)
    report["similar_hotspot"] = bench_similar(hot, make_queries(hot, min(queries, 60), seed), records_source(hot, clock))
    try:
        from ui.civic_feedback.v2 import ComplaintStore
    except ImportError as exc:
        report["similar_r09_store"] = {"status": "NOT_RUN", "reason": f"нет ui.civic_feedback.v2 ({exc.name})"}
    else:
        store = ComplaintStore(":memory:", clock=clock)
        for rec in city:
            store.import_record(dict(rec, due_at=rec["created_at"], schema="civic-complaint-v2"))
        from ui.civic_ml_api.similar import StoreSource
        report["similar_r09_store"] = bench_similar(city, make_queries(city, queries, seed), StoreSource(store))
        hstore = ComplaintStore(":memory:", clock=clock)
        for rec in hot:
            hstore.import_record(dict(rec, due_at=rec["created_at"], schema="civic-complaint-v2"))
        report["similar_r09_store_hotspot"] = bench_similar(hot, make_queries(hot, min(queries, 60), seed),
                                                            StoreSource(hstore))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_dedup.bench")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--queries", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--out", type=Path, default=C.RESULTS_DIR / "bench.json")
    args = ap.parse_args(argv)
    reset()
    report = run(args.n, args.queries, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = report["classify"]
    print(f"classify: первый вызов {c['first_call_ms']} мс, p50 {c['p50_ms']} мс, p95 {c['p95_ms']} мс "
          f"({c['chain']['model_version']}; решали: {c['sources']})")
    for key in ("similar_city", "similar_hotspot", "similar_r09_store", "similar_r09_store_hotspot"):
        r = report.get(key) or {}
        if "cold" in r:
            print(f"{key}: cold p95 {r['cold']['p95_ms']} мс, warm p50 {r['warm']['p50_ms']} / p95 {r['warm']['p95_ms']} мс, "
                  f"совпадений в среднем {r['mean_matches']}")
        else:
            print(f"{key}: {r.get('status')} {r.get('reason', '')}")
    print(f"отчёт: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
