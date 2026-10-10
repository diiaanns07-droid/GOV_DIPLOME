"""Применение модели v2 — то, что подключает R04 в POST /api/civic/v2/classify (CONTRACT §7).

    from ml.civic_classifier_v2.predict import Classifier, ModelUnavailable
    clf = Classifier.load()            # $BIRGE_CLF_V2_DIR или artifacts/onnx (int8) -> artifacts/final (PyTorch);
                                       # нет модели -> ModelUnavailable
    clf.classify("Во дворе не горят фонари")
    # {"category": "lighting", "score": 0.93, "needs_review": True, "model_version": "civic-clf-v2-…",
    #  "top3": [{"category": "lighting", "score": 0.93}, {"category": "yards", "score": 0.03}, …]}

Бэкенды:
  onnx  — onnxruntime + tokenizers (лёгкие, без torch); файл model.int8.onnx или model.onnx;
  torch — папка save_pretrained от train.py (нужны torch и transformers).
Если модели нет — ModelUnavailable; R04 тогда отдаёт запасную v1 (контракт), интерфейс — ручной выбор.

needs_review = True, если: score < порога из validation, категория other, текст почти пустой,
или порогу нельзя доверять — в обучении не было текстов людей (review_policy != "threshold")
или рецепт не проверен на людях (human_eval != EVALUATED в birge_meta.json). Тогда подсказка
всегда требует проверки сотрудником, как у v1.

CLI:  python -m ml.civic_classifier_v2.predict "Во дворе не горят фонари" [--model DIR] [--backend onnx|torch]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.config import ARTIFACTS_DIR

META_NAME = "birge_meta.json"
MAX_TEXT = 5000
MIN_LETTERS = 3
DEFAULT_DIRS = (ARTIFACTS_DIR / "onnx", ARTIFACTS_DIR / "final")
ENV_DIR = "BIRGE_CLF_V2_DIR"  # переменная окружения: папка модели вместо путей по умолчанию (для R04/сервера)
# Потоки onnxruntime. «Все потоки» на гибридном процессоре ноутбука (24 потока, Intel P+E ядра) дали 103 мс на текст,
# 4 потока — 21 мс; в облаке на 4 vCPU 4 потока тоже лучше одного (11 против 15 мс). Поэтому по умолчанию 4.
ENV_THREADS = "BIRGE_CLF_V2_THREADS"
DEFAULT_THREADS = 4


def resolve_threads(threads: int | None) -> int:
    """None -> $BIRGE_CLF_V2_THREADS или min(4, число ядер); 0 -> решает onnxruntime (все потоки)."""
    if threads is None:
        env = os.environ.get(ENV_THREADS, "").strip()
        try:
            threads = int(env) if env else min(DEFAULT_THREADS, os.cpu_count() or DEFAULT_THREADS)
        except ValueError:
            threads = min(DEFAULT_THREADS, os.cpu_count() or DEFAULT_THREADS)
    return max(0, int(threads))


class ModelUnavailable(RuntimeError):
    """Нет файлов модели или не установлены нужные библиотеки."""


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


class _OnnxBackend:
    def __init__(self, model_dir: Path, onnx_file: Path, max_length: int, threads: int | None):
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ModelUnavailable("не установлен onnxruntime") from exc
        so = ort.SessionOptions()
        self.threads = resolve_threads(threads)
        if self.threads:
            so.intra_op_num_threads = self.threads
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(onnx_file), so, providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.session.get_inputs()}
        self.max_length = max_length
        self.file = onnx_file.name
        tok_json = model_dir / "tokenizer.json"
        self._hf = None
        try:
            from tokenizers import Tokenizer
            if not tok_json.exists():
                raise FileNotFoundError(tok_json)
            self.tok = Tokenizer.from_file(str(tok_json))
            self.tok.enable_truncation(max_length=max_length)
            pad_id = self.tok.token_to_id("<pad>")
            self.pad_id = 1 if pad_id is None else pad_id
            self.tok.no_padding()
        except (ImportError, FileNotFoundError):
            try:  # запасной путь: токенизатор transformers
                from transformers import AutoTokenizer
            except ImportError as exc:
                raise ModelUnavailable("нет tokenizers/transformers для токенизации") from exc
            self._hf = AutoTokenizer.from_pretrained(model_dir)

    def _encode(self, texts: list[str]) -> dict:
        if self._hf is not None:
            enc = self._hf(texts, padding=True, truncation=True, max_length=self.max_length, return_tensors="np")
            ids, mask = enc["input_ids"].astype(np.int64), enc["attention_mask"].astype(np.int64)
        else:
            encs = self.tok.encode_batch(texts)
            width = max(len(e.ids) for e in encs)
            ids = np.full((len(texts), width), self.pad_id, dtype=np.int64)
            mask = np.zeros((len(texts), width), dtype=np.int64)
            for i, e in enumerate(encs):
                ids[i, :len(e.ids)] = e.ids
                mask[i, :len(e.ids)] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        return {k: v for k, v in feed.items() if k in self.input_names}

    def logits(self, texts: list[str]) -> np.ndarray:
        return self.session.run(["logits"], self._encode(texts))[0]


class _TorchBackend:
    def __init__(self, model_dir: Path):
        try:
            from ml.civic_classifier_v2 import transformer as T
            self.tm = T.load(model_dir)
        except ImportError as exc:
            raise ModelUnavailable("не установлены torch/transformers") from exc
        self.file = "pytorch"

    def logits(self, texts: list[str]) -> np.ndarray:
        import torch
        tm = self.tm
        enc = tm.tokenizer(texts, padding=True, truncation=True, max_length=tm.cfg.max_length, return_tensors="pt")
        enc = {k: v.to(tm.device) for k, v in enc.items() if k in ("input_ids", "attention_mask")}
        with torch.no_grad():
            return tm.model(**enc).logits.float().cpu().numpy()


class Classifier:
    def __init__(self, model_dir: Path, meta: dict, backend, backend_name: str):
        self.model_dir = Path(model_dir)
        self.meta = meta
        self.labels = tuple(meta["labels"])
        self._backend = backend
        self.backend = backend_name
        self.threshold = float(meta.get("threshold", 1.0))
        self.model_version = meta.get("model_version", "civic-clf-v2-unknown")
        self.human_eval = (meta.get("human_eval") or {}).get("status", "NOT_EVALUATED")
        self.training_data = meta.get("training_data", "unknown")
        # Порогу доверяем, только если в обучении были тексты людей и рецепт проверен на людях.
        self.always_review = meta.get("review_policy") != "threshold" or self.human_eval != "EVALUATED"
        if self.labels != L.labels():
            raise ModelUnavailable("метки модели не совпадают с categories_v2.json — переобучите модель")

    # ---------- загрузка ----------
    @classmethod
    def load(cls, path: Path | None = None, backend: str = "auto", threads: int | None = None) -> "Classifier":
        env_dir = os.environ.get(ENV_DIR, "").strip()
        dirs = [Path(path)] if path else [Path(env_dir)] if env_dir else list(DEFAULT_DIRS)
        errors = []
        for d in dirs:
            meta_path = d / META_NAME
            if not meta_path.exists():
                errors.append(f"{d}: нет {META_NAME}")
                continue
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            max_len = int((meta.get("train_config") or {}).get("max_length", 128))
            if backend in ("auto", "onnx"):
                for name in ("model.int8.onnx", "model.onnx"):
                    f = d / name
                    if f.exists():
                        return cls(d, meta, _OnnxBackend(d, f, max_len, threads), f"onnx:{name}")
                if backend == "onnx":
                    errors.append(f"{d}: нет model.int8.onnx / model.onnx")
                    continue
            if backend in ("auto", "torch") and (d / "config.json").exists():
                return cls(d, meta, _TorchBackend(d), "torch")
            errors.append(f"{d}: нет файлов модели для backend={backend}")
        raise ModelUnavailable("; ".join(errors) or "модель не найдена")

    # ---------- применение ----------
    def predict_proba(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, len(self.labels)))
        out = []
        for i in range(0, len(texts), batch_size):
            chunk = [str(t)[:MAX_TEXT] for t in texts[i:i + batch_size]]
            out.append(_softmax(np.asarray(self._backend.logits(chunk), dtype=np.float64)))
        return np.concatenate(out, axis=0)

    def classify(self, text) -> dict:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        letters = sum(ch.isalpha() for ch in text)
        if letters < MIN_LETTERS:
            # Пустое/бессодержательное сообщение: модель не применяем.
            return {"category": L.OTHER, "score": 0.0, "needs_review": True, "model_version": self.model_version,
                    "top3": []}
        p = self.predict_proba([text])[0]
        order = np.argsort(-p, kind="stable")[:3]
        best = int(order[0])
        score = round(float(p[best]), 4)
        needs_review = self.always_review or score < self.threshold or self.labels[best] == L.OTHER
        return {"category": self.labels[best], "score": score, "needs_review": bool(needs_review),
                "model_version": self.model_version,
                "top3": [{"category": self.labels[int(i)], "score": round(float(p[int(i)]), 4)} for i in order]}

    def info(self) -> dict:
        return {"model_version": self.model_version, "backend": self.backend, "threshold": self.threshold,
                "human_eval": self.human_eval, "always_review": self.always_review,
                "threads": getattr(self._backend, "threads", None),
                "training_data": self.training_data, "labels": list(self.labels)}


_default: dict = {}
_lock = threading.Lock()


def get_default() -> Classifier:
    """Ленивая однократная загрузка модели по умолчанию; ошибка запоминается (файл не перечитывается)."""
    if "clf" in _default:
        return _default["clf"]
    if "error" in _default:
        raise ModelUnavailable(_default["error"])
    with _lock:
        if "clf" not in _default and "error" not in _default:
            try:
                _default["clf"] = Classifier.load()
            except ModelUnavailable as exc:
                _default["error"] = str(exc)
                raise
    return _default["clf"]


def classify(text: str) -> dict:
    """Функция для R04: ответ по контракту POST /classify. Нет модели -> ModelUnavailable."""
    return get_default().classify(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ml.civic_classifier_v2.predict")
    ap.add_argument("text", nargs="*", help="тексты; без аргументов — по строке из stdin")
    ap.add_argument("--model", help="папка модели (по умолчанию artifacts/onnx, затем artifacts/final)")
    ap.add_argument("--backend", choices=("auto", "onnx", "torch"), default="auto")
    args = ap.parse_args(argv)
    try:
        clf = Classifier.load(Path(args.model) if args.model else None, args.backend)
    except ModelUnavailable as exc:
        print(f"модель недоступна: {exc}", file=sys.stderr)
        return 2
    texts = args.text or [line.strip() for line in sys.stdin if line.strip()]
    print(json.dumps(clf.info(), ensure_ascii=False))
    for t in texts:
        t0 = time.perf_counter()
        res = clf.classify(t)
        res["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
