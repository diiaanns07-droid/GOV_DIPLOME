"""LOCAL-задача: multilingual-e5 -> ONNX int8 для поиска дублей. Запуск на ноутбуке владельца (venv birge-ml).

    C:\\Users\\LEGION\\venvs\\birge-ml\\Scripts\\python.exe -m ml.civic_dedup.export_e5
    ... -m ml.civic_dedup.export_e5 --model <путь к снимку в кэше HuggingFace>      # если имя не находится

Без сети: модель берётся из кэша HuggingFace (local_files_only=True; LOCAL-3 уже скачал
intfloat/multilingual-e5-base, ревизия d128750…, research/round-14-results/LOCAL/ENV.md).

Шаги:
  1. PyTorch-модель + быстрый токенизатор из кэша;
  2. обёртка: среднее по attention_mask + L2-нормировка -> выход "embedding" (как в карточке e5);
     ONNX fp32 (opset 17, динамические batch и длина): сначала классический экспортёр, при ошибке — dynamo
     (тот же порядок, что у R03 в ml/civic_classifier_v2/export_onnx.py);
  3. int8: onnxruntime.quantization.quantize_dynamic (веса int8) -> model.int8.onnx;
  4. tokenizer.json (библиотека tokenizers, без transformers на сервере);
  5. проверка на 200 текстах (пары R02 или встроенные фразы): id токенов tokenizers == transformers;
     косинус ONNX fp32 / int8 к PyTorch (критерии: min ≥ 0.999 / ≥ 0.98);
  6. скорость: один текст за вызов, p50/p95 мс;
  7. e5_meta.json: модель, ревизия, префикс, max_length, pad_id, размер, файлы (sha256), проверки.
Результат: ml/civic_dedup/artifacts/e5/ (не в Git: ≈ 280 МБ int8 + ≈ 1.1 ГБ fp32; --drop-fp32 удаляет fp32).
Дальше: python -m ml.civic_dedup.tune --method all --write-config  и  python -m ml.civic_dedup.bench
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ml.civic_dedup import config as C
from ml.civic_dedup.e5 import DEFAULT_MAX_LENGTH, DEFAULT_PREFIX, META_NAME, E5Scorer

MODEL_ID = "intfloat/multilingual-e5-base"
REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"  # LOCAL-3 (ENV.md)
OPSET = 17
MIN_COS_FP32 = 0.999
MIN_COS_INT8 = 0.98


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_hf(model: str, revision: str | None):
    from transformers import AutoModel, AutoTokenizer
    kw = {"local_files_only": True}
    if revision and not Path(model).exists():
        kw["revision"] = revision
    tok = AutoTokenizer.from_pretrained(model, **kw)
    try:  # «eager»-внимание трассируется без условий по форме входа
        mdl = AutoModel.from_pretrained(model, attn_implementation="eager", add_pooling_layer=False, **kw)
    except (TypeError, ValueError):
        mdl = AutoModel.from_pretrained(model, **kw)
    return tok, mdl.float().eval()


def export_fp32(model, tokenizer, onnx_path: Path, exporter: str = "auto") -> dict:
    import torch

    class Wrapper(torch.nn.Module):
        """input_ids, attention_mask -> embedding (среднее по маске, L2)."""

        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            hidden = self.m(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            return torch.nn.functional.normalize(pooled, p=2, dim=-1)

    wrapped = Wrapper(model).eval()
    enc = tokenizer([DEFAULT_PREFIX + "Во дворе не горят фонари", DEFAULT_PREFIX + "яма"], padding=True,
                    return_tensors="pt")
    args = (enc["input_ids"], enc["attention_mask"])
    kwargs = dict(input_names=["input_ids", "attention_mask"], output_names=["embedding"],
                  dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                "embedding": {0: "batch"}}, opset_version=OPSET, do_constant_folding=True)
    has_dynamo = "dynamo" in inspect.signature(torch.onnx.export).parameters
    order = {"auto": [False, True], "torchscript": [False], "dynamo": [True]}[exporter] if has_dynamo else [None]
    errors = []
    for use_dynamo in order:
        try:
            extra = {} if use_dynamo is None else {"dynamo": use_dynamo}
            kw = kwargs
            if use_dynamo:
                batch, seq = torch.export.Dim("batch"), torch.export.Dim("seq", max=512)
                extra["dynamic_shapes"] = {"input_ids": {0: batch, 1: seq}, "attention_mask": {0: batch, 1: seq}}
                kw = {k: v for k, v in kwargs.items() if k != "dynamic_axes"}
            with torch.no_grad():
                torch.onnx.export(wrapped, args, str(onnx_path), **kw, **extra)
            return {"exporter": "dynamo" if use_dynamo else "torchscript", "opset": OPSET, "torch": torch.__version__,
                    "errors_before_success": errors}
        except Exception as exc:  # пробуем другой экспортёр
            errors.append(f"dynamo={use_dynamo}: {type(exc).__name__}: {str(exc)[:300]}")
    raise RuntimeError("экспорт ONNX не удался: " + " | ".join(errors))


def _clean_copy(src: Path, dst: Path) -> None:
    """Копия без value_info: формы промежуточных тензоров от dynamo мешают выводу форм при квантовании."""
    import onnx
    model = onnx.load(str(src))
    del model.graph.value_info[:]
    big = model.ByteSize() > 1_800_000_000  # protobuf ограничен 2 ГБ
    onnx.save(model, str(dst), save_as_external_data=big, location=dst.name + ".data" if big else None)


def quantize(fp32: Path, int8: Path) -> dict:
    """ONNX fp32 -> int8 (динамическое квантование весов). Нужны только onnx и onnxruntime."""
    import onnxruntime
    from onnxruntime.quantization import QuantType, quantize_dynamic
    clean = fp32.with_name("model.clean.onnx")
    pre = fp32.with_name("model.pre.onnx")
    _clean_copy(fp32, clean)
    src, preprocessed = clean, False
    try:
        from onnxruntime.quantization.shape_inference import quant_pre_process
        quant_pre_process(str(clean), str(pre), skip_symbolic_shape=True)
        src, preprocessed = pre, True
    except Exception:  # предобработка рекомендуется, но не обязательна
        pass
    quantize_dynamic(str(src), str(int8), weight_type=QuantType.QInt8)
    for f in (clean, pre, clean.with_name(clean.name + ".data"), pre.with_name(pre.name + ".data")):
        if f.exists():
            f.unlink()
    return {"method": "onnxruntime.quantization.quantize_dynamic", "weight_type": "QInt8",
            "preprocessed": preprocessed, "onnxruntime": onnxruntime.__version__}


def check_texts(n: int) -> list[str]:
    texts = []
    if C.PAIRS_PATH.exists():
        for line in C.PAIRS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                texts += [r["a"], r["b"]]
    if not texts:
        from ml.civic_dedup.fixtures import PHRASES
        texts = [t for ts in PHRASES.values() for t in ts]
    return list(dict.fromkeys(texts))[:n]


def torch_embed(model, tokenizer, texts: list[str], max_length: int):
    import numpy as np
    import torch
    out = []
    for i in range(0, len(texts), 16):
        enc = tokenizer([DEFAULT_PREFIX + t for t in texts[i:i + 16]], padding=True, truncation=True,
                        max_length=max_length, return_tensors="pt")
        with torch.no_grad():
            hidden = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).last_hidden_state
        mask = enc["attention_mask"].unsqueeze(-1).float()
        pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        out.append(torch.nn.functional.normalize(pooled, p=2, dim=-1).numpy())
    return np.concatenate(out)


def verify(out_dir: Path, model, tokenizer, texts: list[str], max_length: int) -> dict:
    ref = torch_embed(model, tokenizer, texts, max_length)
    report = {"n_texts": len(texts)}
    # токены: tokenizers (сервер) == transformers (обучение/экспорт)
    sc = E5Scorer.load(out_dir)
    hf_ids = [tokenizer(DEFAULT_PREFIX + t, truncation=True, max_length=max_length)["input_ids"] for t in texts]
    tk_ids = [e.ids for e in sc.tokenizer.encode_batch([DEFAULT_PREFIX + t for t in texts])]
    report["token_ids_equal"] = round(sum(a == b for a, b in zip(hf_ids, tk_ids)) / len(texts), 4)
    for name in ("model.onnx", "model.int8.onnx"):
        if not (out_dir / name).exists():
            continue
        emb = E5Scorer.load(out_dir, onnx_name=name).embed(texts)
        cos = (emb * ref).sum(axis=1)
        report[name] = {"cos_min": round(float(cos.min()), 5), "cos_mean": round(float(cos.mean()), 5)}
    report["pass"] = bool(report["token_ids_equal"] == 1.0
                          and report.get("model.onnx", {}).get("cos_min", 1.0) >= MIN_COS_FP32
                          and report.get("model.int8.onnx", {}).get("cos_min", 0.0) >= MIN_COS_INT8)
    report["criteria"] = {"token_ids_equal": 1.0, "fp32_cos_min": MIN_COS_FP32, "int8_cos_min": MIN_COS_INT8}
    return report


def speed(out_dir: Path, texts: list[str]) -> dict:
    sc = E5Scorer.load(out_dir)
    sc.embed(texts[:4])
    ms = []
    for t in texts[:100]:
        t0 = time.perf_counter()
        sc.embed([t])
        ms.append((time.perf_counter() - t0) * 1000)
    ms.sort()
    batch_t0 = time.perf_counter()
    sc.embed(texts[:64])
    return {"one_text_p50_ms": round(statistics.median(ms), 2), "one_text_p95_ms": round(ms[int(0.95 * (len(ms) - 1))], 2),
            "batch64_ms": round((time.perf_counter() - batch_t0) * 1000, 1), "file": sc.meta.get("file")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_dedup.export_e5")
    ap.add_argument("--model", default=MODEL_ID, help="имя в кэше HuggingFace или путь к снимку")
    ap.add_argument("--revision", default=REVISION)
    ap.add_argument("--out", type=Path, default=C.E5_DIR)
    ap.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    ap.add_argument("--exporter", choices=("auto", "torchscript", "dynamo"), default="auto")
    ap.add_argument("--n", type=int, default=200, help="текстов для проверки")
    ap.add_argument("--drop-fp32", action="store_true", help="удалить model.onnx (fp32) после проверки")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    print(f"1/6 загрузка {args.model} из кэша (без сети)…")
    tokenizer, model = load_hf(args.model, args.revision)
    print("2/6 экспорт ONNX fp32…")
    export_info = export_fp32(model, tokenizer, out / "model.onnx", args.exporter)
    print("3/6 квантование int8…")
    quant_info = quantize(out / "model.onnx", out / "model.int8.onnx")
    print("4/6 токенизатор…")
    tokenizer.save_pretrained(str(out))
    if not (out / "tokenizer.json").exists():
        print("нет tokenizer.json: нужен быстрый токенизатор (pip install tokenizers)", file=sys.stderr)
        return 2
    revision = getattr(model.config, "_commit_hash", None) or args.revision
    meta = {"model_id": MODEL_ID if not Path(args.model).exists() else str(args.model), "revision": revision,
            "prefix": DEFAULT_PREFIX, "max_length": args.max_length, "pad_id": int(tokenizer.pad_token_id),
            "dim": int(model.config.hidden_size), "pooling": "mean", "normalize": True,
            "quantization": "int8", "opset": OPSET, "export": export_info, "quantize": quant_info,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "env": {"python": platform.python_version(), "platform": platform.platform()}}
    (out / META_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("5/6 проверка совпадения с PyTorch…")
    texts = check_texts(args.n)
    meta["verify"] = verify(out, model, tokenizer, texts, args.max_length)
    print("6/6 скорость…")
    meta["speed"] = speed(out, texts)
    if args.drop_fp32 and meta["verify"]["pass"]:
        (out / "model.onnx").unlink()
    meta["files"] = {f.name: {"bytes": f.stat().st_size, "sha256": sha256(f)}
                     for f in sorted(out.iterdir()) if f.is_file() and f.suffix in (".onnx", ".json")
                     and f.name != META_NAME}
    (out / META_NAME).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    C.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    small = {k: meta[k] for k in ("model_id", "revision", "max_length", "dim", "export", "quantize", "verify",
                                   "speed", "files", "created_at", "env")}
    (C.RESULTS_DIR / "e5_export.json").write_text(json.dumps(small, ensure_ascii=False, indent=1) + "\n",
                                                  encoding="utf-8")
    v = meta["verify"]
    print(f"проверка: {'PASS' if v['pass'] else 'FAIL'} — токены {v['token_ids_equal']}, "
          f"fp32 {v.get('model.onnx')}, int8 {v.get('model.int8.onnx')}; скорость {meta['speed']}")
    print(f"готово: {out}. Дальше: python -m ml.civic_dedup.tune --method all --write-config")
    return 0 if v["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
