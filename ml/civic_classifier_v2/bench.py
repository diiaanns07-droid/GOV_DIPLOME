"""Нагрузка на /classify: скорость модели v2 на длинных текстах и при одновременных запросах (CPU).

Зачем: R15 ограничил /classify 60 запросами в минуту с адреса и длиной до 5000 знаков; нагрузку на настоящей
модели никто не мерил. Здесь — тот же путь, что у R04: Classifier.classify() (обрезка до MAX_TEXT, токенизация,
ONNX int8, ответ по CONTRACT §7). Тексты генерируются из коротких фраз-жалоб (синтетика) — тексты людей не нужны.

    python -m ml.civic_classifier_v2.bench                             # artifacts/onnx -> results/classify_load.json
    python -m ml.civic_classifier_v2.bench --model DIR --label laptop --n 100 --workers 1,4,8

Что меряется:
  1. по одному запросу подряд при длине 40 / 300 / 1000 / 5000 знаков: mean / p50 / p95 / max, мс;
  2. одновременные запросы самой большой длины (потоки, как у многопоточного сервера): запросов в минуту
     и p95 задержки одного запроса;
  3. пиковая память процесса (Linux/macOS; в Windows — NOT_RUN).
Модель обрезает вход до max_length токенов (128), поэтому после ~1000 знаков время почти не растёт.
Числа зависят от процессора: облачный замер на случайных весах размера xlm-roberta-base говорит о скорости,
не о качестве; на ноутбуке владельца — запустить с настоящей моделью (RUN.txt).
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ml.civic_classifier_v2.config import RESULTS_DIR
from ml.civic_classifier_v2.predict import MAX_TEXT, Classifier, ModelUnavailable, resolve_threads

# Короткие синтетические жалобы (ru / kk / смешанные) — из них собираются тексты нужной длины.
PHRASES = (
    "Во дворе огромная яма, машины бьют колёса.",
    "Третий день не горят фонари вдоль улицы, вечером очень темно.",
    "Мусорные баки переполнены, мусор не вывозят уже неделю.",
    "Аулада балалар алаңы сынған, әткеншек құлап тұр.",
    "Тротуарда көктайғақ, құм себілмеген, адамдар құлап жатыр.",
    "На остановке разбито стекло павильона, ждать автобус негде.",
    "Аялдамада жарық жоқ, вечером на остановке темно.",
    "Нет горячей воды в подъезде, в акимат звонили — без ответа.",
    "Машины стоят на газоне во дворе, детям негде гулять.",
    "Ночью гоняют на машинах, шумно и опасно для пешеходов.",
)
LENGTHS = (40, 300, 1000, 5000)
LIMIT_PER_MINUTE = 60  # лимит R15 (P-R01) для /classify с одного адреса


def make_text(length: int, rng: random.Random) -> str:
    """Синтетический текст ровно length знаков (фразы подряд, последняя обрезается)."""
    parts, size = [], 0
    while size < length:
        p = rng.choice(PHRASES)
        parts.append(p)
        size += len(p) + 1
    return " ".join(parts)[:length]


def _stats(lat_ms: list[float]) -> dict:
    lat = sorted(lat_ms)
    return {"n": len(lat), "mean_ms": round(statistics.fmean(lat), 2), "p50_ms": round(lat[len(lat) // 2], 2),
            "p95_ms": round(lat[max(0, int(0.95 * len(lat)) - 1)], 2), "max_ms": round(lat[-1], 2)}


def _timed(clf: Classifier, text: str) -> float:
    t0 = time.perf_counter()
    clf.classify(text)
    return (time.perf_counter() - t0) * 1000


def n_tokens(clf: Classifier, text: str) -> int | None:
    """Сколько токенов реально уходит в модель (после обрезки); только для ONNX-бэкенда."""
    enc = getattr(clf._backend, "_encode", None)
    return int(enc([text[:MAX_TEXT]])["input_ids"].shape[1]) if enc else None


def sequential(clf: Classifier, lengths, n: int, seed: int, warmup: int = 5) -> dict:
    rng = random.Random(seed)
    out = {}
    for length in lengths:
        texts = [make_text(length, rng) for _ in range(n)]
        for t in texts[:warmup]:
            clf.classify(t)
        out[str(length)] = _stats([_timed(clf, t) for t in texts])
        toks = [n_tokens(clf, t) for t in texts[:20]]
        out[str(length)]["tokens_mean"] = round(statistics.fmean(toks), 1) if None not in toks else None
    return out


def concurrent(clf: Classifier, length: int, n: int, workers, seed: int) -> dict:
    """n запросов длины length, одновременно workers потоков; один Classifier на всех (как в сервере)."""
    rng = random.Random(seed + 1)
    out = {}
    for w in workers:
        texts = [make_text(length, rng) for _ in range(n)]
        with ThreadPoolExecutor(max_workers=w) as pool:
            list(pool.map(lambda t: clf.classify(t), texts[:w]))  # прогрев потоков
            t0 = time.perf_counter()
            lat = list(pool.map(lambda t: _timed(clf, t), texts))
            wall = time.perf_counter() - t0
        row = _stats(lat)
        row["wall_s"] = round(wall, 3)
        row["requests_per_minute"] = int(n / wall * 60)
        out[str(w)] = row
    return out


def peak_rss_mb() -> float | None:
    try:
        import resource
    except ImportError:  # Windows
        return None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def run(clf: Classifier, lengths=LENGTHS, n: int = 100, workers=(1, 4, 8), seed: int = 20261011) -> dict:
    seq = sequential(clf, lengths, n, seed)
    longest = max(lengths)
    conc = concurrent(clf, longest, n, workers, seed)
    best = max(conc.values(), key=lambda r: r["requests_per_minute"])
    return {
        "what": "Classifier.classify() — путь R04 /classify: обрезка, токенизация, ONNX, ответ CONTRACT §7",
        "texts": "синтетика: фразы-жалобы ru/kk подряд до нужной длины (тексты людей не используются)",
        "model_version": clf.model_version, "backend": clf.backend,
        "threads_per_request": getattr(clf._backend, "threads", None), "max_text_chars": MAX_TEXT,
        "cpu": {"cpu_count": os.cpu_count(), "machine": platform.machine(), "system": platform.system(),
                "processor": platform.processor() or platform.machine()},
        "sequential_by_length": seq,
        "concurrent_longest": {"length": longest, "by_workers": conc},
        "capacity": {"requests_per_minute_at_longest": best["requests_per_minute"],
                     "limit_per_address_per_minute": LIMIT_PER_MINUTE,
                     "addresses_at_full_limit": round(best["requests_per_minute"] / LIMIT_PER_MINUTE, 1)},
        "peak_rss_mb": peak_rss_mb(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="папка модели (по умолчанию как у predict: artifacts/onnx, затем final)")
    ap.add_argument("--backend", choices=("auto", "onnx", "torch"), default="onnx")
    ap.add_argument("--threads", type=int, help=f"потоков на запрос (по умолчанию {resolve_threads(None)})")
    ap.add_argument("--n", type=int, default=100, help="запросов на каждую длину и на каждый вариант потоков")
    ap.add_argument("--lengths", default=",".join(map(str, LENGTHS)))
    ap.add_argument("--workers", default="1,4,8", help="одновременных запросов")
    ap.add_argument("--label", default="", help="метка в имени файла: classify_load_<label>.json")
    ap.add_argument("--note", default="", help="пояснение в отчёт (например, «случайные веса, облако»)")
    ap.add_argument("--out", help="файл отчёта (по умолчанию results/classify_load[_label].json)")
    args = ap.parse_args(argv)
    try:
        clf = Classifier.load(Path(args.model) if args.model else None, args.backend, args.threads)
    except ModelUnavailable as exc:
        print(f"модель недоступна: {exc}", file=sys.stderr)
        return 2
    rep = run(clf, [int(x) for x in args.lengths.split(",")], args.n, [int(x) for x in args.workers.split(",")])
    rep["note"] = args.note
    out = Path(args.out) if args.out else RESULTS_DIR / f"classify_load{'_' + args.label if args.label else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for length, r in rep["sequential_by_length"].items():
        print(f"{length:>5} знаков ({r['tokens_mean']} токенов): mean {r['mean_ms']} мс, p95 {r['p95_ms']} мс")
    for w, r in rep["concurrent_longest"]["by_workers"].items():
        print(f"{w} одновременно ({rep['concurrent_longest']['length']} знаков): {r['requests_per_minute']} запросов/мин, "
              f"p95 {r['p95_ms']} мс")
    cap = rep["capacity"]
    print(f"{out}: до {cap['requests_per_minute_at_longest']} запросов/мин — {cap['addresses_at_full_limit']} адресов "
          f"на полном лимите {cap['limit_per_address_per_minute']}/мин; память {rep['peak_rss_mb']} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
