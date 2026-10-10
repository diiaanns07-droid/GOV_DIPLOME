"""Экспорт итоговой модели в ONNX + динамическое квантование int8 + проверка + замер скорости на CPU.

    python -m ml.civic_classifier_v2.export_onnx                         # artifacts/final -> artifacts/onnx
    python -m ml.civic_classifier_v2.export_onnx --model DIR --out DIR --texts FILE.jsonl --n 200

Шаги:
  1. model.onnx (fp32): входы input_ids, attention_mask (динамические batch и длина), выход logits;
  2. model.int8.onnx: onnxruntime.quantization.quantize_dynamic (веса int8);
  3. проверка на N текстах (по умолчанию 200 из синтетики v3 test/val — тексты людей не нужны):
     совпадение argmax и разница вероятностей PyTorch vs ONNX fp32 vs ONNX int8;
  4. скорость на CPU: один текст за вызов (как в /classify), прогрев, mean/p50/p95, 1 поток и все потоки.
  5. рядом кладутся токенизатор и birge_meta.json — папку целиком подключает R04 (predict.Classifier).
Отчёт: <out>/export_report.json и ml/civic_classifier_v2/results/onnx_export.json (только числа).
Критерии: fp32 argmax 100% и max|Δp| < 1e-3; int8 argmax ≥ --min-int8-agreement (0.97); mean < 50 мс.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import platform
import shutil
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from ml.civic_classifier_v2 import data as D
from ml.civic_classifier_v2.config import ARTIFACTS_DIR, RESULTS_DIR, SYNTH_V3_DIR
from ml.civic_classifier_v2.predict import META_NAME, Classifier

OPSET = 17
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                   "sentencepiece.bpe.model", "vocab.txt", "added_tokens.json")
FALLBACK_TEXTS = [
    "Во дворе не горят фонари уже неделю", "На дороге огромная яма, машины бьют колёса",
    "Аулада шам жанбайды", "Не вывозят мусор, баки переполнены", "Тротуар весь в снегу и наледи",
    "Аялдамада павильон сынған", "Нет горячей воды третий день", "Ночью громкая музыка из кафе",
    "Машины паркуются на газоне", "Пахнет гарью по вечерам", "Спасибо за ремонт дороги", "Қоқыс шығарылмайды",
]


def export_fp32(model_dir: Path, onnx_path: Path) -> dict:
    """PyTorch -> ONNX. Сначала классический экспортёр (dynamo=False), при ошибке — dynamo."""
    import torch
    from ml.civic_classifier_v2 import transformer as T

    tm = T.load(model_dir, device="cpu")
    model = tm.model.float().eval()

    class Wrapper(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            return self.m(input_ids=input_ids, attention_mask=attention_mask).logits

    wrapped = Wrapper(model).eval()
    enc = tm.tokenizer(["Во дворе не горят фонари", "яма"], padding=True, return_tensors="pt")
    args = (enc["input_ids"], enc["attention_mask"])
    kwargs = dict(input_names=["input_ids", "attention_mask"], output_names=["logits"],
                  dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                "logits": {0: "batch"}}, opset_version=OPSET, do_constant_folding=True)
    has_dynamo = "dynamo" in inspect.signature(torch.onnx.export).parameters
    errors = []
    for use_dynamo in ([False, True] if has_dynamo else [None]):
        try:
            extra = {} if use_dynamo is None else {"dynamo": use_dynamo}
            if use_dynamo:
                batch, seq = torch.export.Dim("batch"), torch.export.Dim("seq", max=512)
                extra["dynamic_shapes"] = {"input_ids": {0: batch, 1: seq}, "attention_mask": {0: batch, 1: seq}}
                kw = {k: v for k, v in kwargs.items() if k != "dynamic_axes"}
            else:
                kw = kwargs
            with torch.no_grad():
                torch.onnx.export(wrapped, args, str(onnx_path), **kw, **extra)
            return {"exporter": "dynamo" if use_dynamo else "torchscript", "opset": OPSET,
                    "torch": torch.__version__, "errors_before_success": errors}
        except Exception as exc:  # пробуем другой экспортёр
            errors.append(f"dynamo={use_dynamo}: {type(exc).__name__}: {str(exc)[:300]}")
    raise RuntimeError("экспорт ONNX не удался: " + " | ".join(errors))


def quantize(fp32: Path, int8: Path) -> dict:
    from onnxruntime.quantization import QuantType, quantize_dynamic
    import onnxruntime
    src = fp32
    pre = fp32.with_name("model.pre.onnx")
    try:  # рекомендуемая предобработка (вывод форм); не обязательна
        from onnxruntime.quantization.shape_inference import quant_pre_process
        quant_pre_process(str(fp32), str(pre), skip_symbolic_shape=True)
        src = pre
    except Exception:
        pass
    quantize_dynamic(str(src), str(int8), weight_type=QuantType.QInt8)
    if pre.exists():
        pre.unlink()
    return {"method": "onnxruntime.quantization.quantize_dynamic", "weight_type": "QInt8",
            "onnxruntime": onnxruntime.__version__}


def load_texts(path: str | None, n: int) -> tuple[list[str], str]:
    """Тексты для проверки: файл (JSONL с полем text или .txt построчно) или синтетика v3 test+val."""
    if path:
        p = Path(path)
        if p.suffix.lower() == ".txt":
            texts = [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        else:
            texts = [D.clean_text(r.get("text")) for r in D.read_rows(p)[0] if r.get("text")]
        return texts[:n], p.name
    try:
        recs, _ = D.load_corpus(SYNTH_V3_DIR, source="synth_v3", evidence="synthetic_template")
        texts = [r["text"] for r in recs if r["split"] in ("test", "val")] or [r["text"] for r in recs]
        if texts:
            return texts[:n], "synth_v3 test/val"
    except FileNotFoundError:
        pass
    texts = [f"{t} {i}" if i >= len(FALLBACK_TEXTS) else t for i, t in
             enumerate(FALLBACK_TEXTS * (n // len(FALLBACK_TEXTS) + 1))][:n]
    return texts, "встроенные примеры (синтетика R03, повторы с номером)"


def compare(ref: np.ndarray, other: np.ndarray, margin: float = 0.05) -> dict:
    """Совпадение top-1 и разница вероятностей. confident — тексты, где у PyTorch top-1 опережает top-2
    хотя бы на margin: там расхождение — настоящая ошибка квантования, а не «ничья»."""
    srt = np.sort(ref, axis=1)
    conf = (srt[:, -1] - srt[:, -2]) >= margin
    same = ref.argmax(1) == other.argmax(1)
    return {"argmax_agreement": round(float(same.mean()), 4),
            "argmax_agreement_confident": round(float(same[conf].mean()), 4) if conf.any() else None,
            "n_confident": int(conf.sum()), "confident_margin": margin,
            "max_abs_diff_prob": round(float(np.abs(ref - other).max()), 6),
            "mean_abs_diff_prob": round(float(np.abs(ref - other).mean()), 6)}


def bench(clf: Classifier, texts: list[str], warmup: int = 10) -> dict:
    for t in texts[:warmup]:
        clf.predict_proba([t])
    lat = []
    for t in texts:
        t0 = time.perf_counter()
        clf.predict_proba([t])
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    return {"n": len(lat), "mean_ms": round(statistics.fmean(lat), 2), "p50_ms": round(lat[len(lat) // 2], 2),
            "p95_ms": round(lat[max(0, int(0.95 * len(lat)) - 1)], 2), "max_ms": round(lat[-1], 2)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.export_onnx", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=str(ARTIFACTS_DIR / "final"))
    ap.add_argument("--out", default=str(ARTIFACTS_DIR / "onnx"))
    ap.add_argument("--texts", help="JSONL/TXT с текстами для проверки (по умолчанию синтетика v3)")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--min-int8-agreement", type=float, default=0.97)
    ap.add_argument("--max-mean-ms", type=float, default=50.0)
    ap.add_argument("--keep-fp32", action="store_true", help="оставить model.onnx (fp32) рядом с int8")
    ap.add_argument("--results", default=str(RESULTS_DIR / "onnx_export.json"))
    args = ap.parse_args(argv)

    model_dir, out = Path(args.model), Path(args.out)
    if not (model_dir / META_NAME).exists():
        print(f"нет модели в {model_dir} (сначала train.py)", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"model_dir": str(model_dir.name), "out_dir": str(out.name)}
    fp32, int8 = out / "model.onnx", out / "model.int8.onnx"

    t0 = time.time()
    report["export"] = export_fp32(model_dir, fp32)
    report["export"]["seconds"] = round(time.time() - t0, 1)
    t0 = time.time()
    report["quantize"] = quantize(fp32, int8)
    report["quantize"]["seconds"] = round(time.time() - t0, 1)
    for name in TOKENIZER_FILES:
        if (model_dir / name).exists():
            shutil.copy2(model_dir / name, out / name)
    meta = json.loads((model_dir / META_NAME).read_text(encoding="utf-8"))
    meta["onnx"] = {"fp32": fp32.name, "int8": int8.name, "opset": OPSET, "exported_from": model_dir.name}
    (out / META_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report["sizes_mb"] = {f.name: round(f.stat().st_size / 2 ** 20, 1) for f in (fp32, int8)}
    report["model_version"] = meta.get("model_version")

    texts, source = load_texts(args.texts, args.n)
    report["check"] = {"n_texts": len(texts), "texts_source": source}
    ref = Classifier.load(model_dir, backend="torch").predict_proba(texts)
    tmp_fp32 = Classifier(out, meta, None, "onnx:model.onnx")
    from ml.civic_classifier_v2.predict import _OnnxBackend
    max_len = int(meta["train_config"]["max_length"])
    tmp_fp32._backend = _OnnxBackend(out, fp32, max_len, None)
    p32 = tmp_fp32.predict_proba(texts)
    clf8 = Classifier.load(out, backend="onnx")  # int8 — то, что получит R04
    p8 = clf8.predict_proba(texts)
    report["check"]["onnx_fp32_vs_torch"] = compare(ref, p32)
    report["check"]["onnx_int8_vs_torch"] = compare(ref, p8)
    ok32 = (report["check"]["onnx_fp32_vs_torch"]["argmax_agreement"] == 1.0
            and report["check"]["onnx_fp32_vs_torch"]["max_abs_diff_prob"] < 1e-3)
    ok8 = report["check"]["onnx_int8_vs_torch"]["argmax_agreement"] >= args.min_int8_agreement

    cpu = {"machine": platform.machine(), "processor": platform.processor() or platform.machine(),
           "cpu_count": os.cpu_count(), "system": platform.system()}
    report["latency_cpu"] = {"cpu": cpu, "unit": "один текст за вызов, включая токенизацию"}
    report["latency_cpu"]["int8_all_threads"] = bench(clf8, texts)
    report["latency_cpu"]["int8_1_thread"] = bench(Classifier.load(out, backend="onnx", threads=1), texts)
    report["latency_cpu"]["fp32_all_threads"] = bench(tmp_fp32, texts)
    fast = report["latency_cpu"]["int8_all_threads"]["mean_ms"] < args.max_mean_ms
    report["verdict"] = {"fp32_matches_torch": "PASS" if ok32 else "FAIL",
                         "int8_agreement": "PASS" if ok8 else "FAIL",
                         f"int8_mean_lt_{int(args.max_mean_ms)}ms": "PASS" if fast else "FAIL"}
    if not args.keep_fp32:
        fp32.unlink()
        report["note"] = "model.onnx (fp32) удалён после проверки; R04 использует model.int8.onnx"
    text = json.dumps(report, ensure_ascii=False, indent=1)
    (out / "export_report.json").write_text(text + "\n", encoding="utf-8")
    Path(args.results).parent.mkdir(parents=True, exist_ok=True)
    Path(args.results).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if ok32 and ok8 else 1


if __name__ == "__main__":
    sys.exit(main())
